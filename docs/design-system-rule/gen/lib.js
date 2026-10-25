// Generator for the Rule pages (Modernist → terminal). Exact 80-column padding.
export const W = 80;
export const vis = s => s.replace(/<[^>]+>/g, '').replace(/&[a-z]+;/g, 'x').length;
export const pad = (s, n = W) => s + ' '.repeat(Math.max(0, n - vis(s)));
export const row = s => `<div>${pad(s)}</div>`;
export const blank = () => `<div> </div>`;
export const sp = (cls, t) => `<span class="${cls}">${t}</span>`;
export const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

// heavy square frame — the terminal's 2px rule. edge class, title flush-left in the top rule.
export function box(lines, { edge = 'rl', title = '', w = W } = {}) {
  const iw = w - 2;
  const top = title
    ? sp(edge, '┏━ ') + title + sp(edge, ' ' + '━'.repeat(iw - 4 - vis(title)) + '┓')
    : sp(edge, '┏' + '━'.repeat(iw) + '┓');
  const body = lines.map(l => sp(edge, '┃') + pad(' ' + l, iw) + sp(edge, '┃'));
  return [top, ...body, sp(edge, '┗' + '━'.repeat(iw) + '┛')].map(l => `<div>${l}</div>`).join('');
}

// turn divider: heavy rule, number flush left
export const rule = (n) => row(sp('rl', '━━ ') + sp('mu b', String(n).padStart(2, '0')) + sp('rl', ' ' + '━'.repeat(W - 6)));
export const hr = () => row(sp('rl', '━'.repeat(W)));

export function footing({ typed = '', hint = '/new python cli order-metrics', left = '? shortcuts', model = 'claude-sonnet-4-5', cwd = '~/Developer/order-metrics', ctx = '34%', popup = '' } = {}) {
  const inner = typed ? sp('as b', '›') + ' ' + typed + sp('cur', ' ') : sp('as b', '›') + ' ' + sp('cur', ' ') + sp('dm', hint);
  let right = `${model} ${sp('dm', '·')} ${cwd} ${sp('dm', '·')} ctx ${ctx}`;
  if (vis(left) + vis(right) + 6 > W) right = `${model} ${sp('dm', '·')} ctx ${ctx}`;
  if (vis(left) + vis(right) + 6 > W) right = `ctx ${ctx}`;
  const status = `<div>${pad('  ' + sp('dm', left), W - vis(right) - 2)}${sp('mu', right)}  </div>`;
  return box([inner]) + popup + status;
}

export function popup(items, sel = 0) {
  return items.map((it, i) => {
    const [cmd, desc] = it;
    const line = i === sel
      ? ' ' + sp('as b', '■') + ' ' + sp('b', cmd.padEnd(14)) + sp('mu', desc)
      : '   ' + cmd.padEnd(14) + sp('dm', desc);
    return `<div>${pad(line)}</div>`;
  }).join('');
}

// 28×20 mascot: a canoe (ink) with a paddle (accent). I ink · R red · . empty
export const MASCOT = `
.......................RR...
......................RRRR..
......................RRRR..
.....................RRRR...
....................RR......
...................RR.......
..................RR........
.................RR.........
................RR..........
...............RR...........
..............RR............
I............RR............I
II..........RR............II
IIIIIIIIIIIIIIIIIIIIIIIIIIII
.IIIIIIIIIIIIIIIIIIIIIIIIII.
..IIIIIIIIIIIIIIIIIIIIIIII..
....IIIIIIIIIIIIIIIIIIII....
.......IIIIIIIIIIIIII.......
............................
.RR.RR...RR.RR....RR.RR.RR..`.trim().split('\n');
const INK = { I: 'var(--fg)', R: 'var(--ac)' };
export function mascot() {
  const out = [];
  for (let r = 0; r < MASCOT.length; r += 2) {
    let s = '';
    for (let c = 0; c < 28; c++) {
      const a = INK[MASCOT[r][c]], b = INK[MASCOT[r + 1][c]];
      if (!a && !b) s += ' ';
      else if (a === b) s += `<span style="color:${a}">█</span>`;
      else if (a && b) s += `<span style="color:${a};background:${b}">▀</span>`;
      else if (a) s += `<span style="color:${a}">▀</span>`;
      else s += `<span style="color:${b}">▄</span>`;
    }
    out.push(s);
  }
  return out;
}

export function banner({ version = '0.1.0', facts = [], hints = [], tagline = 'projects from the canon' } = {}) {
  const li = 30, ri = W - 3 - li;
  const left = [...mascot().map(l => ' ' + l), '', ' ' + sp('b', 'DS-NEXT') + sp('mu', '  ' + tagline)];
  const right = ['', ...facts.map(([k, v]) => '  ' + sp('dm', k.toUpperCase().padEnd(10)) + v), '', ...hints.map(h => '  ' + sp('dm', h))];
  const title = sp('b', 'DS-NEXT') + sp('dm', ' ' + version);
  const rows = [sp('rl', '┏━ ') + title + sp('rl', ' ' + '━'.repeat(li - 4 - vis(title)) + '┳' + '━'.repeat(ri) + '┓')];
  for (let i = 0; i < Math.max(left.length, right.length); i++) {
    rows.push(sp('rl', '┃') + pad(left[i] || '', li) + sp('rl', '┃') + pad(right[i] || '', ri) + sp('rl', '┃'));
  }
  rows.push(sp('rl', '┗' + '━'.repeat(li) + '┻' + '━'.repeat(ri) + '┛'));
  return rows.map(l => `<div>${l}</div>`).join('');
}

