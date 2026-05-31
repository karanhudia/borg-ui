---
name: Borg UI
description: Calm, modern, precise web interface for BorgBackup operations.
colors:
  # Brand identity (logo, address bar, brand-tinted surfaces).
  brand: "#059669"
  brand-deep: "#065f46"
  # Framework primary used in MUI/Tailwind (NOT the brand color; see "Open Issues"
  # for the known divergence between framework primary and brand identity).
  primary: "#2563eb"
  primary-light: "#3b82f6"
  primary-dark: "#1e40af"
  primary-50: "#eff6ff"
  primary-100: "#dbeafe"
  primary-200: "#bfdbfe"
  primary-300: "#93c5fd"
  primary-400: "#60a5fa"
  primary-500: "#3b82f6"
  primary-600: "#2563eb"
  primary-700: "#1d4ed8"
  primary-800: "#1e40af"
  primary-900: "#1e3a8a"
  secondary: "#7c3aed"
  secondary-light: "#8b5cf6"
  secondary-dark: "#6d28d9"
  success: "#16a34a"
  success-light: "#22c55e"
  success-dark: "#15803d"
  warning: "#ea580c"
  warning-tw-500: "#f59e0b"
  warning-tw-600: "#d97706"
  danger: "#dc2626"
  danger-light: "#ef4444"
  danger-dark: "#b91c1c"
  info: "#0891b2"
  info-light: "#06b6d4"
  bg-default-light: "#f9fafb"
  bg-paper-light: "#ffffff"
  bg-default-dark: "#1a1a1a"
  bg-paper-dark: "#27272a"
  text-primary-light: "#111827"
  text-secondary-light: "#6b7280"
  text-primary-dark: "#fafafa"
  text-secondary-dark: "#a1a1aa"
  dash-glass-text-primary-light: "#1e293b"
  dash-glass-text-primary-dark: "#e2e8f0"
  dash-glass-text-muted-light: "#64748b"
  dash-glass-text-muted-dark: "#94a3b8"
  dash-status-healthy: "#22c55e"
  dash-status-warning: "#f59e0b"
  dash-status-critical: "#ef4444"
  dash-status-unknown: "#64748b"
  dash-accent-blue: "#3b82f6"
  dash-accent-indigo: "#6366f1"
  dash-accent-pink: "#ec4899"
  step-location-light: "#1565c0"
  step-location-dark: "#64b5f6"
  step-source-light: "#2e7d32"
  step-source-dark: "#81c784"
  step-security-light: "#7b1fa2"
  step-security-dark: "#ce93d8"
  step-config-light: "#e65100"
  step-config-dark: "#ffb74d"
  step-review-light: "#0277bd"
  step-review-dark: "#4fc3f7"
  entity-accent-default: "#059669"
  entity-accent-highlight: "#f59e0b"
  meta-theme-color-light: "#059669"
  meta-theme-color-dark: "#065f46"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "2.25rem"
    fontWeight: 700
    lineHeight: 1.2
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 600
    lineHeight: 1.3
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.4
  subtitle:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.5
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  body-small:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: 1.2
  mono-data:
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', ui-monospace, monospace"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.4
rounded:
  xs: "2px"
  sm: "6px"
  md: "8px"
  lg: "12px"
  xl: "14px"
  pill: "999px"
  full: "50%"
spacing:
  baseline: "8px"
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  page-x-mobile: "12px"
  page-x-desktop: "24px"
  drawer-width: "240px"
  header-height: "64px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#ffffff"
    rounded: "{rounded.lg}"
    padding: "8px 16px"
    typography: "{typography.label}"
  button-primary-hover:
    backgroundColor: "{colors.primary-700}"
    textColor: "#ffffff"
  button-secondary:
    backgroundColor: "#e5e7eb"
    textColor: "{colors.text-primary-light}"
    rounded: "{rounded.lg}"
    padding: "8px 16px"
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "#ffffff"
    rounded: "{rounded.lg}"
    padding: "8px 16px"
  card-flat:
    backgroundColor: "{colors.bg-paper-light}"
    rounded: "{rounded.md}"
    padding: "24px"
  card-glass-light:
    backgroundColor: "rgba(0,0,0,0.03)"
    rounded: "{rounded.xl}"
    padding: "16px"
  card-glass-dark:
    backgroundColor: "rgba(255,255,255,0.05)"
    rounded: "{rounded.xl}"
    padding: "16px"
  input-outlined:
    backgroundColor: "{colors.bg-paper-light}"
    textColor: "{colors.text-primary-light}"
    rounded: "{rounded.lg}"
    padding: "8px 12px"
    height: "56px"
  chip-status:
    rounded: "{rounded.sm}"
    typography: "{typography.body-small}"
  wizard-step-active:
    backgroundColor: "{colors.step-location-light}"
    textColor: "#ffffff"
    rounded: "{rounded.full}"
    width: "32px"
    height: "32px"
