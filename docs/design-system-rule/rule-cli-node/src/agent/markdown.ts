// Agent text (Markdown) as Rule rows: ■ on the first line, col 3 after; headings uppercase and bold;
// **bold** in bold; `code` on the surface; fenced code muted. No italics: Modernist doesn't slant.
import * as b from '../builders.js';
import {bold, type Row, s, wrapRow} from '../text.js';
import {GRID} from '../tokens.js';

function inline(line: string): Row {
	return line
		.split(/(\*\*[^*]+\*\*|`[^`]+`)/)
		.filter(Boolean)
		.map(part =>
			part.startsWith('**') && part.endsWith('**') && part.length > 4
				? bold(part.slice(2, -2))
				: part.startsWith('`') && part.endsWith('`') && part.length > 2
					? b.code(part.slice(1, -1))
					: s(part.replace(/(^|\W)[*_]([^*_]+)[*_](?=\W|$)/g, '$1$2')), // *emphasis* reads as plain text
		);
}

export function agentRows(text: string, w: number): Row[] {
	const width = w - GRID.indent;
	const lines: Row[] = [];
	let fenced = false;
	for (const raw of text.replace(/\s+$/, '').split('\n')) {
		if (/^\s*```/.test(raw)) {
			fenced = !fenced;
			continue;
		}
		if (fenced) {
			lines.push([s(raw.slice(0, width), 'muted')]);
			continue;
		}
		const h = /^#{1,6}\s+(.*)$/.exec(raw);
		if (h) {
			lines.push([bold(h[1]!.replace(/\*\*/g, '').toUpperCase())]);
			continue;
		}
		if (!raw.trim()) {
			lines.push([]);
			continue;
		}
		// List items keep their marker and wrap under their text.
		const item = /^(\s*(?:[-*]|\d+[.)])\s+)(.*)$/.exec(raw);
		if (item) {
			const lead = item[1]!.replace(/^(\s*)[*]/, '$1-');
			const wrapped = wrapRow(inline(item[2]!), width - lead.length);
			wrapped.forEach((r, i) => lines.push([s(i === 0 ? lead : ' '.repeat(lead.length)), ...r]));
			continue;
		}
		lines.push(...wrapRow(inline(raw), width));
	}
	while (lines.length && !lines[0]!.length) lines.shift();
	return b.agent(lines, w);
}
