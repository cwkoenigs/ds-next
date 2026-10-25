// Answers in, a repository out. Deterministic: no model, no network. A port of ds-next's
// scaffold.py: the code skeleton is an accepted scaffold from the canon, never a template held
// here; every other file is local (from an answer) or inherited (a [[pointer]] into the canon).
import {spawnSync} from 'node:child_process';
import {chmodSync, existsSync, mkdirSync, readdirSync, renameSync, unlinkSync, writeFileSync} from 'node:fs';
import {basename, dirname, isAbsolute, join} from 'node:path';
import {parse as parseToml} from 'smol-toml';
import {Canon, expandUser, isDir, isFile, jsonStr, purePath, readText, Skills} from './kb.js';
import {addDays, isSymlink, pyRepr, pySlice, pyStr, resolvePath, shlexQuote, today as todayIso, which, within} from './py.js';

export const DS_VERSION = '0.1.0'; // written into manifests as ds_version, as ds-next writes its own

/** skills-os procedures worth naming in a new repo's AGENTS.md, in the order a project meets them. */
export const RECOMMENDED_SKILLS = ['so-build-feature-interview', 'so-bug-review-interview', 'so-best-practice-audit', 'so-capture', 'so-changes'];
const NAME_RE = /^[a-z][a-z0-9-]{1,40}$/;
const NAME_RULE = 'lowercase words joined by hyphens, like ds-next ([[repo-naming]])';
const TAG_RE = /^[a-z0-9][a-z0-9-]{0,30}$/;
// keyword.kwlist + keyword.softkwlist (Python 3.13), the ones a lowercase name can reach
const PY_KEYWORDS = new Set([
	'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except', 'finally', 'for', 'from',
	'global', 'if', 'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'try', 'while', 'with', 'yield',
	'case', 'match', 'type',
]);

/** A wrong answer: the agent is told and asks again (ValueError in ds-next). */
export class InputError extends Error {}
/** The target already has files (FileExistsError). */
export class ExistsError extends Error {}
/** The files were written but finishing the repo (git) failed; the message says where. */
export class ScaffoldError extends Error {}

/** What a person typed, bent toward the rule: lowercase, spaces and underscores to hyphens, nothing
 *  but a-z 0-9 and -. Leading hyphens and doubled hyphens are dropped as they appear. */
export function normalizeName(text: string): string {
	return text
		.toLowerCase()
		.replace(/[\s_]+/g, '-')
		.replace(/[^a-z0-9-]/g, '')
		.replace(/-{2,}/g, '-')
		.replace(/^-+/, '');
}

export function nameProblem(name: string): string | undefined {
	if (!NAME_RE.test(name) || name.endsWith('-') || name.includes('--')) return `${NAME_RULE}; 2 to 41 characters`;
	const pkg = name.replaceAll('-', '_');
	if (PY_KEYWORDS.has(pkg)) return `${pyRepr(name)} would make the package a Python keyword`;
	return undefined;
}

/** Every answer is a single line of printable text: it lands in Markdown, TOML, YAML and Python. */
function oneLine(label: string, value: string): void {
	const bad = /[\p{Cc}\p{Zl}\p{Zp}]/u.exec(value);
	if (bad) throw new InputError(`${label}: one line of text, without control characters (${pyRepr(bad[0])})`);
}

export function gitUser(): string {
	const r = spawnSync('git', ['config', 'user.name'], {encoding: 'utf8'});
	return (r.status === null && r.error ? '' : r.stdout?.trim()) || 'unknown';
}

export type Answers = {
	name: string;
	purpose: string;
	scaffold: string; // a canon scaffold id
	owner: string;
	test_cmd: string; // empty: the scaffold's default
	lint_cmd: string;
	tags: string[]; // extra tags beyond the scaffold's own
	snowflake: string; // DATABASE.SCHEMA, or empty
	notes: string;
	declines: Record<string, string>; // standard id -> reason
};

const FIELDS = ['name', 'purpose', 'scaffold', 'owner', 'test_cmd', 'lint_cmd', 'tags', 'snowflake', 'notes', 'declines'] as const;

