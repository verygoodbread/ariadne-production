# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A handoff bundle from Claude Design: a single, self-contained HTML/CSS/JS landing page
for **Ariadne** ("Lovable, but for physical products"), plus a browsable design-system
folder extracted from it.

`project/README.md` frames these as throwaway prototypes to be rebuilt in a real
framework. In practice the workflow has diverged: **`project/The Thread v4.html` is
treated as the canonical, living product** and is edited directly. New versions (v5,
v6, "v6 2", etc.) arrive from outside the repo (often `~/Downloads`); the task is
usually to fold their changes into `The Thread v4.html`, which stays the single source
of truth. Don't create new `v#` files — edit v4.

## No build system

There is no package manager, bundler, linter, or test suite. Everything is one
`<style>` and one `<script>` inside a single ~5,000-line HTML file. "Running" it means
serving the file statically and opening it.

Preview servers are defined in `.claude/launch.json` (start via the Claude Preview MCP,
not raw `python` in Bash):
- **`ariadne-static`** → serves `project/` on `:8770` (the product page)
- **`ariadne-root`** → serves the repo root on `:8771` (needed for `design-system/`, which sits outside `project/`)

The page is layout- and scroll-driven, so changes are verified by previewing in a
browser at a real viewport and measuring with `preview_eval` — screenshots alone miss
clipping and scroll behavior. (This contradicts `project/README.md`'s "don't render in
a browser" note; the note reflects the original bundle intent, not how this file is
actually being iterated.)

## Architecture of `project/The Thread v4.html`

**Two acts.** Act I "the film" — a near-black cinematic hero with a sticky stage, a
warm radial *bloom*, a *spark* core, and a letter-by-letter brand reveal. Act II "the
paper/product" — the editorial product section. The acts share type, motion, and
accent; they differ only in light.

**The palette/skin system.** Design tokens are CSS custom properties on `:root`, with
nine `body[data-palette="…"]` skins (aurora is the default and canonical: vellum,
slate, ember, dawn, twilight, verdigris, rose, ocean). Components must reference tokens
(`var(--accent)`), never raw hex, so a skin swap re-themes everything. There is exactly
one easing curve, `--ease: cubic-bezier(0.22, 1, 0.36, 1)`; differences come from
duration, not from swapping curves. Type: `--serif` (EB Garamond, the voice) and
`--sans` (Inter, product-UI chrome only).

**The ops stepper — the load-bearing interaction.** This is the part that needs
multiple files/sections read to understand:
- `.ops-scroll` is `8 * 100vh` tall; `.ops` is `position: sticky` inside it.
- `activeStepFromScroll()` in the `<script>` maps scroll progress to one of seven
  steps — `STEPS = ['design','validation','sourcing','manufacturing','quality','fulfillment','insights']` —
  via `floor(p * 7)` and sets `data-active` on `.ops`.
- CSS keyed off `.ops[data-active="…"]` reveals the matching `.ops-screen`. All seven
  screens are stacked `position: absolute; inset: 0; height: 100%`, so they share **one
  fixed frame** sized to the viewport.
- Each screen is a two-column grid: serif copy + a bespoke "viz" stage (globe, QC grid,
  manufacturing run, etc.).
- **Frame-fit invariant:** every viz stage uses `height: 100%; min-height: 0` so it
  conforms to the shared frame. Do **not** reintroduce fixed `min-height` on a stage —
  that makes content taller than the viewport-constrained frame and `overflow: hidden`
  clips the bottom. Vertical space for the stepper is deliberately reclaimed by keeping
  the title and inter-block margins small.
- A `@media (max-width: 820px)` block collapses the sticky scroll-jack into normal
  stacked flow for mobile; changes to the ops layout must be checked there too.

## `design-system/`

A browsable reference (open `design-system/index.html`), one page per concern: logo,
colours, typography, spacing, motion. `tokens.css` is the single source of truth and
every page imports it; `ds.css` styles the doc pages only and is not a product file.
**These tokens are a hand-extracted mirror of `The Thread v4.html`** — when a token
changes in the product, update `design-system/tokens.css` (and any affected swatch
page) to match. They do not auto-sync.

## Repo hygiene

- `ariadne-production-design-system/` at the repo root is external production-reference
  material — untracked and **not** part of the deliverable. Don't commit it.
- Commit with **explicit file paths**, never `git add .` / `-A`: the working tree
  contains the untracked reference folder above and `.DS_Store` files.
- Remote is the private `github.com/verygoodbread/ariadne-production`; pushing is not
  automatic — confirm before `git push`.
