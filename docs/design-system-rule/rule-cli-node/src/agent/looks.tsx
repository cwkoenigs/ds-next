// How `rule agent` draws, in either look. Everything that differs between Rule and Rail is here: the
// banner, the turn's rhythm, how a tool call reads, the box, the approval. The session, the queue,
// the watchdog and the commands are AgentApp's, the same in both.
import {useInput} from 'ink';
import {homedir} from 'node:os';
import {basename} from 'node:path';
import {type ReactElement, useRef, useState} from 'react';
import * as b from '../builders.js';
import {Lines} from '../components/Lines.js';
import {DialogPicker, type Editor} from '../components/live.js';
import {StatusRow} from '../components/rule.js';
import {pyJsonDumps, pyJsonIndent} from '../ds/py.js';
import * as r from '../rail/builders.js';
import * as RT from '../rail/tokens.js';
import {bold, type Content, row, type Row, s, truncate, width, wrapRow, wrapWords} from '../text.js';
import {G, GRID, type LookName, SPINNER} from '../tokens.js';
import {type Answer, SERVER} from './backend.js';
import type {Desk} from './desk.js';
import {agentRows, markdownLines} from './markdown.js';
import {askContent, displayName, landed, toolArgs} from './present.js';

export const VERSION = '0.1.0';

export const tilde = (p: string, max = Infinity) => {
	const t = p.startsWith(homedir()) ? '~' + p.slice(homedir().length) : p;
	return t.length <= max ? t : '…' + t.slice(-(max - 1));
};

/** The session as it stands: what the banner, the footing and the approval say. */
export type Status = {
	label: string; // Cortex Code, Claude Code
	cwd: string;
	model: string;
	effort?: string;
	cost: number;
	lines: number; // every accepted line: Rule numbers each one
	turns: number; // agent turns: Rail numbers these (#n)
	queued: number;
	connected: boolean;
	mode: 'idle' | 'turn' | 'ask';
	where: string; // this repo against the canon
	desk: Desk;
};

export type Ending = {n: number; tools: number; durationMs: number; costUsd?: number; failure?: string};
export type Kind = 'ok' | 'warn' | 'err';
export type Step = {kind: 'start'; connected: boolean; label: string} | {kind: 'thinking'} | {kind: 'tool'; name: string} | {kind: 'toolResult'};
export type ApprovalProps = {name: string; input: Record<string, unknown>; cwd: string; w: number; status: Status; onAnswer: (a: Answer, typed: string) => void};
type Commands = readonly (readonly [string, string])[];

export interface AgentLook {
	name: LookName;
	spinner: {readonly frames: readonly string[]; readonly intervalMs: number};
	/** What ctrl-c does: leave at once (Rule), or interrupt a turn and leave on a second press (Rail, as ds-next). */
	ctrlC: 'exit' | 'interrupt';
	/** A blank line between messages inside a turn (Rule's rhythm), or one unbroken rail (Rail). */
	spaced: boolean;
	/** Between facts on one line: two spaces (Rule), " · " (Rail). */
	sep: string;
	/** The transcript's width in a terminal `cols` wide (Rail stops at 80, as ds-next does). */
	width(cols: number): number;
	banner(st: Status, cols: number): Row[];
	/** What stays in the scrollback when a line is accepted. */
	accepted(line: string, st: Status, cols: number, w: number): Row[];
	/** Output that is not part of a turn (a local command, an error): framed by the look's spacing. */
	block(rows: Row[]): Row[];
	turnStart(n: number): Row[];
	text(markdown: string, w: number): Row[];
	/** The line a thought leaves in the transcript, and what ctrl-o opens (none: Rail keeps reasoning private). */
	thinking(text: string, secs: number, w: number): {rows: Row[]; fold: Row[] | null};
	toolStart(name: string, input: Record<string, unknown>, cwd: string, w: number): Row[];
	toolRunning(name: string, input: Record<string, unknown>, cwd: string): Row | null;
	toolEnd(name: string, input: Record<string, unknown>, cwd: string, text: string, isError: boolean, w: number): Row[];
	/** A tool's whole output: ctrl-o and /last. */
	output(text: string): Row[];
	ending(e: Ending, w: number): Row[];
	interrupted(secs: number, w: number): Row[];
	outcome(kind: Kind, subject: string, detail: string, w: number): Row[];
	failure(label: string, message: string, w: number): Row[];
	note(text: string): Row[];
	hint(text: string): Row[];
	/** The spinner's word for this moment, or undefined to keep the one shown. */
	step(e: Step): string | undefined;
	working(frame: string, step: string, secs: number): Row;
	labelled(label: string, value: Content): Row;
	help(commands: Commands, label: string): Row[];
	keys(): Row[];
	footing(editor: Editor, st: Status, cols: number, w: number): Row[];
	/** Printed when the agent asks (Rail prints its approval frame; Rule's dialog is live). */
	asking(name: string, input: Record<string, unknown>, w: number): Row[];
	Approval(p: ApprovalProps): ReactElement;
	answered(a: Answer, typed: string, what: string): Row[];
}