/** Answers from loose input (a tool call, a form), checked as ds-next's Answers.__post_init__ checks them. */
export function answers(input: Record<string, unknown>): Answers {
	for (const k of Object.keys(input)) {
		if (!(FIELDS as readonly string[]).includes(k)) throw new InputError(`unexpected answer ${pyRepr(k)}; the answers are ${FIELDS.join(', ')}`);
	}
	if (input['name'] === undefined || input['purpose'] === undefined) throw new InputError('name and purpose are required');
	const str = (k: string, d = '') => (input[k] === undefined || input[k] === null ? d : String(input[k]));
	const rawTags = input['tags'];
	const a: Answers = {
		name: str('name'),
		purpose: str('purpose'),
		scaffold: str('scaffold', 'python-cli'),
		owner: input['owner'] === undefined ? gitUser() : str('owner'),
		test_cmd: str('test_cmd'),
		lint_cmd: str('lint_cmd'),
		tags: Array.isArray(rawTags) ? rawTags.map(String) : typeof rawTags === 'string' ? rawTags.split(',') : [],
		snowflake: str('snowflake'),
		notes: str('notes'),
		declines: Object.fromEntries(Object.entries((input['declines'] as Record<string, unknown>) ?? {}).map(([k, v]) => [k, String(v)])),
	};
	if (!NAME_RE.test(a.name) || a.name.endsWith('-') || a.name.includes('--')) throw new InputError(`name ${pyRepr(a.name)}: lowercase letters, digits and single dashes, 2-41 chars`);
	if (PY_KEYWORDS.has(pkgOf(a))) throw new InputError(`name ${pyRepr(a.name)}: ${pyRepr(pkgOf(a))} is a Python keyword, so it cannot be imported`);
	if (!a.purpose.trim()) throw new InputError('purpose: one line on what the repo does');
	if (!a.owner.trim()) throw new InputError('owner: who answers for this repo');
	for (const label of ['name', 'purpose', 'scaffold', 'owner', 'test_cmd', 'lint_cmd', 'snowflake', 'notes'] as const) oneLine(label, a[label]);
	a.tags = a.tags.map(t => t.trim().toLowerCase()).filter(Boolean);
	for (const t of a.tags) if (!TAG_RE.test(t)) throw new InputError(`tag ${pyRepr(t)}: lowercase letters, digits and dashes`);
	for (const [sid, why] of Object.entries(a.declines)) {
		if (!why.trim()) throw new InputError(`decline of ${sid}: a decline needs a reason`);
		oneLine(`decline of ${sid}`, why);
	}
	return a;
}

export const pkgOf = (a: {name: string}): string => a.name.replaceAll('-', '_');

/** Fill what the scaffold decides: its tags (always), and its commands when none were given.
 *  Refuses a scaffold the canon does not have or has not accepted. */
export function resolveAnswers(a: Answers, canon: Canon): Answers {
	const sc = canon.scaffolds.get(a.scaffold);
	if (!sc) throw new InputError(`scaffold ${pyRepr(a.scaffold)}: the canon has ${[...canon.scaffolds.keys()].join(', ') || 'none'}`);
	if (!sc.accepted) throw new InputError(`scaffold ${sc.id} is ${sc.status}, not accepted: its owner approves it in the canon`);
	const tags = [...new Set([...sc.tags, ...(a.snowflake ? ['snowflake'] : []), ...a.tags])];
	const dflt = (k: string, d: string) => (k in sc.defaults ? String(sc.defaults[k] ?? '') : d); // as dict.get(k, d)
	return {...a, tags, test_cmd: a.test_cmd || dflt('test_cmd', 'uv run pytest -q'), lint_cmd: a.lint_cmd || dflt('lint_cmd', 'uv run ruff check .')};
}

const tomlStr = jsonStr; // a JSON string is a valid TOML basic string

/** str() of an answer's value, as `asdict(a)` prints into interview.md. */
function answerText(v: string | string[] | Record<string, string>): string {
	if (typeof v === 'string') return v;
	if (Array.isArray(v)) return `[${v.map(pyRepr).join(', ')}]`;
	return `{${Object.entries(v).map(([k, x]) => `${pyRepr(k)}: ${pyRepr(x)}`).join(', ')}}`;
}

function indexStamp(canon: Canon): string {
	try {
		const d = JSON.parse(readText(join(canon.root, 'index.json'))) as Record<string, unknown>;
		return 'generated' in d ? pyStr(d['generated']) : '';
	} catch {
		return '';
	}
}

const skillLines = (skills: Skills): string =>
	RECOMMENDED_SKILLS.filter(n => skills.all.has(n))
		.map(n => `- \`/${n}\`: ${skills.all.get(n)!.description.split('. ')[0]!.replace(/\.+$/, '')}.\n`)
		.join('');

