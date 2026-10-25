// The tour, interactive: each chapter is written into scrollback once; the line under it waits for
// enter. The motion chapter plays a live turn before the prompt comes back.
import {Box, Text, useApp, useInput} from 'ink';
import {useEffect, useState} from 'react';
import {LiveTurn} from '../components/LiveTurn.js';
import {Lines} from '../components/Lines.js';
import {Transcript, useTranscript} from '../components/transcript.js';
import {G, type ThemeName} from '../tokens.js';
import {type Chapter, CHAPTERS, landedTurn} from './chapters.js';
import {Header, R} from './doc.js';

export function ChapterView({index, themes, live = false}: {index: number; themes: ThemeName[]; live?: boolean}) {
	const ch = CHAPTERS[index] as Chapter;
	return (
		<Box flexDirection="column">
			<Header n={index} title={ch.title} />
			{ch.body({themes})}
			{ch.live && !live && <Lines rows={landedTurn()} />}
		</Box>
	);
}

export function Tour({start = 0, themes}: {start?: number; themes: ThemeName[]}) {
	const {exit} = useApp();
	const {log, printNode, printRows} = useTranscript();
	const [at, setAt] = useState(start);
	const [playing, setPlaying] = useState(false);
	const last = at >= CHAPTERS.length - 1;

	const show = (i: number) => {
		printNode(<ChapterView index={i} themes={themes} live />);
		if (CHAPTERS[i]!.live) setPlaying(true);
	};

	useEffect(() => show(start), []); // first chapter on mount

	useInput(
		(input, key) => {
			if (input === 'q' || key.escape || last) return exit();
			if (key.return || input === ' ') {
				setAt(at + 1);
				show(at + 1);
			}
		},
		{isActive: !playing},
	);

	return (
		<>
			<Transcript log={log} />
			{playing ? (
				<LiveTurn printRows={printRows} onDone={() => setPlaying(false)} />
			) : (
				<Box marginTop={1}>
					<Text>
						<R role="accentText">{G.prompt}</R>{' '}
						<R role="dim">{last ? 'end of the tour  enter quits' : `enter next  q quits  ${at + 1}/${CHAPTERS.length}  ${CHAPTERS[at + 1]!.title}`}</R>
					</Text>
				</Box>
			)}
		</>
	);
}
