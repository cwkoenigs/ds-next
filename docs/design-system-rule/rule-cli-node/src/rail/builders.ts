// Rail's message types as row builders: ds-next's ui_style.py, ported. Same names where the concept
// is the same (you, run, result, outcome, footer, labelled, hint, fold, error, frame, banner,
// prompt_box → promptBox, toolbar). One rail per turn; a frame means "needs you".
import {bold, type Content, fit, row, type Row, s, type Span, splitAt, truncate, width} from '../text.js';
import {G, GRID, MASCOT, MASCOT_INKS, type RailRole} from './tokens.js';

const W: number = GRID.designWidth;
const cells = (t: string) => width([s(t)]);

/** Text on the brand band (the session tag) and on the key band (the one key to press). */
export const band = (text: string): Span => s(text, 'eye', {bg: 'brand', bold: true});
export const key = (text: string): Span => s(text, 'eye', {bg: 'accent', bold: true});
export const cursor = (ch = ' '): Span => s(ch, undefined, {inverse: true});
/** Inline code in agent text: on the surface. */
export const code = (text: string): Span => s(` ${text} `, undefined, {bg: 'surface'});

/** › what you typed. */
export const you = (line: Content): Row => row(s(G.prompt, 'strong'), ' ', line);

/** ● on the first line, │ on the rest. The lines come wrapped to w − 2 (Markdown is markdown.ts's job). */
export function agent(lines: Content[]): Row[] {
	return lines.map((ln, i) => row(i === 0 ? s(G.agent + ' ', 'accent') : s(G.rail + ' ', 'rule'), ln));
}

/** │ → Tool arg */
export function run(tool: string, arg = ''): Row {
	return row(s(G.rail, 'rule'), ' ', s(G.run, 'muted'), ' ', bold(tool), arg ? [s(' '), s(arg, 'muted')] : '');
}

/** │   ⎿ first  ┄ N more lines · ctrl-o */
export function result(first: string, more = 0, {error = false, key = 'ctrl-o'} = {}): Row {
	return row(
		s(G.rail, 'rule'),
		' '.repeat(GRID.resultIndent - 1),
		s(`${G.result} ${first}`, error ? 'err' : 'dim'),
		more ? s(`  ${G.fold} ${more} more lines${G.sep}${key}`, 'dim') : '',
	);
}

/** ✓ ⚠ ✗ in ok, warn, err: closes a block, never opens one. No rail: local commands are flat. */
export function outcome(kind: 'ok' | 'warn' | 'err', subject: string, detail = ''): Row {
	return row(s(G[kind], kind), ' ', bold(subject), detail ? [s('  '), s(detail, 'muted')] : '');
}

/** ╰ #1 · 2 tool calls · 1.5s · $0.0041 */
export const footer = (...facts: string[]): Row => row(s(G.close, 'rule'), ' ', s(facts.join(G.sep), 'dim'));

/** The one live line: ◐ Thinking · 4s · ctrl-c interrupts. */
export function working(frame: string, step: string, secs: number, keyName = 'ctrl-c'): Row {
	return row(s(frame, 'accent'), ' ', s(step, 'muted'), s(`${G.sep}${secs}s${G.sep}${keyName} interrupts`, 'dim'));
}

export function labelled(label: string, value: Content, {indent = GRID.indent, role = 'dim' as RailRole} = {}): Row {
	return row(' '.repeat(indent), s(label.padEnd(GRID.labelWidth) + ' ', role), value);
}

export const hint = (text: string): Row => [s(' '.repeat(GRID.indent) + text, 'dim')];
export const fold = (text: string): Row => [s(' '.repeat(GRID.indent) + `${G.fold} ${text}`, 'dim')];

/** Red only on the line that failed; the fix follows in dim. */
export function error(what: Content, fix = ''): Row[] {
	return [row(s(G.err, 'err'), ' ', what), ...(fix ? [hint(fix)] : [])];
}

// ── the mascot: the dog and the cat ─────────────────────────────────────────

/** MASCOT as 10 rows of ▀▄█: the top pixel is the foreground, the bottom one the ground. */
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

// ── frames: a frame means "needs you" ────────────────────────────────────────

/** Square frame, exactly `w` wide. kind input → dim edge; approval → warn edge. `keys` sits in the
 *  bottom rule; `prefix` comes before every line (the rail, inside a turn). */
export function frame(
	title: Content,
	rows: (Row | null)[],
	{kind = 'input' as 'input' | 'approval', keys = undefined as Row | undefined, w = W, prefix = [] as Row} = {},
): Row[] {
	const edge: RailRole = kind === 'approval' ? 'warn' : 'dim';
	const iw = w - width(prefix);
	const t = row(title);
	const out: Row[] = [row(prefix, s('┌─ ', edge), t, s(' ' + '─'.repeat(Math.max(0, iw - 5 - width(t))) + '┐', edge))];
	for (const r of rows) out.push(row(prefix, s('│ ', edge), fit(r ?? [], iw - 4), s(' │', edge)));
	out.push(
		keys
			? row(prefix, s('└─ ', edge), keys, s(' ' + '─'.repeat(Math.max(0, iw - 5 - width(keys))) + '┘', edge))
			: row(prefix, s('└' + '─'.repeat(iw - 2) + '┘', edge)),
	);
	return out;
}

