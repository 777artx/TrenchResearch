# Visual direction (v0, 2026-11-17)

Arthur's brief: the site should feel close to Sparsity (dense, one-screen research cards, clean data tables, "what moved" panels) while using institutional, trusted colors, with no gold. We take Sparsity's *structure and density* as the reference, not its logo, colors, typefaces, copy or assets. A near-copy would invite a trade-dress complaint and would undercut the "better than Sparsity" positioning.

## Palette

The register is a sell-side research note or a financial newspaper: deep navy for authority, cool slate neutrals, white space, and muted signal colors used only where they carry meaning. Nothing saturated, no gradients, no gold, and no amber, since amber reads as gold.

| Role | Name | Hex | Use |
|---|---|---|---|
| Ink | Navy ink | `#0B1F3A` | Headlines, top bar, primary text on light backgrounds |
| Primary accent | Harbor blue | `#1F4E79` | Links, selected states, the single highlighted series in a chart |
| Secondary accent | Steel teal | `#2F6F73` | Second series, secondary buttons |
| Body text | Slate | `#334155` | Paragraphs and table text |
| Muted text | Slate 500 | `#64748B` | Captions, axis labels, timestamps |
| Rules | Slate 200 | `#E2E8F0` | Table rules, card borders |
| Page | Paper | `#F7F8FA` | Page background |
| Surface | White | `#FFFFFF` | Cards and tables |
| Positive | Ledger green | `#2E7D5B` | Gains, "Accumulation", positive flow |
| Negative | Oxblood | `#A23B3B` | Losses, "Avoid", negative flow |
| Caution | Terracotta | `#B5562A` | "Distribution risk", warnings (used sparingly) |

Green and red are never the only carrier of meaning: states also carry a label and an arrow or sign, so the site works for colour-blind readers. Chart palettes will be checked for contrast and colour-blind separation before use. A dark theme will mirror these roles on a navy-black (`#0A1422`) base.

## Typography

- **IBM Plex Sans** for interface and body text, and **IBM Plex Mono** for numbers in tables and tickers. Both are open-licensed. Plex has tabular figures, so columns of numbers align, and it reads as a financial terminal rather than a consumer app.
- **Source Serif 4** for page titles and the one-line state headline on each card, which gives a research-publication feel without being decorative.

## Layout principles (from SPEC §3.9 and §6.5)

- Every view answers its question above the fold: state, why, risk, levels, base rate, what would flip it.
- Cards over dashboards: one coin or one chain per card, a fixed order of rows, no decorative charts.
- Tables are the default way to show many items; charts are used only where shape matters.
- Every page footer carries "Research, not financial advice." and the data-source credits (including tehcscreener.com).