/** Every file of the new repo, as {relative path: text}: the knowledge docs from the answers, the
 *  code from the canon scaffold. */
export function render(input: Answers, canon: Canon, skills: Skills, today = todayIso()): Record<string, string> {
	const a = resolveAnswers(input, canon);
	const sc = canon.scaffolds.get(a.scaffold)!;
	const stds = canon.applicable(a.tags);
	const unknown = Object.keys(a.declines).filter(k => !stds.some(s => s.id === k)).sort();
	if (unknown.length) throw new InputError(`cannot decline ${unknown.join(', ')}: not a standard that applies here`);
	const local = `<!-- ds:local interview ${today} -->`;
	const adopted = stds.filter(s => !(s.id in a.declines));
	const files: Record<string, string> = {};
	// the accepted code: a new repo starts on canon-lib when the canon ships it
	const lib = purePath(`${canon.root}/lib`); // written into files, so spelled as Python's Path spells it
	const hasLib = isFile(join(lib, 'pyproject.toml'));
	const stamp = indexStamp(canon);
	const purpose = a.purpose.trim();

	const snow = a.snowflake ? `\nIt reads and writes Snowflake in \`${a.snowflake}\`.\n` : '';
	const outs = sc.outputs.length ? `\nOutputs: ${sc.outputs.join(', ')}.\n` : '';
	const notes = a.notes.trim() ? `\n## Notes\n\n${a.notes.trim()}\n` : '';
	files['README.md'] = `# ${a.name}

${local}
${purpose}
${snow}${outs}
Owner: ${a.owner}

## Run

\`\`\`bash
uv sync
${a.test_cmd}
\`\`\`
${notes}`;

	const sl = skillLines(skills);
	const libLine = hasLib
		? `- Accepted code: \`canon-lib\` is a dependency of this repo. Its modules are listed in \`${purePath(`${lib}/src/canon_lib/__init__.py`)}\`; import from it before writing code of your own, and never copy or edit it here.\n`
		: '';
	const declined = Object.keys(a.declines).length ? 'Declined, with reasons in the manifest: ' + Object.keys(a.declines).sort().join(', ') + '.' : '';
	files['AGENTS.md'] = `# AGENTS.md

${local}
${purpose}

- Test: \`${a.test_cmd}\`
- Lint: \`${a.lint_cmd}\`
- Before changing anything, read \`.ds/manifest.toml\`: it says which standards are in force here.
${libLine}- The team's knowledge base is served by \`ds-next mcp\` (canon_list, canon_read, code_search, code_get, code_add) for any agent that can reach it.
- Query the code graph before reading files, and check a symbol's references with the LSP tools
  before changing it (ds-next registers both when they are installed).

<!-- ds:inherited canon ${today} -->
## Standards

This repo follows ${adopted.map(s => `[[${s.id}]]`).join(', ') || 'no canon standards'}.
${declined}
${sl ? `\n## Skills\n\nFrom skills-os:\n\n${sl}` : ''}`;

	files['DECISIONS.md'] = `# Decisions

${local}
Local decisions for this repo, numbered local-001 upward. Team-wide decisions belong in the
canon as standards; this file links them with \`[[id]]\` rather than restating them.

None yet.
`;

	const lines = [
		'[repo]',
		`name = ${tomlStr(a.name)}`,
		`tags = [${a.tags.map(tomlStr).join(', ')}]`,
		`created = "${today}"`,
		'interview = ".ds/interview.md"',
		`scaffold = "${sc.id}"`,
		`scaffold_version = ${sc.version}`,
		...(sc.type ? [`type = ${tomlStr(sc.type)}`] : []),
		`outputs = [${sc.outputs.map(tomlStr).join(', ')}]`,
		`ds_version = "${DS_VERSION}"`,
		`canon = ${tomlStr(canon.root)}`,
		`canon_index = ${tomlStr(stamp)}`,
	];
	if (hasLib) lines.push(`canon_lib = ${tomlStr(lib)}`);
	lines.push('');
	const revisit = addDays(today, 90);
	for (const s of stds) {
		lines.push(`[standards.${s.id}]`);
		if (s.id in a.declines) {
			lines.push('status = "declined"', `version = ${s.version}`, `by = ${tomlStr(a.owner)}`, `on = "${today}"`, `reason = ${tomlStr(a.declines[s.id]!)}`, `revisit = "${revisit}"`);
		} else {
			lines.push('status = "adopted"', `version = ${s.version}`, `by = ${tomlStr(a.owner)}`, `on = "${today}"`);
		}
		lines.push('');
	}
	files['.ds/manifest.toml'] = lines.join('\n');

	const qa = FIELDS.map(k => `- **${k}**: ${answerText(a[k])}`).join('\n');
	files['.ds/interview.md'] = `# Interview\n\n${local}\n${qa}\n`;

	Object.assign(
		files,
		canon.renderScaffold(sc.id, {
			name: a.name,
			package: pkgOf(a),
			purpose,
			purpose_json: jsonStr(purpose),
			test_cmd: a.test_cmd,
			lint_cmd: a.lint_cmd,
			test_cmd_json: jsonStr(a.test_cmd),
			lint_cmd_json: jsonStr(a.lint_cmd),
			canon_lib_dep: hasLib ? '"canon-lib"' : '',
			canon_lib_source: hasLib ? `\n[tool.uv.sources]\ncanon-lib = { path = ${jsonStr(lib)}, editable = true }\n` : '',
		}),
	);
	return files;
}

