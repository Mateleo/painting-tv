"""Write a self-contained, searchable report for every artwork in the audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TEMPLATE = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Painting TV · Collection quality review</title><style>
*{box-sizing:border-box}body{margin:0;background:#151916;color:#eee7d9;font:14px/1.5 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:28px}h1{font:38px/1.1 Georgia,serif;margin:10px 0 18px}p{color:#b9beb6;max-width:78ch}.eyebrow{letter-spacing:.14em;font-size:11px;color:#c9d5be}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:24px 0}.card{border:1px solid #39443a;border-radius:10px;padding:16px;background:#202720}.card strong{font:32px Georgia,serif;display:block}.card span{color:#c0c6bb;font-size:12px}.bar{display:flex;height:18px;background:#30362f;border-radius:4px;overflow:hidden;margin:7px 0}.bar span{min-width:0}.legend{display:flex;gap:13px;flex-wrap:wrap;font-size:11px;color:#b9beb6;margin:12px 0}.dot{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px}.controls{display:flex;gap:10px;margin:24px 0 12px;flex-wrap:wrap}input,select,button{background:#222b23;color:#eee7d9;border:1px solid #52604f;border-radius:6px;padding:10px;font:inherit}input{flex:1;min-width:190px}button{cursor:pointer}input:focus,select:focus,button:focus{outline:2px solid #d2dcb4;outline-offset:2px}table{width:100%;border-collapse:collapse;font-size:12px}th{text-align:left;color:#c1c6b9;padding:11px 7px;border-bottom:1px solid #69715e;white-space:nowrap}td{padding:13px 7px;border-bottom:1px solid #323d32;vertical-align:top}td:first-child{max-width:330px;width:36%}td strong{display:block;font-size:13px;font-weight:500}small{display:block;color:#a4ada0}a{color:#d1dcb7}a:hover{color:white}.before{color:#9fa99b;font-size:10px;display:block}.tag{color:#d6e8be}.muted{color:#afb6a8}.pager{display:flex;justify-content:space-between;align-items:center;margin:17px 0;gap:10px}.note{font-size:12px;color:#a9b2a4;border-top:1px solid #3b463a;padding-top:18px;margin-top:24px}.table-wrap{overflow:auto}#stats{font-size:12px;color:#a9b2a4}.downloads{display:flex;gap:18px;font-size:12px;margin-top:18px}@media(max-width:560px){main{padding:18px}h1{font-size:30px}.cards{gap:7px}.card{padding:11px}.card strong{font-size:26px}.card span{font-size:10px}th,td{padding:9px 5px}.source-column{display:none}td:first-child{min-width:180px}}
</style><main><div class="eyebrow">PAINTING TV · COMPLETE COLLECTION AUDIT</div><h1>Better sources.<br>Every painting accounted for.</h1>
<p>All original deck files were decoded and measured. Larger reproductions were checked against their references; four missing images were restored from cited title, artist and date evidence.</p>
<div class="cards"><div class="card"><strong id="checked"></strong><span>records checked</span></div><div class="card"><strong id="improved"></strong><span>larger sources / restored</span></div><div class="card"><strong id="native"></strong><span>native 4K with screen fill</span></div></div>
<div class="muted">Original deck · enlargement required for every available image</div><div class="bar" id="before"></div>
<div class="muted">Updated collection · required enlargement in fill-screen mode</div><div class="bar" id="after"></div><div class="legend" id="legend"></div>
<p id="description"></p><div class="controls"><input id="search" aria-label="Find a painting or artist" placeholder="Find a painting or artist…"><select id="filter" aria-label="Filter by quality"><option value="all">All paintings</option><option value="improved">Larger / restored sources</option><option value="fill">Native 4K · screen fill</option><option value="fit">Native 4K · whole painting</option><option value="small">Still needs enlargement</option><option value="missing">Missing / unreadable</option></select></div><div id="stats" aria-live="polite"></div>
<div class="table-wrap"><table><thead><tr><th>Painting / artist</th><th>Source pixels</th><th>4K fill</th><th class="source-column">Source / format</th></tr></thead><tbody id="rows"></tbody></table></div><div class="pager"><button id="prev">← Previous</button><span id="page"></span><button id="next">Next →</button></div>
<div class="note">This is a technical audit, not a claim that every replacement received a human visual review. Automatic image comparisons and pixel dimensions cannot certify genuine scan detail, color accuracy, or every alternate version. Higher resolution masters are kept unchanged. Efficient JPEGs stay unchanged; high-quality WebP is used where it meets the compression-error guard and saves space. No source is enlarged or AI reconstructed. <a href="https://developer.android.com/media/platform/supported-formats#image-formats" target="_blank" rel="noopener">Android image-format support</a>.</div>
<div class="downloads"><a href="https://github.com/Mateleo/painting-tv/releases/tag/v0.2.0" target="_blank" rel="noopener">APK and updated collection</a><a href="https://github.com/Mateleo/painting-tv/blob/main/catalog/quality-upgrade-report.csv" target="_blank" rel="noopener">Full CSV audit</a></div>
</main><script>const DATA=__DATA__;const s=DATA.summary,r=DATA.records;const n=x=>Number(x).toLocaleString();document.querySelector('#checked').textContent=n(s.recordsChecked);document.querySelector('#improved').textContent=n(s.improved);document.querySelector('#native').textContent=n(s.native4kFill);
document.querySelector('#description').textContent=`${n(s.native4kFit)} images can show the whole painting at native 4K resolution with margins. ${n(s.stillNeedsEnlargementFor4kFill)} still need enlargement to fill a 4K screen. ${n(s.missing)} missing, ${n(s.corrupt)} corrupt in the exported collection.`;
const cats=[['Native 4K', '#b9d39e',x=>x.status==='ok'&&x.native4kFill],['Up to 1.5×', '#83996d',x=>x.status==='ok'&&!x.native4kFill&&x.cropUpscale<=1.5],['1.5–2×', '#b29c6e',x=>x.cropUpscale>1.5&&x.cropUpscale<=2],['Over 2×', '#82645b',x=>x.cropUpscale>2]];const good=r.filter(x=>x.status==='ok');cats.forEach(([label,color,test])=>{const count=good.filter(test).length;const bar=document.createElement('span');bar.style.width=(100*count/good.length)+'%';bar.style.background=color;bar.title=label+': '+n(count);document.querySelector('#after').append(bar);const key=document.createElement('span');const dot=document.createElement('i');dot.className='dot';dot.style.background=color;key.append(dot,document.createTextNode(label+' · '+n(count)));document.querySelector('#legend').append(key)});const old=document.createElement('span');old.style.width='100%';old.style.background='#82645b';document.querySelector('#before').append(old);
let page=0,filtered=r;const pageSize=40;function cell(text,cls){const e=document.createElement('td');e.textContent=text;if(cls)e.className=cls;return e}function render(){const body=document.querySelector('#rows');body.replaceChildren();const total=Math.max(1,Math.ceil(filtered.length/pageSize));page=Math.min(page,total-1);filtered.slice(page*pageSize,(page+1)*pageSize).forEach(x=>{const tr=document.createElement('tr');const title=cell('');const strong=document.createElement('strong');strong.textContent=x.title;const artist=document.createElement('small');artist.textContent=x.artist;title.append(strong,artist);if(x.sourceUrl&&x.sourceUrl.startsWith('https://')){const a=document.createElement('a');a.href=x.sourceUrl;a.textContent='Source ↗';a.target='_blank';a.rel='noopener';title.append(a)}const size=cell(x.width?`${n(x.width)} × ${n(x.height)}`:'Unavailable');const before=document.createElement('small');before.className='before';before.textContent=x.beforeWidth?`was ${x.beforeWidth} × ${x.beforeHeight}`:'was missing';size.append(before);const quality=cell(x.status!=='ok'?x.status:x.native4kFill?'Native':Number(x.cropUpscale).toFixed(2)+'× enlargement',x.native4kFill?'tag':'muted');const source=cell(x.selectedSource,'source-column');const format=document.createElement('small');format.textContent=x.compression.startsWith('webp')?'WebP':x.compression?'Original retained':'';source.append(format);tr.append(title,size,quality,source);body.append(tr)});document.querySelector('#stats').textContent=n(filtered.length)+' matching records';document.querySelector('#page').textContent=(page+1)+' / '+total;document.querySelector('#prev').disabled=page===0;document.querySelector('#next').disabled=page>=total-1}function update(){const query=document.querySelector('#search').value.toLocaleLowerCase();const f=document.querySelector('#filter').value;filtered=r.filter(x=>(x.title+' '+x.artist).toLocaleLowerCase().includes(query)&&(f==='all'||f==='improved'&&x.improved||f==='fill'&&x.native4kFill||f==='fit'&&x.native4kFit||f==='small'&&x.status==='ok'&&!x.native4kFill||f==='missing'&&x.status!=='ok'));page=0;render()}document.querySelector('#search').addEventListener('input',update);document.querySelector('#filter').addEventListener('change',update);document.querySelector('#prev').onclick=()=>{page--;render()};document.querySelector('#next').onclick=()=>{page++;render()};render();console.log('Quality review loaded',r.length,'records');</script></html>'''


def render_report(report: Path, output: Path) -> str:
    value = json.loads(report.read_text(encoding="utf-8"))
    data = json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    result = TEMPLATE.replace("__DATA__", data)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result, encoding="utf-8")
    return result


def render_summary(report: Path, output: Path) -> str:
    """Small, theme-aware companion for embedding in the review conversation."""
    value = json.loads(report.read_text(encoding="utf-8"))
    summary = value["summary"]
    compression = value.get("compression", {})
    groups = [
        ("Native 4K fill", sum(r["status"] == "ok" and r["native4kFill"] for r in value["records"]), "#91b889"),
        ("Up to 2× enlargement", sum(r["status"] == "ok" and not r["native4kFill"] and (r["cropUpscale"] or 0) <= 2 for r in value["records"]), "#b9a577"),
        ("Over 2× enlargement", sum(r["status"] == "ok" and (r["cropUpscale"] or 0) > 2 for r in value["records"]), "#a67d73"),
    ]
    total = summary["recordsChecked"]
    bars = "".join(f'<span title="{label}: {count:,}" style="width:{100 * count / total:.3f}%;background:{color}"></span>' for label, count, color in groups)
    keys = "".join(f'<span><i style="background:{color}"></i>{label} · {count:,}</span>' for label, count, color in groups)
    saved = compression.get("sourceBytes", 0) - compression.get("outputBytes", 0)
    result = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
    *{{box-sizing:border-box}}html,body{{background:transparent;margin:0;color:var(--foreground,#eee);font:14px/1.55 var(--font-sans,system-ui)}}
    .cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.card{{padding:16px;background:var(--card,#252925);border-radius:var(--radius,10px)}}strong{{display:block;font-size:30px;font-weight:600}}.label,p,.legend{{color:var(--muted-foreground,#aaa)}}.label{{font-size:12px}}.bar{{display:flex;height:22px;border-radius:5px;overflow:hidden;margin:10px 0}}.legend{{display:flex;flex-wrap:wrap;gap:12px;font-size:12px}}i{{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px}}a{{color:var(--foreground,#eee)}}p{{margin:18px 0 0}}@media(max-width:450px){{.cards{{gap:7px}}.card{{padding:16px}}strong{{font-size:25px}}}}
    </style><div class="cards"><div class="card"><strong>{total:,}</strong><span class="label">images checked</span></div><div class="card"><strong>{summary['improved']:,}</strong><span class="label">larger / restored</span></div><div class="card"><strong>{summary['native4kFit']:,}</strong><span class="label">4K with whole painting</span></div></div>
    <p>Updated collection · enlargement needed to fill a 4K screen</p><div class="bar">{bars}</div><div class="legend">{keys}</div>
    <p>{summary['missing']} missing · {summary['corrupt']} corrupt. Four absent deck images restored. Compression saves {saved / 1_000_000:.0f} MB; native dimensions are preserved and efficient JPEGs stay unchanged.</p>
    <p>Every file was technically checked; source matching used automated comparisons and a separate model visual review. Larger pixel dimensions alone cannot certify scan detail. The collection still includes small reproductions.</p>
    <p><a href="https://github.com/Mateleo/painting-tv/blob/main/catalog/quality-upgrade-report.csv" target="_blank" rel="noopener">Review every painting in the CSV audit ↗</a></p></html>'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result, encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "catalog/quality-upgrade-report.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/quality-review.html")
    parser.add_argument("--summary", action="store_true", help="Write a compact inline summary instead of the searchable review")
    args = parser.parse_args()
    (render_summary if args.summary else render_report)(args.report, args.output)
    print(args.output)


if __name__ == "__main__":
    main()
