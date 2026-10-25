// Rail's screens as mockups: `rule screen --look rail`. Built from the same look `rule agent --look
// rail` draws with (agent/looks.tsx), so what you see here is what the live terminal prints.
import {RAIL, type Status} from '../agent/looks.js';
import {NO_DESK} from '../agent/desk.js';
import {row, type Row, s} from '../text.js';
import * as r from './builders.js';
import {G, GRID, SPINNER} from './tokens.js';

const W = GRID.designWidth;

const status = (o: Partial<Status> = {}): Status => ({
	label: 'Cortex Code',
	cwd: '/Users/you/Developer/order-metrics',
	model: 'claude-sonnet-4-5',
	effort: 'low',
	cost: 0,
	lines: 0,
	turns: 0,
	queued: 0,
	connected: false,
	mode: 'idle',
	where: 'order-metrics: 16 adopted · 0 declined · 1 pending',
	desk: {canon: {standards: 26, scaffolds: 4, root: '/Users/you/Developer/canon'}, skills: 5, docs: true, where: () => ''},
	...o,
});

const editor = (value = '', items: [string, string][] = [], selected = 0) => ({value, at: value.length, items, selected, clear: () => {}});

export function start(): Row[] {
	return RAIL.banner(status(), W).slice(0, -1);
}

export function noCanon(): Row[] {
	return RAIL.banner(status({desk: NO_DESK, model: ''}), W).slice(0, -1);
}

const TESTING = '# Testing\nEvery repo runs its tests with one command.\nTests live beside the code they cover.';
const PASSED = '13 passed in 1.42s\ntests/test_cli.py ........\ntests/test_metrics.py .....';
const BASH = {command: 'uv run pytest -q', description: 'Run the test suite'};

/** One turn, landed: the echoed box, #1, the rail, a read, an approval, the run, the footer. */
export function turn(): Row[] {
	const cwd = status().cwd;
	return [
		...RAIL.accepted('run the tests and tell me if the testing standard is met', status(), W, W),
		...RAIL.turnStart(1),
		...RAIL.text("I'll read the canon's **testing** standard, then run `uv run pytest -q`.", W),
		...RAIL.toolStart('mcp__ds__canon_read', {id: 'testing'}, cwd, W),
		...RAIL.toolEnd('mcp__ds__canon_read', {id: 'testing'}, cwd, TESTING, false, W),
		...RAIL.toolStart('Bash', BASH, cwd, W),
		...RAIL.asking('Bash', BASH, W),
		...RAIL.answered('yes', 'y', 'Bash'),
		...RAIL.toolEnd('Bash', BASH, cwd, PASSED, false, W),
		...RAIL.text('## Done\nThe suite passes: **13 passed** in 1.42s.\n- the testing standard is met\n- nothing to change', W),
		...RAIL.ending({n: 1, tools: 2, durationMs: 15200, costUsd: 0.0041}, W).slice(0, -1),
	];
}

/** A ds tool that writes asks with its whole input, as Cortex sends it. */
export function approval(): Row[] {
	const input = {action: 'execute_command', resource: 'mcp__ds__scaffold_project\nInput: {\n "scaffold": "python-cli",\n "scaffold_version": 3,\n "name": "order-metrics",\n "purpose": "Daily order metrics for the ops team"\n}'};
	return [
		...RAIL.toolStart('mcp__ds__scaffold_project', {scaffold: 'python-cli', name: 'order-metrics'}, '', W),
		...RAIL.asking('mcp__ds__scaffold_project', input, W),
		r.answerLine(row('a', r.cursor())),
	];
}

/** The box, idle, with its toolbar; then with / typed and the menu open. */
export function prompt(): Row[] {
	const items: [string, string][] = [
		['/status', 'Agent, model, session and cost'],
		['/model', 'Switch model: /model <name>'],
		['/last', 'Full output of the last tool call'],
	];
	return [
		...RAIL.footing(editor(), status({turns: 1, connected: true}), W, W),
		[],
		...RAIL.footing(editor('/', items, 2), status({turns: 1, connected: true}), W, W),
	];
}