---

# Design System: Borg UI

## 1. Overview

**Creative North Star: "The Safe Pair of Hands"**

Borg UI sits in the same homelab tab as Plex, Linear, Tailscale, and Proxmox. It is operational, not aspirational. The user is opening it at 3am because a backup failed, or on a quiet Sunday to set up a new SFTP repository; in both cases the surface needs to feel like a dependable instrument rather than a marketing site. The visual register matches that: emerald-tinted neutrals carrying the brand, restrained accents on status, generous spacing, real motion only where it earns its place, and a dual MUI plus Tailwind token stack tuned in both light and dark modes.

The system is "Restrained" in color strategy. The brand identity is **emerald** (`#059669` on the logo, `#065f46` deep); surface tints across the dashboard pick up a low-alpha version of that hue so the page feels brand-anchored without being colored. Status semantics (green, amber, red) appear only on actual status, never as decoration. The framework primary in MUI and Tailwind is currently blue (`#2563eb`), which is a known divergence from the brand identity captured in **Open Issues** below; until that's reconciled, components that route through `theme.palette.primary.main` still render blue. The dashboard introduces a small set of named accent dyes (indigo `#6366f1`, blue `#3b82f6`, pink `#ec4899`) for charts; the rest of the product treats color as load-bearing signal, not flavor. Wizards earn one named-step color each (blue location, green source, purple security, orange config, cyan review) so that the user always knows which phase of which wizard they are in, in both themes.

Density is product-grade: 8px spacing baseline, 8px to 14px corner radii, page gutters of 12px on mobile growing to 24px on desktop, a fixed 240px sidebar drawer, and a 64px header. Type rhythm is system-font driven. Numbers and identifiers on the dashboard switch to `JetBrains Mono` to read as data.

This system explicitly rejects:
- Webmin / Cockpit / cPanel / 2014-era Bootstrap admin chrome.
- Consumer SaaS marketing inside the app: hero metric cards with gradient accents, aspirational empty-state illustrations, emoji-led tooltips, verbs like "supercharge".
- Cream / sand / beige body backgrounds, tracked all-caps eyebrows above every section, numbered `01 . 02 . 03` scaffolding, gradient text, decorative glassmorphism.
- Heavy left-accent borders on cards, alerts, list items, or status surfaces.

**Key Characteristics:**
- Restrained palette: one blue primary, status colors load-bearing, neutral surfaces.
- Dual token systems: MUI theme tokens (`frontend/src/theme.ts`) for product chrome plus a Tailwind palette (`frontend/tailwind.config.js`) for utility composition; both share blue 600 (`#2563eb`) as the primary anchor.
- Light and dark are first-class. Dark is not an inversion; it has its own paper (`#27272a`) and text scale (`#fafafa` / `#a1a1aa`).
- Component reuse is the design system. `ResponsiveDialog`, `WizardDialog`, `WizardStepIndicator`, `SshConnectionSelect`, `RichSelectRow`, `EntityCard`, `StatusBadge` are the real source of truth; visual consistency is enforced by composition, not by a written guide.

## 2. Colors

The palette is a restrained emerald-brand system: brand-tinted neutrals across surfaces, a (currently blue) framework primary for interactive controls, and green/amber/red reserved for true status. Indigo and pink appear only inside the dashboard chart vocabulary. Wizard step keys have their own named light/dark color pair. The brand-vs-framework gap is documented in Open Issues.

### Brand
- **Borg Emerald** (`#059669` light, `#065f46` deep): the brand identity. Pulled directly from `assets/logo-light.png` / `assets/logo-dark.png` and the `BORG UI 2.0` badge. Drives the address-bar `theme-color` in `frontend/index.html`, the dashboard's tinted `bgCard` / `border` surfaces in `dashboard-v3/tokens.tsx`, and is the canonical emerald to reach for when a chrome surface needs to feel "of Borg UI".

