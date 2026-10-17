# TRACE UI design

Station screens are read for long stretches, often on older monitors, by officers switching between English and Malayalam. The design is **black and white, with red reserved for warnings and errors**, and it works offline.

All tokens live in one place: the `:root` block at the top of `frontend/app/globals.css`. Components use the existing global classes (`.box`, `.note`, `.tag`, `button.primary`, …), so most new screens need no styling of their own.

## Colour tokens

| Token | Hex | Purpose |
|---|---|---|
| `--primary` | `#000000` | Top banner, headings, primary buttons, active tab and nav |
| `--primary-hover` | `#262626` | Primary button hover |
| `--on-primary` / `--on-primary-muted` | `#FFFFFF` / `#D4D4D4` | Text on the black banner |
| `--accent` | `#000000` | Links: black and always underlined |
| `--bg`, `--surface` | `#FFFFFF` | Page, cards, tables, inputs |
| `--soft` | `#F0F0F0` | Table headers, case header strip, hover |
| `--zebra` | `#F7F7F7` | Alternate table rows |
| `--border` | `#BDBDBD` | Light dividers |
| `--border-strong` | `#595959` | Outlines of cards, tables, inputs and secondary buttons |
| `--text` / `--text-2` | `#000000` / `#404040` | Primary / secondary text |
| `--hl` | `#E6E6E6` | Highlighted row or sentence |
| `--focus` | `#000000` | Keyboard focus outline (white inside the banner) |
| `--disabled-fg` / `--disabled-bg` | `#4D4D4D` / `#E3E3E3` | Disabled buttons and fields |

### Status: red means "warning"

| Token | Hex | Tint | Used for |
|---|---|---|---|
| `--warning`, `--danger` | `#B91C1C` | `#FDECEC` | Review status, "Recommend forensic review", sources disagree, unsupported sentences, chain broken, errors, destructive buttons, outside-recommendation warnings |
| `--success`, `--info` | `#000000` | `#F0F0F0` / `#F7F7F7` | Approved, sources agree, chain intact, neutral notes: black, distinguished by their label |

**Colour never carries meaning alone.** Every status in TRACE is written in words ("Approved", "Recommend forensic review", "✓ Sources agree", "✗ Sources disagree"). Red warnings are also marked by a thicker 2px tag border or a 6px note bar, so they still stand out when printed in black and white. When you add a status:

- put the meaning in the text (`<span className="tag warn">Awaiting SHO approval</span>`), never as an empty coloured mark;
- use `.warn` / `.bad` (red) only for things that need the officer's attention; use `.ok` (black, bold) for good states;
- never use red for decoration or emphasis; use bold or a heading for that.

## Typography

| Use | Font | Size | Token |
|---|---|---|---|
| Reading text: body, table cells, draft FIR, transcripts, headings | **Times New Roman** (primary) | 21px, line-height 1.6 | `--font-serif`, `--fs-body` |
| Interface: buttons, inputs, labels, table headers, tabs, tags, banner, `.small` notes | **Inter** (secondary) | 18px (`--fs-ui`), 17px for small text | `--font-sans`, `--fs-small` |
| Hashes, timestamps, file lines, source chips | System monospace | 17px | `--font-mono` |
| h1 / h2 / h3 / h4 | Times New Roman, bold | 38 / 31 / 26 / 23px | `--fs-h1` … `--fs-h4` |

Reading areas (the draft narrative and Malayalam blocks) are capped at `--measure` (75ch). The smallest visible text anywhere is 17px.

### Fonts and offline use

| Font | Source |
|---|---|
| Times New Roman | Installed with Windows, so nothing is bundled. Fallbacks: Times (macOS), Liberation Serif (Linux), then the system serif |
| Inter | Bundled: `frontend/app/fonts/inter-*.woff2` (SIL OFL) |
| Noto Sans Malayalam | Bundled: `frontend/app/fonts/noto-sans-malayalam-*.woff2` (SIL OFL). Neither Times New Roman nor Inter has Malayalam glyphs, so every Malayalam character falls through to this face, in serif and sans contexts alike. `.ml` blocks get line-height 1.85 for the stacked conjuncts |

The bundled fonts are declared with `@font-face` in `globals.css` and served from `/_next/static/media`, so the app makes **no external font requests** and works offline on station hardware. No npm dependency was added.

## Spacing, layout and targets

| Token | Value |
|---|---|
| `--sp-1` … `--sp-6` | 6, 10, 16, 20, 32, 44px |
| `--page-x` | 56px left and right page margin (32px below 1100px wide, 16px below 800px) |
| `--radius` | 4px |
| `--target` | 48px: minimum height of every button, link-button, input and select |

- **Banner:** the black top bar is at least 96px tall, with a 34px serif "TRACE" wordmark. It runs full width and its content uses the page margins.
- **Main content:** up to 1520px wide, with 44px top and 64px bottom padding. Cards have 32px padding and a 1px dark outline.
- **Buttons:** secondary by default (white, black text, dark outline); `.primary` is solid black; `.danger` is a red outline. `button.link` keeps inline text flow, because WCAG exempts inline links from target size.
- **Focus:** a 3px outline with a 2px offset on every focusable element.
- **Tables:** 16px vertical padding, row dividers and zebra striping, a grey header row. Tables with 8 or more columns (such as the manifest) use tighter horizontal padding so they fit 1280px screens without sideways scroll.
- **Side-by-side Malayalam/English** (`.grid2`): two equal columns with a divider between them, each under its own heading; they stack below 800px.
- No dark mode and no animations.

## Contrast (WCAG 2.1 AA)

Body text needs 4.5:1; large text and UI boundaries need 3:1.

| Foreground | Background | Ratio |
|---|---|---|
| Black | White / soft / zebra / highlight | 21.0 / 18.4 / 19.6 / 16.8 |
| Secondary `#404040` | White / soft / highlight | 10.4 / 9.1 / 8.3 |
| White / `#D4D4D4` | Black banner | 21.0 / 14.2 |
| Red `#B91C1C` | White / red tint / zebra / soft / highlight | 6.47 / 5.66 / 6.04 / 5.68 / 5.18 |
| Black | Red tint | 18.4 |
| Disabled `#4D4D4D` | `#E3E3E3` | 6.59 |
| Outline `#595959` | White / soft | 7.0 / 6.2 |

## Using the tokens in new components

- Prefer the existing classes: `.box` (card), `.note` with `.warnbar` / `.badbar` / `.okbar`, `.tag` with `.ok` / `.warn` / `.bad`, `.row`, `.grid2`, `.form`, `.muted`, `.small`, `.mono`, `.err`.
- When you need a new rule, use the variables (`var(--primary)`, `var(--sp-4)`, `var(--font-sans)`), never raw hex or pixel values.
- Reading text inherits Times New Roman. Controls and labels set `font-family: var(--font-sans)`.
- Inline `style` is for layout only (flex, margins, widths).
- Malayalam blocks get `className="ml"`.

Older variable names (`--fg`, `--muted`, `--line`, `--ok`, `--warn`, `--bad`) are kept as aliases for existing markup; new code should use the new names.
