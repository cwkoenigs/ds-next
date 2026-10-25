// The ds port on a small canon built here, as ds-next's tests build theirs (tests/conftest.py).
// The full comparison with ds-next's Python on a real canon is test/parity/run.sh.
import {createHash} from 'node:crypto';
import {existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname, join} from 'node:path';
import {beforeAll, describe, expect, it} from 'vitest';
import {readOnlyIds} from '../src/agent/backend.js';
import * as code from '../src/ds/code.js';
import {Canon, CanonError, Skills} from '../src/ds/kb.js';
import * as reconcile from '../src/ds/reconcile.js';
import * as scaffold from '../src/ds/scaffold.js';
import {runTool, tools} from '../src/ds/tools.js';

beforeAll(() => {
	Object.assign(process.env, {GIT_AUTHOR_NAME: 'Test', GIT_AUTHOR_EMAIL: 't@example', GIT_COMMITTER_NAME: 'Test', GIT_COMMITTER_EMAIL: 't@example'});
	process.env['DS_STATE'] = mkdtempSync(join(tmpdir(), 'ds-state-'));
});

const put = (path: string, text: string) => {
	mkdirSync(dirname(path), {recursive: true});
	writeFileSync(path, text);
};
const sha12 = (parts: (string | Buffer)[]) => {
	const h = createHash('sha256');
	parts.forEach(p => h.update(p));
	return h.digest('hex').slice(0, 12);
};

const STANDARDS: [string, number, string, string[]][] = [
	['adr-000', 1, 'Repo knowledge system', ['*']],
	['testing', 1, 'Testing and QA', ['*']],
	['error-handling', 1, 'Error handling', ['service', 'package']],
	['idempotency', 1, 'Idempotency', ['service', 'pipeline']],
];

/** The canon from ds-next's conftest.make_canon, plus one indexed code symbol. */
function makeCanon(root: string, bump: Record<string, number> = {}): Canon {
	const rows = STANDARDS.map(([id, v0, title, applies]) => {
		const v = bump[id] ?? v0;
		put(join(root, `${id}.md`), `---\nid: ${id}\nversion: ${v}\n---\n\n# ${title}\n\nBody of ${id}.\n`);
		return {id, version: v, title, applies_to: applies, owner: 'o', status: 'accepted', path: `${id}.md`};
	});
	const files: Record<string, string> = {
		'pyproject.toml': '[project]\nname = "{{name}}"\ndescription = {{purpose_json}}\ndependencies = []\n\n[dependency-groups]\ndev = ["pytest>=8"]\n',
		'src/__package__/__init__.py': '"""{{purpose}}"""\n',
		'dot-gitignore': '.venv/\n',
	};
	const scaffolds = [
		['python-cli', 'accepted', ['python', 'cli'], ['python', 'package', 'cli'], 'cli', []],
		['python-draft', 'proposed', ['python', 'draft'], ['python'], '', []],
	].map(([id, status, path, tags, type, outputs]) => {
		const d = join(root, 'scaffolds', id as string);
		Object.entries(files).forEach(([rel, text]) => put(join(d, 'files', rel), text));
		put(join(d, 'SCAFFOLD.md'), `---\nid: ${id}\n---\n\n# ${id}\n\nAbout ${id}.\n`);
		const rels = Object.keys(files).sort();
		const hash = sha12([readFileSync(join(d, 'SCAFFOLD.md')), ...rels.flatMap(r => [`files/${r}`, readFileSync(join(d, 'files', r))])]);
		return {id, version: 3, title: `T ${id}`, path, tags, owner: 'o', status, type, outputs, defaults: {test_cmd: 'uv run pytest -q'}, hash, dir: `scaffolds/${id}`, files: rels};
	});
	const blocks = ([['block-demo', 'accepted', bump['block-demo'] ?? 1], ['block-draft', 'proposed', 1]] as const).map(([id, status, version]) => {
		const d = join(root, 'blocks', id);
		put(join(d, 'BLOCK.md'), `---\nid: ${id}\n---\n\n# ${id}\n\nAbout ${id} v${version}.\n`);
		put(join(d, 'code', 'demo_mod.py'), `VERSION = ${version}\n\n\ndef shout(s):\n    return s.upper()\n`);
		put(join(d, 'tests', 'test_demo_mod.py'), "from {{package}}.demo_mod import shout\n\n\ndef test_shout():\n    assert shout('a') == 'A'\n");
		const rels = ['code/demo_mod.py', 'tests/test_demo_mod.py'];
		const hash = sha12([readFileSync(join(d, 'BLOCK.md')), ...rels.flatMap(r => [r, readFileSync(join(d, r))])]);
		return {id, version, title: `T ${id}`, module: 'demo_mod', requires: ['rich>=13'], test_requires: ['pyyaml>=6'], tags: ['python'], owner: 'o', status, hash, dir: `blocks/${id}`, tests: ['test_demo_mod.py']};
	});
	const codeIndex = [{id: 'block-demo:shout', block: 'block-demo', name: 'shout', kind: 'function', version: 1, status: 'accepted', signature: 'shout(s)', summary: 'Upper-case a string', tags: ['python'], lessons: [], needs: [], lines: 2}];
	put(join(root, 'index.json'), JSON.stringify({generated: 'today', standards: rows, scaffolds, blocks, code: codeIndex}));
	return new Canon(root);
}

