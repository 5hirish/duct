"use client";

// Foundations and primitives — the other two thirds of the design system.
//
// `catalogue.jsx` answers "what is the pattern for this job" using DESIGN.md's
// canon. This file answers the two questions underneath it: what is the
// material (colour, type, spacing, icons) and what are the parts (the vendored
// `ui/*` primitives, with their variants).
//
// Scope is deliberate. Every primitive here is one that call sites actually
// choose between — a Button has six variants and five sizes, so seeing them
// together is the difference between picking one and inventing one. Primitives
// with a single appearance and no decision to make (`separator`, `skeleton`)
// appear inside the specimens that use them rather than as entries of their
// own, and `sidebar` is an app shell rather than a part. This is a design
// system, not an inventory.

import {
  ChevronDown,
  Ellipsis,
  Plus,
  Search,
  Settings,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

import TokenSheet from "./TokenSheet";

/** A labelled row of variants, so the choice is visible as a choice. */
function Row({ label, children }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

function Stack({ children }) {
  return <div className="flex flex-col gap-5">{children}</div>;
}

const BUTTON_VARIANTS = ["default", "secondary", "outline", "ghost", "destructive", "link"];
const BUTTON_SIZES = ["xs", "sm", "default", "lg"];

/**
 * Tailwind 4 derives every `p-*`/`gap-*`/`space-*` from `--spacing: 0.25rem`.
 * Shown in `rem` as well as px because the px is only true at a 16px root — the
 * text lens moves it, and a spacing scale that claims to be pixels is the
 * reason someone eventually writes `p-[13px]`.
 */
const SPACING_STEPS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16];

export const FOUNDATIONS = [
  {
    id: "tokens",
    group: "Foundations",
    title: "Colour, type and shape",
    state: "reference",
    note: "Read from computed style, so it is the value after the cascade — switch the frame to light to see the other half of every token. Try it under Vision: deuteranopia.",
    render: () => <TokenSheet />,
  },
  {
    id: "spacing",
    group: "Foundations",
    title: "Spacing",
    state: "reference",
    note: "One scale, from --spacing: 0.25rem. Overlay: 8px grid draws it over any scene.",
    render: () => (
      <div className="flex flex-col gap-2">
        {SPACING_STEPS.map((n) => (
          <div key={n} className="flex items-center gap-3">
            <span className="w-8 shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
              {n}
            </span>
            <span
              className="h-3 shrink-0 rounded-sm bg-primary/30"
              style={{ width: `calc(var(--spacing, 0.25rem) * ${n})` }}
            />
            <span className="font-mono text-xs text-muted-foreground tabular-nums">
              {n * 0.25}rem · {n * 4}px
            </span>
          </div>
        ))}
      </div>
    ),
  },
  {
    id: "icons",
    group: "Foundations",
    title: "Icons",
    state: "reference",
    note: "lucide-react only — no heroicons, no emoji, no one-off SVGs. Decorative icons take aria-hidden; an icon-only button takes an aria-label.",
    render: () => (
      <Stack>
        <Row label="Sizes — size-3.5 in xs rows, size-4 default, size-5 in tiles">
          <Search className="size-3.5" aria-hidden="true" />
          <Search className="size-4" aria-hidden="true" />
          <Search className="size-5" aria-hidden="true" />
        </Row>
        <Row label="Beside a label — the icon is decorative, the word is the name">
          <Button size="sm" variant="secondary">
            <Plus aria-hidden="true" />
            New project
          </Button>
        </Row>
        <Row label="Icon-only — allowed for repeated row-level actions, and it must be named">
          <Button size="icon-sm" variant="ghost" aria-label="Project settings">
            <Settings aria-hidden="true" />
          </Button>
          <Button size="icon-sm" variant="ghost" aria-label="Delete project">
            <Trash2 aria-hidden="true" />
          </Button>
          <Button size="icon-sm" variant="ghost" aria-label="More actions">
            <Ellipsis aria-hidden="true" />
          </Button>
        </Row>
      </Stack>
    ),
  },
];

export const PRIMITIVES = [
  {
    id: "ui-button",
    group: "Primitives",
    title: "Button",
    state: "6 variants · 4 sizes",
    note: "Restyle at source through the CVA variants — a call site that pastes a class string to override one is a fork in disguise.",
    render: () => (
      <Stack>
        <Row label="Variants">
          {BUTTON_VARIANTS.map((v) => (
            <Button key={v} size="sm" variant={v}>
              {v}
            </Button>
          ))}
        </Row>
        <Row label="Sizes">
          {BUTTON_SIZES.map((s) => (
            <Button key={s} size={s}>
              {s}
            </Button>
          ))}
        </Row>
        <Row label="States">
          <Button size="sm">Idle</Button>
          <Button size="sm" disabled>
            Disabled
          </Button>
          <Button size="sm" variant="secondary">
            <Plus aria-hidden="true" />
            With icon
          </Button>
        </Row>
      </Stack>
    ),
  },
  {
    id: "ui-badge",
    group: "Primitives",
    title: "Badge",
    state: "5 variants",
    note: "The canonical status badge. Semantic tokens only — .status-pill hardcodes hexes and is retired on touch.",
    render: () => (
      <Row label="Variants">
        {["default", "secondary", "destructive", "outline", "ghost"].map((v) => (
          <Badge key={v} variant={v}>
            {v}
          </Badge>
        ))}
      </Row>
    ),
  },
  {
    id: "ui-input",
    group: "Primitives",
    title: "Input and Label",
    state: "4 states",
    note: "Every control needs an accessible name. A placeholder is not one — it disappears on focus and some readers skip it.",
    render: () => (
      <div className="flex max-w-sm flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pv-name">Project name</Label>
          <Input id="pv-name" defaultValue="Organic Growth" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pv-domain">Domain</Label>
          <Input id="pv-domain" placeholder="getduct.ai" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pv-locked">Workspace</Label>
          <Input id="pv-locked" defaultValue="Alleviate Lab" disabled />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pv-bad">Report email</Label>
          <Input id="pv-bad" defaultValue="not-an-email" aria-invalid />
          <p role="alert" className="text-xs text-destructive">
            That address is missing an @.
          </p>
        </div>
      </div>
    ),
  },
  {
    id: "ui-select",
    group: "Primitives",
    title: "Select",
    state: "2 sizes",
    note: "Never a native <select>: its option list is drawn by the OS, ignoring every class on the element.",
    render: () => (
      <Stack>
        <Row label="Sizes">
          {["sm", "default"].map((size) => (
            <Select key={size} defaultValue="ga4">
              <SelectTrigger size={size} aria-label={`Data source (${size})`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ga4">Google Analytics</SelectItem>
                <SelectItem value="gsc">Search Console</SelectItem>
              </SelectContent>
            </Select>
          ))}
        </Row>
        <Row label="Disabled">
          <Select defaultValue="ga4" disabled>
            <SelectTrigger size="sm" aria-label="Data source (disabled)">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ga4">Google Analytics</SelectItem>
            </SelectContent>
          </Select>
        </Row>
      </Stack>
    ),
  },
  {
    id: "ui-switch",
    group: "Primitives",
    title: "Switch",
    state: "on · off · disabled",
    note: "For a setting that takes effect immediately. A choice that needs saving is a checkbox in a form, not a switch.",
    render: () => (
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2.5">
          <Switch id="pv-sw-on" defaultChecked />
          <Label htmlFor="pv-sw-on">Weekly brief</Label>
        </div>
        <div className="flex items-center gap-2.5">
          <Switch id="pv-sw-off" />
          <Label htmlFor="pv-sw-off">Alert on anomalies</Label>
        </div>
        <div className="flex items-center gap-2.5">
          <Switch id="pv-sw-dis" disabled />
          <Label htmlFor="pv-sw-dis">Slack delivery (connect Slack first)</Label>
        </div>
      </div>
    ),
  },
  {
    id: "ui-tabs",
    group: "Primitives",
    title: "Tabs",
    state: "default",
    render: () => (
      <Tabs defaultValue="overview" className="max-w-md">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="sources">Sources</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="pt-3 text-sm text-muted-foreground">
          Nine sources connected. Last brief two days ago.
        </TabsContent>
        <TabsContent value="sources" className="pt-3 text-sm text-muted-foreground">
          Search Console, Google Ads, GA4, Stripe.
        </TabsContent>
        <TabsContent value="history" className="pt-3 text-sm text-muted-foreground">
          Twelve briefs since March.
        </TabsContent>
      </Tabs>
    ),
  },
  {
    id: "ui-table",
    group: "Primitives",
    title: "Table",
    state: "with numerics",
    note: "Numbers right-aligned and tabular-nums, so digits line up column-wise and a total can be scanned.",
    render: () => (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Source</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Sessions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {[
            ["Search Console", "Connected", "18,204"],
            ["Google Ads", "Partial", "4,981"],
            ["Stripe", "Not connected", "—"],
          ].map(([source, status, n]) => (
            <TableRow key={source}>
              <TableCell className="font-medium">{source}</TableCell>
              <TableCell className="text-muted-foreground">{status}</TableCell>
              <TableCell className="text-right tabular-nums">{n}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    ),
  },
  {
    id: "ui-progress",
    group: "Primitives",
    title: "Progress",
    state: "determinate",
    note: "Only when the fraction is real. Unknown-length work gets PipelineProgress or a spinner, never a bar that guesses.",
    render: () => (
      <div className="flex max-w-sm flex-col gap-4">
        <Progress value={18} aria-label="Crawl progress: 18%" />
        <Progress value={64} aria-label="Crawl progress: 64%" />
        <Progress value={100} aria-label="Crawl progress: complete" />
      </div>
    ),
  },
  {
    id: "ui-breadcrumb",
    group: "Primitives",
    title: "Breadcrumb",
    state: "default",
    render: () => (
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink href="#">Projects</BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink href="#">Organic Growth</BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>Members</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
    ),
  },
  {
    id: "ui-menu",
    group: "Primitives",
    title: "Dropdown menu",
    state: "open",
    note: "Radix supplies portal, focus trap, Escape and typeahead. Never hand-roll a menu.",
    render: () => (
      <DropdownMenu defaultOpen modal={false}>
        <DropdownMenuTrigger asChild>
          <Button size="sm" variant="outline">
            Actions
            <ChevronDown aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuLabel>Organic Growth</DropdownMenuLabel>
          <DropdownMenuItem>Rename</DropdownMenuItem>
          <DropdownMenuItem>Duplicate</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem variant="destructive">Delete project</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    ),
  },
  {
    id: "ui-tooltip",
    group: "Primitives",
    title: "Tooltip",
    state: "open",
    note: "A tooltip supplements a name, it never supplies one — an icon-only button still needs its aria-label.",
    render: () => (
      <div className="flex items-center gap-6">
        <Tooltip open>
          <TooltipTrigger asChild>
            <Button size="icon-sm" variant="ghost" aria-label="Where this credential lives">
              <Settings aria-hidden="true" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">Saved to your account</TooltipContent>
        </Tooltip>
        <Separator orientation="vertical" className="h-6" />
        <span className="text-xs text-muted-foreground">
          Held open here; it opens on hover and on keyboard focus.
        </span>
      </div>
    ),
  },
];
