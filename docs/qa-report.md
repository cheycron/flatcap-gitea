# QA report: Flatcap 2.0 for Gitea, before and after

Target: Gitea 28.2.0 (`gitea/gitea:28.2.0`, rootful, SQLite), throwaway container on `127.0.0.1`, removed afterwards. Browser: Google Chrome for Testing 149.0.7827.55 through `playwright-core`, 1440×900, `en-US`. Themes installed as in the README: three files in `/data/gitea/public/assets/css/` and `[ui] THEMES = gitea-auto,gitea-light,gitea-dark,flatcap-auto,flatcap-slate,flatcap-daylight`. The live Gitea of the author was only read (`gitea --version`), never changed. The scripts used are in `qa/`: `seed.py` (demo data: users `ada`, `grace`, `linus`, organization `aurora`, repository `aurora/ledger` with commits, a Python diff, README with headings, table, task list and code, labeled open and closed issues, an open PR with two inline review comments and a merged PR), `shot.mjs` (screenshots) and `scan.mjs` (computed-color scan). They are not run by CI.

## Static checks (literal results)

```
$ python3 scripts/build.py --check
ok: 6 generated files current, every variable is in the Gitea 28.2.0 inventory, contrast targets met

$ python3 scripts/inventory.py --check /tmp/fc-gitea/dir
ok: inventory matches /tmp/fc-gitea/dir

$ docker exec fc-gitea-demo gitea --version
gitea version 28.2.0 built with go1.27.2 : bindata, timetzdata,
```

`/tmp/fc-gitea/dir` is the built frontend (`index.*.css`, `theme-gitea-auto.*.css`, `index.*.js` and 73 lazy chunks) fetched from that container with `scripts/inventory.py --fetch`.

Inventory: 294 theme variables (the same 294 in the built-in light and dark themes, including `accent-color` and `color-scheme`); 222 are read by `index.css`, 5 only by JavaScript (activity heatmap, charts, `colord`), 65 have no reader in the 28.2.0 bundle and are set anyway. Every one is set in both modes. 4 more variables outside the themes (two fonts, two radii) are overridden. 39 further custom properties of `index.css` (spacing, z-index, font weights, icons) are not touched.

The themes were compared with the built-in ones: names and values of the built-in `:root` blocks match the version tag source (`v28.2.0`) 294 for 294.

## Contrast

