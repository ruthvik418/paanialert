# Web Interface Guidelines

Source: https://vercel.com/design/guidelines (Vercel). Condensed from the page; check it for exact wording.

## Interactions
- Every flow is keyboard-operable and follows WAI-ARIA patterns.
- Visible, unobscured focus ring: `:focus-visible`, and `:focus-within` for grouped controls. Sticky UI must not cover focused elements.
- Manage focus: trap and move/return focus per WAI-ARIA patterns.
- Hit targets ≥24px (≥44px on mobile); visual and hit targets match.
- Mobile inputs use ≥16px font (or the viewport meta prevents auto-zoom). Never disable browser zoom.
- Inputs keep focus and value after hydration. Never block paste.
- Loading buttons show an indicator and keep the original label.
- Loading states: ~150–300 ms show delay and ~300–500 ms minimum visible time to avoid flicker.
- Persist state in the URL (filters, tabs, pagination, expanded panels) so share, refresh and Back/Forward work.
- Optimistic updates: update immediately, reconcile with the server, roll back or offer Undo on failure.
- Menu items that open a follow-up, and loading labels, end with "…".
- Destructive actions need confirmation or an Undo window.
- `touch-action: manipulation` on controls; set `-webkit-tap-highlight-color` to match the design.
- Forgiving interactions: generous targets, clear affordances, predictable behavior. No dead zones: if it looks interactive, it is.
- Tooltips: delay the first in a group; peers show without delay.
- `overscroll-behavior: contain` in modals/drawers. On fine pointers only, `overscroll-behavior: none` on `<html>`.
- Back/Forward restores scroll position.
- Autofocus a single primary input on desktop; rarely on mobile.
- Dragging: disable text selection and apply `inert` to dragged elements.
- Every gesture (drag, swipe, pinch) has a tap/click and keyboard alternative unless the gesture is essential.
- Navigation uses `<a>`/`<Link>`, never `<button>` or `<div>`.
- Announce async updates (toasts, inline validation) with polite `aria-live`.
- Shortcuts are locale-aware (non-QWERTY layouts, platform-specific symbols).

## Animation
- Honor `prefers-reduced-motion`.
- Prefer CSS, then the Web Animations API, then JS libraries.
- Animate only `transform` and `opacity`, never layout properties.
- Animate only to clarify cause and effect or for deliberate delight. Easing fits what changes.
- Animations are interruptible by user input. No autoplay except muted, non-essential loops; motion over 5 s needs pause/stop/hide.
- Correct `transform-origin` (where the motion physically starts).
- Never `transition: all`; list the properties.
- SVG: animate a `<g>` wrapper with `transform-box: fill-box; transform-origin: center`.

## Layout
- Optical alignment (±1px where perception differs from geometry); align everything to a grid, baseline, edge or optical center.
- Balance icon/text lockups (weight, size, spacing, color).
- Test mobile, laptop and ultra-wide (zoom to 50%).
- Respect safe areas with `env(safe-area-inset-*)`.
- No unnecessary scrollbars.
- Prefer flex/grid/intrinsic sizing over JS measurement.

## Content
- Inline help first; tooltips last.
- Skeletons match final content (no layout shift).
- `<title>` reflects the current context.
- No dead ends: every screen offers a next step or recovery.
- Design empty, sparse, dense and error states. Handle short, average and very long user content.
- Curly quotes; "…" not "..."; avoid widows/orphans.
- `tabular-nums` for numbers being compared.
- Never rely on color alone for status.
- Icons and icon-only buttons have accessible names (`aria-label`); decoration gets `aria-hidden`. Visible labels may be omitted, accessible names may not.
- Semantic HTML before ARIA. Hierarchical headings and a "Skip to content" link. `scroll-margin-top` on anchored headings.
- Media: captions, transcripts, descriptions of essential visuals, keyboard-operable controls.
- Locale-aware dates, numbers and currency. Detect language from `Accept-Language` / `navigator.languages`, never IP or GPS.
- `translate="no"` on brand names, code and identifiers.
- `&nbsp;` to keep units, shortcuts and names together.

## Forms
- Enter submits when a single text input is focused; in textareas ⌘/Ctrl+Enter submits and Enter adds a line.
- Every control has a label; clicking the label focuses the control; checkbox/radio and label share one hit target.
- Keep submit enabled until submission starts; then disable it, show a spinner, and send an idempotency key. Don't pre-disable submit.
- Don't block typing; accept input and show validation. Errors appear beside fields; focus the first error on submit.
- Meaningful `name` and `autocomplete`; correct `type` and `inputmode`; disable spellcheck for emails, codes, usernames.
- Placeholders show an example value or pattern and end with "…".
- Warn before leaving with unsaved changes.
- Work with password managers and 2FA (allow pasting one-time codes); keep non-auth fields from triggering password managers.
- Trim trailing whitespace from input values.
- Set explicit `background-color` and `color` on `<select>` (Windows).

## Performance
- Test iOS Low Power Mode and macOS Safari; profile with extensions disabled and with CPU/network throttling.
- Minimize re-renders; batch layout reads and writes.
- POST/PATCH/DELETE complete in <500 ms.
- Prefer uncontrolled inputs for keystroke cost.
- Virtualize large lists or use `content-visibility: auto`.
- Preload above-the-fold images, lazy-load the rest; explicit image dimensions (no CLS).
- `<link rel="preconnect">` for asset origins; preload critical fonts; subset fonts.
- Move long tasks to Web Workers.
- Looping `<video>` instead of GIF, with a still fallback and reduced-motion support.

## Design
- Layered shadows (≥2 layers); semi-transparent borders combined with shadows.
- Nested radii: child ≤ parent, concentric.
- Tint borders, shadows and text toward the background hue.
- Color-blind-friendly chart palettes. Prefer APCA for contrast.
- Hover/active/focus increase contrast over rest.
- `theme-color` meta matches the background; `color-scheme: dark` on `<html>` in dark themes.
- Avoid gradient banding (use background images rather than CSS masks for fades to dark).

## Copywriting
- Active voice, second person, action-oriented, as few words as possible.
- Consistent nouns: introduce as few unique terms as possible.
- Numerals for counts ("8 reports"); a space between number and unit ("10 MB", non-breaking).
- Consistent currency decimals within a context.
- Positive framing for errors, and every error says how to fix it.
- Specific labels: "Save Alert", not "Continue".
- Vercel house style (optional here): Title Case for headings/buttons, "&" over "and".
