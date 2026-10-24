// The tour: one chapter per section of the spec page, then one per screen.
import {Box, Text} from 'ink';
import type {ReactNode} from 'react';
import * as b from '../builders.js';
import {Lines} from '../components/Lines.js';
import * as S from '../screens.js';
import * as spec from '../spec.js';
import {useTheme} from '../theme.js';
import {row, s} from '../text.js';
import {ANSI16, G, GRID, MASCOT, type ThemeName} from '../tokens.js';
import {Gap, Mocks, Pairs, Para, R, Rule, Table} from './doc.js';

export type Chapter = {
	title: string;
	body: (o: {themes: ThemeName[]}) => ReactNode;
	/** Plays a live turn after the body when the tour is interactive. */
	live?: boolean;
};

function Swatch({hex}: {hex: string}) {
	const theme = useTheme();
	return theme.depth === 'hex' ? <Text backgroundColor={hex}>{'  '}</Text> : null;
}

const screenChapter = ([n, title, note]: readonly [number, string, string]): Chapter => ({
	title: `Screen ${n} · ${title}`,
	body: ({themes}) => (
		<>
			<Para role="muted">{note}</Para>
			<Gap />
			<Mocks rows={S.SCREENS[n]!} caption={String(n)} themes={themes} />
		</>
	),
});