### Framework Primary (out of sync with brand)
- **Framework Blue** (`#2563eb` light, `#3b82f6` dark): MUI `palette.primary.main` in `frontend/src/theme.ts` and Tailwind `primary.600` in `frontend/tailwind.config.js`. Currently carries primary buttons, primary focus rings, active nav, link text, primary CTAs. This is the legacy framework default; until reconciled with the brand emerald (see Open Issues), components routing through `palette.primary` will render blue. New chrome surfaces should reach for the brand emerald; new interactive controls keep using `palette.primary` until the migration.
- **Framework Blue Deep** (`#1e40af`, Tailwind `primary.800`, MUI `palette.primary.dark`): hover state for primary surfaces.

### Secondary
- **Violet Accent** (`#7c3aed` light, `#8b5cf6` dark): MUI `palette.secondary.main`. Used sparingly: secondary chips, occasional emphasis. Not a brand color; treat as a tertiary highlight.

### Status (Tertiary, semantic)
- **Success Green** (`#16a34a` MUI, `#22c55e` dashboard, `success.600` Tailwind): "completed", healthy repository, connected SSH dot. The dashboard `tokens.tsx` and Tailwind use `#22c55e`; MUI uses the deeper `#16a34a`. Both ship in the product.
- **Warning Amber** (`#ea580c` MUI, `#f59e0b` dashboard and EntityCard highlight): the MUI palette uses orange `#ea580c`; the dashboard and Tailwind `warning.500` use the softer amber `#f59e0b`. Pairs with an icon or chip, never used alone as a colored stripe.
- **Danger Red** (`#dc2626` MUI, `#ef4444` dashboard and Tailwind `danger.500`): "failed", critical health, destructive confirm buttons. Same dual-value pattern as warning.
- **Info Cyan** (`#0891b2` MUI, `#06b6d4` light): running / in-progress states.

### Dashboard Glass Surfaces
The DashboardV3 surface ("Void" command center) uses a separate token set in `frontend/src/pages/dashboard-v3/tokens.tsx`:
- **Glass Card** (`rgba(255,255,255,0.05)` dark, `rgba(0,0,0,0.03)` light): card fill.
- **Hairline Border** (`rgba(255,255,255,0.08)` dark, `rgba(0,0,0,0.1)` light): 1px card border.
- **Slate Text Primary** (`#e2e8f0` dark, `#1e293b` light): body text.
- **Slate Text Muted** (`#94a3b8` dark, `#64748b` light): supporting copy.
- **Chart Hues**: indigo `#6366f1`, blue `#3b82f6`, green `#22c55e`, amber `#f59e0b`, pink `#ec4899` (`SEG_COLORS`). Job-type chart colors are pinned: backup green, check blue, compact indigo, restore amber, prune pink.

### Wizard Step Colors
Defined in `frontend/src/components/wizard/WizardStepIndicator.tsx` as named light/dark pairs:
- **location** `#1565c0` / `#64b5f6` (blue)
- **source** `#2e7d32` / `#81c784` (green)
- **security** `#7b1fa2` / `#ce93d8` (purple)
- **config** `#e65100` / `#ffb74d` (orange)
- **review** `#0277bd` / `#4fc3f7` (cyan)
- Schedule wizard reuses the same palette under the keys `basic`, `schedule`, `scripts`, `maintenance`.

### Neutrals
- **Page Background** (`#f9fafb` light, `#1a1a1a` dark): MUI `background.default`. The dark value is a custom soft gray, not pure black.
- **Paper / Card Background** (`#ffffff` light, `#27272a` dark, Zinc 800).
- **Text Primary** (`#111827` light, `#fafafa` dark).
- **Text Secondary** (`#6b7280` light, `#a1a1aa` dark).
- **Border / Divider**: MUI `divider` token; on dashboard glass surfaces the hairline border replaces it.

### Named Rules
**The Brand-Anchored Surface Rule.** The brand identity is emerald (`#059669` light, `#065f46` deep). Surface tints, address-bar `theme-color`, and the dashboard's `bgCard` / `border` tokens carry a low-alpha version of that hue so the page reads as Borg UI without colored cards. Status colors (green, amber, red) still carry semantic state on top. The framework primary (MUI `palette.primary.main = #2563eb`, Tailwind `primary.600`) currently anchors buttons and links and is OUT OF SYNC with the brand identity; see Open Issues. Until reconciled, follow this rule: tinted neutrals and chrome use the emerald brand; primary CTAs continue to use whatever `palette.primary` resolves to.

