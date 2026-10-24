import {renderToString} from 'ink';
import {render} from 'ink-testing-library';
import {describe, expect, it} from 'vitest';
import {Demo} from '../src/demo/Demo.js';
import {CHAPTERS} from '../src/tour/chapters.js';
import {ChapterView, Tour} from '../src/tour/Tour.js';

const tick = (ms = 30) => new Promise(r => setTimeout(r, ms));
const ENTER = '\r';
const DOWN = '\u001B[B';

async function until(frame: () => string | undefined, test: (f: string) => boolean, ms = 3000) {
	const end = Date.now() + ms;
	while (Date.now() < end) {
		if (test(frame() ?? '')) return frame() ?? '';
		await tick(20);
	}
	throw new Error(`timed out; last frame:\n${frame()}`);
}

describe('the demo', () => {
	it('types into a box that stays closed', async () => {
		const app = render(<Demo width={80} fast />);
		await tick();
		app.stdin.write('hello there');
		const f = await until(app.lastFrame, f => f.includes('hello there'));
		const line = f.split('\n').find(l => l.includes('› hello there'))!;
		expect(line.startsWith('┃')).toBe(true);
		expect(line.trimEnd().endsWith('┃')).toBe(true);
		app.unmount();
	});

	it('opens the slash popup, moves with ↓ and runs the selection', async () => {
		const app = render(<Demo width={80} fast />);
		await tick();
		app.stdin.write('/s');
		await until(app.lastFrame, f => f.includes('/standards') && f.includes('↑↓ move'));
		app.stdin.write(DOWN);
		await until(app.lastFrame, f => /■ \/standards/.test(f));
		app.stdin.write(ENTER);
		await until(app.lastFrame, f => f.includes('› /standards') && f.includes('6 of 16 apply here'));
		app.unmount();
	});

	it('plays a turn, asks, and lands the answer', async () => {
		const app = render(<Demo width={80} fast />);
		await tick();
		app.stdin.write('add a --since flag');
		await tick();
		app.stdin.write(ENTER);
		await until(app.lastFrame, f => f.includes('BASH COMMAND') && f.includes('enter chooses'));
		app.stdin.write('1');
		const f = await until(app.lastFrame, f => f.includes('› Yes') && f.includes('3 tools  15.2s'));
		expect(f).toContain('━━ 01 ━');
		expect(f).toContain('· Thought for');
		expect(f).toContain('▪ Bash uv run pytest -q');
		expect(f).toContain('? shortcuts'); // the box is back
		app.unmount();
	});
});

describe('the tour', () => {
	it('renders every chapter', () => {
		for (let i = 0; i < CHAPTERS.length; i++) {
			const out = renderToString(<ChapterView index={i} themes={['dark', 'light']} />, {columns: 80});
			expect(out).toContain(CHAPTERS[i]!.title.toUpperCase());
		}
	});

	it('pages on enter', async () => {
		const app = render(<Tour themes={['dark']} />);
		await until(app.lastFrame, f => f.includes('1/19'));
		app.stdin.write(ENTER);
		await until(app.lastFrame, f => f.includes('CANOPY VS RULE') && f.includes('2/19'));
		app.unmount();
	});
});
