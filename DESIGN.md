---
name: Chat With Database
description: A familiar chat surface that keeps the machinery inspectable, in soft neutrals with a single blue voice.
colors:
  messenger-blue: "#0a84ff"
  messenger-blue-dark: "#3b9cff"
  accent-text: "#0066d6"
  accent-fill-dark: "#0a6fe0"
  on-accent: "#ffffff"
  canvas: "#f5f5f7"
  surface: "#ffffff"
  surface-alt: "#f7f8fa"
  hairline: "#e3e4e8"
  ink: "#1c1e21"
  ink-muted: "#5d6573"
  bubble-assistant: "#f0f1f4"
  error-bg: "#fdecec"
  error-ink: "#b3261e"
  status-ok: "#2ecc71"
  status-warn: "#e67e22"
  disabled: "#d0d2d8"
typography:
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"
    fontSize: "1.05em"
    fontWeight: 600
    letterSpacing: "-0.01em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"
    fontSize: "0.96em"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"
    fontSize: "0.75em"
    fontWeight: 700
    letterSpacing: "0.04em"
  code:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace"
    fontSize: "0.92em"
rounded:
  sm: "4px"
  md: "6px"
  lg: "10px"
  bubble: "16px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
components:
  button-primary:
    backgroundColor: "{colors.accent-text}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.pill}"
    padding: "10px 20px"
  button-primary-disabled:
    backgroundColor: "{colors.disabled}"
    textColor: "{colors.ink-muted}"
  input-chat:
    backgroundColor: "{colors.surface-alt}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "12px 16px"
  bubble-user:
    backgroundColor: "{colors.accent-text}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.bubble}"
    padding: "10px 14px"
  bubble-assistant:
    backgroundColor: "{colors.bubble-assistant}"
    textColor: "{colors.ink}"
    rounded: "{rounded.bubble}"
    padding: "10px 14px"
  bubble-error:
    backgroundColor: "{colors.error-bg}"
    textColor: "{colors.error-ink}"
  details-panel:
    backgroundColor: "{colors.surface-alt}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "10px 12px"
  sidebar-input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "8px 10px"
---

# Design System: Chat With Database

## Overview

**Creative North Star: "The Glass Box"**

The product answers in the voice of an ordinary messaging app, then lets the reader lift the lid. Everything the system did to reach an answer (the SQL, the result table, step timings, cache hits, retries) is present, but folded behind a quiet "details" control so a non-technical analyst reads the plain sentence first. Transparency is available, never imposed.

The surface is soft and familiar: system font, rounded bubbles, hairline borders, tonal greys, and one blue voice. It is flat at rest; only message bubbles carry a faint shadow. It follows the OS light or dark preference with no manual toggle.

**Key Characteristics:**
- Chat-bubble lineage: user right in blue, assistant left in tonal grey.
- One accent, used for identity and action only.
- Depth by tonal surface and hairline border, not by shadow.
- Detail on demand: inspection UI is smaller, muted, and collapsible.
- Light and dark are equal citizens via CSS custom properties.

## Colors

A restrained neutral palette with a single saturated blue; everything else is grey or a semantic state.

