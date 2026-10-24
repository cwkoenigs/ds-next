// The live parts of Rule: the only things that redraw. The spinner line above the footing, the input
// box (closed on all four sides while you type), the slash popup and the dialog that replaces the box.
import {useInput} from 'ink';
import {useEffect, useState} from 'react';
import * as b from '../builders.js';
import type {Content} from '../text.js';
import {SPINNER} from '../tokens.js';
import {Lines} from './Lines.js';

/** ▘ Verb  4s  esc interrupts. The quadrant turns every 160 ms; seconds count from `since`. */
export function Working({verb, since}: {verb: string; since?: number}) {
	const [start] = useState(() => since ?? Date.now());
	const [tick, setTick] = useState(0);
	useEffect(() => {
		const t = setInterval(() => setTick(x => x + 1), SPINNER.intervalMs);
		return () => clearInterval(t);
	}, []);
	const frame = SPINNER.frames[tick % SPINNER.frames.length]!;
	return <Lines rows={[b.working(frame, verb, Math.floor((Date.now() - start) / 1000))]} />;
}

export type Command = readonly [string, string];

export type Editor = {
	value: string;
	at: number;
	/** Commands matching what's typed, while it is a bare /word. */
	items: Command[];
	selected: number;
};

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
	const [st, set] = useState({value: '', at: 0, selected: 0});
	const matching = (v: string) => (v.startsWith('/') && !v.includes(' ') ? commands.filter(([c]) => c.startsWith(v)) : []);
	const items = matching(st.value);

	useInput(
		(input, key) => {
			if (key.return) {
				const line = items.length ? items[Math.min(st.selected, items.length - 1)]![0] : st.value;
				set({value: '', at: 0, selected: 0});
				onSubmit(line.trim());
				return;
			}
			if (key.ctrl && input === 'd') {
				if (!st.value) onExit?.();
				return;
			}
			if (key.tab) {
				if (items.length) {
					const v = items[Math.min(st.selected, items.length - 1)]![0];
					set({value: v, at: v.length, selected: 0});
				}
				return;
			}
			if (key.upArrow || key.downArrow) {
				if (items.length) set(s => ({...s, selected: (s.selected + (key.upArrow ? items.length - 1 : 1)) % items.length}));
				return;
			}
			if (key.escape) {
				set({value: '', at: 0, selected: 0});
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
			if (key.ctrl && input === 'u') return set({value: '', at: 0, selected: 0});
			if (key.ctrl || key.meta || !input) return;
			const text = input.replace(/[\r\n]+/g, ' ');
			set(s => ({value: s.value.slice(0, s.at) + text + s.value.slice(s.at), at: s.at + text.length, selected: 0}));
		},
		{isActive: active},
	);

	return {value: st.value, at: st.at, items, selected: Math.min(st.selected, Math.max(0, items.length - 1))};
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
	const [focus, setFocus] = useState(0);
	const n = options.length;
	useInput(
		(input, key) => {
			if (key.upArrow) setFocus(f => (f + n - 1) % n);
			else if (key.downArrow || key.tab) setFocus(f => (f + 1) % n);
			else if (key.return) onAnswer(focus);
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
