// The knowledge base, read-only: the canon (standards, scaffolds, blocks, code; index.json says
// what is in it), skills-os (SKILL.md procedures) and docs-ds. A port of ds-next's kb.py: each is
// found by an environment variable, then beside the others under ~/Developer, ~/code or ~/.ds.
import {createHash} from 'node:crypto';
import {readdirSync, readFileSync, statSync} from 'node:fs';
import {homedir} from 'node:os';
import {join, sep} from 'node:path';
import {pyRepr} from './py.js';

export const POINTER_RE = /\[\[([a-z0-9-]+)(?:@(\d+))?\]\]/g;
// Code is not a claim: fenced blocks (``` or ~~~, three or more, closed by at least as many of the
// same character) and inline code spans are masked before pointers are read.
const CODE_RE = /^[ \t]{0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?(?:^[ \t]{0,3}\1[`~]*[ \t]*$|(?![\s\S]))|(`+)[^`\n][\s\S]*?\2/gm;
const PLACEHOLDER_RE = /\{\{([a-z_]+)\}\}/g;

/** A file as Python's read_text() gives it: UTF-8, with \r\n and \r read as \n. */
export const readText = (path: string): string => readFileSync(path, 'utf8').replace(/\r\n?/g, '\n');
export const isFile = (p: string): boolean => {
	try {
		return statSync(p).isFile();
	} catch {
		return false;
	}
};
export const isDir = (p: string): boolean => {
	try {
		return statSync(p).isDirectory();
	} catch {
		return false;
	}
};
/** A path as Python's Path(p) spells it: doubled separators, `.` parts and a trailing separator
 *  dropped, `..` kept (Path does not resolve it). The canon's path is written into manifests. */
export function purePath(p: string): string {
	const root = /^[\\/]/.test(p) ? sep : '';
	const parts = p.split(/[\\/]+/).filter(x => x && x !== '.');
	return root + parts.join(sep) || '.';
}

export const expandUser = (p: string): string => (p === '~' || p.startsWith('~/') ? homedir() + p.slice(1) : p);

function find(env: string, name: string): string | undefined {
	const set = process.env[env];
	if (set) return expandUser(set);
	for (const base of [join(homedir(), 'Developer'), join(homedir(), 'code'), join(homedir(), '.ds')]) {
		if (isDir(join(base, name))) return join(base, name);
	}
	return undefined;
}

export const canonPath = () => find('DS_CANON', 'canon');
export const skillsPath = () => find('DS_SKILLS', 'skills-os');
export const docsShellPath = () => find('DS_DOCS_SHELL', 'docs-ds');

/** Python's str.splitlines() line breaks. */
const LINE_BREAKS = /\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/;

/** Flat `key: value` front matter. Enough for canon and SKILL.md; not a YAML parser. */
export function frontMatter(text: string): [Record<string, string>, string] {
	if (!text.startsWith('---\n')) return [{}, text];
	const rest = text.slice(4);
	const at = rest.indexOf('\n---\n');
	const head = at < 0 ? rest : rest.slice(0, at);
	const body = at < 0 ? '' : rest.slice(at + 5);
	const meta: Record<string, string> = {};
	for (const line of head.split(LINE_BREAKS)) {
		const colon = line.indexOf(':');
		if (colon >= 0 && !line.startsWith(' ')) meta[line.slice(0, colon).trim()] = line.slice(colon + 1).trim().replace(/^"+|"+$/g, '');
	}
	return [meta, body.replace(/^\n+/, '')];
}

/** fnmatch.fnmatchcase: * ? [seq] [!seq], case-sensitive, nothing special about /. */
export function fnmatchcase(name: string, pattern: string): boolean {
	let re = '';
	for (let i = 0; i < pattern.length; i++) {
		const c = pattern[i]!;
		if (c === '*') re += '[\\s\\S]*';
		else if (c === '?') re += '[\\s\\S]';
		else if (c === '[') {
			let j = i + 1;
			if (pattern[j] === '!') j++;
			if (pattern[j] === ']') j++;
			while (j < pattern.length && pattern[j] !== ']') j++;
			if (j >= pattern.length) re += '\\[';
			else {
				let set = pattern.slice(i + 1, j).replace(/\\/g, '\\\\');
				if (set.startsWith('!')) set = '^' + set.slice(1);
				else if (set.startsWith('^')) set = '\\' + set;
				re += `[${set}]`;
				i = j;
			}
		} else re += c.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');
	}
	return new RegExp(`^(?:${re})$`).test(name);
}

export type Standard = {
	id: string;
	version: number;
	title: string;
	appliesTo: string[];
	owner: string;
	status: string;
	path: string;
	kind: string; // "standard" or "gotcha": a lesson, adopted like any standard
};

export const applies = (s: Standard, tags: readonly string[]): boolean => s.appliesTo.some(p => p === '*' || tags.some(t => fnmatchcase(t, p)));

/** An accepted project shape from the canon: templates plus the tags it gives a repo. */
export type Scaffold = {
	id: string;
	version: number;
	title: string;
	path: string[]; // menu path, e.g. ["python", "cli"]
	tags: string[];
	status: string;
	defaults: Record<string, string>;
	dir: string;
	files: string[];
	hash: string;
	type: string; // cli, library, analysis, streamlit-app, ml-pipeline
	outputs: string[]; // report, dashboard, model, features
	accepted: boolean;
};

/** Accepted code from the canon: one tested module a repo pulls instead of rewriting. */
export type Block = {
	id: string;
	version: number;
	title: string;
	module: string;
	requires: string[];
	tags: string[];
	status: string;
	dir: string;
	tests: string[];
	hash: string;
	testRequires: string[];
	accepted: boolean;
};

/** One function, class or constant in a block, as index.json "code" records it. */
export type CodeSymbol = {
	id: string;
	block: string;
	name: string;
	kind: string;
	version: number;
	status: string;
	signature: string;
	summary: string;
	tags: string[];
	lessons: string[];
	needs: string[];
	lines: number;
};

/** A string literal that is valid JSON, Python, TOML and YAML (double-quoted) at once, for text
 *  that came from a person. Raw Unicode is kept; DEL, which TOML and YAML refuse, is escaped. */
export const jsonStr = (s: string): string => JSON.stringify(s).replace(/\x7f/g, '\\u007f');

/** One pass over the template: a value is never searched again, so user text that happens to
 *  contain `{{test_cmd}}` stays literal. */
export const fill = (text: string, values: Record<string, string>): string => text.replace(PLACEHOLDER_RE, (m, k: string) => values[k] ?? m);

export class CanonError extends Error {}
export class NotFound extends Error {}

const sha12 = (parts: Buffer[]): string => {
	const h = createHash('sha256');
	for (const p of parts) h.update(p);
	return h.digest('hex').slice(0, 12);
};

type Index = {standards: Map<string, Standard>; scaffolds: Map<string, Scaffold>; blocks: Map<string, Block>; code: Map<string, CodeSymbol>; generated: string};

export class Canon {
	readonly root: string;
	private stamp?: bigint;
	private data?: Index;

	constructor(root?: string) {
		const r = root ?? canonPath();
		if (!r || !isFile(join(r, 'index.json'))) throw new NotFound('canon not found: set DS_CANON or clone it to ~/Developer/canon');
		this.root = purePath(r);
	}

	/** index.json, re-read whenever it changes on disk, so a long session sees canon updates. */
	private index(): Index {
		const path = join(this.root, 'index.json');
		const stamp = statSync(path, {bigint: true}).mtimeNs;
		if (this.stamp !== stamp || !this.data) {
			const d = JSON.parse(readText(path)) as Record<string, any>;
			const list = (x: unknown): string[] => (Array.isArray(x) ? x.map(String) : []);
			this.data = {
				generated: String(d['generated'] ?? ''),
				standards: new Map(
					(d['standards'] as any[]).map(s => [
						s.id,
						{id: s.id, version: Number.parseInt(s.version, 10), title: s.title, appliesTo: list(s.applies_to), owner: s.owner ?? '', status: s.status ?? '', path: s.path, kind: s.kind ?? 'standard'},
					]),
				),
				blocks: new Map(
					((d['blocks'] ?? []) as any[]).map(b => [
						b.id,
						{
							id: b.id, version: Number.parseInt(b.version, 10), title: b.title, module: b.module, requires: list(b.requires), tags: list(b.tags),
							status: b.status ?? '', dir: b.dir, tests: list(b.tests), hash: b.hash ?? '', testRequires: list(b.test_requires), accepted: b.status === 'accepted',
						},
					]),
				),
				scaffolds: new Map(
					((d['scaffolds'] ?? []) as any[]).map(s => [
						s.id,
						{
							id: s.id, version: Number.parseInt(s.version, 10), title: s.title, path: list(s.path), tags: list(s.tags), status: s.status ?? '',
							defaults: {...(s.defaults ?? {})}, dir: s.dir, files: list(s.files), hash: s.hash ?? '', type: s.type ?? '', outputs: list(s.outputs), accepted: s.status === 'accepted',
						},
					]),
				),
				code: new Map(((d['code'] ?? []) as CodeSymbol[]).map(c => [c.id, c])),
			};
			this.stamp = stamp;
		}
		return this.data;
	}

	get standards() {
		return this.index().standards;
	}
	get scaffolds() {
		return this.index().scaffolds;
	}
	get blocks() {
		return this.index().blocks;
	}
	/** Every function, class and constant in the blocks, by "<block>:<name>". */
	get code() {
		return this.index().code;
	}
	/** index.json's "generated" stamp. */
	get generated() {
		return this.index().generated;
	}

	blockAbout(bid: string): string {
		return frontMatter(readText(join(this.root, this.blocks.get(bid)!.dir, 'BLOCK.md')))[1];
	}

	/** {repo path: text} for a block: its module under src/<package>/ and its tests under tests/
	 *  with {{package}} filled. Refuses a block whose files no longer match the index. */
	blockFiles(bid: string, pkg: string): Record<string, string> {
		const b = this.blocks.get(bid)!;
		const base = join(this.root, b.dir);
		const codeRel = `code/${b.module}.py`;
		const rels = [codeRel, ...b.tests.map(t => `tests/${t}`)];
		const digest = sha12([readFileSync(join(base, 'BLOCK.md')), ...rels.flatMap(r => [Buffer.from(r), readFileSync(join(base, r))])]);
		if (b.hash && digest !== b.hash) throw new CanonError(`block ${bid}: its files changed since index.json was built; run scripts/build_index.py in the canon (and bump its version)`);
		const out: Record<string, string> = {[`src/${pkg}/${b.module}.py`]: readText(join(base, codeRel))};
		for (const t of b.tests) out[`tests/${t}`] = fill(readText(join(base, 'tests', t)), {package: pkg});
		return out;
	}

	scaffoldAbout(sid: string): string {
		return frontMatter(readText(join(this.root, this.scaffolds.get(sid)!.dir, 'SCAFFOLD.md')))[1];
	}

	/** The hash build_index.py writes: SCAFFOLD.md, then each template's path and bytes. */
	scaffoldDigest(sid: string): string {
		const sc = this.scaffolds.get(sid)!;
		const base = join(this.root, sc.dir);
		return sha12([readFileSync(join(base, 'SCAFFOLD.md')), ...sc.files.flatMap(r => [Buffer.from(`files/${r}`), readFileSync(join(base, 'files', r))])]);
	}

	/** The scaffold's templates with {{placeholders}} filled. `__package__` in a path is the package
	 *  name; a leading `dot-` becomes `.`. Refuses templates that no longer match the index, and
	 *  template paths that could land outside the new repo. */
	renderScaffold(sid: string, values: Record<string, string>): Record<string, string> {
		const sc = this.scaffolds.get(sid)!;
		if (sc.hash && this.scaffoldDigest(sid) !== sc.hash) throw new CanonError(`scaffold ${sid}: its templates changed since index.json was built; run scripts/build_index.py in the canon (and bump its version)`);
		const out: Record<string, string> = {};
		for (const rel of sc.files) {
			const parts = rel.split('/').filter(p => p && p !== '.'); // as PurePosixPath reads it
			if (rel.startsWith('/') || parts.includes('..') || !parts.length) throw new CanonError(`scaffold ${sid}: template path ${pyRepr(rel)} is not a plain relative path`);
			const text = readText(join(this.root, sc.dir, 'files', rel));
			const target = parts.map(p => (p.startsWith('dot-') ? '.' + p.slice(4) : p)).join('/');
			out[target.replaceAll('__package__', values['package']!)] = fill(text, values);
		}
		return out;
	}

	applicable(tags: readonly string[]): Standard[] {
		return [...this.standards.values()].filter(s => applies(s, tags)).sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
	}

	read(sid: string): string {
		const s = this.standards.get(sid);
		if (!s) throw new NotFound(`no standard ${pyRepr(sid)} in the canon`);
		return frontMatter(readText(join(this.root, s.path)))[1];
	}

	/** What is wrong with the [[pointers]] in prose: an id the canon does not have, or a pin to a
	 *  version it never had. Code is skipped so a doc can talk about the syntax. */
	pointerProblems(text: string): string[] {
		const prose = text.replace(CODE_RE, '');
		const problems = new Set<string>();
		for (const m of prose.matchAll(POINTER_RE)) {
			const [, sid, pin] = m;
			const std = this.standards.get(sid!);
			if (!std) problems.add(`[[${sid}]] is not in the canon`);
			else if (pin !== undefined && !(Number(pin) >= 1 && Number(pin) <= std.version)) problems.add(`[[${sid}@${pin}]] pins a version the canon never had (current v${std.version})`);
		}
		return [...problems].sort();
	}
}

export type Skill = {name: string; description: string; path: string};
export const readSkill = (s: Skill): string => frontMatter(readText(s.path))[1];

export class Skills {
	readonly root?: string;
	private cached?: Map<string, Skill>;

	constructor(root?: string) {
		this.root = root ?? skillsPath();
	}

	get all(): Map<string, Skill> {
		if (this.cached) return this.cached;
		const out = new Map<string, Skill>();
		if (this.root && isDir(this.root)) {
			for (const dir of readdirSync(this.root).sort()) {
				const f = join(this.root, dir, 'SKILL.md');
				if (!isFile(f)) continue;
				const [meta] = frontMatter(readText(f));
				const name = meta['name'] ?? dir;
				out.set(name, {name, description: meta['description'] ?? '', path: f});
			}
		}
		return (this.cached = out);
	}
}