**The Color-Is-Signal Rule.** Green, amber, and red appear only when the surface actually reports success, warning, or failure status. They are never used as decoration, gradients, or section eyebrows. A green chip means the thing is connected. A red chip means the thing failed. If you cannot defend the semantic, use a neutral.

**The Tinted-Status-Background Rule.** Status tint is carried by background alpha plus a matching icon or chip, never by a colored left border. See `dashboard-v3/tokens.tsx`: `greenDim: rgba(34,197,94,0.1)`, `redDim: rgba(239,68,68,0.1)`. Pair tint with the corresponding solid color in iconography and labels.

## 3. Typography

**Display / Body Font:** the macOS / Windows system stack, `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`. No webfont download. Set in `frontend/src/theme.ts` and `frontend/src/index.css`.

**Mono / Data Font:** `JetBrains Mono`, with fallbacks `Fira Code`, `Cascadia Code`, `ui-monospace`, `monospace`. Used on the DashboardV3 surface for every numeric and identifier value (archive IDs, sizes, exit codes, timestamps in compact form). Defined in `frontend/src/pages/dashboard-v3/tokens.tsx`.

**Character:** native and unsentimental. The system font reads as part of the OS; the mono switch on data reads as "these are real numbers, not marketing". Pairing avoids the "homepage typeface" feeling.

### Hierarchy

Sizes from `theme.ts`:
- **Display / h1** (700, `2.25rem`, line-height 1.2): the top of a page-level header. Rarely shown inside the app; most product pages start at h2 or use `PageHeader`.
- **Headline / h2** (600, `1.875rem`, line-height 1.3): page section openers.
- **Title / h3** (600, `1.5rem`, line-height 1.4): card and dialog titles, including `WizardDialog` titles which override to `variant="h5"` at `fontWeight: 700`.
- **Subtitle / h4** (600, `1.25rem`, line-height 1.5): sub-section titles inside cards.
- **h5** (600, `1.125rem`, line-height 1.5): wizard dialog title (boosted to weight 700 in `WizardDialog`).
- **h6** (600, `1rem`, line-height 1.5): list group labels.
- **Body / body1** (400, `1rem`, line-height 1.5): the workhorse paragraph size.
- **Body Small / body2** (400, `0.875rem`, line-height 1.5): table rows, secondary descriptions, `RichSelectRow` primary line, dialog subtitles.
- **Label / caption** (500, `0.75rem` to `0.875rem`, line-height 1.2 to 1.3): chip labels, `RichSelectRow` secondary line, wizard step labels, status badges.
- **Mono Data** (`JetBrains Mono`, `0.875rem`): dashboard numeric values, repo IDs.

### Named Rules

**The Numbers Are Mono Rule.** Numeric values on the dashboard, archive IDs, repo IDs, exit codes, and any tabular numeric data render in `JetBrains Mono`. Prose stays in the system stack. The switch is the signal that this is real data, not narrative.

**The No-Eyebrow Rule.** No tracked all-caps eyebrow labels above sections (e.g. `· OVERVIEW ·`, `01 . SETUP`). Section structure is conveyed by the h2 / h3 heading and spacing.

**The No-Title-Case-Buttons Rule.** Buttons use sentence case, not title case. Set by `theme.ts` `components.MuiButton.styleOverrides.root.textTransform: 'none'` and `typography.button.textTransform: 'none'`. "Save changes", not "Save Changes" or "SAVE CHANGES".

## 4. Elevation

The system is mostly flat with two distinct elevation vocabularies layered on top.

**1. Product chrome (MUI default).** Cards use a low ambient shadow (`box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)`) set in `theme.ts` `MuiCard.styleOverrides.root`. Buttons explicitly disable shadow at rest (`boxShadow: 'none'`) and apply a near-invisible `0 1px 2px 0 rgb(0 0 0 / 0.05)` on `contained:hover` only. This is "calm" elevation: surfaces sit on the page, lifted only on direct hover.

