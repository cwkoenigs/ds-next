// `rule agent`: a real session with Claude Code or Cortex Code, drawn in Rule. Each event lands in
// the transcript once; the live area holds only the running tools, the spinner and the footing.
import {Box, useApp, useInput} from 'ink';
import {homedir} from 'node:os';
import {useCallback, useEffect, useRef, useState} from 'react';
import * as b from '../builders.js';
import {Lines} from '../components/Lines.js';
import {DialogPicker, Footing, useLineEditor, Working} from '../components/live.js';
import {StatusRow} from '../components/rule.js';
import {Transcript, useTranscript} from '../components/transcript.js';
import {bold, row, type Row, s, wrapRow, wrapWords} from '../text.js';
import {G, GRID} from '../tokens.js';
import {type AgentSession, type Answer, type Backend, LABELS, type SessionOptions} from './backend.js';
import type {AgentEvent} from './events.js';
import {agentRows} from './markdown.js';
import {askContent, displayName, landed, toolArgs} from './present.js';

export type Opener = (o: SessionOptions) => Promise<AgentSession>;

const COMMANDS: [string, string][] = [
	['/status', 'Agent, model, session and cost'],
	['/model', 'Switch model: /model <name>'],
	['/clear', 'Start a new conversation'],
	['/help', 'List commands'],
	['/exit', 'Leave'],
];

const KEYS: [string, string][] = [
	['/', 'commands; ↑↓ move, tab completes'],
	['enter', 'send; while a turn runs, it queues'],
	['esc', 'interrupt the turn; clear the box'],
	['ctrl-o', 'open the last fold (thinking or tool output)'],
	['ctrl-d', 'leave (on an empty box)'],
];

/** Silence longer than this, outside an approval, interrupts the turn (as ds-next does). */
export const IDLE_MS = 10 * 60 * 1000;

const VERBS: Record<string, string> = {Read: 'Reading', Grep: 'Searching', Glob: 'Searching', Bash: 'Running', Edit: 'Editing', Write: 'Writing', WebFetch: 'Fetching', WebSearch: 'Searching'};

const tilde = (p: string) => (p.startsWith(homedir()) ? '~' + p.slice(homedir().length) : p);

/** An outcome that wraps instead of running off the edge; continuation lines sit at col 3. */
const outcome = (kind: 'ok' | 'warn' | 'err', subject: string, detail: string, w: number): Row[] =>
	wrapRow(b.outcome(kind, subject, detail), w).map((r, i) => (i ? row('  ', r) : r));

type Pending = {name: string; input: Record<string, unknown>};
type Ask = {name: string; input: Record<string, unknown>; resolve: (a: Answer) => void};
/** What was printed last, for the rhythm: a blank between messages, none between tools. */
type Last = 'none' | 'text' | 'tool' | 'thought' | 'rule';

