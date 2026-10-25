import {describe, expect, it} from 'vitest';
import * as b from '../src/builders.js';
import * as S from '../src/screens.js';
import * as spec from '../src/spec.js';
import {plain, width} from '../src/text.js';
import {CHAPTERS} from '../src/tour/chapters.js';

const MOCKS: Record<string, () => ReturnType<typeof S.banner>> = {
	...Object.fromEntries(Object.entries(S.SCREENS).map(([n, f]) => [`screen ${n}`, f])),
	messages: S.messageTypes,
	grid: S.gridDiagram,
	versus: S.ruleVsCanopy,
	dialog: S.dialogReference,
};

describe('the 80-column grid', () => {
	it.each(Object.keys(MOCKS))('%s: rows fit in 80 and frames are exactly 80', name => {
		for (const r of MOCKS[name]!()) {
			expect(width(r), plain(r)).toBeLessThanOrEqual(80);
			if ('┏┃┗'.includes(plain(r)[0] ?? 'x')) expect(width(r), plain(r)).toBe(80);
		}
	});

	it('turn rule numbers sit flush left', () => {
		expect(plain(b.turnRule(3))).toMatch(/^━━ 03 ━/);
		expect(width(b.turnRule(7, 120))).toBe(120);
	});

	it('frames stretch to the width they are given', () => {
		for (const r of b.dialog('Bash command', ['x'], ['Yes', 'No'], {w: 100})) expect(width(r)).toBe(100);
	});
});

describe('the input box', () => {
	it('stays closed and grows downward when the line wraps', () => {
		const rows = b.inputBox('word '.repeat(40), {w: 60});
		expect(rows.length).toBeGreaterThan(3);
		for (const r of rows) expect(width(r)).toBe(60);
		expect(plain(rows[0]!)[0]).toBe('┏');
		expect(plain(rows.at(-1)!)[0]).toBe('┗');
		expect(plain(rows[2]!)).toMatch(/^┃ {3}\S/); // continuation lines sit two cells in
	});

	it('shows the hint only while empty', () => {
		expect(plain(b.inputLine('', {hint: 'ask'}))).toBe('›  ask');
		expect(plain(b.inputLine('hi', {hint: 'ask'}))).toBe('› hi ');
	});
});

describe('the status row', () => {
	it('drops cwd, then the model, to fit one row', () => {
		const r = plain(b.statusRow('tab next  ←→ cycle  enter create  esc cancel', S.MODEL_LINE));
		expect(r).not.toContain('~/Developer');
		expect(r.endsWith('claude-sonnet-4-5 · ctx 34%  ')).toBe(true);
		expect(r.length).toBe(80);
	});
});

describe('the spec', () => {
	it('has every section', () => {
		const j = spec.asJson();
		expect(Object.keys(j.principles)).toHaveLength(8);
		expect(Object.keys(j.colour.roles)).toHaveLength(8);
		expect(j.screens).toHaveLength(7);
		expect(j.mascot.pixels).toHaveLength(20);
	});

	it('the tour has a chapter per section and per screen', () => {
		expect(CHAPTERS).toHaveLength(19);
		for (const [n, title] of spec.SCREENS) expect(CHAPTERS.some(c => c.title === `Screen ${n} · ${title}`)).toBe(true);
	});
});

describe('word wrap', () => {
	it('keeps two-space facts and breaks between words', async () => {
		const {wrapWords} = await import('../src/text.js');
		expect(wrapWords('▘ Drafting  4s  esc interrupts sits above the box', 30)).toEqual(['▘ Drafting  4s  esc interrupts', 'sits above the box']);
		expect(wrapWords('a\nb', 10)).toEqual(['a', 'b']);
	});
});
