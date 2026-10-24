#!/usr/bin/env node
// rule: the Rule terminal design system as a runnable reference CLI.
import {render, renderToString} from 'ink';
import {writeFileSync} from 'node:fs';
import {parseArgs} from 'node:util';
import type {ReactNode} from 'react';
import {Demo} from './demo/Demo.js';
import {build} from './html.js';
import * as spec from './spec.js';
import {type Depth, makeTheme, setDepth, type Theme, ThemeContext} from './theme.js';
import {GRID, type ThemeName} from './tokens.js';
import {CHAPTERS} from './tour/chapters.js';
import {ChapterView, Tour} from './tour/Tour.js';

const VERSION = '0.1.0';

const HELP = `rule: the Rule terminal design system, walked through.

  rule                     walk through every part of the spec (same as \`rule tour\`)
  rule tour [-c N]         the walkthrough, or one chapter of it
  rule chapters            list the chapters
  rule screen [N]          print screen N (1-7), or all seven, in dark and light
  rule spec [--json]       the spec as text, or as data
  rule html [-o FILE]      the tour as one web page, for reading on a phone
  rule demo                a live session drawn in Rule

Options
  --theme dark|light       theme for the prose and the demo (default: $DS_THEME, else dark)
  --color truecolor|ansi16|none
                           force the colour depth (default: what the terminal supports)
  --one-theme              show each mockup in --theme only, not dark and light
  --no-pause               print the tour straight through
  --from N                 start the tour at chapter N
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

async function live(theme: Theme, node: ReactNode): Promise<void> {
	const app = render(<ThemeContext.Provider value={theme}>{node}</ThemeContext.Provider>);
	await app.waitUntilExit();
}

const interactive = () => Boolean(process.stdin.isTTY && process.stdout.isTTY);

async function main(argv: string[]): Promise<number> {
	const {values: o, positionals} = parseArgs({
		args: argv,
		allowPositionals: true,
		options: {
			theme: {type: 'string'},
			color: {type: 'string'},
			'one-theme': {type: 'boolean'},
			'no-pause': {type: 'boolean'},
			from: {type: 'string'},
			chapter: {type: 'string', short: 'c'},
			json: {type: 'boolean'},
			out: {type: 'string', short: 'o'},
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
	const theme = makeTheme(themeName);
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
			const out = o.out ?? 'rule-tour.html';
			writeFileSync(out, build(), 'utf8');
			console.log(out);
			return 0;
		}
		case 'demo':
			if (!interactive()) {
				console.error('rule demo needs an interactive terminal: run it directly, not through a pipe.');
				return 1;
			}
			await live(theme, <Demo width={process.stdout.columns ?? GRID.designWidth} />);
			return 0;
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
