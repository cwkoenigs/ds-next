// `rule agent`: a real session with Claude Code or Cortex Code, drawn in Rule or in Rail (--look).
// Each event lands in the transcript once; the live area holds only what is still happening (the
// running tools, the spinner) and the footing. How each thing reads is the look's (looks.tsx).
import {Box, useApp, useInput} from 'ink';
import {useCallback, useEffect, useRef, useState} from 'react';
import {Lines} from '../components/Lines.js';
import {useLineEditor, Working} from '../components/live.js';
import {Transcript, useTranscript} from '../components/transcript.js';
import type {Row} from '../text.js';
import {type AgentSession, type Answer, type Backend, LABELS, type SessionOptions} from './backend.js';
import {type Desk, NO_DESK} from './desk.js';
import type {AgentEvent} from './events.js';
import {type AgentLook, RULE, type Status, tilde} from './looks.js';
import {displayName} from './present.js';

export type Opener = (o: SessionOptions) => Promise<AgentSession>;

const COMMANDS: [string, string][] = [
	['/status', 'Agent, model, session and cost'],
	['/model', 'Switch model: /model <name>'],
	['/last', 'Full output of the last tool call'],
	['/clear', 'Start a new conversation'],
	['/help', 'List commands'],
	['/exit', 'Leave'],
];

/** Silence longer than this, outside an approval, interrupts the turn (as ds-next does). */
export const IDLE_MS = 10 * 60 * 1000;

type Pending = {name: string; input: Record<string, unknown>};
type Ask = {name: string; input: Record<string, unknown>; resolve: (a: Answer) => void};
/** What was printed last, for Rule's rhythm: a blank between messages, none between tools. */
type Last = 'none' | 'text' | 'tool' | 'thought' | 'rule';

