// The Rule design system as Ink components. Each is a thin wrapper over a row builder, so a CLI can
// either compose components or print rows; both draw the same cells.
import * as b from '../builders.js';
import type {Content, Row} from '../text.js';
import type {Role} from '../tokens.js';
import {Lines} from './Lines.js';

type W = {w?: number};

/** ━━ 03 ━━━… before every prompt. */
export const TurnRule = ({n, w}: {n: number} & W) => <Lines rows={[b.turnRule(n, w)]} />;

/** › what you typed, echoed flat. */
export const You = ({children}: {children: Content}) => <Lines rows={[b.you(children)]} />;

/** ■ agent text; a string wraps to the text column. */
export const Agent = ({body, w}: {body: string | Content[]} & W) => <Lines rows={b.agent(body, w)} />;

/** An uppercase heading inside agent text. */
export const Heading = ({children}: {children: string}) => <Lines rows={[b.heading(children)]} />;

/** ▪ Name args, with its └ result and optional fold. */
export const Tool = ({name, args, state, result, more, error}: {name: string; args?: string; state?: b.ToolState; result?: string; more?: number; error?: boolean}) => (
	<Lines rows={[b.tool(name, args, state), ...(result === undefined ? [] : b.result(result, more, {error}))]} />
);

/** Dim reasoning lines with a · lead. */
export const Thinking = ({lines}: {lines: string[]}) => <Lines rows={lines.map((l, i) => b.thinking(l, i === 0))} />;

/** The folded thinking line. */
export const Thought = ({secs}: {secs: number}) => <Lines rows={[b.thought(secs)]} />;

/** ✓ ⚠ ✗ for local commands: ink for done, red for anything that needs you. */
export const Outcome = ({kind, subject, detail}: {kind: 'ok' | 'warn' | 'err'; subject: string; detail?: string}) => (
	<Lines rows={[b.outcome(kind, subject, detail)]} />
);

/** Dim facts, two spaces apart. */
export const Facts = ({items}: {items: string[]}) => <Lines rows={[b.facts(...items)]} />;

/** label at col 3, value at col 16. */
export const Labelled = ({label, children, upper}: {label: string; children: Content; upper?: boolean}) => (
	<Lines rows={[b.labelled(label, children, {upper})]} />
);

/** A heavy square frame; `edge="accent"` while it is asking. */
export const Frame = ({rows, edge, title, w}: {rows: (Row | null)[]; edge?: Role; title?: Row} & W) => <Lines rows={b.frame(rows, {edge, title, w})} />;

/** A static dialog (see DialogPicker for the live one). */
export const Dialog = ({title, body, options, focus, w}: {title: string; body: Content[]; options: Content[]; focus?: number} & W) => (
	<Lines rows={b.dialog(title, body, options, {focus, w})} />
);

/** The bare row under the box. */
export const StatusRow = ({left, right, w}: {left: string; right: string} & W) => <Lines rows={[b.statusRow(left, right, w)]} />;

/** The slash popup. */
export const Popup = ({items, selected}: {items: readonly (readonly [string, string])[]; selected?: number}) => <Lines rows={b.popupRows(items, selected)} />;

/** The heavy two-pane banner with the canoe. */
export const Banner = ({version, facts, hints, tagline, w}: {version: string; facts: [string, string][]; hints: string[]; tagline: string} & W) => (
	<Lines rows={b.banner(version, facts, hints, tagline, w)} />
);
