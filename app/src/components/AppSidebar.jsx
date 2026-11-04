"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Gauge,
  Check,
  Plus,
  ChevronsUpDown,
  LogIn,
  LogOut,
  Settings,
  Cpu,
  SquareTerminal,
  Sun,
  Moon,
  Bell,
  BellOff,
  BellRing,
  ArrowUpRight,
  Bug,
  Lightbulb,
  UserRound,
  Brain,
  Cookie,
} from "lucide-react";
import { useTheme } from "next-themes";
import { msg } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
} from "@/components/ui/sidebar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import {
  PROFILE_CHANGED,
  PROFILE_DEFAULTS,
  loadProfile,
} from "@/lib/userProfile";
import {
  notificationSurface,
  canOpenNotificationSettings,
  openNotificationSettings,
} from "@/lib/notify";
import { CONSENT_SETTINGS_EVENT } from "@/lib/consent";
import { isDesktopShell } from "@/lib/shell";

// Where "this is broken" and "this should exist" go. Two places on purpose,
// and .github/ISSUE_TEMPLATE/config.yml already draws the line: issues are for
// tracked, actionable work, discussions for open-ended proposals. Straight to
// the bug form rather than the chooser — blank issues are disabled, so
// /issues/new only ever bounces there anyway.
const GITHUB_ISSUES_URL =
  "https://github.com/5hirish/duct/issues/new?template=bug_report.yml";
const GITHUB_DISCUSSIONS_URL =
  "https://github.com/5hirish/duct/discussions/new?category=ideas";

// The wordmark is the brand, lower-case by design, and not copy: it is the one
// string on the sidebar a translator must never touch.
const WORDMARK = "duct";
import {
  PROJECTS_CHANGED,
  getActiveProjectId,
  getProjects,
  resolveActiveProjectId,
  setActiveProjectId,
} from "@/lib/projects";
import { faviconUrl } from "@/lib/favicon";
import { CONNECTORS_CHANGED, countConnectedSources } from "@/lib/connectorsApi";
import { NAV_SECTIONS } from "@/lib/navigation";
import { runsUnder } from "@/lib/liveRuns";
import { useLiveRuns } from "@/hooks/useLiveRuns";
import { LanguageMenuItem } from "@/components/LanguageMenu";

// ---------------------------------------------------------------------------
// Project switcher in sidebar header
// ---------------------------------------------------------------------------

/** Project avatar: site favicon when a website URL is set, else the name initial. */
function ProjectAvatar({ project, wrapperClass, imgSize = 16 }) {
  const favicon = faviconUrl(project?.company?.website_url || "");
  const initial = (project?.name || "P").charAt(0).toUpperCase();
  return (
    <span className={wrapperClass}>
      {favicon ? (
        <img
          src={favicon}
          alt=""
          width={imgSize}
          height={imgSize}
          className="rounded-sm"
          style={{ width: imgSize, height: imgSize }}
        />
      ) : (
        initial
      )}
    </span>
  );
}

