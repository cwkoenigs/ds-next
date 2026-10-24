"""The Rule design spec as source.

Everything in "Rule Terminal Design System" and "Rule Screens" lives here as data:
principles, colour roles, glyphs, grid, case, motion, mascot, code mapping and the
screen list. `ui_style.py` holds the rendering helpers; this module holds the words.
`rule-cli spec --json` prints it.
"""
from __future__ import annotations

from . import ui_style as u

NAME = "Rule"
PRODUCT = "ds-next"
VERSION = "1.0.0-modernist"
DATE = "2026-10-24"
TAGLINE = "One red, strong rules, nothing rounded."
SOURCE = "Modernist design system (fb669593): neutral + accent ramps, 2px rules, radius 0, flush-left labels"

SUMMARY = (
    "The Modernist design system translated to a terminal. Every turn opens with a numbered 2px rule; "
    "the input is a heavy square box pinned to the bottom; the agent speaks from a red square, tools from "
    "an ink one; results and folds align under them on a three-column grid. Red is the only colour and it "
    "means needs you: the prompt, the focused option, a failure. Everything else is ink on ground."
)

ASSUMPTIONS = [
    ("Source", ("Modernist tokens: neutral ramp for the greys, accent-500/400 (dark) and accent/accent-700 "
               "(light) for red. No green, no yellow.")),
    ("Stack", "Rich prints the transcript; prompt_toolkit owns the footing. No alt-buffer."),
    ("Rules", "Heavy box-drawing (━ ┃ ┏ ┓) is the terminal's 2px divider. Light lines are not used."),
    ("Width", "80 columns; rules, box and status row stretch to the real width."),
]

# §1: what changes from Canopy (the reference system)
CHANGES_FROM_CANOPY = [
    ("⏺", "■ agent (red) and ▪ tool (ink)"),
    ("⎿", "└"),
    ("Read 142 lines", "142 lines: results read as facts, not sentences"),
    ("✻ Thought … (italic)", "· Thought for 3s  ctrl-o: the fold loses its italics"),
    ("## heading", "HEADING: headings in agent text are uppercase"),
    ("a · b · c", "a  b  c: facts separated by two spaces"),
    ("╭ rounded box ╮", "┏ heavy square box ┓"),
    ("? for shortcuts", "? shortcuts: the status row is bare"),
]

# §2
PRINCIPLES = [
    ("The grid shows",
     ("Three columns: 1 for glyphs, 3 for what is said or run, 5 for what came back, and a label column at 12. "
     "Values land in the same place on every screen so the eye reads down, not across.")),
    ("Rules divide",
     ("Every prompt opens with a full-width heavy rule carrying the turn number flush left. Turns are "
     "addressable; the transcript reads as a ruled page. Nothing else draws horizontal lines.")),
    ("One red, and it means you",
     ("Red is for the prompt glyph, the focused option, a failure, a warning. The agent's square is red because "
     "its words are addressed to you. Done is ink; success doesn't need a colour.")),
    ("Nothing rounded",
     ("The input box and dialogs are heavy square frames. Squares (■ ▪ ▫ □) are the markers. "
     "The spinner is a rotating quadrant.")),
    ("Flush left, always",
     ("Titles sit at the left end of a rule, labels at the left of their column, option numbers before their "
     "text. Nothing is centred: not the banner, not a dialog question.")),
    ("The footing never moves",
     "Heavy box + bare status row, redrawn in place; everything above is append-only scrollback."),
    ("Thinking is quiet",
     ("Reasoning streams in dim with a · lead, then folds to · Thought for 3s  ctrl-o. No italics: "
     "Modernist doesn't slant.")),
    ("Facts, not sentences",
     ("Results are terse columns: +14 −1, 13 passed 1.42s, 3 tools  15.2s  $0.0041. "
     "Two spaces between facts; no separators.")),
]

