// ds-next's agent tools (agent.py), for `rule agent`: the knowledge base as tools that run in this
// process, so the agent reads the same canon and skills the commands read, and the only things that
// write a project are scaffold.write, scaffold.adopt, addBlock and code.add. Read-only tools are
// pre-approved; the rest ask the person first.
import {mkdirSync, realpathSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {z} from 'zod';
import * as code from './code.js';
import * as codetools from './codetools.js';
import {Canon, CanonError, expandUser, NotFound, readSkill, Skills} from './kb.js';
import {isSymlink, pyJsonDumps, pyJsonIndent, pyRepr, pyReprValue, resolvePath, today, within} from './py.js';
import * as reconcile from './reconcile.js';
import * as scaffold from './scaffold.js';

export const SERVER = 'ds';
export const ERROR_PREFIX = 'ERROR: ';

/** A tool result. Cortex Code drops the is_error flag of in-process tools, so errors also say so in
 *  their first word, which the model reads and the terminal colours. */
export type Result = {text: string; error: boolean};
const ok = (text: string): Result => ({text, error: false});
const fail = (text: string): Result => ({text: ERROR_PREFIX + text, error: true});

export type DsTool = {
	name: string;
	description: string;
	shape: Record<string, z.ZodType>;
	readOnly: boolean;
	run: (args: Record<string, unknown>) => Promise<Result> | Result;
};

/** The first argument present under any of these names. Models mix up `id`, `name`, `ids` and
 *  `query` across tools; taking the aliases costs nothing and saves a failed turn. */
function arg(args: Record<string, unknown>, ...names: string[]): string | string[] {
	for (const n of names) {
		const v = args[n];
		if (v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length) || (typeof v === 'object' && !Array.isArray(v) && !Object.keys(v).length)) continue;
		return typeof v === 'string' || Array.isArray(v) ? (v as string | string[]) : String(v);
	}
	return '';
}
const argStr = (args: Record<string, unknown>, ...names: string[]): string => {
	const v = arg(args, ...names);
	return Array.isArray(v) ? v.join(',') : v; // a list of tags or ids reads as the comma-separated string
};

/** Optional string arguments: {name: description}. */
const optional = (props: Record<string, string>): Record<string, z.ZodType> => Object.fromEntries(Object.entries(props).map(([k, d]) => [k, z.string().optional().describe(d)]));