**2. Dialogs (WizardDialog).** Dialogs get a real elevation. The Paper sx in `frontend/src/components/wizard/WizardDialog.tsx`:
- Light: `box-shadow: 0 24px 48px rgba(0,0,0,0.1)`
- Dark: `box-shadow: 0 24px 48px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.1)`
Plus `backdrop-filter: blur(10px)` and a near-imperceptible top sheen (`linear-gradient(rgba(255,255,255,0.05), rgba(255,255,255,0.05))`). This is the only place in the product where backdrop-filter is used.

**3. Dashboard glass (DashboardV3).** A separate vocabulary. Cards are translucent surfaces (`rgba(255,255,255,0.05)` dark, `rgba(0,0,0,0.03)` light) with a hairline border (`rgba(255,255,255,0.08)` dark, `rgba(0,0,0,0.1)` light) and `backdropFilter: blur(12px)`. Border color shifts on hover to `borderHover` (`rgba(255,255,255,0.18)` dark, `rgba(0,0,0,0.22)` light). No drop shadow. Elevation is signaled by tint plus border contrast, not by cast shadow.

### Shadow Vocabulary
- **Card rest** (`0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)`): MUI `MuiCard` default; product surfaces.
- **Button hover** (`0 1px 2px 0 rgb(0 0 0 / 0.05)`): only on `MuiButton` `variant="contained"` hover.
- **Wizard step pulse** (`0 2px 8px alpha(stepColor, 0.4)`): active step circle in `WizardStepIndicator`.
- **Dialog lift light** (`0 24px 48px rgba(0,0,0,0.1)`): `WizardDialog` paper.
- **Dialog lift dark** (`0 24px 48px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.1)`): dark dialog paper, includes an inset ring instead of a border.

### Named Rules

**The Flat-By-Default Rule.** Surfaces are flat at rest. Cards have one near-invisible 1px shadow; buttons have none. Real elevation is reserved for modals and the dashboard's glass treatment.

**The No-Glass-Outside-Dashboard Rule.** Backdrop-filter blur appears in exactly two places: the WizardDialog paper, and DashboardV3 glass cards. Do not glassmorph generic product cards, alerts, or list items.

## 5. Components

Reach for the shared primitives first. Reinventing them is the most common drift vector in this codebase.

### Buttons
- **Shape:** softly rounded (12px). Overridden from MUI's default 8px in `theme.ts` `MuiButton.styleOverrides.root.borderRadius: 12`.
- **Primary (MUI `contained color="primary"`):** background `#2563eb` light / `#3b82f6` dark, white text, weight 600, font size `0.875rem`, padding `8px 16px`, sentence case, no shadow at rest, faint shadow on hover only.
- **Tailwind primary (`.btn-primary` in `index.css`):** background `bg-primary-600`, hover `bg-primary-700`, focus ring `ring-primary-500`, padding `px-4 py-2`, rounded `rounded-lg` (8px). Used by older or Tailwind-first surfaces.
- **Secondary:** MUI outlined or Tailwind `.btn-secondary` (gray-200 background, gray-900 text).
- **Danger:** MUI `color="error"` or Tailwind `.btn-danger` (danger-600 background, hover danger-700).
- **Focus:** Tailwind buttons render a 2px ring with 2px offset on focus. MUI buttons inherit MUI's default focus-visible outline.

### Cards / Containers
- **Standard card (MUI):** white paper (`#27272a` dark), 8px radius, border `1px solid` of the theme divider on Tailwind `.card`, near-invisible shadow on MUI `Card`. Internal padding 24px (`p-6` in `.card`).
- **EntityCard** (`frontend/src/components/EntityCard.tsx`): composes title, subtitle, stats grid, meta rows, tag chips, footer toggle plus action icons. Uses a 32x32 rounded square (radius `1.5` from MUI spacing, ~12px) for icon buttons. Accent default `#059669` (green), highlight `#f59e0b` (amber). Action icon hover bg: `alpha('#fff', 0.07)` dark, `alpha('#000', 0.06)` light.
- **DashboardV3 glass card:** see Elevation section. Radius 14px (`T.radius`), translucent fill, hairline border, blur 12px.

### Inputs / Fields
- **MUI TextField / Select:** default `variant="outlined"`, `size="small"`, radius 8px. The `SshConnectionSelect` overrides the trigger to a fixed 56px height (the standard MUI outlined input height) to prevent the empty state from collapsing.
- **Tailwind input (`.input`):** `border-gray-300`, focus ring `ring-primary-500`, focus border transparent, radius 8px.

