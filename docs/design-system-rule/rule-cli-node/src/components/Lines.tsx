// Rows on screen. Every Rule component ends here: a row of spans becomes one Ink <Text> line.
import {Box, Text} from 'ink';
import {resolve, ThemeContext, useTheme} from '../theme.js';
import {fit, type Row} from '../text.js';
import {GRID, type ThemeName} from '../tokens.js';

export function Line({row}: {row: Row}) {
	const theme = useTheme();
	if (!row.length) return <Text> </Text>;
	return (
		<Text wrap="truncate-end">
			{row.map((sp, i) => {
				const r = resolve(theme, sp);
				return (
					<Text key={i} color={r.color} backgroundColor={r.backgroundColor} bold={r.bold} inverse={r.inverse}>
						{sp.text}
					</Text>
				);
			})}
		</Text>
	);
}

export function Lines({rows}: {rows: Row[]}) {
	return (
		<Box flexDirection="column">
			{rows.map((r, i) => (
				<Line key={i} row={r} />
			))}
		</Box>
	);
}

/** A terminal mockup painted on its own theme's ground, so dark and light both read in any terminal. */
export function Mock({rows, theme: name}: {rows: Row[]; theme: ThemeName}) {
	const theme = useTheme();
	return (
		<ThemeContext.Provider value={{...theme, name, ground: true}}>
			<Lines rows={rows.map(r => fit(r, GRID.designWidth))} />
		</ThemeContext.Provider>
	);
}
