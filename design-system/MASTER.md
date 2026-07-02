# Rusty UI-R2 Design System

## 1. Design Positioning
Rusty UI-R2 is a local authoring command center for novel rewriting. The visual direction is Obsidian-inspired, dark, glassmorphic, calm, and information-rich. It should feel like a personal writing studio rather than an admin panel.

Primary keywords:
- Obsidian-inspired
- Glassmorphism
- Dark creative workspace
- Personal dashboard
- Ambient background
- Translucent cards
- Author / writing studio
- Command center

The UI must remain practical: clear hierarchy, readable text, obvious loading/error states, and no decorative effect that hides workflow state.

## 2. Color Tokens
Use CSS custom properties as the single source of truth.

```css
:root {
  --bg-main: #07111f;
  --bg-ink: #030712;
  --bg-panel: rgba(15, 23, 42, 0.58);
  --bg-panel-strong: rgba(15, 23, 42, 0.78);
  --bg-panel-hover: rgba(30, 41, 59, 0.72);
  --border-soft: rgba(255, 255, 255, 0.12);
  --border-strong: rgba(255, 255, 255, 0.2);
  --text-main: #f8fafc;
  --text-muted: #94a3b8;
  --text-soft: #64748b;
  --accent-gold: #f0c36a;
  --accent-blue: #60a5fa;
  --accent-cyan: #67e8f9;
  --accent-green: #34d399;
  --accent-red: #fb7185;
  --accent-violet: #a78bfa;
}
```

Usage:
- Gold is for authoring warmth, key highlights, and primary dashboard accents.
- Blue/cyan is for active navigation, selected project state, and technical progress.
- Green is for completed/success states only.
- Red is for destructive or failed states only.
- Never use pure black as the main surface.

## 3. Typography
No external font files. Do not depend on Google Fonts at runtime.

Font stack:
```css
font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", system-ui, sans-serif;
```

Type scale:
- Hero clock: 64px / 700 / -0.04em
- Page title: 34px / 700
- Section title: 20px / 650
- Card title: 16px / 650
- Body: 14px / 400
- Meta: 12px / 500
- Label: 11px / 650 / 0.12em uppercase

Rules:
- Chinese labels are first-class; do not shrink Chinese text to fit English layouts.
- Use numeric metrics with tabular alignment where practical.
- Avoid long all-caps text except small technical labels.

## 4. Spacing System
Base spacing uses 4px increments.

Tokens:
- `--space-1`: 4px
- `--space-2`: 8px
- `--space-3`: 12px
- `--space-4`: 16px
- `--space-5`: 20px
- `--space-6`: 24px
- `--space-8`: 32px
- `--space-10`: 40px
- `--space-12`: 48px

Layout rules:
- App content padding: 28px desktop, 18px tablet, 14px mobile.
- Card padding: 20-24px desktop, 16px mobile.
- Dense lists use 10-12px row gaps.
- Avoid cramming more than three columns below 1100px.

## 5. Radius System
- Small controls: 10px
- Buttons: 12px
- Cards: 18px
- Feature panels: 24px
- Full shells/dialog panels: 28px

Use radius consistently. Do not mix sharp admin-table corners with glass cards.

## 6. Shadow and Glass Rules
Glass card base:
```css
background: var(--bg-panel);
border: 1px solid var(--border-soft);
box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
backdrop-filter: blur(22px);
```

Rules:
- Use stronger panel opacity for text-heavy areas.
- Do not place long text on weak blur over high-contrast background imagery.
- Keep shadows soft and wide; avoid material-style hard elevation.
- Hover lift is subtle: translateY(-1px) max.

## 7. Background Rules
The app shell uses an ambient generated CSS background, not a mandatory image asset.

Required layers:
- Deep navy radial base.
- Warm gold orb near upper-right or lower-left.
- Blue/cyan orb opposite the warm accent.
- Dark overlay to preserve contrast.
- Optional fine noise via CSS gradients only.

If a configurable background image is added later:
- Always apply `linear-gradient(rgba(3,7,18,.68), rgba(3,7,18,.86))`.
- Never render text directly over a bright photo.

## 8. Card Components
Glass cards are the primary building block.

Card variants:
- `default`: dashboard and mixed content.
- `strong`: text-heavy chapter/original/rewrite panels.
- `interactive`: project cards and navigation cards.
- `danger`: delete confirmations and error blocks.

Card content order:
- Optional eyebrow/meta label.
- Title.
- Supporting copy or metric.
- Actions at bottom or top-right, never floating randomly.

## 9. Button Levels
Primary:
- Gold-to-blue subtle gradient or strong gold.
- Used for creation, entering workspace, export success path.

Secondary:
- Transparent glass with soft border.
- Used for navigation and non-destructive actions.

Danger:
- Red border/text on dark glass, red fill only for final destructive confirmation.

Ghost:
- No border, low emphasis, used in sidebar/topbar utility controls.

All clickable elements need `cursor: pointer`, visible focus states, and disabled states that remain readable.

## 10. Status Tags
Status pill variants:
- `default`: gray, neutral imported/idle.
- `info`: blue, processing/current.
- `success`: green, completed.
- `warning`: gold/yellow, pending/needs rewrite.
- `danger`: red, failed/deleted risk.

Pills should be compact, rounded, and include text labels. Icons are optional but must use Lucide, not emoji.

## 11. Empty States
Empty states should be calm and useful.

Structure:
- Small framed icon from Lucide.
- Clear title.
- One-line explanation.
- Optional action button.

Tone:
- No fake success.
- No placeholder data pretending to be real.
- State whether the backend is unavailable, no project exists, or a selection is missing.

## 12. Loading / Error / Success States
Loading:
- Skeleton panels for cards/lists.
- Small spinner only for button-local operations.

Error:
- Red-accent glass card with exact user-actionable message.
- Preserve debug detail in collapsible/preformatted block only when useful.

Success:
- Green pill or compact toast.
- Do not interrupt writing flow with blocking success dialogs.

Backend unavailable:
- Show request-level error in the affected page.
- Do not replace the whole app with a startup gate in UI-R2.

## 13. Page Layout Rules
App shell:
- Left sidebar: 84px collapsed rail desktop, bottom nav or compact rail on mobile.
- Topbar: project-aware command strip, translucent.
- Main content: route page with max readable width where appropriate.

Responsive:
- Desktop: dashboard grids and three-column workspace.
- Tablet: two-column workspace, right stats collapse below.
- Mobile: single column, chapter list becomes a panel section.

Navigation model:
- `/home`: dashboard.
- `/library`: project library.
- `/workspace/:projectId`: project-bound writing workspace.
- `/new-project`: minimal preview/create flow.
- `/models`: read-only or list-only model entry in UI-R2.
- `/prompts`: read-only or list-only prompt entry in UI-R2.

## 14. Forbidden UI Anti-Patterns
- Do not make the UI look like a database admin form.
- Do not use fake project data when backend returns empty.
- Do not hide backend/API errors.
- Do not expose API keys in frontend state, logs, or UI.
- Do not use broad rainbow gradients or busy animation.
- Do not use emoji as functional icons.
- Do not put destructive actions next to primary actions without visual separation.
- Do not make card transparency so high that long text becomes unreadable.
- Do not implement a frontend-only business workflow that bypasses Python services.
