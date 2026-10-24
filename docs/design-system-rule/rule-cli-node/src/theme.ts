// Theme: which palette (dark, light) at which colour depth. Hex colours go to chalk, which
// downsamples them for 256-colour terminals; ANSI-16 terminals get the named fallbacks.
import chalk from 'chalk';
import {createContext, useContext} from 'react';
import {ANSI16, BOLD_ROLES, PALETTE, type Role, type ThemeName} from './tokens.js';
import type {Span} from './text.js';

export type Depth = 'hex' | 'ansi16' | 'none';

export type Theme = {
	name: ThemeName;
	depth: Depth;
	/** Paint every span on the theme's own ground (for mockups shown in either terminal theme). */
	ground: boolean;
};

export function detectDepth(): Depth {
	if (chalk.level === 0) return 'none';
	return chalk.level === 1 ? 'ansi16' : 'hex';
}

/** Force a depth for this process (chalk is shared with Ink, so this reaches every component). */
export function setDepth(depth: Depth): void {
	chalk.level = depth === 'none' ? 0 : depth === 'ansi16' ? 1 : 3;
}

export function makeTheme(name: ThemeName = 'dark', depth: Depth = detectDepth(), ground = false): Theme {
	return {name, depth, ground};
}

export function colour(theme: Theme, role: Role | undefined): string | undefined {
	if (!role || theme.depth === 'none') return undefined;
	return theme.depth === 'hex' ? PALETTE[theme.name][role] : ANSI16[role];
}

/** Resolved Ink/chalk props for a span. */
export type Resolved = {color?: string; backgroundColor?: string; bold?: boolean; inverse?: boolean};

export function resolve(theme: Theme, sp: Span): Resolved {
	const ground = theme.ground && theme.depth === 'hex';
	const color = colour(theme, sp.role) ?? (ground ? PALETTE[theme.name].text : undefined);
	const backgroundColor = colour(theme, sp.bg) ?? (ground ? PALETTE[theme.name].bg : undefined);
	const bold = sp.bold || (sp.role !== undefined && BOLD_ROLES.has(sp.role)) || undefined;
	return {color, backgroundColor, bold, inverse: sp.inverse};
}

export const ThemeContext = createContext<Theme>(makeTheme());
export const useTheme = (): Theme => useContext(ThemeContext);
