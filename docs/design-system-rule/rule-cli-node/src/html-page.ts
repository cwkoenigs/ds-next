// The HTML page around the tour (Modernist doc chrome). {{TOC}}, {{BODY}}, {{VERSION}} and %VERBS% are filled by html.ts.
export const PAGE = `<title>Rule Terminal Tour</title>
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
<p class="lede">The tour from <code>rule</code>, chapter by chapter. Every terminal below is the CLI's own output at 80 columns.</p>
</header>
<nav class="toc" aria-label="Chapters">{{TOC}}</nav>
<div class="bar" role="toolbar" aria-label="Mockup display">
<span>Mockups</span>
<div class="seg" id="seg-theme"><button type="button" id="m-dark" data-v="dark">Dark</button><button type="button" id="m-light" data-v="light">Light</button><button type="button" id="m-both" data-v="both">Both</button></div>
<div class="seg" id="seg-fit"><button type="button" id="f-fit" data-v="fit">Fit width</button><button type="button" id="f-real" data-v="real">Actual size</button></div>
</div>
<main>{{BODY}}</main>
<footer>Run it yourself: <code>npm install &amp;&amp; npm run build &amp;&amp; npm link</code>, then <code>rule</code>. The page is generated by <code>rule html</code>.</footer>
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
`;
