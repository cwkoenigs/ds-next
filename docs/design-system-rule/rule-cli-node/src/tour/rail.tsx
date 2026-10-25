// Rail's screens in the terminal: `rule screen --look rail`. Each is a mockup in dark and light,
// painted on its own ground, with a line on what it shows.
import {Box} from 'ink';
import {SCREENS} from '../rail/screens.js';
import type {ThemeName} from '../tokens.js';
import {Gap, Header, Mocks, Para} from './doc.js';

export function RailScreen({index, themes}: {index: number; themes: ThemeName[]}) {
	const [title, note, rows] = SCREENS[index]!;
	return (
		<Box flexDirection="column">
			<Header n={index + 1} title={`Rail · ${title}`} />
			<Para role="muted">{note}</Para>
			<Gap />
			<Mocks rows={rows} themes={themes} />
		</Box>
	);
}
