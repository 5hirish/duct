"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  CalendarClock,
  Check,
  ChevronDown,
  Circle,
  CircleDot,
  ExternalLink,
  RefreshCw,
  Users,
} from "lucide-react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { Spinner } from "@/components/ui/spinner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { HelpTip } from "@/components/ui/page";
import { SkeletonList } from "@/components/ui/skeleton";
import { useConfirm } from "@/components/ui/confirm-dialog";
import {
  connectVendorKey,
  disconnectVendorKey,
  getChannels,
  listLinkedAccounts,
  listPublishers,
  listSocialAccounts,
  saveChannels,
  saveLinkedAccounts,
} from "@/lib/contentApi";
import { MediaKind, MEDIA_KIND_LABELS } from "@/lib/contentEnums";
import { cn } from "@/lib/utils";
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

// The save-state key for the primary-scheduler choice, beside the channel ids.
const PRIMARY_SAVE = "__primary";
const SAVED_FLASH_MS = 1500;

const EMPTY_PROFILE = Object.freeze({
  enabled: false, username: "", display_name: "", bio: "", notes: "", target_media: [],
});

// The kinds a channel can be asked to post, when its guide does not say.
const POST_MEDIA = [MediaKind.VIDEO, MediaKind.SLIDESHOW, MediaKind.IMAGE, MediaKind.TEXT];

const API_SAVE = Object.freeze({ linked: saveLinkedAccounts, channels: saveChannels });

/**
 * Accounts tab: the schedulers posts go out through, and the channels Duct
 * plans for.
 *
 * Schedulers (PostBridge, Zernio: the server's list, `listPublishers`) are
 * connectors the project's owner brings with their own API key. Two can be
 * connected; ONE is primary, and that is the one a post goes out through,
 * so only its accounts can be linked. Channels are first-class with or
 * without a scheduler: every one Duct offers is a row with a switch, and a
 * channel that is on with no account behind it is posted by hand. What the
 * person says about each channel (handle, bio, notes, which media) rides
 * into the agent's opening turn beside the platform guide shown on the row.
 *
 * `load` stands in for the four reads and `save` for the two writes in
 * /preview; `defaultOpen` / `defaultGuideOpen` name channel rows and guide
 * disclosures to open on mount, so a state is reachable by URL.
 */
