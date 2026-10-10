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
  ink-muted: "#6b7280"
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

Dark mode reassigns every token (canvas #16171a, surface #1e1f23, surface-alt #232428, hairline #302f34, ink #eceef1, bubble #2a2b30) under `prefers-color-scheme`.

### Named Rules
**The One Voice Rule.** Messenger Blue is the only chromatic color. A new hue needs a semantic job (state, status), never decoration.

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

A centered shell, max 1100px, with a fixed 280px sidebar and a flexible chat column filling the viewport height. The sidebar holds connection status, a connect form, and a schema tree; the chat column stacks header, scrolling messages, and a pinned input row. Spacing follows a 4/8/12/16/20px rhythm; messages are separated by 10px gaps and assistant bubbles cap at 85% width. Below 700px the shell stacks vertically, with the sidebar capped at 40vh above the chat.

## Elevation & Depth

Flat and tonal. Layers are distinguished by surface shade and 1px hairline borders. The only shadow is a soft two-layer ambient shadow on message bubbles (`0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.05)`; heavier in dark mode); the user bubble gets a blue-tinted version. The chat input gains a 3px blue glow ring (15% alpha) on focus.

### Named Rules
**The Flat Chrome Rule.** Header, sidebar, panels and inputs never cast shadows. Only content (message bubbles) lifts.

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

### Inputs / Fields
- **Chat input:** pill, Surface Alt fill, hairline border; focus turns the border blue and adds the glow ring.
- **Sidebar fields:** 6px radius, Surface fill, hairline border; focus only changes border to blue.

### Details Panel (signature)
A Surface Alt card with 10px radius under an assistant bubble, holding uppercase section labels, a timing list with a bold total row, monospace SQL blocks, few-shot examples, and a collapsible prompt. It is how the Glass Box shows its work.

### Result Table
Bordered 10px-radius scroll wrapper, uppercase muted header on Surface Alt, hairline row dividers, even rows zebra-tinted, nowrap cells.

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
- **Don't** introduce a second accent hue or gradients.
- **Don't** show raw SQL or timing data in the primary answer flow.
- **Don't** set body or answer text below 0.9em; reserve small sizes for detail.
- **Don't** hardcode hex values in component rules.
