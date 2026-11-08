"use client";

import { useEffect, useMemo, useState } from "react";
import { BarChart3, CalendarClock, Check, ExternalLink, Plus, RefreshCw, Users } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Spinner } from "@/components/ui/spinner";
import { Button } from "@/components/ui/button";
import { useConfirm } from "@/components/ui/confirm-dialog";
import {
  connectVendorKey,
  disconnectVendorKey,
  listLinkedAccounts,
  listPublishers,
  listSocialAccounts,
  saveLinkedAccounts,
} from "@/lib/contentApi";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";
import VendorKeyForm from "./VendorKeyForm";
import ConnectorGate, { ReportedPlatforms, schedulerOptions } from "./ConnectorGate";
import LoadError from "@/components/LoadError";

// A scheduler's own picture when it has one (Zernio does), else one resolved
// from the public handle (best-effort, falls back to a monogram on error).
function avatarUrl(account) {
  if (account.avatar_url) return account.avatar_url;
  if (!account.username) return "";
  return `https://unavatar.io/${account.platform}/${encodeURIComponent(account.username)}?fallback=false`;
}

// Accounts are unique per scheduler, not overall: two schedulers can number
// theirs the same.
const accountKey = (a) => `${a.publisher || ""}:${a.id ?? a.account_id}`;

/**
 * Accounts tab — connect a scheduler, then link the project's social accounts.
 *
 * Schedulers (PostBridge, Zernio: the server's list, `listPublishers`) are
 * connectors the project's owner brings with their own API key. Nothing is a
 * default: with none connected, nothing publishes, and the tab says so. Each
 * connected scheduler's accounts are listed together, tagged with the one
 * that holds them, and the linked set (persisted) is what a post goes out
 * through and what analytics read.
 *
 * `load` stands in for the three reads in /preview.
 */
