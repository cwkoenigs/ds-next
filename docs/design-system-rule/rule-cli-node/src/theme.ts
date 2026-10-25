// Theme: which look (Rule, Rail), which palette (dark, light), at which colour depth. Hex colours go
// to chalk, which downsamples them for 256-colour terminals; ANSI-16 terminals get the named fallbacks.
import chalk from 'chalk';
import {createContext, useContext} from 'react';
import * as rail from './rail/tokens.js';
import {ANSI16, BOLD_ROLES, type LookName, PALETTE, type Role, type ThemeName} from './tokens.js';
import type {Span} from './text.js';

export type Depth = 'hex' | 'ansi16' | 'none';

export type Theme = {
	name: ThemeName;
	depth: Depth;
	/** Paint every span on the theme's own ground (for mockups shown in either terminal theme). */
	ground: boolean;
	look: LookName;
};

type Inks = {palette: Record<ThemeName, Partial<Record<Role, string>>>; ansi16: Partial<Record<Role, string>>; bold: ReadonlySet<Role>};
export const INKS: Record<LookName, Inks> = {
	rule: {palette: PALETTE, ansi16: ANSI16, bold: BOLD_ROLES},
	rail: {palette: rail.PALETTE, ansi16: rail.ANSI16, bold: rail.BOLD_ROLES},
};

export function detectDepth(): Depth {
	if (chalk.level === 0) return 'none';
	return chalk.level === 1 ? 'ansi16' : 'hex';
}

/** Force a depth for this process (chalk is shared with Ink, so this reaches every component). */
export function setDepth(depth: Depth): void {
	chalk.level = depth === 'none' ? 0 : depth === 'ansi16' ? 1 : 3;
}

export function makeTheme(name: ThemeName = 'dark', depth: Depth = detectDepth(), ground = false, look: LookName = 'rule'): Theme {
	return {name, depth, ground, look};
}

/** A role's colour in this theme. ANSI-16 `inverse` is not a colour; resolve() turns it into reverse video. */
export function colour(theme: Theme, role: Role | undefined): string | undefined {
	if (!role || theme.depth === 'none') return undefined;
	const inks = INKS[theme.look];
	const c = theme.depth === 'hex' ? inks.palette[theme.name][role] : inks.ansi16[role];
	return c === 'inverse' ? undefined : c;
}

/** Resolved Ink/chalk props for a span. */
export type Resolved = {color?: string; backgroundColor?: string; bold?: boolean; inverse?: boolean};

export function resolve(theme: Theme, sp: Span): Resolved {
	const inks = INKS[theme.look];
	const ground = theme.ground && theme.depth === 'hex';
	const color = colour(theme, sp.role) ?? (ground ? inks.palette[theme.name].text : undefined);
	const backgroundColor = colour(theme, sp.bg) ?? (ground ? inks.palette[theme.name].bg : undefined);
	const bold = sp.bold || (sp.role !== undefined && inks.bold.has(sp.role)) || undefined;
	const reverse = theme.depth === 'ansi16' && sp.bg !== undefined && inks.ansi16[sp.bg] === 'inverse';
	return {color, backgroundColor, bold, inverse: sp.inverse || reverse || undefined};
}

export const ThemeContext = createContext<Theme>(makeTheme());
export const useTheme = (): Theme => useContext(ThemeContext);