/** The approval: a bare rail, then a warn frame on the rail. Only y, a or n answers it. */
export function approval(title: string, detail: string, w = W): Row[] {
	const rows: Row[] = (detail || '(no input)').split('\n').slice(0, 8).map(l => [s(l, 'muted')]);
	const keys = row(key(' y '), s(' yes · ', 'dim'), bold('a'), s(' always this session · ', 'dim'), bold('n'), s(' no', 'dim'));
	return [[s(G.rail, 'rule')], ...frame([s(`Allow ${title}?`, 'warn', {bold: true})], rows, {kind: 'approval', keys, w, prefix: [s(G.rail + ' ', 'rule')]})];
}

/** Where the answer is typed, under the approval: │   › y */
export const answerLine = (typed: Content): Row => row(s(G.rail, 'rule'), ' '.repeat(GRID.resultIndent - 1), you(typed));

/** The two-pane frame shown once: the dog and the cat and the word-mark left, facts right, the
 *  canon's path on a footer row. The one decorative frame: a muted edge and a bright title. */
export function banner(version: string, facts: readonly (readonly [string, string])[], hints: string[], path: string, tagline: string, w = W, art: Row[] = mascotRows()): Row[] {
	const li = GRID.bannerLeft;
	const ri = w - 3 - li;
	const e: RailRole = 'muted';
	const title = row(s('ds-next', 'strong'), s(` ${version}`, 'accent'));
	const out: Row[] = [row(s('┌─ ', e), title, s(' ' + '─'.repeat(li - 3 - width(title)) + '┬' + '─'.repeat(ri) + '┐', e))];
	const left: Row[] = [...art, [], row('  ', s('ds-next', 'strong')), [s('  ' + tagline, 'accent')]];
	const right: Row[] = [[], ...facts.map(([k, v]) => row(s('  ' + k.padEnd(GRID.labelWidth) + ' ', 'accent'), v)), [], ...hints.map(h => [s('  ' + h, 'muted')])];
	for (let i = 0; i < Math.max(left.length, right.length); i++) {
		out.push(row(s('│', e), fit(left[i] ?? [], li), s('│', e), fit(right[i] ?? [], ri), s('│', e)));
	}
	out.push([s('├' + '─'.repeat(li) + '┴' + '─'.repeat(ri) + '┤', e)]);
	const p = truncate([s(path, 'muted')], w - 2);
	const lp = Math.floor((w - 2 - width(p)) / 2);
	out.push(row(s('│', e), ' '.repeat(lp), p, ' '.repeat(w - 2 - lp - width(p)), s('│', e)));
	out.push([s('└' + '─'.repeat(w - 2) + '┘', e)]);
	return out;
}

// ── the prompt: Cortex Code's box ────────────────────────────────────────────

/** The prompt frame at width `w`: rounded, the session tag in the band at the right of the top rule.
 *  The line wraps downward; continuation lines sit under the typed text, two cells in. */
export function promptBox(tag: string, body: Row, w: number): Row[] {
	const t = ` ${tag} `;
	const cw = w - 3; // between "│ " and "│"
	const top = row(s('╭' + '─'.repeat(Math.max(1, w - 4 - cells(t))), 'rule'), band(t), s('──╮', 'rule'));
	let [head, rest] = splitAt(body, cw);
	const lines: Row[] = [head];
	while (rest.length) {
		[head, rest] = splitAt(rest, cw - 2);
		if (!head.length) break; // a character wider than the box; nothing more can fit
		lines.push(row('  ', head));
	}
	return [top, ...lines.map(l => row(s('│ ', 'rule'), fit(l, cw), s('│', 'rule'))), [s('╰' + '─'.repeat(w - 2) + '╯', 'rule')]];
}

/** The line inside the live box: › typed, a cursor, and a dim hint while empty. */
export function promptLine(typed: string, {hint: h = '', at = typed.length} = {}): Row {
	return row(s(G.prompt, 'strong'), ' ', typed.slice(0, at), cursor(typed[at] ?? ' '), typed.slice(at + 1), !typed && h ? s(h, 'dim') : '');
}

/** The box again once the line is accepted, with the line in it: what stays in the scrollback. */
export const promptEcho = (tag: string, text: string, w: number): Row[] => promptBox(tag, you(text), w);

/** The `/` menu, dropping below the box at col 3: command and meta, the current row highlighted. */
export function menu(items: readonly (readonly [string, string])[], selected = 0, w = W, max = 8): Row[] {
	if (!items.length) return [];
	const start = Math.max(0, Math.min(selected - max + 1, items.length - max));
	const metaW = Math.max(...items.map(([, d]) => cells(d)));
	return items.slice(start, start + max).map(([c, d], j) => {
		const on = start + j === selected;
		const cmd = ` ${c.padEnd(20)} `; // ds-next's completer pads the command to 20
		const meta = ` ${d.padEnd(metaW)} `;
		return truncate(on ? row('  ', s(cmd, 'text', {bg: 'hl', bold: true}), s(meta, 'text', {bg: 'hl'})) : row('  ', s(cmd), s(meta, 'muted')), w);
	});
}

/** The status band under the box: one quiet row on the surface, facts left, context right. */
export function toolbar(left: string, right: string, w: number): Row {
	const room = w - 5 - cells(right);
	const l = cells(left) > room ? truncate([s(left)], Math.max(0, room - 1)).map(x => x.text).join('') + '…' : left;
	const gap = Math.max(1, w - cells(l) - cells(right) - 4);
	return truncate([s(`  ${l}${' '.repeat(gap)}${right}  `, 'dim', {bg: 'surface'})], w);
}

/** /help: the command bold, its meaning muted. */
export const commandRows = (items: readonly (readonly [string, string])[]): Row[] => items.map(([c, d]) => row('  ', bold(c.padEnd(14)), s(d, 'muted')));