// ── Rule ─────────────────────────────────────────────────────────────────────

const RULE_KEYS: [string, string][] = [
	['/', 'commands; ↑↓ move, tab completes'],
	['enter', 'send; while a turn runs, it queues'],
	['esc', 'interrupt the turn; clear the box'],
	['ctrl-o', 'open the last fold (thinking or tool output)'],
	['ctrl-d', 'leave (on an empty box)'],
];

/** Spinner verbs for the tools whose work has a name. */
const TOOL_VERBS: Record<string, string> = {Read: 'Reading', Grep: 'Searching', Glob: 'Searching', Bash: 'Running', Edit: 'Editing', Write: 'Writing', WebFetch: 'Fetching', WebSearch: 'Searching'};

/** An outcome that wraps instead of running off the edge; continuation lines sit at col 3. */
const ruleOutcome = (kind: Kind, subject: string, detail: string, w: number): Row[] =>
	wrapRow(b.outcome(kind, subject, detail), w).map((x, i) => (i ? row('  ', x) : x));

const ruleRight = (st: Status) => [st.model || st.label, tilde(st.cwd), st.cost ? `$${st.cost.toFixed(4)}` : `${st.lines} turns`].join(' · ');

function RuleApproval({name, input, cwd, w, status, onAnswer}: ApprovalProps) {
	const {title, body} = askContent(name, input, cwd, w);
	const answers: Answer[] = ['yes', 'always', 'no'];
	return (
		<>
			<DialogPicker
				title={title}
				body={body}
				options={['Yes', `Yes, and don't ask again for ${displayName(name)} this session`, row('No, and tell the agent what to do differently', '  ', s('esc', 'dim'))]}
				onAnswer={i => onAnswer(answers[i]!, String(i + 1))}
				w={w}
			/>
			<StatusRow left="enter chooses  1-3 answer  esc declines" right={ruleRight(status)} w={w} />
		</>
	);
}

