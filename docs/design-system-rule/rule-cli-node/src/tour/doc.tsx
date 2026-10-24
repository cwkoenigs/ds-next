// Prose pieces for the tour: Modernist section heads, paragraphs, label/value pairs, tables, and
// mockups shown in dark and light. Laid out at the 80-column design width.
import {Box, Text} from 'ink';
import {isValidElement, type ReactNode} from 'react';
import {Mock} from '../components/Lines.js';
import {colour, useTheme} from '../theme.js';
import {type Row, wrapWords} from '../text.js';
import {G, GRID, type Role, type ThemeName} from '../tokens.js';

const W = GRID.designWidth;

/** Ink's own wrap can start a continuation line with a space; wrap plain text ourselves. */
const wrap = (text: string, w: number) => wrapWords(text, w).join('\n');

/** Text in a colour role. */
export function R({role, bold, children}: {role?: Role; bold?: boolean; children: ReactNode}) {
	const theme = useTheme();
	return (
		<Text color={colour(theme, role)} bold={bold || role === 'accentText'}>
			{children}
		</Text>
	);
}

export const Rule = ({role = 'rule'}: {role?: Role}) => <R role={role}>{G.h.repeat(W)}</R>;

/** Ink chip with the chapter number, uppercase name, heavy rule under it. */
export function Header({n, title}: {n: number; title: string}) {
	return (
		<Box flexDirection="column" marginTop={1}>
			<Text>
				<Text inverse bold>{` ${String(n).padStart(2)} `}</Text>
				<Text>{'  '}</Text>
				<Text bold>{title.toUpperCase()}</Text>
			</Text>
			<Rule />
		</Box>
	);
}

export function Para({children, role}: {children: ReactNode; role?: Role}) {
	return (
		<Box width={W}>
			<R role={role}>{typeof children === 'string' ? wrap(children, W) : children}</R>
		</Box>
	);
}

export const Gap = () => <Text> </Text>;

/** Bold label, muted value; the value wraps in its own column. */
export function Pairs({items, labelWidth = 26}: {items: readonly (readonly [string, string])[]; labelWidth?: number}) {
	return (
		<Box flexDirection="column" width={W}>
			{items.map(([k, v]) => (
				<Box key={k} marginBottom={1}>
					<Box width={labelWidth} flexShrink={0}>
						<Text bold>{k}</Text>
					</Box>
					<Box width={W - labelWidth}>
						<R role="muted">{wrap(v, W - labelWidth)}</R>
					</Box>
				</Box>
			))}
		</Box>
	);
}

export type Col = {title: string; width: number};
/** A table cell: plain text, text in a role, or any node (not wrapped). */
export type Cell = string | {text: string; role?: Role; bold?: boolean} | ReactNode;

function CellView({cell, width}: {cell: Cell; width: number}) {
	if (typeof cell === 'string') return <Text>{wrap(cell, width)}</Text>;
	if (cell && typeof cell === 'object' && !isValidElement(cell) && 'text' in cell) {
		const c = cell as {text: string; role?: Role; bold?: boolean};
		return (
			<R role={c.role} bold={c.bold}>
				{wrap(c.text, width)}
			</R>
		);
	}
	return <>{cell as ReactNode}</>;
}

/** Header in dim caps, a heavy rule, then rows; each cell wraps inside its column. */
export function Table({cols, rows}: {cols: Col[]; rows: Cell[][]}) {
	return (
		<Box flexDirection="column" width={W}>
			<Box>
				{cols.map(c => (
					<Box key={c.title} width={c.width} flexShrink={0}>
						<R role="dim" bold>
							{c.title.toUpperCase()}
						</R>
					</Box>
				))}
			</Box>
			<Rule />
			{rows.map((r, i) => (
				<Box key={i}>
					{r.map((cell, j) => (
						<Box key={j} width={cols[j]!.width} flexShrink={0} paddingRight={1}>
							<CellView cell={cell} width={cols[j]!.width - 1} />
						</Box>
					))}
				</Box>
			))}
		</Box>
	);
}

/** A mockup in each theme (or just one), captioned. */
export function Mocks({rows, caption, themes}: {rows: () => Row[]; caption?: string; themes: ThemeName[]}) {
	return (
		<Box flexDirection="column">
			{themes.map(t => (
				<Box key={t} flexDirection="column" marginBottom={1}>
					{caption !== undefined && (
						<Text>
							<Text bold>{caption.toUpperCase()}</Text>
							<R role="dim">{`  ${t}`}</R>
						</Text>
					)}
					<Mock rows={rows()} theme={t} />
				</Box>
			))}
		</Box>
	);
}
