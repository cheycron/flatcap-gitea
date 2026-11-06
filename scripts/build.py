#!/usr/bin/env python3
"""Generate the Flatcap 2.0 themes for Gitea.

    python3 scripts/build.py             # write themes/*.css and the generated doc blocks
    python3 scripts/build.py --check     # validate and fail if any generated output is stale
    python3 scripts/build.py --sync      # refresh src/theme.json from ../00-Flatcap, then rebuild
    python3 scripts/build.py --contrast  # print the contrast report for the effective Gitea variable pairs

Input  : src/theme.json            versioned copy of the Flatcap 2.0 core (the only source of color values)
         src/gitea-inventory.json  every theme variable Gitea 28.2.0 declares (scripts/inventory.py)
Outputs: themes/theme-flatcap-slate.css, theme-flatcap-daylight.css, theme-flatcap-auto.css
         README.md, docs/mapping.md, docs/inventory.md   only the blocks between <!-- build:NAME --> markers

No color is written by hand here: every entry is a template over Flatcap roles ({role}), a mix of roles or a
scale derived from them, resolved from src/theme.json. A custom Gitea theme replaces the built-in one, so every
inventoried variable is set. Python 3.10+, standard library only. Output is deterministic.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import color as C  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
THEME = ROOT / "src" / "theme.json"
INV_FILE = ROOT / "src" / "gitea-inventory.json"
UPSTREAM = (ROOT / ".." / "00-Flatcap" / "src" / "theme.json").resolve()
THEMES_DIR = ROOT / "themes"
README = ROOT / "README.md"
MAPPING_DOC = ROOT / "docs" / "mapping.md"
INV_DOC = ROOT / "docs" / "inventory.md"
GITEA_VERSION = "28.2.0"

# Flatcap mode -> (file name, Gitea display name, color scheme, is dark)
MODES = {"slate": ("flatcap-slate", "Flatcap Slate", "dark", True),
         "daylight": ("flatcap-daylight", "Flatcap Daylight", "light", False)}
AUTO = ("flatcap-auto", "Flatcap (auto)")

SYNTAX_TEXT = ["keyword", "function", "string", "number", "type", "comment"]
PCT = (10, 20, 30, 40, 50, 60, 70, 80, 90)


# ---------------------------------------------------------------------------
# Per-mode context: roles plus the scales derived from them
# ---------------------------------------------------------------------------
class Ctx:
    def __init__(self, theme: dict, mode: str):
        self.mode = mode
        self.dark = MODES[mode][3]
        self.t = {k: C.parse(v) for k, v in theme["themes"][mode].items()}
        self.typo = theme["typography"]
        self.metrics = theme["metrics"]
        self.shadow = theme["elevation"][mode]["shadow.overlay"]
        self.x: dict[str, C.RGBA] = {}
        self._derive()

    # -- lookup ------------------------------------------------------------
    def rgba(self, key: str) -> C.RGBA:
        if key.startswith("@"):
            return self.x[key]
        return self.t[key]

    def mix(self, a: str, b: str, t: float) -> C.RGBA:
        return C.mix(self.rgba(a), self.rgba(b), t)

    def add(self, key: str, value: C.RGBA) -> None:
        self.x[key] = value

    # -- derived scales ------------------------------------------------------
    def _bisect(self, make, ok, lo: float, hi: float) -> float:
        """Largest t in [lo, hi] for which ok(make(t)) holds (ok must be monotone: true at lo, false at hi)."""
        if ok(make(hi)):
            return hi
        if not ok(make(lo)):
            return lo
        for _ in range(40):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if ok(make(mid)) else (lo, mid)
        return lo

    def _derive(self) -> None:
        t = self.t
        fg_end, bg_end = "contrast.text.primary", ("bg.canvas" if self.dark else "bg.raised")
        self.add("@fg_end", t[fg_end])
        self.add("@bg_end", t[bg_end])
        # primary scale: dark-N moves toward the strongest text, light-N toward the page background.
        # The text on light-4/-5 (review counter) is accent.on, so t5 is the largest tint that keeps 4.6:1 with it.
        on = t["accent.on"]
        t5 = self._bisect(lambda s: C.mix(t["accent.fill"], t[bg_end], s),
                          lambda c: C.contrast(on, c) >= 4.6, 0.05, 0.9)
        t4 = t5 * 0.8
        steps = [t4 * .25, t4 * .5, t4 * .75, t4, t5, 0.9, 0.96]
        for n, s in enumerate(steps, 1):
            self.add(f"@p.light.{n}", C.mix(t["accent.fill"], t[bg_end], s))
        for n, s in enumerate([.12, .24, .36, .48, .66, .84, .96], 1):
            self.add(f"@p.dark.{n}", C.mix(t["accent.fill"], t[fg_end], s))
        # secondary scale: anchors along subtle border -> control border -> muted -> secondary -> primary text.
        anchors = [(0, "border.subtle"), (3, "border.control"), (5, "text.muted"), (8, "text.secondary"),
                   (11, "text.primary"), (13, "contrast.text.primary")]
        for n in range(1, 14):
            for (i0, k0), (i1, k1) in zip(anchors, anchors[1:]):
                if i0 <= n <= i1:
                    self.add(f"@s.dark.{n}", C.mix(t[k0], t[k1], (n - i0) / (i1 - i0)))
                    break
        for n, s in enumerate([.25, .5, .75, 1.0], 1):
            self.add(f"@s.light.{n}", C.mix(t["border.subtle"], t["bg.surface"], s))
        # named colors
        base = {
            "red": t["danger.fg"], "yellow": t["warning.fg"], "green": t["success.fg"], "blue": t["info.fg"],
            "teal": t["data.5"], "violet": t["data.3"], "brown": t["data.4"],
            "orange": C.mix(t["danger.fg"], t["warning.fg"], .5),
            "olive": C.mix(t["warning.fg"], t["success.fg"], .5),
            "purple": C.mix(t["data.3"], t["danger.fg"], .35),
            "pink": C.mix(t["data.3"], t["danger.fg"], .7),
            "black": t["bg.raised"] if self.dark else t["text.primary"],
        }
        for name, col in base.items():
            self.add(f"@{name}", col)
            if self.dark:
                self.add(f"@{name}.light", C.mix(col, t[fg_end], .25))
                self.add(f"@{name}.dark.1", C.mix(col, t[fg_end], .10))
                self.add(f"@{name}.dark.2", C.mix(col, t[fg_end], .20))
            else:
                self.add(f"@{name}.light", C.mix(col, t["bg.raised"], .25))
                self.add(f"@{name}.dark.1", C.mix(col, t[fg_end], .15))
                self.add(f"@{name}.dark.2", C.mix(col, t[fg_end], .30))
        # 16-colour series: the six data colors, then lighter and deeper variants of them
        for i in range(16):
            col = t[f"data.{i % 6 + 1}"]
            if i >= 12:
                col = C.mix(col, t["bg.canvas"] if self.dark else t[fg_end], .25 if self.dark else .30)
            elif i >= 6:
                col = C.mix(col, t[fg_end], .30)
            self.add(f"@series.{i}", col)
        # ansi: bright variants move toward the strongest text (readable on the console background)
        for n, k in (("red", "danger.fg"), ("green", "success.fg"), ("yellow", "warning.fg"), ("blue", "accent.fg"),
                     ("magenta", "data.3"), ("cyan", "data.5")):
            self.add(f"@ansi.{n}", t[k])
            self.add(f"@ansi.bright.{n}", C.mix(t[k], t[fg_end], .22))
        # diff: row = feedback background; gutter and border step toward the feedback foreground;
        # the word highlight is the strongest step that still keeps every code token at 4.6:1
        tokens = [t[f"syntax.{k}"] for k in SYNTAX_TEXT] + [t["text.primary"], t["text.secondary"]]
        for kind, fb in (("add", "success"), ("del", "danger")):
            row, fg = t[f"{fb}.bg"], t[f"{fb}.fg"]
            self.add(f"@diff.{kind}.line", C.mix(row, fg, .04) if self.dark else C.mix(row, t["bg.raised"], .5))
            self.add(f"@diff.{kind}.border", C.mix(row, fg, .18))
            w = self._bisect(lambda s: C.mix(row, fg, s),
                             lambda bg: min(C.contrast(tk, bg) for tk in tokens) >= 4.56 and C.contrast(t["text.primary"], bg) >= 7.05, 0.02, 0.45)
            self.add(f"@diff.{kind}.word", C.mix(row, fg, w))
        self.add("@diff.move.border", C.mix(t["info.bg"], t["info.fg"], .35))
        for kind, fb in (("error", "danger"), ("success", "success"), ("warning", "warning"), ("info", "info")):
            self.add(f"@{kind}.border", C.mix(t[f"{fb}.bg"], t[f"{fb}.fg"], .35))
            self.add(f"@{kind}.active", C.mix(t[f"{fb}.bg"], t[f"{fb}.fg"], .08))
            self.add(f"@{kind}.hover", C.mix(t[f"{fb}.bg"], t[f"{fb}.fg"], .04))
        self.add("@priority.bg", C.mix(t["bg.surface"], t["data.3"], .08))
        self.add("@priority.border", C.mix(t["bg.surface"], t["data.3"], .40))
        self.add("@reaction.active", C.mix(t["bg.selected"], t["accent.fill"], .05))
        self.add("@zebra", C.mix(t["bg.surface"], t["bg.raised"], .5))
        m = re.search(r"rgb\((\d+) (\d+) (\d+) / (\d+)%\)", self.shadow)
        if not m:
            raise SystemExit(f"error: cannot parse shadow.overlay for {self.mode}: {self.shadow!r}")
        r, g, b, a = (int(m.group(i)) for i in (1, 2, 3, 4))
        self.add("@shadow", (r / 255, g / 255, b / 255, a / 100))
        self.add("@scrim", t["bg.canvas"][:3] + (0.75,))

    # -- value resolution -----------------------------------------------------
    def value(self, spec) -> str:
        """Resolve a template to the CSS text. {role}, {role}/N (alpha %), {typography}, {metric}, mix(...)."""
        if callable(spec):
            return spec(self)
        m = re.fullmatch(r"mix\(\{([^}]+)\},\s*\{([^}]+)\},\s*([\d.]+)\)", spec)
        if m:
            return self.hex(C.mix(self.rgba(m.group(1)), self.rgba(m.group(2)), float(m.group(3))))

        def sub(mm: re.Match) -> str:
            key, pct = mm.group(1), mm.group(2)
            if key in self.t or key.startswith("@"):
                col = self.rgba(key)
                if pct:
                    col = (col[0], col[1], col[2], int(pct) / 100)
                return self.hex(col)
            if key in self.typo:
                return self.typo[key]
            if key in self.metrics:
                return self.metrics[key]
            raise SystemExit(f"error: unknown token {{{key}}} in template {spec!r}")
        return re.sub(r"\{([^}/]+)\}(?:/(\d+))?", sub, spec)

    @staticmethod
    def hex(col: C.RGBA) -> str:
        return C.fmt(col, upper=False)


# ---------------------------------------------------------------------------
# Mapping: (variable, template, what Gitea uses it for)
# ---------------------------------------------------------------------------
def _pri() -> list:
    rows = [
        ("--color-primary", "{accent.fill}", "Links, primary buttons, focus border, checked controls, progress."),
        ("--color-primary-contrast", "{accent.on}", "Text and icons on primary fills."),
    ]
    for n in range(1, 8):
        rows.append((f"--color-primary-dark-{n}", f"{{@p.dark.{n}}}", "Toward the strongest text (code match text, label hover, heatmap)." if n < 5 else "Far end of the dark scale."))
    for n in range(1, 8):
        rows.append((f"--color-primary-light-{n}", f"{{@p.light.{n}}}", "Toward the page background (heatmap low end, review counter, autofill, run labels)." if n < 7 else "Faintest tint."))
    for p in PCT:
        rows.append((f"--color-primary-alpha-{p}", f"{{accent.fill}}/{p}", f"Accent at {p}% (overlays, autocomplete selection)."))
    rows += [("--color-primary-hover", "{accent.hover}", "Hover of primary buttons and links."),
             ("--color-primary-active", "{accent.pressed}", "Pressed state of primary buttons.")]
    return rows


def _sec() -> list:
    rows = [("--color-secondary", "{border.subtle}", "Default separators, dividers, table rules (decorative: surfaces already separate)." )]
    for n in range(1, 14):
        rows.append((f"--color-secondary-dark-{n}", f"{{@s.dark.{n}}}", {1: "Progress track, footer rule.", 2: "Hover border of default buttons.", 4: "Disabled checked controls.", 5: "Form help text (muted text tier).", 8: "Loading spinner, image-diff handle."}.get(n, "Step on the subtle border → control border → text scale.")))
    for n in range(1, 5):
        rows.append((f"--color-secondary-light-{n}", f"{{@s.light.{n}}}", "Subtle border toward the surface."))
    for p in PCT:
        rows.append((f"--color-secondary-alpha-{p}", f"{{border.subtle}}/{p}", f"Subtle border at {p}% (table cell rules, heatmap empty cell)."))
    rows += [("--color-secondary-button", "var(--color-secondary-dark-4)", "Unused by 28.2.0 CSS; kept as in Gitea."),
             ("--color-secondary-hover", "var(--color-secondary-dark-3)", "Unused by 28.2.0 CSS; kept as in Gitea."),
             ("--color-secondary-active", "var(--color-secondary-dark-2)", "Unused by 28.2.0 CSS; kept as in Gitea.")]
    return rows


def _named() -> list:
    names = ["red", "orange", "yellow", "olive", "green", "teal", "blue", "violet", "purple", "pink", "brown", "black"]
    src = {"red": "danger.fg", "yellow": "warning.fg", "green": "success.fg", "blue": "info.fg", "teal": "data.5",
           "violet": "data.3", "brown": "data.4", "orange": "mix(danger.fg, warning.fg)", "olive": "mix(warning.fg, success.fg)",
           "purple": "mix(data.3, danger.fg)", "pink": "mix(data.3, danger.fg)", "black": "bg.raised (Slate) / text.primary (Daylight)"}
    rows = []
    for n in names:
        rows.append((f"--color-{n}", f"{{@{n}}}", f"Named color from {src[n]}; fills carry `--color-white` ({{accent.on}}) text."))
    for n in names:
        rows.append((f"--color-{n}-light", f"{{@{n}.light}}", "Lighter step."))
    for k in (1, 2):
        for n in names:
            rows.append((f"--color-{n}-dark-{k}", f"{{@{n}.dark.{k}}}", "Hover and pressed step (moves toward the strongest text)."))
    return rows


def _badges() -> list:
    rows = []
    for n, k in (("red", "red"), ("green", "green"), ("yellow", "yellow"), ("orange", "orange")):
        rows += [(f"--color-{n}-badge", f"{{@{k}}}", "Badge text and border."),
                 (f"--color-{n}-badge-bg", f"{{@{k}}}/10", "Badge fill (10% over the surface)."),
                 (f"--color-{n}-badge-hover-bg", f"{{@{k}}}/18", "Badge hover fill (18%).")]
    return rows


def _ansi() -> list:
    rows = []
    for n in ("red", "green", "yellow", "blue", "magenta", "cyan"):
        rows.append((f"--color-ansi-{n}", f"{{@ansi.{n}}}", "Actions log and console file colors."))
    rows += [("--color-ansi-black", lambda c: c.hex(c.t["border.control"] if c.dark else c.t["text.primary"]), "Readable on the console background in both modes (border.control in Slate, text.primary in Daylight)."),
             ("--color-ansi-bright-black", "{text.muted}", "Dim output."),
             ("--color-ansi-white", "var(--color-console-fg-subtle)", "As in Gitea."),
             ("--color-ansi-bright-white", "var(--color-console-fg)", "As in Gitea.")]
    for n in ("red", "green", "yellow", "blue", "magenta", "cyan"):
        rows.append((f"--color-ansi-bright-{n}", f"{{@ansi.bright.{n}}}", "Bright step, toward the strongest text."))
    return rows


def _series() -> list:
    return [(f"--color-series-16-{i}", f"{{@series.{i}}}", "Chart series: data.1…6, then lighter and deeper variants." if i == 0 else "Chart series.") for i in range(16)]


def _syntax() -> list:
    S = lambda k: f"{{syntax.{k}}}"  # noqa: E731
    rows = [
        ("--color-syntax-keyword", S("keyword"), "Keywords."), ("--color-syntax-control", S("keyword"), "Control-flow keywords."),
        ("--color-syntax-tag", S("keyword"), "Markup tags."), ("--color-syntax-preproc", S("keyword"), "Preprocessor."),
        ("--color-syntax-heading", S("keyword"), "Markdown headings in highlighted text."),
        ("--color-syntax-name", S("function"), "Function and class names."), ("--color-syntax-property", S("function"), "Properties."),
        ("--color-syntax-subheading", S("function"), "Sub-headings."),
        ("--color-syntax-type", S("type"), "Types."), ("--color-syntax-attribute", S("type"), "Attributes."),
        ("--color-syntax-entity", S("type"), "Entities."), ("--color-syntax-decorator", S("type"), "Decorators."),
        ("--color-syntax-name-pseudo", S("type"), "Pseudo names."),
        ("--color-syntax-string", S("string"), "Strings."), ("--color-syntax-string-special", S("string"), "Special strings."),
        ("--color-syntax-regexp", S("string"), "Regular expressions."), ("--color-syntax-preproc-file", S("string"), "Include paths."),
        ("--color-syntax-number", S("number"), "Numbers."), ("--color-syntax-bool", S("number"), "Booleans, constants."),
        ("--color-syntax-escape", S("number"), "Escape sequences."),
        ("--color-syntax-comment", S("comment"), "Comments."), ("--color-syntax-comment-special", S("comment"), "Doc comments."),
        ("--color-syntax-output", S("comment"), "Shell output."),
        ("--color-syntax-operator", "{text.secondary}", "Operators stay neutral."),
        ("--color-syntax-punctuation", "{text.secondary}", "Punctuation stays neutral."),
        ("--color-syntax-namespace", "{text.secondary}", "Namespaces stay neutral."),
        ("--color-syntax-text-alt", "{text.secondary}", "Secondary text."),
        ("--color-syntax-variable", "{text.primary}", "Variables stay neutral."),
        ("--color-syntax-text", "{text.primary}", "Plain code."), ("--color-syntax-diff-fg", "{text.primary}", "Text of highlighted diff lines."),
        ("--color-syntax-emph", "{text.primary}", "Emphasis (italic by the stylesheet)."),
        ("--color-syntax-strong", "{text.primary}", "Strong (bold by the stylesheet)."),
        ("--color-syntax-prompt", "{text.muted}", "Shell prompts."),
        ("--color-syntax-whitespace", "{text.disabled}", "Visible whitespace marks (decorative)."),
        ("--color-syntax-invalid", "{danger.fg}", "Invalid input."), ("--color-syntax-traceback", "{danger.fg}", "Tracebacks."),
        ("--color-syntax-link", "var(--color-primary)", "Links in code."),
        ("--color-syntax-deleted-bg", "{danger.bg}", "Deleted lines in a patch."),
        ("--color-syntax-inserted-bg", "{success.bg}", "Inserted lines in a patch."),
        ("--color-syntax-matching-bracket-bg", "{info.bg}", "Matching bracket."),
        ("--color-syntax-nonmatching-bracket-bg", "{danger.bg}", "Non-matching bracket."),
    ]
    return rows


GROUPS: list[tuple[str, list]] = [
    ("Theme metadata", [
        ("--is-dark-theme", lambda c: "true" if c.dark else "false", "Read by Gitea's color library to pick light or dark behavior."),
        ("accent-color", "var(--color-accent)", "Native controls (checkbox fallback, range)."),
        ("color-scheme", lambda c: "dark" if c.dark else "light", "Native form controls and scrollbars."),
    ]),
    ("Primary (accent)", _pri()),
    ("Secondary (borders and neutral steps)", _sec()),
    ("Surfaces", [
        ("--color-body", "{bg.canvas}", "Page background."),
        ("--color-box-header", "{bg.raised}", "Box and table headers."),
        ("--color-box-body", "{bg.surface}", "Box, segment and card content."),
        ("--color-box-body-highlight", "{bg.selected}", "Highlighted row inside a box."),
        ("--color-nav-bg", "{bg.surface}", "Top navigation bar."),
        ("--color-secondary-nav-bg", "{bg.surface}", "Repository sub-navigation."),
        ("--color-footer", "var(--color-nav-bg)", "Footer."),
        ("--color-menu", "{bg.raised}", "Dropdowns, menus, popups."),
        ("--color-card", "{bg.raised}", "Cards."),
        ("--color-button", "{bg.raised}", "Default button background."),
        ("--color-secondary-bg", "{bg.raised}", "Secondary segments, modal action bars, read-only inputs."),
        ("--color-code-bg", "{bg.canvas}", "Code view, code blocks, editor."),
        ("--color-expand-button", "{bg.selected}", "Diff expander."),
        ("--color-project-column-bg", "{bg.surface}", "Project board columns."),
        ("--color-hover", "{bg.hover}", "Hover background (opaque, so it never depends on the surface)."),
        ("--color-hover-opaque", "{bg.hover}", "Hover background where an opaque color is required."),
        ("--color-active", "{bg.selected}", "Active and selected rows, menu items."),
        ("--color-light", "{bg.hover}", "File input button."),
        ("--color-overlay-backdrop", "{@scrim}", "Modal scrim."),
        ("--color-shadow", "{@shadow}", "Shadow color of menus and modals (the core's overlay shadow)."),
        ("--color-shadow-opaque", "{border.subtle}", "Opaque shadow; unused by 28.2.0 CSS."),
        ("--color-timeline", "{border.subtle}", "Issue timeline line and badge ring."),
        ("--color-transparency-grid-light", "{bg.raised}", "Transparent image checkerboard."),
        ("--color-transparency-grid-dark", "{bg.hover}", "Transparent image checkerboard."),
    ]),
    ("Borders", [
        ("--color-light-border", "{border.control}", "Button, select, label and file-input outlines (functional: 3:1)."),
        ("--color-input-border", "{border.control}", "Input, checkbox and radio outlines (functional: 3:1)."),
        ("--color-input-toggle-background", "{border.control}", "Off track of toggles (functional mark: 3:1)."),
        ("--color-workflow-edge-hover", "{border.control}", "Actions workflow graph edge on hover."),
    ]),
    ("Text", [
        ("--color-text-dark", "{text.primary}", "Strongest text: headings, input text."),
        ("--color-text", "{text.primary}", "Body text."),
        ("--color-text-light", "{text.secondary}", "Secondary text."),
        ("--color-text-light-1", "{text.secondary}", "Secondary text."),
        ("--color-text-light-2", "{text.muted}", "Meta text, timestamps, counters."),
        ("--color-text-light-3", "{text.muted}", "Placeholders."),
        ("--color-placeholder-text", "var(--color-text-light-3)", "Input placeholders."),
        ("--color-caret", "{text.primary}", "Text caret."),
        ("--color-input-text", "var(--color-text-dark)", "Input text."),
        ("--color-input-background", "{bg.canvas}", "Input, textarea and checkbox background."),
        ("--color-nav-text", "var(--color-text)", "Navigation text."),
        ("--color-nav-hover-bg", "{bg.hover}", "Navigation hover."),
        ("--color-accent", "{accent.fg}", "Accent foreground (native control accent, small accents)."),
        ("--color-small-accent", "{bg.selected}", "Small accent backgrounds."),
        ("--color-tooltip-text", "{text.primary}", "Tooltip text."),
        ("--color-tooltip-bg", "{bg.raised}", "Tooltip surface."),
        ("--color-label-text", "{text.primary}", "Text of neutral labels."),
        ("--color-label-bg", "{bg.hover}", "Neutral label fill."),
        ("--color-label-hover-bg", "{bg.selected}", "Neutral label hover."),
        ("--color-label-active-bg", "{border.subtle}", "Neutral label pressed."),
        ("--color-highlight-fg", "{warning.fg}", "Search match and highlighted line text."),
        ("--color-highlight-bg", "{warning.bg}", "Search match and highlighted line background."),
        ("--color-editor-line-highlight", "{bg.hover}", "Editor current line."),
        ("--color-editor-selection", "{selection.bg}", "Editor selection."),
        ("--color-reaction-bg", "{bg.hover}", "Reaction chip."),
        ("--color-reaction-hover-bg", "{bg.selected}", "Reaction chip hover."),
        ("--color-reaction-active-bg", "{@reaction.active}", "Reaction chip you reacted with."),
        ("--color-markup-table-row", "{@zebra}", "Zebra rows in rendered markdown."),
        ("--color-markup-code-block", "{bg.canvas}", "Fenced code blocks in markdown."),
        ("--color-markup-code-inline", "{bg.hover}", "Inline code in markdown."),
    ]),
    ("Feedback", [
        ("--color-error-text", "{danger.fg}", "Danger text and icons."),
        ("--color-error-bg", "{danger.bg}", "Danger messages."),
        ("--color-error-bg-hover", "{@error.hover}", "Danger hover (4% step)."),
        ("--color-error-bg-active", "{@error.active}", "Danger pressed (8% step)."),
        ("--color-error-border", "{@error.border}", "Danger message outline (decorative: icon and text carry the meaning)."),
        ("--color-success-text", "{success.fg}", "Success text and CI passed icons."),
        ("--color-success-bg", "{success.bg}", "Success messages."),
        ("--color-success-border", "{@success.border}", "Success outline."),
        ("--color-warning-text", "{warning.fg}", "Warning text."),
        ("--color-warning-bg", "{warning.bg}", "Warning messages."),
        ("--color-warning-border", "{@warning.border}", "Warning outline."),
        ("--color-info-text", "{info.fg}", "Info text."),
        ("--color-info-bg", "{info.bg}", "Info messages."),
        ("--color-info-border", "{@info.border}", "Info outline."),
        ("--color-priority-text", "{syntax.number}", "Priority label text (violet data tone)."),
        ("--color-priority-bg", "{@priority.bg}", "Priority label background."),
        ("--color-priority-border", "{@priority.border}", "Priority label border."),
        ("--color-danger", "var(--color-red)", "Danger actions."),
    ]),
    ("Named colors", _named() + [
        ("--color-grey", "{text.muted}", "Grey labels and fills."),
        ("--color-grey-light", "{text.secondary}", "Grey text."),
        ("--color-gold", "{warning.fg}", "Gold (stars, sponsors)."),
        ("--color-white", "{accent.on}", "Text on every colored fill (buttons, labels, toggles, selection). It is the role accent.on, not white."),
    ]),
    ("Badges and brand", _badges() + [
        ("--color-git", "{text.secondary}", "Git mark color (set to secondary text; the Git logo in images keeps its own colors)."),
        ("--color-logo", "{accent.fg}", "Gitea mark color (set to the accent; the header logo is an image and renders in Gitea green)."),
    ]),
    ("Diff", [
        ("--color-diff-added-fg", "{success.fg}", "Added line text and + sign."),
        ("--color-diff-added-row-bg", "{success.bg}", "Added line."),
        ("--color-diff-added-linenum-bg", "{@diff.add.line}", "Added line number gutter."),
        ("--color-diff-added-row-border", "{@diff.add.border}", "Added line border."),
        ("--color-diff-added-word-bg", "{@diff.add.word}", "Added word (code tokens keep 4.5:1)."),
        ("--color-diff-removed-fg", "{danger.fg}", "Removed line text and − sign."),
        ("--color-diff-removed-row-bg", "{danger.bg}", "Removed line."),
        ("--color-diff-removed-linenum-bg", "{@diff.del.line}", "Removed line number gutter."),
        ("--color-diff-removed-row-border", "{@diff.del.border}", "Removed line border."),
        ("--color-diff-removed-word-bg", "{@diff.del.word}", "Removed word (code tokens keep 4.5:1)."),
        ("--color-diff-moved-row-bg", "{info.bg}", "Moved line (info tone, apart from added and removed)."),
        ("--color-diff-moved-row-border", "{@diff.move.border}", "Moved line border."),
        ("--color-diff-inactive", "{bg.canvas}", "Collapsed context."),
    ]),
    ("Console and Actions log", [
        ("--color-console-fg", "{text.primary}", "Log text."),
        ("--color-console-fg-subtle", "{text.secondary}", "Log timestamps and step counters."),
        ("--color-console-bg", "{bg.canvas}", "Log background."),
        ("--color-console-hover-bg", "{bg.hover}", "Log line hover."),
        ("--color-console-active-bg", "{bg.selected}", "Log line active."),
        ("--color-console-link", "{accent.fg}", "Links in the log."),
    ] + _ansi()),
    ("Chart series", _series()),
    ("Syntax", _syntax()),
    ("Fonts and radii", [
        ("--fonts-proportional", "{font.ui}", "Interface font (IBM Plex Sans; not bundled)."),
        ("--fonts-monospace", lambda c: c.typo["font.code"] + ", var(--fonts-emoji)", "Code font (Cascadia Code; not bundled)."),
        ("--border-radius", "{radius.control}", "Controls."),
        ("--border-radius-medium", "{radius.panel}", "Panels and popups."),
    ]),
]

OVERRIDES = """\
/* Selection: Gitea paints it with --color-primary-light-1 and --color-white; Flatcap has its own selection role. */
::selection,
relative-time::part(root)::selection {
  background: %(sel_bg)s;
  color: %(sel_fg)s;
}

