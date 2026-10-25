#!/usr/bin/env node
// rule: the Rule terminal design system as a runnable reference CLI, and the ds-next agent terminal
// in either look: Rule, or Rail (ds-next's blue system with the dog and the cat).
import {render, renderToString} from 'ink';
import {writeFileSync} from 'node:fs';
import {parseArgs} from 'node:util';
import type {ReactNode} from 'react';
import {AgentApp} from './agent/AgentApp.js';
import {chooseBackend, openSession} from './agent/backend.js';
import {readDesk} from './agent/desk.js';
import {LOOK} from './agent/looks.js';
import {Demo} from './demo/Demo.js';
import {scripted} from './demo/scripted.js';
import {build, buildRail} from './html.js';
import * as spec from './spec.js';
import {type Depth, makeTheme, setDepth, type Theme, ThemeContext} from './theme.js';
import {SCREENS as RAIL_SCREENS} from './rail/screens.js';
import {GRID, type LookName, LOOKS, type ThemeName} from './tokens.js';
import {CHAPTERS} from './tour/chapters.js';
import {RailScreen} from './tour/rail.js';
import {ChapterView, Tour} from './tour/Tour.js';

const VERSION = '0.1.0';

const HELP = `rule: the Rule terminal design system, walked through, and the ds-next agent terminal.

  rule                     walk through every part of the spec (same as \`rule tour\`)
  rule tour [-c N]         the walkthrough, or one chapter of it
  rule chapters            list the chapters
  rule screen [N]          print screen N (1-7), or all seven, in dark and light
  rule spec [--json]       the spec as text, or as data
  rule html [-o FILE]      the tour as one web page, for reading on a phone
  rule demo                a live session with a faked agent
  rule agent               a real session with Cortex Code or Claude Code

Options
  --look rule|rail         how the agent, the demo and the screens are drawn: Rule (this design
                           system), or Rail (ds-next's blue one, with the dog and the cat)
                           (default: $DS_LOOK, else rule). With rail, \`rule screen\` prints
                           Rail's screens and \`rule html\` makes a page of them
  --theme dark|light       theme for the prose and the demo (default: $DS_THEME, else dark)
  --color truecolor|ansi16|none
                           force the colour depth (default: what the terminal supports)
  --one-theme              show each mockup in --theme only, not dark and light
  --no-pause               print the tour straight through
  --from N                 start the tour at chapter N
  --agent cortex|claude    which agent \`rule agent\` runs (default: $DS_AGENT, ~/.ds/config.toml,
                           then whichever CLI is on PATH, Cortex first)
  --model NAME             the model for \`rule agent\`
  --connection NAME        the Snowflake connection for Cortex (default: the CLI's default)
  --effort LEVEL           reasoning effort for \`rule agent\` (low, medium, high)
  -h, --help               this help
  -v, --version            the version`;

class UsageError extends Error {}

function int(value: string | undefined, name: string, lo: number, hi: number): number | undefined {
	if (value === undefined) return undefined;
	const n = Number(value);
	if (!Number.isInteger(n) || n < lo || n > hi) throw new UsageError(`${name} must be a whole number from ${lo} to ${hi}, not "${value}".`);
	return n;
}

/** Write a node once, without a live app: for pipes, --no-pause and the one-shot commands. */
function printOnce(theme: Theme, node: ReactNode): void {
	process.stdout.write(renderToString(<ThemeContext.Provider value={theme}>{node}</ThemeContext.Provider>, {columns: GRID.designWidth}) + '\n');
}

async function live(theme: Theme, node: ReactNode, {exitOnCtrlC = true} = {}): Promise<void> {
	const app = render(<ThemeContext.Provider value={theme}>{node}</ThemeContext.Provider>, {exitOnCtrlC});
	await app.waitUntilExit();
}

const interactive = () => Boolean(process.stdin.isTTY && process.stdout.isTTY);