export default function AccountsTab({ projectId, load = loadAccounts }) {
  const { t } = useLingui();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [publishers, setPublishers] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [linkedKeys, setLinkedKeys] = useState(() => new Set());
  const [saving, setSaving] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);
  // A list that never arrived is not an empty list: the two states used to
  // share `error` and render as "No accounts available yet", which tells
  // someone whose request simply failed that they have nothing connected.
  const [loadError, setLoadError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const { confirm, dialog } = useConfirm();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      setLoadError("");
      try {
        const out = await load(projectId);
        if (cancelled) return;
        setPublishers(out.publishers);
        setAccounts(out.accounts);
        setLinkedKeys(new Set(out.linked.map(accountKey)));
      } catch (e) {
        if (!cancelled) setLoadError(e.message || "");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [projectId, reloadKey, load]);

  const connected = publishers.filter((p) => p.connected);

  const grouped = useMemo(() => {
    const map = {};
    for (const a of accounts) (map[a.platform] ||= []).push(a);
    return Object.entries(map).sort((a, b) =>
      platformMeta(a[0]).label.localeCompare(platformMeta(b[0]).label)
    );
  }, [accounts]);

  async function persist(nextSet) {
    const payload = accounts
      .filter((a) => nextSet.has(accountKey(a)))
      .map((a) => ({ account_id: a.id, publisher: a.publisher, platform: a.platform, username: a.username }));
    setSaving(true);
    try {
      await saveLinkedAccounts(projectId, payload);
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 1500);
    } catch (e) {
      setError(e.message || t`That didn't save — your selection has been put back. Try again.`);
      throw e;
    } finally {
      setSaving(false);
    }
  }

  async function setLinked(keys) {
    const prev = linkedKeys;
    setLinkedKeys(keys); // optimistic
    try {
      await persist(keys);
    } catch {
      setLinkedKeys(prev); // revert
    }
  }

  function toggle(account) {
    const key = accountKey(account);
    const next = new Set(linkedKeys);
    next.has(key) ? next.delete(key) : next.add(key);
    setLinked(next);
  }

  async function connect(publisher, apiKey) {
    await connectVendorKey(publisher.id, apiKey);
    setReloadKey((k) => k + 1);
  }

  async function disconnect(publisher) {
    const scheduler = publisher.label;
    const ok = await confirm({
      title: t`Disconnect ${scheduler}?`,
      description: t`Duct forgets your API key and stops publishing through your ${scheduler} account. Your accounts stay connected in ${scheduler}, and posts already scheduled there still go out.`,
      action: t`Disconnect`,
      destructive: true,
    });
    if (!ok) return;
    try {
      await disconnectVendorKey(publisher.id);
      setReloadKey((k) => k + 1);
    } catch (e) {
      setError(e.message || t`That didn't disconnect. Try again.`);
    }
  }

  const allKeys = useMemo(() => accounts.map(accountKey), [accounts]);
  const allLinked = allKeys.length > 0 && allKeys.every((k) => linkedKeys.has(k));

  if (loading) {
    return <p className="text-sm text-muted-foreground"><Trans>Loading accounts…</Trans></p>;
  }

  if (loadError) {
    return (
      <LoadError
        what={t`your social accounts`}
        detail={loadError}
        onRetry={() => setReloadKey((k) => k + 1)}
      />
    );
  }

  if (connected.length === 0) {
    return (
      <div className="max-w-6xl">
        <ConnectorGate
          title={t`Post to all your accounts from one place`}
          lead={t`Connect a scheduler and Duct publishes for you: link several accounts, schedule each post for its best time, and see how it did.`}
          benefits={[
            { icon: Users, title: t`Several accounts, one project`, text: t`LinkedIn, X, TikTok, Instagram and YouTube, side by side.` },
            { icon: CalendarClock, title: t`Scheduled for you`, text: t`Approve a draft and it goes out at its best time. No copying and pasting.` },
            { icon: BarChart3, title: t`Numbers come back`, text: t`Views, likes and shares land on each post, and the next plan learns from them.` },
          ]}
          connectLabel={t`Connect a scheduler to start`}
          connectors={schedulerOptions(publishers, connect)}
          footnote={t`Your own account and API key, stored encrypted. Duct posts only when you ask it to.`}
          example={<AccountsExample />}
        />
        {error && <p className="mt-3 text-xs text-destructive">{error}</p>}
        {dialog}
      </div>
    );
  }

  return (
    <div className="max-w-4xl space-y-8">
      <Schedulers publishers={publishers} onConnect={connect} onDisconnect={disconnect} />

      {connected.length > 0 && (accounts.length === 0 ? (
        <NoAccounts connected={connected} onRefresh={() => setReloadKey((k) => k + 1)} />
      ) : (
        <section className="space-y-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold"><Trans>Linked accounts</Trans></h2>
              <p className="mt-0.5 text-sm text-muted-foreground">
                <Trans>
                  Choose which accounts this project posts to — they&apos;re pre-selected when
                  scheduling and used for analytics.
                </Trans>
              </p>
            </div>
            <div className="flex items-center gap-3">
              <SaveState saving={saving} saved={savedFlash} count={linkedKeys.size} />
              <Button
                variant="outline"
                size="sm"
                disabled={saving || allKeys.length === 0}
                onClick={() => setLinked(new Set(allLinked ? [] : allKeys))}
              >
                {allLinked ? <Trans>Unlink all</Trans> : <Trans>Link all</Trans>}
              </Button>
            </div>
          </div>

          {error && <p className="text-xs text-destructive">{error}</p>}

          {grouped.map(([platform, list]) => {
            const meta = platformMeta(platform);
            return (
              <section key={platform} className="space-y-2.5">
                <div className="flex items-center gap-2">
                  <PlatformGlyph platform={platform} className="size-4" />
                  <h3 className="text-sm font-medium">{meta.label}</h3>
                  <span className="text-xs tabular-nums text-muted-foreground">{list.length}</span>
                </div>
                <div className="grid grid-cols-1 gap-3 @lg:grid-cols-2">
                  {list.map((a) => (
                    <AccountCard
                      key={accountKey(a)}
                      account={a}
                      linked={linkedKeys.has(accountKey(a))}
                      busy={saving}
                      onToggle={() => toggle(a)}
                    />
                  ))}
                </div>
              </section>
            );
          })}
        </section>
      ))}
      {error && accounts.length === 0 && <p className="text-xs text-destructive">{error}</p>}
      {dialog}
    </div>
  );
}