### Primary
- **Messenger Blue** (#0a84ff, #3b9cff in dark): the brand hue, used for focus rings, borders and tints. The only chromatic voice in the interface.
- **Accessible Blue** (#0066d6 light; fills #0a6fe0 and text #3b9cff in dark): the same hue deepened to pass AA with white text. Used for user bubbles, the send button, links, toggles and badges.

### Neutral
- **Canvas** (#f5f5f7): page background outside the 1100px shell.
- **Surface** (#ffffff): chat area, header, inputs inside the sidebar.
- **Surface Alt** (#f7f8fa): sidebar, chat input field, details panel, table header, zebra rows.
- **Hairline** (#e3e4e8): all dividers and borders.
- **Ink** (#1c1e21) and **Ink Muted** (#6b7280): primary and secondary text, timestamps, labels.
- **Assistant Bubble** (#f0f1f4): assistant message fill.
- **Disabled** (#d0d2d8): disabled buttons and scrollbar thumbs.

### Semantic
- **Error** (#fdecec fill, #b3261e text): failed responses and connection errors.
- **Status Green** (#2ecc71) and **Status Amber** (#e67e22): connection dot only.

Every token holds both its light and dark value through `light-dark()` in a single `:root` block, so there is one source of truth. Dark values: canvas #16171a, surface #1e1f23, surface-alt #232428, hairline #302f34, ink #eceef1, muted #9799a1, bubble #2a2b30. The scheme follows the OS by default; a theme toggle (System, Light, Dark) in the rail footer and on the sign-in screen pins it through `data-theme` on the root element, saved in `localStorage` and applied before first paint so there is no flash.

- **Field Border** (#858b97 light, #6f727c dark): the boundary of text inputs, the composer and the schema filter, at least 3:1 against what is behind them. Decorative dividers keep the lighter hairline.

### Named Rules
**The One Voice Rule.** Messenger Blue is the only chromatic color for identity and action. Any other hue must carry meaning; the only others are the five stage colors below and the semantic error and status colors.

**The Stage Color Rule.** Color follows the pipeline. Reading your question is Indigo (#5b5fe0 / #8b8ff5 in dark), writing the query is Violet (#9b5de5 / #b98af0), running it on your data is Teal (#0b8f8e / #3ad1cf), writing the answer is Green (#1b8a5a / #4cd09a), and a failure is Coral (#e5484d / #ff8a8e). They appear only while work is happening and in brief accents afterward, as dots, lines, rings and a faint idle wash. They never color body text, and the stage name is always shown as words too. The light-mode Teal and Green are deepened from the originally proposed #0ea5a4 and #22a06b so they hold 3:1 against the assistant bubble.

**The Both Modes Rule.** A new color is added as one `light-dark()` token with both values checked for contrast. Never style a mode separately in a component rule.

**The Token Only Rule.** Components read colors from the `--bg/--surface/--text/--accent` custom properties so dark mode comes free; raw hex belongs only in the token block and the status dot.

## Typography

**Font:** the platform system stack (-apple-system, Segoe UI, system-ui) for everything; ui-monospace for SQL and code.

**Character:** native and unbranded; hierarchy comes from weight, size in `em`, and case, not from a typeface.

### Hierarchy
- **Title** (600, 1.05em, -0.01em): chat header.
- **Body** (400, 0.96em, 1.45): message bubbles.
- **Detail** (0.82em to 0.88em): details panel and tables.
- **Label** (700, 0.75em, uppercase, 0.04em tracking, muted): sidebar and details headings, table headers.
- **Code** (monospace, 0.92em): SQL blocks and inline code in the details panel.

### Named Rules
**The Quiet Detail Rule.** Technical content (SQL, timings, prompts) is set smaller and muted compared to the answer. Size encodes audience: the answer is for everyone, the detail is for whoever opens it.

## Layout

A full-width shell: a 280px conversation rail on the left and a flexible chat column filling the viewport height. The rail holds New chat, past chats grouped by day, and the account row. The chat column stacks a top bar (title and database pill), scrolling messages, and a pinned composer. Message content is centered in an 820px column so lines stay readable on wide screens. The connected database and its schema live in a slide-over drawer opened from the database pill. Spacing follows a 4/8/12/16/20px rhythm; messages are separated by 10px gaps and assistant bubbles cap at 85% width. At 900px and below the rail becomes a slide-in drawer opened from a menu button; while a drawer is open the rest of the page is inert and Esc closes it, returning focus to its trigger. On coarse pointers, interactive controls grow to 44px.

## Elevation & Depth

Flat and tonal. Layers are distinguished by surface shade and 1px hairline borders. The only shadow is a soft two-layer ambient shadow on message bubbles (`0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.05)`; heavier in dark mode); the user bubble gets a blue-tinted version. The composer gains a 3px blue glow ring (15% alpha) on focus. Drawers sit above a 40% black scrim and carry no shadow.

### Named Rules
**The Flat Chrome Rule.** Header, sidebar, panels and inputs never cast shadows. Only content (message bubbles) lifts.

### Motion

One authored moment per question: a thin line along the pending bubble carries the current stage color and cross-fades between stages (0.5s), each finished stage keeps its own colored dot, and the stop button wears a ring in the stage color. When the answer lands it settles in with a short green sweep and its table rows follow in a capped stagger; bar charts grow from zero. The empty chat has a slow, low-contrast drift of the stage colors behind the starters; a failed answer shakes once. Everything uses transform and opacity with an exponential ease-out (cubic-bezier(0.16, 1, 0.3, 1)). With reduced motion the stage color, arrival fade and failure feedback stay, and all movement, shimmer and drift are removed.

## Shapes

Friendly and rounded, with a clear radius hierarchy: pills (999px) for the chat input, send button, chips and badges; 16px for bubbles, with the sender-side bottom corner squared to 4px as the tail; 10px for the details panel and table wrapper; 6px for sidebar fields and buttons; 4px for small badges and inline code. Borders are always 1px hairline.

## Components

### Buttons
- **Primary (send):** Messenger Blue pill, white 600 text, 10px 20px. Hover drops opacity to 0.9; active scales to 0.97; disabled turns grey with muted text.
- **Sidebar action:** 6px-radius blue block, 0.85em, same disabled treatment.
- **Link button:** no background, blue 600 text (Details toggle, "connect database").

### Chat Bubbles
- **User:** blue fill, white text, bottom-right corner 4px, blue-tinted shadow.
- **Assistant:** tonal grey fill, bottom-left corner 4px, sits above a meta row (latency, cache badge, Details toggle).
- **Error:** soft red fill with red text.
- **Pending:** three bouncing muted dots.
- Messages enter with a 0.18s fade and 4px rise.

### Conversation Rail
A Surface Alt column. New chat is a bordered 10px-radius button; past chats are text rows grouped under small uppercase labels (Today, Yesterday, Previous 7 days, Earlier). The active row is white with a hairline inset border. Rename and delete icons appear on hover or focus (always on touch). Delete confirms inline ("Delete this chat? Delete / Keep") and focus returns to the row afterwards.

### Composer
A 22px-radius Surface Alt box with an auto-growing textarea (up to about six lines) and a round send button in Accessible Blue. While a request runs the send button becomes a stop button (ink on surface). Enter sends, Shift+Enter adds a line. A one-line hint sits below; editing the last question shows an "Editing your last question" strip above.

### Progress
While waiting, the assistant bubble lists only the pipeline stages reached so far (Reading your question, Writing the query, Running it on your data, Writing the answer): finished ones muted with a filled dot, the current one with a pulsing blue dot.

### Starter and Follow-up Chips
Pill buttons with a hairline border and white fill; hover turns the border blue. Starters (on the empty chat) are written from the connected schema; follow-ups sit below the latest answer.

### Inputs / Fields
- **Sidebar fields:** see below.
- **Sidebar fields:** 6px radius, Surface fill, hairline border; focus only changes border to blue.

### Details Panel (signature)
A Surface Alt card with 10px radius under an assistant bubble, holding uppercase section labels, a timing list with a bold total row, monospace SQL blocks, few-shot examples, and a collapsible prompt. It is how the Glass Box shows its work.

### Result Table
Bordered 10px-radius scroll region (focusable, max 360px tall) with a sticky uppercase muted header on Surface Alt, sortable columns (header buttons with an arrow icon), right-aligned tabular numbers, hairline row dividers, zebra rows, nowrap cells and a dash for empty values. Beyond 10 rows it collapses behind "Show all N rows". Beneath it, pill tool buttons offer Chart (only for a label plus a number, 2 to 30 rows), Copy and CSV. The chart is horizontal bars in the brand blue on a hairline track.

### Message Actions
A muted row under each assistant bubble: latency, cached badge, Copy answer, and for the latest answer Regenerate and Edit question (drawn icons plus text), then the Details toggle.

### Schema Tree
Filter field plus expandable table rows (rotating caret), muted column counts, and small PK (blue tint) and FK (grey tint) badges.

### Status Pill and Badges
Cache-hit badge: blue outline pill. Chat notice: muted Surface Alt pill centered in the message stream.

## Do's and Don'ts

### Do:
- **Do** lead every response with the plain-language answer; keep SQL and timings behind the Details toggle.
- **Do** use Messenger Blue only for identity and action.
- **Do** reference colors through the CSS custom properties so both color schemes work.
- **Do** keep the 16px bubble with a 4px sender-side tail.
- **Do** keep focus visible: blue border plus ring on the chat input.

### Don't:
- **Don't** add shadows to chrome (header, sidebar, panels).
- **Don't** add hues beyond the five stage colors, or use them for decoration or body text.
- **Don't** loop motion once an answer has arrived; only the pending state and the idle wash may repeat.
- **Don't** show raw SQL or timing data in the primary answer flow.
- **Don't** set body or answer text below 0.9em; reserve small sizes for detail.
- **Don't** hardcode hex values in component rules.
