import {render} from 'ink-testing-library';
import {describe, expect, it} from 'vitest';
import {AgentApp, type Opener} from '../src/agent/AgentApp.js';
import {type AgentSession, type Answer, chooseBackend, dsServer, load, openSession, permissionGate, ruleSpec, type SessionOptions} from '../src/agent/backend.js';
import {normalize} from '../src/agent/events.js';
import {agentRows} from '../src/agent/markdown.js';
import {displayName, resultSummary, toolArgs} from '../src/agent/present.js';
import {Canon, Skills} from '../src/ds/kb.js';
import {tools as dsTools} from '../src/ds/tools.js';
import {plain, width} from '../src/text.js';

const tick = (ms = 20) => new Promise(r => setTimeout(r, ms));
const ENTER = '\r';

// Waits end as soon as the frame matches; the ceiling only matters on a loaded machine.
async function until(frame: () => string | undefined, test: (f: string) => boolean, ms = 10_000) {
	const end = Date.now() + ms;
	while (Date.now() < end) {
		if (test(frame() ?? '')) return frame() ?? '';
		await tick();
	}
	throw new Error(`timed out; last frame:\n${frame()}`);
}

/** A scripted agent: each message runs one turn with a Bash call that needs approval. */
function fake() {
	const log = {sent: [] as string[], answers: [] as Answer[], interrupts: 0};
	let n = 0;
	const open: Opener = async (o: SessionOptions): Promise<AgentSession> => {
		o.onEvent({kind: 'init', model: 'test-model', sessionId: 'sess-1'});
		return {
			send(text) {
				log.sent.push(text);
				const id = `t${++n}`;
				void (async () => {
					await tick();
					o.onEvent({kind: 'thinking', text: 'The user wants the tests run.'});
					o.onEvent({kind: 'text', text: "I'll run the **tests** with `uv run pytest`."});
					o.onEvent({kind: 'tool', id, name: 'Bash', input: {command: 'uv run pytest -q', description: 'Run the tests'}});
					const a = await o.ask('Bash', {command: 'uv run pytest -q', description: 'Run the tests'});
					log.answers.push(a);
					if (a === 'no') {
						o.onEvent({kind: 'toolResult', id, text: 'The person declined this.', isError: true});
						o.onEvent({kind: 'result', ok: false, durationMs: 900, errors: ['interrupted']});
						return;
					}
					o.onEvent({kind: 'toolResult', id, text: '13 passed in 1.42s\nline 2\nline 3', isError: false});
					o.onEvent({kind: 'text', text: '## Done\nThe tests pass.'});
					o.onEvent({kind: 'result', ok: true, durationMs: 15200, costUsd: 0.0041, errors: []});
				})();
			},
			async interrupt() {
				log.interrupts++;
			},
			async setModel() {},
			close() {},
		};
	};
	return {open, log};
}

const app = (open: Opener) => render(<AgentApp backend="cortex" open={open} cwd="/work/order-metrics" width={80} />);

describe('rule agent', () => {
	it('plays a turn into the transcript and asks before running a command', async () => {
		const {open, log} = fake();
		const a = app(open);
		await tick();
		a.stdin.write('run the tests');
		await tick();
		a.stdin.write(ENTER);
		const asking = await until(a.lastFrame, f => f.includes('BASH COMMAND'));
		expect(asking).toContain('uv run pytest -q');
		expect(asking).toContain('▫ Bash uv run pytest -q'); // the running tool sits above the dialog
		a.stdin.write('1');
		const f = await until(a.lastFrame, f => f.includes('1 tools  15.2s  $0.0041'));
		expect(log.sent).toEqual(['run the tests']);
		expect(log.answers).toEqual(['yes']);
		expect(f).toContain('━━ 01 ━');
		expect(f).toContain('· Thought for');
		expect(f).toContain("■ I'll run the tests with  uv run pytest .");
		expect(f).toMatch(/▪ Bash uv run pytest -q\n {2}└ 13 passed in 1\.42s\n {4}└ 2 more lines {2}ctrl-o/);
		expect(f).toContain('DONE');
		a.unmount();
	});

	it('a decline ends the turn without reporting a failure', async () => {
		const {open, log} = fake();
		const a = app(open);
		await tick();
		a.stdin.write('run the tests');
		await tick();
		a.stdin.write(ENTER);
		await until(a.lastFrame, f => f.includes('BASH COMMAND'));
		a.stdin.write('3');
		const f = await until(a.lastFrame, f => f.includes('0.9s'));
		expect(log.answers).toEqual(['no']);
		expect(f).toContain('› No');
		expect(f).not.toContain('turn failed');
		a.unmount();
	});

	it('says what went wrong when the agent cannot start', async () => {
		const a = app(async () => {
			throw new Error('Cortex Code SDK did not load. It needs Node 22.22 or newer.');
		});
		await tick();
		a.stdin.write('hello');
		await tick();
		a.stdin.write(ENTER);
		const f = await until(a.lastFrame, f => f.includes('did not load'));
		expect(f).toContain('✗ Cortex Code');
		expect(f).toContain('? shortcuts'); // back to the box
		a.unmount();
	});

	it('answers its own commands without the agent', async () => {
		const {open, log} = fake();
		const a = app(open);
		await tick();
		a.stdin.write('/status');
		await tick();
		a.stdin.write(ENTER);
		const f = await until(a.lastFrame, f => f.includes('not started'));
		expect(f).toContain('Cortex Code');
		expect(log.sent).toEqual([]);
		a.unmount();
	});
});

