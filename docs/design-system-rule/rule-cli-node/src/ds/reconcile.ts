// `reconcile`: offline, deterministic, read-only. Compares a repo's manifest with the canon. A port of
// ds-next's reconcile.py. Pending standards are information; only a malformed manifest or a broken
// pointer is an error, so the pre-push hook never blocks on a standard nobody has decided on yet.
import {lstatSync, readdirSync} from 'node:fs';
import {basename, dirname, join} from 'node:path';
import {parse as parseToml, TomlDate} from 'smol-toml';
import {Canon, isFile, readText} from './kb.js';
import {pyRepr, pyReprValue, resolvePath, today as todayIso} from './py.js';

const STATUSES = ['adopted', 'declined', 'pending'];

export class Report {
	tags: string[] = [];
	adopted: string[] = [];
	declined = new Map<string, string>();
	pending: string[] = []; // "id vN" strings
	overdue: string[] = []; // declines past their revisit date
	blocks: string[] = []; // "id vN" of accepted code in use
	type = ''; // project type from the scaffold
	outputs: string[] = [];
	errors: string[] = [];

	constructor(public repo: string) {}

	get ok(): boolean {
		return !this.errors.length;
	}

	summary(): string {
		return `${this.repo}: ${this.counts()}`;
	}

	/** 26 adopted · 1 declined · 0 pending (errors only when there are any). */
	counts(): string {
		const s = `${this.adopted.length} adopted · ${this.declined.size} declined · ${this.pending.length} pending`;
		return s + (this.errors.length ? ` · ${this.errors.length} errors` : '');
	}
}

export function findRepo(start: string): string | undefined {
	let p = resolvePath(start);
	while (true) {
		if (isFile(join(p, '.ds', 'manifest.toml'))) return p;
		const up = dirname(p);
		if (up === p) return undefined;
		p = up;
	}
}

const SKIP_DIRS = new Set(['.git', '.venv', 'venv', 'node_modules', 'site', 'build', 'dist', '__pycache__']);

/** Every Markdown file a person would read, skipping hidden, generated and vendored directories,
 *  in the order Python sorts paths (part by part). */
function docs(repo: string): string[] {
	const out: string[][] = [];
	const walk = (parts: string[]) => {
		let names: string[];
		try {
			names = readdirSync(join(repo, ...parts));
		} catch {
			return;
		}
		for (const name of names) {
			const st = lstatSync(join(repo, ...parts, name));
			if (st.isDirectory()) {
				if (!SKIP_DIRS.has(name) && !name.startsWith('.')) walk([...parts, name]);
			} else if (st.isFile() && name.endsWith('.md')) out.push([...parts, name]);
		}
	};
	walk([]);
	const cmp = (a: string[], b: string[]) => {
		for (let i = 0; i < Math.min(a.length, b.length); i++) if (a[i] !== b[i]) return a[i]! < b[i]! ? -1 : 1;
		return a.length - b.length;
	};
	return out.sort(cmp).map(p => p.join('/'));
}

type Entry = Record<string, unknown>;
const isTable = (x: unknown): x is Entry => typeof x === 'object' && x !== null && !Array.isArray(x) && !(x instanceof Date);

/** A version: a whole number from 1 up (not a bool, not a float). */
function version(e: Entry): number | undefined {
	const v = e['version'];
	return typeof v === 'number' && Number.isInteger(v) && v >= 1 ? v : undefined;
}

/** Accepted code in use, and which copies are behind the canon. Runs even when the rest of the
 *  manifest is broken, so a stale block is never hidden behind another error. */
function checkBlocks(manifest: Entry, canon: Canon, rep: Report): void {
	let blocks = manifest['blocks'] ?? {};
	if (!isTable(blocks) || !Object.values(blocks).every(isTable)) {
		rep.errors.push('[blocks] must hold one table per block, like [blocks.block-text-safety]');
		blocks = {};
	}
	for (const [bid, e] of Object.entries(blocks as Record<string, Entry>)) {
		const b = canon.blocks.get(bid);
		const v = version(e);
		if (!b) rep.errors.push(`manifest uses block ${bid}, which the canon does not have`);
		else if (v === undefined || v > b.version) rep.errors.push(`block ${bid}: version must be a whole number from 1 to v${b.version}, not ${pyReprValue(e['version'])}`);
		else {
			rep.blocks.push(`${bid} v${v}`);
			if (v < b.version) rep.pending.push(`${bid} v${b.version} (block; this repo has v${v})`);
		}
	}
}

/** A revisit date as YYYY-MM-DD, or undefined if it is not a date (a datetime is not a date). */
function revisitDate(v: unknown): string | undefined {
	if (v instanceof TomlDate) return v.isDate() ? v.toISOString().slice(0, 10) : undefined;
	if (typeof v !== 'string') return undefined;
	const m = /^(\d{4})-?(\d{2})-?(\d{2})$/.exec(v); // what date.fromisoformat takes
	if (!m) return undefined;
	const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
	const iso = `${m[1]}-${m[2]}-${m[3]}`;
	return d.toISOString().slice(0, 10) === iso ? iso : undefined;
}