export function AgentApp({backend, open, cwd, width, model: initialModel, connection, effort}: {
	backend: Backend;
	open: Opener;
	cwd: string;
	width: number;
	model?: string;
	connection?: string;
	effort?: string;
}) {
	const {exit} = useApp();
	const w = Math.max(GRID.minWidth, width);
	const label = LABELS[backend];
	const {log, printRows} = useTranscript();

	const [mode, setMode] = useState<'idle' | 'turn' | 'ask'>('idle');
	const [pending, setPending] = useState<Map<string, Pending>>(new Map());
	const [verb, setVerb] = useState('Drafting');
	const [ask, setAsk] = useState<Ask | null>(null);
	const [queue, setQueue] = useState<string[]>([]);
	const [model, setModel] = useState(initialModel ?? '');
	const [turnStart, setTurnStart] = useState(Date.now());

	const session = useRef<AgentSession | null>(null);
	const sessionId = useRef<string | undefined>(undefined);
	const closing = useRef(false);
	const interrupted = useRef(false);
	const last = useRef<Last>('none');
	const lastEvent = useRef(Date.now());
	const fold = useRef<Row[]>([]);
	const pendingRef = useRef(pending);
	const modeRef = useRef(mode);
	const stats = useRef({turns: 0, tools: 0, turnTools: 0, cost: 0});
	pendingRef.current = pending;
	modeRef.current = mode;

	/** Print with the spec's rhythm. */
	const emit = useCallback(
		(kind: Last, rows: Row[]) => {
			const tight = (kind === 'tool' && last.current === 'tool') || (kind === 'text' && last.current === 'thought') || last.current === 'rule' || last.current === 'none';
			printRows(tight ? rows : [[], ...rows]);
			last.current = kind;
		},
		[printRows],
	);

	const endTurn = useCallback(() => {
		setPending(new Map());
		setMode('idle');
	}, []);

	const onEvent = useCallback(
		(e: AgentEvent) => {
			const now = Date.now();
			const since = Math.max(1, (now - lastEvent.current) / 1000);
			lastEvent.current = now;
			switch (e.kind) {
				case 'init':
					sessionId.current = e.sessionId || sessionId.current;
					if (e.model) setModel(e.model);
					return;
				case 'thinking':
					fold.current = wrapWords(e.text, w - GRID.indent).map((l, i) => b.thinking(l, i === 0));
					emit('thought', [b.thought(since)]);
					return;
				case 'text':
					emit('text', agentRows(e.text, w));
					return;
				case 'tool':
					stats.current.tools++;
					stats.current.turnTools++;
					setVerb(VERBS[displayName(e.name)] ?? b.verb());
					setPending(p => new Map(p).set(e.id, {name: e.name, input: e.input}));
					return;
				case 'toolResult': {
					const p = pendingRef.current.get(e.id);
					if (!p) return;
					setPending(m => {
						const n = new Map(m);
						n.delete(e.id);
						return n;
					});
					const rows = landed(p.name, p.input, cwd, e.text, e.isError);
					if (rows.length > 2 || e.isError) fold.current = e.text.split('\n').map(l => [s('    ' + l, 'dim')]);
					emit('tool', rows); // the ▪ lands where the ▫ was
					return;
				}
				case 'result': {
					if (e.costUsd) stats.current.cost += e.costUsd;
					const facts = [`${stats.current.turnTools} tools`, `${(e.durationMs / 1000).toFixed(1)}s`];
					if (e.costUsd !== undefined) facts.push(`$${e.costUsd.toFixed(4)}`);
					const rows: Row[] = [b.facts(...facts)];
					if (!e.ok && !interrupted.current) rows.unshift(...outcome('err', 'turn failed', e.errors[0] ?? 'the agent reported an error', w));
					printRows([[], ...rows, []]);
					last.current = 'none';
					endTurn();
					return;
				}
				case 'error':
					printRows([[], ...outcome('err', label, e.message, w), []]);
					last.current = 'none';
					endTurn();
					return;
			}
		},
		[cwd, emit, endTurn, label, printRows, w],
	);

	const askPerson = useCallback(
		(name: string, input: Record<string, unknown>) =>
			new Promise<Answer>(resolve => {
				setAsk({name, input, resolve});
				setMode('ask');
			}),
		[],
	);

	const ensureSession = useCallback(async (): Promise<AgentSession | null> => {
		if (session.current) return session.current;
		try {
			session.current = await open({
				backend,
				cwd,
				ask: askPerson,
				onEvent,
				model: model || undefined,
				connection,
				effort,
				resume: sessionId.current, // after a crash or a stall, carry on the same conversation
				onClose: () => {
					session.current = null;
					if (closing.current) {
						closing.current = false; // we closed it ourselves
						return;
					}
					if (modeRef.current !== 'idle') {
						printRows([[], ...outcome('err', label, 'stopped; ask again to continue the same session', w), []]);
						endTurn();
					}
				},
			});
			return session.current;
		} catch (err) {
			printRows([[], ...outcome('err', label, (err as Error).message, w), []]);
			return null;
		}
	}, [askPerson, backend, connection, cwd, effort, endTurn, label, model, onEvent, open, printRows]);

	const closeSession = () => {
		if (!session.current) return;
		closing.current = true;
		session.current.close();
		session.current = null;
	};

	useEffect(() => {
		printRows([
			...b.banner('0.1.0', [['agent', label], ['cwd', tilde(cwd)], ['model', model || 'default'], ['session', 'new']], ['/help lists commands', 'ctrl-o opens a fold', 'ctrl-d leaves'], 'projects from the canon'),
			[],
		]);
		return () => session.current?.close();
	}, []);

	const run = async (line: string) => {
		if (!line) return;
		if (line === '/exit' || line === '/quit') {
			closeSession();
			return exit();
		}
		const n = ++stats.current.turns;
		printRows([b.turnRule(n, w), b.you(line)]);
		last.current = 'rule';
		if (line === '?') return printRows([[], ...KEYS.map(([k, v]) => row('  ', s(k.padEnd(10), 'dim'), s(v, 'muted'))), []]);
		if (line === '/help') return printRows([[], ...b.popupRows(COMMANDS, -1), []]);
		if (line === '/status') {
			return printRows([
				[],
				b.labelled('agent', label),
				b.labelled('model', model || 'default'),
				b.labelled('session', sessionId.current ?? 'not started'),
				b.labelled('cwd', tilde(cwd)),
				b.labelled('turns', `${n - 1}  ${stats.current.tools} tools${stats.current.cost ? `  $${stats.current.cost.toFixed(4)}` : ''}`),
				[],
			]);
		}
		if (line === '/clear') {
			closeSession();
			sessionId.current = undefined;
			return printRows([[], ...outcome('ok', 'new conversation', 'the next message starts a fresh session', w), []]);
		}
		if (line.startsWith('/model')) {
			const name = line.slice('/model'.length).trim();
			if (!name) return printRows([[], ...outcome('warn', 'model', `${model || 'default'} now; /model <name> switches`, w), []]);
			setModel(name);
			await session.current?.setModel(name).catch(() => undefined);
			return printRows([[], ...outcome('ok', 'model', name, w), []]);
		}
		// Anything else, unknown /commands included, goes to the agent: its own commands still work.
		stats.current.turnTools = 0;
		interrupted.current = false;
		lastEvent.current = Date.now();
		setTurnStart(Date.now());
		setVerb('Drafting');
		setMode('turn');
		const ses = await ensureSession();
		if (!ses) return setMode('idle');
		ses.send(line);
	};

	const editor = useLineEditor({
		active: mode !== 'ask',
		commands: COMMANDS,
		onSubmit: line => (mode === 'idle' ? void run(line) : line && setQueue(q => [...q, line])),
		onExit: () => {
			closeSession();
			exit();
		},
	});

	// esc interrupts a turn; ctrl-o opens the last fold.
	useInput(
		(input, key) => {
			if (key.escape && mode === 'turn' && session.current) {
				interrupted.current = true;
				printRows([[], ...outcome('warn', 'interrupted', 'tell the agent what to do instead', w), []]);
				last.current = 'none';
				void session.current.interrupt().catch(() => undefined);
			}
			if (key.ctrl && input === 'o' && fold.current.length) printRows([...fold.current, []]);
		},
		{isActive: mode !== 'ask'},
	);

	// Messages typed during a turn send once it is over.
	useEffect(() => {
		if (mode === 'idle' && queue.length) {
			const [next, ...rest] = queue;
			setQueue(rest);
			void run(next!);
		}
	}, [mode, queue]);

	// The stall watchdog: a turn silent for IDLE_MS, outside an approval, is interrupted.
	useEffect(() => {
		if (mode !== 'turn') return;
		const t = setInterval(() => {
			if (Date.now() - lastEvent.current > IDLE_MS && session.current) {
				printRows([[], ...outcome('warn', `no word from ${label} for ${IDLE_MS / 60000} min`, 'interrupted; ask again to continue', w), []]);
				void session.current.interrupt().catch(() => undefined);
				closeSession(); // the next message resumes the same session
				endTurn();
			}
		}, 5000);
		return () => clearInterval(t);
	}, [mode]);

	const answer = (i: number) => {
		if (!ask) return;
		const a: Answer = i === 0 ? 'yes' : i === 1 ? 'always' : 'no';
		const what = displayName(ask.name);
		printRows([row(s(G.prompt, 'accentText'), ' ', bold(a === 'no' ? 'No' : a === 'always' ? `Yes, and don't ask again for ${what}` : 'Yes'))]);
		last.current = 'tool';
		lastEvent.current = Date.now(); // the watchdog does not count time spent deciding
		if (a === 'no') interrupted.current = true; // a decline ends the turn; that is not a failure
		ask.resolve(a);
		setAsk(null);
		setMode('turn');
	};

	const right = [model || label, tilde(cwd), stats.current.cost ? `$${stats.current.cost.toFixed(4)}` : `${stats.current.turns} turns`].join(' · ');
	const running: Row[] = [...pending.values()].map(p => b.tool(displayName(p.name), toolArgs(p.name, p.input, cwd), 'running'));
	const asking = ask ? askContent(ask.name, ask.input, cwd, w) : null;

	return (
		<>
			<Transcript log={log} />
			{mode !== 'idle' && running.length > 0 && <Lines rows={[[], ...running]} />}
			{mode === 'turn' && (
				<Box flexDirection="column" marginTop={1}>
					<Working verb={verb} since={turnStart} />
				</Box>
			)}
			{mode === 'ask' && ask && asking ? (
				<Box flexDirection="column" marginTop={1}>
					<DialogPicker
						key={ask.name + JSON.stringify(ask.input)}
						title={asking.title}
						body={asking.body}
						options={['Yes', `Yes, and don't ask again for ${displayName(ask.name)} this session`, row('No, and tell the agent what to do differently', '  ', s('esc', 'dim'))]}
						onAnswer={answer}
						w={w}
					/>
					<StatusRow left="enter chooses  1-3 answer  esc declines" right={right} w={w} />
				</Box>
			) : (
				<Box marginTop={1}>
					<Footing
						editor={editor}
						w={w}
						hint={mode === 'turn' ? 'queue a message  it sends after this turn' : `ask ${label} anything  / for commands  ? for keys`}
						left={mode === 'turn' ? `esc interrupts${queue.length ? `  ${queue.length} queued` : ''}` : '? shortcuts'}
						right={right}
					/>
				</Box>
			)}
		</>
	);
}

