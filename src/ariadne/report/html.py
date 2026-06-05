"""Self-contained interactive workup report (ADR-0017).

Renders a single offline ``report.html`` from a persisted workup's artifacts
(``note.md`` + ``provenance.jsonl`` + ``citations.json`` + optional
``tradecraft.json`` / ``governance.json``). No server, no network, no runtime
deps — CSS + JS + data are embedded inline so the file opens with a double-click
and survives an air-gap. The note stays the source of truth; this is a *view*.

Design: provenance is the hero. Every ``[cite:gN]`` is a clickable chip that
reveals the exact query that grounds it; a radial "thread" graph ties the entity
to its evidence by source. Structured on Shneiderman's overview -> zoom/filter ->
details-on-demand.
"""

from __future__ import annotations

import html as _html
import json
import re
from pathlib import Path
from typing import Any

from ariadne.provenance.hook import _source_label

_CITE_RE = re.compile(r"\[cite:(g\d+)\]")
_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _inline(text: str) -> str:
    """Escape one line of note prose, then re-introduce bold/italic + cite chips."""
    s = _html.escape(text)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", s)
    return _CITE_RE.sub(
        lambda m: f'<button class="cite" data-cite="{m.group(1)}">{m.group(1)}</button>', s
    )


def _render_note_html(note: str) -> str:
    """Minimal, dependency-free Markdown -> HTML for the analytic note."""
    out: list[str] = []
    in_ul = False

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    for raw in note.splitlines():
        line = raw.rstrip()
        if not line.strip():
            close_ul()
            continue
        header = _HEADER_RE.match(line)
        if header:
            close_ul()
            level = len(header.group(1))
            out.append(f"<h{level}>{_inline(header.group(2))}</h{level}>")
            continue
        bullet = _BULLET_RE.match(line)
        if bullet:
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline(bullet.group(1))}</li>")
            continue
        close_ul()
        out.append(f"<p>{_inline(line)}</p>")
    close_ul()
    return "\n".join(out)


def extract_report_data(workup_dir: str | Path) -> dict[str, Any]:
    """Read a persisted workup directory into a JSON-serializable report payload."""
    d = Path(workup_dir)
    note = (d / "note.md").read_text(encoding="utf-8") if (d / "note.md").exists() else ""
    cites = _load_json(d / "citations.json") or {}
    entity = cites.get("entity") or d.name
    ledger = []
    for e in _read_ledger(d / "provenance.jsonl"):
        tool = e.get("tool", "")
        tool_input = e.get("tool_input", {}) or {}
        query = (
            tool_input.get("query")
            or tool_input.get("sql")
            or json.dumps(tool_input, ensure_ascii=False)
        )
        ledger.append(
            {
                "id": e.get("id", ""),
                "tool": tool,
                "source": _source_label(tool),
                "query": query,
                "excerpt": str(e.get("response_excerpt", "")),
            }
        )
    return {
        "entity": entity,
        "note_html": _render_note_html(note),
        "citations": {
            k: cites.get(k) for k in ("ok", "cited", "dangling", "unused", "unsupported", "uncited")
        },
        "ledger": ledger,
        "tradecraft": _load_json(d / "tradecraft.json"),
        "governance": _load_json(d / "governance.json"),
    }


def render_report(workup_dir: str | Path) -> str:
    """Return the full self-contained HTML report for ``workup_dir``."""
    data = extract_report_data(workup_dir)
    # Guard the JSON against premature </script> termination inside the data island.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    title = _html.escape(str(data["entity"]))
    return _TEMPLATE.replace("__ENTITY_TITLE__", title).replace("/*__REPORT_DATA__*/", payload)


