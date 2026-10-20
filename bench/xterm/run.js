// ds-next in a real xterm.js: the engine VS Code's terminal uses. Fake ttys never show what
// xterm does to a frame when the panel is resized; this does. `npm install` here first.
//
//   node run.js <cols> <rows> <keys...>
//
// keys: text (typed one character at a time), ENTER, TAB, ESC, CTRLD, RESIZE:<cols>x<rows>
// (xterm reflows, then the pty gets SIGWINCH, as VS Code does), XRESIZE:… (xterm only),
// PRESIZE:… (SIGWINCH only), LINES (row lengths and wrap flags), CELLS (the last written cell
// of rows in $ROWS). Env: CMD runs another program (e.g. cortex) instead of ds-next, SRC sets
// PYTHONPATH (a worktree of another commit), CWD, BOOT (ms to wait for the banner), LOG (a file
// for every byte written and every reply the terminal sent back).
const pty = require('node-pty');
const fs = require('fs');
const { Terminal } = require('@xterm/headless');
const [cols, rows, ...keys] = process.argv.slice(2);
const term = new Terminal({ cols: +cols, rows: +rows, allowProposedApi: true, scrollback: 2000 });
const py = process.env.HOME + '/Developer/ds-next/.venv/bin/python';
const p = pty.spawn(process.env.CMD || py, process.env.CMD ? [] : ['-c', 'from ds_next.cli import app; app()'], {
  name: 'xterm-256color', cols: +cols, rows: +rows, cwd: process.env.CWD || process.env.HOME + '/Developer/try',
  env: { ...process.env, PYTHONPATH: process.env.SRC || '', TERM: 'xterm-256color', COLORTERM: 'truecolor', TERM_PROGRAM: 'vscode' },
});
const log = [];
p.onData(d => { log.push('OUT ' + JSON.stringify(d)); term.write(d); });
term.onData(d => { log.push('IN  ' + JSON.stringify(d)); p.write(d); });   // CPR and other replies
const sleep = ms => new Promise(r => setTimeout(r, ms));
const buf = () => term.buffer.active;
const cursor = () => (buf().cursorY + buf().viewportY) + ',' + buf().cursorX;

function dump() {
  const b = buf(), out = [];
  for (let i = 0; i < b.length; i++) out.push(b.getLine(i).translateToString(true));
  while (out.length && !out[out.length - 1].trim()) out.pop();
  return out;
}
function lines() {
  const b = buf();
  for (let i = 0; i < b.length; i++) {
    const L = b.getLine(i), t = L.translateToString(false);
    if (t.trim() || L.isWrapped) console.log(String(i).padStart(3) + ' len=' + String(L.length).padStart(3) + (L.isWrapped ? ' WRAPPED' : '') + ' |' + t.slice(0, 60));
  }
  console.log('cursor', cursor());
}
function cells() {
  const b = buf();
  for (const i of (process.env.ROWS || '18,19,20').split(',').map(Number)) {
    const L = b.getLine(i); if (!L) continue;
    let last = -1;
    for (let x = 0; x < L.length; x++) if (L.getCell(x).getCode() !== 0) last = x;
    console.log('row', i, 'last written col', last, 'wrapped', L.isWrapped);
  }
  console.log('cursor', cursor());
}
(async () => {
  await sleep(+(process.env.BOOT || 4000));
  for (const k of keys) {
    log.push('KEY ' + k + ' cursor=' + cursor());
    const size = k.includes(':') ? k.split(':')[1].split('x').map(Number) : null;
    if (k === 'LINES') lines();
    else if (k === 'CELLS') cells();
    else if (k.startsWith('RESIZE:')) { term.resize(size[0], size[1]); p.resize(size[0], size[1]); }
    else if (k.startsWith('XRESIZE:')) term.resize(size[0], size[1]);
    else if (k.startsWith('PRESIZE:')) p.resize(size[0], size[1]);
    else if (k === 'ENTER') p.write('\r');
    else if (k === 'TAB') p.write('\t');
    else if (k === 'ESC') p.write('\x1b');
    else if (k === 'CTRLD') p.write('\x04');
    else for (const ch of k) { p.write(ch); await sleep(150); }
    await sleep(500);
  }
  const out = dump();
  out.forEach((l, i) => { if (l.trim()) console.log(String(i).padStart(3) + '|' + l); });
  console.log(`\n== ${out.filter(l => l.includes('New session')).length} 'New session' rules, cursor ${cursor()}`);
  if (process.env.LOG) fs.writeFileSync(process.env.LOG, log.join('\n'));
  p.kill();
  process.exit(0);
})();
