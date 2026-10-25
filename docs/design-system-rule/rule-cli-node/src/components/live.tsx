// The live parts of Rule: the only things that redraw. The spinner line above the footing, the input
// box (closed on all four sides while you type), the slash popup and the dialog that replaces the box.
import {useInput} from 'ink';
import {useEffect, useRef, useState} from 'react';
import * as b from '../builders.js';
import type {Content, Row} from '../text.js';
import {SPINNER} from '../tokens.js';
import {Lines} from './Lines.js';

type Spinner = {readonly frames: readonly string[]; readonly intervalMs: number};

/** ▘ Verb  4s  esc interrupts. The quadrant turns every 160 ms; seconds count from `since`. Another
 *  look passes its own spinner and line (Rail: ◐ Thinking · 4s · ctrl-c interrupts, every 125 ms). */
export function Working({verb, since, spinner = SPINNER, draw = b.working}: {verb: string; since?: number; spinner?: Spinner; draw?: (frame: string, verb: string, secs: number) => Row}) {
	const [start] = useState(() => since ?? Date.now());
	const [tick, setTick] = useState(0);
	useEffect(() => {
		const t = setInterval(() => setTick(x => x + 1), spinner.intervalMs);
		return () => clearInterval(t);
	}, [spinner.intervalMs]);
	const frame = spinner.frames[tick % spinner.frames.length]!;
	return <Lines rows={[draw(frame, verb, Math.floor((Date.now() - start) / 1000))]} />;
}

export type Command = readonly [string, string];

export type Editor = {
	value: string;
	at: number;
	/** Commands matching what's typed, while it is a bare /word. */
	items: Command[];
	selected: number;
	/** Empty the line (Rail's first ctrl-c). */
	clear: () => void;
};

type Line = {value: string; at: number; selected: number};
const EMPTY: Line = {value: '', at: 0, selected: 0};

/** Line editing for the input box: typing, ←→, backspace, ctrl-a/e/u, and the slash popup (↑↓, tab). */
export function useLineEditor({
	active = true,
	commands = [],
	onSubmit,
	onExit,
}: {
	active?: boolean;
	commands?: readonly Command[];
	onSubmit: (line: string) => void;
	onExit?: () => void;
}): Editor {
	const [st, setSt] = useState<Line>(EMPTY);
	// Keys read and write the line here, not in `st`: a key can arrive before the render that follows
	// the one before it (fast typing, a busy machine), and Ink would hand it to the handler from an
	// older render, which would see an older line. Enter would then send what was there before.
	const cur = useRef<Line>(EMPTY);
	const handlers = useRef({onSubmit, onExit});
	handlers.current = {onSubmit, onExit};
	const set = (next: Line | ((s: Line) => Line)) => {
		cur.current = typeof next === 'function' ? next(cur.current) : next;
		setSt(cur.current);
	};
	const matching = (v: string) => (v.startsWith('/') && !v.includes(' ') ? commands.filter(([c]) => c.startsWith(v)) : []);
	const items = matching(st.value);

	useInput(
		(input, key) => {
			const now = cur.current;
			const shown = matching(now.value);
			const pick = () => shown[Math.min(now.selected, shown.length - 1)]![0];
			if (key.return) {
				const line = shown.length ? pick() : now.value;
				set(EMPTY);
				handlers.current.onSubmit(line.trim());
				return;
			}
			if (key.ctrl && input === 'd') {
				if (!now.value) handlers.current.onExit?.();
				return;
			}
			if (key.tab) {
				if (shown.length) {
					const v = pick();
					set({value: v, at: v.length, selected: 0});
				}
				return;
			}
			if (key.upArrow || key.downArrow) {
				if (shown.length) set(s => ({...s, selected: (s.selected + (key.upArrow ? shown.length - 1 : 1)) % shown.length}));
				return;
			}
			if (key.escape) {
				set(EMPTY);
				return;
			}
			// Many terminals send DEL (0x7f) for the backspace key, which Ink reports as `delete`.
			if (key.backspace || key.delete) {
				set(s => (s.at ? {value: s.value.slice(0, s.at - 1) + s.value.slice(s.at), at: s.at - 1, selected: 0} : s));
				return;
			}
			if (key.leftArrow) return set(s => ({...s, at: Math.max(0, s.at - 1)}));
			if (key.rightArrow) return set(s => ({...s, at: Math.min(s.value.length, s.at + 1)}));
			if (key.ctrl && input === 'a') return set(s => ({...s, at: 0}));
			if (key.ctrl && input === 'e') return set(s => ({...s, at: s.value.length}));
			if (key.ctrl && input === 'u') return set(EMPTY);
			if (key.ctrl || key.meta || !input) return;
			const text = input.replace(/[\r\n]+/g, ' ');
			set(s => ({value: s.value.slice(0, s.at) + text + s.value.slice(s.at), at: s.at + text.length, selected: 0}));
		},
		{isActive: active},
	);

	return {value: st.value, at: st.at, items, selected: Math.min(st.selected, Math.max(0, items.length - 1)), clear: () => set(EMPTY)};
}

/** The pinned box, closed while you type; a long line wraps and the box grows downward. */
export const InputBox = ({value, at, hint, w}: {value: string; at?: number; hint?: string; w?: number}) => (
	<Lines rows={b.inputBox(value, {hint, at, w})} />
);

/** The whole footing: box, popup when / is typed, then the bare status row. */
export function Footing({editor, hint, left, right, w}: {editor: Editor; hint?: string; left: string; right: string; w?: number}) {
	const popup = editor.items.length > 0;
	return (
		<Lines
			rows={[
				...b.inputBox(editor.value, {hint, at: editor.at, w}),
				...b.popupRows(editor.items, editor.selected),
				b.statusRow(popup ? '↑↓ move  tab complete  esc close' : left, right, w),
			]}
		/>
	);
}

/** A live dialog: ↑↓ move the ■, a number answers, enter takes the focus, esc takes the last option. */
export function DialogPicker({
	title,
	body,
	options,
	onAnswer,
	w,
	active = true,
}: {
	title: string;
	body: Content[];
	options: Content[];
	onAnswer: (index: number) => void;
	w?: number;
	active?: boolean;
}) {
	const [focus, setFocusState] = useState(0);
	const cur = useRef(0); // read by the keys: see useLineEditor
	const setFocus = (f: (x: number) => number) => setFocusState((cur.current = f(cur.current)));
	const n = options.length;
	useInput(
		(input, key) => {
			if (key.upArrow) setFocus(f => (f + n - 1) % n);
			else if (key.downArrow || key.tab) setFocus(f => (f + 1) % n);
			else if (key.return) onAnswer(cur.current);
			else if (key.escape) onAnswer(n - 1);
			else {
				const d = Number(input);
				if (Number.isInteger(d) && d >= 1 && d <= n) onAnswer(d - 1);
			}
		},
		{isActive: active},
	);
	return <Lines rows={b.dialog(title, body, options, {focus, w})} />;
}
