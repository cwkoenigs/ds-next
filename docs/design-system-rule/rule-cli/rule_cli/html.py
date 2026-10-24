"""`rule-cli html`: the tour as one self-contained web page, readable on a phone.

Mockups are the same Rich rows the terminal tour prints, exported with their colours;
the prose is plain HTML from spec.py, styled in Modernist doc chrome.
"""
from __future__ import annotations

import io
import os
from collections.abc import Callable
from html import escape

from rich.text import Text

from . import screens as S
from . import spec
from . import ui_style as u
from .tour import make_console


def mock(rows: Callable[[], S.Rows], theme: str) -> str:
    os.environ["COLORTERM"] = "truecolor"
    c = make_console(theme, record=True, width=u.DESIGN_WIDTH, color_system="truecolor", force_terminal=True,
                     file=io.StringIO())
    bg, fg, _ = u.BG[theme]
    for r in rows():
        r = r.copy()
        r.pad_right(u.DESIGN_WIDTH - r.cell_len)
        r.stylize_before(f"{fg} on {bg}")
        c.print(r, no_wrap=True, overflow="crop")
    code = c.export_html(inline_styles=True, code_format="{code}")
    return f'<pre class="term" data-t="{theme}" style="background:{bg};color:{fg}">{code}</pre>'


def mocks(rows: Callable[[], S.Rows], caption: str = "") -> str:
    cap = f'<p class="cap">{escape(caption)}</p>' if caption else ""
    return f'<figure class="mock">{cap}<div class="scroll">{mock(rows, "dark")}{mock(rows, "light")}</div></figure>'


def _mascot() -> S.Rows:
    return [Text(" ").append_text(m) for m in u.mascot_lines()]


def section(n: int, title: str, body: str, anchor: str) -> str:
    return (f'<section id="{anchor}"><h2><a class="chip" href="#{anchor}">{n}</a>{escape(title)}</h2>'
            f"{body}</section>")


def p(s: str, cls: str = "") -> str:
    return f'<p class="{cls}">{escape(s)}</p>' if cls else f"<p>{escape(s)}</p>"


def dl(items) -> str:
    return '<dl class="pairs">' + "".join(f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in items) + "</dl>"


def table(head: list[str], rows: list[list[str]], raw: set[int] = frozenset()) -> str:
    th = "".join(f"<th>{escape(h)}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{c if i in raw else escape(c)}</td>" for i, c in enumerate(r)) + "</tr>"
                 for r in rows)
    return f'<div class="scroll"><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'


def build() -> str:
    secs: list[tuple[str, str, str]] = []  # (anchor, title, body)

    secs.append(("rule", "Rule", "".join([
        p(spec.SUMMARY, "lede"), dl(spec.ASSUMPTIONS)])))

    secs.append(("versus", "Canopy vs Rule", "".join([
        p("The same turn. Canopy is warm and rounded; Rule is ink, red and square, with a numbered rule "
          "opening each turn."),
        mocks(S.rule_vs_canopy, "1b · Rule"),
        table(["Canopy", "Rule"], [list(r) for r in spec.CHANGES_FROM_CANOPY])])))

    secs.append(("principles", "Principles", '<ol class="principles">' + "".join(
        f"<li><h3>{escape(t)}</h3><p>{escape(b)}</p></li>" for t, b in spec.PRINCIPLES) + "</ol>"))

    sw = lambda h: f'<span class="sw" style="background:{h}"></span><code>{h}</code>'
    secs.append(("colour", "Colour roles", "".join([
        p("Eight roles, both from Modernist's ramps. The dark theme inverts the page. There is no ok/warn/err "
          "triad: done is text, warn and err are red (err bold)."),
        table(["Role", "Dark", "Token", "Light", "Token", "Used for"],
              [[r, sw(d), dt, sw(l), lt, use] for r, d, dt, l, lt, use in spec.COLOURS], raw={1, 3}),
        p("ANSI-16: " + "  ".join(f"{k} {v}" for k, v in spec.ANSI16.items()), "small"),
        "<ul class='rules'>" + "".join(f"<li>{escape(r)}</li>" for r in spec.COLOUR_RULES) + "</ul>"])))

    secs.append(("glyphs", "Glyph vocabulary", "".join([
        table(["Glyph", "Name", "Means", "Colour", "Column"],
              [[f'<span class="g">{escape(g)}</span>', escape(n), escape(m), escape(c), escape(col)]
               for g, n, m, c, col in spec.GLYPHS], raw={0, 1, 2, 3, 4}),
        p("Not used: " + ", ".join(spec.RETIRED) + ". The three systems never share a screen.", "small")])))

    g = spec.GRID
    secs.append(("grid", "Grid and the footing", "".join([
        mocks(S.grid_diagram, "5a · the 80-column grid"),
        dl(spec.GRID_NOTES),
        dl([("Design width", str(g["design_width"])), ("Min width", str(g["min_width"])),
            ("Indent", str(g["indent"])), ("Result indent", str(g["result_indent"])),
            ("Label width", str(g["label_width"])), ("Fact separator", "two spaces")]),
        p(spec.CASE)])))

    secs.append(("messages", "Every message type", mocks(S.message_types, "6 · message types")))
    secs.append(("dialogs", "Dialogs", p("Heavy frame, red edge while asking, uppercase title flush left, numbered "
                                         "options with ■ on the focus and □ on the rest.")
                 + mocks(S.dialog_reference, "7 · permission")))

    secs.append(("motion", "Motion", "".join([
        ('<div class="live" aria-hidden="true"><span class="q">▘</span> <span class="v">Drafting</span>'
        '<span class="d">  <span class="s">0</span>s  esc interrupts</span></div>'),
        dl(spec.MOTION),
        p("Spinner verbs: " + " · ".join(spec.VERBS), "small")])))

    secs.append(("mascot", "Mascot", p(spec.MASCOT["note"]) + mocks(_mascot, "canoe · 28×20 px in half-blocks")))

    secs.append(("code", "Where it lands in code", table(["Token / helper", "In ui_style.py", "Differs from Canopy"],
                                                          [list(r) for r in spec.CODE_MAP])))

    for n, title, note in spec.SCREENS:
        secs.append((f"screen-{n}", f"Screen {n} · {title}", p(note) + mocks(S.SCREENS[n])))

    secs.append(("gaps", "Known gaps", "<ul class='rules'>" + "".join(
        f"<li>{escape(x)}</li>" for x in spec.KNOWN_GAPS) + "</ul>"))

    toc = "".join(f'<a href="#{a}"><b>{i}</b>{escape(t)}</a>' for i, (a, t, _) in enumerate(secs))
    body = "".join(section(i, t, b, a) for i, (a, t, b) in enumerate(secs))
    return PAGE.replace("{{TOC}}", toc).replace("{{BODY}}", body).replace("{{VERSION}}", spec.VERSION)