export default function AccountsTab({
  projectId,
  load = loadAccounts,
  save = API_SAVE,
  defaultOpen = [],
  defaultGuideOpen = [],
}) {
  const { t } = useLingui();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [publishers, setPublishers] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [linkedKeys, setLinkedKeys] = useState(() => new Set());
  const [channels, setChannels] = useState([]);
  // The channel config as one value, so a save sends everything the server
  // replaces; a ref carries the latest through two quick toggles.
  const [config, setConfig] = useState({ primary: "", profiles: {} });
  const configRef = useRef(config);
  configRef.current = config;
  const [saving, setSaving] = useState(false);
  const [linkErrorFor, setLinkErrorFor] = useState("");
  const [savedFlash, setSavedFlash] = useState(false);
  // Per channel (and the primary choice): "saving" | "saved" | undefined.
  const [saveState, setSaveState] = useState({});
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
        const list = out.channels?.channels || [];
        setChannels(list);
        setConfig({
          primary: out.channels?.primary_publisher || "",
          profiles: Object.fromEntries(list.map((c) => [c.id, { ...EMPTY_PROFILE, ...c.profile }])),
        });
      } catch (e) {
        if (!cancelled) setLoadError(e.message || "");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [projectId, reloadKey, load]);

  const connected = publishers.filter((p) => p.connected);
  // A stored primary that was since disconnected is no primary; one connected
  // scheduler is the primary without being asked, and the first save keeps it.
  const primary = connected.some((p) => p.id === config.primary)
    ? config.primary
    : connected.length === 1 ? connected[0].id : "";
  const primaryLabel = publishers.find((p) => p.id === primary)?.label || "";

  const linkedAtPrimary = useMemo(
    () => accounts.filter((a) => a.publisher === primary && linkedKeys.has(accountKey(a))),
    [accounts, primary, linkedKeys],
  );

  function mark(key, state) {
    setSaveState((s) => ({ ...s, [key]: state }));
  }
  function flash(key) {
    mark(key, "saved");
    setTimeout(() => setSaveState((s) => (s[key] === "saved" ? { ...s, [key]: undefined } : s)), SAVED_FLASH_MS);
  }

  async function persistLinked(nextSet) {
    const payload = accounts
      .filter((a) => nextSet.has(accountKey(a)))
      .map((a) => ({ account_id: a.id, publisher: a.publisher, platform: a.platform, username: a.username }));
    setSaving(true);
    try {
      await save.linked(projectId, payload);
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), SAVED_FLASH_MS);
    } catch (e) {
      setError(e.message || t`That didn't save — your selection has been put back. Try again.`);
      throw e;
    } finally {
      setSaving(false);
    }
  }

  async function setLinked(keys, channelId = "") {
    const prev = linkedKeys;
    setLinkedKeys(keys); // optimistic
    setLinkErrorFor("");
    try {
      await persistLinked(keys);
    } catch {
      setLinkedKeys(prev); // revert
      // The error line at the top of the section can be off screen when the
      // click was deep in a channel's panel; say it there too.
      setLinkErrorFor(channelId);
    }
  }

  /** Save the whole channel config, optimistic, reverting on failure. */
  async function commitChannels(next, key) {
    const prev = configRef.current;
    setConfig(next);
    configRef.current = next;
    mark(key, "saving");
    try {
      await save.channels(projectId, { primaryPublisher: next.primary, channels: next.profiles });
      flash(key);
    } catch (e) {
      setConfig(prev);
      configRef.current = prev;
      mark(key, undefined);
      setError(e.message || t`That didn't save — your change has been put back. Try again.`);
    }
  }

  function setProfile(channelId, patch) {
    const cur = configRef.current;
    const profile = { ...EMPTY_PROFILE, ...cur.profiles[channelId], ...patch };
    commitChannels({ primary, profiles: { ...cur.profiles, [channelId]: profile } }, channelId);
  }

  function choosePrimary(publisherId) {
    if (publisherId === primary) return;
    commitChannels({ ...configRef.current, primary: publisherId }, PRIMARY_SAVE);
  }

  function toggleAccount(account) {
    const key = accountKey(account);
    const next = new Set(linkedKeys);
    next.has(key) ? next.delete(key) : next.add(key);
    setLinked(next, account.platform);
    if (!next.has(key)) return;
    // Linking is the selection for this project, so it does the whole job: the
    // channel goes on (a Linked account under an Off channel is a
    // contradiction), the profile takes the account's own metadata where the
    // person typed nothing, and every media kind the channel takes is on
    // (an empty list). Unlinking leaves all of it alone.
    const cur = { ...EMPTY_PROFILE, ...configRef.current.profiles[account.platform] };
    const fill = (field, value) => (cur[field] ? cur[field] : String(value || "").trim());
    setProfile(account.platform, {
      enabled: true,
      username: fill("username", String(account.username || "").replace(/^@/, "")),
      display_name: fill("display_name", account.display_name),
      bio: fill("bio", account.bio),
      target_media: [],
    });
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

  if (loading) {
    return <SkeletonList rows={5} label={t`Loading accounts`} className="max-w-4xl" />;
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

  const onCount = channels.filter((c) => config.profiles[c.id]?.enabled).length;
  const linkedCount = linkedAtPrimary.length;

  return (
    <div className="max-w-4xl space-y-10">
      <section className="space-y-4">
        {/* The gate carries its own title, so the section heading would be a second one over it. */}
        {connected.length > 0 && (
          <SectionHead title={<Trans>Schedulers</Trans>}>
            {primary ? <Trans>Posts go out through {primaryLabel}.</Trans> : <Trans>Pick the one posts go out through.</Trans>}
          </SectionHead>
        )}

        {connected.length === 0 ? (
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
        ) : (
          <Schedulers
            publishers={publishers}
            primary={primary}
            primarySaving={saveState[PRIMARY_SAVE] === "saving"}
            onChoosePrimary={choosePrimary}
            onConnect={connect}
            onDisconnect={disconnect}
          />
        )}

        {connected.length > 0 && accounts.length === 0 && (
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            <Trans>No accounts in {connected.map((p) => p.label).join(", ")} yet. Add them there, then refresh.</Trans>
            <Button variant="outline" size="sm" onClick={() => setReloadKey((k) => k + 1)}>
              <RefreshCw className="size-3.5" aria-hidden /> <Trans>Refresh</Trans>
            </Button>
          </p>
        )}
      </section>

      <section className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <SectionHead title={<Trans>Channels</Trans>}>
            {onCount === 0
              ? <Trans>None on yet. Switch on where this brand posts.</Trans>
              : primary
                ? <Trans>{onCount} on · {linkedCount} linked via {primaryLabel}</Trans>
                : <Trans>{onCount} on, all posted by hand</Trans>}
          </SectionHead>
          <SaveState saving={saving} saved={savedFlash} />
        </div>

        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

        <Card className="gap-0 p-0">
          {channels.map((channel, i) => (
            <ChannelRow
              key={channel.id}
              channel={channel}
              profile={config.profiles[channel.id] || EMPTY_PROFILE}
              accounts={accounts.filter((a) => a.platform === channel.id)}
              linkedKeys={linkedKeys}
              primary={primary}
              primaryLabel={primaryLabel}
              busy={saving}
              saveState={saveState[channel.id]}
              linkError={linkErrorFor === channel.id ? error : ""}
              first={i === 0}
              defaultOpen={defaultOpen.includes(channel.id)}
              defaultGuideOpen={defaultGuideOpen.includes(channel.id)}
              onEnable={(enabled) => setProfile(channel.id, { enabled })}
              onSaveProfile={(patch) => setProfile(channel.id, patch)}
              onToggleAccount={toggleAccount}
            />
          ))}
        </Card>
      </section>
      {dialog}
    </div>
  );
}

/** A section's heading with one line of state under it, at most. */
function SectionHead({ title, children }) {
  return (
    <div>
      <h2 className="text-base font-semibold">{title}</h2>
      {children && <p className="mt-0.5 text-sm text-muted-foreground">{children}</p>}
    </div>
  );
}

// What the tab holds once a scheduler is connected, drawn by the real card.
const EXAMPLE_ACCOUNTS = [
  { id: "1", publisher: "example", publisher_label: "Zernio", platform: "linkedin", username: "yourbrand", linked: true },
  { id: "2", publisher: "example", publisher_label: "Zernio", platform: "twitter", username: "yourbrand", linked: true },
  { id: "3", publisher: "example", publisher_label: "Zernio", platform: "tiktok", username: "yourbrand.app", linked: false },
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
  const [publishers, channels] = await Promise.all([listPublishers(projectId), getChannels(projectId)]);
  if (!publishers.some((p) => p.connected)) return { publishers, accounts: [], linked: [], channels };
  const [accounts, linked] = await Promise.all([
    listSocialAccounts(projectId),
    listLinkedAccounts(projectId).catch(() => []),
  ]);
  return { publishers, accounts: Array.isArray(accounts) ? accounts : [], linked: linked || [], channels };
}

/** Every scheduler, connected or not, and which one is primary. */
function Schedulers({ publishers, primary, primarySaving, onChoosePrimary, onConnect, onDisconnect }) {
  const { t } = useLingui();
  // The one posts go out through reads first, then the rest of the connected
  // ones, then those still to connect; choosing a new primary reorders.
  const rank = (p) => (p.id === primary ? 0 : p.connected ? 1 : 2);
  const ordered = [...publishers].sort((a, b) => rank(a) - rank(b));
  return (
    <div role="radiogroup" aria-label={t`Primary scheduler`} className="grid grid-cols-1 gap-3 @2xl:grid-cols-2">
      {ordered.map((p) => (
        <SchedulerCard
          key={p.id}
          publisher={p}
          isPrimary={p.id === primary}
          primarySaving={primarySaving}
          onChoosePrimary={() => onChoosePrimary(p.id)}
          onConnect={onConnect}
          onDisconnect={onDisconnect}
        />
      ))}
    </div>
  );
}

function SchedulerCard({ publisher, isPrimary, primarySaving, onChoosePrimary, onConnect, onDisconnect }) {
  const [open, setOpen] = useState(false);
  const scheduler = publisher.label;
  return (
    <Card size="sm" variant={isPrimary ? "hero" : "default"}>
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
        {publisher.connected ? (
          // A card that is not connected cannot be primary, so it has no radio.
          <button
            type="button"
            role="radio"
            aria-checked={isPrimary}
            disabled={primarySaving}
            onClick={onChoosePrimary}
            className={cn(
              "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg px-2 text-xs font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:opacity-70",
              isPrimary ? "text-brand" : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {isPrimary
              ? <CircleDot className="size-4" aria-hidden />
              : <Circle className="size-4" aria-hidden />}
            <Trans>Primary</Trans>
          </button>
        ) : (
          !open && <Button size="sm" onClick={() => setOpen(true)}><Trans>Connect</Trans></Button>
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
            className="inline-flex min-h-6 items-center gap-1 text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            <Trans>Add accounts in {scheduler}</Trans>
            <ExternalLink className="size-3" aria-hidden />
          </a>
          {publisher.own_key && publisher.is_owner && (
            <Button variant="link" size="sm" className="h-auto min-h-6 p-0 text-xs text-muted-foreground" onClick={() => onDisconnect(publisher)}>
              <Trans>Disconnect</Trans>
            </Button>
          )}
        </div>
      )}
    </Card>
  );
}

/**
 * One channel: the switch, one line of state, and behind the chevron its
 * accounts, the person's own words about it and the guide the agent reads.
 */
function ChannelRow({
  channel, profile, accounts, linkedKeys, primary, primaryLabel, busy, saveState, linkError = "",
  first, defaultOpen, defaultGuideOpen, onEnable, onSaveProfile, onToggleAccount,
}) {
  const { t } = useLingui();
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();
  const label = channel.label || platformMeta(channel.id).label;

  const atPrimary = accounts.filter((a) => a.publisher === primary);
  const elsewhere = accounts.filter((a) => a.publisher !== primary);
  const linkedAt = atPrimary.filter((a) => linkedKeys.has(accountKey(a)));
  const linkedHere = linkedAt.length;
  // What the scheduler knows about the linked account stands in for a field
  // the person has not typed: the form is never empty over a linked account.
  const seed = linkedAt[0];
  const shown = seed
    ? {
        ...profile,
        username: profile.username || String(seed.username || "").replace(/^@/, ""),
        display_name: profile.display_name || seed.display_name || "",
        bio: profile.bio || seed.bio || "",
      }
    : profile;

  return (
    <div className={cn(!first && "border-t border-border")}>
      <div className="flex items-center gap-3 px-4 py-3">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((o) => !o)}
          className="flex min-h-10 min-w-0 flex-1 items-center gap-3 rounded-lg text-left outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card"
        >
          <span
            className="flex size-8 shrink-0 items-center justify-center rounded-full text-white"
            style={{ backgroundColor: platformMeta(channel.id).color }}
            aria-hidden
          >
            <PlatformGlyph platform={channel.id} className="size-4" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">{label}</span>
            <span className="block truncate text-xs text-muted-foreground">
              {!profile.enabled ? <Trans>Off</Trans>
                : linkedHere > 0 ? <Trans><Plural value={linkedHere} one="# account" other="# accounts" /> via {primaryLabel}</Trans>
                : <Trans>Posting by hand</Trans>}
            </span>
          </span>
          <ChevronDown
            className={cn("size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
            aria-hidden
          />
        </button>
        <Switch
          checked={profile.enabled}
          onCheckedChange={onEnable}
          aria-label={t`Post on ${label}`}
          disabled={saveState === "saving"}
        />
      </div>

      {open && (
        <div id={panelId} className="space-y-6 border-t border-border/60 bg-muted/40 px-4 py-4">
          {channel.guide && (
            <ChannelGuide guide={channel.guide} label={label} defaultOpen={defaultGuideOpen} />
          )}

          {accounts.length > 0 && (
            <div className="space-y-2.5">
              <h4 className="text-xs font-medium text-muted-foreground">
                {atPrimary.length > 0 ? <Trans>Accounts via {primaryLabel}</Trans> : <Trans>Accounts</Trans>}
              </h4>
              <div className="grid grid-cols-1 gap-3 @lg:grid-cols-2">
                {atPrimary.map((a) => (
                  <AccountCard
                    key={accountKey(a)}
                    account={a}
                    linked={linkedKeys.has(accountKey(a))}
                    busy={busy}
                    onToggle={() => onToggleAccount(a)}
                  />
                ))}
                {elsewhere.map((a) => (
                  <AccountCard
                    key={accountKey(a)}
                    account={a}
                    linked={false}
                    busy
                    muted
                    onToggle={() => {}}
                  />
                ))}
              </div>
            </div>
          )}

          {linkError && <p role="alert" className="text-sm text-destructive">{linkError}</p>}

          <ProfileForm
            channel={channel}
            label={label}
            profile={shown}
            saveState={saveState}
            onSave={onSaveProfile}
          />
        </div>
      )}
    </div>
  );
}

/** The guide the agent is told: cadence in one line, limits as chips, the rest behind the "?". */
function ChannelGuide({ guide, label, defaultOpen }) {
  const { t } = useLingui();
  const lists = [
    { title: t`Make`, items: guide.formats },
    { title: t`Wins`, items: guide.wins },
    { title: t`Avoid`, items: guide.avoid },
  ].filter((l) => l.items?.length);
  return (
    <div className="space-y-2">
      <div className="min-w-0">
        {/* One chevron per card, the card's own: the rest of the guide is a "?" popover, not a second expander. */}
        <h4 className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
          <Trans>What Duct writes for {label}</Trans>
          {lists.length > 0 && (
            <HelpTip label={t`More about posting on ${label}`} defaultOpen={defaultOpen} className="-my-1.5">
              <dl className="grid gap-3 text-sm">
                {lists.map((l) => (
                  <div key={l.title}>
                    <dt className="font-medium">{l.title}</dt>
                    <dd>
                      <ul className="mt-1 space-y-1 text-muted-foreground">
                        {l.items.map((item) => <li key={item}>{item}</li>)}
                      </ul>
                    </dd>
                  </div>
                ))}
              </dl>
            </HelpTip>
          )}
        </h4>
        {guide.cadence && <p className="mt-0.5 text-sm">{guide.cadence}</p>}
      </div>
      {guide.limits?.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {guide.limits.map((limit) => (
            <li key={limit}>
              <Badge variant="secondary" className="h-auto whitespace-normal py-0.5 text-left font-normal text-muted-foreground">{limit}</Badge>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * The person's own words about their presence on a channel. Fields are a
 * draft until a blur or Save commits them; media chips commit on click.
 */
function ProfileForm({ channel, label, profile, saveState, onSave }) {
  const { t, i18n } = useLingui();
  const id = useId();
  const [draft, setDraft] = useState(profile);
  // A save that came back (or was put back) is the new baseline for the fields.
  useEffect(() => { setDraft(profile); }, [profile]);

  const textKeys = ["username", "display_name", "bio", "notes"];
  const dirty = textKeys.some((k) => (draft[k] || "") !== (profile[k] || ""));

  function commit() {
    if (!dirty) return;
    onSave(Object.fromEntries(textKeys.map((k) => [k, draft[k] || ""])));
  }

  const kinds = channel.long_form
    ? [MediaKind.ARTICLE]
    : (channel.guide?.media?.length ? channel.guide.media : POST_MEDIA);
  // An empty list means everything the channel takes, so it is drawn as every
  // chip on; taking one off writes the rest, and putting the last one back
  // returns to empty.
  const stored = new Set(profile.target_media || []);
  const picked = stored.size === 0 ? new Set(kinds) : stored;
  function toggleKind(kind) {
    const next = new Set(picked);
    next.has(kind) ? next.delete(kind) : next.add(kind);
    const all = kinds.every((k) => next.has(k));
    onSave({ target_media: all ? [] : kinds.filter((k) => next.has(k)) });
  }

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => { e.preventDefault(); commit(); }}
    >
      <h4 className="text-xs font-medium text-muted-foreground"><Trans>Your {label} account</Trans></h4>
      <div className="grid gap-3 @lg:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-handle`} className="text-xs"><Trans>Handle</Trans></Label>
          <Input
            id={`${id}-handle`}
            value={draft.username || ""}
            autoComplete="off"
            onChange={(e) => setDraft((d) => ({ ...d, username: e.target.value.replace(/^@/, "") }))}
            onBlur={commit}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-name`} className="text-xs"><Trans>Display name</Trans></Label>
          <Input
            id={`${id}-name`}
            value={draft.display_name || ""}
            autoComplete="off"
            onChange={(e) => setDraft((d) => ({ ...d, display_name: e.target.value }))}
            onBlur={commit}
          />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-bio`} className="text-xs"><Trans>Bio</Trans></Label>
        <Textarea
          id={`${id}-bio`}
          value={draft.bio || ""}
          className="min-h-16"
          onChange={(e) => setDraft((d) => ({ ...d, bio: e.target.value }))}
          onBlur={commit}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-notes`} className="text-xs"><Trans>What to know about this channel</Trans></Label>
        <Textarea
          id={`${id}-notes`}
          value={draft.notes || ""}
          className="min-h-16"
          onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))}
          onBlur={commit}
        />
      </div>
      <div className="space-y-1.5">
        <p id={`${id}-media`} className="text-xs font-medium"><Trans>Post only</Trans></p>
        <div role="group" aria-labelledby={`${id}-media`} className="flex flex-wrap gap-1.5">
          {kinds.map((kind) => {
            const active = picked.has(kind);
            return (
              <button
                key={kind}
                type="button"
                aria-pressed={active}
                disabled={saveState === "saving"}
                onClick={() => toggleKind(kind)}
                className={cn(
                  "inline-flex h-7 items-center gap-1 rounded-full px-2.5 text-xs font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:opacity-70",
                  active ? "bg-foreground text-background" : "bg-muted text-muted-foreground hover:text-foreground",
                )}
              >
                {active && <Check className="size-3" aria-hidden />}
                {i18n._(MEDIA_KIND_LABELS[kind])}
              </button>
            );
          })}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Button type="submit" size="sm" variant={dirty ? "default" : "outline"} disabled={!dirty || saveState === "saving"}>
          <Trans>Save</Trans>
        </Button>
        <SaveState saving={saveState === "saving"} saved={saveState === "saved"} />
      </div>
    </form>
  );
}

function AccountCard({ account, linked, busy, onToggle, noAvatar = false, muted = false }) {
  const scheduler = account.publisher_label;
  const platform = platformMeta(account.platform).label;
  return (
    <Card
      className={cn(
        "flex-row items-center gap-3 p-3 transition-all",
        linked && "border-primary/40 bg-primary/[0.04] ring-1 ring-primary/20",
        muted && "border-dashed",
      )}
    >
      <AccountAvatar account={account} linked={linked} noAvatar={noAvatar} />

      <div className="min-w-0 flex-1">
        <p className={cn("truncate text-sm font-semibold", muted && "text-muted-foreground")}>@{account.username}</p>
        <p className="truncate text-xs text-muted-foreground">
          {muted ? <Trans>At {scheduler}</Trans>
            : scheduler ? <Trans>{platform} · via {scheduler}</Trans> : platform}
        </p>
        {account.needs_reconnect && (
          <p className="truncate text-xs text-warning"><Trans>Reconnect it in {scheduler}</Trans></p>
        )}
      </div>

      {!muted && (
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
      )}
    </Card>
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

/** Saving… / Saved, else the count when there is one to show. */
function SaveState({ saving, saved, count }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      {saving ? (
        <><Spinner className="size-3.5" /> <Trans>Saving…</Trans></>
      ) : saved ? (
        <><Check className="size-3.5 text-success" /> <Trans>Saved</Trans></>
      ) : count !== undefined ? (
        <Trans><span className="font-medium text-foreground tabular-nums">{count}</span> linked</Trans>
      ) : null}
    </span>
  );
}