def write_report(workup_dir: str | Path) -> Path:
    """Write ``report.html`` into ``workup_dir`` and return its path."""
    out = Path(workup_dir) / "report.html"
    out.write_text(render_report(workup_dir), encoding="utf-8")
    return out


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ariadne · __ENTITY_TITLE__</title>
<style>
:root{
  --bg:#0b0d12; --bg2:#0e1118; --panel:#13161f; --panel2:#171b26;
  --line:#242a38; --ink:#e9e5d8; --soft:#b9bdc9; --muted:#7c8190;
  --thread:#e0a73c; --graph:#69b6d6; --relational:#b58ce0; --text:#76d3a4;
  --ok:#76d3a4; --bad:#e8746e;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif;
  --sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{
  background:
    radial-gradient(1200px 600px at 80% -10%, #15324022, transparent 60%),
    radial-gradient(900px 500px at -10% 10%, #2a1f3a22, transparent 55%),
    var(--bg);
  color:var(--ink); font-family:var(--sans); line-height:1.5;
  -webkit-font-smoothing:antialiased;
}
body::before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.035;z-index:1;
  background-image:radial-gradient(#fff 1px,transparent 1px);background-size:3px 3px;}
a{color:var(--thread)}
.wrap{max-width:1280px;margin:0 auto;padding:0 28px 80px}

/* Masthead */
header.top{position:sticky;top:0;z-index:20;backdrop-filter:blur(8px);
  background:linear-gradient(#0b0d12ee,#0b0d12bb);border-bottom:1px solid var(--line)}
.top .row{max-width:1280px;margin:0 auto;padding:16px 28px;display:flex;align-items:baseline;gap:18px;flex-wrap:wrap}
.mark{font-family:var(--serif);font-size:15px;letter-spacing:.42em;text-transform:uppercase;color:var(--thread)}
.mark b{font-weight:600}
.crumb{color:var(--muted);font-size:12px;letter-spacing:.22em;text-transform:uppercase}
h1.entity{font-family:var(--serif);font-weight:600;font-size:30px;letter-spacing:.01em;margin:0}
.entity small{display:block;font-family:var(--sans);font-size:11px;letter-spacing:.32em;
  text-transform:uppercase;color:var(--muted);margin-bottom:4px;font-weight:600}

/* Dashboard */
.dash{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:26px 0 8px}
.stat{background:linear-gradient(180deg,var(--panel),var(--bg2));border:1px solid var(--line);
  border-radius:14px;padding:16px 18px;position:relative;overflow:hidden}
.stat .k{font-size:10.5px;letter-spacing:.24em;text-transform:uppercase;color:var(--muted);font-weight:700}
.stat .v{font-family:var(--serif);font-size:30px;margin-top:8px;line-height:1}
.stat .sub{font-size:11.5px;color:var(--soft);margin-top:6px}
.stat .rail{position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--thread)}
.stat.ok .rail{background:var(--ok)} .stat.bad .rail{background:var(--bad)}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;
  letter-spacing:.06em;padding:3px 9px;border-radius:999px;border:1px solid currentColor}
.pill.ok{color:var(--ok)} .pill.bad{color:var(--bad)}

/* Layout */
.grid{display:grid;grid-template-columns:1.15fr .85fr;gap:24px;margin-top:24px}
@media(max-width:980px){.grid{grid-template-columns:1fr}}
.card{background:linear-gradient(180deg,var(--panel),var(--bg2));border:1px solid var(--line);border-radius:16px}
.card>h2{font-family:var(--sans);font-size:11px;letter-spacing:.28em;text-transform:uppercase;
  color:var(--muted);font-weight:700;margin:0;padding:16px 22px;border-bottom:1px solid var(--line)}
.note{padding:6px 26px 26px;font-family:var(--serif);font-size:17px;color:#efeada;max-height:none}
.note h1,.note h2,.note h3{font-family:var(--serif);color:var(--ink);line-height:1.25;margin:26px 0 8px}
.note h1{font-size:24px} .note h2{font-size:20px;color:var(--thread)} .note h3{font-size:17px;letter-spacing:.02em}
.note p{margin:10px 0} .note ul{margin:8px 0 8px 2px;padding-left:20px} .note li{margin:6px 0}
.note strong{color:#fff;font-weight:600} .note em{color:var(--soft)}
.note .blk-hot{background:#e0a73c14;box-shadow:inset 3px 0 0 var(--thread);border-radius:4px;
  transition:background .25s}

/* Cite chips */
.cite{font-family:var(--mono);font-size:11px;font-weight:600;color:var(--thread);
  background:#e0a73c14;border:1px solid #e0a73c44;border-radius:6px;padding:1px 6px;margin:0 1px;
  cursor:pointer;vertical-align:baseline;transition:all .15s;letter-spacing:.02em}
.cite:hover,.cite.sel{background:var(--thread);color:#1a1205;border-color:var(--thread);
  box-shadow:0 0 0 3px #e0a73c33}

/* Graph */
.graphwrap{padding:10px 14px 18px}
#graph{width:100%;height:430px;display:block}
.legend{display:flex;gap:16px;flex-wrap:wrap;padding:0 22px 16px;font-size:11px;color:var(--soft)}
.legend i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle}
.node{cursor:pointer}
.node circle{transition:r .15s,opacity .2s,stroke-width .15s}
.node text{font-family:var(--mono);font-size:10px;fill:var(--soft);pointer-events:none}
.edge{fill:none;stroke:var(--line);stroke-width:1.4;transition:stroke .2s,stroke-width .2s,opacity .2s}
.edge.hot{stroke:var(--thread);stroke-width:2.4}
.dim{opacity:.16}

/* Evidence drawer */
.drawer{position:fixed;right:0;top:0;bottom:0;width:min(460px,92vw);z-index:40;
  background:linear-gradient(180deg,#10131c,#0b0d12);border-left:1px solid var(--line);
  box-shadow:-30px 0 60px #0009;transform:translateX(100%);transition:transform .32s cubic-bezier(.22,1,.36,1);
  display:flex;flex-direction:column}
.drawer.open{transform:none}
.drawer .dh{padding:18px 22px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:12px}
.drawer .dh .gid{font-family:var(--mono);font-size:18px;color:var(--thread);font-weight:700}
.drawer .x{margin-left:auto;background:none;border:1px solid var(--line);color:var(--soft);
  border-radius:8px;width:32px;height:32px;cursor:pointer;font-size:16px}
.drawer .x:hover{color:var(--ink);border-color:var(--muted)}
.drawer .body{padding:20px 22px;overflow:auto}
.srcbadge{font-size:10px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;
  padding:3px 9px;border-radius:999px}
.lbl{font-size:10.5px;letter-spacing:.24em;text-transform:uppercase;color:var(--muted);
  font-weight:700;margin:18px 0 7px}
.qbox{font-family:var(--mono);font-size:12.5px;line-height:1.55;color:#cfe6f2;white-space:pre-wrap;
  background:#0a0c11;border:1px solid var(--line);border-radius:10px;padding:14px;overflow:auto}
.exbox{font-family:var(--mono);font-size:12px;line-height:1.55;color:var(--soft);white-space:pre-wrap;
  background:#0a0c11;border:1px solid var(--line);border-radius:10px;padding:14px;max-height:240px;overflow:auto}
.scrim{position:fixed;inset:0;background:#0008;opacity:0;pointer-events:none;transition:opacity .3s;z-index:35}
.scrim.open{opacity:1;pointer-events:auto}

/* Trajectory */
.traj{display:flex;gap:0;align-items:stretch;overflow-x:auto;padding:18px 22px}
.step{min-width:118px;border:1px solid var(--line);border-radius:12px;padding:11px 13px;margin-right:10px;
  cursor:pointer;background:var(--panel2);transition:border-color .2s,transform .2s;flex:0 0 auto}
.step:hover{border-color:var(--thread);transform:translateY(-2px)}
.step .sg{font-family:var(--mono);font-weight:700;color:var(--thread);font-size:13px}
.step .ss{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-top:5px}
.step .sq{font-family:var(--mono);font-size:10.5px;color:var(--soft);margin-top:7px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.foot{color:var(--muted);font-size:11px;text-align:center;margin-top:40px;letter-spacing:.06em}
[data-src=graph]{color:var(--graph)} [data-src=relational]{color:var(--relational)}
[data-src=text]{color:var(--text)} [data-src=evidence]{color:var(--soft)}
.bgs-graph{background:#69b6d622;color:var(--graph)} .bgs-relational{background:#b58ce022;color:var(--relational)}
.bgs-text{background:#76d3a422;color:var(--text)} .bgs-evidence{background:#7c819022;color:var(--soft)}
.reveal{opacity:0;transform:translateY(10px);animation:rise .6s cubic-bezier(.22,1,.36,1) forwards}
@keyframes rise{to{opacity:1;transform:none}}
</style>
</head>
<body>
<header class="top"><div class="row">
  <span class="mark"><b>ARIADNE</b></span>
  <span class="crumb">analytic workup · provenance-grounded</span>
</div></header>

<div class="wrap">
  <div class="reveal" style="margin-top:30px">
    <h1 class="entity"><small>Target entity</small><span id="entity">__ENTITY_TITLE__</span></h1>
  </div>

  <section class="dash reveal" id="dash" style="animation-delay:.05s"></section>

  <div class="grid">
    <section class="card reveal" style="animation-delay:.12s">
      <h2>Analytic note · click a <span style="color:var(--thread)">cite</span> to trace it</h2>
      <div class="note" id="note"></div>
    </section>
    <section class="card reveal" style="animation-delay:.18s">
      <h2>Provenance thread · entity → source → evidence</h2>
      <div class="graphwrap"><svg id="graph" viewBox="0 0 600 430" preserveAspectRatio="xMidYMid meet"></svg></div>
      <div class="legend" id="legend"></div>
    </section>
  </div>

  <section class="card reveal" style="margin-top:24px;animation-delay:.24s">
    <h2>Evidence trajectory · the order the agent gathered ground truth</h2>
    <div class="traj" id="traj"></div>
  </section>

  <div class="foot">Self-contained · offline · generated by Ariadne from note.md + provenance.jsonl — the note is the source of truth.</div>
</div>

<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" aria-hidden="true">
  <div class="dh"><span class="gid" id="d-gid"></span><span class="srcbadge" id="d-src"></span>
    <button class="x" id="d-x" aria-label="Close">×</button></div>
  <div class="body">
    <div class="lbl">Evidence query</div><div class="qbox" id="d-q"></div>
    <div class="lbl">Returned excerpt</div><div class="exbox" id="d-ex"></div>
  </div>
</aside>

<script id="ariadne-report-data" type="application/json">/*__REPORT_DATA__*/</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("ariadne-report-data").textContent);
const byId = Object.fromEntries(DATA.ledger.map(e => [e.id, e]));
const $ = s => document.querySelector(s);

// Which gN are actually cited in the note, and how often (for node weight).
const citeCounts = {};
document.getElementById("note").innerHTML = DATA.note_html || "<p style='color:var(--muted)'>No note.</p>";
document.querySelectorAll("#note .cite").forEach(b => {
  const id = b.dataset.cite; citeCounts[id] = (citeCounts[id]||0)+1;
  b.addEventListener("click", () => selectEvidence(id, b));
});

// ---- Dashboard ----
const c = DATA.citations || {};
const nCited=(c.cited||[]).length, nUncited=(c.uncited||[]).length,
      nDangling=(c.dangling||[]).length, nUnsup=(c.unsupported||[]).length;
const gov = DATA.governance || null, tc = DATA.tradecraft || null;
const govOk = gov ? gov.ok !== false : null;
function stat(cls, k, v, sub){return `<div class="stat ${cls}"><div class="rail"></div>
  <div class="k">${k}</div><div class="v">${v}</div><div class="sub">${sub}</div></div>`;}
$("#dash").innerHTML = [
  stat(c.ok?"ok":"bad","Citation gate", c.ok?'<span class="pill ok">PASS</span>':'<span class="pill bad">FAIL</span>',
       `${nCited} cited · ${nUncited} uncited · ${nDangling} dangling`),
  stat("","Evidence calls", DATA.ledger.length, `${new Set(DATA.ledger.map(e=>e.source)).size} source(s) engaged`),
  gov!==null ? stat(govOk?"ok":"bad","Read-only contract", govOk?'<span class="pill ok">UPHELD</span>':'<span class="pill bad">VIOLATED</span>',
       `${(gov.write_attempts||[]).length} write attempt(s)`) : "",
  tc!==null ? stat("","ICD-203 tradecraft", (tc.standard_terms||[]).length,
       `${(tc.nonstandard_terms||[]).length} non-standard · confidence ${tc.has_confidence_statement?"stated":"—"}`) : "",
].join("");

// ---- Radial provenance graph ----
const SRC_COLORS={graph:"#69b6d6",relational:"#b58ce0",text:"#76d3a4",evidence:"#7c8190"};
const W=600,H=430,cx=W/2,cy=H/2+6;
const sources=[...new Set(DATA.ledger.map(e=>e.source))];
const svg=$("#graph"); const NS="http://www.w3.org/2000/svg";
function el(t,a){const n=document.createElementNS(NS,t);for(const k in a)n.setAttribute(k,a[k]);return n;}
const pos={}; // id -> {x,y}
// sources on an inner ring
sources.forEach((s,i)=>{const a=-Math.PI/2 + i/sources.length*2*Math.PI;
  pos["src:"+s]={x:cx+Math.cos(a)*92,y:cy+Math.sin(a)*92,a};});
// evidence on outer ring, grouped near their source angle
const bySrc={}; DATA.ledger.forEach(e=>{(bySrc[e.source]=bySrc[e.source]||[]).push(e);});
DATA.ledger.forEach(e=>{
  const grp=bySrc[e.source], idx=grp.indexOf(e), base=pos["src:"+e.source].a;
  const spread=Math.min(0.34,(grp.length-1)*0.12), off=grp.length>1? -spread/2+idx/(grp.length-1)*spread:0;
  const a=base+off; pos[e.id]={x:cx+Math.cos(a)*182,y:cy+Math.sin(a)*182};
});
const edges=[];
sources.forEach(s=>edges.push(["entity","src:"+s,null]));
DATA.ledger.forEach(e=>edges.push(["src:"+e.source,e.id,e.id]));
pos["entity"]={x:cx,y:cy};
// thread edges (curved)
const eEls={};
edges.forEach(([a,b,gid])=>{const p1=pos[a],p2=pos[b];
  const mx=(p1.x+p2.x)/2,my=(p1.y+p2.y)/2, dx=p2.x-p1.x,dy=p2.y-p1.y;
  const cxp=mx-dy*0.12, cyp=my+dx*0.12;
  const path=el("path",{class:"edge",d:`M${p1.x},${p1.y} Q${cxp},${cyp} ${p2.x},${p2.y}`});
  if(gid){path.dataset.gid=gid;(eEls[gid]=eEls[gid]||[]).push(path);}
  svg.appendChild(path);});
// nodes
function addNode(id,x,y,r,color,label,onclick){
  const g=el("g",{class:"node",transform:`translate(${x},${y})`});
  const circ=el("circle",{r:r,fill:color+"22",stroke:color,"stroke-width":1.6});
  g.appendChild(circ);
  if(label!==null){const t=el("text",{"text-anchor":"middle",y:r+13});t.textContent=label;g.appendChild(t);}
  if(onclick){g.style.cursor="pointer";g.addEventListener("click",onclick);}
  g.dataset.node=id; svg.appendChild(g); return g;
}
addNode("entity",cx,cy,17,"#e0a73c",null,null)
  .appendChild(Object.assign(el("text",{"text-anchor":"middle",dy:"0.35em",style:"fill:#1a1205;font-weight:700;font-size:11px"}),{textContent:(DATA.entity||"?").slice(0,3).toUpperCase()}));
sources.forEach(s=>addNode("src:"+s,pos["src:"+s].x,pos["src:"+s].y,11,SRC_COLORS[s]||"#7c8190",s,null));
DATA.ledger.forEach(e=>{const w=4.5+(citeCounts[e.id]||0)*2.4;
  addNode(e.id,pos[e.id].x,pos[e.id].y,Math.min(w,12),SRC_COLORS[e.source]||"#7c8190",e.id,
    ()=>selectEvidence(e.id,null));});
$("#legend").innerHTML=sources.map(s=>`<span><i style="background:${SRC_COLORS[s]}"></i>${s}</span>`).join("")
  + `<span><i style="background:#e0a73c"></i>entity</span><span style="color:var(--muted)">node size = times cited</span>`;

// ---- Evidence drawer (details-on-demand) ----
function selectEvidence(id, chip){
  const e=byId[id]; if(!e) return;
  $("#d-gid").textContent=id;
  const sb=$("#d-src"); sb.textContent=e.source; sb.className="srcbadge bgs-"+e.source;
  $("#d-q").textContent=e.query||"—"; $("#d-ex").textContent=e.excerpt||"—";
  $("#drawer").classList.add("open"); $("#scrim").classList.add("open");
  $("#drawer").setAttribute("aria-hidden","false");
  // cross-highlight: chips, note blocks, graph
  document.querySelectorAll("#note .cite").forEach(b=>{
    const on=b.dataset.cite===id; b.classList.toggle("sel",on);
    const blk=b.closest("p,li,h1,h2,h3"); if(blk) blk.classList.toggle("blk-hot",on);
  });
  document.querySelectorAll(".node").forEach(n=>n.classList.toggle("dim", n.dataset.node!==id && n.dataset.node!=="entity" && n.dataset.node!=="src:"+e.source));
  document.querySelectorAll(".edge").forEach(p=>{const on=p.dataset.gid===id;
    p.classList.toggle("hot",on); p.classList.toggle("dim", p.dataset.gid && !on);});
}
function closeDrawer(){
  $("#drawer").classList.remove("open"); $("#scrim").classList.remove("open");
  $("#drawer").setAttribute("aria-hidden","true");
  document.querySelectorAll(".sel").forEach(n=>n.classList.remove("sel"));
  document.querySelectorAll(".blk-hot").forEach(n=>n.classList.remove("blk-hot"));
  document.querySelectorAll(".dim").forEach(n=>n.classList.remove("dim"));
  document.querySelectorAll(".edge.hot").forEach(n=>n.classList.remove("hot"));
}
$("#d-x").addEventListener("click",closeDrawer);
$("#scrim").addEventListener("click",closeDrawer);
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeDrawer();});

// ---- Trajectory ----
$("#traj").innerHTML = DATA.ledger.map(e=>
  `<div class="step" data-gid="${e.id}"><div class="sg">${e.id}</div>
   <div class="ss" data-src="${e.source}">${e.source}</div>
   <div class="sq">${(e.query||"").replace(/[<&]/g,m=>({"<":"&lt;","&":"&amp;"}[m]))}</div></div>`).join("");
document.querySelectorAll("#traj .step").forEach(s=>
  s.addEventListener("click",()=>selectEvidence(s.dataset.gid,null)));
</script>
</body>
</html>
"""