### Chips / Badges
- **MUI Chip:** radius 6px (`theme.ts` override), used for tags, repository labels, plan badges.
- **StatusBadge** (`frontend/src/components/StatusBadge.tsx`): outlined `Chip` whose color maps from status string: `completed` to success, `failed` to error, `running` to info, `completed_with_warnings` to warning, `pending` to default. Wrapped in a Tooltip carrying the localized status label. Pairs color with text (never color alone).
- **Connected dot** (in `SshConnectionSelect`): 8px filled circle in `success.main`. Optional tooltip on hover.

### Alerts
MUI `Alert` with radius 6px. Severity carries color and icon together. Anti-pattern (banned): no left-accent border stripe wider than 1px; emphasis must come from background tint plus icon plus body text.

### Navigation
- **AppHeader** (`frontend/src/components/AppHeader.tsx`): fixed AppBar, height 64px, translucent background (`alpha(background.default, 0.9)` dark, `0.82` light), zero elevation, `text.primary` foreground. Holds the mobile menu button, plan badge (drawer), notification bell, and user avatar popover.
- **AppSidebar**: fixed Drawer, width 240px, system font, lucide-react icons. Mobile collapses into a SwipeableDrawer toggled by the header menu button. Items composed via `NavItem` and `NavGroup` (collapsible groups).
- **Layout shell** (`frontend/src/components/Layout.tsx`): flex row of sidebar plus main; main has horizontal padding `xs 12px / sm 20px / md 24px`, vertical padding `xs 16px / sm 24px`, background `background.default`, and wraps content in a `Container maxWidth="xl"` with `mt: 1/2` and inner `px: 0/8px`. Above the page, the `<Toolbar />` spacer reserves the 64px header.

### Dialogs (Signature)
- **ResponsiveDialog** (`frontend/src/components/ResponsiveDialog.tsx`): the canonical dialog primitive. Below the `md` breakpoint it renders a bottom-anchored `SwipeableDrawer` with a 44px drag-handle row (32x4 pill in `divider` color), close icon at top-right, scrollable content, and a sticky footer that respects `env(safe-area-inset-bottom)`. At and above `md` it renders a centered `Dialog`. Paper radius: 16px top corners on mobile drawer; default on desktop.
- **WizardDialog** (`frontend/src/components/wizard/WizardDialog.tsx`): composes ResponsiveDialog plus WizardStepIndicator. Paper radius 24px (`borderRadius: 3` in MUI spacing units), fixed height `min(860px, calc(100vh - 64px))` on desktop, glass blur and elevated shadow as documented in Elevation. Title renders as `variant="h5"` weight 700, optional subtitle in `body2 text.secondary`. Content area has min-height 450px on desktop and `auto` on mobile.

### Wizard Step Indicator (Signature)
`frontend/src/components/wizard/WizardStepIndicator.tsx`. Two responsive forms:
- **Desktop:** full-width grid of equal-width tabs. Each tab shows a 30-32px filled circle icon plus `(index+1). Label`. Active tab gets a 2px bottom underline animated via `scaleX` over a `cubic-bezier(0.4, 0, 0.2, 1)` 300ms transition; the circle bg fills with the step color and a `0 2px 8px alpha(stepColor, 0.4)` shadow appears.
- **Mobile:** a label row (`Step X / N` left, active step name in step color right) above a centered row of 40x40 icon circles with a 16x2 underline dot under the active circle. Inactive circles use `alpha(stepColor, 0.1)` background and the step color as foreground; active uses solid step color background and white foreground, plus a `scale(1.1)` lift.
Step keys map to fixed light/dark color pairs (see Colors). Reuse the keys (`location`, `source`, `security`, `config`, `review`, `basic`, `schedule`, `scripts`, `maintenance`); do not invent new ones.

### SshConnectionSelect (Signature)
`frontend/src/components/SshConnectionSelect.tsx`. Used in the Repository wizard's Location and Data Source steps and in the Backup Plan source dialog. Renders an MUI outlined Select at fixed 56px height, with each option a `RichSelectRow`: 32x32 rounded-square icon container (Cloud icon, `action.hover` background, `text.secondary` foreground), primary line `user@host` in body2 weight 600 (truncated), secondary line `Port X . mount_point | default_path` in caption text.secondary (truncated), plus an 8px green status dot when the connection is connected. Empty state renders an MUI Alert severity warning unless `hideEmptyAlert` is set.

