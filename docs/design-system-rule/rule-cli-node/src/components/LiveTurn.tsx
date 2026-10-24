// One agent turn, played live: thinking streams dim then folds, each tool runs under the spinner and
// lands in place, the reply prints. The agent is faked; the motion is the spec's.
import {Box, Text, useInput} from 'ink';
import {useEffect, useRef, useState} from 'react';
import * as b from '../builders.js';
import * as S from '../screens.js';
import type {Row} from '../text.js';
import {Lines} from './Lines.js';
import {Working} from './live.js';

export function LiveTurn({printRows, onDone, fast = false}: {printRows: (rows: Row[]) => void; onDone: (interrupted: boolean) => void; fast?: boolean}) {
	const [live, setLive] = useState<{rows: Row[]; verb: string}>({rows: [], verb: 'Drafting'});
	const [start] = useState(() => Date.now());
	const stopped = useRef(false);

	useInput((_input, key) => {
		if (key.escape) stopped.current = true;
	});

	useEffect(() => {
		const wait = (ms: number) => new Promise(r => setTimeout(r, fast ? 1 : ms));
		const interrupted = () => {
			if (!stopped.current) return false;
			setLive({rows: [], verb: ''});
			printRows([b.outcome('warn', 'interrupted', 'tell ds-next what to do instead'), []]);
			onDone(true);
			return true;
		};
		void (async () => {
			const shown: Row[] = [];
			for (const [i, t] of S.THINKING.entries()) {
				shown.push(b.thinking(t, i === 0));
				setLive({rows: [...shown], verb: 'Drafting'});
				await wait(800);
				if (interrupted()) return;
			}
			// The thinking folds to one line; the opening reply lands under it.
			printRows([b.thought(Math.max(1, (Date.now() - start) / 1000)), ...S.opening(), []]);
			for (const t of S.TOOLS) {
				setLive({rows: [b.tool(t.name, t.args, 'running'), ...b.result('…')], verb: t.verb});
				await wait(1100);
				if (interrupted()) return;
				printRows([b.tool(t.name, t.args), ...b.result(t.result, t.more)]); // the ▪ lands where the ▫ was
			}
			setLive({rows: [], verb: ''});
			printRows([[], ...S.done(), []]);
			onDone(false);
		})();
	}, []); // the script runs once per mount

	if (!live.verb) return null;
	return (
		<Box flexDirection="column">
			<Lines rows={live.rows} />
			{live.rows.length > 0 && <Text> </Text>}
			<Working verb={live.verb} since={start} />
			<Text> </Text>
		</Box>
	);
}
