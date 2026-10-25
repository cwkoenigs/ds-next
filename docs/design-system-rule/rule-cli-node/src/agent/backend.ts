// Which agent runs the turns, and one session with it. Claude Code (@anthropic-ai/claude-agent-sdk)
// or Cortex Code (@snowflake/cortex-agent-sdk, Snowflake's fork of the same SDK). Chosen as ds-next
// chooses: --agent, then DS_AGENT, then `agent = "..."` in ~/.ds/config.toml, then whichever CLI is
// on PATH, Cortex first. Nothing outside this file knows which SDK is loaded.
import {randomUUID} from 'node:crypto';
import {existsSync, readFileSync} from 'node:fs';
import {homedir} from 'node:os';
import {delimiter, join} from 'node:path';
import {z} from 'zod';
import * as spec from '../spec.js';
import {type AgentEvent, normalize} from './events.js';

export type Backend = 'claude' | 'cortex';
export const LABELS: Record<Backend, string> = {claude: 'Claude Code', cortex: 'Cortex Code'};
export const CONFIG = join(homedir(), '.ds', 'config.toml');

const isBackend = (v: unknown): v is Backend => v === 'claude' || v === 'cortex';

function onPath(cmd: string): boolean {
	const exts = process.platform === 'win32' ? (process.env['PATHEXT'] ?? '.EXE;.CMD;.BAT').split(';') : [''];
	return (process.env['PATH'] ?? '').split(delimiter).some(dir => dir && exts.some(ext => existsSync(join(dir, cmd + ext))));
}

