// What this machine has, for the banner and the Rail toolbar: the canon, skills-os, docs-ds, and
// where the repo you're in stands against the canon. Nothing here throws; a missing piece says so.
import {Canon, docsShellPath, isDir, Skills} from '../ds/kb.js';
import {check, findRepo} from '../ds/reconcile.js';

export type Desk = {
	canon?: {standards: number; scaffolds: number; root: string};
	skills?: number;
	docs: boolean;
	/** This repo against the canon (ds-next's toolbar), read again before each prompt. */
	where: () => string;
};

export const NO_DESK: Desk = {docs: false, where: () => 'not a ds repo'};

export function readDesk(cwd: string): Desk {
	let canon: Canon | undefined;
	let info: Desk['canon'];
	try {
		canon = new Canon();
		info = {standards: canon.standards.size, scaffolds: canon.scaffolds.size, root: canon.root};
	} catch {
		canon = undefined;
	}
	let skills: number | undefined;
	try {
		const s = new Skills();
		skills = s.root && isDir(s.root) ? s.all.size : undefined;
	} catch {
		skills = undefined;
	}
	const docs = Boolean(docsShellPath() && isDir(docsShellPath()!));
	const where = (): string => {
		try {
			const repo = findRepo(cwd);
			if (!repo) return 'not a ds repo';
			return canon ? check(repo, canon).summary() : 'canon not found';
		} catch (err) {
			return `status unavailable (${(err as Error).name})`; // the toolbar must never take the terminal down
		}
	};
	return {canon: info, skills, docs, where};
}
