// A scripted agent for `rule demo --look rail`: the real agent terminal (AgentApp), with a session
// that plays one canned turn per message instead of calling a model. It reads the canon, runs the
// tests after asking, and reports; esc or ctrl-c interrupts it, and a "no" ends the turn.
import type {Opener} from '../agent/AgentApp.js';
import type {SessionOptions} from '../agent/backend.js';

const TESTING = `# Testing
Every repo runs its tests with one command, named in AGENTS.md.
Tests live beside the code they cover and run in under a minute.
A failing test blocks the push; a skipped one says why.`;

const PASSED = `13 passed in 1.42s
tests/test_cli.py ........
tests/test_metrics.py .....`;

export function scripted({fast = false} = {}): Opener {
	return async (o: SessionOptions) => {
		let turn = 0;
		let stopped = false;
		const wait = (ms: number) => new Promise(r => setTimeout(r, fast ? 1 : ms));
		o.onEvent({kind: 'init', model: '', sessionId: 'demo-session'});
		const play = async (text: string) => {
			const n = ++turn;
			const started = Date.now();
			const ended = () => {
				if (!stopped) return false;
				o.onEvent({kind: 'result', ok: false, durationMs: Date.now() - started, errors: ['interrupted']});
				return true;
			};
			await wait(700);
			if (ended()) return;
			o.onEvent({kind: 'thinking', text: `The person asked: ${text}. Read the testing standard, then run the suite.`});
			o.onEvent({kind: 'text', text: "I'll check the canon's **testing** standard, then run the tests with `uv run pytest -q`."});
			o.onEvent({kind: 'tool', id: `${n}-read`, name: 'mcp__ds__canon_read', input: {id: 'testing'}});
			await wait(800);
			if (ended()) return;
			o.onEvent({kind: 'toolResult', id: `${n}-read`, text: TESTING, isError: false});
			const run = {command: 'uv run pytest -q', description: 'Run the test suite'};
			o.onEvent({kind: 'tool', id: `${n}-bash`, name: 'Bash', input: run});
			const answer = await o.ask('Bash', run);
			if (answer === 'no') {
				o.onEvent({kind: 'toolResult', id: `${n}-bash`, text: 'The person declined this.', isError: true});
				o.onEvent({kind: 'result', ok: false, durationMs: Date.now() - started, errors: ['declined']});
				return;
			}
			await wait(1200);
			if (ended()) return;
			o.onEvent({kind: 'toolResult', id: `${n}-bash`, text: PASSED, isError: false});
			o.onEvent({kind: 'text', text: '## Done\nThe suite passes: **13 passed** in 1.42s.\n- the testing standard is met\n- nothing to change'});
			o.onEvent({kind: 'result', ok: true, durationMs: Date.now() - started, costUsd: 0.0041, errors: []});
		};
		return {
			send(text) {
				stopped = false;
				void play(text);
			},
			async interrupt() {
				stopped = true;
			},
			async setModel() {},
			close() {
				stopped = true;
				o.onClose();
			},
		};
	};
}