const DS = '_ds/modernist-fb669593-396e-4e4b-a166-55c9d4bbdb45';
export const docHead = (title) => `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title}</title>
<script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet data-dc-atomics><meta name="design_doc_mode" content="canvas">
<link rel="stylesheet" href="${DS}/styles.css">
<script src="${DS}/_ds_bundle.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>body{margin:0;background:var(--color-bg);font-family:var(--font-body);color:var(--color-text)}a{color:var(--color-accent-700)}a:hover{color:var(--color-accent)}code{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.9em}
.sec{padding:40px 44px 36px;border-bottom:2px solid var(--color-divider);scroll-margin-top:16px}.shd{display:flex;align-items:baseline;gap:12px;margin:0 0 18px;flex-wrap:wrap}.sid{font:800 11px var(--font-heading);padding:4px 7px;background:var(--color-text);color:var(--color-bg);text-decoration:none}.sname{font:800 22px/1.1 var(--font-heading);letter-spacing:-.015em}.lede{font:400 15px/1.5 var(--font-body);color:var(--color-neutral-800);max-width:760px;margin:0 0 20px}.snote{font:13px/1.4 var(--font-body);color:var(--color-neutral-700)}
.row{display:flex;flex-wrap:wrap;gap:36px;align-items:flex-start}.opt{flex:none;display:flex;flex-direction:column;gap:9px;scroll-margin-top:16px}.oid{font:800 11px var(--font-heading);padding:4px 7px;background:var(--color-neutral-200);color:var(--color-text);text-decoration:none}.olabel{display:flex;align-items:baseline;gap:8px;font:400 13px/1.3 var(--font-body);color:var(--color-neutral-700);max-width:744px}.opt:target .oid{background:var(--color-accent);color:var(--color-bg)}.next{margin:22px 0 0;font:13px/1.5 var(--font-body);color:var(--color-neutral-700);max-width:900px}
.fr{border-top:2px solid var(--color-text);padding-top:6px}
.t>div{min-height:19px}.t{font-family:"JetBrains Mono",ui-monospace,Menlo,monospace;font-size:12.5px;line-height:19px;white-space:pre;padding:14px 18px;width:744px;box-sizing:border-box;background:var(--bg);color:var(--fg)}
.d{--bg:#201e1d;--sf:#2d2b2b;--fg:#f3f2f2;--mu:#bab6b6;--dm:#7d7979;--rl:#9b9797;--ac:#ff563c;--as:#ff9783;--cur:#f3f2f2;--curfg:#201e1d}
.l{--bg:#f3f2f2;--sf:#eae9e9;--fg:#201e1d;--mu:#605d5d;--dm:#9b9797;--rl:#605d5d;--ac:#ec3013;--as:#ae1800;--cur:#201e1d;--curfg:#f3f2f2}
.ac{color:var(--ac)}.as{color:var(--as)}.dm{color:var(--dm)}.mu{color:var(--mu)}.rl{color:var(--rl)}.b{font-weight:700}.cur{background:var(--cur);color:var(--curfg)}.sf{background:var(--sf)}.cd{background:var(--sf)}.inv{background:var(--fg);color:var(--bg);font-weight:700}.acb{background:var(--ac);color:var(--bg);font-weight:700}
.sw{display:flex;flex-direction:column;gap:6px;font:12px/1.3 var(--font-body);width:118px}.chip{height:44px;display:flex;align-items:flex-end;padding:6px 8px;font:700 11px "JetBrains Mono",monospace}
.tbl{border-collapse:collapse;font:13px/1.45 var(--font-body);max-width:960px}.tbl th{text-align:left;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--color-neutral-700);padding:6px 10px 6px 0;border-bottom:2px solid var(--color-divider);font-weight:600}.tbl td{padding:7px 10px 7px 0;border-bottom:1px solid var(--color-neutral-300);vertical-align:top}.g{font-family:"JetBrains Mono",monospace;font-size:14px;background:var(--color-text);color:var(--color-bg);display:inline-block;min-width:26px;text-align:center;padding:2px 6px}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:0 24px;max-width:1100px}.pr{padding:14px 0 16px;border-top:2px solid var(--color-text)}.pr h4{font:800 17px/1.15 var(--font-heading);margin:0 0 6px;letter-spacing:-.01em}.pr p{font:13px/1.5 var(--font-body);margin:0;color:var(--color-neutral-800)}
</style></helmet>
`;
export const docTail = (props) => `</x-dc>
<script type="text/x-dc" data-dc-script data-props="${esc(JSON.stringify(props)).replace(/"/g, '&quot;')}">
class Component extends DCLogic {
  renderVals() {
    return { mockCls: (this.props.mockTheme ?? "dark") === "light" ? "l" : "d" };
  }
}
</script>
</body>
</html>
`;
export const term = (cls, body) => `<div class="fr"><div class="t ${cls}">${body}</div></div>`;
export const opt = (id, label, body) => `<div class="opt" id="${id}"><div class="olabel"><a class="oid" href="#${id}">${id}</a><span>${label}</span></div>${body}</div>`;