function makeSkills(root: string): Skills {
	put(join(root, 'so-capture', 'SKILL.md'), '---\nname: so-capture\ndescription: Capture gotchas. Long tail.\n---\n\n# so-capture\n\nSteps.\n');
	put(join(root, 'so-changes', 'SKILL.md'), '---\nname: so-changes\ndescription: Record decisions.\n---\n\n# so-changes\n\nSteps.\n');
	return new Skills(root);
}

function setup() {
	const tmp = mkdtempSync(join(tmpdir(), 'ds-test-'));
	return {tmp, canon: makeCanon(join(tmp, 'canon')), skills: makeSkills(join(tmp, 'skills-os'))};
}

const answers = (over: Record<string, unknown> = {}) => scaffold.answers({name: 'demo-app', purpose: 'Demo things', owner: 'Ann', ...over});

describe('scaffold.render', () => {
	it('writes the knowledge docs and the canon templates', () => {
		const {canon, skills} = setup();
		const files = scaffold.render(answers({tags: ['extra']}), canon, skills, '2026-10-25');
		expect(Object.keys(files).sort()).toEqual(['.ds/interview.md', '.ds/manifest.toml', '.gitignore', 'AGENTS.md', 'DECISIONS.md', 'README.md', 'pyproject.toml', 'src/demo_app/__init__.py']);
		expect(files['.ds/manifest.toml']).toContain('tags = ["python", "package", "cli", "extra"]');
		expect(files['.ds/manifest.toml']).toContain('[standards.error-handling]\nstatus = "adopted"');
		expect(files['.ds/manifest.toml']).not.toContain('idempotency');
		expect(files['AGENTS.md']).toContain('This repo follows [[adr-000]], [[error-handling]], [[testing]].');
		expect(files['AGENTS.md']).toContain('- `/so-capture`: Capture gotchas.');
		expect(files['pyproject.toml']).toContain('description = "Demo things"');
		expect(files['.ds/interview.md']).toContain("- **tags**: ['python', 'package', 'cli', 'extra']");
	});

	it('records a decline with a reason and a revisit date 90 days out', () => {
		const {canon, skills} = setup();
		const m = scaffold.render(answers({declines: {testing: 'later'}}), canon, skills, '2026-10-25')['.ds/manifest.toml']!;
		expect(m).toContain('[standards.testing]\nstatus = "declined"\nversion = 1\nby = "Ann"\non = "2026-10-25"\nreason = "later"\nrevisit = "2027-01-23"');
	});

	it.each([
		[{scaffold: 'python-draft'}, /proposed, not accepted/],
		[{scaffold: 'nope'}, /the canon has python-cli, python-draft/],
		[{name: 'class'}, /'class' is a Python keyword/],
		[{name: 'Bad_Name'}, /lowercase letters, digits and single dashes/],
		[{purpose: 'two\nlines'}, /purpose: one line of text, without control characters \('\\n'\)/],
		[{declines: {idempotency: 'x'}}, /cannot decline idempotency: not a standard that applies here/],
		[{tags: ['Bad Tag!']}, /tag 'bad tag!'/],
	])('refuses %j', (over, msg) => {
		const {canon, skills} = setup();
		expect(() => scaffold.render(answers(over), canon, skills)).toThrow(msg);
	});

	it('refuses templates edited since the index was built', () => {
		const {tmp, canon, skills} = setup();
		writeFileSync(join(tmp, 'canon', 'scaffolds', 'python-cli', 'files', 'dot-gitignore'), 'changed\n');
		expect(() => scaffold.render(answers(), canon, skills)).toThrow(CanonError);
	});
});

