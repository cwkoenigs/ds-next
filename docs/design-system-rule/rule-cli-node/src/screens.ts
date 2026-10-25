// The seven Rule screens, plus the spec page's reference mockups, as rows. Each screen is the
// whole terminal at 80 columns: ruled transcript above, the heavy square footing below.
import * as b from './builders.js';
import {bold, type Content, row, type Row, s} from './text.js';
import {G, GRID} from './tokens.js';

export const MODEL_LINE = 'claude-sonnet-4-5 · ~/Developer/order-metrics · ctx 34%';
export const PROJECT_HINT = '/new python cli order-metrics';
const SEP = GRID.factSep;
const BLANK: Row = [];

// ── footing ──────────────────────────────────────────────────────────────────

export function footing(hint = PROJECT_HINT, left = '? shortcuts', right = MODEL_LINE, typed = ''): Row[] {
	return [...b.inputBox(typed, {hint}), b.statusRow(left, right)];
}

export function echo(n: number, said: string): Row[] {
	return [b.turnRule(n), b.you(said), BLANK];
}

const since = bold('--since');

export function changed(rows: [string, string][], wid = 26): Row[] {
	return rows.map(([f, d]) => row('  ', b.code(f), ' '.repeat(wid - f.length - 1), s(d, 'muted')));
}

// ── 1 banner ─────────────────────────────────────────────────────────────────

export const BANNER_FACTS: [string, string][] = [
	['cwd', '~/Developer'],
	['canon', '16 standards  2 scaffolds'],
	['skills', '5 from skills-os'],
	['docs', 'docs-ds found'],
];
export const BANNER_HINTS = ['/new starts a project', '/help lists commands', 'ctrl-d leaves'];

export function bannerRows(): Row[] {
	return b.banner('0.1.0', BANNER_FACTS, BANNER_HINTS, 'projects from the canon');
}

export function banner(): Row[] {
	return [...bannerRows(), BLANK, ...footing('/new python cli order-metrics  or ask a question')];
}

// ── 2 /new form ──────────────────────────────────────────────────────────────

function formRow(label: string, value: Content, {required = false, focus = false} = {}): Row {
	const lab = label.toUpperCase().padEnd(GRID.labelWidth - 1) + (required ? '*' : ' ');
	return row(s(lab, focus ? 'accentText' : 'dim'), ' ', value);
}

export function newFormFrame(): Row[] {
	return b.frame(
		[
			formRow('type', row('‹ Python command-line tool ›', SEP, s('1/2', 'dim'))),
			formRow('name', 'order-metrics', {required: true}),
			formRow('purpose', row('Pull daily order metrics from Snowflake for finance', b.cursor()), {required: true, focus: true}),
			formRow('owner', 'cwkoenigs'),
			null,
			formRow('applies', ['python-package', 'cli-ux', 'logging', 'testing', 'security', 'docs'].join(SEP)),
			formRow('into', '~/Developer/order-metrics'),
		],
		{edge: 'accent', title: [bold('NEW PROJECT FROM THE CANON', 'accent')]},
	);
}

export function newForm(n = 1): Row[] {
	return [...echo(n, PROJECT_HINT), ...newFormFrame(), BLANK, ...footing(PROJECT_HINT, 'tab next  ←→ cycle  enter create  esc cancel')];
}

// ── 3 working ────────────────────────────────────────────────────────────────

export const created = (): Row => b.outcome('ok', 'order-metrics', ['python-cli v1', '6 standards', '~/Developer/order-metrics'].join(SEP));

export const THINKING = [
	'The user wants an ISO date. Yesterday is the natural default because the',
	'purpose line says daily metrics for finance. Check how click options are',
	'declared in cli.py first…',
];

export function workingScreen(): Row[] {
	return [
		b.turnRule(1), b.you(PROJECT_HINT), BLANK, created(), BLANK,
		...echo(2, 'add a --since flag to the metrics command'),
		...THINKING.map((t, i) => b.thinking(t, i === 0)),
		BLANK,
		b.tool('Read', 'src/order_metrics/cli.py', 'running'), ...b.result('reading…'),
		BLANK, b.working('▝', 'Measuring', 4), BLANK,
		...footing('queue a message  it sends after this turn', 'esc interrupts'),
	];
}

// ── 4 agent turn ─────────────────────────────────────────────────────────────

