// Code intelligence for the agent: a code graph, a language server, and Snowflake search. A port of
// ds-next's codetools.py. Each is optional: missing tools are simply not offered; nothing installs.
//   graph   codebase-memory-mcp, a local index of symbols, calls and files (read-only `analysis` profile)
//   lsp     Serena: find a symbol, its references, its declaration; its edit tools always ask
//   search  `cortex search`: Snowflake docs, catalog objects and table details, read-only
import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import {basename, join} from 'node:path';
import {pyReprValue, pySlice, resolvePath, which} from './py.js';

export const GRAPH = 'graph';
export const LSP = 'lsp';

// codebase-memory-mcp --tool-profile=analysis serves only these, all reads.
const GRAPH_READ = ['search_graph', 'query_graph', 'trace_path', 'get_code_snippet', 'get_file_outline', 'get_graph_schema', 'compare_graphs', 'get_architecture', 'search_code', 'list_projects', 'index_status', 'check_index_coverage', 'detect_changes'];
// Serena tools annotated readOnly; everything else it offers edits files or memories.
const LSP_READ = ['search_for_pattern', 'get_symbols_overview', 'find_symbol', 'find_referencing_symbols', 'find_implementations', 'find_declaration', 'get_diagnostics_for_file', 'read_memory', 'list_memories', 'initial_instructions'];

export const graphBin = () => which('codebase-memory-mcp');
export const serenaBin = () => which('serena');
export const cortexBin = () => which('cortex');

/** The name codebase-memory-mcp gives a repository: its absolute path with / as -. */
export const graphProject = (repo: string): string => resolvePath(repo).replace(/^\/+|\/+$/g, '').replaceAll('/', '-');

export type StdioServer = {type: 'stdio'; command: string; args: string[]};

/** Stdio MCP server configs for the agent, for the tools that are installed. */
export function mcpServers(cwd: string): Record<string, StdioServer> {
	const servers: Record<string, StdioServer> = {};
	const g = graphBin();
	if (g) servers[GRAPH] = {type: 'stdio', command: g, args: ['--tool-profile=analysis']};
	const s = serenaBin();
	if (s) servers[LSP] = {type: 'stdio', command: s, args: ['start-mcp-server', '--context', 'ide', '--project', resolvePath(cwd), '--enable-web-dashboard', 'false', '--open-web-dashboard', 'false']};
	return servers;
}

export function readOnlyIds(servers: Record<string, unknown>): Set<string> {
	const ids = new Set<string>();
	if (GRAPH in servers) GRAPH_READ.forEach(t => ids.add(`mcp__${GRAPH}__${t}`));
	if (LSP in servers) LSP_READ.forEach(t => ids.add(`mcp__${LSP}__${t}`));
	return ids;
}

/** Run a command to the end without blocking: stdout, stderr, exit code, or timedOut. */
function run(cmd: string, args: string[], timeoutMs: number): Promise<{stdout: string; stderr: string; code: number | null; timedOut: boolean}> {
	return new Promise(res => {
		const child = spawn(cmd, args, {stdio: ['ignore', 'pipe', 'pipe']});
		let stdout = '';
		let stderr = '';
		let timedOut = false;
		const t = setTimeout(() => {
			timedOut = true;
			child.kill();
		}, timeoutMs);
		child.stdout.on('data', d => (stdout += d));
		child.stderr.on('data', d => (stderr += d));
		child.on('error', err => {
			clearTimeout(t);
			res({stdout, stderr: stderr || err.message, code: null, timedOut});
		});
		child.on('close', code => {
			clearTimeout(t);
			res({stdout, stderr, code, timedOut});
		});
	});
}

/** Build or refresh the graph for repo. Returns a one-line summary; never throws. */
export async function index(repoIn: string, timeout = 300): Promise<string> {
	const g = graphBin();
	if (!g) return 'graph: codebase-memory-mcp not installed';
	const repo = resolvePath(repoIn);
	if (!existsSync(join(repo, '.git'))) return `graph: ${basename(repo)} is not a git repository, not indexed`;
	const r = await run(g, ['cli', '--quiet', 'index_repository', JSON.stringify({repo_path: repo})], timeout * 1000);
	if (r.timedOut) return `graph: indexing ${basename(repo)} took longer than ${timeout}s`;
	try {
		const data = JSON.parse(r.stdout) as Record<string, unknown>;
		return `graph: ${data['nodes'] ?? '?'} symbols, ${data['edges'] ?? '?'} edges in ${data['project'] ?? basename(repo)}`;
	} catch {
		return `graph: indexing ${basename(repo)} failed: ${pySlice((r.stderr || r.stdout).trim(), 200)}`;
	}
}

/** [text, isError] from `cortex search <kind> <query>`. */
export async function snowflakeSearch(kind: string, query: string, connection?: string, timeout = 60): Promise<[string, boolean]> {
	if (!['docs', 'object', 'table-details'].includes(kind)) return [`kind must be docs, object or table-details, not ${pyReprValue(kind)}`, true];
	const c = cortexBin();
	if (!c) return ['cortex is not installed', true];
	const r = await run(c, ['search', kind, query, ...(connection ? ['--connection', connection] : [])], timeout * 1000);
	if (r.timedOut) return [`cortex search took longer than ${timeout}s`, true];
	if (r.code !== 0) return [pySlice((r.stderr || r.stdout).trim(), 1000), true];
	try {
		const data = JSON.parse(r.stdout) as unknown;
		const results = data && typeof data === 'object' && !Array.isArray(data) && 'results' in data ? (data as {results: unknown}).results : r.stdout;
		return [pySlice(typeof results === 'string' ? results : pyReprValue(results), 12000), false];
	} catch {
		return [pySlice(r.stdout, 12000), false];
	}
}
