// The append-only transcript. Whatever is printed here is written into scrollback once and never
// redrawn (Ink's <Static>); only the footing below it repaints.
import {Box, Static} from 'ink';
import {type ReactNode, useCallback, useRef, useState} from 'react';
import type {Row} from '../text.js';
import {Lines} from './Lines.js';

type Entry = {id: number; node: ReactNode};

export function useTranscript() {
	const [log, setLog] = useState<Entry[]>([]);
	const next = useRef(0);
	const printNode = useCallback((node: ReactNode) => setLog(l => [...l, {id: next.current++, node}]), []);
	const printRows = useCallback((rows: Row[]) => printNode(<Lines rows={rows} />), [printNode]);
	return {log, printNode, printRows};
}

export function Transcript({log}: {log: Entry[]}) {
	return (
		<Static items={log}>
			{e => (
				<Box key={e.id} flexDirection="column">
					{e.node}
				</Box>
			)}
		</Static>
	);
}