/** Symbol ids from a tool argument: a comma-separated string, a JSON list, or a list. */
export function parseIds(raw: unknown): string[] {
	if (Array.isArray(raw)) return raw.map(i => String(i).trim()).filter(Boolean);
	let text = String(raw ?? '').trim();
	if (text.startsWith('[')) {
		try {
			return parseIds(JSON.parse(text));
		} catch {
			text = text.replace(/^[[\]]+|[[\]]+$/g, '');
		}
	}
	return text
		.split(',')
		.map(i => i.trim().replace(/^["']+|["']+$/g, ''))
		.filter(Boolean);
}

export type Context = {cwd: string; connection?: string; canon: () => Canon; skills: () => Skills};

export function tools(ctx: Context): DsTool[] {
	const {cwd} = ctx;
	// (scaffold id, version, template hash) the model has fetched this session; scaffold_project accepts
	// only one of these, so the code always comes from a scaffold the model looked at
	const fetched = new Set<string>();
	const key = (id: string, version: unknown, hash: string) => JSON.stringify([id, version, hash]);

	return [
		{
			name: 'canon_list',
			description: "List the canon standards and gotchas. Optional tags (comma-separated, e.g. 'python,cli') keep only those that apply; no tags lists everything.",
			shape: optional({tags: 'comma-separated repo tags; omit to list every standard'}),
			readOnly: true,
			run: args => {
				const canon = ctx.canon();
				const tags = argStr(args, 'tags').split(',').map(t => t.trim()).filter(Boolean);
				const stds = tags.length ? canon.applicable(tags) : [...canon.standards.values()].sort((a, b) => (a.id < b.id ? -1 : 1));
				return ok(stds.map(s => `${s.id} v${s.version} ${s.status || 'proposed'}${s.kind === 'gotcha' ? ' (gotcha)' : ''} [${s.appliesTo.join(', ')}] ${s.title}`).join('\n'));
			},
		},
		{
			name: 'canon_read',
			description: 'Read one standard or gotcha in full, by id (as canon_list prints it).',
			shape: optional({id: "the standard's id, e.g. gotcha-validation", name: 'alias of id', standard: 'alias of id'}),
			readOnly: true,
			run: args => {
				const sid = argStr(args, 'id', 'name', 'standard', 'tags').trim().replace(/^[[\]"']+|[[\]"']+$/g, '');
				if (!sid) return fail("pass id: the standard's id, as canon_list prints it");
				return ok(ctx.canon().read(sid)); // an unknown id is NotFound, which runTool reports
			},
		},
		{
			name: 'skills_list',
			description: 'List the skills-os procedures (name: description).',
			shape: {},
			readOnly: true,
			run: () => ok([...ctx.skills().all.values()].map(s => `${s.name}: ${s.description}`).join('\n') || 'skills-os not found'),
		},
		{
			name: 'skill_read',
			description: 'Read one skills-os SKILL.md by name, to follow its procedure.',
			shape: {name: z.string()},
			readOnly: true,
			run: args => {
				const sk = ctx.skills().all.get(String(args['name']));
				return sk ? ok(readSkill(sk)) : fail(`no skill ${pyRepr(String(args['name']))}`);
			},
		},
		{
			name: 'project_status',
			description: 'Reconcile the repo at the working directory against the canon: adopted, declined, pending, errors.',
			shape: {},
			readOnly: true,
			run: () => {
				const repo = reconcile.findRepo(cwd);
				if (!repo) return ok(`${cwd} is not a ds repo (no .ds/manifest.toml up the tree)`);
				const r = reconcile.check(repo, ctx.canon());
				return ok(
					pyJsonIndent({
						summary: r.summary(), type: r.type, outputs: r.outputs, tags: r.tags, adopted: r.adopted,
						declined: r.declined, pending: r.pending, overdue_declines: r.overdue, errors: r.errors,
					}),
				);
			},
		},
		{
			name: 'scaffold_list',
			description: "List the canon's project types (scaffolds): id, version, status, type, the outputs a repo of that type produces, menu path, tags.",
			shape: {},
			readOnly: true,
			run: () =>
				ok(
					[...ctx.canon().scaffolds.values()]
						.map(sc => `${sc.id} v${sc.version} ${sc.status} type=${sc.type || '-'} outputs=${sc.outputs.join(',') || 'none'} [${sc.path.join(' > ')}] tags=${sc.tags.join(',')} ${sc.title}`)
						.join('\n') || 'the canon has no scaffolds',
				),
		},
		{
			name: 'scaffold_get',
			description:
				'Fetch one accepted scaffold from the canon: what it is, its version, the tags it gives a repo, its default commands and the files it creates. Required before scaffold_project, which takes the version this returns.',
			shape: {id: z.string()},
			readOnly: true,
			run: args => {
				const canon = ctx.canon();
				const sc = canon.scaffolds.get(String(args['id']));
				if (!sc) return fail(`no scaffold ${pyRepr(String(args['id']))}; scaffold_list shows them`);
				fetched.add(key(sc.id, sc.version, sc.hash));
				return ok(
					pyJsonIndent({
						id: sc.id, version: sc.version, status: sc.status, accepted: sc.accepted, title: sc.title, type: sc.type,
						outputs: sc.outputs, tags: sc.tags, defaults: sc.defaults, files: sc.files, about: canon.scaffoldAbout(sc.id),
					}),
				);
			},
		},
		{
			name: 'scaffold_project',
			description: 'Create a new repository from an accepted canon scaffold and the answers. The only way to create a project: never write project files yourself.',
			shape: {
				scaffold: z.string().describe('scaffold id from scaffold_get'),
				scaffold_version: z.number().int().describe('the version scaffold_get returned'),
				name: z.string().describe('lowercase-with-dashes'),
				purpose: z.string().describe('one line'),
				owner: z.string().optional(),
				tags: z.array(z.string()).optional().describe("extra tags beyond the scaffold's own"),
				test_cmd: z.string().optional(),
				lint_cmd: z.string().optional(),
				snowflake: z.string().optional().describe('DATABASE.SCHEMA or empty'),
				notes: z.string().optional().describe('what future-you should know'),
				declines: z.record(z.string(), z.string()).optional().describe('standard id -> reason, for standards declined now'),
				directory: z.string().optional().describe('parent directory; default cwd'),
			},
			readOnly: false,
			run: input => {
				const args = {...input};
				const parent = expandUser(String(args['directory'] || cwd));
				delete args['directory'];
				const version = args['scaffold_version'];
				delete args['scaffold_version'];
				const canon = ctx.canon();
				const sc = canon.scaffolds.get(String(args['scaffold'] ?? ''));
				if (!sc || !fetched.has(key(sc.id, version, sc.hash))) {
					const current = sc ? `v${sc.version}` : 'not in the canon';
					return fail(
						`not created: scaffold ${pyReprValue(args['scaffold'])} (${current}) has not been fetched at v${pyReprValue(version)} in this session. Call scaffold_get first and pass the version it returns.`,
					);
				}
				let a: scaffold.Answers;
				let files: string[];
				let r: reconcile.Report;
				try {
					a = scaffold.answers(Object.fromEntries(Object.entries(args).filter(([, v]) => v !== undefined && v !== null && v !== '')));
					files = scaffold.write(a, join(parent, a.name), canon, ctx.skills());
					r = reconcile.check(join(parent, a.name), canon);
				} catch (err) {
					if (err instanceof scaffold.ScaffoldError) return fail(`partly created: ${err.message}`);
					if (err instanceof scaffold.InputError || err instanceof scaffold.ExistsError || err instanceof CanonError) return fail(`not created: ${err.message}`);
					throw err;
				}
				return ok(`created ${join(parent, a.name)} from ${sc.id} v${sc.version}\n${r.summary()}\nfiles:\n` + files.join('\n'));
			},
		},
		{
			name: 'adopt_repo',
			description:
				'Bring an existing repository into the knowledge system: writes its .ds/manifest.toml, an AGENTS.md (or adds the standards section to the one it has), a DECISIONS.md if it has none, and the pre-push hook. Nothing else changes. Standards stay pending until the owner adopts them. Call with no overrides first: the reply shows what was detected (purpose, owner, tags, test and lint), and the user corrects it.',
			shape: {
				directory: z.string().optional().describe('the repository; default cwd'),
				purpose: z.string().optional().describe("one line; default the README's first sentence"),
				owner: z.string().optional().describe('default the git user'),
				tags: z.array(z.string()).optional().describe('default detected'),
				adopt_all: z.boolean().optional().describe('adopt every applicable standard now'),
			},
			readOnly: false,
			run: args => {
				const repo = expandUser(String(args['directory'] || cwd));
				let a: scaffold.Adoption;
				let written: string[];
				let r: reconcile.Report;
				try {
					a = scaffold.detect(repo);
					if (args['purpose']) a.purpose = String(args['purpose']);
					if (args['owner']) a.owner = String(args['owner']);
					if (Array.isArray(args['tags']) && args['tags'].length) a.tags = args['tags'].map(String);
					a = scaffold.validateAdoption(a);
					written = scaffold.adopt(repo, a, ctx.canon(), ctx.skills(), Boolean(args['adopt_all']));
					r = reconcile.check(resolvePath(repo), ctx.canon());
				} catch (err) {
					if (err instanceof scaffold.ScaffoldError) return fail(`partly adopted: ${err.message}`);
					if (err instanceof scaffold.InputError || err instanceof scaffold.ExistsError || err instanceof CanonError) return fail(`not adopted: ${err.message}`);
					throw err;
				}
				return ok(
					`${resolvePath(repo)} joined the system\npurpose: ${a.purpose}\nowner: ${a.owner}\ntags: ${a.tags.join(', ')}\ntest: ${a.test_cmd || 'none found'}\nlint: ${a.lint_cmd || 'none found'}\nwrote: ${written.join(', ')}\n${r.summary()}`,
				);
			},
		},
		{
			name: 'block_list',
			description: "List the canon's accepted code blocks: tested modules to add to a repo instead of writing that code yourself. Optional comma-separated tags filter them.",
			shape: {tags: z.string()},
			readOnly: true,
			run: args => {
				const tags = new Set(argStr(args, 'tags').split(',').map(t => t.trim()).filter(Boolean));
				const rows = [...ctx.canon().blocks.values()].filter(b => b.accepted && (!tags.size || b.tags.some(t => tags.has(t))));
				return ok(rows.map(b => `${b.id} v${b.version} module=${b.module} tags=${b.tags.join(',')} requires=${b.requires.join(',') || '-'} :: ${b.title}`).join('\n') || 'no accepted blocks match');
			},
		},
		{
			name: 'block_get',
			description: 'Read one block: what it is for, its API, and its full source and tests.',
			shape: {id: z.string()},
			readOnly: true,
			run: args => {
				const canon = ctx.canon();
				const b = canon.blocks.get(String(args['id']));
				if (!b) return fail(`no block ${pyRepr(String(args['id']))}; block_list shows them`);
				const files = canon.blockFiles(b.id, '<package>');
				return ok(canon.blockAbout(b.id) + '\n\n' + Object.entries(files).map(([path, text]) => `--- ${path}\n${text}`).join('\n\n'));
			},
		},
		{
			name: 'block_add',
			description:
				'Add an accepted block to the repo at the working directory: copies its module into src/<package>/ and its tests into tests/, adds its requirements, records its version. Import it from your code; never edit the copied file in place.',
			shape: {id: z.string()},
			readOnly: false,
			run: args => {
				const repo = reconcile.findRepo(cwd);
				if (!repo) return fail(`${cwd} is not a ds repo; create one with /new first`);
				let d: scaffold.BlockAdded;
				try {
					d = scaffold.addBlock(repo, String(args['id']), ctx.canon());
				} catch (err) {
					if (err instanceof scaffold.InputError || err instanceof scaffold.ExistsError || err instanceof CanonError) return fail(`not added: ${err.message}`);
					throw err;
				}
				return ok(
					`${d.note}: ${d.block} v${d.version}\nfiles: ${d.files.join(', ') || '-'}\nrequirements added: ${d.requires.join(', ') || '-'} (run uv sync)` +
						(d.manual.length ? `\nadd by hand, no one-line list found: ${d.manual.join(', ')}` : ''),
				);
			},
		},
		{
			name: 'code_search',
			description:
				"Search the canon's accepted code, one function, class or constant at a time, by what it does (e.g. 'user text into TOML', 'empty an output folder safely'). Returns ids, signatures and the lessons each carries. Search before writing code.",
			shape: {query: z.string()},
			readOnly: true,
			run: args => {
				const hits = code.search(ctx.canon(), String(args['query'] ?? ''));
				code.usageLog('code_search', hits.map(h => h.id));
				return ok(
					hits.map(h => `${h.id}${code.label(h.status)}  ${h.signature}\n    ${h.summary || '-'}  [lessons: ${h.lessons.join(', ') || '-'}; ${h.lines} lines]`).join('\n') ||
						'nothing matches; try other words, or block_list',
				);
			},
		},
		{
			name: 'code_get',
			description: 'Read one code symbol by id (block:name, as code_search prints it): its source with only what it needs, and the tests that cover it.',
			shape: optional({id: 'block:name', name: 'alias of id', query: 'words to search instead, if you have no id'}),
			readOnly: true,
			run: args => {
				const canon = ctx.canon();
				const sid = argStr(args, 'id', 'name').trim();
				if (!sid) {
					const query = argStr(args, 'query');
					if (!query) return fail('pass id (block:name), or query to search');
					const hits = code.search(canon, query);
					return hits.length ? ok('no id given; code_search found:\n' + hits.map(h => `${h.id}  ${h.signature}`).join('\n')) : fail('no id given and nothing matches the query');
				}
				let text: string;
				try {
					text = code.get(canon, sid);
				} catch (err) {
					if (err instanceof scaffold.InputError || err instanceof CanonError) return fail(`${err.message}; code_search finds ids`);
					throw err;
				}
				code.usageLog('code_get', [sid]);
				return ok(text);
			},
		},
		{
			name: 'code_add',
			description:
				"Add code symbols to the repo at the working directory: ids is a comma-separated list of block:name. Copies each block's module cut down to them (and what they need) into src/<package>/, with the tests that cover them, and records them in the manifest. Import them from your code; never edit the copy.",
			shape: optional({ids: 'comma-separated block:name ids', id: 'alias of ids', name: 'alias of ids', symbols: 'alias of ids'}),
			readOnly: false,
			run: args => {
				const repo = reconcile.findRepo(cwd);
				if (!repo) return fail(`${cwd} is not a ds repo; create one with /new first`);
				const ids = parseIds(arg(args, 'ids', 'id', 'name', 'symbols'));
				if (!ids.length) return fail('pass ids: comma-separated block:name, as code_search prints them');
				let done: code.CodeAdded[];
				try {
					done = code.add(repo, ids, ctx.canon());
				} catch (err) {
					if (err instanceof scaffold.InputError || err instanceof scaffold.ExistsError || err instanceof CanonError) return fail(`not added: ${err.message}`);
					throw err;
				}
				return ok(
					done
						.map(
							d =>
								`${d.note}: ${d.block} ${d.symbols === 'all' ? 'all' : d.symbols.join(', ')}\n  files: ${d.files.join(', ') || '-'}; requirements added: ${(d.requires ?? []).join(', ') || '-'}` +
								(d.manual?.length ? `\n  add by hand: ${d.manual.join(', ')}` : ''),
						)
						.join('\n'),
				);
			},
		},
		{
			name: 'snowflake_search',
			description: "Search Snowflake: kind 'docs' (product documentation), 'object' (tables, views, schemas... in this account's catalog) or 'table-details' (columns, joins, usage for named tables). Read-only.",
			shape: {kind: z.string(), query: z.string()},
			readOnly: true,
			run: async args => {
				const [text, err] = await codetools.snowflakeSearch(String(args['kind'] ?? ''), String(args['query'] ?? ''), ctx.connection);
				return err ? fail(text) : ok(text);
			},
		},
		{
			name: 'capture',
			description: 'Draft a proposed canon standard from something learned in this session (a gotcha, a decision, a pattern). Writes a draft for review; never edits the canon.',
			shape: {title: z.string(), body: z.string(), applies_to: z.array(z.string()).optional()},
			readOnly: false,
			run: args => {
				const title = String(args['title']).split(/\s+/).filter(Boolean).join(' '); // front matter is one line per key
				const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 50).replace(/^-+|-+$/g, '') || 'capture';
				const base = resolvePath(reconcile.findRepo(cwd) ?? cwd);
				const folder = join(base, '.ds', 'captures');
				if (isSymlink(join(base, '.ds')) || isSymlink(folder)) return fail(`not written: ${join(base, '.ds')} or its captures folder is a symbolic link`);
				mkdirSync(folder, {recursive: true});
				if (!within(base, realpathSync(folder)) || realpathSync(folder) === base) return fail(`not written: ${folder} resolves outside ${base}`);
				const applies = pyJsonDumps(Array.isArray(args['applies_to']) && args['applies_to'].length ? args['applies_to'] : ['*']);
				for (let n = 1; n < 100; n++) {
					// never overwrite an earlier draft, or follow a link; the canon id matches the file
					const sid = n === 1 ? slug : `${slug}-${n}`;
					const path = join(folder, `${sid}.md`);
					const text =
						`---\nid: ${sid}\nversion: 1\ntitle: ${title}\napplies_to: ${applies}\n` +
						`owner: ${scaffold.gitUser()}\nstatus: proposed\ndate: ${today()}\n---\n\n` +
						`# ${title}\n\n${String(args['body']).trim()}\n`;
					try {
						writeFileSync(path, text, {flag: 'wx'});
					} catch (err) {
						if ((err as NodeJS.ErrnoException).code === 'EEXIST') continue;
						throw err;
					}
					return ok(`draft at ${path}. To publish: open a canon merge request with this file (the so-capture skill does it), then run scripts/build_index.py.`);
				}
				return fail(`not written: 99 drafts already named ${slug}`);
			},
		},
	];
}

/** Run a tool. A missing canon, an unknown id, a canon that no longer matches its index, or a bad
 *  answer becomes an ERROR result the model can read and act on, never a crashed call. */
export async function runTool(t: DsTool, args: Record<string, unknown>): Promise<Result> {
	try {
		return await t.run(args ?? {});
	} catch (err) {
		if (err instanceof NotFound || err instanceof CanonError || err instanceof scaffold.InputError || err instanceof scaffold.ExistsError) return fail(err.message);
		return fail(`${t.name} failed: ${(err as Error).message}`);
	}
}

/** The prompt lines for whichever code-intelligence tools are installed. */
export function codeToolLines(cwd: string): string {
	const servers = codetools.mcpServers(cwd);
	const lines: string[] = [];
	if (codetools.GRAPH in servers) {
		lines.push(
			`- Query the code graph before reading files: \`graph\` tools search_graph, search_code and trace_path find what already exists and who calls it (project "${codetools.graphProject(cwd)}"). Reuse what it finds instead of rewriting it.`,
		);
	}
	if (codetools.LSP in servers) lines.push('- Before changing or removing a symbol, use the `lsp` tools find_symbol and find_referencing_symbols to see every use of it.');
	lines.push('- For Snowflake questions (docs, tables, columns), use snowflake_search before guessing.');
	return lines.join('\n');
}

/** ds-next's system prompt, word for word. */
export function systemPrompt(cwd: string, canon: Canon, skills: Skills): string {
	const repo = reconcile.findRepo(cwd);
	const where = repo ? `The working directory is inside the ds repo ${repo.split(/[\\/]/).pop()}.` : 'The working directory is not a ds repo yet.';
	return `You are ds, the front door to the team's knowledge system, running in a terminal.

The knowledge system has three parts, all readable through your \`ds\` tools:
- the canon: ${canon.standards.size} versioned standards, the only place team rules are written,
  and ${canon.scaffolds.size} project scaffolds (${[...canon.scaffolds.keys()].join(', ')}), the only accepted project shapes,
  and ${canon.blocks.size} blocks of accepted, tested code;
- skills-os: ${skills.all.size} procedures (SKILL.md files) for how the team works;
- docs-ds: the site that renders both (the user runs /docs; you do not).

Rules:
- Cite standards as [[id]] pointers and read them with canon_read before relying on them.
  Never paste a standard's text into a repo file.
- New projects come from accepted canon scaffolds. The /new form sends you a complete draft:
  check it against the canon (canon_list with its tags; canon_read only a standard the answers
  actually touch). If something is wrong or too vague to be useful, say so in at most three
  short bullets and ask once. Never replace an answer with one you made up: a purpose, name or
  schema you invent is not a suggestion. Offer a concrete value only when it follows from what
  the user gave (a name fixed to lowercase-with-dashes, a decline that names a real standard).
  Otherwise, or once the user answers, call scaffold_get for the draft's scaffold and then
  scaffold_project with its version, passing the user's values unchanged unless they agreed to
  a change. Do not re-ask what the draft already answers.
- An existing repository joins the system with adopt_repo, never by writing its manifest or
  AGENTS.md yourself. Call it with no overrides, show what it detected, and let the user correct it.
- If the user asks for a project in chat instead, propose a complete draft in one message
  (scaffold, name, purpose, and suggested values for the rest), ask for one confirmation, and
  create it the same way. Never ask one question at a time. Never write project files yourself.
- Before writing code, code_search for accepted code that already does it (one function at a
  time), code_get to read it, and code_add it rather than writing your own; import it from the
  package. block_add takes a whole block when you need most of it. Before building anything, read the gotchas
  (canon_list marks them) whose tags match the work: they are mistakes already made here once.
- When a skill fits the request, skill_read it and follow it.
${codeToolLines(cwd)}
- When the session uncovers something the team should remember, offer to capture it.
- Be brief. This is a terminal.

${where} Today is ${today()}.`;
}