### RichSelectRow
`frontend/src/components/wizard/RichSelectRow.tsx`. The shared row shape inside any rich Select: 32x32 icon square, 2-line text with truncation, optional indicator at the right of the primary line. Use this; do not hand-roll a `Box`/`Stack` composition for select options.

### Motion
- **Easing:** `cubic-bezier(0.4, 0, 0.2, 1)` (MUI's standard) and `'ease'` for simple state changes.
- **Durations:** 200ms (button color hover, generic transitions), 300ms (wizard step active transitions, scale, underline).
- **Animated properties:** background color, transform (`scale`, `scaleX`, `translateY`), box-shadow, border color, opacity. No layout-thrash animations.
- **Reduced motion:** the codebase does not yet ship a global `prefers-reduced-motion` override; PRODUCT.md targets WCAG 2.1 AA and commits to one. Documented under Open Issues.

## 6. Do's and Don'ts

### Do
- **Do** anchor brand chrome (address bar, tinted surfaces, brand artwork) on Borg Emerald (`#059669` light, `#065f46` deep). Anchor interactive primary controls (buttons, links, focus rings, active nav) on whatever `theme.palette.primary.main` resolves to. Today those are different colors; see Open Issues for the reconciliation plan.
- **Do** keep status semantics load-bearing. Green only when something is healthy or connected; amber only on warning; red only on failure.
- **Do** use sentence case on buttons. `theme.ts` sets `textTransform: 'none'`; never override it.
- **Do** compose new dialogs from `ResponsiveDialog`. Wizards must compose `WizardDialog`. Place action buttons in the `footer` prop so they stay sticky above the iOS safe area on mobile.
- **Do** reuse `WizardStepIndicator` step-color keys (`location`, `source`, `security`, `config`, `review`, `basic`, `schedule`, `scripts`, `maintenance`). Pick the closest semantic match instead of introducing a new color.
- **Do** use `SshConnectionSelect` for any SSH connection dropdown. Extend or fix it; do not inline another `Select` over `SSHConnection[]`.
- **Do** use `RichSelectRow` inside any 2-line `MenuItem`.
- **Do** use `StatusBadge` for any job/run status surface, so color + label + tooltip stay consistent.
- **Do** render numeric data and identifiers on the dashboard in `JetBrains Mono`.
- **Do** verify light and dark mode for every new surface. Dark uses `#27272a` paper and `#fafafa` / `#a1a1aa` text, not an inverted light theme.
- **Do** size touch targets to at least 40x40 on mobile (the wizard step circles do this with 1.5x gap).

### Don't
- **Don't** introduce a third product-level accent color. The brand emerald anchors chrome; the framework primary anchors controls. Violet, indigo, and pink belong to dashboard charts or one wizard step, not to general UI.
- **Don't** use heavy left-accent borders on cards, alerts, list items, or status surfaces (AGENTS.md and PRODUCT.md both prohibit this). Carry emphasis with background tint plus icon plus label.
- **Don't** ship cream / sand / beige body backgrounds, tiny tracked all-caps eyebrows, numbered `01 . 02 . 03` section scaffolding, gradient text, or decorative glassmorphism outside `WizardDialog` and `DashboardV3` glass cards. These read as "AI made that".
- **Don't** rename borg vocabulary. "Archive" stays "archive", "repository" stays "repository", "prune" stays "prune". The user came here knowing borg; speak the same language.
- **Don't** wrap failure states in red walls or panicked copy. Failure surfaces are factual: status badge, error text, the next action button. Calm under failure is a design principle.
- **Don't** use hero metric cards with gradient accents, aspirational empty-state illustrations, or emoji-led tooltips. Borg UI is operational, not aspirational.
- **Don't** add a raw MUI `Dialog`. Reach for `ResponsiveDialog`. Adding a raw `Dialog` is almost always wrong (AGENTS.md).
- **Don't** roll a custom step indicator. `WizardStepIndicator` already covers desktop tabs and mobile circles.
- **Don't** rely on color as the only signal. Pair green/amber/red with an icon, label, or chip so color-blind users get the same information (WCAG 2.1 AA commitment in PRODUCT.md).
- **Don't** use `Title Case Buttons` or `ALL CAPS BUTTONS`. Sentence case only.
- **Don't** hardcode `'#2563eb'` in component code when MUI `palette.primary.main` or Tailwind `bg-primary-600` will do.

## 7. Open Issues

These are real inconsistencies and unfilled gaps in the current visual system. Resolve before treating them as ground truth.

1. **Framework primary is blue but brand identity is emerald.** The logo (`assets/logo-light.png`, `app/static/logo*.png`) is unmistakably emerald green at roughly `#059669`/`#065f46`. The dashboard's `theme-color`, surface tints, and brand-tinted neutrals (`dashboard-v3/tokens.tsx`) have been aligned to that brand identity. The framework primary in MUI (`theme.ts` `palette.primary.main = #2563eb`) and the Tailwind `primary` ramp (also blue) are still the legacy framework default and are OUT OF SYNC with the brand. Until reconciled, every primary button, link, focus ring, and active nav item routing through `palette.primary` will render blue against an emerald-tinted page. The right fix is to update MUI primary to the emerald ramp (and align Tailwind), but that's a large surface area change and warrants a dedicated migration. Document this divergence explicitly so the gap is visible and not papered over.

2. **Dual color system (MUI plus Tailwind) with non-identical values.** Status colors are defined twice with slightly different hex codes:
   - Warning: MUI `palette.warning.main = #ea580c` vs Tailwind `warning.500 = #f59e0b` vs dashboard amber `#f59e0b`.
   - Danger: MUI `palette.error.main = #dc2626` vs Tailwind `danger.500 = #ef4444` vs dashboard red `#ef4444`.
   - Success: MUI `palette.success.main = #16a34a` vs Tailwind `success.500 = #22c55e` vs dashboard green `#22c55e`.
   Either align both systems on the same hex, or formally document MUI as the "product chrome" palette and Tailwind/dashboard as the "data viz" palette and live with the split.

3. **MUI gray text (`text.secondary = #6b7280` light, `#a1a1aa` dark) on tinted status backgrounds risks failing WCAG 2.1 AA contrast** (≥ 4.5:1) when stacked on `alpha(statusColor, 0.1)` fills. Audit `RichSelectRow` secondary line, EntityCard meta rows, and StatusBadge tooltips against the actual rendered backgrounds in both themes and adjust either the tint alpha or the text color.

4. **No global `prefers-reduced-motion` override.** PRODUCT.md commits to WCAG 2.1 AA, which requires reduced-motion alternatives. `WizardStepIndicator` and `EntityCard` use `transform: scale(...)`, `translateY(...)`, and animated underlines unconditionally. Add a top-level `@media (prefers-reduced-motion: reduce)` rule (in `index.css` or via an emotion global) that collapses these to opacity-only or instant transitions.

5. **`WizardDialog` uses `backdrop-filter: blur(10px)` plus a faint white gradient sheen (`linear-gradient(rgba(255,255,255,0.05), rgba(255,255,255,0.05))`).** This is the closest the product gets to glassmorphism, which PRODUCT.md lists as an anti-pattern. The current treatment is restrained enough to read as "elevated modal" rather than "decorative glass", but the rule needs to be explicit so it does not drift. Either document the dialog blur as a sanctioned exception or remove it.

6. **`EntityCard` accent defaults to `#059669` (a teal-leaning green) and highlight to `#f59e0b`.** Neither value is in MUI's palette or the Tailwind ramp; both are one-offs hardcoded in the file. Either move them into the theme as named tokens (e.g. `entity.accent`, `entity.highlight`) or align to existing tokens.

7. **Dark mode "background.default" is `#1a1a1a`, a custom near-black.** Most MUI dark themes use `#121212`. Keep, but document it as intentional in `theme.ts` so future PRs do not "fix" it to MUI's default.

8. **No `box-shadow` token vocabulary.** Shadow values are inlined at the point of use (cards, dialogs, wizard step circles). Consider extracting a small set of named shadow tokens (`shadow.card`, `shadow.dialog`, `shadow.pulse`) into the theme or a constants file so they are not redefined per component.

9. **`btn`, `card`, `input` classes in `index.css` overlap with MUI's `MuiButton`, `MuiCard`, `MuiTextField` overrides.** Two parallel button systems exist. Document which surface uses which, or pick one (likely MUI for product chrome, Tailwind utilities for one-off layout) and migrate.