describe('scaffold.write and reconcile', () => {
	it('creates a committed repo with the pre-push hook, and refuses a non-empty directory', () => {
		const {tmp, canon, skills} = setup();
		const dest = join(tmp, 'demo-app');
		const files = scaffold.write(answers(), dest, canon, skills);
		expect(files).toContain('AGENTS.md');
		expect(readFileSync(join(dest, '.git', 'hooks', 'pre-push'), 'utf8')).toContain(scaffold.HOOK_MARKER);
		expect(() => scaffold.write(answers(), dest, canon, skills)).toThrow(/is not empty/);
		const r = reconcile.check(dest, canon);
		expect(r.summary()).toBe('demo-app: 3 adopted · 0 declined · 0 pending');
	});

	it('sees a newer standard as pending, and a broken pointer as an error', () => {
		const {tmp, canon, skills} = setup();
		const dest = join(tmp, 'demo-app');
		scaffold.write(answers(), dest, canon, skills, {withGit: false});
		writeFileSync(join(dest, 'NOTES.md'), 'See [[testing]] and [[nope]].\n\n```\n[[in-code]]\n```\n');
		const bumped = makeCanon(join(tmp, 'canon'), {testing: 2});
		const r = reconcile.check(dest, bumped);
		expect(r.pending).toEqual(['testing v2']);
		expect(r.errors).toEqual(['NOTES.md: [[nope]] is not in the canon']);
	});
});

describe('canon code in a repo', () => {
	it('adds a block with its requirements, once', () => {
		const {tmp, canon, skills} = setup();
		const dest = join(tmp, 'demo-app');
		scaffold.write(answers(), dest, canon, skills, {withGit: false});
		const d = scaffold.addBlock(dest, 'block-demo', canon, 'Ann', '2026-10-25');
		expect(d).toMatchObject({note: 'added', requires: ['rich>=13', 'pyyaml>=6'], files: ['src/demo_app/demo_mod.py', 'tests/test_demo_mod.py']});
		expect(readFileSync(join(dest, 'tests', 'test_demo_mod.py'), 'utf8')).toContain('from demo_app.demo_mod import shout');
		expect(readFileSync(join(dest, '.ds', 'manifest.toml'), 'utf8')).toContain('[blocks.block-demo]\nversion = 1\nby = "Ann"');
		expect(scaffold.addBlock(dest, 'block-demo', canon).note).toBe('already at this version');
		expect(() => scaffold.addBlock(dest, 'block-draft', canon)).toThrow(/proposed, not accepted/);
	});

	it('finds, reads and adds one symbol, cut down to what it needs', () => {
		const {tmp, canon, skills} = setup();
		expect(code.search(canon, 'upper case a string').map(s => s.id)).toEqual(['block-demo:shout']);
		const text = code.get(canon, 'block-demo:shout');
		expect(text).toContain('def shout(s):');
		expect(text).not.toContain('VERSION = '); // shout does not use it, so the cut leaves it out
		const dest = join(tmp, 'demo-app');
		scaffold.write(answers(), dest, canon, skills, {withGit: false});
		const [d] = code.add(dest, ['block-demo:shout'], canon, 'Ann');
		expect(d).toMatchObject({block: 'block-demo', symbols: ['shout'], note: 'added'});
		expect(readFileSync(join(dest, '.ds', 'manifest.toml'), 'utf8')).toContain('symbols = ["shout"]');
	});
});

describe('the ds tools', () => {
	it('creates a project only from a scaffold fetched in this session', async () => {
		const {tmp, canon, skills} = setup();
		const t = new Map(tools({cwd: tmp, canon: () => canon, skills: () => skills}).map(x => [x.name, x]));
		const args = {scaffold: 'python-cli', scaffold_version: 3, name: 'demo-app', purpose: 'Demo things', owner: 'Ann'};
		expect((await runTool(t.get('scaffold_project')!, args)).text).toMatch(/^ERROR: not created: scaffold 'python-cli' \(v3\) has not been fetched at v3/);
		await runTool(t.get('scaffold_get')!, {id: 'python-cli'});
		const r = await runTool(t.get('scaffold_project')!, args);
		expect(r.error).toBe(false);
		expect(r.text).toContain(`created ${join(tmp, 'demo-app')} from python-cli v3\ndemo-app: 3 adopted`);
		expect(existsSync(join(tmp, 'demo-app', '.git'))).toBe(true);
	});

	it('reports a missing canon as an error the agent can read', async () => {
		const t = tools({cwd: tmpdir(), canon: () => new Canon(join(tmpdir(), 'no-canon-here')), skills: () => new Skills()});
		const r = await runTool(t.find(x => x.name === 'canon_list')!, {});
		expect(r).toEqual({text: 'ERROR: canon not found: set DS_CANON or clone it to ~/Developer/canon', error: true});
	});

	it('asks before writing, never before reading', () => {
		const {tmp, canon, skills} = setup();
		const t = tools({cwd: tmp, canon: () => canon, skills: () => skills});
		const ro = readOnlyIds(t, {});
		expect(t.map(x => x.name)).toContain('adopt_repo'); // defined but not registered in ds-next's agent.py
		for (const id of ['canon_list', 'canon_read', 'code_get', 'scaffold_get', 'rule_spec']) expect(ro.has(`mcp__ds__${id}`)).toBe(true);
		for (const id of ['scaffold_project', 'adopt_repo', 'block_add', 'code_add', 'capture']) expect(ro.has(`mcp__ds__${id}`)).toBe(false);
	});
});