PAGE = """<title>Rule Terminal Tour</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
/* Modernist doc chrome: ink on ground, one red, 2px rules, radius 0, flush left. Mockups carry their own ground. */
:root{--bg:#f3f2f2;--surface:#eae9e9;--ink:#201e1d;--muted:#605d5d;--line:#9b9797;--accent:#ec3013;--accent-text:#ae1800;
--doc:"Archivo",system-ui,sans-serif;--mono:"JetBrains Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#201e1d;--surface:#2d2b2b;--ink:#f3f2f2;--muted:#bab6b6;--line:#7d7979;--accent:#ff563c;--accent-text:#ff9783;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#201e1d;--surface:#2d2b2b;--ink:#f3f2f2;--muted:#bab6b6;--line:#7d7979;--accent:#ff563c;--accent-text:#ff9783;color-scheme:dark}
body{background:var(--bg);color:var(--ink);font:400 16px/1.55 var(--doc)}
.wrap{max-width:860px;margin:0 auto;padding-block:28px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
header .eyebrow{font:600 12px var(--doc);letter-spacing:.08em;text-transform:uppercase;color:var(--accent-text);margin:0 0 10px}
h1{font:800 clamp(30px,8vw,48px)/1.02 var(--doc);letter-spacing:-.02em;margin:0 0 12px;text-wrap:balance}
h2{display:flex;align-items:baseline;gap:12px;font:800 22px/1.15 var(--doc);letter-spacing:-.01em;margin:0 0 16px;text-wrap:balance}
h3{font:800 17px/1.2 var(--doc);margin:0 0 4px}
.chip{flex:none;font:800 12px var(--doc);padding:4px 7px;background:var(--ink);color:var(--bg);text-decoration:none;min-width:14px;text-align:center}
section{border-top:2px solid var(--ink);padding-block:28px 32px;scroll-margin-top:12px}
p{margin:0 0 14px;max-width:65ch}.lede{font-size:18px}.small{font-size:13px;color:var(--muted)}
.toc{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:0 20px;margin:20px 0 28px;border-top:2px solid var(--ink)}
.toc a{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--line);color:var(--ink);text-decoration:none;font-size:14px}
.toc a b{font-variant-numeric:tabular-nums;color:var(--accent-text);min-width:18px}.toc a:hover,.toc a:focus-visible{color:var(--accent-text)}
.bar{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--bg);display:flex;gap:10px;align-items:center;padding-block:8px;border-bottom:2px solid var(--ink);font-size:13px;flex-wrap:wrap}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:10;background:var(--bg)}
.bar span{color:var(--muted);text-transform:uppercase;letter-spacing:.08em;font-weight:600;font-size:11px}
.seg{display:flex;border:2px solid var(--ink)}
.seg button{font:600 13px var(--doc);background:var(--bg);color:var(--ink);border:0;padding:5px 11px;cursor:pointer}
.seg button[aria-pressed="true"]{background:var(--ink);color:var(--bg)}
.seg button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.mock{margin:0 0 18px}.cap{font:600 11px var(--doc);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}
.scroll{overflow-x:auto;max-width:100%;-webkit-overflow-scrolling:touch}
.term{font:400 var(--tsize,12.5px)/1.22 var(--mono);margin:0;padding:12px 14px;width:max-content;border-top:2px solid var(--ink)}
.term span{white-space:pre}
body[data-mock="dark"] .term[data-t="light"],body[data-mock="light"] .term[data-t="dark"]{display:none}
body[data-fit="fit"] .term{--tsize:min(12.5px,calc((100vw - 32px - 28px) / 48.4))}
table{border-collapse:collapse;font-size:14px;min-width:100%}
th{text-align:left;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600;padding:6px 12px 6px 0;border-bottom:2px solid var(--ink)}
td{padding:8px 12px 8px 0;border-bottom:1px solid var(--line);vertical-align:top}
td code,dd code{font-family:var(--mono);font-size:12px}
.sw{display:inline-block;width:18px;height:18px;vertical-align:-4px;margin-right:6px;border:1px solid var(--line)}
.g{font:700 15px var(--mono);background:var(--ink);color:var(--bg);padding:2px 6px;white-space:nowrap}
.pairs{display:grid;grid-template-columns:minmax(0,11em) minmax(0,1fr);gap:8px 16px;margin:0 0 18px}
.pairs dt{font-weight:800}.pairs dd{margin:0;color:var(--muted)}
@media (max-width:520px){.pairs{grid-template-columns:1fr;gap:2px}.pairs dd{margin-bottom:10px}}
.principles{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:0 24px;counter-reset:p}
.principles li{border-top:2px solid var(--ink);padding-block:12px 16px;counter-increment:p}
.principles h3::before{content:counter(p) "  ";color:var(--accent);white-space:pre}
.principles p{font-size:14px;color:var(--muted);margin:0}
.rules{padding-left:0;list-style:none}.rules li{padding-left:18px;position:relative;margin:0 0 6px;max-width:65ch}
.rules li::before{content:"■";position:absolute;left:0;color:var(--accent);font-size:11px;top:3px}
.live{font:400 15px var(--mono);background:#201e1d;color:#7d7979;padding:12px 14px;margin:0 0 18px;border-top:2px solid var(--ink)}
.live .q,.live .v{color:#ff563c}
footer{border-top:2px solid var(--ink);padding-top:16px;font-size:13px;color:var(--muted)}
footer code{font-family:var(--mono)}
</style>
<div class="wrap">
<header>
<p class="eyebrow">ds-next · terminal design system · Modernist direction · {{VERSION}}</p>
<h1>The grid shows. One red, strong rules, nothing rounded.</h1>
<p class="lede">The tour from <code>rule-cli</code>, chapter by chapter. Every terminal below is the CLI's own output at 80 columns.</p>
</header>
<nav class="toc" aria-label="Chapters">{{TOC}}</nav>
<div class="bar" role="toolbar" aria-label="Mockup display">
<span>Mockups</span>
<div class="seg" id="seg-theme"><button type="button" id="m-dark" data-v="dark">Dark</button><button type="button" id="m-light" data-v="light">Light</button><button type="button" id="m-both" data-v="both">Both</button></div>
<div class="seg" id="seg-fit"><button type="button" id="f-fit" data-v="fit">Fit width</button><button type="button" id="f-real" data-v="real">Actual size</button></div>
</div>
<main>{{BODY}}</main>
<footer>Run it yourself: <code>pip install -e rule-cli &amp;&amp; rule-cli</code>. The page is generated by <code>rule-cli html</code>.</footer>
</div>
<script>
(function(){
  var b=document.body, narrow=window.matchMedia("(max-width:760px)").matches;
  var dark=window.matchMedia("(prefers-color-scheme: dark)").matches;
  function get(k,d){try{return localStorage.getItem(k)||d}catch(e){return d}}
  function put(k,v){try{localStorage.setItem(k,v)}catch(e){}}
  function wire(id,attr,key,def){
    var seg=document.getElementById(id);
    function set(v){b.setAttribute(attr,v);seg.querySelectorAll("button").forEach(function(x){x.setAttribute("aria-pressed",String(x.dataset.v===v))});put(key,v)}
    seg.addEventListener("click",function(e){var t=e.target.closest("button");if(t)set(t.dataset.v)});
    set(get(key,def));
  }
  wire("seg-theme","data-mock","rule-mock",narrow?(dark?"dark":"light"):"both");
  wire("seg-fit","data-fit","rule-fit",narrow?"fit":"real");
  var live=document.querySelector(".live");
  if(live && !window.matchMedia("(prefers-reduced-motion: reduce)").matches){
    var Q=["▖","▘","▝","▗"],V=%VERBS%,i=0,q=live.querySelector(".q"),v=live.querySelector(".v"),s=live.querySelector(".s");
    setInterval(function(){i++;q.textContent=Q[i%4];if(i%19===0)v.textContent=V[(i/19)%V.length|0];s.textContent=String(Math.floor(i*0.16)%60)},160);
  }
})();
</script>
"""
PAGE = PAGE.replace("%VERBS%", "[" + ",".join(f'"{v}"' for v in spec.VERBS) + "]")
