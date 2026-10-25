// The TypeScript port, through the same steps.
import {spawnSync} from 'node:child_process';
import {existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync} from 'node:fs';
import {dirname, join} from 'node:path';
const SRC = new URL('../../src/ds', import.meta.url).pathname;
const {Canon, Skills} = await import(`${SRC}/kb.ts`);
const {tools, runTool} = await import(`${SRC}/tools.ts`);
const reconcile = await import(`${SRC}/reconcile.ts`);
const scaffold = await import(`${SRC}/scaffold.ts`);
const [ROOT, CANON, SKILLS, SCEN, OUT] = process.argv.slice(2) as [string, string, string, string, string];
process.env['DS_STATE'] = join(ROOT, 'state');
const canon = new Canon(CANON);
const skills = new Skills(SKILLS);
const sc = JSON.parse(readFileSync(SCEN, 'utf8'));
mkdirSync(join(ROOT, 'work'), {recursive: true});
mkdirSync(join(ROOT, 'projects'));
const norm = (t: string) => t.replaceAll(ROOT, '<ROOT>');
const cache = new Map<string, Map<string, any>>();
const toolsFor = (cwd: string) => {
	if (!cache.has(cwd)) cache.set(cwd, new Map(tools({cwd: join(ROOT, cwd), canon: () => canon, skills: () => skills}).map((t: any) => [t.name, t])));
	return cache.get(cwd)!;
};
const steps = [];
for (const st of sc.steps) {
	const args = JSON.parse(JSON.stringify(st.args).replaceAll('<ROOT>', ROOT));
	const r = await runTool(toolsFor(st.cwd).get(st.tool), args);
	steps.push({tool: st.tool, text: norm(r.text), error: r.error});
}
function tree(base: string): Record<string, string> {
	const out: [string, string][] = [];
	const walk = (rel: string[]) => {
		for (const n of readdirSync(join(base, ...rel))) {
			const p = [...rel, n];
			const full = join(base, ...p);
			const st = statSync(full);
			if (st.isDirectory()) walk(p);
			else if (st.isFile()) {
				const r = p.join('/');
				if (('/' + r).includes('/.git/') && !r.endsWith('hooks/pre-push')) continue;
				out.push([r, norm(readFileSync(full, 'utf8'))]);
			}
		}
	};
	if (existsSync(base)) walk([]);
	return Object.fromEntries(out.sort(([a], [b]) => (a.split('/').join('\0') < b.split('/').join('\0') ? -1 : 1)));
}
const rep = (r: any) => ({repo: r.repo, tags: r.tags, adopted: r.adopted, declined: Object.fromEntries(r.declined), pending: r.pending, overdue: r.overdue,
	blocks: r.blocks, type: r.type, outputs: r.outputs, errors: r.errors.map(norm)});
const recon: Record<string, unknown> = {};
for (const c of sc.reconcile) {
	const d = join(ROOT, 'recon', c.name);
	mkdirSync(d, {recursive: true});
	if (c.manifest !== null) {
		mkdirSync(join(d, '.ds'));
		writeFileSync(join(d, '.ds', 'manifest.toml'), c.manifest);
	}
	for (const [rel, text] of Object.entries(c.docs as Record<string, string>)) {
		mkdirSync(dirname(join(d, rel)), {recursive: true});
		writeFileSync(join(d, rel), text);
	}
	recon[c.name] = rep(reconcile.check(d, canon));
}
const pointers = sc.pointers.map((t: string) => canon.pointerProblems(t));
const adopt: Record<string, unknown> = {};
for (const c of sc.adopt) {
	const d = join(ROOT, 'existing', c.name);
	mkdirSync(d, {recursive: true});
	for (const [rel, text] of Object.entries(c.files as Record<string, string>)) {
		mkdirSync(dirname(join(d, rel)), {recursive: true});
		writeFileSync(join(d, rel), text);
	}
	spawnSync('git', ['init', '-q', d]);
	const a = scaffold.detect(d);
	const det = {name: a.name, purpose: a.purpose, owner: a.owner, tags: a.tags, test_cmd: a.test_cmd, lint_cmd: a.lint_cmd};
	try {
		const written = scaffold.adopt(d, a, canon, skills, c.adopt_all);
		adopt[c.name] = {detect: det, written, summary: reconcile.check(d, canon).summary(), files: tree(d)};
	} catch (e) {
		adopt[c.name] = {detect: det, error: `${(e as Error).constructor.name}: ${norm((e as Error).message)}`};
	}
}
const usagePath = join(ROOT, 'state', 'usage.jsonl');
const usage = existsSync(usagePath) ? norm(readFileSync(usagePath, 'utf8')).split('\n').filter(Boolean).map(l => l.replace(/"at": "[^"]+"/, '"at": "<AT>"')) : [];
writeFileSync(OUT, JSON.stringify({steps, files: tree(join(ROOT, 'projects')), captures: tree(join(ROOT, 'work')), reconcile: recon, pointers, adopt, usage}, null, 1));
console.log('ts:', steps.length, 'steps,', Object.keys(tree(join(ROOT, 'projects'))).length, 'project files');