/** Never throws on a bad manifest: every problem becomes an error line, so the hook and the terminal
 *  always get an answer. */
export function check(repoIn: string, canon = new Canon(), today = todayIso()): Report {
	const repo = resolvePath(repoIn);
	const rep = new Report(basename(repo));
	const path = join(repo, '.ds', 'manifest.toml');
	let manifest: Entry;
	if (!isFile(path)) {
		rep.errors.push('no .ds/manifest.toml (create the repo with ds-next new)');
		return rep;
	}
	try {
		manifest = parseToml(readText(path)) as Entry;
	} catch (err) {
		rep.errors.push(`manifest is not valid TOML: ${(err as Error).message.split('\n')[0]}`);
		return rep;
	}

	const head = manifest['repo'];
	if (!isTable(head)) {
		rep.errors.push('manifest has no [repo] table');
		return rep;
	}
	if (typeof head['name'] === 'string' && head['name']) rep.repo = head['name'];
	else rep.errors.push('[repo] name must be a non-empty string');
	const tags = head['tags'];
	if (!(Array.isArray(tags) && tags.length && tags.every(t => typeof t === 'string' && t))) {
		rep.errors.push('[repo] tags must be a non-empty list of strings');
		checkBlocks(manifest, canon, rep);
		return rep;
	}
	rep.tags = [...(tags as string[])];
	if (typeof head['type'] === 'string') rep.type = head['type'];
	const outs = head['outputs'] ?? [];
	if (Array.isArray(outs) && outs.every(o => typeof o === 'string' && o)) rep.outputs = [...(outs as string[])];
	const entries = manifest['standards'] ?? {};
	if (!isTable(entries) || !Object.values(entries).every(isTable)) {
		rep.errors.push('[standards] must hold one table per standard, like [standards.testing]');
		return rep;
	}

	for (const [sid, e] of Object.entries(entries as Record<string, Entry>)) {
		const status = e['status'];
		if (!canon.standards.has(sid)) {
			rep.errors.push(`manifest names ${sid}, which the canon does not have`);
			continue;
		}
		if (typeof status !== 'string' || !STATUSES.includes(status)) {
			rep.errors.push(`${sid}: status ${pyReprValue(status)} is not one of ${STATUSES.join(', ')}`);
			continue;
		}
		const decided = status === 'adopted' || status === 'declined';
		if (decided && version(e) === undefined) {
			rep.errors.push(`${sid}: version must be a whole number from 1 up, not ${pyReprValue(e['version'])}`);
			continue;
		}
		if (decided && !(typeof e['by'] === 'string' && e['by'].trim())) {
			rep.errors.push(`${sid}: by must name who decided, not ${pyReprValue(e['by'])}`);
			continue;
		}
		if (decided && version(e)! > canon.standards.get(sid)!.version) {
			rep.errors.push(`${sid}: ${status} at v${version(e)}, but the canon only has v${canon.standards.get(sid)!.version}`);
			continue;
		}
		if (status === 'declined') {
			const missing = [
				['reason', typeof e['reason'] === 'string' && e['reason'].trim()],
				['revisit', e['revisit'] !== undefined && e['revisit'] !== ''],
			].filter(([, ok]) => !ok).map(([k]) => k);
			if (missing.length) {
				rep.errors.push(`${sid}: a decline needs ${missing.join(', ')}`);
				continue;
			}
			const revisit = revisitDate(e['revisit']);
			if (!revisit) {
				rep.errors.push(`${sid}: revisit must be a date like 2027-01-31, not ${typeof e['revisit'] === 'string' ? pyRepr(e['revisit']) : pyReprValue(e['revisit'])}`);
				continue;
			}
			rep.declined.set(sid, String(e['reason']));
			if (revisit < today) rep.overdue.push(sid);
		}
	}

	for (const std of canon.applicable(rep.tags)) {
		const e = (entries as Record<string, Entry>)[std.id] ?? {};
		const status = e['status'];
		if (status === 'declined' && rep.declined.has(std.id)) {
			if ((version(e) ?? 0) >= std.version) continue;
			// a decline answers the version it was made against; a newer one is a new question
			rep.declined.delete(std.id);
			rep.overdue = rep.overdue.filter(s => s !== std.id);
			rep.pending.push(`${std.id} v${std.version} (declined at v${version(e)})`);
			continue;
		}
		if (status === 'adopted' && (version(e) ?? 0) >= std.version) rep.adopted.push(std.id);
		else if (!rep.errors.some(err => err.startsWith(`${std.id}:`))) rep.pending.push(`${std.id} v${std.version}`);
	}

	checkBlocks(manifest, canon, rep);

	for (const rel of docs(repo)) {
		let text: string;
		try {
			text = readText(join(repo, rel));
		} catch {
			continue;
		}
		rep.errors.push(...canon.pointerProblems(text).map(p => `${rel}: ${p}`));
	}
	return rep;
}