# §3: (role, dark hex, dark Modernist token, light hex, light Modernist token, use)
COLOURS = [
    ("bg",          "#201e1d", "text",        "#f3f2f2", "bg",          "ground"),
    ("surface",     "#2d2b2b", "neutral-900", "#eae9e9", "surface",     "inline code, file chips"),
    ("text",        "#f3f2f2", "bg",          "#201e1d", "text",        "ink; everything done"),
    ("muted",       "#bab6b6", "neutral-400", "#605d5d", "neutral-700", "tool args, facts"),
    ("dim",         "#7d7979", "neutral-600", "#9b9797", "neutral-500", "results, thinking, hints, status row"),
    ("rule",        "#9b9797", "neutral-500", "#605d5d", "neutral-700", "turn rules, frames"),
    ("accent",      "#ff563c", "accent-500",  "#ec3013", "accent",      "■ agent, ⚠, asking frame"),
    ("accent_text", "#ff9783", "accent-400",  "#ae1800", "accent-700",  "› prompt, focus, failure line, ✗"),
]
ANSI16 = {"text": "default", "muted": "bright_black", "dim": "bright_black", "rule": "bright_black",
          "accent": "red", "accent_text": "bold red", "surface": "on bright_black"}
COLOUR_RULES = [
    "one colour: red means needs-you (prompt, agent square, focused option, warning, failure)",
    "done is text; there is no green",
    "tool args and facts muted; results, thinking, hints, status row dim",
    "rules and frames in rule; a frame goes accent while asking",
    "a failed result's first line is accent_text",
]

# §4: (glyph, name, meaning, colour, column)
GLYPHS = [
    (u.G.prompt, "prompt", "Inside the box while typing; echoed flat under the turn rule.", "accent", "box col 3 · echo col 1"),
    (u.G.agent, "agent", "The agent speaking. Also the focused option in a dialog or popup.", "accent", "1 · dialog col 3"),
    (u.G.tool, "tool", "A tool call that finished. Red when it failed.", "text · accent", "1"),
    (f"{u.G.pending} {u.G.option}", "pending", "▫ a tool still running · □ an unselected dialog option.", "dim", "1 · dialog col 3"),
    (u.G.result, "result", "First line of a tool result, and the fold line under it.", "dim · accent text", "3 · fold 5"),
    (u.G.think, "thinking", "Leads streaming reasoning and its fold. Also the fact separator in the status row.", "dim", "1"),
    ("▘", "working", "Quadrant spinner ▖▘▝▗ with a verb: ▘ Drafting  4s  esc interrupts.", "accent", "1"),
    (f"{u.G.ok} {u.G.warn} {u.G.err}", "outcome", "Local command results.", "text · accent · accent bold", "1"),
    ("━ ┃ ┏ ┓ ┗ ┛", "rule / frame", "Heavy lines only: turn rules, the box, dialogs, the banner.", "rule · accent", "1 / width"),
    ("‹ ›", "choice", "A value you cycle with ←/→ in a form.", "text", "field"),
]
RETIRED = ["⏺ ⎿ ✻ (Canopy)", "● → │ ╰ ◐ (Rail)", "rounded corners", "light box lines", "any colour but red"]

# §5
GRID = {
    "design_width": u.DESIGN_WIDTH, "min_width": 60,
    "indent": u.INDENT, "result_indent": u.RESULT_INDENT, "label_width": u.LABEL_W, "fact_separator": u.FACT_SEP,
    "columns": {"glyph": 1, "text": 3, "result_glyph": 3, "result_text": 5, "form_value": 16},
}
GRID_NOTES = [
    ("Three indents", ("Col 1 glyphs, col 3 speech and tool calls, col 5 results (└ at 3, text at 5). "
                      "Folds sit at col 5 under the result text.")),
    ("Label column 12", ("Forms, /status, the banner facts: label flush left at col 3, value at col 16. "
                        "Labels are uppercase in frames, lowercase in flow.")),
    ("The footing is four rows", ("Box top, input, box bottom, status row. Popups insert above the status row. "
                                 "The box grows downward.")),
    ("Rhythm", ("A heavy rule before every prompt, one blank line after it, one between messages, none between "
               "a tool and its └. Frames get a blank line above.")),
]
CASE = "Frame titles, banner word-mark (DS-NEXT) and form labels uppercase. Flow text lowercase. No italics anywhere."

# §8
MOTION = [
    ("Redraw only the footing", ("Box, popup and status row are the only repainted rows. "
                                "The transcript above is written once.")),
    ("One live line, then it lands", ("▘ Drafting  4s  esc interrupts sits above the box; when the step "
                                     "finishes, the message replaces it in place: the ▪ lands where the ▘ was.")),
    ("Thinking folds", "Dim lines collapse to · Thought for 3s  ctrl-o. ctrl-o reopens the last fold."),
    ("Quadrant tempo", ("▖▘▝▗ at 6 fps: a square turning, never a spinner's circle. "
                       "Verb changes per step; seconds tick once a second.")),
    ("Popup, not page", "/ opens a list under the box; ■ marks the focus; tab completes."),
    ("Dialogs replace the box", ("The frame edge goes red; the status row carries its keys; the answer prints "
                                "as a flat line and the box returns.")),
]
SPINNER = {"name": u.SPINNER, "frames": ["▖", "▘", "▝", "▗"], "interval_ms": 160}
VERBS = u.VERBS