/** While a turn runs: the one live line, then the box, which queues what you type. */
export function working(): Row[] {
	const rows = SPINNER.frames.map((f, i) => RAIL.working(f, i === 0 ? 'Connecting to Cortex Code' : i === 1 ? 'Thinking' : 'Running canon_read', 2 + i));
	return [...rows, [], ...RAIL.footing(editor('then open a PR'), status({turns: 1, connected: true, mode: 'turn', queued: 1}), W, W)];
}

/** Local commands: flat, no rail. Colour names an outcome. */
export function local(): Row[] {
	return [
		RAIL.labelled('agent', 'Cortex Code'),
		RAIL.labelled('model', 'claude-sonnet-4-5'),
		RAIL.labelled('session', '7f3c2a10-…'),
		RAIL.labelled('turns', ['2', '5 tools', '$0.0093'].join(G.sep)),
		[],
		...RAIL.outcome('ok', 'new conversation', 'the next message starts a fresh session', W),
		...RAIL.outcome('warn', 'model', 'auto now; /model <name> switches', W),
		...RAIL.failure('Cortex Code', 'Cortex Code CLI not found: cortex is not on your PATH', W),
		[],
		...RAIL.interrupted(12, W),
		r.footer('#3'),
		...RAIL.hint('ctrl-c again to leave · or /exit'),
	];
}

export function help(): Row[] {
	return RAIL.help(
		[
			['/status', 'Agent, model, session and cost'],
			['/model', 'Switch model: /model <name>'],
			['/last', 'Full output of the last tool call'],
			['/clear', 'Start a new conversation'],
			['/help', 'List commands'],
			['/exit', 'Leave'],
		],
		'Cortex Code',
	);
}

/** The dog and the cat, alone. */
export const mascot = (): Row[] => r.mascotRows().map(m => row('  ', m));

export const glyphs = (): Row[] => [
	row(s(G.prompt, 'strong'), s('  you              strong  col 1', 'muted')),
	row(s(G.agent, 'accent'), s('  agent text       accent  col 1', 'muted')),
	row(s(G.rail, 'rule'), ' ', s(G.run, 'muted'), s('  tool call      muted   col 3', 'muted')),
	row(s(G.rail, 'rule'), '   ', s(G.result, 'dim'), s('  first result  dim     col 5', 'muted')),
	row(s(G.close, 'rule'), s('  turn footer      rule    col 1', 'muted')),
	row(s(G.ok, 'ok'), ' ', s(G.warn, 'warn'), ' ', s(G.err, 'err'), s('  outcomes     ok · warn · err, nothing else', 'muted')),
	row(s(G.fold, 'dim'), s('  more lines       dim', 'muted')),
	row(r.band(' New session '), s('  the session tag, on the brand band', 'muted')),
	row(r.key(' y '), s('  the one key to press', 'muted')),
];

/** [title, note, rows] for each screen, in order. */
export const SCREENS: [string, string, () => Row[]][] = [
	['Start', 'The banner, once: the dog and the cat, ds-next in strong, facts in accent, the canon\'s path on its own row.', start],
	['A turn', 'The box stays in the scrollback with your line. One rail per turn: ● the agent, → a tool, ⎿ its result, ╰ the footer.', turn],
	['Approval', 'A frame means "needs you": warn edge on the rail, the whole input, and the one key on a band. Only y, a or n answers.', approval],
	['The prompt', "Cortex Code's box, the terminal's width: rounded, the session tag on the top rule, the menu below it, the toolbar under all.", prompt],
	['Working', '◐◓◑◒ every 125 ms. The step says what is happening; the box below queues the next message.', working],
	['Local commands', 'Flat, no rail. ✓ ⚠ ✗ are the only coloured outcomes.', local],
	['Help', '/help: the command bold, its meaning muted.', help],
	['Glyphs', 'Each glyph has one meaning and one colour role.', glyphs],
	['Mascot', 'The dog (brand) and the cat (strong), arms around each other: 28×20 px in half-blocks, eyes in the terminal\'s ground.', mascot],
	['Without a canon', 'What the banner says on a machine with nothing set up yet.', noCanon],
];