// What the tab holds once a scheduler is connected, drawn by the real card.
const EXAMPLE_ACCOUNTS = [
  { id: "1", publisher: "example", publisher_label: "Zernio", platform: "linkedin", username: "yourbrand", linked: true },
  { id: "2", publisher: "example", publisher_label: "Zernio", platform: "twitter", username: "yourbrand", linked: true },
  { id: "3", publisher: "example", publisher_label: "PostBridge", platform: "tiktok", username: "yourbrand.app", linked: false },
];

function AccountsExample() {
  return (
    <div className="grid grid-cols-1 gap-3">
      {EXAMPLE_ACCOUNTS.map((a) => (
        <AccountCard key={a.id} account={{ ...a, avatar_url: "" }} linked={a.linked} busy={false} onToggle={() => {}} noAvatar />
      ))}
    </div>
  );
}

async function loadAccounts(projectId) {
  const publishers = await listPublishers(projectId);
  if (!publishers.some((p) => p.connected)) return { publishers, accounts: [], linked: [] };
  const [accounts, linked] = await Promise.all([
    listSocialAccounts(projectId),
    listLinkedAccounts(projectId).catch(() => []),
  ]);
  return { publishers, accounts: Array.isArray(accounts) ? accounts : [], linked: linked || [] };
}

/** Every scheduler, connected or not, with what each one reports. */
function Schedulers({ publishers, onConnect, onDisconnect }) {
  const none = !publishers.some((p) => p.connected);
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-base font-semibold"><Trans>Scheduler</Trans></h2>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {none
            ? <Trans>Duct publishes through a scheduler you connect, with your own account. Connect one to schedule posts and see how they do.</Trans>
            : <Trans>Duct publishes through these, with your own accounts, and reads each post&apos;s numbers back from them.</Trans>}
        </p>
      </div>
      <div className="grid grid-cols-1 gap-3 @2xl:grid-cols-2">
        {publishers.map((p) => (
          <SchedulerCard key={p.id} publisher={p} onConnect={onConnect} onDisconnect={onDisconnect} />
        ))}
      </div>
    </section>
  );
}