function SidebarProjectSwitcher() {
  const router = useRouter();
  const { t } = useLingui();
  const [projects, setProjects] = useState([]);
  const [activeId, setActiveId] = useState("");

  useEffect(() => {
    // resolveActiveProjectId persists whatever it falls back to, so what the
    // switcher shows is always what the rest of the app reads back.
    const sync = () => {
      const ps = getProjects();
      setProjects(ps);
      setActiveId(resolveActiveProjectId(ps));
    };
    sync();
    window.addEventListener("storage", sync);
    window.addEventListener(PROJECTS_CHANGED, sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener(PROJECTS_CHANGED, sync);
    };
  }, []);

  const active = projects.find((p) => p.id === activeId) || null;

  function select(id) {
    // setActiveProjectId persists the pick and notifies; sync() picks it up.
    setActiveProjectId(id);
    setActiveId(id);
  }

  if (!active && projects.length === 0) {
    return (
      <button
        onClick={() => router.push("/projects")}
        className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
      >
        <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-brand">
          <Plus className="size-4" />
        </span>
        <span className="flex-1 truncate font-medium text-sidebar-foreground group-data-[collapsible=icon]:hidden">
          <Trans>New project</Trans>
        </span>
      </button>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0">
          <ProjectAvatar
            project={active}
            wrapperClass="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-brand font-semibold text-xs"
            imgSize={16}
          />
          <span className="flex-1 truncate font-medium text-sidebar-foreground group-data-[collapsible=icon]:hidden">
            {active?.name || t`Select project`}
          </span>
          <ChevronsUpDown className="size-3.5 shrink-0 text-sidebar-foreground/50 group-data-[collapsible=icon]:hidden" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-56" align="start" side="bottom">
        {projects.map((p) => (
          <DropdownMenuItem key={p.id} onClick={() => select(p.id)}>
            <ProjectAvatar
              project={p}
              wrapperClass="flex size-5 shrink-0 items-center justify-center rounded bg-muted text-xs font-semibold"
              imgSize={14}
            />
            <span className="ml-2 truncate">{p.name}</span>
            {p.id === activeId && <Check className="ml-auto size-3.5 text-brand" />}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        {/* The project list lives with the projects. It sat in the account
            menu, one menu away from the switcher that already names them. */}
        <DropdownMenuItem onClick={() => router.push("/projects")}>
          <Settings className="size-4" />
          <span><Trans>Manage projects</Trans></span>
        </DropdownMenuItem>
        {/* A project starts from a site, at /start; /projects was a hop to
            the same button. */}
        <DropdownMenuItem onClick={() => router.push("/start")}>
          <Plus className="size-4" />
          <span><Trans>New project</Trans></span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// ---------------------------------------------------------------------------
// User footer
// ---------------------------------------------------------------------------

/** The notification state to render, once we know which surface we are on.
 *
 * Async because the shell answers over IPC (`getShellInfo`). Starts as
 * "unknown", which renders nothing — better a row that appears a beat late
 * than one that claims "Off" and corrects itself. */
function useNotificationPermission() {
  const [permission, setPermission] = useState("unknown");
  // Only meaningful while `permission` is "system": whether this shell has an
  // OS page to send the user to.
  const [hasSettingsPage, setHasSettingsPage] = useState(false);

  useEffect(() => {
    let alive = true;
    notificationSurface().then(async (surface) => {
      if (!alive) return;
      // The shell posts through the OS, which owns the switch and has no
      // permission for the page to request. "system" is that state: Duct will
      // post, and whether anything appears is settled in System Settings.
      setPermission(surface === "shell" ? "system" : surface === "browser" ? Notification.permission : "none");
      if (surface !== "shell") return;
      const canOpen = await canOpenNotificationSettings();
      if (alive) setHasSettingsPage(canOpen);
    });
    return () => {
      alive = false;
    };
  }, []);

  /** The one thing clicking the row does, whichever surface we are on. */
  async function act() {
    // The shell cannot ask — `permission_state` there is a constant `Granted`,
    // so the OS page is the only place the real answer lives or changes.
    if (permission === "system") {
      await openNotificationSettings();
      return;
    }
    if (permission !== "default") return;
    setPermission(await Notification.requestPermission());
  }

  return { permission, hasSettingsPage, act };
}

function NotificationMenuItem() {
  const { permission, hasSettingsPage, act } = useNotificationPermission();

  if (permission === "unknown" || permission === "none") return null;
  return <NotificationRow permission={permission} hasSettingsPage={hasSettingsPage} onAct={act} />;
}

/** The row itself, given a state rather than detecting one.
 *
 * Split from the hook so every state is reachable: two of the four ("System",
 * "Blocked") cannot be produced in a browser at all, which is exactly why they
 * are the ones that go unreviewed. `/preview` renders all four side by side. */
export function NotificationRow({ permission, hasSettingsPage = false, onAct }) {
  const { t } = useLingui();
  // One row shape for every setting in the menu: the name, then its current
  // value in muted text, as Language and Appearance do. It used to be a green
  // monospace pill here, a third way of showing a value in one group of three.
  // "Off" is the one state whose row is an action rather than a setting, so
  // it says the action instead of a value.
  const states = {
    default: { icon: Bell,     label: t`Turn on notifications`, value: null,        clickable: true  },
    granted: { icon: BellRing, label: t`Notifications`,         value: t`On`,       clickable: false },
    denied:  { icon: BellOff,  label: t`Notifications`,         value: t`Blocked`,  clickable: false },
    system:  { icon: BellRing, label: t`Notifications`,         value: t`System`,   clickable: hasSettingsPage },
  };
  const { icon: Icon, label, value, clickable } = states[permission] ?? states.default;
  // The one row that leaves the app says so before the click does.
  const opensElsewhere = permission === "system" && hasSettingsPage;

  const hint =
    permission === "denied" ? t`Blocked in browser — open Site Settings to re-enable` :
    opensElsewhere ? t`Duct posts through the OS — open System Settings to turn them on or off` :
    permission === "system" ? t`Handled by the OS — change it in your system notification settings` :
    undefined;

  return (
    <DropdownMenuItem
      // Opening System Settings puts another window in front; closing the menu
      // first means returning to the app does not land back inside a stale one.
      onSelect={clickable ? onAct : undefined}
      className={cn("justify-between", !clickable && "cursor-default opacity-60")}
      title={hint}
    >
      <span className="flex min-w-0 items-center gap-2">
        <Icon className="size-4 shrink-0" />
        <span className="truncate">{label}</span>
      </span>
      {value && (
        <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
          {value}
          {opensElsewhere && <ArrowUpRight className="size-3.5" aria-hidden />}
        </span>
      )}
    </DropdownMenuItem>
  );
}

function ProfileMenuItem() {
  const [set, setSet] = useState(false);

  // The mark answers "have I told Duct anything about myself", which is the
  // only question this row can answer without opening it. It reads the local
  // cache rather than the server: the menu opens in a frame, and a fetch to
  // decorate a menu item is a request nobody asked for.
  useEffect(() => {
    const check = () => {
      const profile = loadProfile();
      setSet(
        Boolean(profile.display_name || profile.role || profile.notes || profile.communication_language)
          || profile.writing_preset !== PROFILE_DEFAULTS.writing_preset,
      );
    };
    check();
    window.addEventListener("storage", check);
    window.addEventListener(PROFILE_CHANGED, check);
    return () => {
      window.removeEventListener("storage", check);
      window.removeEventListener(PROFILE_CHANGED, check);
    };
  }, []);

  return (
    <DropdownMenuItem asChild className="justify-between">
      <Link href="/settings/profile">
        <span className="flex items-center gap-2">
          <UserRound className="size-4" />
          <Trans>Profile</Trans>
        </span>
        {set && (
          <span className="text-xs text-muted-foreground">
            <Trans>Set</Trans>
          </span>
        )}
      </Link>
    </DropdownMenuItem>
  );
}

/**
 * The account menu, in the order people look for things in one: who you are
 * to Duct, then what runs your work, then how this app looks and talks to you,
 * then the way out to us, then the way out.
 *
 *   Profile · Your memory
 *   Models & providers · Usage · Connect your AI agent
 *   Language · Appearance · Notifications · Cookie settings
 *   Report a bug · Suggest an improvement
 *   Log out
 *
 * It was nine rows in one block with nothing between them: Profile sixth,
 * away from the memory it belongs beside; the theme row naming the mode it
 * would switch to rather than the one you were in; Cookie settings, a
 * preference, filed under feedback. "Manage projects" moved to the project
 * switcher. A setting's row carries its current value on the right, muted,
 * the same way on every row that has one.
 *
 * Exported so `/preview` can show the whole menu, not only its parts.
 */
export function AccountMenuItems({ guest = false, onSignOut }) {
  return (
    <>
      {guest && (
        <>
          {/* The one thing a guest cannot do yet. Sign-in links this guest's
              work to the account it creates (lib/guest.js). */}
          <DropdownMenuItem asChild>
            <Link href="/">
              <LogIn className="size-4" />
              <span><Trans>Sign in to keep this</Trans></span>
            </Link>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
        </>
      )}
      {/* What you declare and what Duct has learned about you are the same
          subject, and both are yours to edit. */}
      <ProfileMenuItem />
      <DropdownMenuItem asChild>
        <Link href="/memory">
          <Brain className="size-4" />
          <span><Trans>Your memory</Trans></span>
        </Link>
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      {/* Was an "Engine" dialog that could only change the harness — it
          showed a model name it had no power to set. The page it points at
          owns what is still a choice: which models, and whose key. */}
      <DropdownMenuItem asChild>
        <Link href="/settings/models">
          <Cpu className="size-4" />
          <span><Trans>Models &amp; providers</Trans></span>
        </Link>
      </DropdownMenuItem>
      {/* Out of the sidebar on 2026-11-02: what your key spent is an
          account question, asked monthly, not a place you work in. */}
      <DropdownMenuItem asChild>
        <Link href="/usage">
          <Gauge className="size-4" />
          <span><Trans>Usage</Trans></span>
        </Link>
      </DropdownMenuItem>
      {/* Duct reached from outside: the person's own agent setting up their
          projects through the MCP server (settings/agents). */}
      <DropdownMenuItem asChild>
        <Link href="/settings/agents">
          <SquareTerminal className="size-4" />
          <span><Trans>Connect your AI agent</Trans></span>
        </Link>
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      {/* The profile page has the same control; here it is one click away
          for someone who landed in a language they cannot read. */}
      <LanguageMenuItem />
      <AppearanceMenuItem />
      <NotificationMenuItem />
      {/* No cookies to settle in the desktop shell — it loads no tags. */}
      {isDesktopShell() ? null : (
        <DropdownMenuItem onClick={() => window.dispatchEvent(new Event(CONSENT_SETTINGS_EVENT))}>
          <Cookie className="size-4" />
          <span><Trans>Cookie settings</Trans></span>
        </DropdownMenuItem>
      )}
      <DropdownMenuSeparator />
      {/* Plain new-tab links: installExternalLinkHandler (lib/shell.js)
          reroutes target="_blank" to the system browser inside the desktop
          shell, where a new tab would otherwise go nowhere at all. */}
      <DropdownMenuItem asChild>
        <a href={GITHUB_ISSUES_URL} target="_blank" rel="noreferrer noopener">
          <Bug className="size-4" />
          <span><Trans>Report a bug</Trans></span>
        </a>
      </DropdownMenuItem>
      <DropdownMenuItem asChild>
        <a href={GITHUB_DISCUSSIONS_URL} target="_blank" rel="noreferrer noopener">
          <Lightbulb className="size-4" />
          <span><Trans>Suggest an improvement</Trans></span>
        </a>
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem onClick={onSignOut}>
        <LogOut className="size-4" />
        <span><Trans>Log out</Trans></span>
      </DropdownMenuItem>
    </>
  );
}

function SidebarUserFooter() {
  const { user, signOut } = useAuth();
  const { t } = useLingui();

  if (!user) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0">
          <span className="relative shrink-0">
            {user.picture ? (
              <img
                className="size-7 rounded-full object-cover"
                src={user.picture}
                alt={user.name || user.email}
                width={28}
                height={28}
                referrerPolicy="no-referrer"
              />
            ) : (
              <span className="flex size-7 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">
                {(user.name || user.email || "U").charAt(0).toUpperCase()}
              </span>
            )}
          </span>
          <div className="flex min-w-0 flex-col group-data-[collapsible=icon]:hidden">
            <span className="truncate text-xs font-medium text-sidebar-foreground">
              {user.guest ? t`Guest` : user.name || user.email}
            </span>
            {/* A guest's email is a synthetic install id; the useful second
                line is what an account would do for them. */}
            <span className="truncate text-2xs text-sidebar-foreground/50">
              {user.guest ? t`Sign in to save your work` : user.email}
            </span>
          </div>
          <ChevronsUpDown className="ml-auto size-3.5 shrink-0 text-sidebar-foreground/40 group-data-[collapsible=icon]:hidden" />
        </button>
      </DropdownMenuTrigger>
      {/* No name-and-email header inside: the menu opens above the button
          that already shows both. */}
      <DropdownMenuContent className="w-64" align="start" side="top">
        <AccountMenuItems guest={user.guest} onSignOut={signOut} />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// ---------------------------------------------------------------------------
// Appearance
// ---------------------------------------------------------------------------

const APPEARANCES = [
  { value: "system", label: msg`System` },
  { value: "light", label: msg`Light` },
  { value: "dark", label: msg`Dark` },
];

// Appearance follows the system by default (Apple: avoid an app-specific
// appearance setting), so the override lives in the account menu rather than
// as a permanent row in the sidebar where it sat beside the real navigation.
// A sub-menu, the same shape as Language, rather than the one-click toggle it
// was: the toggle could leave the system setting but never return to it, and
// it named the mode it would switch to, so the row read "Light mode" in dark.
function AppearanceMenuItem() {
  const { i18n } = useLingui();
  const { theme, resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // next-themes knows nothing until mount; the row says nothing until then
  // rather than claim "System" and correct itself.
  const current = APPEARANCES.find((a) => a.value === theme) ?? APPEARANCES[0];
  const Icon = mounted && resolvedTheme === "dark" ? Moon : Sun;

  return (
    <DropdownMenuSub>
      <DropdownMenuSubTrigger>
        {/* The label takes the free space, so the value sits against the
            chevron. Two `ml-auto`s split it and left the value floating. */}
        <span className="flex flex-1 items-center gap-2">
          <Icon className="size-4 text-muted-foreground" aria-hidden />
          <span><Trans>Appearance</Trans></span>
        </span>
        <span className="truncate text-xs text-muted-foreground">
          {mounted ? i18n._(current.label) : null}
        </span>
      </DropdownMenuSubTrigger>
      <DropdownMenuSubContent>
        <DropdownMenuRadioGroup value={mounted ? current.value : ""} onValueChange={setTheme}>
          {APPEARANCES.map((a) => (
            <DropdownMenuRadioItem key={a.value} value={a.value}>
              {i18n._(a.label)}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}

// ---------------------------------------------------------------------------
// AppSidebar
// ---------------------------------------------------------------------------

/** How many sources are connected, for the count beside the Toolbox.
 *
 * It used to count two hardcoded sessionStorage keys — GA4 and GSC — so the
 * badge could never read higher than 2 and never saw Google Ads, GTM, or any
 * server-stored connector at all. Replacing that with the browser's union of
 * server rows and session tokens fixed the ceiling and introduced a subtler
 * disagreement: the badge read "1" from a Google token living only in this
 * tab while the desk checklist, asking the server, correctly reported no
 * source connected. Two honest answers to two different questions, sitting a
 * few hundred pixels apart.
 *
 * So it now asks `countConnectedSources` — the same call the desk makes — and
 * asks it per project, because which sources a project can reach depends on
 * its bindings.
 *
 * Refreshed on the connector-changed event, on a project switch, on cross-tab
 * storage writes, and on focus — the last of which is what catches a
 * connection made in the OAuth tab that handed control back without any of the
 * others firing.
 */
function useConnectionCount() {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let alive = true;
    let seq = 0;
    let inFlightFor = null;
    const check = () => {
      // Read at call time rather than from state: a project switch and this
      // check race, and the id in hand is the one that just won.
      const forProject = getActiveProjectId() || "";
      // Focus fires in bursts, and one answer per project is enough — but a
      // switch to a DIFFERENT project is a different question, and coalescing
      // it away would leave the badge showing the project you just left.
      if (inFlightFor === forProject) return;
      inFlightFor = forProject;
      const mine = ++seq;
      countConnectedSources(forProject)
        .then((n) => {
          // A later check has been issued since; its answer is the current one.
          if (alive && mine === seq) setCount(n);
        })
        .finally(() => {
          if (inFlightFor === forProject) inFlightFor = null;
        });
    };
    check();
    window.addEventListener(CONNECTORS_CHANGED, check);
    window.addEventListener(PROJECTS_CHANGED, check);
    window.addEventListener("storage", check);
    window.addEventListener("focus", check);
    return () => {
      alive = false;
      window.removeEventListener(CONNECTORS_CHANGED, check);
      window.removeEventListener(PROJECTS_CHANGED, check);
      window.removeEventListener("storage", check);
      window.removeEventListener("focus", check);
    };
  }, []);
  return count;
}

export default function AppSidebar() {
  const pathname = usePathname();
  const { t, i18n } = useLingui();
  const connectionCount = useConnectionCount();
  // Runs this tab left mid-turn: the entry they belong to pulses until the
  // backend says the turn is over or the page picks the run back up.
  const liveRuns = useLiveRuns();

  function isActive(item) {
    if (!item.matchPrefix || !pathname) return false;
    return pathname === item.matchPrefix || pathname.startsWith(item.matchPrefix + "/");
  }

  return (
    <Sidebar collapsible="icon">
      {/* Logo + Project */}
      <SidebarHeader className="gap-0 border-b border-sidebar-border pb-0">
        {/* Expanded logo */}
        <div className="flex items-center gap-2 px-4 py-3 group-data-[collapsible=icon]:hidden">
          <Link
            href="/insights/organic-growth"
            className="inline-flex items-center gap-1.5 font-serif text-lg tracking-tight text-sidebar-foreground hover:text-brand transition-colors"
          >
            {WORDMARK}
            <span
              className="size-2 rounded-full bg-[var(--orange)] animate-[pop_2.5s_ease-in-out_infinite]"
              aria-hidden
            />
          </Link>
          <span className="text-xs text-sidebar-foreground/40 font-sans">app</span>
        </div>

        {/* Collapsed mini logo — "d·" mark */}
        <div className="hidden group-data-[collapsible=icon]:flex justify-center py-3">
          <Link
            href="/insights/organic-growth"
            className="inline-flex items-end gap-0.5 font-serif text-xl font-bold tracking-tight text-sidebar-foreground hover:text-brand transition-colors leading-none"
            aria-label={t`duct home`}
          >
            d
            <span
              className="size-2 rounded-full bg-[var(--orange)] animate-[pop_2.5s_ease-in-out_infinite] mb-0.5"
              aria-hidden
            />
          </Link>
        </div>

        <div className="px-2 pb-2 group-data-[collapsible=icon]:hidden">
          <SidebarProjectSwitcher />
        </div>
      </SidebarHeader>

      {/* Nav sections */}
      <SidebarContent className="gap-0">
        {NAV_SECTIONS.map((section, i) => (
          <div key={section.key}>
            {/* Collapsed-only divider between sections */}
            {i > 0 && (
              <SidebarSeparator className="hidden group-data-[collapsible=icon]:block mx-2 my-1" />
            )}

            <SidebarGroup className="py-2">
              <SidebarGroupLabel className="px-4 text-xs font-medium text-muted-foreground">
                {i18n._(section.label)}
              </SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {section.items.map((item) => {
                    const Icon = item.icon;
                    const active = isActive(item);
                    const label = i18n._(item.label);
                    const working = runsUnder(liveRuns, item.matchPrefix).length > 0;

                    if (!item.available) return null;
                    const count = item.badge === "connections" ? connectionCount : 0;

                    return (
                      <SidebarMenuItem key={item.key}>
                        <SidebarMenuButton asChild isActive={active} tooltip={label}>
                          <Link href={item.href}>
                            <Icon className="size-4" />
                            <span>{label}</span>
                            {working ? (
                              <span
                                role="img"
                                aria-label={t`Working…`}
                                className="ml-auto size-2 shrink-0 animate-pulse rounded-full bg-primary group-data-[collapsible=icon]:hidden"
                              />
                            ) : count > 0 ? (
                              <span className="ml-auto text-xs tabular-nums text-muted-foreground group-data-[collapsible=icon]:hidden">
                                {count}
                              </span>
                            ) : null}
                          </Link>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    );
                  })}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          </div>
        ))}
      </SidebarContent>

      {/* Footer */}
      <SidebarFooter className="gap-0 border-t border-sidebar-border p-2">

        {/* User */}
        <SidebarUserFooter />
      </SidebarFooter>
    </Sidebar>
  );
}