export const RULE: AgentLook = {
	name: 'rule',
	spinner: SPINNER,
	ctrlC: 'exit',
	spaced: true,
	sep: GRID.factSep,
	width: cols => Math.max(GRID.minWidth, cols),
	banner: st => [...b.banner(VERSION, [['agent', st.label], ['cwd', tilde(st.cwd)], ['model', st.model || 'default'], ['session', 'new']], ['/help lists commands', 'ctrl-o opens a fold', 'ctrl-d leaves'], 'projects from the canon'), []],
	accepted: (line, st, _cols, w) => [b.turnRule(st.lines, w), b.you(line)],
	block: rows => [[], ...rows, []],
	turnStart: () => [],
	text: agentRows,
	thinking: (text, secs, w) => ({rows: [b.thought(secs)], fold: wrapWords(text, w - GRID.indent).map((l, i) => b.thinking(l, i === 0))}),
	toolStart: () => [],
	toolRunning: (name, input, cwd) => b.tool(displayName(name), toolArgs(name, input, cwd), 'running'),
	toolEnd: (name, input, cwd, text, isError) => landed(name, input, cwd, text, isError), // the ▪ lands where the ▫ was
	output: text => text.split('\n').map(l => [s('    ' + l, 'dim')]),
	ending: (e, w) => {
		const facts = [`${e.tools} tools`, `${(e.durationMs / 1000).toFixed(1)}s`];
		if (e.costUsd !== undefined) facts.push(`$${e.costUsd.toFixed(4)}`);
		return [[], ...(e.failure ? ruleOutcome('err', 'turn failed', e.failure, w) : []), b.facts(...facts), []];
	},
	interrupted: (_secs, w) => [[], ...ruleOutcome('warn', 'interrupted', 'tell the agent what to do instead', w), []],
	outcome: ruleOutcome,
	failure: (label, message, w) => ruleOutcome('err', label, message, w),
	note: text => [b.facts(text)],
	hint: text => [b.facts(text)],
	step: e => (e.kind === 'start' ? 'Drafting' : e.kind === 'tool' ? (TOOL_VERBS[displayName(e.name)] ?? b.verb()) : undefined),
	working: b.working,
	labelled: (label, value) => b.labelled(label, value),
	help: commands => b.popupRows(commands, -1),
	keys: () => RULE_KEYS.map(([k, v]) => row('  ', s(k.padEnd(10), 'dim'), s(v, 'muted'))),
	footing: (ed, st, _cols, w) => {
		const turn = st.mode === 'turn';
		const left = turn ? `esc interrupts${st.queued ? `  ${st.queued} queued` : ''}` : '? shortcuts';
		const hint = turn ? 'queue a message  it sends after this turn' : `ask ${st.label} anything  / for commands  ? for keys`;
		return [
			[],
			...b.inputBox(ed.value, {hint, at: ed.at, w}),
			...b.popupRows(ed.items, ed.selected),
			b.statusRow(ed.items.length ? '↑↓ move  tab complete  esc close' : left, ruleRight(st), w),
		];
	},
	asking: () => [],
	Approval: RuleApproval,
	answered: (a, _typed, what) => [row(s(G.prompt, 'accentText'), ' ', bold(a === 'no' ? 'No' : a === 'always' ? `Yes, and don't ask again for ${what}` : 'Yes'))],
};

// ── Rail: ds-next as it ships ────────────────────────────────────────────────

const RAIL_KEYS: [string, string][] = [
	['/', 'commands; ↑↓ move, tab completes'],
	['enter', 'send; while a turn runs, it queues'],
	['ctrl-c', 'interrupt the turn; twice at the prompt leaves'],
	['esc', 'interrupt the turn too; clear the box'],
	['ctrl-o', 'the last tool output in full (/last too)'],
	['ctrl-d', 'leave (on an empty box)'],
];

/** ds tools by their own name, other MCP servers' tools as server.tool, built-ins capitalised. */
export function railName(name: string): string {
	if (name.startsWith('mcp__')) {
		const [, server, ...rest] = name.split('__');
		if (rest.length) return server === SERVER ? rest.join('__') : `${server}.${rest.join('__')}`;
	}
	return displayName(name);
}

/** The one argument shown after the tool's name: ds-next's _arg_summary. */
export function argSummary(input: Record<string, unknown>): string {
	const cut = (t: string) => (t.length <= 60 ? t : t.slice(0, 57) + '…');
	for (const k of ['command', 'file_path', 'path', 'pattern', 'id', 'name', 'query', 'url', 'title']) {
		const v = input[k];
		if (typeof v === 'string') return cut(v.replace(/\n/g, ' '));
	}
	const json = pyJsonDumps(input);
	return json === '{}' ? '' : cut(json);
}

