"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  TrendingUp,
  BarChart3,
  Megaphone,
  Search,
  PenLine,
  Plug,
  Check,
  Plus,
  ChevronsUpDown,
  LogOut,
  Settings,
  Cpu,
  Sun,
  Moon,
  Bell,
  BellOff,
  BellRing,
  SlidersHorizontal,
} from "lucide-react";
import { useTheme } from "next-themes";
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
import EngineDialog from "./EngineDialog";
import PreferencesDialog from "./PreferencesDialog";
import { loadPreferences, hasNonDefaultPreferences } from "@/lib/userPreferences";
import {
  DEFAULT_ENGINE,
  ENGINE_STORAGE_KEY,
  getEngine,
} from "@/lib/engines";
import {
  getActiveProjectId,
  getProjects,
  setActiveProjectId,
} from "@/lib/projects";

// ---------------------------------------------------------------------------
// Nav structure
// ---------------------------------------------------------------------------

const NAV_SECTIONS = [
  {
    key: "insights",
    label: "Insights",
    items: [
      {
        key: "organic_growth",
        label: "Organic Growth",
        icon: TrendingUp,
        href: "/insights/organic-growth",
        available: true,
        matchPrefix: "/insights/organic-growth",
      },
      {
        key: "product_intelligence",
        label: "Product Intelligence",
        icon: BarChart3,
        href: null,
        available: false,
      },
      {
        key: "paid_ads",
        label: "Paid Ads Intelligence",
        icon: Megaphone,
        href: null,
        available: false,
      },
    ],
  },
  {
    key: "audit",
    label: "Audit",
    items: [
      {
        key: "seo_audit",
        label: "SEO Audit",
        icon: Search,
        href: "/audit/seo",
        available: true,
        matchPrefix: "/audit/seo",
      },
    ],
  },
  {
    key: "execute",
    label: "Execute",
    items: [
      {
        key: "content_marketing",
        label: "Content Marketing",
        icon: PenLine,
        href: "/content",
        available: true,
        matchPrefix: "/content",
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Project switcher in sidebar header
// ---------------------------------------------------------------------------

function SidebarProjectSwitcher() {
  const router = useRouter();
  const [projects, setProjects] = useState([]);
  const [activeId, setActiveId] = useState("");

  useEffect(() => {
    const sync = () => {
      const ps = getProjects();
      const aid = getActiveProjectId();
      setProjects(ps);
      setActiveId(ps.find((p) => p.id === aid)?.id || ps[0]?.id || "");
    };
    sync();
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  const active = projects.find((p) => p.id === activeId) || null;

  function select(id) {
    setActiveProjectId(id);
    setActiveId(id);
    window.dispatchEvent(new Event("duct:project-changed"));
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
          New project
        </span>
      </button>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary font-semibold text-xs">
            {(active?.name || "P").charAt(0).toUpperCase()}
          </span>
          <span className="flex-1 truncate font-medium text-sidebar-foreground group-data-[collapsible=icon]:hidden">
            {active?.name || "Select project"}
          </span>
          <ChevronsUpDown className="size-3.5 shrink-0 text-sidebar-foreground/50 group-data-[collapsible=icon]:hidden" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-56" align="start" side="bottom">
        {projects.map((p) => (
          <DropdownMenuItem key={p.id} onClick={() => select(p.id)}>
            <span className="flex size-5 shrink-0 items-center justify-center rounded bg-muted text-xs font-semibold">
              {p.name.charAt(0).toUpperCase()}
            </span>
            <span className="ml-2 truncate">{p.name}</span>
            {p.id === activeId && <Check className="ml-auto size-3.5 text-primary" />}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => router.push("/projects")}>
          <Plus className="size-4" />
          <span>New project</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// ---------------------------------------------------------------------------
// User footer
// ---------------------------------------------------------------------------

function useNotificationPermission() {
  const supported = typeof window !== "undefined" && "Notification" in window;
  const [permission, setPermission] = useState(() =>
    supported ? Notification.permission : "unsupported"
  );

  async function request() {
    if (!supported || permission !== "default") return;
    const result = await Notification.requestPermission();
    setPermission(result);
  }

  return { permission, request };
}

function NotificationMenuItem() {
  const { permission, request } = useNotificationPermission();

  if (permission === "unsupported") return null;

  const states = {
    default:     { icon: Bell,     badge: "Off",      label: "Enable notifications", clickable: true  },
    granted:     { icon: BellRing, badge: "On",       label: "Notifications",        clickable: false },
    denied:      { icon: BellOff,  badge: "Blocked",  label: "Notifications",        clickable: false },
  };
  const { icon: Icon, badge, label, clickable } = states[permission] ?? states.default;

  return (
    <DropdownMenuItem
      onClick={clickable ? request : undefined}
      className={`flex items-center justify-between ${!clickable ? "cursor-default opacity-60" : ""}`}
      title={permission === "denied" ? "Blocked in browser — open Site Settings to re-enable" : undefined}
    >
      <span className="flex items-center gap-2">
        <Icon className="size-4" />
        {label}
      </span>
      <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
        permission === "granted"  ? "bg-green-500/15 text-green-600 dark:text-green-400" :
        permission === "denied"   ? "bg-destructive/10 text-destructive" :
                                    "bg-muted text-muted-foreground"
      }`}>
        {badge}
      </span>
    </DropdownMenuItem>
  );
}

function PreferencesDialogMenuItem() {
  const [hasPrefs, setHasPrefs] = useState(false);

  useEffect(() => {
    const check = () => setHasPrefs(hasNonDefaultPreferences(loadPreferences()));
    check();
    window.addEventListener("storage", check);
    return () => window.removeEventListener("storage", check);
  }, []);

  return (
    <PreferencesDialog>
      <DropdownMenuItem
        onSelect={(e) => e.preventDefault()}
        className="flex items-center justify-between"
      >
        <span className="flex items-center gap-2">
          <SlidersHorizontal className="size-4" />
          Preferences
        </span>
        {hasPrefs && (
          <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
            Set
          </span>
        )}
      </DropdownMenuItem>
    </PreferencesDialog>
  );
}

function SidebarUserFooter() {
  const { user, signOut } = useAuth();
  const { resolvedTheme, setTheme } = useTheme();
  const [engineKey, setEngineKey] = useState(DEFAULT_ENGINE);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    setEngineKey(localStorage.getItem(ENGINE_STORAGE_KEY) || DEFAULT_ENGINE);
    function onStorage(e) {
      if (e.key === ENGINE_STORAGE_KEY) setEngineKey(e.newValue || DEFAULT_ENGINE);
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const engine = getEngine(engineKey);
  const isDark = resolvedTheme === "dark";

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
            <span
              aria-hidden
              className="absolute -bottom-0.5 -right-0.5 rounded-full border border-sidebar bg-muted px-1 py-px font-mono text-[8px] font-semibold leading-none text-muted-foreground"
            >
              {engine.badge}
            </span>
          </span>
          <div className="flex min-w-0 flex-col group-data-[collapsible=icon]:hidden">
            <span className="truncate text-xs font-medium text-sidebar-foreground">
              {user.name || user.email}
            </span>
            <span className="truncate text-[11px] text-sidebar-foreground/50">
              {user.email}
            </span>
          </div>
          <ChevronsUpDown className="ml-auto size-3.5 shrink-0 text-sidebar-foreground/40 group-data-[collapsible=icon]:hidden" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-56" align="start" side="top">
        <DropdownMenuItem asChild>
          <Link href="/projects">
            <Settings className="size-4" />
            <span>Manage projects</span>
          </Link>
        </DropdownMenuItem>
        <EngineDialog>
          <DropdownMenuItem
            onSelect={(e) => e.preventDefault()}
            className="flex items-center justify-between"
          >
            <span className="flex items-center gap-2">
              <Cpu className="size-4" />
              Engine
            </span>
            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {engine.badge}
            </span>
          </DropdownMenuItem>
        </EngineDialog>
        <PreferencesDialogMenuItem />
        <NotificationMenuItem />
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={signOut}>
          <LogOut className="size-4" />
          <span>Log out</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// ---------------------------------------------------------------------------
// Theme sidebar item
// ---------------------------------------------------------------------------

function ThemeSidebarItem() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const isDark = resolvedTheme === "dark";

  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        onClick={() => mounted && setTheme(isDark ? "light" : "dark")}
        tooltip={isDark ? "Light mode" : "Dark mode"}
      >
        {mounted && isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
        <span>{mounted && isDark ? "Light mode" : "Dark mode"}</span>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );
}

// ---------------------------------------------------------------------------
// AppSidebar
// ---------------------------------------------------------------------------

function useConnectionCount() {
  const [count, setCount] = useState(0);
  useEffect(() => {
    const check = () => {
      let n = 0;
      if (sessionStorage.getItem("ga4_refresh_token")) n++;
      if (sessionStorage.getItem("gsc_refresh_token")) n++;
      setCount(n);
    };
    check();
    window.addEventListener("storage", check);
    return () => window.removeEventListener("storage", check);
  }, []);
  return count;
}

export default function AppSidebar() {
  const pathname = usePathname();
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
            duct
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
            aria-label="duct home"
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
              <SidebarGroupLabel className="px-4 text-[11px] font-semibold uppercase tracking-wider text-sidebar-foreground/40">
                {section.label}
              </SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {section.items.map((item) => {
                    const Icon = item.icon;
                    const active = isActive(item);

                    if (!item.available) {
                      return (
                        <SidebarMenuItem key={item.key}>
                          <SidebarMenuButton
                            className="cursor-default opacity-45 hover:bg-transparent hover:text-sidebar-foreground/45"
                            tooltip={`${item.label} — coming soon`}
                          >
                            <Icon className="size-4" />
                            <span>{item.label}</span>
                            <span className="ml-auto rounded-full bg-muted px-1.5 py-px text-[10px] leading-none text-muted-foreground">
                              Soon
                            </span>
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      );
                    }

                    return (
                      <SidebarMenuItem key={item.key}>
                        <SidebarMenuButton asChild isActive={active} tooltip={item.label}>
                          <Link href={item.href}>
                            <Icon className="size-4" />
                            <span>{item.label}</span>
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
              tooltip={connectionCount ? `Connections · ${connectionCount} active` : "Connections — add a source"}
            >
              <Link href="/connections">
                <Plug className="size-4" />
                <span>Connections</span>
                {connectionCount > 0 ? (
                  <span className="ml-auto rounded-full bg-primary/15 px-1.5 py-px text-[10px] leading-none font-medium text-primary group-data-[collapsible=icon]:hidden">
                    {connectionCount}
                  </span>
                ) : (
                  <span className="ml-auto text-[11px] text-muted-foreground/60 group-data-[collapsible=icon]:hidden">
                    New
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
