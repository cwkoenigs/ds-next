// Small pieces of Python's behaviour the port keeps, so the files and messages ds writes are the
// ones ds-next writes: repr() in messages, json.dumps spacing, Path.resolve(), shlex.quote(),
// shutil.which(), today's date.
import {existsSync, lstatSync, realpathSync} from 'node:fs';
import {delimiter, dirname, isAbsolute, join, resolve, sep} from 'node:path';

const UNPRINTABLE = /[\p{Cc}\p{Zl}\p{Zp}\p{Cs}]/gu;

/** repr() of a string: 'x', or "it's"; control characters escaped as Python escapes them. */
export function pyRepr(s: string): string {
	const q = s.includes("'") && !s.includes('"') ? '"' : "'";
	let body = s.replace(/\\/g, '\\\\');
	if (q === "'") body = body.replace(/'/g, "\\'");
	body = body.replace(UNPRINTABLE, ch => {
		if (ch === '\n') return '\\n';
		if (ch === '\r') return '\\r';
		if (ch === '\t') return '\\t';
		const c = ch.codePointAt(0)!;
		return c < 0x100 ? `\\x${c.toString(16).padStart(2, '0')}` : `\\u${c.toString(16).padStart(4, '0')}`;
	});
	return q + body + q;
}

/** repr() of a value read from TOML or JSON. */
export function pyReprValue(v: unknown): string {
	if (v === undefined || v === null) return 'None';
	if (typeof v === 'string') return pyRepr(v);
	if (typeof v === 'boolean') return v ? 'True' : 'False';
	if (typeof v === 'number' || typeof v === 'bigint') return String(v);
	if (v instanceof Date) return v.toISOString();
	if (Array.isArray(v)) return `[${v.map(pyReprValue).join(', ')}]`;
	if (typeof v === 'object') return `{${Object.entries(v as Record<string, unknown>).map(([k, x]) => `${pyRepr(k)}: ${pyReprValue(x)}`).join(', ')}}`;
	return String(v);
}

/** str() of a JSON value, as `str(json.get(...))` would give it. */
export const pyStr = (v: unknown): string => (typeof v === 'string' ? v : pyReprValue(v));

/** json.dumps(value) with Python's defaults: ", " and ": " separators, non-ASCII escaped. */
export function pyJsonDumps(v: unknown): string {
	if (v === undefined || v === null) return 'null';
	if (typeof v === 'string') return JSON.stringify(v).replace(/[\u007f-￿]/g, c => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);
	if (typeof v !== 'object') return JSON.stringify(v);
	if (Array.isArray(v)) return `[${v.map(pyJsonDumps).join(', ')}]`;
	return `{${Object.entries(v as Record<string, unknown>).map(([k, x]) => `${pyJsonDumps(k)}: ${pyJsonDumps(x)}`).join(', ')}}`;
}

/** json.dumps(value, indent=n): one item per line, empty lists and objects as [] and {}. */
export function pyJsonIndent(v: unknown, n = 1, depth = 0): string {
	const pad = (d: number) => ' '.repeat(n * d);
	if (v instanceof Map) v = Object.fromEntries(v);
	if (Array.isArray(v)) {
		if (!v.length) return '[]';
		return `[\n${v.map(x => pad(depth + 1) + pyJsonIndent(x, n, depth + 1)).join(',\n')}\n${pad(depth)}]`;
	}
	if (v && typeof v === 'object') {
		const entries = Object.entries(v as Record<string, unknown>);
		if (!entries.length) return '{}';
		return `{\n${entries.map(([k, x]) => `${pad(depth + 1)}${pyJsonDumps(k)}: ${pyJsonIndent(x, n, depth + 1)}`).join(',\n')}\n${pad(depth)}}`;
	}
	return pyJsonDumps(v);
}

/** Path.resolve(): absolute, with symbolic links in the part that exists followed. */
export function resolvePath(p: string): string {
	let head = resolve(p);
	const tail: string[] = [];
	while (!existsSync(head)) {
		const up = dirname(head);
		if (up === head) break;
		tail.unshift(head.slice(up.length).replace(/^[\\/]/, ''));
		head = up;
	}
	try {
		head = realpathSync(head);
	} catch {
		// keep it as given
	}
	return tail.length ? join(head, ...tail) : head;
}

export const isSymlink = (p: string): boolean => {
	try {
		return lstatSync(p).isSymbolicLink();
	} catch {
		return false;
	}
};

/** `inner` is `outer` or below it. */
export const within = (outer: string, inner: string): boolean => inner === outer || inner.startsWith(outer.endsWith(sep) ? outer : outer + sep);

/** shlex.quote(). */
export function shlexQuote(s: string): string {
	if (!s) return "''";
	if (/^[\w@%+=:,./-]+$/.test(s)) return s;
	return "'" + s.replace(/'/g, `'"'"'`) + "'";
}

/** shutil.which(): the command's path on PATH, honouring PATHEXT on Windows. */
export function which(cmd: string): string | undefined {
	if (isAbsolute(cmd)) return existsSync(cmd) ? cmd : undefined;
	const exts = process.platform === 'win32' ? ['', ...(process.env['PATHEXT'] ?? '.EXE;.CMD;.BAT').split(';')] : [''];
	for (const dir of (process.env['PATH'] ?? '').split(delimiter)) {
		if (!dir) continue;
		for (const ext of exts) {
			const p = join(dir, cmd + ext);
			try {
				if (existsSync(p) && !lstatSync(p).isDirectory()) return p;
			} catch {
				// unreadable entry: not this one
			}
		}
	}
	return undefined;
}

/** date.today(): the local date as YYYY-MM-DD. */
export function today(): string {
	const d = new Date();
	return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** A YYYY-MM-DD date plus some days. */
export function addDays(day: string, n: number): string {
	const [y, m, d] = day.split('-').map(Number) as [number, number, number];
	const t = new Date(Date.UTC(y, m - 1, d + n));
	return t.toISOString().slice(0, 10);
}

/** text[:n], by code point as Python slices. */
export const pySlice = (s: string, n: number): string => (s.length <= n ? s : Array.from(s).slice(0, n).join(''));
