# Ariadne — Design System

The reusable parts of the landing page, pulled out of `project/The Thread v4.html`
into one room per topic instead of a single long document.

## How to browse

Open **`index.html`** in a browser. Every page is visual — colours render as
swatches, type renders at real size, motion actually animates.

```
design-system/
├── index.html        ← start here (overview + links)
├── tokens.css        ← single source of truth (all CSS custom properties)
├── ds.css            ← styling for these doc pages only (not a product file)
├── logo.html         ← the labyrinth mark, wordmark, lockup, clear-space, don'ts
├── colours.html      ← core palette, surface set, 9 scroll-driven palettes
├── typography.html   ← the two typefaces + the fluid type scale
├── spacing.html      ← clamp() rhythm, content widths, corner radii
├── motion.html       ← the one easing curve + duration bands
└── interaction.html  ← scroll-driven stepper, puzzle nav, viz entrances, film reveal
```

## The one rule

`tokens.css` is canonical. Components reference tokens
(`color: var(--accent)`), never raw hex. Change a value once and the
swatches, the samples, and the product all move together.

> `tokens.css` was extracted from the product. If a token changes in
> `project/The Thread v4.html`, update it here too so the two stay in sync.
