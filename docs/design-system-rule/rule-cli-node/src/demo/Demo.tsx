// A live session drawn in Rule. The agent is faked; everything you see and press is the real UI:
// the closed input box, the slash popup, a turn that plays and lands, the approval dialog.
import {Box, useApp} from 'ink';
import {homedir} from 'node:os';
import {useEffect, useRef, useState} from 'react';
import * as b from '../builders.js';
import {Lines} from '../components/Lines.js';
import {LiveTurn} from '../components/LiveTurn.js';
import {DialogPicker, Footing, useLineEditor} from '../components/live.js';
import {StatusRow} from '../components/rule.js';
import {Transcript, useTranscript} from '../components/transcript.js';
import * as S from '../screens.js';
import {bold, row, type Row, s} from '../text.js';
import {G, GRID} from '../tokens.js';

const COMMANDS: [string, string][] = [
	['/new', 'Start a project from the canon'],
	...S.COMMANDS,
	['/help', 'List commands'],
	['/exit', 'Leave'],
];

const SHORTCUTS: [string, string][] = [
	['/', 'commands; ↑↓ move, tab completes'],
	['enter', 'send; while a turn runs, it queues'],
	['esc', 'interrupt a turn; clear the box'],
	['←→ ctrl-a ctrl-e', 'move in the line'],
	['ctrl-u', 'clear the line'],
	['ctrl-d', 'leave (on an empty box)'],
];

type Mode = 'idle' | 'turn' | 'ask';

function cwd(): string {
	const here = process.cwd();
	const home = homedir();
	return here.startsWith(home) ? '~' + here.slice(home.length) : here;
}

export function Demo({width, fast = false}: {width: number; fast?: boolean}) {
	const {exit} = useApp();
	const w = Math.max(GRID.minWidth, width);
	const {log, printRows} = useTranscript();
	const [mode, setMode] = useState<Mode>('idle');
	const [queue, setQueue] = useState<string[]>([]);
	const turns = useRef(0);
	const right = `claude-sonnet-4-5 · ${cwd()} · ctx ${34 + 3 * turns.current}%`;

	useEffect(() => printRows([...S.bannerRows(), []]), []); // the banner, once

	const run = (line: string) => {
		if (!line) return;
		if (line === '/exit' || line === '/quit') return exit();
		const n = ++turns.current;
		const head = [b.turnRule(n, w), b.you(line), [] as Row];
		if (line === '?') {
			return printRows([...head, ...SHORTCUTS.map(([k, v]) => row('  ', s(k.padEnd(18), 'dim'), s(v, 'muted'))), []]);
		}
		if (line === '/help' || line === '/') return printRows([...head, ...b.popupRows(COMMANDS, -1), []]);
		if (line.startsWith('/new')) return printRows([...head, ...S.newFormFrame(), [], S.created(), []]);
		if (line === '/status') return printRows([...head, ...S.statusBody(), []]);
		if (line === '/standards') {
			return printRows([...head, ...['python-package', 'cli-ux', 'logging', 'testing', 'security', 'docs'].map(x => b.outcome(x === 'security' ? 'warn' : 'ok', x)), b.facts('6 of 16 apply here'), []]);
		}
		if (line === '/skills') return printRows([...head, ...['so-build-feature-interview', 'so-bug-review-interview', 'so-best-practice-audit', 'so-capture', 'so-changes'].map(x => b.outcome('ok', x)), b.facts('5 from skills-os'), []]);
		if (line === '/scaffold') return printRows([...head, b.outcome('ok', 'python-cli v1', 're-applied  0 files changed'), []]);
		if (line.startsWith('/')) return printRows([...head, b.outcome('err', line, 'not a command  /help lists them'), []]);
		printRows(head);
		setMode('turn');
	};

	const editor = useLineEditor({
		active: mode !== 'ask',
		commands: COMMANDS,
		onSubmit: line => (mode === 'turn' ? line && setQueue(q => [...q, line]) : run(line)),
		onExit: exit,
	});

	// Messages typed during a turn send once it is over.
	useEffect(() => {
		if (mode === 'idle' && queue.length) {
			const [next, ...rest] = queue;
			setQueue(rest);
			run(next!);
		}
	}, [mode, queue]);

	const answer = (i: number) => {
		const yes = i < 2;
		printRows([row(s(G.prompt, 'accentText'), ' ', bold(yes ? 'Yes' : 'No'))]);
		if (yes) {
			printRows([b.tool('Bash', 'uv run pytest -q'), ...b.result('13 passed in 1.42s', 11), [], ...S.summary(), []]);
		} else {
			printRows([b.outcome('warn', 'declined', 'tell ds-next what to do differently'), []]);
		}
		setMode('idle');
	};

	return (
		<>
			<Transcript log={log} />
			{mode === 'turn' && (
				<LiveTurn
					fast={fast}
					printRows={printRows}
					onDone={interrupted => {
						if (interrupted) return setMode('idle');
						printRows([...S.approvalAsk(), []]);
						setMode('ask');
					}}
				/>
			)}
			{mode === 'ask' ? (
				<Box flexDirection="column">
					<Lines rows={[b.tool('Bash', 'uv run pytest -q', 'running'), []]} />
					<DialogPicker title="Bash command" body={[[bold('uv run pytest -q')], [s('Run the test suite to check the new flag', 'muted')]]} options={S.APPROVAL_OPTIONS} onAnswer={answer} w={w} />
					<StatusRow left="enter chooses  1-3 answer  esc declines" right={right} w={w} />
				</Box>
			) : (
				<Footing
					editor={editor}
					w={w}
					hint={mode === 'turn' ? 'queue a message  it sends after this turn' : 'ask a question  / for commands  ? for keys'}
					left={mode === 'turn' ? `esc interrupts${queue.length ? `  ${queue.length} queued` : ''}` : '? shortcuts'}
					right={right}
				/>
			)}
		</>
	);
}
