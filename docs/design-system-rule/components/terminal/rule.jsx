// Rule terminal primitives (React, no build step; window.Rule). One 19px line per row, 80 cols.
// Colours from ../../tokens/colors.css (--rl-*). Heavy square frames, squares as markers, one red.
(function () {
  const h = React.createElement;
  const mono = { fontFamily: 'var(--rl-mono)', fontSize: 'var(--rl-font-size)', lineHeight: 'var(--rl-line)', whiteSpace: 'pre' };
  const C = (role) => ({ color: `var(--rl-${role})` });
  const pad = (s, n) => s + ' '.repeat(Math.max(0, n - s.length));
  const Term = ({ theme = 'dark', cols = 80, children }) =>
    h('div', { 'data-theme': theme, style: { ...mono, width: `calc(${cols}ch + 36px)`, padding: '14px 18px', boxSizing: 'border-box', background: 'var(--rl-bg)', color: 'var(--rl-text)' } }, children);
  const Line = ({ children, style }) => h('div', { style: { minHeight: 'var(--rl-line)', ...style } }, children);
  // TurnRule: ━━ 03 ━━━… flush-left number, opens every prompt
  const TurnRule = ({ n, cols = 80 }) => h(Line, null, h('span', { style: C('rule') }, '━━ '), h('b', { style: C('muted') }, String(n).padStart(2, '0')), h('span', { style: C('rule') }, ' ' + '━'.repeat(cols - 6)));
  const You = ({ children }) => h(Line, null, h('b', { style: C('accent-text') }, '›'), ' ', children);
  const Agent = ({ children }) => React.Children.toArray(children).map((l, i) => h(Line, { key: i }, i === 0 ? h('span', { style: C('accent') }, '■') : ' ', ' ', l));
  const Heading = ({ children }) => h(Line, null, '  ', h('b', null, String(children).toUpperCase()));
  const Tool = ({ name, args = '', state = 'done' }) => h(Line, null,
    h('span', { style: C({ running: 'dim', done: 'text', failed: 'accent' }[state]) }, state === 'running' ? '▫' : '▪'), ' ', h('b', null, name), args ? h('span', { style: C('muted') }, ' ' + args) : null);
  const Result = ({ children, more = 0, error = false, keyName = 'ctrl-o' }) => [
    h(Line, { key: 'r', style: error ? { ...C('accent-text'), fontWeight: 700 } : C('dim') }, '  └ ', children),
    more ? h(Line, { key: 'f', style: C('dim') }, `    └ ${more} more lines  ${keyName}`) : null];
  const Thinking = ({ secs, children }) => secs != null
    ? h(Line, { style: C('dim') }, `· Thought for ${secs}s  ctrl-o`)
    : React.Children.toArray(children).map((l, i) => h(Line, { key: i, style: C('dim') }, i === 0 ? '· ' : '  ', l));
  const Working = ({ verb = 'Drafting', secs = 0, frame = 1 }) => h(Line, null, h('span', { style: C('accent') }, '▖▘▝▗'[frame % 4] + ' ' + verb), h('span', { style: C('dim') }, `  ${secs}s  esc interrupts`));
  const Outcome = ({ kind = 'ok', subject, detail }) => h(Line, null,
    h('span', { style: kind === 'ok' ? C('text') : { ...C('accent'), fontWeight: kind === 'err' ? 700 : 400 } }, { ok: '✓', warn: '⚠', err: '✗' }[kind]), ' ', h('b', null, subject), detail ? h('span', { style: C('muted') }, '  ' + detail) : null);
  const Facts = ({ items }) => h(Line, { style: C('dim') }, '  ' + items.join('  '));
  const Code = ({ children }) => h('span', { style: { background: 'var(--rl-surface)' } }, ` ${children} `);
  const Labelled = ({ label, upper = false, children }) => h(Line, null, '  ', h('span', { style: C('dim') }, pad(upper ? label.toUpperCase() : label, 12)), ' ', children);
  // Frame: heavy square; edge rule|accent; title uppercase flush left in the rule
  const Frame = ({ edge = 'rule', title, cols = 80, children }) => {
    const iw = cols - 2, ec = C(edge);
    const top = title
      ? h(Line, null, h('span', { style: ec }, '┏━ '), h('b', { style: ec }, title.toUpperCase()), h('span', { style: ec }, ' ' + '━'.repeat(iw - 4 - title.length) + '┓'))
      : h(Line, { style: ec }, '┏' + '━'.repeat(iw) + '┓');
    return [top, ...React.Children.toArray(children).map((c, i) => h(Line, { key: i }, h('span', { style: ec }, '┃'), ' ', h('span', { style: { display: 'inline-block', width: `${iw - 1}ch` } }, c), h('span', { style: ec }, '┃'))),
      h(Line, { key: 'b', style: ec }, '┗' + '━'.repeat(iw) + '┛')];
  };
  const InputBox = ({ typed = '', hint = '/new python cli order-metrics', cols = 80 }) =>
    h(Frame, { cols }, h('span', null, h('b', { style: C('accent-text') }, '›'), ' ', typed, h('span', { style: { background: 'var(--rl-text)', color: 'var(--rl-bg)' } }, ' '), typed ? null : h('span', { style: C('dim') }, hint)));
  const StatusRow = ({ left = '? shortcuts', model = 'claude-sonnet-4-5', cwd = '~/Developer', ctx = '34%', cols = 80 }) => {
    let right = `${model} · ${cwd} · ctx ${ctx}`;
    if (left.length + right.length + 6 > cols) right = `${model} · ctx ${ctx}`;
    if (left.length + right.length + 6 > cols) right = `ctx ${ctx}`;
    return h(Line, null, h('span', { style: C('dim') }, pad('  ' + left, cols - right.length - 2)), h('span', { style: C('muted') }, right), '  ');
  };
  const Popup = ({ items, selected = 0 }) => items.map(([cmd, desc], i) => i === selected
    ? h(Line, { key: i }, ' ', h('b', { style: C('accent-text') }, '■'), ' ', h('b', null, pad(cmd, 14)), h('span', { style: C('muted') }, desc))
    : h(Line, { key: i }, '   ' + pad(cmd, 14), h('span', { style: C('dim') }, desc)));
  const Dialog = ({ title, body = [], question = 'Proceed?', options, selected = 1, cols = 80 }) =>
    h(Frame, { edge: 'accent', title, cols }, ...body, ' ', h('b', null, question.toUpperCase()), ...options.map((o, i) => i + 1 === selected
      ? h('span', null, h('b', { style: C('accent-text') }, '■'), ' ', h('b', null, i + 1), '  ', o)
      : h('span', null, h('span', { style: C('dim') }, '□'), ' ', h('span', { style: C('muted') }, i + 1), '  ', o)));
  const Footing = ({ dialog, popup, ...rest }) => [dialog || h(InputBox, rest), popup || null, h(StatusRow, rest)];
  const MAP = `.......................RR...
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
.RR.RR...RR.RR....RR.RR.RR..`.split('\n');
  const INK = { I: 'var(--rl-text)', R: 'var(--rl-accent)' };
  const Mascot = () => {
    const rows = [];
    for (let r = 0; r < MAP.length; r += 2) {
      const cells = [];
      for (let c = 0; c < 28; c++) {
        const a = INK[MAP[r][c]], b = INK[MAP[r + 1][c]];
        if (!a && !b) cells.push(' ');
        else if (a === b) cells.push(h('span', { key: c, style: { color: a } }, '█'));
        else if (a && b) cells.push(h('span', { key: c, style: { color: a, background: b } }, '▀'));
        else if (a) cells.push(h('span', { key: c, style: { color: a } }, '▀'));
        else cells.push(h('span', { key: c, style: { color: b } }, '▄'));
      }
      rows.push(h(Line, { key: r }, ...cells));
    }
    return rows;
  };
  window.Rule = { Term, Line, TurnRule, You, Agent, Heading, Tool, Result, Thinking, Working, Outcome, Facts, Code, Labelled, Frame, InputBox, StatusRow, Popup, Dialog, Footing, Mascot };
})();
