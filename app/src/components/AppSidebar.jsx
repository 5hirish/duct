"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Plug,
  Check,
  Plus,
  ChevronsUpDown,
  LogIn,
  LogOut,
  Settings,
  Cpu,
  Sun,
  Moon,
  Bell,
  BellOff,
  BellRing,
  Bug,
  Lightbulb,
  SlidersHorizontal,
  Brain,
  Cookie,
} from "lucide-react";
import { useTheme } from "next-themes";
import { Trans, useLingui } from "@lingui/react/macro";
import { plural } from "@lingui/core/macro";
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
  DropdownMenuSeparator,
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
        <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
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
            wrapperClass="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary font-semibold text-xs"
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
            {p.id === activeId && <Check className="ml-auto size-3.5 text-primary" />}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => router.push("/projects")}>
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
  // "system" is the only row whose label depends on more than the permission:
  // it is an action when the shell can open the OS page and a statement when it
  // cannot (Linux, or a shell older than `open_notification_settings`).
  const states = {
    default:     { icon: Bell,     badge: t`Off`,      label: t`Enable notifications`, clickable: true  },
    granted:     { icon: BellRing, badge: t`On`,       label: t`Notifications`,        clickable: false },
    denied:      { icon: BellOff,  badge: t`Blocked`,  label: t`Notifications`,        clickable: false },
    system: hasSettingsPage
      ? { icon: BellRing, badge: t`System`, label: t`Notification settings`, clickable: true  }
      : { icon: BellRing, badge: t`System`, label: t`Notifications`,         clickable: false },
  };
  const { icon: Icon, badge, label, clickable } = states[permission] ?? states.default;

  const hint =
    permission === "denied" ? t`Blocked in browser — open Site Settings to re-enable` :
    permission === "system" && hasSettingsPage ? t`Duct posts through the OS — open System Settings to turn them on or off` :
    permission === "system" ? t`Handled by the OS — change it in your system notification settings` :
    undefined;

  return (
    <DropdownMenuItem
      // Opening System Settings puts another window in front; closing the menu
      // first means returning to the app does not land back inside a stale one.
      onSelect={clickable ? onAct : undefined}
      className={`flex items-center justify-between gap-2 ${!clickable ? "cursor-default opacity-60" : ""}`}
      title={hint}
    >
      {/* The label truncates rather than wraps: "Notification settings" plus
          the badge is wider than the menu in English and wider still in
          German, and a two-line row in a list of one-line rows reads as a
          mistake. The hint carries the full sentence. */}
      <span className="flex min-w-0 items-center gap-2">
        <Icon className="size-4 shrink-0" />
        <span className="truncate">{label}</span>
      </span>
      <span className={`shrink-0 rounded px-1.5 py-0.5 font-mono text-2xs ${
        permission === "granted" ||
        permission === "system"   ? "bg-success/15 text-success" :
        permission === "denied"   ? "bg-destructive/10 text-destructive" :
                                    "bg-muted text-muted-foreground"
      }`}>
        {badge}
      </span>
    </DropdownMenuItem>
  );
}