export const CHAPTERS: Chapter[] = [
	{
		title: 'Rule',
		body: () => (
			<>
				<Para role="accentText">{`${spec.PRODUCT} · terminal design system · Modernist direction · ${spec.VERSION}`}</Para>
				<Gap />
				<Text bold>The grid shows.</Text>
				<Text bold>{spec.TAGLINE}</Text>
				<Gap />
				<Para>{spec.SUMMARY}</Para>
				<Gap />
				<Pairs items={spec.ASSUMPTIONS} labelWidth={12} />
			</>
		),
	},
	{
		title: 'Canopy vs Rule',
		body: ({themes}) => (
			<>
				<Para role="muted">The same turn. Canopy is warm and rounded; Rule is ink, red and square, with a numbered rule opening each turn.</Para>
				<Gap />
				<Mocks rows={S.ruleVsCanopy} caption="1b Rule" themes={themes} />
				<Table cols={[{title: 'Canopy', width: 24}, {title: 'Rule', width: 56}]} rows={spec.CHANGES_FROM_CANOPY.map(([a, r]) => [{text: a, role: 'dim'}, r])} />
			</>
		),
	},
	{
		title: 'Principles',
		body: () => (
			<>
				{spec.PRINCIPLES.map(([title, text], i) => (
					<Box key={title} flexDirection="column" marginBottom={1}>
						<Rule role="text" />
						<Text>
							<R role="accent" bold>{`${i + 1}  `}</R>
							<Text bold>{title}</Text>
						</Text>
						<Para role="muted">{text}</Para>
					</Box>
				))}
			</>
		),
	},
	{
		title: 'Colour roles',
		body: () => (
			<>
				<Para role="muted">
					Eight roles, both from Modernist's ramps. The dark theme inverts the page: ground = Modernist text, text = Modernist ground. There is no ok/warn/err triad: done is
					text, warn and err are red (err bold).
				</Para>
				<Gap />
				<Table
					cols={[{title: 'role', width: 12}, {title: 'dark', width: 18}, {title: 'light', width: 18}, {title: 'use', width: 32}]}
					rows={spec.COLOURS.map(([role, d, dt, l, lt, use]) => [
						role,
						<Text>
							<Swatch hex={d} /> {d}
							{'\n'}
							<R role="dim">{`   ${dt}`}</R>
						</Text>,
						<Text>
							<Swatch hex={l} /> {l}
							{'\n'}
							<R role="dim">{`   ${lt}`}</R>
						</Text>,
						{text: use, role: 'muted'},
					])}
				/>
				<Gap />
				<Lines rows={[b.labelled('ANSI-16', [s(Object.entries(ANSI16).filter(([, v]) => v).map(([k, v]) => `${k} ${v}`).join('  '), 'muted')], {upper: true})]} />
				<Gap />
				{spec.COLOUR_RULES.map(r => (
					<Text key={r}>
						<R role="accent">{G.agent}</R> {r}
					</Text>
				))}
				<Gap />
				<Para role="dim">In use, in this terminal's theme:</Para>
				{(['text', 'muted', 'dim', 'rule', 'accent', 'accentText'] as const).map(role => (
					<Text key={role}>
						{`  ${role.padEnd(12)}`}
						<R role={role}>{`the quick brown canoe ${G.agent} ${G.h.repeat(6)}`}</R>
					</Text>
				))}
			</>
		),
	},
	{
		title: 'Glyph vocabulary',
		body: () => (
			<>
				<Table
					cols={[{title: 'glyph', width: 13}, {title: 'name', width: 13}, {title: 'means', width: 30}, {title: 'colour', width: 14}, {title: 'column', width: 10}]}
					rows={spec.GLYPHS.map(([g, name, means, col, column]) => [
						{text: g, bold: true},
						name,
						{text: means, role: 'muted'},
						{text: col, role: 'dim'},
						{text: column, role: 'dim'},
					])}
				/>
				<Gap />
				<Para role="dim">{`Not used: ${spec.RETIRED.join(', ')}. The three systems never share a screen.`}</Para>
			</>
		),
	},
	{
		title: 'Grid and the footing',
		body: ({themes}) => (
			<>
				<Mocks rows={S.gridDiagram} caption="5a 80-column grid" themes={themes} />
				<Pairs items={spec.GRID_NOTES} />
				<Lines
					rows={[
						b.labelled('design width', String(GRID.designWidth)),
						b.labelled('min width', String(GRID.minWidth)),
						b.labelled('indent', String(GRID.indent)),
						b.labelled('result indent', String(GRID.resultIndent)),
						b.labelled('label width', String(GRID.labelWidth)),
						b.labelled('fact sep', 'two spaces'),
					]}
				/>
				<Gap />
				<Para>
					<Text bold>Case </Text>
					<R role="muted">{spec.CASE}</R>
				</Para>
			</>
		),
	},
	{
		title: 'Every message type',
		body: ({themes}) => <Mocks rows={S.messageTypes} caption="6 every message type" themes={themes} />,
	},
	{
		title: 'Dialogs',
		body: ({themes}) => (
			<>
				<Para role="muted">Heavy frame, red edge while asking, uppercase title flush left, numbered options with ■ on the focus and □ on the rest.</Para>
				<Gap />
				<Mocks rows={S.dialogReference} caption="7 permission" themes={themes} />
			</>
		),
	},
	{
		title: 'Motion',
		live: true,
		body: () => (
			<>
				<Pairs items={spec.MOTION} />
				<Para role="dim">{`Spinner verbs: ${spec.VERBS.join(' · ')}. Tool runs may pass an explicit verb (Running tests).`}</Para>
				<Gap />
				<Para role="dim">A live turn, in this terminal:</Para>
				<Gap />
				<Lines rows={S.echo(2, 'add a --since flag to the metrics command')} />
			</>
		),
	},
	{
		title: 'Mascot',
		body: () => (
			<>
				<Para role="muted">{spec.MASCOT_NOTE}</Para>
				<Gap />
				<Lines rows={S.mascot()} />
				<Gap />
				<Para role="dim">The pixels (I = ink, R = red), two rows per half-block cell:</Para>
				<Lines rows={MASCOT.map(line => row('  ', ...[...line].map(ch => s(ch, ch === 'I' ? 'text' : ch === 'R' ? 'accent' : 'dim'))))} />
			</>
		),
	},
	{
		title: 'Where it lands in code',
		body: () => (
			<Table
				cols={[{title: 'token / helper', width: 16}, {title: 'in this package', width: 36}, {title: 'differs from Canopy', width: 28}]}
				rows={spec.CODE_MAP.map(([t, where, d]) => [{text: t, bold: true}, where, {text: d, role: 'muted'}])}
			/>
		),
	},
	...spec.SCREENS.map(screenChapter),
	{
		title: 'Known gaps',
		body: () => (
			<>
				{spec.KNOWN_GAPS.map(g => (
					<Box key={g} width={GRID.designWidth}>
						<Text>
							<R role="accent">{G.warn}</R> {g}
						</Text>
					</Box>
				))}
				<Gap />
				<Para role="dim">That's the whole system. `rule demo` runs a live session in it.</Para>
			</>
		),
	},
];

/** What the motion chapter shows when nothing can play live: the turn as it lands. */
export const landedTurn = () => [...S.turnBody(), [], ...S.summary()];