MASCOT = {"name": "canoe with paddle", "size": [28, 20], "inks": {"I": "text", "R": "accent"},
          "note": "Two inks only, like the system. Canoe in ink, paddle and water in red."}

# §9: (token / helper, where in ui_style.py, differs from Canopy)
CODE_MAP = [
    ("Colour roles", "PALETTE (8 roles), theme(), pt_style()", "No ok/warn/err/thinking roles; accent_text added"),
    ("Glyphs", "G.agent G.tool G.pending G.option G.result G.think; SPINNER = 'quadrant'", "Squares and └ instead of ⏺ ⎿ ✻"),
    ("Turn rule", "turn_rule(n, w)", "New"),
    ("Grid", "INDENT = 2, RESULT_INDENT = 4, LABEL_W = 12, FACT_SEP = '  '", "Results one column shallower; two-space fact separator"),
    ("Builders", "agent_lines() tool() result() thinking() thought() outcome() facts()", "outcome() colours by need-you, not by kind"),
    ("Frames", "frame() heavy square; dialog(), input_frame(), status_row(), popup_rows()", "Heavy ━┃, uppercase titles"),
    ("Banner + mascot", "banner(), MASCOT (canoe, ink + red paddle)", "Two inks only"),
]

# Rule Screens: (number, title, note)
SCREENS = [
    (1, "Banner", ("Shown once. Heavy two-pane frame, canoe mascot in ink with a red paddle, uppercase word-mark "
                  "and labels flush left, the footing already waiting.")),
    (2, "/new form", ("A form is a dialog: heavy frame, red edge, uppercase labels at col 3, values at col 16. "
                     "The status row carries the keys.")),
    (3, "Working", ("Thinking streams dim; a running tool shows ▫; the quadrant spinner with a verb sits above "
                   "the footing. Typing queues.")),
    (4, "Agent turn", ("Numbered rule, folded thinking, squares by voice, └ results as facts, uppercase heading "
                      "in the reply, the box back in place.")),
    (5, "Approval", ("The dialog takes the box's place. ■ on the default, □ on the rest, numbers answer, "
                    "esc is the last option.")),
    (6, "Slash popup", "A filtered list between the box and the status row. ■ follows ↑↓; tab completes."),
    (7, "/status", "Local command: flat, no square. ✓ in ink, ⚠ in red. Label column 12."),
]

KNOWN_GAPS = [
    "With no green, a long /status with many ✓ reads flat; intentional, worth a check on a real session.",
    "Heavy box-drawing needs a font with the full box set (Menlo, JetBrains Mono, Cascadia have it).",
    "ANSI-16 maps accent and accent text both to red (bold distinguishes).",
    "prompt_toolkit must own the heavy box live; input_frame() is the static form.",
]


def as_dict() -> dict:
    return {
        "name": NAME, "product": PRODUCT, "version": VERSION, "date": DATE, "source": SOURCE,
        "tagline": TAGLINE, "summary": SUMMARY,
        "assumptions": dict(ASSUMPTIONS),
        "changes_from_canopy": dict(CHANGES_FROM_CANOPY),
        "principles": dict(PRINCIPLES),
        "colour": {
            "roles": {r: {"dark": d, "dark_token": dt, "light": l, "light_token": lt, "use": use}
                      for r, d, dt, l, lt, use in COLOURS},
            "ansi16": ANSI16, "rules": COLOUR_RULES,
        },
        "glyphs": {name: {"glyph": g, "means": m, "colour": c, "column": col} for g, name, m, c, col in GLYPHS},
        "retired": RETIRED,
        "grid": GRID, "grid_notes": dict(GRID_NOTES), "case": CASE,
        "motion": dict(MOTION), "spinner": SPINNER, "spinner_verbs": VERBS,
        "mascot": {**MASCOT, "pixels": u.MASCOT},
        "code_map": [{"token": t, "helper": h, "vs_canopy": d} for t, h, d in CODE_MAP],
        "screens": [{"n": n, "title": t, "note": note} for n, t, note in SCREENS],
        "known_gaps": KNOWN_GAPS,
    }
