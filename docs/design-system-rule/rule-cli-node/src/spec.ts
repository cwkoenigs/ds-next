// The Rule design spec as source: everything in "Rule Terminal Design System" and "Rule Screens"
// as data. builders.ts draws it; this module holds the words. `rule spec --json` prints it.
import {G, GRID, MASCOT, MASCOT_INKS, PALETTE, ANSI16, SPINNER, VERBS} from './tokens.js';

export {VERBS};

export const NAME = 'Rule';
export const PRODUCT = 'ds-next';
export const VERSION = '1.0.0-modernist';
export const DATE = '2026-10-24';
export const TAGLINE = 'One red, strong rules, nothing rounded.';
export const SOURCE = 'Modernist design system (fb669593): neutral + accent ramps, 2px rules, radius 0, flush-left labels';

export const SUMMARY =
	'The Modernist design system translated to a terminal. Every turn opens with a numbered 2px rule; ' +
	'the input is a heavy square box pinned to the bottom; the agent speaks from a red square, tools from ' +
	'an ink one; results and folds align under them on a three-column grid. Red is the only colour and it ' +
	'means needs you: the prompt, the focused option, a failure. Everything else is ink on ground.';

type Pair = readonly [string, string];

export const ASSUMPTIONS: Pair[] = [
	['Source', 'Modernist tokens: neutral ramp for the greys, accent-500/400 (dark) and accent/accent-700 (light) for red. No green, no yellow.'],
	['Stack', 'The transcript is written once into scrollback; the footing is redrawn live. No alt-buffer.'],
	['Rules', 'Heavy box-drawing (━ ┃ ┏ ┓) is the terminal\'s 2px divider. Light lines are not used.'],
	['Width', '80 columns; rules, box and status row stretch to the real width.'],
];

/** §1: what changes from Canopy, the reference system. */
export const CHANGES_FROM_CANOPY: Pair[] = [
	['⏺', '■ agent (red) and ▪ tool (ink)'],
	['⎿', '└'],
	['Read 142 lines', '142 lines: results read as facts, not sentences'],
	['✻ Thought … (italic)', '· Thought for 3s  ctrl-o: the fold loses its italics'],
	['## heading', 'HEADING: headings in agent text are uppercase'],
	['a · b · c', 'a  b  c: facts separated by two spaces'],
	['╭ rounded box ╮', '┏ heavy square box ┓'],
	['? for shortcuts', '? shortcuts: the status row is bare'],
];

/** §2 */
export const PRINCIPLES: Pair[] = [
	['The grid shows', 'Three columns: 1 for glyphs, 3 for what is said or run, 5 for what came back, and a label column at 12. Values land in the same place on every screen so the eye reads down, not across.'],
	['Rules divide', 'Every prompt opens with a full-width heavy rule carrying the turn number flush left. Turns are addressable; the transcript reads as a ruled page. Nothing else draws horizontal lines.'],
	['One red, and it means you', 'Red is for the prompt glyph, the focused option, a failure, a warning. The agent\'s square is red because its words are addressed to you. Done is ink; success doesn\'t need a colour.'],
	['Nothing rounded', 'The input box and dialogs are heavy square frames. Squares (■ ▪ ▫ □) are the markers. The spinner is a rotating quadrant.'],
	['Flush left, always', 'Titles sit at the left end of a rule, labels at the left of their column, option numbers before their text. Nothing is centred: not the banner, not a dialog question.'],
	['The footing never moves', 'Heavy box + bare status row, redrawn in place; everything above is append-only scrollback.'],
	['Thinking is quiet', 'Reasoning streams in dim with a · lead, then folds to · Thought for 3s  ctrl-o. No italics: Modernist doesn\'t slant.'],
	['Facts, not sentences', 'Results are terse columns: +14 −1, 13 passed 1.42s, 3 tools  15.2s  $0.0041. Two spaces between facts; no separators.'],
];