function SchedulerCard({ publisher, onConnect, onDisconnect }) {
  const [open, setOpen] = useState(false);
  const scheduler = publisher.label;
  return (
    <article
      className={`flex flex-col gap-3 rounded-xl border p-4 ${
        publisher.connected ? "border-primary/40 bg-primary/[0.04]" : "border-border bg-card"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">{scheduler}</h3>
          <p className="mt-0.5 inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            {publisher.connected ? (
              <><Check className="size-3.5 text-success" aria-hidden /> <Trans>Connected</Trans></>
            ) : (
              <Trans>Not connected</Trans>
            )}
          </p>
        </div>
        {!publisher.connected && !open && (
          <Button size="sm" onClick={() => setOpen(true)}><Trans>Connect</Trans></Button>
        )}
      </div>

      {publisher.reports?.length > 0 && <ReportedPlatforms platforms={publisher.reports} />}

      {open && !publisher.connected && (
        <VendorKeyForm
          layout="inline"
          vendor={scheduler}
          homeUrl={publisher.dashboard_url}
          isOwner={publisher.is_owner}
          onConnect={(apiKey) => onConnect(publisher, apiKey)}
        />
      )}

      {publisher.connected && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          <a
            href={publisher.dashboard_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            <Trans>Add accounts in {scheduler}</Trans>
            <ExternalLink className="size-3" aria-hidden />
          </a>
          {publisher.own_key && publisher.is_owner && (
            <Button variant="link" size="sm" className="h-auto p-0 text-xs text-muted-foreground" onClick={() => onDisconnect(publisher)}>
              <Trans>Disconnect</Trans>
            </Button>
          )}
        </div>
      )}
    </article>
  );
}

function NoAccounts({ connected, onRefresh }) {
  return (
    <div className="mx-auto max-w-md rounded-2xl border border-dashed border-border/70 p-10 text-center">
      <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Plus className="size-5" />
      </div>
      <h3 className="text-sm font-semibold"><Trans>No accounts available yet</Trans></h3>
      <p className="mt-1 text-sm text-muted-foreground">
        <Trans>
          Connect your LinkedIn, X, TikTok, Instagram or YouTube account in your scheduler, then
          refresh to link it to this project.
        </Trans>
      </p>
      <div className="mt-4 flex flex-wrap justify-center gap-2">
        {connected.map((p) => (
          <SchedulerLink key={p.id} publisher={p} />
        ))}
        <Button variant="outline" onClick={onRefresh}>
          <RefreshCw className="size-3.5" aria-hidden /> <Trans>Refresh</Trans>
        </Button>
      </div>
    </div>
  );
}

function SchedulerLink({ publisher }) {
  const scheduler = publisher.label;
  return (
    <Button asChild>
      <a href={publisher.dashboard_url} target="_blank" rel="noreferrer"><Trans>Open {scheduler} →</Trans></a>
    </Button>
  );
}

function AccountCard({ account, linked, busy, onToggle, noAvatar = false }) {
  const scheduler = account.publisher_label;
  const platform = platformMeta(account.platform).label;
  return (
    <article
      className={`group relative flex items-center gap-3 rounded-xl border p-3 transition-all ${
        linked
          ? "border-primary/40 bg-primary/[0.04] ring-1 ring-primary/20"
          : "border-border bg-card hover:border-primary/30 hover:bg-muted/30"
      }`}
    >
      <AccountAvatar account={account} linked={linked} noAvatar={noAvatar} />

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold">@{account.username}</p>
        <p className="truncate text-xs text-muted-foreground">
          {scheduler ? <Trans>{platform} · via {scheduler}</Trans> : platform}
        </p>
        {account.needs_reconnect && (
          <p className="truncate text-xs text-warning"><Trans>Reconnect it in {scheduler}</Trans></p>
        )}
      </div>

      <Button
        type="button"
        size="sm"
        variant={linked ? "outline" : "default"}
        disabled={busy}
        onClick={onToggle}
        className="shrink-0"
      >
        {linked ? (
          <>
            <Check className="size-3.5" /> <Trans>Linked</Trans>
          </>
        ) : (
          <Trans>Link</Trans>
        )}
      </Button>
    </article>
  );
}

function AccountAvatar({ account, linked, noAvatar }) {
  const meta = platformMeta(account.platform);
  const [imgFailed, setImgFailed] = useState(false);
  // The example's handles are invented, so it never asks a third party for a face.
  const src = imgFailed || noAvatar ? "" : avatarUrl(account);
  const initial = (account.username || "?").charAt(0).toUpperCase();

  return (
    <div className="relative shrink-0">
      <div className="flex size-11 items-center justify-center overflow-hidden rounded-full border border-border/60 bg-muted">
        {src ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt=""
            className="size-full object-cover"
            referrerPolicy="no-referrer"
            onError={() => setImgFailed(true)}
          />
        ) : (
          <span className="text-sm font-semibold text-muted-foreground">{initial}</span>
        )}
      </div>
      {/* Platform badge — brand-colored chip with a white glyph (legible on both themes) */}
      <span
        className="absolute -bottom-0.5 -right-0.5 flex size-5 items-center justify-center rounded-full border-2 border-card text-white"
        title={meta.label}
        style={{ backgroundColor: meta.color }}
      >
        <PlatformGlyph platform={account.platform} className="size-3" />
      </span>
      {linked && (
        <span className="absolute -left-0.5 -top-0.5 flex size-4 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <Check className="size-2.5" />
        </span>
      )}
    </div>
  );
}

function SaveState({ saving, saved, count }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      {saving ? (
        <><Spinner className="size-3.5" /> <Trans>Saving…</Trans></>
      ) : saved ? (
        <><Check className="size-3.5 text-success" /> <Trans>Saved</Trans></>
      ) : (
        <Trans><span className="font-medium text-foreground tabular-nums">{count}</span> linked</Trans>
      )}
    </span>
  );
}
