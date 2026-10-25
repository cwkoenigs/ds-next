// Rail, the look ds-next ships: its tokens against ds-next's own ui_style.py, every row on the grid,
// and `rule agent --look rail` driven end to end with a scripted agent.
import {renderToString} from 'ink';
import {render} from 'ink-testing-library';
import {existsSync, readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {describe, expect, it} from 'vitest';
import {AgentApp, type Opener} from '../src/agent/AgentApp.js';
import {argSummary, describePermission, RAIL, railName} from '../src/agent/looks.js';
import {scripted} from '../src/demo/scripted.js';
import {buildRail} from '../src/html.js';
import * as r from '../src/rail/builders.js';
import {SCREENS} from '../src/rail/screens.js';
import * as RT from '../src/rail/tokens.js';
import {makeTheme, resolve, ThemeContext} from '../src/theme.js';
import {plain, s, width} from '../src/text.js';
import {RailScreen} from '../src/tour/rail.js';
import {ENTER, fake, ready, tick, until} from './helpers.js';

const UI_STYLE = fileURLToPath(new URL('../../../../src/ds_next/ui_style.py', import.meta.url)); // ds-next's own, when this sits in ds-next
const CTRL_C = '\u0003';

describe("Rail's tokens are ds-next's", () => {
	const py = existsSync(UI_STYLE) ? readFileSync(UI_STYLE, 'utf8') : '';
	const roles = new Map([...py.matchAll(/^\s+"(\w+)":\s*\("([^"]*)",\s*"([^"]*)",\s*"([^"]*)"\)/gm)].map(m => [m[1]!, [m[2]!, m[3]!, m[4]!] as const]));
	const hex = (style: string) => /#[0-9a-f]{6}/.exec(style)?.[0];
	const NAMES: Record<string, string | undefined> = {default: undefined, bright_black: 'gray', reverse: 'inverse'};
	const ansi = (style: string) => {
		const name = style.replace(/^(bold |on )/, '');
		return name in NAMES ? NAMES[name] : name;
	};

	it.skipIf(!py)('has the same colours, dark, light and ANSI-16', () => {
		expect(roles.size).toBeGreaterThan(10);
		for (const role of ['text', 'muted', 'dim', 'rule', 'accent', 'strong', 'brand', 'ok', 'warn', 'err', 'surface', 'hl', 'eye'] as const) {
			const [d, l, a] = roles.get(role)!;
			expect([role, RT.PALETTE.dark[role], RT.PALETTE.light[role]]).toEqual([role, hex(d), hex(l)]);
			const mine = RT.ANSI16[role] === 'blackBright' ? 'gray' : RT.ANSI16[role];
			expect([role, mine]).toEqual([role, ansi(a)]);
		}
		// The bands: the ground's colour, bold, on brand (the tag) or accent (the key).
		expect(roles.get('band')![0]).toBe(`bold ${RT.PALETTE.dark.eye} on ${RT.PALETTE.dark.brand}`);
		expect(roles.get('key')![1]).toBe(`bold ${RT.PALETTE.light.eye} on ${RT.PALETTE.light.accent}`);
	});

	it.skipIf(!py)('has the same glyphs, spinner and mascot', () => {
		for (const [k, v] of Object.entries(RT.G)) expect([k, new RegExp(`\\b${k}: str = "${v.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"`).test(py)]).toEqual([k, true]);
		expect(py).toContain(`SPINNERS["ds"] = {"interval": ${RT.SPINNER.intervalMs}, "frames": list("${RT.SPINNER.frames.join('')}")}`);
		const grid = /MASCOT = """\\\n([\s\S]*?)"""/.exec(py)![1]!.trim().split('\n');
		expect(grid).toEqual([...RT.MASCOT]);
	});

	it('resolves a band and the menu highlight at every depth', () => {
		const tag = r.band(' #2 ');
		expect(resolve(makeTheme('dark', 'hex', false, 'rail'), tag)).toEqual({color: '#1d1f20', backgroundColor: '#749dc4', bold: true, inverse: undefined});
		expect(resolve(makeTheme('light', 'ansi16', false, 'rail'), tag)).toEqual({color: 'black', backgroundColor: 'blue', bold: true, inverse: undefined});
		expect(resolve(makeTheme('dark', 'ansi16', false, 'rail'), s('x', 'text', {bg: 'hl'})).inverse).toBe(true); // Rich's reverse
		expect(resolve(makeTheme('dark', 'hex', false, 'rail'), s('›', 'strong')).bold).toBe(true);
	});
});

describe('Rail on the grid', () => {
	it('draws every screen inside 80 columns, frames exactly 80', () => {
		for (const [title, , rows] of SCREENS) {
			for (const row of rows()) {
				const text = plain(row);
				expect([title, width(row) <= 80]).toEqual([title, true]);
				if (/^[┌╭╰└├]|^│ [┌│└]/.test(text) && /[┐╮╯┘┤]$/.test(text)) expect([title, text, width(row)]).toEqual([title, text, 80]);
			}
		}
	});

	it('the banner is exactly w wide at 80 and at 60, the mascot 10 rows of 28', () => {
		const m = r.mascotRows();
		expect(m.map(width)).toEqual(Array(10).fill(28));
		for (const w of [80, 60]) {
			const rows = r.banner('v0.1.0', [['cwd', '~/x'], ['canon', '26 standards · 4 project types']], ['hint'], '~/Developer/canon', 'start, check and grow', w);
			expect(new Set(rows.map(width))).toEqual(new Set([w]));
		}
	});

	it('the prompt box is the terminal\'s width and wraps a long line downward', () => {
		for (const w of [40, 80, 132]) {
			const rows = r.promptBox('New session', r.promptLine('x'.repeat(150)), w);
			expect(new Set(rows.map(width))).toEqual(new Set([w]));
			expect(plain(rows[0]!)).toMatch(/^╭─+ New session ──╮$/);
			expect(rows.length).toBe(2 + Math.ceil((153 - (w - 3)) / (w - 5)) + 1);
		}
	});

	it('the toolbar fills the width and keeps its right end', () => {
		for (const w of [40, 80]) {
			const t = r.toolbar('order-metrics · order-metrics: 16 adopted · 0 declined · 1 pending · claude-sonnet-4-5 · low · idle', '2 queued · #3', w);
			expect(width(t)).toBe(w);
			expect(plain(t)).toMatch(/… +2 queued · #3 {2}$/);
		}
	});

	it('an approval is a warn frame on the rail, with the keys in its bottom edge', () => {
		const rows = r.approval('Bash', 'uv run pytest -q', 80);
		expect(plain(rows[0]!)).toBe('│');
		expect(plain(rows[1]!)).toMatch(/^│ ┌─ Allow Bash\? ─+┐$/);
		expect(plain(rows.at(-1)!)).toMatch(/^│ └─ {2}y {2}yes · a always this session · n no ─+┘$/);
		expect(rows.slice(1).map(width)).toEqual(Array(rows.length - 1).fill(80));
		expect(rows[1]!.find(sp => sp.text.includes('┌'))!.role).toBe('warn');
	});

	it('every screen renders in the terminal, dark and light', () => {
		SCREENS.forEach(([title], i) => {
			const out = renderToString(
				<ThemeContext.Provider value={makeTheme('dark', 'none', false, 'rail')}>
					<RailScreen index={i} themes={['dark', 'light']} />
				</ThemeContext.Provider>,
				{columns: 80},
			);
			expect(out).toContain(`Rail · ${title}`);
		});
	});

	it('rule html --look rail is one page with every screen', () => {
		const page = buildRail();
		for (const [title] of SCREENS) expect(page).toContain(`${title}</h2>`);
		expect(page).toContain('#749dc4'); // the dog, in dark
		expect(page).not.toMatch(/<script src|<link rel="stylesheet" href="(?!https:\/\/fonts\.googleapis)/);
	});
});

describe('how Rail names tools and asks', () => {
	it('names tools as ds-next does', () => {
		expect([railName('mcp__ds__canon_read'), railName('mcp__graph__trace_path'), railName('bash'), railName('Bash')]).toEqual(['canon_read', 'graph.trace_path', 'Bash', 'Bash']);
		expect(argSummary({command: 'uv run\npytest'})).toBe('uv run pytest');
		expect(argSummary({id: 'testing', other: 1})).toBe('testing');
		expect(argSummary({n: 1})).toBe('{"n": 1}');
		expect(argSummary({})).toBe('');
		expect(argSummary({command: 'x'.repeat(80)})).toBe('x'.repeat(57) + '…');
	});

	it('describes permissions in both agents\' shapes (ds-next test_permission_payloads)', () => {
		expect(describePermission('MCP', {action: 'execute_command', resource: 'mcp__ds__scaffold_project\nInput: {\n "name": "x"\n}'})).toEqual(['scaffold_project', '{\n "name": "x"\n}']);
		// rule's gate passes the tool id it found in the resource
		expect(describePermission('mcp__ds__scaffold_project', {resource: 'mcp__ds__scaffold_project\nInput: {}'})).toEqual(['scaffold_project', '{}']);
		expect(describePermission('Bash', {action: 'execute_command', resource: 'echo hi'})).toEqual(['Bash', 'echo hi']);
		expect(describePermission('mcp__ds__scaffold_project', {name: 'x'})).toEqual(['scaffold_project', '{\n "name": "x"\n}']);
		expect(describePermission('Bash', {command: 'echo hi'})).toEqual(['Bash', 'echo hi']);
	});
});

const rail = (open: Opener, label?: string) => render(<AgentApp backend="cortex" open={open} cwd="/work/order-metrics" width={80} look={RAIL} label={label} />);
const BOX = 'New session ──╮';

describe('rule agent --look rail', () => {
	it('plays a turn on one rail and asks with y, a or n', async () => {
		const {open, log} = fake();
		const a = rail(open);
		await ready(a, BOX);
		expect(a.lastFrame()).toContain('ds-next v0.1.0');
		expect(a.lastFrame()).toContain('start, check and grow');
		a.stdin.write('run the tests');
		await tick();
		a.stdin.write(ENTER);
		const asking = await until(a.lastFrame, f => f.includes('Allow Bash?'));
		expect(asking).toMatch(/╭─+ New session ──╮\n│ › run the tests +│\n╰─+╯\n\n#1\n/); // the box stays, with the line
		expect(asking).toContain("● I'll run the tests with  uv run pytest .");
		expect(asking).toContain('│ → Bash uv run pytest -q\n│\n│ ┌─ Allow Bash? ');
		a.stdin.write(ENTER); // enter alone asks again
		await tick(60);
		expect(log.answers).toEqual([]);
		a.stdin.write('y');
		await tick();
		a.stdin.write(ENTER);
		const f = await until(a.lastFrame, f => f.includes('╰ #1 · 1 tool call · 15.2s · $0.0041'));
		expect(log.answers).toEqual(['yes']);
		expect(f).toMatch(/│ {3}› y\n│ {3}⎿ 13 passed in 1\.42s {2}┄ 2 more lines · ctrl-o\n● Done\n│ The tests pass\.\n╰ #1/);
		expect(f).not.toContain('Thought'); // reasoning stays private
		expect(f).toMatch(/╭─+ #2 ──╮/); // the next box carries the next turn's tag
		expect(f).toMatch(/order-metrics · not a ds repo · test-model · default · connected +#1/);
		a.unmount();
	});

	it('reads a fast y and enter as yes', async () => {
		const {open, log} = fake();
		const a = rail(open);
		await ready(a, BOX);
		a.stdin.write('run the tests');
		a.stdin.write(ENTER);
		await until(a.lastFrame, f => f.includes('Allow Bash?'));
		a.stdin.write('y');
		a.stdin.write(ENTER);
		await until(a.lastFrame, f => f.includes('╰ #1'));
		expect(log.answers).toEqual(['yes']);
		a.unmount();
	});

	it('a decline ends the turn without reporting a failure', async () => {
		const {open, log} = fake();
		const a = rail(open);
		await ready(a, BOX);
		a.stdin.write('run the tests');
		await tick();
		a.stdin.write(ENTER);
		await until(a.lastFrame, f => f.includes('Allow Bash?'));
		a.stdin.write('n');
		await tick();
		a.stdin.write(ENTER);
		const f = await until(a.lastFrame, f => f.includes('╰ #1 · 1 tool call · 0.9s'));
		expect(log.answers).toEqual(['no']);
		expect(f).toContain('│   ⎿ ERROR The person declined this.');
		expect(f).not.toContain('⎿ interrupted');
		a.unmount();
	});

	it('ctrl-c interrupts a turn, then twice at the prompt leaves', async () => {
		const log = {interrupts: 0};
		const busy: Opener = async () => ({send() {}, interrupt: async () => void log.interrupts++, async setModel() {}, close() {}}); // a turn that never ends
		const a = rail(busy);
		await ready(a, BOX);
		a.stdin.write('run the tests');
		await tick();
		a.stdin.write(ENTER);
		await until(a.lastFrame, f => f.includes('ctrl-c interrupts'));
		a.stdin.write(CTRL_C);
		await until(a.lastFrame, f => f.includes('⎿ interrupted after'));
		expect(log.interrupts).toBe(1);
		a.unmount();

		const b = rail(fake().open);
		await ready(b, BOX);
		b.stdin.write('half a thought');
		await tick();
		b.stdin.write(CTRL_C);
		const f = await until(b.lastFrame, f => f.includes('ctrl-c again to leave'));
		expect(f).not.toContain('half a thought'); // the first press clears the line
		b.stdin.write(CTRL_C);
		await tick(60);
		b.stdin.write('still here');
		await tick(60);
		expect(b.lastFrame()).not.toContain('still here'); // the app has exited: nothing reads the keys
		b.unmount();
	});

	it('answers its own commands, flat', async () => {
		const a = rail(fake().open);
		await ready(a, BOX);
		a.stdin.write('/');
		const menu = await until(a.lastFrame, f => f.includes('/status') && f.includes('/last'));
		expect(menu).toMatch(/╰─+╯\n {3}\/status {15}Agent, model, session and cost/); // the menu drops below the box
		a.stdin.write('help');
		await tick();
		a.stdin.write(ENTER);
		const f = await until(a.lastFrame, f => f.includes('anything else'));
		expect(f).toContain('  /status       Agent, model, session and cost');
		expect(f).toContain('ctrl-c interrupts a turn · ctrl-c twice or ctrl-d leaves');
		a.unmount();
	});
});

describe('rule demo --look rail', () => {
	it('plays the scripted turn through the real agent terminal', async () => {
		const a = rail(scripted({fast: true}), 'demo agent');
		await ready(a, BOX);
		a.stdin.write('is the testing standard met?');
		await tick();
		a.stdin.write(ENTER);
		await until(a.lastFrame, f => f.includes('Allow Bash?'));
		expect(a.lastFrame()).toContain('│ → canon_read testing\n│   ⎿ # Testing  ┄ 3 more lines · ctrl-o');
		a.stdin.write('y');
		await tick();
		a.stdin.write(ENTER);
		const f = await until(a.lastFrame, f => f.includes('╰ #1 · 2 tool calls'));
		expect(f).toContain('│   ⎿ 13 passed in 1.42s');
		expect(f).toContain('│ • the testing standard is met');
		a.unmount();
	});
});
