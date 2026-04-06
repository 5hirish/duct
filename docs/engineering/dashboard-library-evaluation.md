# shadcn/ui + Luma Implementation Plan for Duct App

## Context

Duct's Next.js 16 app needs a component library for reports, account management, and settings pages. After evaluating shadcn/ui, daisyUI, Mantine, Tremor, and Refine, **shadcn/ui** was selected for its copy-paste ownership model, Radix accessibility primitives, full coverage of all 3 needs, and alignment with Duct's minimal-dependency philosophy.

**Duct's current stack**: Next.js 16.2.2, React 19, zero UI libraries, vanilla CSS (`globals.css` — 1,534 lines), deployed on Cloudflare Workers.

**Duct's brand**: Orange `#ff5c00`, Navy `#0d0f1a`, off-white `#f7f7f6`, border `#ebebea`, 12px/20px radius, frosted glass header.

---

## shadcn/create Configuration

### Complete Settings

| Setting | Pick | Notes |
|---------|------|-------|
| **Base style** | **Luma** | Rounded geometry + soft elevation (uses `rounded-3xl` containers, `rounded-2xl` items, `shadow-lg` with `ring-1`). Matches Duct's frosted glass + rounded aesthetic |
| **Component base** | **Radix** | More mature a11y primitives, default choice |
| **Base color** | **Stone** | Warm neutrals complement orange; matches Duct's warm off-white `#f7f7f6` |
| **Icon library** | **Lucide React** | 1,541 icons, 5 KB/50 icons (lightest), best tree-shaking |
| **Font (sans)** | **DM Sans** | Rounded, warm, modern geometric sans-serif — complements Luma's rounded aesthetic and orange brand warmth. Replaces system font stack for body text |
| **Font (mono)** | **JetBrains Mono** | Default mono, clean for any code/data displays |
| **Border radius** | **Luma defaults** | `rounded-3xl` containers, `rounded-2xl` items — larger radii than Duct's current 12px/20px, but aligns with Luma's design language |

### Color Configuration (OKLCH)

Primary and semantic colors mapped from Duct's brand, using OKLCH color space (shadcn/ui v4 default):

```css
@layer base {
  :root {
    /* Core brand mapping */
    --background: oklch(1.0 0 0);                /* white */
    --foreground: oklch(0.18 0.03 265);           /* #0d0f1a navy */

    --primary: oklch(0.62 0.22 38);               /* #ff5c00 orange */
    --primary-foreground: oklch(1.0 0 0);          /* white on orange */

    --secondary: oklch(0.96 0.005 80);             /* #f7f7f6 off-white */
    --secondary-foreground: oklch(0.18 0.03 265);  /* navy on off-white */

    --accent: oklch(0.96 0.005 80);                /* #f7f7f6 off-white */
    --accent-foreground: oklch(0.18 0.03 265);     /* navy */

    --muted: oklch(0.96 0.005 80);                 /* #f7f7f6 off-white */
    --muted-foreground: oklch(0.50 0.02 265);      /* #6b6f82 navy-3 */

    --destructive: oklch(0.58 0.22 27);            /* red for errors */
    --destructive-foreground: oklch(1.0 0 0);      /* white on red */

    --card: oklch(1.0 0 0);                        /* white */
    --card-foreground: oklch(0.18 0.03 265);       /* navy */

    --popover: oklch(1.0 0 0);                     /* white */
    --popover-foreground: oklch(0.18 0.03 265);    /* navy */

    --border: oklch(0.92 0.005 80);                /* #ebebea */
    --input: oklch(0.92 0.005 80);                 /* #ebebea */
    --ring: oklch(0.62 0.22 38);                   /* orange focus ring */
  }
}
```

### Chart Color Palette

Warm brand-cohesive palette derived from orange primary + navy secondary using analogous/complementary color theory:

```css
:root {
  /* Chart: orange-anchored warm palette with navy contrast */
  --chart-1: oklch(0.62 0.22 38);     /* Orange — primary data series */
  --chart-2: oklch(0.30 0.05 265);    /* Navy — secondary/contrast series */
  --chart-3: oklch(0.72 0.16 60);     /* Amber — warm analogous to orange */
  --chart-4: oklch(0.55 0.08 265);    /* Steel blue — cool complement */
  --chart-5: oklch(0.80 0.12 80);     /* Warm gold — light accent */
}
```

### Font Update

**Replacing**: Georgia serif headings + system sans body
**With**: DM Sans for body/UI + keeping Georgia for editorial headings if desired

DM Sans rationale:
- Geometric, rounded letterforms match Luma's rounded components
- Warm character complements orange brand (unlike cold fonts like Inter)
- Excellent legibility at dashboard sizes (12-16px)
- Variable font with weight range 100-1000
- Available via `next/font/google` (no external CDN)

```css
@theme {
  --font-sans: 'DM Sans Variable', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'JetBrains Mono Variable', monospace;
}
```

---

## Implementation Steps

### Phase 1: Install Tailwind v4 + shadcn/ui

1. Add devDeps:
   ```bash
   cd app
   npm install -D tailwindcss @tailwindcss/postcss
   ```

2. Create `postcss.config.mjs`:
   ```js
   export default {
     plugins: {
       "@tailwindcss/postcss": {},
     },
   };
   ```

3. Add `@import "tailwindcss"` at the top of `src/app/globals.css` (existing CSS continues working)

4. Add `@theme` block mapping Duct's existing CSS vars to Tailwind tokens

5. Verify existing UI renders identically

6. Initialize shadcn/ui:
   ```bash
   npx shadcn@latest init
   ```
   - Style: radix-luma
   - Base color: stone
   - CSS variables: yes
   - Icon library: lucide
   - Configure `components.json` aliases to match `src/` structure

7. Apply custom color + chart + font overrides to globals.css

8. Add initial components:
   ```bash
   npx shadcn@latest add button input select card table form tabs switch
   ```

### Phase 2: Build new features with shadcn/ui
- Account management page: `Form`, `Input`, `Avatar`, `Card`, `Dialog`
- Settings page: `Tabs`, `Switch`, `RadioGroup`, `Select`, `Label`
- New report components: `Table`, `Card`, `Badge`, `Tooltip`

### Phase 3: Gradual migration (optional)
- Convert generate wizard's form elements to shadcn/ui
- **Do NOT migrate** `GoogleAdsReport.js`, `ReportsList.jsx`, or custom chart/KPI components — purpose-built and better than library equivalents

---

## Key Files

| File | Action |
|------|--------|
| `app/package.json` | Add Tailwind + PostCSS devDeps |
| `app/postcss.config.mjs` | Create — PostCSS config for Tailwind v4 |
| `app/src/app/globals.css` | Add `@import "tailwindcss"`, `@theme`, color tokens |
| `app/components.json` | Created by `shadcn init` — configure aliases + style |
| `app/src/components/ui/` | Created by `shadcn add` — owned component source |
| `app/src/lib/utils.ts` | Created by `shadcn init` — `cn()` utility |
| `app/next.config.mjs` | Verify PostCSS integration (should work automatically) |
| `app/src/components/GoogleAdsReport.js` | Do NOT modify |

---

## Verification

1. After Tailwind install: all existing pages render identically (visual regression check)
2. After shadcn init: `<Button>` renders with orange primary color + Luma rounded style
3. `next build` succeeds on Cloudflare Workers target
4. CSS output size stays reasonable (Tailwind v4 tree-shakes aggressively)
5. DM Sans font loads correctly via `next/font/google`
