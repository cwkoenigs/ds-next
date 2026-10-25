// Rail tokens: ds-next's own terminal design system (the blue one, with the dog and the cat), as
// ds-next ships it in src/ds_next/ui_style.py. Same values; composite Rich styles ("bold #1d1f20 on
// #749dc4") are split into a role, a ground role and bold, which is how spans carry them here.
import type {ThemeName} from '../tokens.js';

export type RailRole = 'text' | 'muted' | 'dim' | 'rule' | 'accent' | 'strong' | 'brand' | 'ok' | 'warn' | 'err' | 'surface' | 'hl' | 'eye' | 'bg';

export const PALETTE: Record<ThemeName, Record<RailRole, string>> = {
	dark: {
		bg: '#1d1f20',
		surface: '#2b2b2d',
		text: '#e7e7ea',
		muted: '#98989b',
		dim: '#7a7a7d',
		rule: '#424244',
		accent: '#94bce3', // the agent's voice
		strong: '#b5d9fd', // yours, and the cat
		brand: '#749dc4', // the band, and the dog
		ok: '#7fd4a0',
		warn: '#e3c56b',
		err: '#ef8a7a',
		hl: '#2c455d', // the menu's current row
		eye: '#1d1f20', // the mascot's eyes and the text on a band: the terminal's ground
	},
	light: {
		bg: '#f2f2f3',
		surface: '#e9e9ea',
		text: '#1d1f20',
		muted: '#5d5d60',
		dim: '#7a7a7d',
		rule: '#d4d4d7',
		accent: '#416180',
		strong: '#2c455d',
		brand: '#5980a6',
		ok: '#2f7d4f',
		warn: '#8a6a12',
		err: '#b3402e',
		hl: '#c9dcee',
		eye: '#f2f2f3',
	},
};

/** ANSI-16 fallback, as ui_style.py has it. `inverse` stands for Rich's `reverse`. */
export const ANSI16: Record<RailRole, string | undefined> = {
	bg: undefined,
	text: undefined,
	muted: 'gray',
	dim: 'gray',
	rule: 'gray',
	accent: 'cyan',
	strong: 'cyan',
	brand: 'blue',
	ok: 'green',
	warn: 'yellow',
	err: 'red',
	surface: 'blackBright',
	hl: 'inverse',
	eye: 'black',
};

/** `strong` is "bold #b5d9fd": always bold. */
export const BOLD_ROLES = new Set<RailRole>(['strong']);

export const G = {
	prompt: '›', // you                 strong  col 1
	agent: '●', // agent text            accent  col 1
	run: '→', // tool call               muted   col 3
	result: '⎿', // first result line    dim     col 5
	rail: '│', // continuation           rule    col 1
	close: '╰', // turn footer           rule    col 1
	ok: '✓',
	warn: '⚠',
	err: '✗',
	select: '❯', // focused row          strong  col 2
	sep: ' · ',
	fold: '┄',
} as const;

export const SPINNER = {name: 'ds', frames: ['◐', '◓', '◑', '◒'], intervalMs: 125} as const;

export const GRID = {
	designWidth: 80,
	minWidth: 60,
	indent: 2, // agent text, tool calls → col 3
	resultIndent: 4, // tool results → col 5
	labelWidth: 12, // forms, /status → values at col 16
	bannerLeft: 30, // the banner's left pane
} as const;

/** The dog (steel) and the cat (light accent), arms around each other: 28×20 px, two pixel rows per
 *  cell in half-blocks. D dog · C cat · k eye/nose (the terminal's ground) · . empty */
export const MASCOT = [
	'............................',
	'................C......C....',
	'....DDDDDD......CC....CC....',
	'..DDDDDDDDDD....CCCCCCCCC...',
	'.DDDDDDDDDDDD..CCCCCCCCCCC..',
	'.DDDDDDDDDDDD..CCCCCCCCCCC..',
	'.DDDkkDDDkkDD..CCkkCCCCkkC..',
	'.DDDkkDDDkkDD..CCkkCCCCkkC..',
	'.DDDDDDDDDDDD..CCCCCCCCCCC..',
	'.DDDDDkkDDDDD..CCCCCkkCCCC..',
	'.DD.DDDDDD.DD...CCCCCCCCC...',
	'....DDDDDD........CCCCC.....',
	'..CCCDDDDDDDDDCCCCCCCCCDDD..',
	'..CDDDDDDDDDDDCCCCCCCCCCCD..',
	'..DDDDDDDDDDD..CCCCCCCCCC...',
	'..DDDDDDDDDDD..CCCCCCCCCC.C.',
	'..DDDDDDDDDDD..CCCCCCCCCCCC.',
	'..DDDDDDDDDDD..CCCCCCCCCC...',
	'..DDD..DDD.....CCC..CCC.....',
	'..DDD..DDD.....CCC..CCC.....',
] as const;

export const MASCOT_INKS: Record<string, RailRole> = {D: 'brand', C: 'strong', k: 'eye'};
