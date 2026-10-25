// What the live tests share: waiting for a frame, and a scripted agent session.
import type {Opener} from '../src/agent/AgentApp.js';
import type {AgentSession, Answer, SessionOptions} from '../src/agent/backend.js';

export const tick = (ms = 20) => new Promise(r => setTimeout(r, ms));
export const ENTER = '\r';

// Waits end as soon as the frame matches; the ceiling only matters on a loaded machine.
export async function until(frame: () => string | undefined, test: (f: string) => boolean, ms = 10_000) {
	const end = Date.now() + ms;
	while (Date.now() < end) {
		if (test(frame() ?? '')) return frame() ?? '';
		await tick();
	}
	throw new Error(`timed out; last frame:\n${frame()}`);
}

/** Keys written before the input hooks are attached are lost. They attach in an effect after the
 *  first frame, late on a loaded machine; the banner, printed by an effect of the same flush, comes
 *  in a later frame. So wait for the box and for a second frame. */
export async function ready(app: {lastFrame: () => string | undefined; frames: string[]}, box = '? shortcuts') {
	await until(app.lastFrame, f => f.includes(box) && app.frames.length > 1);
}

/** A scripted agent: each message runs one turn with a Bash call that needs approval. */
export function fake() {
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
