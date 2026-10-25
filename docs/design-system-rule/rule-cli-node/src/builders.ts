// Rule's message types as row builders. Same names as ui_style.py where the concept is the same.
// Every frame is exactly `w` cells wide; every other row fits inside it.
import {bold, type Content, fit, row, type Row, s, type Span, splitAt, width, wrapWords} from './text.js';
import {G, GRID, MASCOT, MASCOT_INKS, type Role, VERBS} from './tokens.js';

const W: number = GRID.designWidth;
const SEP = GRID.factSep;
const pad2 = (n: number) => String(n).padStart(2, '0');

export const verb = (): string => VERBS[Math.floor(Math.random() * VERBS.length)]!;

/** ━━ 03 ━━━… opens every prompt; the number is flush left. */
export function turnRule(n: number, w = W): Row {
	return [s(G.h.repeat(2) + ' ', 'rule'), bold(pad2(n), 'muted'), s(' ' + G.h.repeat(w - 6), 'rule')];
}

/** › what you typed, echoed flat under the turn rule. */
export function you(line: Content): Row {
	return row(s(G.prompt, 'accentText'), ' ', line);
}

/** ■ on the first line, col 3 for the rest. A string is word-wrapped to the text column;
 *  an array is taken as lines already wrapped (each a row or a string). */
export function agent(body: string | Content[], w = W): Row[] {
	const lines = typeof body === 'string' ? wrapWords(body, w - GRID.indent) : body;
	return lines.map((ln, i) => row(i === 0 ? s(G.agent, 'accent') : ' ', ' ', ln));
}

/** A Markdown heading inside agent text: uppercase, bold, col 3. */
export function heading(text: string): Row {
	return [bold(' '.repeat(GRID.indent) + text.toUpperCase())];
}

export type ToolState = 'running' | 'done' | 'failed';

export function tool(name: string, args = '', state: ToolState = 'done'): Row {
	const [glyph, role]: [string, Role] =
		state === 'running' ? [G.pending, 'dim'] : state === 'failed' ? [G.tool, 'accent'] : [G.tool, 'text'];
	return row(s(glyph, role), ' ', bold(name), args ? s(' ' + args, 'muted') : '');
}

export function result(first: string, more = 0, {error = false, key = 'ctrl-o'} = {}): Row[] {
	const out = [row(' '.repeat(GRID.indent), s(`${G.result} ${first}`, error ? 'accentText' : 'dim'))];
	if (more) out.push(row(' '.repeat(GRID.resultIndent), s(`${G.result} ${more} more lines${SEP}${key}`, 'dim')));
	return out;
}

export function thinking(line: string, first = false): Row {
	return [s((first ? G.think + ' ' : '  ') + line, 'dim')];
}

export function thought(secs: number, key = 'ctrl-o'): Row {
	return [s(`${G.think} Thought for ${Math.round(secs)}s${SEP}${key}`, 'dim')];
}

/** ok → ink; warn → accent; err → accent text. Colour means "needs you", not "kind". */
export function outcome(kind: 'ok' | 'warn' | 'err', subject: string, detail = ''): Row {
	const role: Role = kind === 'ok' ? 'text' : kind === 'warn' ? 'accent' : 'accentText';
	return row(s(G[kind], role), ' ', bold(subject), detail ? [s(SEP), s(detail, 'muted')] : '');
}

/** Dim fact row: `3 tools  15.2s  $0.0041`. */
export function facts(...items: string[]): Row {
	return [s(' '.repeat(GRID.indent) + items.join(SEP), 'dim')];
}

/** The one live line: ▘ Drafting  4s  esc interrupts. */
export function working(frame: string, v: string, secs: number): Row {
	return [s(frame, 'accent'), s(' '), s(v, 'accent'), s(`${SEP}${secs}s${SEP}esc interrupts`, 'dim')];
}

export function labelled(label: string, value: Content, {upper = false} = {}): Row {
	const lab = (upper ? label.toUpperCase() : label).padEnd(GRID.labelWidth);
	return row(' '.repeat(GRID.indent), s(lab + ' ', 'dim'), value);
}

/** Inline code and file chips: the text on the surface role. */
export const code = (text: string): Span => s(` ${text} `, undefined, {bg: 'surface'});
export const cursor = (ch = ' '): Span => s(ch, undefined, {inverse: true});

// ── frames: heavy, square, title flush left ──────────────────────────────────

export function frame(rows: (Row | null)[], {edge = 'rule' as Role, title = undefined as Row | undefined, w = W} = {}): Row[] {
	const iw = w - 2;
	const top = title
		? row(s(G.tl + G.h + ' ', edge), title, s(' ' + G.h.repeat(Math.max(0, iw - 3 - width(title))) + G.tr, edge))
		: [s(G.tl + G.h.repeat(iw) + G.tr, edge)];
	const body = rows.map(r => row(s(G.v + ' ', edge), fit(r ?? [], iw - 1), s(G.v, edge)));
	return [top, ...body, [s(G.bl + G.h.repeat(iw) + G.br, edge)]];
}