export const TOOLS: {name: string; args: string; result: string; more: number; verb: string}[] = [
	{name: 'Read', args: 'src/order_metrics/cli.py', result: '142 lines', more: 0, verb: 'Reading'},
	{name: 'Edit', args: 'src/order_metrics/cli.py', result: '+14 −1', more: 0, verb: 'Squaring'},
	{name: 'Bash', args: 'uv run pytest -q', result: '13 passed in 1.42s', more: 11, verb: 'Running tests'},
];

export const opening = (): Row[] =>
	b.agent([row("I'll add ", since, ' as an ISO date and default it to yesterday, which is'), 'what the finance team asked for in the purpose line.']);
export const done = (): Row[] => b.agent([row('Done. ', since, ' defaults to yesterday and the tests pass.')]);

export function turnBody(): Row[] {
	return [
		b.thought(3), ...opening(), BLANK,
		...TOOLS.flatMap(t => [b.tool(t.name, t.args), ...b.result(t.result, t.more)]),
		BLANK, ...done(),
	];
}

export function summary(): Row[] {
	return [
		b.heading('Changed'),
		...changed([
			['src/order_metrics/cli.py', 'new option, ISO date, default yesterday'],
			['tests/test_cli.py', 'two cases: explicit date, default'],
		]),
		BLANK, b.facts('3 tools', '15.2s', '$0.0041'),
	];
}

export function turnScreen(): Row[] {
	return [...echo(2, 'add a --since flag to the metrics command'), ...turnBody(), BLANK, ...summary(), BLANK, ...footing()];
}

// ── 5 approval ───────────────────────────────────────────────────────────────

export const APPROVAL_OPTIONS: Content[] = [
	'Yes',
	row("Yes, and don't ask again for ", b.code('uv run'), ' in this project'),
	row('No, and tell ds-next what to do differently', SEP, s('esc', 'dim')),
];

export function approvalDialog(focus = 0, w?: number): Row[] {
	return b.dialog('Bash command', [[bold('uv run pytest -q')], [s('Run the test suite to check the new flag', 'muted')]], APPROVAL_OPTIONS, {focus, w});
}

export const approvalAsk = (): Row[] => b.agent('The flag parses. I want to run the suite to confirm nothing else moved.');

export function approvalScreen(): Row[] {
	return [
		...approvalAsk(), BLANK,
		b.tool('Bash', 'uv run pytest -q', 'running'), BLANK,
		...approvalDialog(), BLANK,
		...footing(PROJECT_HINT, 'enter chooses  1-3 answer  esc declines'),
	];
}

// ── 6 slash popup ────────────────────────────────────────────────────────────

export const COMMANDS: [string, string][] = [
	['/status', 'Project, canon and docs status'],
	['/standards', 'List the 16 standards and what applies here'],
	['/skills', 'Skills loaded from skills-os'],
	['/scaffold', 'Re-run a scaffold on the current project'],
];

export function popupScreen(typed = '/s', selected = 0): Row[] {
	const items = COMMANDS.filter(([c]) => c.startsWith(typed));
	return [
		...done(), BLANK, b.facts('3 tools', '15.2s', '$0.0041'), BLANK,
		...b.inputBox(typed), ...b.popupRows(items.length ? items : COMMANDS, selected), b.statusRow('↑↓ move  tab complete  esc close', MODEL_LINE),
	];
}

// ── 7 /status ────────────────────────────────────────────────────────────────

/** ✓ in ink, ⚠ in accent. Wraps at the value column rather than past col 80. */
function standardsRows(items: ['ok' | 'warn', string][], perLine = 4): Row[] {
	const out: Row[] = [];
	for (let i = 0; i < items.length; i += perLine) {
		const val: Row = [];
		items.slice(i, i + perLine).forEach(([kind, name], j) => {
			if (j) val.push(s(SEP));
			val.push(s(G[kind], kind === 'ok' ? 'text' : 'accent'), s(' ' + name));
		});
		out.push(b.labelled(i === 0 ? 'standards' : '', val));
	}
	return out;
}

export function statusBody(): Row[] {
	return [
		row('  ', bold('order-metrics'), SEP, s('python-cli v1  ~/Developer/order-metrics', 'muted')),
		BLANK,
		...standardsRows([['ok', 'python-package'], ['ok', 'cli-ux'], ['ok', 'logging'], ['ok', 'testing'], ['warn', 'security'], ['ok', 'docs']]),
		b.labelled('security', [s('1 finding: secrets read from env without a schema', 'muted')]),
		b.labelled('', [s('/explain security', 'muted')]),
		b.labelled('docs', ['docs-ds', '3 pages', 'built 2h ago'].join(SEP)),
		b.labelled('canon', ['16 standards', '2 scaffolds', 'up to date'].join(SEP)),
		b.labelled('session', ['4 turns', '9 tools', '$0.0128', 'ctx 34%'].join(SEP)),
	];
}

