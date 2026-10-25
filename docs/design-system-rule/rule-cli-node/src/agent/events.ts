// What the terminal needs from an agent turn, whichever SDK sent it. Claude Code and Cortex Code
// emit the same message shapes (Cortex's SDK is a fork); this reduces them to a few events.

export type AgentEvent =
	| {kind: 'init'; model: string; sessionId: string}
	| {kind: 'text'; text: string}
	| {kind: 'thinking'; text: string}
	| {kind: 'tool'; id: string; name: string; input: Record<string, unknown>}
	| {kind: 'toolResult'; id: string; text: string; isError: boolean}
	| {kind: 'result'; ok: boolean; durationMs: number; costUsd?: number; errors: string[]}
	| {kind: 'error'; message: string};

type Block = {type: string; [k: string]: unknown};
type Msg = {type: string; subtype?: string; [k: string]: unknown};

const textOf = (content: unknown): string =>
	typeof content === 'string'
		? content
		: Array.isArray(content)
			? content.map(c => (c && typeof c === 'object' && 'text' in c ? String((c as {text: unknown}).text) : '')).join('\n')
			: '';

/** One SDK message → zero or more events. Messages from subagents (parent_tool_use_id) are left out:
 *  the transcript shows the subagent's tool call and its result, not its inner steps. */
export function normalize(raw: unknown): AgentEvent[] {
	const m = raw as Msg;
	if (!m || typeof m !== 'object') return [];
	if (m['parent_tool_use_id']) return [];
	switch (m.type) {
		case 'system':
			return m.subtype === 'init' ? [{kind: 'init', model: String(m['model'] ?? ''), sessionId: String(m['session_id'] ?? '')}] : [];
		case 'assistant': {
			const inner = m['message'] as {content?: Block[]} | undefined;
			const blocks = (inner?.content ?? (m['content'] as Block[] | undefined) ?? []) as Block[];
			const out: AgentEvent[] = [];
			for (const b of blocks) {
				if (b.type === 'text' && String(b['text'] ?? '').trim()) out.push({kind: 'text', text: String(b['text'])});
				else if (b.type === 'thinking') out.push({kind: 'thinking', text: String(b['thinking'] ?? '')});
				else if (b.type === 'tool_use') out.push({kind: 'tool', id: String(b['id']), name: String(b['name']), input: (b['input'] ?? {}) as Record<string, unknown>});
			}
			if (m['error']) out.push({kind: 'error', message: String(m['error'])});
			return out;
		}
		case 'user': {
			const content = (m['message'] as {content?: unknown} | undefined)?.content;
			if (!Array.isArray(content)) return [];
			return (content as Block[])
				.filter(b => b.type === 'tool_result')
				.map(b => ({kind: 'toolResult', id: String(b['tool_use_id']), text: textOf(b['content']), isError: Boolean(b['is_error'])}));
		}
		case 'result':
			return [
				{
					kind: 'result',
					ok: !m['is_error'],
					durationMs: Number(m['duration_ms'] ?? 0),
					costUsd: typeof m['total_cost_usd'] === 'number' ? (m['total_cost_usd'] as number) : undefined,
					errors: Array.isArray(m['errors']) ? (m['errors'] as unknown[]).map(String) : [],
				},
			];
		default:
			return [];
	}
}