/** (title, detail) for an approval: ds-next's describe_permission. Cortex asks with a kind ("MCP",
 *  "Bash") and a resource string; Claude Code with the tool's id and its input. */
export function describePermission(name: string, input: Record<string, unknown>): [string, string] {
	const resource = typeof input['resource'] === 'string' ? (input['resource'] as string) : '';
	const [first = '', ...rest] = resource.split('\n');
	if (name === 'MCP' || (resource && first.trim() === name)) return [railName(first.trim()), rest.join('\n').replace(/^Input:/, '').trim()];
	if (name.startsWith('mcp__')) return [railName(name), Object.keys(input).length ? pyJsonIndent(input) : ''];
	if (typeof input['command'] === 'string') return [displayName(name), input['command'] as string];
	return [displayName(name), resource || pyJsonIndent(input)];
}

/** │   ⎿ first  ┄ N more lines · ctrl-o, cut so the whole row fits `w`. */
function railResult(text: string, isError: boolean, w: number): Row {
	const clean = text.replace(/<\/?tool_use_error>/g, '').trim();
	const lines = clean ? clean.split('\n') : ['(no output)'];
	const error = isError || clean.startsWith('ERROR:'); // Cortex drops is_error; ds tools say so in their first word
	const first = (error ? 'ERROR ' + lines[0]!.replace(/^ERROR:/, '').trim() : lines[0]!).slice(0, 66);
	let out = r.result(first, lines.length - 1, {error});
	for (let room = first.length; width(out) > w && room > 1; room--) out = r.result(first.slice(0, room - 1) + '…', lines.length - 1, {error});
	return out;
}

/** An error that wraps; continuation lines sit at col 3. */
const railError = (what: string, w: number, fix = ''): Row[] => [
	...wrapRow(row(s(RT.G.err, 'err'), ' ', what), w).map((x, i) => (i ? row('  ', x) : x)),
	...(fix ? [r.hint(fix)] : []),
];

const railTag = (st: Status) => (st.turns === 0 ? 'New session' : `#${st.turns + 1}`);

function RailApproval({onAnswer}: ApprovalProps) {
	const [typed, setTypedState] = useState('');
	const cur = useRef(''); // read by the keys, so a fast "y" then enter is never read as ""
	const setTyped = (t: string) => setTypedState((cur.current = t));
	// Only an explicit y, a or n counts; enter alone asks again. Esc and ctrl-c say no, as ds-next's do.
	useInput((input, key) => {
		if (key.return) {
			const t = cur.current.trim().toLowerCase();
			const a: Answer | undefined = t === 'y' || t === 'yes' ? 'yes' : t === 'a' || t === 'always' ? 'always' : t === 'n' || t === 'no' ? 'no' : undefined;
			if (a) onAnswer(a, cur.current.trim());
			else setTyped('');
			return;
		}
		if (key.escape || (key.ctrl && input === 'c')) return onAnswer('no', 'n');
		if (key.backspace || key.delete) return setTyped(cur.current.slice(0, -1));
		if (key.ctrl || key.meta || !input) return;
		setTyped(cur.current + input.replace(/[\r\n]+/g, ''));
	});
	return <Lines rows={[r.answerLine(row(typed, r.cursor()))]} />;
}