export function statusScreen(n = 3): Row[] {
	return [...echo(n, '/status'), ...statusBody(), BLANK, ...footing()];
}

export const SCREENS: Record<number, () => Row[]> = {
	1: banner, 2: newForm, 3: workingScreen, 4: turnScreen, 5: approvalScreen, 6: popupScreen, 7: statusScreen,
};

// ── spec page mockups ────────────────────────────────────────────────────────

const label = (t: string): Row => [s(t, 'dim')];

/** Spec §6: every message type, each under a dim caption. */
export function messageTypes(): Row[] {
	return [
		label('turn rule · numbered, flush left · before every prompt'), b.turnRule(4),
		label('you'), b.you('add a --since flag to the metrics command'), BLANK,
		label('thinking · dim, no italics, folds to one line'),
		b.thinking(THINKING[0]!, true), b.thinking('purpose line says daily metrics for finance…'), b.thought(3), BLANK,
		label('agent · ■ accent, text at col 3, headings uppercase, code on surface'),
		...b.agent([row("I'll add ", since, ' as an ISO date. Run ', b.code('uv run pytest'), ' after.')]), BLANK,
		label('tool + result · ▪ ink when done, └ result, fold aligned under it'),
		b.tool('Bash', 'uv run pytest -q'), ...b.result('13 passed in 1.42s', 11), BLANK,
		label('running tool · ▫ outline'),
		b.tool('Read', 'src/order_metrics/cli.py', 'running'), ...b.result('reading…'), BLANK,
		label('failed tool · the square and the first line go red'),
		b.tool('canon_read', 'securty', 'failed'), ...b.result('Error: securty is not a standard', 0, {error: true}),
		[s('    did you mean security?', 'dim')], BLANK,
		label('working · one live line, quadrant spinner'), b.working('▘', 'Drafting', 4), BLANK,
		label('outcomes · local commands · ink for done, red for anything that needs you'),
		b.outcome('ok', 'order-metrics', 'python-cli v1  6 standards applied'),
		b.outcome('warn', 'security', '1 finding  /explain security'),
		b.outcome('err', 'docs-ds', 'not found  set DS_DOCS or run /docs'), BLANK,
		label('turn summary · dim, two-space columns, no separators'), b.facts('3 tools', '15.2s', '$0.0041'),
	];
}

/** Spec §5a: the 80-column grid, the turn rule, the four pinned rows. */
export function gridDiagram(): Row[] {
	return [
		[s('col 1 3 5' + ' '.repeat(67) + '80', 'dim')],
		[s('│ │ │' + ' '.repeat(72) + '│', 'rule')],
		b.turnRule(1),
		row(s(G.prompt, 'accentText'), ' ', bold('you — echoed flat after the turn rule')),
		row(s(G.agent, 'accent'), ' ', s('agent text at col 3, wraps to col 3', 'dim')),
		row(G.tool, ' ', s('Tool args — name bold, args muted, same row', 'dim')),
		...b.result('result at col 5, under the tool name', 11),
		label('· thinking and its fold share col 1 with the squares'), BLANK,
		label('the footing · heavy square box · bare status row · always last'),
		...b.frame([row(s(G.prompt, 'accentText'), ' ', s('input · grows downward when wrapping', 'dim'))]),
		b.statusRow('? shortcuts', 'model · cwd · ctx 34%  right-aligned'), BLANK,
		label('rhythm   a rule before every prompt · blank after it · none between tool and └'),
	];
}

/** Spec §1b: the reference turn in Rule. */
export function ruleVsCanopy(): Row[] {
	return [...echo(3, 'add a --since flag to the metrics command'), ...turnBody(), BLANK, ...summary(), BLANK, ...footing()];
}

/** Spec §7: the permission dialog after an edit. */
export function dialogReference(): Row[] {
	return [b.tool('Edit', 'src/order_metrics/cli.py'), ...b.result('+14 −1'), BLANK, ...approvalDialog(), BLANK, ...footing(PROJECT_HINT, 'enter chooses  1-3 answer  esc declines')];
}

export const mascot = (): Row[] => b.mascotRows().map(m => row(' ', m));