describe('agent events', () => {
	it('reads Claude Code and Cortex Code messages alike', () => {
		const claude = {type: 'assistant', parent_tool_use_id: null, message: {content: [{type: 'thinking', thinking: 'hm'}, {type: 'text', text: 'hi'}, {type: 'tool_use', id: 'a', name: 'Bash', input: {command: 'ls'}}]}};
		expect(normalize(claude).map(e => e.kind)).toEqual(['thinking', 'text', 'tool']);
		const cortex = {type: 'assistant', parent_tool_use_id: null, content: [{type: 'text', text: 'hi'}], message: {content: [{type: 'text', text: 'hi'}]}};
		expect(normalize(cortex)).toEqual([{kind: 'text', text: 'hi'}]);
		const result = {type: 'user', message: {content: [{type: 'tool_result', tool_use_id: 'a', content: [{type: 'text', text: 'x'}], is_error: true}]}};
		expect(normalize(result)).toEqual([{kind: 'toolResult', id: 'a', text: 'x', isError: true}]);
		expect(normalize({type: 'result', is_error: false, duration_ms: 5, total_cost_usd: 0.01})).toEqual([{kind: 'result', ok: true, durationMs: 5, costUsd: 0.01, errors: []}]);
		expect(normalize({type: 'assistant', parent_tool_use_id: 'x', message: {content: [{type: 'text', text: 'sub'}]}})).toEqual([]);
	});
});

describe('presenting tools', () => {
	it('names and summarises tool calls from either agent', () => {
		expect(displayName('bash')).toBe('Bash');
		expect(displayName('mcp__ds__rule_spec')).toBe('rule_spec');
		expect(toolArgs('read', {file_path: '/work/app/src/cli.py'}, '/work/app')).toBe('src/cli.py');
		expect(resultSummary('Edit', {old_string: 'a', new_string: 'a\nb\nc'}, '', false).first).toBe('+3 −1');
		expect(resultSummary('Bash', {}, 'ERROR: <tool_use_error>boom</tool_use_error>', true).first).toBe('boom');
	});

	it('draws Markdown in Rule: uppercase headings, code on the surface, wrapped at the text column', () => {
		const rows = agentRows('## Next steps\nRun `uv run pytest` and then **ship** it. ' + 'word '.repeat(30), 60);
		expect(plain(rows[0]!)).toBe('■ NEXT STEPS');
		expect(rows[1]!.some(sp => sp.bg === 'surface' && sp.text === ' uv run pytest ')).toBe(true);
		for (const r of rows) expect(width(r)).toBeLessThanOrEqual(60);
	});
});

describe('the permission gate', () => {
	it("asks once per tool after 'don't ask again', and never for the terminal's read-only tools", async () => {
		const asked: string[] = [];
		const gate = permissionGate(async name => {
			asked.push(name);
			return 'always';
		});
		expect((await gate('Bash', {command: 'ls'})).behavior).toBe('allow');
		expect((await gate('Bash', {command: 'pwd'})).behavior).toBe('allow');
		expect((await gate('mcp__ds__rule_spec', {})).behavior).toBe('allow');
		// Cortex asks about in-process tools as kind MCP, naming the tool on the resource's first line.
		expect((await gate('MCP', {resource: 'mcp__ds__rule_spec\nsection: grid'})).behavior).toBe('allow');
		expect(asked).toEqual(['Bash']);
	});

	it('a decline denies and interrupts', async () => {
		const gate = permissionGate(async () => 'no');
		expect(await gate('Edit', {file_path: 'x'})).toMatchObject({behavior: 'deny', interrupt: true});
	});
});

describe('backends', () => {
	it('chooses --agent, then DS_AGENT', () => {
		expect(chooseBackend('claude')).toBe('claude');
		process.env['DS_AGENT'] = 'claude';
		expect(chooseBackend()).toBe('claude');
		delete process.env['DS_AGENT'];
	});

	it.each(['claude', 'cortex'] as const)('%s: the SDK loads and builds the ds server with every tool', async backend => {
		const sdk = await load(backend);
		expect(typeof sdk.query).toBe('function');
		const all = dsTools({cwd: '.', canon: () => new Canon('/nowhere'), skills: () => new Skills('/nowhere')});
		const server = dsServer(sdk, all) as {type?: string; name?: string; instance?: unknown};
		expect(server.type).toBe('sdk');
		expect(server.name).toBe('ds');
		expect(all).toHaveLength(17);
	});

	it('says when the Cortex CLI is missing instead of hanging', async () => {
		process.env['CORTEX_CODE_CLI_PATH'] = '/nowhere/cortex';
		try {
			await expect(openSession({backend: 'cortex', cwd: '.', ask: async () => 'no', onEvent: () => {}, onClose: () => {}})).rejects.toThrow(/Cortex Code CLI not found/);
		} finally {
			delete process.env['CORTEX_CODE_CLI_PATH'];
		}
	});

	it('rule_spec reads a section, and says which exist when one does not', () => {
		expect(JSON.parse(ruleSpec('principles'))['The grid shows']).toMatch(/Three columns/);
		expect(ruleSpec('nope')).toMatch(/^ERROR: no section/);
	});
});