/** The text inside the input box: › typed, a cursor, and a dim hint while empty. */
export function inputLine(typed: string, {hint = '', at = typed.length} = {}): Row {
	const ch = typed[at] ?? ' ';
	return row(
		s(G.prompt, 'accentText'),
		' ',
		typed.slice(0, at),
		cursor(ch),
		typed.slice(at + 1),
		!typed && hint ? s(hint, 'dim') : '',
	);
}

/** The pinned input box, closed on all four sides. It grows downward when the line wraps;
 *  continuation lines sit under the typed text, two cells in. */
export function inputBox(typed: string, {hint = '', at = typed.length, w = W} = {}): Row[] {
	const inner = w - 3; // frame content width
	let [head, rest] = splitAt(inputLine(typed, {hint, at}), inner);
	const rows: Row[] = [head];
	while (rest.length) {
		[head, rest] = splitAt(rest, inner - 2);
		if (!head.length) break; // a character wider than the box; nothing more can fit
		rows.push(row('  ', head));
	}
	return frame(rows, {w});
}

/** Red heavy frame, uppercase title, ■ on the focused option, □ on the rest, esc = the last option. */
export function dialog(title: string, body: Content[], options: Content[], {focus = 0, question = 'PROCEED?', w = W} = {}): Row[] {
	const rows: (Row | null)[] = body.map(b => row(b));
	rows.push(null, [bold(question)]);
	options.forEach((o, i) => {
		const on = i === focus;
		rows.push(row(on ? s(G.agent, 'accentText') : s(G.option, 'dim'), ' ', on ? bold(String(i + 1)) : s(String(i + 1), 'muted'), SEP, o));
	});
	return frame(rows, {edge: 'accent', title: [bold(title.toUpperCase(), 'accent')], w});
}

/** The bare row under the box: keys dim on the left, facts muted on the right. Drops cwd, then model, to fit. */
export function statusRow(left: string, right: string, w = W): Row {
	const parts = right.split(' · ');
	while (parts.length > 1 && left.length + parts.join(' · ').length + 6 > w) parts.splice(parts.length === 2 ? 0 : 1, 1);
	const r = parts.join(' · ');
	const gap = Math.max(1, w - left.length - r.length - 4);
	const out: Row = [s('  '), s(left, 'dim'), s(' '.repeat(gap))];
	parts.forEach((p, i) => {
		if (i) out.push(s(' · ', 'dim'));
		out.push(s(p, 'muted'));
	});
	out.push(s('  '));
	return out;
}

/** The slash popup: ■ follows the selection. */
export function popupRows(items: readonly (readonly [string, string])[], selected = 0): Row[] {
	return items.map(([cmd, desc], i) =>
		i === selected
			? [s(' '), s(G.agent, 'accentText'), s(' '), bold(cmd.padEnd(14)), s(desc, 'muted')]
			: [s('   ' + cmd.padEnd(14)), s(desc, 'dim')],
	);
}

// ── banner + mascot ──────────────────────────────────────────────────────────

export function mascotRows(): Row[] {
	const out: Row[] = [];
	for (let y = 0; y < MASCOT.length; y += 2) {
		const top = MASCOT[y]!;
		const bot = MASCOT[y + 1]!;
		const r: Row = [];
		for (let x = 0; x < top.length; x++) {
			const a = MASCOT_INKS[top[x]!];
			const b = MASCOT_INKS[bot[x]!];
			if (!a && !b) r.push(s(' '));
			else if (a === b) r.push(s('█', a));
			else if (a && b) r.push(s('▀', a, {bg: b}));
			else if (a) r.push(s('▀', a));
			else r.push(s('▄', b));
		}
		out.push(r);
	}
	return out;
}

/** The heavy two-pane frame shown once. Word-mark and labels uppercase, flush left. */
export function banner(version: string, facts_: [string, string][], hints: string[], tagline: string, w = W): Row[] {
	const li = 30;
	const ri = w - 3 - li;
	const title = row(bold('DS-NEXT'), s(` ${version}`, 'dim'));
	const out: Row[] = [
		row(s(G.tl + G.h + ' ', 'rule'), title, s(' ' + G.h.repeat(li - 3 - width(title)) + G.teeDown + G.h.repeat(ri) + G.tr, 'rule')),
	];
	const left: Row[] = [...mascotRows().map(m => row(' ', m)), [], [bold(' DS-NEXT')], [s(' ' + tagline, 'muted')]];
	const right: Row[] = [
		[],
		...facts_.map(([k, v]) => row(s('  ' + k.toUpperCase().padEnd(10), 'dim'), v)),
		[],
		...hints.map(h => [s('  ' + h, 'dim')]),
	];
	for (let i = 0; i < Math.max(left.length, right.length); i++) {
		out.push(row(s(G.v, 'rule'), fit(left[i] ?? [], li), s(G.v, 'rule'), fit(right[i] ?? [], ri), s(G.v, 'rule')));
	}
	out.push([s(G.bl + G.h.repeat(li) + G.teeUp + G.h.repeat(ri) + G.br, 'rule')]);
	return out;
}