435 report lines (see [mapping.md](mapping.md#contrast)); the build fails on any miss. Lowest measured value per group, across both modes:

| Group | Target | Lowest |
| :--- | ---: | :--- |
| Text on surfaces | 7:1 (5:1 for selection, highlight, alpha overlays) | 5.64:1 text on editor selection (Slate) |
| Secondary and muted text | 5:1 | 5.21:1 `text-light-2` on hover (Daylight) |
| Links and accent | 5:1 | 5.79:1 `primary-active` on box header (Slate) |
| Primary fills | 4.5:1 | 4.59:1 `primary-contrast` on `primary-light-5` (Daylight) |
| Colored fills (`--color-white` on red, orange, yellow, green, purple and hover steps) | 4.5:1 | 5.96:1 on purple (Daylight); 8.36:1 on red (Slate) |
| Feedback | 5:1 (4.5:1 hover and pressed) | 4.59:1 error text on pressed (Daylight) |
| Diff | 7:1 text, 5:1 gutters | 5.09:1 removed foreground on its row (Daylight) |
| Diff code tokens on row and word backgrounds | 4.5:1 | 4.57:1 `syntax-number` on added word (Daylight) |
| Syntax on code background | 5:1 | 5.66:1 `syntax-number` on code (Daylight) |
| Console and Actions log | 5:1 | 5.41:1 `ansi-black` on console (Slate) |
| Functional outlines, focus ring | 3:1 | 4.02:1 button border on body (Daylight) |
| Chart series | 3:1 | 4.44:1 series 14 on box body (Slate) |

These are token-level numbers. Two measures were adjusted during the work after the build reported misses: the text of `primary-light-4/-5` (the scale now stops at 4.6:1 with `accent.on`) and the diff word highlight (now the strongest step that keeps tokens at 4.5:1).

## Browser checks

| Check | Result |
| :--- | :--- |
| *Settings → Appearance* lists the themes | `Flatcap Slate = flatcap-slate`, `Flatcap (auto) = flatcap-auto`, `Flatcap Daylight = flatcap-daylight`, next to Auto, Dark and Light. |
| Each theme loads | With `flatcap-slate`, `flatcap-daylight` and `flatcap-auto` selected: computed `--color-body` is `#191d22` (dark), `#f3f5f7` (light); with the Gitea themes `#1e1f20` and `#ffffff`. |
| `Flatcap (auto)` follows the system | Emulated `prefers-color-scheme: light` → `--color-body #f3f5f7`, `color-scheme: light`, `--is-dark-theme: false`; `dark` → `#191d22`, `dark`, `true`. Only emulation was run; no real OS switch. |
| Focus ring | Visible outside the focused "Create Issue" button in Slate (screenshot inspected). Not inspected on every control. |
| Screenshots viewed | Repository home, PR Files changed, issue list, PR conversation, code view (Slate and Daylight, as applicable), new issue with editor (Slate). The other scanned pages were not opened by eye. |

## Scan: computed colors, before and after

For 14 pages (repository, PR files, issue list, PR, issue, settings, profile, new issue, code file, commits, branches, explore, merged PR, labels) the scan reads the computed `color`, `background-color`, the four `border-*-color` (when drawn), `outline-color` (when drawn), `fill` and `stroke` of every visible element under `body`, and counts them. `fill: rgb(0,0,0)`, the inherited default of non-SVG elements, is dropped. A color is `flatcap` if it equals a hex value in the generated theme file, `gitea` if it equals a default value of a Gitea built-in theme (any hex in the inventory), otherwise `other`. This is a heuristic on RGB values: a match does not prove where a color came from, and alpha is ignored.

| | Gitea theme (before) | Flatcap (after) |
| :--- | ---: | ---: |
| Dark: `flatcap` | 0 | 10 214 |
| Dark: `gitea` default | 10 270 | 56 |
| Dark: `other` | 38 | 38 |
| Light: `flatcap` | 0 | 10 237 |
| Light: `gitea` default | 10 260 | 32 |
| Light: `other` | 38 | 38 |

"Before" is `gitea-dark` / `gitea-light` on the same pages and data.

### Remaining matches with Gitea defaults (after)

| Where | Color | Count (Slate) | Why it remains |
| :--- | :--- | ---: | :--- |
| Native checkbox, radio and text `input` `color` | `#ffffff` (Slate), `#000000` (Daylight) | 56 / 32 | The user-agent default of `color` for form controls under `color-scheme`, not a Gitea variable. |

### Remaining `other` colors

| Where | Why it remains |
| :--- | :--- |
| `span.ui.label` fills (the seeded label colors `#d73a4a`, `#d9a441`, `#4a8fd7`, `#7b6fc9`, `#4aa86b`, `#8a939e`) | Chosen by repository owners per label; Gitea sets the text color by luminance. |
| `div.bar`, `i.color-icon` (`#3572a5`) | Language bar and dot: GitHub-linguist language colors (left as asked). |
| `path` fills (`#ff5722`, `#42a5f5`, `#0288d1`, `#fdd835`) | File-type icons of the Material icon set (Python and other file icons). |
| Gray `#aaaaaa` (Slate) / `#545454` (Daylight) on 5 `input` elements of one page | Not traced; it matches no Flatcap or Gitea value and looks like a native control default. |

Not covered by the scan: shadow-DOM content, canvases (activity heatmap, charts), images and avatars, pseudo-elements, and states that need interaction (hover, open dropdowns, modals).

## Not validated

- Actions log, runners, Mermaid, CodeMirror editor view, projects, packages, wiki, admin pages: not opened.
- Activity heatmap and chart canvases: variables set and the sequential order checked in luminance, not inspected as pixels.
- Firefox, Safari, mobile sizes, forced-colors, `prefers-contrast`, print.
- Real users and assistive technology; other Gitea versions.