export function AgentApp({backend, open, cwd, width, model: initialModel, connection, effort, look = RULE, desk = NO_DESK, label: name}: {
	backend: Backend;
	open: Opener;
	cwd: string;
	width: number;
	model?: string;
	connection?: string;
	effort?: string;
	look?: AgentLook;
	desk?: Desk;
	/** What the agent is called on screen; the backend's name unless given (the demo's scripted agent). */
	label?: string;
}) {
	const {exit} = useApp();
	const cols = Math.max(40, width); // the box and the toolbar
	const w = look.width(width); // everything else
	const label = name ?? LABELS[backend];
	const {log, printRows} = useTranscript();

	const [mode, setModeState] = useState<'idle' | 'turn' | 'ask'>('idle');
	const [pending, setPending] = useState<Map<string, Pending>>(new Map());
	const [step, setStep] = useState('');
	const [ask, setAsk] = useState<Ask | null>(null);
	const [queue, setQueue] = useState<string[]>([]);
	const [model, setModel] = useState(initialModel ?? '');
	const [turnStart, setTurnStart] = useState(Date.now());
	const [where, setWhere] = useState(() => desk.where());

	const session = useRef<AgentSession | null>(null);
	const sessionId = useRef<string | undefined>(undefined);
	const closing = useRef(false);
	const interrupted = useRef(false);
	const last = useRef<Last>('none');
	const lastEvent = useRef(Date.now());
	const lastCtrlC = useRef(0);
	const fold = useRef<Row[]>([]);
	const lastOutput = useRef('');
	const pendingRef = useRef(pending); // written as events arrive, so a result can follow its call in the same tick
	const askChain = useRef<Promise<unknown>>(Promise.resolve());
	const modeRef = useRef(mode);
	const stats = useRef({lines: 0, turns: 0, tools: 0, turnTools: 0, cost: 0});
	/** Mode for the keys and the session's callbacks, current before the next render is. */
	const setMode = (m: 'idle' | 'turn' | 'ask') => {
		modeRef.current = m;
		setModeState(m);
	};

	const status = (): Status => ({
		label,
		cwd,
		model,
		effort,
		cost: stats.current.cost,
		lines: stats.current.lines,
		turns: stats.current.turns,
		queued: queue.length,
		connected: session.current !== null,
		mode,
		where,
		desk,
	});

	/** Print with the look's rhythm. */
	const emit = useCallback(
		(kind: Last, rows: Row[]) => {
			const tight = !look.spaced || (kind === 'tool' && last.current === 'tool') || (kind === 'text' && last.current === 'thought') || last.current === 'rule' || last.current === 'none';
			printRows(tight ? rows : [[], ...rows]);
			last.current = kind;
		},
		[look, printRows],
	);

	const block = useCallback((rows: Row[]) => printRows(look.block(rows)), [look, printRows]);

	const setPendingNow = (m: Map<string, Pending>) => {
		pendingRef.current = m;
		setPending(m);
	};

	const endTurn = useCallback(() => {
		setPendingNow(new Map());
		setMode('idle');
	}, []);

	const nextStep = (e: Parameters<AgentLook['step']>[0]) => {
		const v = look.step(e);
		if (v !== undefined) setStep(v);
	};

	const onEvent = useCallback(
		(e: AgentEvent) => {
			const now = Date.now();
			const since = Math.max(1, (now - lastEvent.current) / 1000);
			lastEvent.current = now;
			switch (e.kind) {
				case 'init':
					sessionId.current = e.sessionId || sessionId.current;
					if (e.model) setModel(e.model);
					nextStep({kind: 'thinking'}); // connected: Rail stops saying "Connecting to"
					return;
				case 'thinking': {
					const t = look.thinking(e.text, since, w);
					if (t.fold) fold.current = t.fold;
					if (t.rows.length) emit('thought', t.rows);
					nextStep({kind: 'thinking'});
					return;
				}
				case 'text':
					emit('text', look.text(e.text, w));
					return;
				case 'tool': {
					stats.current.tools++;
					stats.current.turnTools++;
					nextStep({kind: 'tool', name: e.name});
					setPendingNow(new Map(pendingRef.current).set(e.id, {name: e.name, input: e.input}));
					const rows = look.toolStart(e.name, e.input, cwd, w);
					if (rows.length) emit('tool', rows);
					return;
				}
				case 'toolResult': {
					const p = pendingRef.current.get(e.id);
					if (!p) return;
					const m = new Map(pendingRef.current);
					m.delete(e.id);
					setPendingNow(m);
					lastOutput.current = e.text;
					fold.current = look.output(e.text);
					emit('tool', look.toolEnd(p.name, p.input, cwd, e.text, e.isError, w));
					nextStep({kind: 'toolResult'});
					return;
				}
				case 'result': {
					if (e.costUsd) stats.current.cost += e.costUsd;
					const failure = !e.ok && !interrupted.current ? e.errors.join('; ') || 'the agent reported an error' : undefined;
					printRows(look.ending({n: stats.current.turns, tools: stats.current.turnTools, durationMs: e.durationMs, costUsd: e.costUsd, failure}, w));
					last.current = 'none';
					endTurn();
					return;
				}
				case 'note':
					printRows(look.note(e.text));
					return;
				case 'error':
					block(look.failure(label, e.message, w));
					last.current = 'none';
					endTurn();
					return;
			}
		},
		[block, cwd, emit, endTurn, label, look, printRows, w],
	);

	/** One question at a time: an agent can ask about parallel calls at once, and two prompts on one
	 *  terminal would send an answer to the wrong one. */
	const askPerson = useCallback(
		(name: string, input: Record<string, unknown>) => {
			const answered = askChain.current.then(
				() =>
					new Promise<Answer>(resolve => {
						printRows(look.asking(name, input, w));
						setAsk({name, input, resolve});
						setMode('ask');
					}),
			);
			askChain.current = answered.catch(() => undefined);
			return answered;
		},
		[look, printRows, w],
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
						block(look.failure(label, 'stopped; ask again to continue the same session', w));
						endTurn();
					}
				},
			});
			return session.current;
		} catch (err) {
			block(look.failure(label, (err as Error).message, w));
			return null;
		}
	}, [askPerson, backend, block, connection, cwd, effort, endTurn, label, look, model, onEvent, open, w]);

	const closeSession = () => {
		if (!session.current) return;
		closing.current = true;
		session.current.close();
		session.current = null;
	};

	const leave = () => {
		closeSession();
		exit();
	};

	useEffect(() => {
		printRows(look.banner(status(), cols));
		return () => session.current?.close();
	}, []);

	// The toolbar's "where": this repo against the canon, read again whenever the box comes back.
	useEffect(() => {
		if (mode === 'idle') setWhere(desk.where());
	}, [mode]);

	const run = async (line: string) => {
		if (!line) return;
		if (line === '/exit' || line === '/quit') return leave();
		stats.current.lines++;
		printRows(look.accepted(line, status(), cols, w));
		last.current = 'rule';
		if (line === '?') return block(look.keys());
		if (line === '/help') return block(look.help(COMMANDS, label));
		if (line === '/status') {
			const s = stats.current;
			return block([
				look.labelled('agent', label),
				look.labelled('model', model || 'default'),
				...(effort ? [look.labelled('effort', effort)] : []),
				look.labelled('session', sessionId.current ?? 'not started'),
				look.labelled('cwd', tilde(cwd)),
				look.labelled('turns', [String(s.turns), `${s.tools} tools`, ...(s.cost ? [`$${s.cost.toFixed(4)}`] : [])].join(look.sep)),
			]);
		}
		if (line === '/last') return block(lastOutput.current ? look.output(lastOutput.current) : look.hint('no tool output yet'));
		if (line === '/clear') {
			closeSession();
			sessionId.current = undefined;
			stats.current.turns = 0;
			return block(look.outcome('ok', 'new conversation', 'the next message starts a fresh session', w));
		}
		if (line.startsWith('/model')) {
			const name = line.slice('/model'.length).trim();
			if (!name) return block(look.outcome('warn', 'model', `${model || 'default'} now; /model <name> switches`, w));
			setModel(name);
			await session.current?.setModel(name).catch(() => undefined);
			return block(look.outcome('ok', 'model', name, w));
		}
		// Anything else, unknown /commands included, goes to the agent: its own commands still work.
		printRows(look.turnStart(++stats.current.turns));
		stats.current.turnTools = 0;
		interrupted.current = false;
		lastEvent.current = Date.now();
		setTurnStart(Date.now());
		nextStep({kind: 'start', connected: session.current !== null, label});
		setMode('turn');
		const ses = await ensureSession();
		if (!ses) return setMode('idle');
		ses.send(line);
	};

	const editor = useLineEditor({
		active: mode !== 'ask',
		commands: COMMANDS,
		onSubmit: line => (modeRef.current === 'idle' ? void run(line) : line && setQueue(q => [...q, line])),
		onExit: leave,
	});

	const interrupt = () => {
		if (modeRef.current !== 'turn' || !session.current) return;
		interrupted.current = true;
		printRows(look.interrupted(Math.floor((Date.now() - turnStart) / 1000), w));
		last.current = 'none';
		void session.current.interrupt().catch(() => undefined);
	};

	// esc interrupts a turn; ctrl-o opens the last fold; ctrl-c is the look's (Rail: ds-next's habit,
	// one interrupts or clears the line, a second within two seconds leaves).
	useInput(
		(input, key) => {
			if (key.ctrl && input === 'c') {
				if (look.ctrlC === 'exit') return leave();
				if (modeRef.current === 'turn') return interrupt();
				const now = Date.now();
				if (now - lastCtrlC.current < 2000) return leave();
				lastCtrlC.current = now;
				editor.clear();
				printRows(look.hint('ctrl-c again to leave · or /exit'));
				return;
			}
			if (key.escape && modeRef.current === 'turn') interrupt();
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
				block(look.outcome('warn', `no word from ${label} for ${IDLE_MS / 60000} min`, 'interrupted; ask again to continue', w));
				void session.current.interrupt().catch(() => undefined);
				closeSession(); // the next message resumes the same session
				endTurn();
			}
		}, 5000);
		return () => clearInterval(t);
	}, [mode]);

	const answer = (a: Answer, typed: string) => {
		if (!ask) return;
		printRows(look.answered(a, typed, displayName(ask.name)));
		last.current = 'tool';
		lastEvent.current = Date.now(); // the watchdog does not count time spent deciding
		if (a === 'no') interrupted.current = true; // a decline ends the turn; that is not a failure
		ask.resolve(a);
		setAsk(null);
		setMode('turn');
	};

	const st = status();
	const running = [...pending.values()].map(p => look.toolRunning(p.name, p.input, cwd)).filter((x): x is Row => x !== null);
	const gap = look.spaced ? 1 : 0;

	return (
		<>
			<Transcript log={log} />
			{mode !== 'idle' && running.length > 0 && <Lines rows={[[], ...running]} />}
			{mode === 'turn' && (
				<Box flexDirection="column" marginTop={gap}>
					<Working verb={step} since={turnStart} spinner={look.spinner} draw={look.working} />
				</Box>
			)}
			{mode === 'ask' && ask ? (
				<Box flexDirection="column" marginTop={gap}>
					<look.Approval key={ask.name + JSON.stringify(ask.input)} name={ask.name} input={ask.input} cwd={cwd} w={w} status={st} onAnswer={answer} />
				</Box>
			) : (
				<Box flexDirection="column" marginTop={mode === 'turn' ? 1 - gap : 0}>
					<Lines rows={look.footing(editor, st, cols, w)} />
				</Box>
			)}
		</>
	);
}