/** §3: [role, dark hex, dark Modernist token, light hex, light Modernist token, use]. */
export const COLOURS: (readonly [string, string, string, string, string, string])[] = [
	['bg', PALETTE.dark.bg, 'text', PALETTE.light.bg, 'bg', 'ground'],
	['surface', PALETTE.dark.surface, 'neutral-900', PALETTE.light.surface, 'surface', 'inline code, file chips'],
	['text', PALETTE.dark.text, 'bg', PALETTE.light.text, 'text', 'ink; everything done'],
	['muted', PALETTE.dark.muted, 'neutral-400', PALETTE.light.muted, 'neutral-700', 'tool args, facts'],
	['dim', PALETTE.dark.dim, 'neutral-600', PALETTE.light.dim, 'neutral-500', 'results, thinking, hints, status row'],
	['rule', PALETTE.dark.rule, 'neutral-500', PALETTE.light.rule, 'neutral-700', 'turn rules, frames'],
	['accent', PALETTE.dark.accent, 'accent-500', PALETTE.light.accent, 'accent', '■ agent, ⚠, asking frame'],
	['accentText', PALETTE.dark.accentText, 'accent-400', PALETTE.light.accentText, 'accent-700', '› prompt, focus, failure line, ✗'],
];

export const COLOUR_RULES = [
	'one colour: red means needs-you (prompt, agent square, focused option, warning, failure)',
	'done is text; there is no green',
	'tool args and facts muted; results, thinking, hints, status row dim',
	'rules and frames in rule; a frame goes accent while asking',
	'a failed result\'s first line is accentText',
];

/** §4: [glyph, name, meaning, colour, column]. */
export const GLYPHS: (readonly [string, string, string, string, string])[] = [
	[G.prompt, 'prompt', 'Inside the box while typing; echoed flat under the turn rule.', 'accent', 'box col 3 · echo col 1'],
	[G.agent, 'agent', 'The agent speaking. Also the focused option in a dialog or popup.', 'accent', '1 · dialog col 3'],
	[G.tool, 'tool', 'A tool call that finished. Red when it failed.', 'text · accent', '1'],
	[`${G.pending} ${G.option}`, 'pending', '▫ a tool still running · □ an unselected dialog option.', 'dim', '1 · dialog col 3'],
	[G.result, 'result', 'First line of a tool result, and the fold line under it.', 'dim · accent text', '3 · fold 5'],
	[G.think, 'thinking', 'Leads streaming reasoning and its fold. Also the fact separator in the status row.', 'dim', '1'],
	['▘', 'working', 'Quadrant spinner ▖▘▝▗ with a verb: ▘ Drafting  4s  esc interrupts.', 'accent', '1'],
	[`${G.ok} ${G.warn} ${G.err}`, 'outcome', 'Local command results.', 'text · accent · accent bold', '1'],
	['━ ┃ ┏ ┓ ┗ ┛', 'rule / frame', 'Heavy lines only: turn rules, the box, dialogs, the banner.', 'rule · accent', '1 / width'],
	['‹ ›', 'choice', 'A value you cycle with ←/→ in a form.', 'text', 'field'],
];
export const RETIRED = ['⏺ ⎿ ✻ (Canopy)', '● → │ ╰ ◐ (Rail)', 'rounded corners', 'light box lines', 'any colour but red'];

/** §5 */
export const GRID_NOTES: Pair[] = [
	['Three indents', 'Col 1 glyphs, col 3 speech and tool calls, col 5 results (└ at 3, text at 5). Folds sit at col 5 under the result text.'],
	['Label column 12', 'Forms, /status, the banner facts: label flush left at col 3, value at col 16. Labels are uppercase in frames, lowercase in flow.'],
	['The footing is four rows', 'Box top, input, box bottom, status row. Popups insert above the status row. The box grows downward.'],
	['Rhythm', 'A heavy rule before every prompt, one blank line after it, one between messages, none between a tool and its └. Frames get a blank line above.'],
];
export const CASE = 'Frame titles, banner word-mark (DS-NEXT) and form labels uppercase. Flow text lowercase. No italics anywhere.';

/** §8 */
export const MOTION: Pair[] = [
	['Redraw only the footing', 'Box, popup and status row are the only repainted rows. The transcript above is written once.'],
	['One live line, then it lands', '▘ Drafting  4s  esc interrupts sits above the box; when the step finishes, the message replaces it in place: the ▪ lands where the ▘ was.'],
	['Thinking folds', 'Dim lines collapse to · Thought for 3s  ctrl-o. ctrl-o reopens the last fold.'],
	['Quadrant tempo', '▖▘▝▗ at 6 fps: a square turning, never a spinner\'s circle. Verb changes per step; seconds tick once a second.'],
	['Popup, not page', '/ opens a list under the box; ■ marks the focus; tab completes.'],
	['Dialogs replace the box', 'The frame edge goes red; the status row carries its keys; the answer prints as a flat line and the box returns.'],
];

