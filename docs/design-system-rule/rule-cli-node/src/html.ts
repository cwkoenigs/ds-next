// `rule html`: the tour as one self-contained web page, readable on a phone. Mockups are the same
// rows the terminal draws, coloured from the palette; the prose comes from spec.ts.
import * as S from './screens.js';
import * as spec from './spec.js';
import {makeTheme, resolve} from './theme.js';
import {fit, type Row} from './text.js';
import {GRID, PALETTE, type ThemeName} from './tokens.js';
import {PAGE} from './html-page.js';
import {landedTurn} from './tour/chapters.js';

const esc = (t: string) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function rowHtml(r: Row, name: ThemeName): string {
	const theme = makeTheme(name, 'hex', true);
	return fit(r, GRID.designWidth)
		.map(sp => {
			let {color, backgroundColor, bold, inverse} = resolve(theme, sp);
			if (inverse) [color, backgroundColor] = [backgroundColor, color];
			const style = [color && `color:${color}`, backgroundColor && `background:${backgroundColor}`, bold && 'font-weight:bold'].filter(Boolean).join(';');
			return `<span style="${style}">${esc(sp.text)}</span>`;
		})
		.join('');
}

function mock(rows: Row[], name: ThemeName): string {
	const {bg, text} = PALETTE[name];
	return `<pre class="term" data-t="${name}" style="background:${bg};color:${text}">${rows.map(r => rowHtml(r, name)).join('\n')}</pre>`;
}

function mocks(rows: () => Row[], caption = ''): string {
	const cap = caption ? `<p class="cap">${esc(caption)}</p>` : '';
	return `<figure class="mock">${cap}<div class="scroll">${mock(rows(), 'dark')}${mock(rows(), 'light')}</div></figure>`;
}

const p = (t: string, cls = '') => (cls ? `<p class="${cls}">${esc(t)}</p>` : `<p>${esc(t)}</p>`);
const dl = (items: readonly (readonly [string, string])[]) =>
	'<dl class="pairs">' + items.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('') + '</dl>';
const ul = (items: string[]) => "<ul class='rules'>" + items.map(x => `<li>${esc(x)}</li>`).join('') + '</ul>';

/** Cells are escaped unless their column index is in `raw`. */
function table(head: string[], rows: string[][], raw = new Set<number>()): string {
	const th = head.map(h => `<th>${esc(h)}</th>`).join('');
	const tr = rows.map(r => '<tr>' + r.map((c, i) => `<td>${raw.has(i) ? c : esc(c)}</td>`).join('') + '</tr>').join('');
	return `<div class="scroll"><table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table></div>`;
}

export function build(): string {
	const secs: [anchor: string, title: string, body: string][] = [];
	const sw = (h: string) => `<span class="sw" style="background:${h}"></span><code>${h}</code>`;

	secs.push(['rule', 'Rule', p(spec.SUMMARY, 'lede') + dl(spec.ASSUMPTIONS)]);
	secs.push(['versus', 'Canopy vs Rule',
		p('The same turn. Canopy is warm and rounded; Rule is ink, red and square, with a numbered rule opening each turn.') +
		mocks(S.ruleVsCanopy, '1b · Rule') +
		table(['Canopy', 'Rule'], spec.CHANGES_FROM_CANOPY.map(r => [...r]))]);
	secs.push(['principles', 'Principles',
		'<ol class="principles">' + spec.PRINCIPLES.map(([t, x]) => `<li><h3>${esc(t)}</h3><p>${esc(x)}</p></li>`).join('') + '</ol>']);
	secs.push(['colour', 'Colour roles',
		p('Eight roles, both from Modernist\'s ramps. The dark theme inverts the page. There is no ok/warn/err triad: done is text, warn and err are red (err bold).') +
		table(['Role', 'Dark', 'Token', 'Light', 'Token', 'Used for'], spec.COLOURS.map(([r, d, dt, l, lt, use]) => [r, sw(d), dt, sw(l), lt, use]), new Set([1, 3])) +
		p('ANSI-16: ' + Object.entries(spec.asJson().colour.ansi16).filter(([, v]) => v).map(([k, v]) => `${k} ${v}`).join('  '), 'small') +
		ul(spec.COLOUR_RULES)]);
	secs.push(['glyphs', 'Glyph vocabulary',
		table(['Glyph', 'Name', 'Means', 'Colour', 'Column'], spec.GLYPHS.map(([g, n, m, c, col]) => [`<span class="g">${esc(g)}</span>`, esc(n), esc(m), esc(c), esc(col)]), new Set([0, 1, 2, 3, 4])) +
		p(`Not used: ${spec.RETIRED.join(', ')}. The three systems never share a screen.`, 'small')]);
	secs.push(['grid', 'Grid and the footing',
		mocks(S.gridDiagram, '5a · the 80-column grid') + dl(spec.GRID_NOTES) +
		dl([['Design width', String(GRID.designWidth)], ['Min width', String(GRID.minWidth)], ['Indent', String(GRID.indent)],
			['Result indent', String(GRID.resultIndent)], ['Label width', String(GRID.labelWidth)], ['Fact separator', 'two spaces']]) +
		p(spec.CASE)]);
	secs.push(['messages', 'Every message type', mocks(S.messageTypes, '6 · message types')]);
	secs.push(['dialogs', 'Dialogs', p('Heavy frame, red edge while asking, uppercase title flush left, numbered options with ■ on the focus and □ on the rest.') + mocks(S.dialogReference, '7 · permission')]);
	secs.push(['motion', 'Motion',
		'<div class="live" aria-hidden="true"><span class="q">▘</span> <span class="v">Drafting</span><span class="d">  <span class="s">0</span>s  esc interrupts</span></div>' +
		dl(spec.MOTION) + p(`Spinner verbs: ${spec.VERBS.join(' · ')}`, 'small') +
		mocks(() => [...S.echo(2, 'add a --since flag to the metrics command'), ...landedTurn()], 'a turn, landed')]);
	secs.push(['mascot', 'Mascot', p(spec.MASCOT_NOTE) + mocks(S.mascot, 'canoe · 28×20 px in half-blocks')]);
	secs.push(['code', 'Where it lands in code', table(['Token / helper', 'In this package', 'Differs from Canopy'], spec.CODE_MAP.map(r => [...r]))]);
	for (const [n, title, note] of spec.SCREENS) secs.push([`screen-${n}`, `Screen ${n} · ${title}`, p(note) + mocks(S.SCREENS[n]!)]);
	secs.push(['gaps', 'Known gaps', ul(spec.KNOWN_GAPS)]);

	const toc = secs.map(([a, t], i) => `<a href="#${a}"><b>${i}</b>${esc(t)}</a>`).join('');
	const body = secs.map(([a, t, x], i) => `<section id="${a}"><h2><a class="chip" href="#${a}">${i}</a>${esc(t)}</h2>${x}</section>`).join('');
	// Function replacers, so `$` in the content (prices like $0.0041) is never read as a pattern.
	return PAGE.replace('{{TOC}}', () => toc)
		.replace('{{BODY}}', () => body)
		.replace('{{VERSION}}', () => spec.VERSION)
		.replace('%VERBS%', () => JSON.stringify(spec.VERBS));
}