// ── the pre-push hook ────────────────────────────────────────────────────────

export const HOOK_MARKER = '# ds:derived ds-next hooks.';

/** The pre-push hook. It runs `ds-next reconcile`, found on PATH or where it was when the hook was
 *  made, and says so out loud when it cannot, instead of skipping the check in silence. */
function hookText(): string {
	const here = which('ds-next') ?? '';
	const fallback = basename(here) === 'ds-next' ? here : '';
	return `#!/bin/sh
${HOOK_MARKER} Pending standards never block; broken pointers and a bad manifest do.
# A pre-push hook that was here before ds-next is kept as pre-push.local and runs first.
HERE="$(dirname "$0")"
if [ -x "$HERE/pre-push.local" ]; then
  "$HERE/pre-push.local" "$@" || exit $?
fi
DS="$(command -v ds-next 2>/dev/null)"
[ -z "$DS" ] && [ -x ${shlexQuote(fallback)} ] && DS=${shlexQuote(fallback)}
if [ -z "$DS" ]; then
  echo "ds: ds-next not found, so reconcile did not run. Install it (uv tool install ds-next) or put it on PATH." >&2
  exit 0
fi
exec "$DS" reconcile --quiet
`;
}

/** Write the pre-push hook where git will actually run it. Returns why it could not, or undefined.
 *  Git decides where hooks live (core.hooksPath can move them), so ask git, and write only inside
 *  this repo's own .git, never through a symbolic link. */
export function installHook(repoIn: string): string | undefined {
	const repo = resolvePath(repoIn);
	const gitDir = join(repo, '.git');
	if (isSymlink(gitDir) || !isDir(gitDir)) return `${gitDir} is not this repo's own git directory`;
	const r = spawnSync('git', ['-C', repo, 'rev-parse', '--git-path', 'hooks'], {encoding: 'utf8'});
	const out = r.status === 0 ? r.stdout.trim() : '';
	let hooks = out ? (isAbsolute(out) ? out : join(repo, out)) : join(gitDir, 'hooks');
	if (isSymlink(hooks)) return `${hooks} is a symbolic link`;
	hooks = resolvePath(hooks);
	if (!within(resolvePath(gitDir), hooks)) return `git runs hooks from ${hooks} (core.hooksPath), outside this repo, so it was not installed there`;
	mkdirSync(hooks, {recursive: true});
	const hook = join(hooks, 'pre-push');
	if (isSymlink(hook)) unlinkSync(hook); // never write through a link to somewhere else
	if (existsSync(hook) && !readText(hook).includes(HOOK_MARKER)) {
		// someone else's hook (a template's, a team's): keep it and run it first, never drop it
		const local = join(hooks, 'pre-push.local');
		if (existsSync(local) || isSymlink(local)) return `${hook} and ${local} both exist, so ds-next left them alone`;
		renameSync(hook, local);
	}
	writeFileSync(hook, hookText());
	chmodSync(hook, 0o755);
	return undefined;
}

// ── writing ──────────────────────────────────────────────────────────────────