/** The agent named in ~/.ds/config.toml (`ds-next setup --agent` writes it), if any. */
export function configured(): Backend | undefined {
	try {
		const m = /^\s*agent\s*=\s*["'](\w+)["']/m.exec(readFileSync(CONFIG, 'utf8'));
		return isBackend(m?.[1]) ? m[1] : undefined;
	} catch {
		return undefined;
	}
}

export function chooseBackend(flag?: string): Backend {
	for (const v of [flag, process.env['DS_AGENT']]) {
		const x = v?.trim().toLowerCase();
		if (isBackend(x)) return x;
	}
	return configured() ?? (onPath('cortex') ? 'cortex' : onPath('claude') ? 'claude' : 'cortex');
}

// ── the session ──────────────────────────────────────────────────────────────

export type Answer = 'yes' | 'always' | 'no';
/** Ask the person about one tool call. `name` is the tool's id (mcp__ds__x for in-process tools). */
export type Ask = (name: string, input: Record<string, unknown>) => Promise<Answer>;

export type SessionOptions = {
	backend: Backend;
	cwd: string;
	ask: Ask;
	onEvent: (e: AgentEvent) => void;
	/** Called once when the agent process ends, for whatever reason. */
	onClose: () => void;
	model?: string;
	connection?: string;
	effort?: string;
	resume?: string;
};

export interface AgentSession {
	send(text: string): void;
	interrupt(): Promise<void>;
	setModel(model?: string): Promise<void>;
	close(): void;
}

export class AgentUnavailable extends Error {}

/** The terminal's own tools, served in-process as the `ds` MCP server. Reading never asks. */
export const SERVER = 'ds';
export const READ_ONLY = new Set([`mcp__${SERVER}__rule_spec`]);

const SECTIONS = ['summary', 'principles', 'colour', 'glyphs', 'grid', 'motion', 'mascot', 'codeMap', 'screens', 'knownGaps'] as const;

export function ruleSpec(section?: string): string {
	const all = spec.asJson() as Record<string, unknown>;
	if (!section || section === 'all') return JSON.stringify(all, null, 1);
	if (!(section in all)) return `ERROR: no section ${JSON.stringify(section)}; one of ${SECTIONS.join(', ')}, or all`;
	return JSON.stringify(all[section], null, 1);
}

export function systemPrompt(cwd: string): string {
	return `You are ds, the team's assistant, running in a terminal drawn in Rule, the ds-next terminal design system.

- Your \`ds\` tools are the terminal's own. rule_spec reads the Rule design system: principles, colour roles, glyphs, grid, motion, screens.
- Anything that writes a file or runs a command asks the person first, in a dialog. If they decline, stop and wait for them to say what to do instead.
- Be brief. This is a terminal: facts, not sentences.

The working directory is ${cwd}. Today is ${new Date().toISOString().slice(0, 10)}.`;
}

/** Cortex asks about in-process tools as kind "MCP" with a resource string whose first line names the tool. */
function toolId(name: string, input: Record<string, unknown>): string {
	return name === 'MCP' ? String(input['resource'] ?? '').split('\n')[0]!.trim() || name : name;
}

type Sdk = {
	query: (p: {prompt: AsyncIterable<unknown>; options: Record<string, unknown>}) => AsyncGenerator<unknown> & {
		interrupt(): Promise<void>;
		setModel(model?: string): Promise<void>;
	};
	tool: (...a: any[]) => unknown;
	createSdkMcpServer: (o: {name: string; version?: string; tools: unknown[]}) => unknown;
};

export async function load(backend: Backend): Promise<Sdk> {
	try {
		return (backend === 'claude' ? await import('@anthropic-ai/claude-agent-sdk') : await import('@snowflake/cortex-agent-sdk/code')) as unknown as Sdk;
	} catch (err) {
		const need = backend === 'cortex' ? 'Node 22.22 or newer and @snowflake/cortex-agent-sdk' : '@anthropic-ai/claude-agent-sdk';
		throw new AgentUnavailable(`${LABELS[backend]} SDK did not load (${(err as Error).message.split('\n')[0]}). It needs ${need}; run npm install.`);
	}
}

/** A queue the SDK reads the conversation from: each send() is the next user message. */
function inbox() {
	const queue: unknown[] = [];
	let wake: (() => void) | undefined;
	let done = false;
	return {
		push(text: string) {
			queue.push({
				type: 'user',
				message: {role: 'user', content: [{type: 'text', text}]},
				parent_tool_use_id: null,
				session_id: '',
				uuid: randomUUID(),
			});
			wake?.();
		},
		end() {
			done = true;
			wake?.();
		},
		async *messages() {
			while (true) {
				while (queue.length) yield queue.shift();
				if (done) return;
				await new Promise<void>(r => (wake = r));
				wake = undefined;
			}
		},
	};
}

/** The SDK's canUseTool: reading the terminal's own tools never asks; everything else asks the
 *  person, and "don't ask again" lasts for the session. */
export function permissionGate(ask: Ask) {
	const always = new Set<string>();
	return async (name: string, input: Record<string, unknown>) => {
		const id = toolId(name, input);
		let answer: Answer = 'yes';
		if (!READ_ONLY.has(id) && !always.has(id)) answer = await ask(id, input);
		if (answer === 'always') always.add(id);
		return answer === 'no'
			? {behavior: 'deny' as const, message: 'The person declined this and will say what to do instead.', interrupt: true}
			: {behavior: 'allow' as const, updatedInput: input};
	};
}

/** The `ds` MCP server, built with the loaded SDK's own helpers. */
export function dsServer(sdk: Sdk): unknown {
	return sdk.createSdkMcpServer({
		name: SERVER,
		version: '0.1.0',
		tools: [
			sdk.tool(
				'rule_spec',
				'Read the Rule terminal design system spec this terminal is drawn in. Pass a section, or omit it for everything.',
				{section: z.string().optional().describe(`one of ${SECTIONS.join(', ')}; omit for all`)},
				async (args: {section?: string}) => {
					const text = ruleSpec(args.section);
					return {content: [{type: 'text', text}], isError: text.startsWith('ERROR: ')};
				},
			),
		],
	});
}

/** Cortex's SDK hangs, silently, when its CLI is missing (0.0.2 records the spawn error and never
 *  reports it), so look first, the way the SDK will: CORTEX_CODE_CLI_PATH, else `cortex` on PATH. */
export function cortexCli(): string | undefined {
	const set = process.env['CORTEX_CODE_CLI_PATH'];
	if (set) return existsSync(set) ? set : undefined;
	return onPath('cortex') ? 'cortex' : undefined;
}

export async function openSession(o: SessionOptions): Promise<AgentSession> {
	if (o.backend === 'cortex' && !cortexCli()) {
		const where = process.env['CORTEX_CODE_CLI_PATH'] ? `CORTEX_CODE_CLI_PATH (${process.env['CORTEX_CODE_CLI_PATH']}) does not exist` : 'cortex is not on your PATH';
		throw new AgentUnavailable(`Cortex Code CLI not found: ${where}. Install it, or run with --agent claude.`);
	}
	const sdk = await load(o.backend);
	const server = dsServer(sdk);
	const canUseTool = permissionGate(o.ask);
	const abortController = new AbortController();
	const common = {cwd: o.cwd, mcpServers: {[SERVER]: server}, canUseTool, model: o.model, effort: o.effort, resume: o.resume, abortController};
	const options =
		o.backend === 'claude'
			? {
					...common,
					strictMcpConfig: true, // the terminal's own servers only
					systemPrompt: {type: 'preset', preset: 'claude_code', append: systemPrompt(o.cwd)},
					settingSources: ['user', 'project'], // the repo's CLAUDE.md and the user's settings, as a normal session has
					permissionMode: 'default', // approvals come to the dialog, not to auto mode
				}
			: {
					...common,
					// No allowedTools: Cortex treats that list as exclusive. Read-only tools are allowed in canUseTool.
					appendSystemPrompt: systemPrompt(o.cwd),
					connection: o.connection,
					onlyExplicitMcpServers: true, // skip the user's mcp.json, or `ds` tools appear twice
				};

	const box = inbox();
	const q = sdk.query({prompt: box.messages(), options});
	void (async () => {
		try {
			for await (const m of q) for (const e of normalize(m)) o.onEvent(e);
		} catch (err) {
			if (!abortController.signal.aborted) o.onEvent({kind: 'error', message: (err as Error).message.split('\n')[0] ?? String(err)});
		} finally {
			o.onClose();
		}
	})();

	return {
		send: text => box.push(text),
		interrupt: () => q.interrupt(),
		setModel: model => q.setModel(model),
		close: () => {
			box.end();
			abortController.abort();
		},
	};
}
