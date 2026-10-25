// How an agent's tool calls read in Rule: a short name, the one argument that matters, a result
// as a fact (142 lines, +14 −1), and what the approval dialog says.
import {relative} from 'node:path';
import * as b from '../builders.js';
import {bold, type Row, s} from '../text.js';

/** Cortex names tools in lowercase (bash, web_fetch); Claude Code in PascalCase (Bash, WebFetch). */
const NAMES: Record<string, string> = {
	bash: 'Bash', read: 'Read', write: 'Write', edit: 'Edit', multiedit: 'MultiEdit', grep: 'Grep', glob: 'Glob',
	web_fetch: 'WebFetch', webfetch: 'WebFetch', web_search: 'WebSearch', websearch: 'WebSearch',
	notebook_edit: 'NotebookEdit', notebookedit: 'NotebookEdit', notebook_execute: 'NotebookExecute',
	task: 'Task', agent: 'Agent', todowrite: 'TodoWrite',
};

/** `mcp__ds__canon_read` → `canon_read`; `bash` → `Bash`. */
export function displayName(name: string): string {
	if (name.startsWith('mcp__')) return name.split('__').slice(2).join('__') || name;
	return NAMES[name.toLowerCase()] ?? name;
}

const str = (input: Record<string, unknown>, ...keys: string[]): string => {
	for (const k of keys) if (typeof input[k] === 'string' && input[k]) return input[k] as string;
	return '';
};

const oneLine = (t: string, max = 60) => {
	const line = t.split('\n')[0]!.trim();
	return line.length > max ? line.slice(0, max - 1) + '…' : line;
};

const linesIn = (t: string) => (t ? t.split('\n').length : 0);

/** The argument shown after the tool name, muted. */
export function toolArgs(name: string, input: Record<string, unknown>, cwd: string): string {
	const path = str(input, 'file_path', 'path', 'filePath', 'notebook_path');
	switch (displayName(name)) {
		case 'Bash':
			return oneLine(str(input, 'command', 'cmd'));
		case 'Read':
		case 'Write':
		case 'Edit':
		case 'MultiEdit':
		case 'NotebookEdit':
			return path ? relative(cwd, path) || path : '';
		case 'Grep':
		case 'Glob':
			return oneLine(str(input, 'pattern', 'query'));
		case 'WebFetch':
			return oneLine(str(input, 'url'));
		case 'WebSearch':
			return oneLine(str(input, 'query'));
		case 'Task':
		case 'Agent':
			return oneLine(str(input, 'description', 'prompt'));
		case 'TodoWrite':
			return Array.isArray(input['todos']) ? `${(input['todos'] as unknown[]).length} items` : '';
		default: {
			const first = Object.values(input).find(v => typeof v === 'string' && v) as string | undefined;
			return first ? oneLine(first) : '';
		}
	}
}

/** The └ line and how many more lines the fold hides. Errors read as their first line. */
export function resultSummary(name: string, input: Record<string, unknown>, text: string, isError: boolean): {first: string; more: number} {
	const clean = text.replace(/<\/?tool_use_error>/g, '').replace(/^ERROR: /, '').trim();
	if (isError) return {first: oneLine(clean, 70) || 'failed', more: Math.max(0, linesIn(clean) - 1)};
	switch (displayName(name)) {
		case 'Read':
			return {first: `${linesIn(clean)} lines`, more: 0};
		case 'Edit': {
			const add = linesIn(str(input, 'new_string'));
			const del = linesIn(str(input, 'old_string'));
			return {first: `+${add} −${del}`, more: 0};
		}
		case 'Write':
			return {first: `${linesIn(str(input, 'content'))} lines written`, more: 0};
		case 'Grep':
		case 'Glob':
			return {first: clean ? `${linesIn(clean)} found` : 'nothing found', more: 0};
		default: {
			const lines = clean.split('\n').filter(l => l.trim());
			return {first: lines.length ? oneLine(lines[0]!, 70) : 'done', more: Math.max(0, lines.length - 1)};
		}
	}
}

/** The landed tool line and its result rows. */
export function landed(name: string, input: Record<string, unknown>, cwd: string, text: string, isError: boolean): Row[] {
	const {first, more} = resultSummary(name, input, text, isError);
	return [b.tool(displayName(name), toolArgs(name, input, cwd), isError ? 'failed' : 'done'), ...b.result(first, more, {error: isError})];
}

/** Title and body of the approval dialog for a tool call. */
export function askContent(name: string, input: Record<string, unknown>, cwd: string, w: number): {title: string; body: Row[]} {
	const shown = displayName(name);
	const fit = (t: string) => oneLine(t, w - 6);
	switch (shown) {
		case 'Bash': {
			const cmd = str(input, 'command', 'cmd');
			const body: Row[] = cmd.split('\n').slice(0, 6).map(l => [bold(fit(l))]);
			const why = str(input, 'description');
			if (why) body.push([s(fit(why), 'muted')]);
			return {title: 'Bash command', body};
		}
		case 'Edit':
		case 'MultiEdit':
		case 'Write':
		case 'NotebookEdit': {
			const {first} = resultSummary(name, input, '', false);
			return {title: shown === 'Write' ? 'Write file' : 'Edit file', body: [[bold(fit(toolArgs(name, input, cwd)))], [s(first, 'muted')]]};
		}
		case 'WebFetch':
			return {title: 'Fetch', body: [[bold(fit(str(input, 'url')))], [s(fit(str(input, 'prompt')), 'muted')]]};
		default: {
			const json = JSON.stringify(input);
			return {title: shown.replace(/_/g, ' '), body: [[bold(shown)], [s(fit(json === '{}' ? 'no arguments' : json), 'muted')]]};
		}
	}
}