/** The path for rel under dest, refusing anything that would land elsewhere or pass through a link. */
export function inside(dest: string, rel: string): string {
	const parts = rel.split(/[\\/]/).filter(Boolean);
	if (isAbsolute(rel) || parts.includes('..')) throw new InputError(`refusing to write ${pyRepr(rel)}: not a plain relative path`);
	let p = dest;
	for (const part of parts) {
		p = join(p, part);
		if (isSymlink(p)) throw new InputError(`refusing to write ${pyRepr(rel)}: ${p} is a symbolic link`);
	}
	const target = join(dest, ...parts);
	if (!within(dest, resolvePath(target)) || resolvePath(target) === dest) throw new InputError(`refusing to write ${pyRepr(rel)}: it resolves outside ${dest}`);
	return target;
}

function git(dest: string, ...args: string[]): void {
	const r = spawnSync('git', ['-C', dest, ...args], {encoding: 'utf8'});
	if (r.status !== 0) throw new ScaffoldError(`files are in ${dest}, but \`git ${args.slice(0, 2).join(' ')}\` failed: ${pySlice((r.stderr || r.stdout || String(r.error ?? '')).trim(), 300)}`);
}

const writeFiles = (targets: Record<string, string>, files: Record<string, string>) => {
	for (const [rel, text] of Object.entries(files)) {
		mkdirSync(dirname(targets[rel]!), {recursive: true});
		writeFileSync(targets[rel]!, text);
	}
};

/** Create the repo at dest. Refuses a directory that already has files in it, a symbolic link as the
 *  destination, and any file that would land outside it. Returns the files written, sorted. */
export function write(a: Answers, destIn: string, canon = new Canon(), skills = new Skills(), {withGit = true, today = todayIso()} = {}): string[] {
	const raw = expandUser(destIn);
	if (isSymlink(raw)) throw new InputError(`refusing to write into ${raw}: it is a symbolic link`);
	const dest = resolvePath(raw);
	if (existsSync(dest) && readdirSync(dest).some(n => n !== '.git')) throw new ExistsError(`${dest} is not empty`);
	if (isSymlink(join(dest, '.git'))) throw new InputError(`refusing to write into ${dest}: its .git is a symbolic link`);
	const files = render(a, canon, skills, today);
	const targets = Object.fromEntries(Object.keys(files).map(rel => [rel, inside(dest, rel)])); // every path checked before any is written
	writeFiles(targets, files);
	if (withGit) {
		if (!existsSync(join(dest, '.git'))) git(dest, 'init', '-q', '-b', 'main');
		const top = spawnSync('git', ['-C', dest, 'rev-parse', '--show-toplevel'], {encoding: 'utf8'}).stdout?.trim() ?? '';
		if (!top || resolvePath(top) !== dest) throw new ScaffoldError(`files are in ${dest}, but git resolves it to ${top || 'no repository'}`); // never stage into a parent repository
		const hookProblem = installHook(dest);
		git(dest, 'add', '-A');
		git(dest, 'commit', '-q', '-m', `Scaffold ${a.name} from the canon with ds-next`);
		if (hookProblem) throw new ScaffoldError(`${dest} is created and committed, but the pre-push hook is not installed: ${hookProblem}`);
	}
	return Object.keys(files).sort();
}

// ── adding canon code to a repo ──────────────────────────────────────────────

