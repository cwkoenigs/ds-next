// The canon's code library, one function at a time. A port of ds-next's code.py: search a symbol
// by what it does, read one with only what it needs, add just those symbols to a repo. Cutting a
// module down to some symbols works on Python's own syntax tree, so that part runs ds-next's
// functions in Python (python/code_cut.py); everything else is here.
import {spawnSync} from 'node:child_process';
import {appendFileSync, existsSync, mkdirSync, writeFileSync} from 'node:fs';
import {homedir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {Canon, type CodeSymbol, jsonStr} from './kb.js';
import {pyJsonDumps, pyRepr, resolvePath, today as todayIso, which} from './py.js';
import {addRequirements, ExistsError, gitUser, inside, InputError, repoPackage, setBlockTable} from './scaffold.js';

const STOP = new Set(['a', 'an', 'the', 'to', 'of', 'in', 'on', 'for', 'and', 'or', 'is', 'it', 'that', 'with', 'i', 'need', 'want', 'how', 'do', 'from', 'into', 'by', 'be', 'as', 'at', 'my', 'some', 'this', 'safely']);

function words(text: string): string[] {
	return (text.replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase().match(/[a-z0-9]+/g) ?? []).filter(w => !STOP.has(w));
}

// adr-001 (3): proposed code is served at once, labelled unreviewed; the owner's review makes it accepted
const SERVED = new Set(['accepted', 'proposed']);

export const label = (status: string): string => (status === 'accepted' ? '' : ` (${status}, unreviewed)`);

/** Served code symbols ranked by how well their name, summary and context match the query. */
export function search(canon: Canon, query: string, limit = 8): CodeSymbol[] {
	const terms = words(query);
	if (!terms.length) return [];
	const titles = new Map([...canon.blocks.values()].map(b => [b.id, b.title]));
	const scored: [number, CodeSymbol][] = [];
	for (const s of canon.code.values()) {
		if (!SERVED.has(s.status)) continue;
		const fields: [number, string[]][] = [
			[3, words(s.name)],
			[2, words(s.summary)],
			[1, [...words(s.signature), ...words(titles.get(s.block) ?? ''), ...s.tags, ...s.lessons]],
		];
		let score = 0;
		for (const t of terms) {
			score += Math.max(0, ...fields.filter(([, ws]) => ws.some(x => x === t || (t.length > 3 && x.startsWith(t.slice(0, 5))))).map(([w]) => w));
		}
		if (score) scored.push([score, s]);
	}
	return scored
		.sort(([a, x], [b, y]) => b - a || x.lines - y.lines || (x.id < y.id ? -1 : x.id > y.id ? 1 : 0))
		.slice(0, limit)
		.map(([, s]) => s);
}

// ── the Python cut ───────────────────────────────────────────────────────────

const HELPER = fileURLToPath(new URL('../../python/code_cut.py', import.meta.url));
let python: string[] | null | undefined; // undefined: not looked for yet; null: none found

/** A Python 3.10+ to run the cut with: $DS_PYTHON, then uv, then python3, python, py -3. */
function findPython(): string[] | null {
	if (python !== undefined) return python;
	const uv = which('uv');
	const candidates: string[][] = [
		...(process.env['DS_PYTHON'] ? [[process.env['DS_PYTHON']]] : []),
		...(uv ? [[uv, 'run', '--no-project', '--quiet', '--python', '>=3.10', 'python']] : []),
		...['python3', 'python'].flatMap(c => (which(c) ? [[which(c)!]] : [])),
		...(process.platform === 'win32' && which('py') ? [[which('py')!, '-3']] : []),
	];
	for (const c of candidates) {
		const r = spawnSync(c[0]!, [...c.slice(1), '-I', '-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'], {encoding: 'utf8', timeout: 120_000});
		if (r.status === 0) return (python = c);
	}
	return (python = null);
}

type Cut = {code: string; kept: string[]; tests: [string, string][]; third_party_code: boolean; third_party_tests: boolean[]};

function cut(req: {code: string; names: string[]; header: string; tests: [string, string][]; module_import: string; test_header: string}): Cut {
	const py = findPython();
	if (!py) throw new InputError('code_get and code_add need Python 3.10 or newer: install uv or python3, or set DS_PYTHON');
	const r = spawnSync(py[0]!, [...py.slice(1), '-I', HELPER], {input: JSON.stringify(req), encoding: 'utf8', maxBuffer: 64 * 1024 * 1024});
	if (r.status !== 0) throw new InputError(`cutting the code failed: ${(r.stderr || String(r.error ?? '')).trim().split('\n').slice(-1)[0]}`);
	return JSON.parse(r.stdout) as Cut;
}

type Piece = {symbols: string[]; code: [string, string]; tests: [string, string][]; block: string; version: number; thirdPartyCode: boolean; thirdPartyTests: boolean};

/** {block id: the module cut down to the ids' symbols, and the tests that use only them}. */
export function pieces(canon: Canon, ids: string[], pkg: string): Map<string, Piece> {
	const byBlock = new Map<string, Set<string>>();
	for (const sid of ids) {
		const s = canon.code.get(sid);
		if (!s) throw new InputError(`no code symbol ${pyRepr(sid)}; code_search finds them (ids look like block-x:name)`);
		if (!SERVED.has(s.status)) throw new InputError(`${sid} is in block ${s.block}, which is ${s.status}, not served`);
		if (!byBlock.has(s.block)) byBlock.set(s.block, new Set());
		byBlock.get(s.block)!.add(s.name);
	}
	const out = new Map<string, Piece>();
	for (const [bid, names] of byBlock) {
		const b = canon.blocks.get(bid)!;
		const files = canon.blockFiles(bid, pkg); // refuses files that changed since the index
		const codePath = `src/${pkg}/${b.module}.py`;
		const sorted = [...names].sort();
		const c = cut({
			code: files[codePath]!,
			names: sorted,
			header: `"""From the canon's ${bid} v${b.version}: ${sorted.join(', ')} and what they need.\nAdded with code_add; change it in the canon, not here."""\n`,
			tests: Object.entries(files).filter(([p]) => p.startsWith('tests/')),
			module_import: `${pkg}.${b.module}`,
			test_header: `"""Tests from the canon's ${bid} v${b.version}."""\n`,
		});
		out.set(bid, {symbols: sorted, code: [codePath, c.code], tests: c.tests, block: bid, version: b.version, thirdPartyCode: c.third_party_code, thirdPartyTests: c.third_party_tests.some(Boolean)});
	}
	return out;
}

export function get(canon: Canon, sid: string): string {
	const s = canon.code.get(sid);
	if (!s) throw new InputError(`no code symbol ${pyRepr(sid)}; code_search finds them`);
	const p = pieces(canon, [sid], 'yourpkg').get(s.block)!;
	const tests = p.tests.map(([path, text]) => `--- ${path}\n${text}`).join('\n') || '(no tests use only this)';
	return (
		`${sid}  (${s.kind}, block ${s.block} v${s.version})\n${s.signature}\n${s.summary}\n` +
		`needs: ${s.needs.join(', ') || '-'}  lessons: ${s.lessons.join(', ') || '-'}\n\n` +
		`--- ${p.code[0]}\n${p.code[1]}\n${tests}`
	);
}

/** Append what was pulled to ~/.ds/usage.jsonl ($DS_STATE overrides), the file ds-next writes, so a
 *  team sees what code is reused. Never fails the call. */
export function usageLog(event: string, ids: string[], repo?: string): void {
	try {
		const state = process.env['DS_STATE'] || join(homedir(), '.ds');
		mkdirSync(state, {recursive: true});
		const d = new Date();
		const p2 = (n: number) => String(n).padStart(2, '0');
		const at = `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}T${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`;
		appendFileSync(join(state, 'usage.jsonl'), pyJsonDumps({at, event, ids, repo: repo ?? null}) + '\n');
	} catch {
		// usage is a nicety; the call it records has already succeeded
	}
}

export type CodeAdded = {block: string; symbols: string[] | 'all'; files: string[]; requires?: string[]; manual?: string[]; note: string};

/** Add these code symbols to the repo: each block's module cut down to them (plus what they need),
 *  and the block tests that use only them. Merges with symbols added before; a repo that already has
 *  the whole block keeps it. */
export function add(repoIn: string, ids: string[], canon = new Canon(), by?: string, today = todayIso()): CodeAdded[] {
	const repo = resolvePath(repoIn);
	const {manifestPath, manifest, pkg, manifestText: text} = repoPackage(repo, 'code');
	let manifestText = text;
	const have = manifest.blocks ?? {};
	for (const sid of ids) {
		// every id is checked before anything is written
		const s = canon.code.get(sid);
		if (!s) throw new InputError(`no code symbol ${pyRepr(sid)}; code_search finds them (ids look like block-x:name)`);
		if (!SERVED.has(s.status)) throw new InputError(`${sid} is in block ${s.block}, which is ${s.status}, not served`);
	}
	if (!ids.length) throw new InputError('no ids given');
	const wanted = new Map<string, string[]>();
	for (const sid of ids) {
		const bid = sid.split(':', 1)[0]!;
		wanted.set(bid, [...(wanted.get(bid) ?? []), sid]);
	}
	const done: CodeAdded[] = [];
	for (const [bid, sids] of wanted) {
		const prior = have[bid];
		if (prior && !('symbols' in prior) && prior.version === canon.blocks.get(bid)?.version) {
			done.push({block: bid, symbols: 'all', note: 'the repo already has the whole block', files: []});
			continue;
		}
		const names = new Set(Array.isArray(prior?.symbols) ? (prior.symbols as unknown[]).map(String) : []);
		const allIds = [...new Set([...[...names].map(n => `${bid}:${n}`), ...sids])].sort();
		const p = pieces(canon, allIds, pkg).get(bid)!;
		const files: Record<string, string> = {[p.code[0]]: p.code[1], ...Object.fromEntries(p.tests)};
		const targets = Object.fromEntries(Object.keys(files).map(rel => [rel, inside(repo, rel)]));
		if (!prior) {
			const clash = Object.keys(targets).filter(rel => existsSync(targets[rel]!));
			if (clash.length) throw new ExistsError(`not added: ${clash.join(', ')} already exist and were not written from ${bid}`);
		}
		for (const [rel, text] of Object.entries(files)) {
			mkdirSync(join(targets[rel]!, '..'), {recursive: true});
			writeFileSync(targets[rel]!, text);
		}
		const b = canon.blocks.get(bid)!;
		const {added, manual} = addRequirements(repo, [
			['dependencies', p.thirdPartyCode ? b.requires : []],
			['dev', p.thirdPartyTests ? b.testRequires : []],
		]);
		const table =
			`[blocks.${bid}]\nversion = ${b.version}\nby = ${jsonStr(by ?? gitUser())}\n` +
			`on = "${today}"\nmodule = ${jsonStr(p.code[0])}\n` +
			`symbols = [${p.symbols.map(jsonStr).join(', ')}]\n`;
		manifestText = setBlockTable(manifestText, bid, table);
		done.push({block: bid, symbols: p.symbols, files: Object.keys(files).sort(), requires: added, manual, note: prior ? 'updated' : 'added'});
	}
	writeFileSync(manifestPath, manifestText);
	usageLog('code_add', ids, repo);
	return done;
}