export const MASCOT_NOTE = 'A canoe with a paddle. Two inks only, like the system: canoe in ink, paddle and water in red.';

/** §9: [token / helper, where in this package, differs from Canopy]. */
export const CODE_MAP: (readonly [string, string, string])[] = [
	['Colour roles', 'tokens.ts PALETTE, ANSI16 · theme.ts makeTheme(), resolve()', 'No ok/warn/err/thinking roles; accentText added'],
	['Glyphs', 'tokens.ts G, SPINNER (quadrant)', 'Squares and └ instead of ⏺ ⎿ ✻'],
	['Turn rule', 'builders.ts turnRule(n, w) · <TurnRule>', 'New'],
	['Grid', 'tokens.ts GRID: indent 2, resultIndent 4, labelWidth 12, factSep two spaces', 'Results one column shallower; two-space fact separator'],
	['Builders', 'agent() tool() result() thinking() thought() outcome() facts()', 'outcome() colours by need-you, not by kind'],
	['Frames', 'frame() heavy square; dialog(), inputBox(), statusRow(), popupRows()', 'Heavy ━┃, uppercase titles'],
	['Live parts', '<Working> <InputBox> <Popup> <DialogPicker> <Footing>', 'The box stays closed while you type'],
	['Banner + mascot', 'banner(), mascotRows(), MASCOT (canoe, ink + red paddle)', 'Two inks only'],
];

/** Rule Screens: [number, title, note]. */
export const SCREENS: (readonly [number, string, string])[] = [
	[1, 'Banner', 'Shown once. Heavy two-pane frame, canoe mascot in ink with a red paddle, uppercase word-mark and labels flush left, the footing already waiting.'],
	[2, '/new form', 'A form is a dialog: heavy frame, red edge, uppercase labels at col 3, values at col 16. The status row carries the keys.'],
	[3, 'Working', 'Thinking streams dim; a running tool shows ▫; the quadrant spinner with a verb sits above the footing. Typing queues.'],
	[4, 'Agent turn', 'Numbered rule, folded thinking, squares by voice, └ results as facts, uppercase heading in the reply, the box back in place.'],
	[5, 'Approval', 'The dialog takes the box\'s place. ■ on the default, □ on the rest, numbers answer, esc is the last option.'],
	[6, 'Slash popup', 'A filtered list between the box and the status row. ■ follows ↑↓; tab completes.'],
	[7, '/status', 'Local command: flat, no square. ✓ in ink, ⚠ in red. Label column 12.'],
];

export const KNOWN_GAPS = [
	'With no green, a long /status with many ✓ reads flat; intentional, worth a check on a real session.',
	'Heavy box-drawing needs a font with the full box set (Menlo, JetBrains Mono, Cascadia have it). On Windows use Windows Terminal, not the old console.',
	'ANSI-16 maps accent and accent text both to red (bold distinguishes).',
];

export function asJson() {
	const obj = (pairs: Pair[]) => Object.fromEntries(pairs);
	return {
		name: NAME, product: PRODUCT, version: VERSION, date: DATE, source: SOURCE, tagline: TAGLINE, summary: SUMMARY,
		assumptions: obj(ASSUMPTIONS),
		changesFromCanopy: obj(CHANGES_FROM_CANOPY),
		principles: obj(PRINCIPLES),
		colour: {
			roles: Object.fromEntries(COLOURS.map(([r, d, dt, l, lt, use]) => [r, {dark: d, darkToken: dt, light: l, lightToken: lt, use}])),
			ansi16: ANSI16,
			rules: COLOUR_RULES,
		},
		glyphs: Object.fromEntries(GLYPHS.map(([g, name, means, colour, column]) => [name, {glyph: g, means, colour, column}])),
		retired: RETIRED,
		grid: GRID, gridNotes: obj(GRID_NOTES), case: CASE,
		motion: obj(MOTION), spinner: SPINNER, spinnerVerbs: VERBS,
		mascot: {name: 'canoe with paddle', size: [28, 20], inks: MASCOT_INKS, note: MASCOT_NOTE, pixels: MASCOT},
		codeMap: CODE_MAP.map(([token, where, vsCanopy]) => ({token, where, vsCanopy})),
		screens: SCREENS.map(([n, title, note]) => ({n, title, note})),
		knownGaps: KNOWN_GAPS,
	};
}