const reqName = (r: string) => r.split(/[<>=!~[ ;]/, 1)[0]!.toLowerCase();
const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Add items to a one-line TOML list `key = [...]` (the shape the scaffolds write). Returns the new
 *  text and what was added (nothing when all are present), or undefined if there is no such line. */
export function addToListLine(text: string, key: string, items: string[]): [string, string[]] | undefined {
	const m = new RegExp(`^(${escapeRe(key)} = )\\[(.*)\\]$`, 'm').exec(text);
	if (!m) return undefined;
	let current: string[];
	try {
		current = (parseToml(`x = [${m[2]}]`) as {x: unknown[]}).x.map(String);
	} catch (err) {
		throw new InputError(`${key} in pyproject.toml is not a TOML list: ${(err as Error).message.split('\n')[0]}`);
	}
	const names = new Set(current.map(reqName));
	const added = items.filter(i => !names.has(reqName(i)));
	if (!added.length) return [text, []];
	const line = `${m[1]}[${[...current, ...added].map(jsonStr).join(', ')}]`;
	return [text.slice(0, m.index) + line + text.slice(m.index + m[0].length), added];
}

/** Replace a manifest's [blocks.<id>] table, or append it. */
export function setBlockTable(manifest: string, bid: string, table: string): string {
	const existing = new RegExp(`^\\[blocks\\.${escapeRe(bid)}\\]\\n(?:(?!\\[).*\\n?)*`, 'm');
	return existing.test(manifest) ? manifest.replace(existing, () => table + '\n') : manifest.replace(/\n+$/, '') + '\n\n' + table;
}

export type Manifest = {repo?: {name?: unknown}; blocks?: Record<string, {version?: unknown; symbols?: unknown}>; [k: string]: unknown};

/** The repo's manifest and package, checked as add_block and code_add check them. */
export function repoPackage(repo: string, what: string): {manifestPath: string; manifestText: string; manifest: Manifest; pkg: string} {
	const manifestPath = join(repo, '.ds', 'manifest.toml');
	if (!isFile(manifestPath)) throw new InputError(`${repo} has no .ds/manifest.toml; create it with ds-next new first`);
	const manifestText = readText(manifestPath);
	let manifest: Manifest;
	try {
		manifest = parseToml(manifestText) as Manifest;
	} catch (err) {
		throw new InputError(`${repo}/.ds/manifest.toml is not valid TOML: ${(err as Error).message.split('\n')[0]}`);
	}
	const pkg = String(manifest.repo?.name ?? '').replaceAll('-', '_');
	if (!pkg || !isDir(join(repo, 'src', pkg))) throw new InputError(`${repo} has no src/${pkg}/ package to add ${what} to`);
	return {manifestPath, manifestText, manifest, pkg};
}

/** Add the requirements to pyproject.toml's one-line lists; what could not be added is returned to say so. */
export function addRequirements(repo: string, lists: [key: string, reqs: string[]][]): {added: string[]; manual: string[]} {
	const added: string[] = [];
	const manual: string[] = [];
	const pyproject = join(repo, 'pyproject.toml');
	for (const [key, wanted] of lists) {
		if (!wanted.length) continue;
		const result = addToListLine(isFile(pyproject) ? readText(pyproject) : '', key, wanted);
		if (!result) {
			manual.push(...wanted.map(w => `${w} (${key})`)); // no one-line list to add to: say so, never skip in silence
			continue;
		}
		if (result[1].length) writeFileSync(pyproject, result[0]);
		added.push(...result[1]);
	}
	return {added, manual};
}

export type BlockAdded = {block: string; version: number; files: string[]; requires: string[]; manual: string[]; note: string};

/** Copy an accepted canon block into a repo: its module into the package, its tests into tests/, its
 *  requirements into pyproject.toml, its version into the manifest. A file the block did not write
 *  before is never overwritten. */
export function addBlock(repoIn: string, bid: string, canon = new Canon(), by?: string, today = todayIso()): BlockAdded {
	const repo = resolvePath(repoIn);
	const b = canon.blocks.get(bid);
	if (!b) throw new InputError(`block ${pyRepr(bid)}: the canon has ${[...canon.blocks.keys()].join(', ') || 'none'}`);
	if (!b.accepted) throw new InputError(`block ${bid} is ${b.status}, not accepted: its owner approves it in the canon`);
	const {manifestPath, manifestText, manifest, pkg} = repoPackage(repo, 'the block');
	const have = manifest.blocks?.[bid]?.version;
	if (have === b.version) return {block: bid, version: b.version, files: [], requires: [], manual: [], note: 'already at this version'};
	const files = canon.blockFiles(bid, pkg);
	const targets = Object.fromEntries(Object.keys(files).map(rel => [rel, inside(repo, rel)]));
	if (have === undefined) {
		const clash = Object.keys(targets).filter(rel => existsSync(targets[rel]!));
		if (clash.length) throw new ExistsError(`not added: ${clash.join(', ')} already exist and were not written by ${bid}`);
	}
	writeFiles(targets, files);
	const {added, manual} = addRequirements(repo, [['dependencies', b.requires], ['dev', b.testRequires]]);
	const table = `[blocks.${bid}]\nversion = ${b.version}\nby = ${jsonStr(by ?? gitUser())}\non = "${today}"\nmodule = ${jsonStr(`src/${pkg}/${b.module}.py`)}\n`;
	writeFileSync(manifestPath, setBlockTable(manifestText, bid, table));
	return {block: bid, version: b.version, files: Object.keys(files).sort(), requires: added, manual, note: have !== undefined ? 'updated' : 'added'};
}

// ── an existing repository joins the system ──────────────────────────────────

export const ADOPT_MARKER = '<!-- ds:inherited canon';

/** What an existing repository says about itself. `detect` fills it from the files; the owner
 *  corrects it; `adopt` writes the manifest from it. */
export type Adoption = {name: string; purpose: string; owner: string; tags: string[]; test_cmd: string; lint_cmd: string};

export function validateAdoption(a: Adoption): Adoption {
	const why = nameProblem(a.name);
	if (why) throw new InputError(`name ${pyRepr(a.name)}: ${why}`);
	if (!a.purpose.trim()) throw new InputError('purpose: one line on what the repo does (the README had no first sentence)');
	if (!a.owner.trim()) throw new InputError('owner: who answers for this repo');
	return {...a, tags: [...new Set(a.tags.map(t => t.trim()).filter(Boolean))].sort()};
}

/** The first sentence of the README's first paragraph that is prose, or empty. */
function readmePurpose(repo: string): string {
	for (const name of ['README.md', 'readme.md', 'README']) {
		const p = join(repo, name);
		if (!isFile(p)) continue;
		for (const raw of readText(p).split(/\n\s*\n/)) {
			const para = raw.split(/\s+/).filter(Boolean).join(' ');
			if (para && !['#', '<!--', '[![', '```', '|', '- ', '* ', '>'].some(x => para.startsWith(x))) return pySlice(para.split(/(?<=[.!?])\s/, 1)[0]!, 200);
		}
	}
	return '';
}

/** Read-only: what the files say. Tags name the stack, so the right standards apply; the test and lint
 *  commands are the project's own scripts; the purpose is the README's first sentence. */
export function detect(repoIn: string): Adoption {
	const repo = resolvePath(expandUser(repoIn));
	const tags = new Set<string>();
	let test = '';
	let lint = '';
	const pkg = join(repo, 'package.json');
	if (isFile(pkg)) {
		let meta: Record<string, any> = {};
		try {
			meta = JSON.parse(readText(pkg)) as Record<string, any>;
		} catch {
			meta = {};
		}
		const deps: Record<string, unknown> = {...(meta['dependencies'] ?? {}), ...(meta['devDependencies'] ?? {})};
		const scripts: Record<string, unknown> = meta['scripts'] ?? {};
		tags.add('node');
		if (isFile(join(repo, 'tsconfig.json')) || 'typescript' in deps) tags.add('typescript');
		if ('next' in deps) ['nextjs', 'web', 'service'].forEach(t => tags.add(t));
		else if ('react' in deps) ['react', 'web'].forEach(t => tags.add(t));
		if (Object.keys(deps).some(d => d.startsWith('snowflake'))) tags.add('snowflake');
		if ('test' in scripts) test = 'npm test';
		lint = ['lint', 'typecheck'].filter(k => k in scripts).map(k => `npm run ${k}`)[0] ?? '';
	}
	const pyproject = join(repo, 'pyproject.toml');
	if (isFile(pyproject)) {
		let meta: Record<string, any> = {};
		try {
			meta = parseToml(readText(pyproject)) as Record<string, any>;
		} catch {
			meta = {};
		}
		const proj: Record<string, any> = meta['project'] ?? {};
		tags.add('python');
		if (proj['scripts'] && Object.keys(proj['scripts']).length) tags.add('cli');
		if (isDir(join(repo, 'src'))) tags.add('package');
		const deps = ((proj['dependencies'] ?? []) as unknown[]).map(String).join(' ');
		if (deps.includes('snowflake')) tags.add('snowflake');
		if (deps.includes('streamlit')) tags.add('streamlit-app');
		test ||= 'uv run pytest';
		lint ||= JSON.stringify(meta).includes('ruff') ? 'uv run ruff check' : '';
	}
	if (isFile(join(repo, 'dbt_project.yml'))) ['dbt', 'pipeline'].forEach(t => tags.add(t));
	if (isFile(join(repo, 'Dockerfile'))) tags.add('docker');
	for (const env of ['.env', '.env.local', '.env.example']) {
		const p = join(repo, env); // variable names only, never values
		if (isFile(p) && /^SNOWFLAKE_/m.test(readText(p))) tags.add('snowflake');
	}
	return {name: normalizeName(basename(repo)), purpose: readmePurpose(repo), owner: gitUser(), tags: [...tags].sort(), test_cmd: test, lint_cmd: lint};
}

/** An existing repository joins the system: its manifest, an AGENTS.md (or the standards section added
 *  to the one it has), a DECISIONS.md if it has none, and the pre-push hook. Everything else stays as
 *  it is. Every applicable standard is pending until the owner decides, unless `adoptAll`. */
export function adopt(repoIn: string, input: Adoption, canon = new Canon(), skills = new Skills(), adoptAll = false, today = todayIso()): string[] {
	const raw = expandUser(repoIn);
	if (isSymlink(raw)) throw new InputError(`refusing to write into ${raw}: it is a symbolic link`);
	const repo = resolvePath(raw);
	if (!isDir(repo)) throw new InputError(`${repo} is not a directory`);
	if (existsSync(join(repo, '.ds', 'manifest.toml'))) throw new ExistsError(`${repo} is already in the system (.ds/manifest.toml): run reconcile`);
	if (!isDir(join(repo, '.git'))) throw new InputError(`${repo} is not a git repository: git init first, the pre-push hook needs it`);
	const a = validateAdoption(input);
	const stds = canon.applicable(a.tags);
	const local = `<!-- ds:local adopted ${today} -->`;
	const written: string[] = [];

	const lines = [
		'[repo]',
		`name = ${tomlStr(a.name)}`,
		`tags = [${a.tags.map(tomlStr).join(', ')}]`,
		`created = "${today}"`,
		`adopted = "${today}"`,
		...(a.test_cmd ? [`test_cmd = ${tomlStr(a.test_cmd)}`] : []),
		...(a.lint_cmd ? [`lint_cmd = ${tomlStr(a.lint_cmd)}`] : []),
		`ds_version = "${DS_VERSION}"`,
		`canon = ${tomlStr(canon.root)}`,
		`canon_index = ${tomlStr(indexStamp(canon))}`,
		'',
	];
	if (adoptAll) for (const s of stds) lines.push(`[standards.${s.id}]`, 'status = "adopted"', `version = ${s.version}`, `by = ${tomlStr(a.owner)}`, `on = "${today}"`, '');
	const manifest = inside(repo, '.ds/manifest.toml');
	mkdirSync(dirname(manifest), {recursive: true});
	writeFileSync(manifest, lines.join('\n'));
	written.push('.ds/manifest.toml');

	const ids = stds.map(s => `[[${s.id}]]`).join(', ') || 'none';
	const section =
		`${ADOPT_MARKER} ${today} -->\n## Standards\n\n` +
		(adoptAll ? `This repo follows ${ids}.\n` : `Standards that apply here, each pending until the owner adopts or declines it in \`.ds/manifest.toml\` (\`/status\` in ds-next): ${ids}.\n`);
	const agents = inside(repo, 'AGENTS.md');
	if (existsSync(agents)) {
		const text = readText(agents);
		if (!text.includes(ADOPT_MARKER)) {
			writeFileSync(agents, text.replace(/\n+$/, '') + '\n\n' + section);
			written.push('AGENTS.md (standards section added)');
		}
	} else {
		const sl = skillLines(skills);
		const own = ['CLAUDE.md', 'CONTEXT.md'].filter(f => isFile(join(repo, f))).map(f => `- Project instructions: \`${f}\`.\n`).join('');
		writeFileSync(
			agents,
			`# AGENTS.md

${local}
${a.purpose.trim()}

${own}${a.test_cmd ? `- Test: \`${a.test_cmd}\`\n` : ''}${a.lint_cmd ? `- Lint: \`${a.lint_cmd}\`\n` : ''}- Before changing anything, read \`.ds/manifest.toml\`: it says which standards are in force here.
- The team's knowledge base is served by \`ds-next mcp\` (canon_list, canon_read, code_search, code_get, code_add) for any agent that can reach it.

${section}${sl ? `\n## Skills\n\nFrom skills-os:\n\n${sl}` : ''}`,
		);
		written.push('AGENTS.md');
	}

	const decisions = inside(repo, 'DECISIONS.md');
	if (!existsSync(decisions)) {
		const earlier = isDir(join(repo, 'docs', 'adr')) ? 'Earlier decisions are in `docs/adr/`; new ones go there too, and this file links them.\n' : 'None yet.\n';
		writeFileSync(
			decisions,
			`# Decisions

${local}
Local decisions for this repo, numbered local-001 upward. Team-wide decisions belong in the
canon as standards; this file links them with \`[[id]]\` rather than restating them.

${earlier}`,
		);
		written.push('DECISIONS.md');
	}

	const problem = installHook(repo);
	if (problem) throw new ScaffoldError(`${repo} joined the system, but the pre-push hook is not installed: ${problem}`);
	written.push('.git/hooks/pre-push');
	return written;
}