/* Focus: Gitea uses --color-primary inside the control; Flatcap uses its ring, outside, against the surface. */
a:focus-visible,
button:focus-visible,
.ui.button:focus-visible,
[role="button"]:focus-visible {
  outline: %(fw)s solid %(ring)s;
  outline-offset: %(fo)s;
}
"""

EMOJI = """\
/* Invert emojis that are hard to read on a dark page (same as Gitea's dark theme). */
.emoji[data-alias="heavy_check_mark"],
.emoji[data-alias="currency_exchange"],
.emoji[data-alias="top"],
.emoji[data-alias="end"],
.emoji[data-alias="on"],
.emoji[data-alias="soon"],
.emoji[data-alias="heavy_dollar_sign"],
.emoji[data-alias="copyright"],
.emoji[data-alias="registered"],
.emoji[data-alias="tm"],
.emoji[data-alias="heavy_multiplication_x"],
.emoji[data-alias="heavy_plus_sign"],
.emoji[data-alias="heavy_minus_sign"],
.emoji[data-alias="heavy_division_sign"],
.emoji[data-alias="curly_loop"],
.emoji[data-alias="loop"],
.emoji[data-alias="wavy_dash"],
.emoji[data-alias="feet"],
.emoji[data-alias="musical_note"],
.emoji[data-alias="notes"] {
  filter: invert(100%) hue-rotate(180deg);
}
"""


# ---------------------------------------------------------------------------
# Loading and validation
# ---------------------------------------------------------------------------
def load() -> dict:
    return json.loads(THEME.read_text())


def load_inventory() -> dict:
    return json.loads(INV_FILE.read_text())


def validate_core(theme: dict) -> list[str]:
    errs = []
    if theme.get("version") != "2.0.0":
        errs.append(f"src/theme.json version is {theme.get('version')!r}, expected 2.0.0")
    for mode in MODES:
        t = theme["themes"].get(mode, {})
        n = sum(1 for k in t if not k.startswith("data."))
        if n != 37 or sum(1 for k in t if k.startswith("data.")) != 6:
            errs.append(f"{mode}: expected 37 semantic keys and 6 data keys, found {n}")
        for k, v in t.items():
            if not C.is_hex(v):
                errs.append(f"{mode}.{k}: not a hex color: {v!r}")
    return errs


def mode_vars(theme: dict, mode: str) -> tuple[list[tuple[str, list[tuple[str, str, str]]]], Ctx]:
    c = Ctx(theme, mode)
    out = []
    for group, rows in GROUPS:
        out.append((group, [(n, c.value(spec), note) for n, spec, note in rows]))
    return out, c


def check_names(groups_by_mode: dict, inv: dict) -> list[str]:
    errs = []
    known = {v["name"] for v in inv["theme_vars"]} | {v["name"] for v in inv["other_vars"]}
    theme_names = {v["name"] for v in inv["theme_vars"]}
    for mode, groups in groups_by_mode.items():
        names = [n for _, rows in groups for n, _, _ in rows]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            errs.append(f"{mode}: duplicated variables {dupes}")
        for n in names:
            if n not in known:
                errs.append(f"{mode}: {n} is not a variable of Gitea {GITEA_VERSION} (src/gitea-inventory.json)")
        missing = sorted(theme_names - set(names))
        if missing:
            errs.append(f"{mode}: {len(missing)} theme variables of Gitea are not set: {missing[:6]}...")
    return errs


# ---------------------------------------------------------------------------
# CSS emission
# ---------------------------------------------------------------------------
def root_block(groups, indent: str = "") -> str:
    lines = [f"{indent}:root {{"]
    for group, rows in groups:
        lines.append(f"{indent}  /* {group} */")
        for n, v, _ in rows:
            lines.append(f"{indent}  {n}: {v};")
    lines.append(f"{indent}}}")
    return "\n".join(lines)


def overrides_block(c: Ctx) -> str:
    return OVERRIDES % {"sel_bg": c.hex(c.t["selection.bg"]), "sel_fg": c.hex(c.t["selection.fg"]),
                        "fw": c.metrics["focus.width"], "fo": c.metrics["focus.offset"], "ring": c.hex(c.t["focus.ring"])}


def indent_text(s: str, pad: str) -> str:
    return "\n".join((pad + l if l else l) for l in s.splitlines())


def header(theme: dict, file: str, what: str) -> str:
    return (f"/* {what} {theme['version']} for Gitea {GITEA_VERSION}+.\n"
            f"   Generated by scripts/build.py from src/theme.json (Flatcap core). Do not edit by hand.\n"
            f"   Install as $GITEA_CUSTOM/public/assets/css/theme-{file}.css (see README). */\n")


def emit_single(theme: dict, mode: str) -> str:
    file, name, scheme, dark = MODES[mode]
    groups, c = mode_vars(theme, mode)
    parts = [header(theme, file, name),
             f'gitea-theme-meta-info {{\n  --theme-display-name: "{name}";\n  --theme-color-scheme: "{scheme}";\n}}\n',
             root_block(groups) + "\n", overrides_block(c)]
    if dark:
        parts.append(EMOJI)
    return "\n".join(parts)


def emit_auto(theme: dict) -> str:
    file, name = AUTO
    parts = [header(theme, file, name)]
    for mode, query in (("daylight", "light"), ("slate", "dark")):
        groups, c = mode_vars(theme, mode)
        body = root_block(groups) + "\n\n" + overrides_block(c) + ("\n" + EMOJI if MODES[mode][3] else "")
        parts.append(f"@media (prefers-color-scheme: {query}) {{\n{indent_text(body.rstrip(chr(10)), '  ')}\n}}\n")
    # Gitea reads the LAST gitea-theme-meta-info block of the file
    parts.append(f'gitea-theme-meta-info {{\n  --theme-display-name: "{name}";\n  --theme-color-scheme: "auto";\n}}\n')
    return "\n".join(parts)


def outputs(theme: dict) -> dict[Path, str]:
    return {THEMES_DIR / "theme-flatcap-slate.css": emit_single(theme, "slate"),
            THEMES_DIR / "theme-flatcap-daylight.css": emit_single(theme, "daylight"),
            THEMES_DIR / "theme-flatcap-auto.css": emit_auto(theme)}


# ---------------------------------------------------------------------------
# Effective values and contrast
# ---------------------------------------------------------------------------
class Eff:
    """Resolves var(--x) chains and composites alpha over a base for one mode."""
    def __init__(self, groups, c: Ctx):
        self.v = {n: val for _, rows in groups for n, val, _ in rows}
        self.c = c

    def get(self, ref: str, base: str | None = None) -> C.RGBA:
        if ref.startswith("{"):
            return self.c.rgba(ref.strip("{}"))
        val = self.v[ref]
        m = re.fullmatch(r"var\((--[\w-]+)\)", val)
        if m:
            return self.get(m.group(1), base)
        col = C.parse(val)
        if col[3] < 1:
            col = C.over(col, self.get(base if base else "--color-box-body"))
        return col


SURF = ["--color-body", "--color-box-body", "--color-box-header", "--color-menu", "--color-card", "--color-input-background",
        "--color-nav-bg", "--color-code-bg", "--color-secondary-bg"]
SYN_TEXT_VARS = ["keyword", "control", "tag", "preproc", "heading", "name", "property", "subheading", "type", "attribute",
                 "entity", "decorator", "name-pseudo", "string", "string-special", "regexp", "preproc-file", "number", "bool",
                 "escape", "comment", "comment-special", "output", "operator", "punctuation", "namespace", "text-alt",
                 "variable", "text", "diff-fg", "emph", "strong", "prompt", "invalid", "traceback", "link"]
NAMED_TEXT = ["red", "orange", "yellow", "olive", "green", "teal", "blue", "violet", "purple", "pink", "brown"]
NAMED_FILL = ["red", "orange", "yellow", "green", "purple"]


def pairs() -> list[tuple[str, str, str, float, str | None, str]]:
    """(group, fg, bg, target, base-for-alpha, label)."""
    P: list = []

    def add(group, fg, bg, target, base=None, label=None):
        P.append((group, fg, bg, target, base, label or f"{fg.strip('{}').replace('--color-', '')} on {bg.strip('{}').replace('--color-', '')}"))

    for fg in ("--color-text", "--color-text-dark"):
        for bg in SURF + ["--color-hover", "--color-active", "--color-box-body-highlight"]:
            add("Text on surfaces (7:1)", fg, bg, 7.0)
    for fg in ("--color-text-light", "--color-text-light-1"):
        for bg in ("--color-body", "--color-box-body", "--color-box-header", "--color-menu", "--color-hover", "--color-code-bg"):
            add("Secondary and muted text (5:1)", fg, bg, 5.0)
    for fg in ("--color-text-light-2", "--color-text-light-3", "--color-placeholder-text"):
        for bg in ("--color-body", "--color-box-body", "--color-box-header", "--color-menu", "--color-input-background", "--color-hover"):
            add("Secondary and muted text (5:1)", fg, bg, 5.0)
    for fg in ("--color-nav-text",):
        for bg in ("--color-nav-bg", "--color-nav-hover-bg"):
            add("Text on surfaces (7:1)", fg, bg, 7.0)
    add("Text on surfaces (7:1)", "--color-tooltip-text", "--color-tooltip-bg", 7.0)
    add("Text on surfaces (7:1)", "--color-label-text", "--color-label-bg", 7.0)
    add("Text on surfaces (7:1)", "--color-label-text", "--color-label-hover-bg", 7.0)
    add("Text on surfaces (7:1)", "--color-text", "--color-markup-code-block", 7.0)
    add("Text on surfaces (7:1)", "--color-text", "--color-markup-code-inline", 7.0)
    add("Text on surfaces (7:1)", "--color-text", "--color-markup-table-row", 7.0)
    add("Text on surfaces (7:1)", "--color-text", "--color-reaction-bg", 7.0)
    add("Text on surfaces (7:1)", "--color-text", "--color-reaction-hover-bg", 7.0)
    add("Text on surfaces (7:1)", "--color-text", "--color-reaction-active-bg", 7.0)
    add("Text on surfaces (7:1)", "--color-text", "--color-primary-light-6", 7.0)
    add("Text on surfaces (7:1)", "--color-text", "--color-primary-light-7", 7.0)
    add("Text on surfaces (7:1)", "--color-text", "--color-primary-alpha-30", 5.0, "--color-code-bg")
    add("Text on surfaces (7:1)", "--color-text", "--color-editor-selection", 5.0)
    add("Text on surfaces (7:1)", "--color-text", "--color-editor-line-highlight", 7.0, "--color-code-bg")
    add("Text on surfaces (7:1)", "--color-highlight-fg", "--color-highlight-bg", 5.0)
    add("Text on surfaces (7:1)", "--color-text", "--color-highlight-bg", 7.0)
    add("Selection", "{selection.fg}", "{selection.bg}", 4.5, None, "selection.fg on selection.bg (::selection rule)")
    for bg in ("--color-body", "--color-box-body", "--color-box-header", "--color-menu", "--color-card"):
        add("Links and accent (5:1)", "--color-primary", bg, 5.0)
        add("Links and accent (5:1)", "--color-primary-hover", bg, 5.0)
        add("Links and accent (5:1)", "--color-primary-active", bg, 5.0)
    add("Links and accent (5:1)", "--color-accent", "--color-box-body", 5.0)
    add("Links and accent (5:1)", "--color-primary-dark-1", "--color-code-bg", 5.0)
    for n in (1, 2, 3, 4):
        add("Primary fills (4.5:1)", "--color-primary-contrast", f"--color-primary-dark-{n}", 4.5)
    for bg in ("--color-primary", "--color-primary-hover", "--color-primary-active", "--color-primary-light-4", "--color-primary-light-5"):
        add("Primary fills (4.5:1)", "--color-primary-contrast", bg, 4.5)
    for n in NAMED_FILL:
        for suf in ("", "-dark-1", "-dark-2"):
            add("Colored fills (4.5:1)", "--color-white", f"--color-{n}{suf}", 4.5)
    add("Colored fills (4.5:1)", "--color-white", "--color-grey", 4.5)
    for n in NAMED_TEXT:
        for bg in ("--color-body", "--color-box-body"):
            add("Named colors as text (5:1)", f"--color-{n}", bg, 5.0)
    for kind in ("error", "success", "warning", "info"):
        bgs = ["bg"] + (["bg-hover", "bg-active"] if kind == "error" else [])
        for b in bgs:
            add("Feedback (5:1)", f"--color-{kind}-text", f"--color-{kind}-{b}", 5.0 if b == "bg" else 4.5)
        add("Feedback (5:1)", "--color-text", f"--color-{kind}-bg", 7.0)
        add("Feedback (5:1)", f"--color-{kind}-text", "--color-box-body", 5.0)
    add("Feedback (5:1)", "--color-priority-text", "--color-priority-bg", 5.0)
    for n in ("red", "green", "yellow", "orange"):
        add("Badges (5:1)", f"--color-{n}-badge", f"--color-{n}-badge-bg", 5.0, "--color-box-body")
        add("Badges (5:1)", f"--color-{n}-badge", f"--color-{n}-badge-hover-bg", 4.5, "--color-box-body")
    for row in ("added", "removed"):
        add("Diff (7:1 text, 4.5:1 code tokens)", "--color-text", f"--color-diff-{row}-row-bg", 7.0)
        add("Diff (7:1 text, 4.5:1 code tokens)", "--color-text", f"--color-diff-{row}-word-bg", 7.0)
        add("Diff (7:1 text, 4.5:1 code tokens)", "--color-text-light-2", f"--color-diff-{row}-linenum-bg", 5.0)
        add("Diff (7:1 text, 4.5:1 code tokens)", f"--color-diff-{row}-fg", "--color-box-body", 5.0)
        add("Diff (7:1 text, 4.5:1 code tokens)", f"--color-diff-{row}-fg", f"--color-diff-{row}-row-bg", 5.0)
        for tok in SYN_TEXT_VARS:
            if tok in ("link", "invalid", "traceback"):
                continue
            add("Diff tokens (4.5:1)", f"--color-syntax-{tok}", f"--color-diff-{row}-row-bg", 4.5)
            add("Diff tokens (4.5:1)", f"--color-syntax-{tok}", f"--color-diff-{row}-word-bg", 4.5)
    add("Diff (7:1 text, 4.5:1 code tokens)", "--color-text", "--color-diff-moved-row-bg", 7.0)
    add("Diff (7:1 text, 4.5:1 code tokens)", "--color-text", "--color-diff-inactive", 7.0)
    add("Diff (7:1 text, 4.5:1 code tokens)", "--color-text", "--color-syntax-deleted-bg", 7.0)
    add("Diff (7:1 text, 4.5:1 code tokens)", "--color-text", "--color-syntax-inserted-bg", 7.0)
    for tok in SYN_TEXT_VARS:
        add("Syntax on code background (5:1)", f"--color-syntax-{tok}", "--color-code-bg", 5.0)
        add("Syntax on code background (5:1)", f"--color-syntax-{tok}", "--color-box-body", 5.0)
    add("Syntax on code background (5:1)", "--color-text", "--color-syntax-matching-bracket-bg", 7.0)
    add("Syntax on code background (5:1)", "--color-text", "--color-syntax-nonmatching-bracket-bg", 7.0)
    for fg, t in (("--color-console-fg", 7.0), ("--color-console-fg-subtle", 5.0), ("--color-console-link", 5.0)):
        add("Console and Actions log", fg, "--color-console-bg", t)
    add("Console and Actions log", "--color-console-fg", "--color-console-hover-bg", 7.0)
    add("Console and Actions log", "--color-console-fg", "--color-console-active-bg", 7.0)
    for n in ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white", "bright-black", "bright-red", "bright-green",
              "bright-yellow", "bright-blue", "bright-magenta", "bright-cyan", "bright-white"):
        add("Console and Actions log", f"--color-ansi-{n}", "--color-console-bg", 5.0)
    for bg in ("--color-body", "--color-box-body", "--color-box-header", "--color-menu", "--color-card", "--color-input-background"):
        add("Functional outlines (3:1)", "{focus.ring}", bg, 3.0, None, f"focus.ring on {bg.replace('--color-', '')}")
    for bg in ("--color-box-body", "--color-button", "--color-menu", "--color-body"):
        add("Functional outlines (3:1)", "--color-light-border", bg, 3.0)
    for bg in ("--color-box-body", "--color-body", "--color-box-header"):
        add("Functional outlines (3:1)", "--color-input-border", bg, 3.0)
    add("Functional outlines (3:1)", "--color-input-toggle-background", "--color-box-body", 3.0)
    add("Functional outlines (3:1)", "--color-primary-light-4", "--color-body", 3.0)
    for i in range(16):
        add("Chart and data marks (3:1)", f"--color-series-16-{i}", "--color-box-body", 3.0)
    add("Chart and data marks (3:1)", "--color-text", "--color-box-body", 3.0, None, "text on box-body")
    return P


def contrast_rows(theme: dict) -> list[dict]:
    effs = {}
    for mode in MODES:
        groups, c = mode_vars(theme, mode)
        effs[mode] = Eff(groups, c)
    rows = []
    for group, fg, bg, target, base, label in pairs():
        r = {"group": group, "label": label, "target": target}
        for mode in MODES:
            e = effs[mode]
            b = e.get(bg, base)
            f = e.get(fg, base if base else bg)
            r[mode] = C.contrast(f, b)
        rows.append(r)
    # heatmap scale must be sequential: luminance is monotone along light-4, light-2, primary, dark-2, dark-4
    for mode in MODES:
        e = effs[mode]
        seq = ["--color-primary-light-4", "--color-primary-light-2", "--color-primary", "--color-primary-dark-2", "--color-primary-dark-4"]
        lums = [C.luminance(e.get(s)) for s in seq]
        mono = all(a < b for a, b in zip(lums, lums[1:])) if mode == "slate" else all(a > b for a, b in zip(lums, lums[1:]))
        rows.append({"group": "Chart and data marks (3:1)", "label": f"heatmap scale is sequential ({mode})", "target": 0.0,
                     "slate": 1.0 if mode == "slate" and mono else (0.0 if mode == "slate" else None),
                     "daylight": 1.0 if mode == "daylight" and mono else (0.0 if mode == "daylight" else None), "flag": True})
    return rows


def contrast_errors(theme: dict) -> list[str]:
    errs = []
    for r in contrast_rows(theme):
        for mode in MODES:
            v = r[mode]
            if v is None:
                continue
            if r.get("flag"):
                if v < 1:
                    errs.append(f"{mode}: {r['label']} fails")
            elif v + 1e-9 < r["target"]:
                errs.append(f"{mode}: {r['label']} = {v:.2f}:1, target {r['target']}:1")
    return errs


def contrast_report(theme: dict) -> str:
    out = []
    for r in contrast_rows(theme):
        if r.get("flag"):
            out.append(f"{r['label']:60s} {'ok' if (r['slate'] or r['daylight']) else 'FAIL'}")
            continue
        flag = "" if all(r[m] + 1e-9 >= r["target"] for m in MODES) else "  <-- FAIL"
        out.append(f"{r['group'][:28]:28s} {r['label'][:52]:52s} slate {r['slate']:5.2f}  daylight {r['daylight']:5.2f}  target {r['target']}{flag}")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Markdown blocks
# ---------------------------------------------------------------------------
def esc(s: str) -> str:
    return s.replace("|", "\\|")


def md_variables(theme: dict) -> str:
    gs, _ = mode_vars(theme, "slate")
    gd, _ = mode_vars(theme, "daylight")
    out = []
    for (group, rows), (_, rows_d) in zip(gs, gd):
        out.append(f"### {group}\n\n| Variable | Slate | Daylight | Role and use |\n| :--- | :--- | :--- | :--- |")
        for (n, vs, note), (_, vd, _) in zip(rows, rows_d):
            same = vs == vd
            out.append(f"| `{n}` | `{esc(vs)}` | {'same' if same else '`' + esc(vd) + '`'} | {esc(note)} |")
        out.append("")
    return "\n".join(out).rstrip()


def md_contrast(theme: dict) -> str:
    rows = contrast_rows(theme)
    out = ["| Pair | Target | Slate | Daylight |", "| :--- | ---: | ---: | ---: |"]
    group = None
    n_pass = n_total = 0
    for r in rows:
        if r.get("flag"):
            continue
        if r["group"] != group:
            group = r["group"]
            out.append(f"| **{group}** | | | |")
        out.append(f"| {r['label']} | {r['target']:g}:1 | {r['slate']:.2f}:1 | {r['daylight']:.2f}:1 |")
        n_total += 1
        n_pass += all(r[m] + 1e-9 >= r["target"] for m in MODES)
    flags = [r for r in rows if r.get("flag")]
    out.append("")
    out.append(f"{n_pass} of {n_total} pairs meet their target in both modes. Heatmap scale (`light-4 → light-2 → primary → dark-2 → dark-4`) is sequential in luminance: "
               + ", ".join(f"{m} {'yes' if any(f[m] == 1.0 for f in flags) else 'NO'}" for m in MODES) + ".")
    return "\n".join(out)


def md_summary(theme: dict) -> str:
    inv = load_inventory()
    gs, _ = mode_vars(theme, "slate")
    n = sum(len(rows) for _, rows in gs)
    return (f"{n} variables set per mode, which is every one of the {inv['counts']['theme_vars']} theme variables Gitea {GITEA_VERSION} "
            f"declares plus {n - inv['counts']['theme_vars']} font and radius variables.")


def md_themes(theme: dict) -> str:
    gs, _ = mode_vars(theme, "slate")
    n = sum(len(rows) for _, rows in gs)
    return "\n".join([
        "| Theme | File | Mode | Variables |", "| :--- | :--- | :--- | ---: |",
        f"| Flatcap (auto) | `theme-flatcap-auto.css` | follows `prefers-color-scheme` | {n} per mode |",
        f"| Flatcap Slate | `theme-flatcap-slate.css` | dark | {n} |",
        f"| Flatcap Daylight | `theme-flatcap-daylight.css` | light | {n} |"])


def md_fonts(theme: dict) -> str:
    t = theme["typography"]
    return "\n".join([
        "| Use | Stack (exact) |", "| :--- | :--- |",
        f"| Interface (`--fonts-proportional`) | `{t['font.ui']}` |",
        f"| Code (`--fonts-monospace`) | `{t['font.code']}` |", "",
        "The themes do not install fonts. Without IBM Plex Sans or Cascadia Code on the device, the stack falls back to Segoe UI, system-ui, Consolas or the system monospace font."])


def md_inventory(theme: dict) -> str:
    inv = load_inventory()
    gs, _ = mode_vars(theme, "slate")
    setn = {n for _, rows in gs for n, _, _ in rows}
    cnt = inv["counts"]
    out = [f"Gitea {GITEA_VERSION}: {cnt['theme_vars']} theme variables declared by the built-in themes; {cnt['read_by_css']} are read by `index.css`, "
           f"{cnt['read_by_js_only']} only by JavaScript, {cnt['no_reader_found']} `--color-*` variables have no reader in the 28.2.0 bundle "
           f"(still set, because a custom theme replaces the built-in one and a plugin or a later release may read them). "
           f"All {cnt['theme_vars']} are set by both modes: {'yes' if all(v['name'] in setn for v in inv['theme_vars']) else 'NO'}.", "",
           "| Variable | Gitea dark default | Gitea light default | CSS reads | JavaScript |", "| :--- | :--- | :--- | ---: | :--- |"]
    for v in inv["theme_vars"]:
        out.append(f"| `{v['name']}` | `{esc(v['dark'])}` | `{esc(v['light'])}` | {v['css_uses']} | {', '.join(v['js']) or '·'} |")
    out += ["", "Variables outside the themes that Flatcap sets:", "", "| Variable | Gitea value |", "| :--- | :--- |"]
    for v in inv["other_vars"]:
        if v["name"] in setn:
            out.append(f"| `{v['name']}` | `{esc(v['value'])}` |")
    return "\n".join(out)


BLOCKS = {README: {"themes": md_themes, "fonts": md_fonts},
          MAPPING_DOC: {"summary": md_summary, "variables": md_variables, "contrast": md_contrast},
          INV_DOC: {"inventory": md_inventory}}


def render_blocks(path: Path, blocks: dict, theme: dict) -> str:
    text = path.read_text()
    for name, fn in blocks.items():
        pat = re.compile(rf"(<!-- build:{name} -->\n).*?(<!-- /build:{name} -->)", re.S)
        if not pat.search(text):
            raise SystemExit(f"error: {path.name} lacks the <!-- build:{name} --> block")
        text = pat.sub(lambda m: m.group(1) + fn(theme) + "\n" + m.group(2), text)
    return text


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--contrast", action="store_true")
    a = ap.parse_args()
    if a.sync:
        if not UPSTREAM.exists():
            print(f"error: {UPSTREAM} not found", file=sys.stderr)
            return 1
        shutil.copyfile(UPSTREAM, THEME)
        print(f"synced src/theme.json from {UPSTREAM.parent.parent.name}")
    theme = load()
    errs = validate_core(theme)
    inv = load_inventory()
    groups = {m: mode_vars(theme, m)[0] for m in MODES}
    errs += check_names(groups, inv)
    if errs:  # unknown or missing variables: contrast cannot be evaluated reliably
        print("\n".join(f"error: {e}" for e in errs), file=sys.stderr)
        return 1
    if a.contrast:
        print(contrast_report(theme))
        return 0
    errs += contrast_errors(theme)
    want = outputs(theme)
    for path in BLOCKS:
        if path.exists():
            want[path] = render_blocks(path, BLOCKS[path], theme)
        else:
            errs.append(f"missing {path.relative_to(ROOT)}")
    if a.check:
        for path, text in want.items():
            if not path.exists() or path.read_text() != text:
                errs.append(f"stale: {path.relative_to(ROOT)} (run python3 scripts/build.py)")
        if errs:
            print("\n".join(f"error: {e}" for e in errs), file=sys.stderr)
            return 1
        print(f"ok: {len(want)} generated files current, every variable is in the Gitea {GITEA_VERSION} inventory, contrast targets met")
        return 0
    if errs:
        print("\n".join(f"error: {e}" for e in errs), file=sys.stderr)
        return 1
    THEMES_DIR.mkdir(exist_ok=True)
    for path, text in want.items():
        path.write_text(text)
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