function ProfileMenuItem() {
  const [set, setSet] = useState(false);

  // The badge answers "have I told Duct anything about myself", which is the
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
    <DropdownMenuItem asChild className="flex items-center justify-between">
      <Link href="/settings/profile">
        <span className="flex items-center gap-2">
          <SlidersHorizontal className="size-4" />
          <Trans>Profile</Trans>
        </span>
        {set && (
          <span className="rounded bg-primary/10 px-1.5 py-0.5 text-2xs font-medium text-primary">
            <Trans>Set</Trans>
          </span>
        )}
      </Link>
    </DropdownMenuItem>
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
      <DropdownMenuContent className="w-64" align="start" side="top">
        {user.guest && (
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
        <DropdownMenuItem asChild>
          <Link href="/projects">
            <Settings className="size-4" />
            <span><Trans>Manage projects</Trans></span>
          </Link>
        </DropdownMenuItem>
        {/* Beside Preferences on purpose: what you declare and what Duct has
            learned about you are the same subject, and both are yours to edit. */}
        <DropdownMenuItem asChild>
          <Link href="/memory">
            <Brain className="size-4" />
            <span><Trans>Your memory</Trans></span>
          </Link>
        </DropdownMenuItem>
        {/* Was an "Engine" dialog that could only change the harness — it
            showed a model name it had no power to set. The page it points at
            owns what is still a choice: which models, and whose key. */}
        <DropdownMenuItem asChild>
          <Link href="/settings/models">
            <Cpu className="size-4" />
            <span><Trans>Models &amp; providers</Trans></span>
          </Link>
        </DropdownMenuItem>
        <ProfileMenuItem />
        <NotificationMenuItem />
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
        {/* No cookies to settle in the desktop shell — it loads no tags. */}
        {isDesktopShell() ? null : (
          <DropdownMenuItem
            onClick={() => window.dispatchEvent(new Event(CONSENT_SETTINGS_EVENT))}
          >
            <Cookie className="size-4" />
            <span><Trans>Cookie settings</Trans></span>
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={signOut}>
          <LogOut className="size-4" />
          <span><Trans>Log out</Trans></span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// ---------------------------------------------------------------------------
// Theme sidebar item
// ---------------------------------------------------------------------------

function ThemeSidebarItem() {
  const { t } = useLingui();
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const isDark = resolvedTheme === "dark";

  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        onClick={() => mounted && setTheme(isDark ? "light" : "dark")}
        tooltip={isDark ? t`Light mode` : t`Dark mode`}
      >
        {mounted && isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
        <span>{mounted && isDark ? t`Light mode` : t`Dark mode`}</span>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );
}

// ---------------------------------------------------------------------------
// AppSidebar
// ---------------------------------------------------------------------------

/** How many sources are connected, for the footer badge.
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
            className="inline-flex items-center gap-1.5 font-serif text-lg tracking-tight text-sidebar-foreground hover:text-primary transition-colors"
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
            className="inline-flex items-end gap-0.5 font-serif text-xl font-bold tracking-tight text-sidebar-foreground hover:text-primary transition-colors leading-none"
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
              <SidebarGroupLabel className="px-4 text-2xs font-semibold uppercase tracking-wider text-sidebar-foreground/40">
                {i18n._(section.label)}
              </SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {section.items.map((item) => {
                    const Icon = item.icon;
                    const active = isActive(item);
                    const label = i18n._(item.label);

                    if (!item.available) {
                      return (
                        <SidebarMenuItem key={item.key}>
                          <SidebarMenuButton
                            className="cursor-default opacity-45 hover:bg-transparent hover:text-sidebar-foreground/45"
                            tooltip={t`${label} — coming soon`}
                          >
                            <Icon className="size-4" />
                            <span>{label}</span>
                            <span className="ml-auto rounded-full bg-muted px-1.5 py-px text-2xs leading-none text-muted-foreground">
                              <Trans>Soon</Trans>
                            </span>
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      );
                    }

                    return (
                      <SidebarMenuItem key={item.key}>
                        <SidebarMenuButton asChild isActive={active} tooltip={label}>
                          <Link href={item.href}>
                            <Icon className="size-4" />
                            <span>{label}</span>
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
        {/* Connections + Theme — same visual style as nav items */}
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              isActive={pathname.startsWith("/connections")}
              tooltip={
                connectionCount
                  ? plural(connectionCount, { one: "Connections · # active", other: "Connections · # active" })
                  : t`Connections — add a source`
              }
            >
              <Link href="/connections">
                <Plug className="size-4" />
                <span><Trans>Connections</Trans></span>
                {connectionCount > 0 ? (
                  <span className="ml-auto rounded-full bg-primary/15 px-1.5 py-px text-2xs leading-none font-medium text-primary group-data-[collapsible=icon]:hidden">
                    {connectionCount}
                  </span>
                ) : (
                  <span className="ml-auto text-2xs text-muted-foreground group-data-[collapsible=icon]:hidden">
                    <Trans>New</Trans>
                  </span>
                )}
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <ThemeSidebarItem />
        </SidebarMenu>

        <SidebarSeparator className="my-2 group-data-[collapsible=icon]:hidden" />

        {/* User */}
        <SidebarUserFooter />
      </SidebarFooter>
    </Sidebar>
  );
}