export const RAIL: AgentLook = {
	name: 'rail',
	spinner: RT.SPINNER,
	ctrlC: 'interrupt',
	spaced: false,
	sep: RT.G.sep,
	width: cols => Math.max(RT.GRID.minWidth, Math.min(cols, RT.GRID.designWidth)),
	banner: st => {
		const d = st.desk;
		const facts: [string, string][] = [
			['agent', st.label],
			['cwd', tilde(st.cwd, 30)],
			['canon', d.canon ? `${d.canon.standards} standards · ${d.canon.scaffolds} project types` : 'not found · set DS_CANON'],
			['skills', d.skills !== undefined ? `${d.skills} from skills-os` : 'skills-os not found'],
			['docs', `docs-ds ${d.docs ? 'found' : 'not found'}`],
			['model', `${st.model || 'auto'} · effort ${st.effort || 'default'}`],
		];
		const path = d.canon ? tilde(d.canon.root, 60) : 'no canon on this machine · set DS_CANON or clone it to ~/Developer/canon';
		return [...r.banner(`v${VERSION}`, facts, ['/help lists commands · ? lists keys', 'ctrl-d leaves · ctrl-c twice too'], path, 'start, check and grow'), []];
	},
	accepted: (line, st, cols) => [...r.promptEcho(railTag(st), line, cols), []], // the box stays in the scrollback, with the line
	block: rows => [...rows, []],
	turnStart: n => [[s(`#${n}`, 'dim')]],
	text: (md, w) => r.agent(markdownLines(md, w - RT.GRID.indent, {upper: false, bullet: '•'})),
	thinking: () => ({rows: [], fold: null}), // private reasoning stays private, as in Claude Code
	toolStart: (name, input, _cwd, w) => [truncate(r.run(railName(name), argSummary(input)), w)],
	toolRunning: () => null,
	toolEnd: (_name, _input, _cwd, text, isError, w) => [railResult(text, isError, w)],
	output: text => text.split('\n').map(l => [s(' '.repeat(RT.GRID.resultIndent) + l, 'muted')]),
	ending: (e, w) => {
		const facts = [`#${e.n}`, `${e.tools} tool call${e.tools === 1 ? '' : 's'}`, `${(e.durationMs / 1000).toFixed(1)}s`];
		if (e.costUsd) facts.push(`$${e.costUsd.toFixed(4)}`);
		const failed = e.failure ? [truncate(r.result(e.failure, 0, {error: true}), w)] : [];
		return [...failed, r.footer(...facts), []];
	},
	interrupted: secs => [r.result(`interrupted after ${secs}s · session kept`, 0, {error: true})],
	outcome: (kind, subject, detail, w) => wrapRow(r.outcome(kind, subject, detail), w).map((x, i) => (i ? row('  ', x) : x)),
	failure: (label, message, w) => railError(`${label}: ${message}`, w, 'retry, or /clear'),
	note: text => [r.hint(text)],
	hint: text => [r.hint(text)],
	step: e => {
		switch (e.kind) {
			case 'start':
				return e.connected ? 'Thinking' : `Connecting to ${e.label}`;
			case 'tool':
				return `Running ${railName(e.name)}`;
			default:
				return 'Thinking';
		}
	},
	working: (frame, step, secs) => r.working(frame, step, secs),
	labelled: (label, value) => r.labelled(label, value),
	help: (commands, label) => [
		...r.commandRows([...commands, ['anything else', `goes to ${label}, with the knowledge base as tools`]]),
		r.hint('ctrl-c interrupts a turn · ctrl-c twice or ctrl-d leaves'),
	],
	keys: () => r.commandRows(RAIL_KEYS),
	footing: (ed, st, cols) => {
		const where = [basename(st.cwd), st.where, st.model || 'auto', st.effort || 'default', st.connected ? 'connected' : 'idle'].join(RT.G.sep);
		const right = `${st.queued ? `${st.queued} queued${RT.G.sep}` : ''}#${st.turns}`;
		const hint = st.mode === 'turn' ? 'queue a message · it sends after this turn' : '';
		return [...r.promptBox(railTag(st), r.promptLine(ed.value, {hint, at: ed.at}), cols), ...r.menu(ed.items, ed.selected, cols), r.toolbar(where, right, cols)];
	},
	asking: (name, input, w) => {
		const [title, detail] = describePermission(name, input);
		return r.approval(title, detail, w);
	},
	Approval: RailApproval,
	answered: (_a, typed) => [r.answerLine(typed)],
};

export const LOOK: Record<LookName, AgentLook> = {rule: RULE, rail: RAIL};
