"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  listLinkedAccounts,
  listSocialAccounts,
  saveLinkedAccounts,
} from "@/lib/contentApi";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";

const POSTBRIDGE_URL = "https://app.post-bridge.com";

// Resolve a real profile picture from the handle (best-effort, falls back to a
// monogram on error). PostBridge itself doesn't return avatars.
function avatarUrl(platform, username) {
  if (!username) return "";
  return `https://unavatar.io/${platform}/${encodeURIComponent(username)}?fallback=false`;
}

/**
 * Accounts tab — link the project's social accounts.
 *
 * Lists the PostBridge accounts available to the user and lets them select
 * which ones are linked to this project. The linked set is persisted (DB) and
 * pre-selected when scheduling / used for analytics.
 */
export default function AccountsTab({ projectId }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [accounts, setAccounts] = useState([]);
  const [linkedIds, setLinkedIds] = useState(() => new Set());
  const [saving, setSaving] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const [available, linked] = await Promise.all([
          listSocialAccounts(projectId),
          listLinkedAccounts(projectId).catch(() => []),
        ]);
        if (cancelled) return;
        setAccounts(Array.isArray(available) ? available : []);
        setLinkedIds(new Set((linked || []).map((a) => Number(a.account_id))));
      } catch (e) {
        if (!cancelled) setError(e.message || "Failed to load accounts.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  const grouped = useMemo(() => {
    const map = {};
    for (const a of accounts) (map[a.platform] ||= []).push(a);
    return Object.entries(map).sort((a, b) =>
      platformMeta(a[0]).label.localeCompare(platformMeta(b[0]).label)
    );
  }, [accounts]);

  async function persist(nextSet) {
    const payload = accounts
      .filter((a) => nextSet.has(Number(a.id)))
      .map((a) => ({ account_id: Number(a.id), platform: a.platform, username: a.username }));
    setSaving(true);
    try {
      await saveLinkedAccounts(projectId, payload);
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 1500);
    } catch (e) {
      setError(e.message || "Failed to save. Please try again.");
      throw e;
    } finally {
      setSaving(false);
    }
  }

  async function setLinked(ids) {
    const prev = linkedIds;
    setLinkedIds(ids); // optimistic
    try {
      await persist(ids);
    } catch {
      setLinkedIds(prev); // revert
    }
  }

  function toggle(account) {
    const id = Number(account.id);
    const next = new Set(linkedIds);
    next.has(id) ? next.delete(id) : next.add(id);
    setLinked(next);
  }

  const allIds = useMemo(() => accounts.map((a) => Number(a.id)), [accounts]);
  const allLinked = allIds.length > 0 && allIds.every((id) => linkedIds.has(id));

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading accounts…</p>;
  }

  if (accounts.length === 0) {
    return (
      <div className="mx-auto max-w-md rounded-2xl border border-dashed border-border/70 p-10 text-center">
        <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <Plus className="size-5" />
        </div>
        <h3 className="text-sm font-semibold">No accounts available yet</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {error
            ? error
            : "Connect a TikTok, Instagram, or YouTube account in PostBridge, then refresh to link it to this project."}
        </p>
        <Button className="mt-4" asChild>
          <a href={POSTBRIDGE_URL} target="_blank" rel="noreferrer">Connect in PostBridge →</a>
        </Button>
      </div>
    );
  }

  return (
    <div className="max-w-4xl space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Linked accounts</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Choose which accounts this project posts to — they&apos;re pre-selected when
            scheduling and used for analytics.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <SaveState saving={saving} saved={savedFlash} count={linkedIds.size} />
          <Button
            variant="outline"
            size="sm"
            disabled={saving || allIds.length === 0}
            onClick={() => setLinked(new Set(allLinked ? [] : allIds))}
          >
            {allLinked ? "Unlink all" : "Link all"}
          </Button>
        </div>
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}

      {/* Per-platform groups */}
      <div className="space-y-6">
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
                    key={a.id}
                    account={a}
                    linked={linkedIds.has(Number(a.id))}
                    busy={saving}
                    onToggle={() => toggle(a)}
                  />
                ))}
              </div>
            </section>
          );
        })}
      </div>

      <p className="text-xs text-muted-foreground/70">
        Profile pictures are resolved from public handles. PostBridge doesn&apos;t expose
        bios or follower counts, so those aren&apos;t shown.
      </p>
    </div>
  );
}

function AccountCard({ account, linked, busy, onToggle }) {
  return (
    <article
      className={`group relative flex items-center gap-3 rounded-xl border p-3 transition-all ${
        linked
          ? "border-primary/40 bg-primary/[0.04] ring-1 ring-primary/20"
          : "border-border bg-card hover:border-primary/30 hover:bg-muted/30"
      }`}
    >
      <AccountAvatar account={account} linked={linked} />

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold">@{account.username}</p>
        <p className="truncate text-xs text-muted-foreground">
          {platformMeta(account.platform).label} · #{account.id}
        </p>
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
            <Check className="size-3.5" /> Linked
          </>
        ) : (
          "Link"
        )}
      </Button>
    </article>
  );
}

function AccountAvatar({ account, linked }) {
  const meta = platformMeta(account.platform);
  const [imgFailed, setImgFailed] = useState(false);
  const src = imgFailed ? "" : avatarUrl(account.platform, account.username);
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
        <><Loader2 className="size-3.5 animate-spin" /> Saving…</>
      ) : saved ? (
        <><Check className="size-3.5 text-green-500" /> Saved</>
      ) : (
        <><span className="font-medium text-foreground tabular-nums">{count}</span> linked</>
      )}
    </span>
  );
}