async function main(argv: string[]): Promise<number> {
	const {values: o, positionals} = parseArgs({
		args: argv,
		allowPositionals: true,
		options: {
			look: {type: 'string'},
			theme: {type: 'string'},
			color: {type: 'string'},
			'one-theme': {type: 'boolean'},
			'no-pause': {type: 'boolean'},
			from: {type: 'string'},
			chapter: {type: 'string', short: 'c'},
			json: {type: 'boolean'},
			out: {type: 'string', short: 'o'},
			agent: {type: 'string'},
			model: {type: 'string'},
			connection: {type: 'string'},
			effort: {type: 'string'},
			help: {type: 'boolean', short: 'h'},
			version: {type: 'boolean', short: 'v'},
		},
	});
	if (o.help || o.version) {
		console.log(o.help ? HELP : VERSION);
		return 0;
	}

	const themeName = (o.theme ?? process.env['DS_THEME'] ?? 'dark') as ThemeName;
	if (themeName !== 'dark' && themeName !== 'light') throw new UsageError(`--theme must be dark or light, not "${themeName}".`);
	if (o.color) {
		const depth = ({truecolor: 'hex', ansi16: 'ansi16', none: 'none'} as Record<string, Depth>)[o.color];
		if (!depth) throw new UsageError(`--color must be truecolor, ansi16 or none, not "${o.color}".`);
		setDepth(depth);
	}
	const look = (o.look ?? process.env['DS_LOOK'] ?? 'rule').trim().toLowerCase() as LookName;
	if (!LOOKS.includes(look)) throw new UsageError(`--look must be rule or rail, not "${look}".`);
	const theme = makeTheme(themeName); // the tour, the spec and the page are Rule's own
	const drawn = makeTheme(themeName, undefined, false, look); // what --look draws
	const themes: ThemeName[] = o['one-theme'] ? [themeName] : ['dark', 'light'];
	const [cmd = 'tour', arg] = positionals;

	switch (cmd) {
		case 'tour': {
			const only = int(o.chapter, '--chapter', 0, CHAPTERS.length - 1);
			const from = int(o.from, '--from', 0, CHAPTERS.length - 1) ?? 0;
			if (only !== undefined) {
				printOnce(theme, <ChapterView index={only} themes={themes} />);
				return 0;
			}
			if (o['no-pause'] || !interactive()) {
				for (let i = from; i < CHAPTERS.length; i++) printOnce(theme, <ChapterView index={i} themes={themes} />);
				return 0;
			}
			await live(theme, <Tour start={from} themes={themes} />);
			return 0;
		}
		case 'chapters':
			CHAPTERS.forEach((c, i) => console.log(`${String(i).padStart(3)}  ${c.title}`));
			return 0;
		case 'screen': {
			if (look === 'rail') {
				const n = int(arg, 'screen', 1, RAIL_SCREENS.length);
				for (const k of n ? [n] : RAIL_SCREENS.map((_, i) => i + 1)) printOnce(drawn, <RailScreen index={k - 1} themes={themes} />);
				return 0;
			}
			const n = int(arg, 'screen', 1, 7);
			for (const k of n ? [n] : [1, 2, 3, 4, 5, 6, 7]) printOnce(theme, <ChapterView index={CHAPTERS.findIndex(c => c.title.startsWith(`Screen ${k} `))} themes={themes} />);
			return 0;
		}
		case 'spec':
			if (o.json) {
				console.log(JSON.stringify(spec.asJson(), null, 2));
				return 0;
			}
			for (let i = 0; i < CHAPTERS.length; i++) printOnce(theme, <ChapterView index={i} themes={[themeName]} />);
			return 0;
		case 'html': {
			const out = o.out ?? (look === 'rail' ? 'rail-screens.html' : 'rule-tour.html');
			writeFileSync(out, look === 'rail' ? buildRail() : build(), 'utf8');
			console.log(out);
			return 0;
		}
		case 'demo':
			if (!interactive()) {
				console.error('rule demo needs an interactive terminal: run it directly, not through a pipe.');
				return 1;
			}
			if (look === 'rail') {
				// Rail's demo is the agent terminal itself, with a scripted agent in place of a model.
				const cwd = process.cwd();
				await live(drawn, <AgentApp backend="cortex" label="demo agent" open={scripted()} cwd={cwd} width={process.stdout.columns ?? GRID.designWidth} look={LOOK.rail} desk={readDesk(cwd)} />, {exitOnCtrlC: false});
				return 0;
			}
			await live(theme, <Demo width={process.stdout.columns ?? GRID.designWidth} />);
			return 0;
		case 'agent': {
			if (o.agent && o.agent !== 'cortex' && o.agent !== 'claude') throw new UsageError(`--agent must be cortex or claude, not "${o.agent}".`);
			if (!interactive()) {
				console.error('rule agent needs an interactive terminal: run it directly, not through a pipe.');
				return 1;
			}
			const backend = chooseBackend(o.agent);
			const cwd = process.cwd();
			await live(
				drawn,
				<AgentApp backend={backend} open={openSession} cwd={cwd} width={process.stdout.columns ?? GRID.designWidth} model={o.model} connection={o.connection} effort={o.effort} look={LOOK[look]} desk={readDesk(cwd)} />,
				{exitOnCtrlC: false}, // the look decides: Rule leaves, Rail interrupts and leaves on a second press
			);
			return 0;
		}
		default:
			throw new UsageError(`unknown command "${cmd}".`);
	}
}

main(process.argv.slice(2)).then(
	code => {
		process.exitCode = code;
	},
	(err: unknown) => {
		// parseArgs reports unknown options with ERR_PARSE_ARGS_* codes; treat those as usage errors too.
		const usage = err instanceof UsageError || (err as {code?: string}).code?.startsWith('ERR_PARSE_ARGS');
		console.error(`rule: ${(err as Error).message}${usage ? '\nRun `rule --help` for the commands.' : ''}`);
		process.exitCode = usage ? 2 : 1;
	},
);
