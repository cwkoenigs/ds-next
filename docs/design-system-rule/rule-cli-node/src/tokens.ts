// Rule tokens: the values in ../tokens.json, typed. Colour roles come from the Modernist ramps.
import type {RailRole} from './rail/tokens.js';

export type RuleRole = 'text' | 'muted' | 'dim' | 'rule' | 'accent' | 'accentText' | 'surface' | 'bg';
/** A span's role in either look; each look's palette colours its own (src/rail/tokens.ts for Rail). */
export type Role = RuleRole | RailRole;
export type ThemeName = 'dark' | 'light';
/** Rule (this design system) or Rail (ds-next's blue one, with the dog and the cat). */
export type LookName = 'rule' | 'rail';
export const LOOKS: readonly LookName[] = ['rule', 'rail'];

export const PALETTE: Record<ThemeName, Record<RuleRole, string>> = {
	dark: {
		bg: '#201e1d', // Modernist text
		surface: '#2d2b2b', // neutral-900
		text: '#f3f2f2', // Modernist bg
		muted: '#bab6b6', // neutral-400
		dim: '#7d7979', // neutral-600
		rule: '#9b9797', // neutral-500
		accent: '#ff563c', // accent-500
		accentText: '#ff9783', // accent-400
	},
	light: {
		bg: '#f3f2f2',
		surface: '#eae9e9',
		text: '#201e1d',
		muted: '#605d5d', // neutral-700
		dim: '#9b9797', // neutral-500
		rule: '#605d5d', // neutral-700
		accent: '#ec3013',
		accentText: '#ae1800', // accent-700
	},
};

/** ANSI-16 fallback: chalk colour names. Accent and accent text are both red; bold tells them apart. */
export const ANSI16: Record<RuleRole, string | undefined> = {
	bg: undefined,
	text: undefined,
	muted: 'gray',
	dim: 'gray',
	rule: 'gray',
	accent: 'red',
	accentText: 'red',
	surface: 'blackBright',
};

/** Roles that are always bold. */
export const BOLD_ROLES = new Set<RuleRole>(['accentText']);

export const G = {
	prompt: '›',
	agent: '■', // agent speaking · focused option          accent
	tool: '▪', // tool done (text) · failed (accent)
	pending: '▫', // tool running                          dim
	option: '□', // unselected dialog option               dim
	result: '└', // first result line · fold               dim
	think: '·', // thinking lead · fold · status-row separator
	ok: '✓',
	warn: '⚠',
	err: '✗',
	h: '━',
	v: '┃',
	tl: '┏',
	tr: '┓',
	bl: '┗',
	br: '┛',
	teeDown: '┳',
	teeUp: '┻',
	choice: ['‹', '›'],
} as const;

export const SPINNER = {name: 'quadrant', frames: ['▖', '▘', '▝', '▗'], intervalMs: 160} as const;

export const VERBS = [
	'Drafting', 'Ruling', 'Measuring', 'Squaring', 'Aligning', 'Plotting', 'Setting', 'Composing',
	'Inking', 'Paddling', 'Portaging', 'Sounding', 'Charting',
] as const;

export const GRID = {
	designWidth: 80,
	minWidth: 60,
	indent: 2, // speech, tool calls → col 3
	resultIndent: 4, // result text → col 5 (└ at col 3)
	labelWidth: 12,
	factSep: '  ', // two spaces between facts; no · in flow
	columns: {glyph: 1, text: 3, resultGlyph: 3, resultText: 5, formValue: 16},
} as const;

/** A canoe in ink with a red paddle and red water: 28×20 px, drawn two rows per cell in half-blocks. */
export const MASCOT = [
	'.......................RR...',
	'......................RRRR..',
	'......................RRRR..',
	'.....................RRRR...',
	'....................RR......',
	'...................RR.......',
	'..................RR........',
	'.................RR.........',
	'................RR..........',
	'...............RR...........',
	'..............RR............',
	'I............RR............I',
	'II..........RR............II',
	'IIIIIIIIIIIIIIIIIIIIIIIIIIII',
	'.IIIIIIIIIIIIIIIIIIIIIIIIII.',
	'..IIIIIIIIIIIIIIIIIIIIIIII..',
	'....IIIIIIIIIIIIIIIIIIII....',
	'.......IIIIIIIIIIIIII.......',
	'............................',
	'.RR.RR...RR.RR....RR.RR.RR..',
] as const;

export const MASCOT_INKS: Record<string, RuleRole> = {I: 'text', R: 'accent'};
