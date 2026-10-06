"""Local, offline review page. Decisions are downloaded and imported explicitly."""
from __future__ import annotations

import html
import json
from pathlib import Path
from .common import save
from .rules import COLORS


def write_review(result, out, evidence_href="evidence/index.html"):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    save(out / "result.json", result)
    pending = [i for i in result["issues"] if not i["resolved"]]
    skeleton = [{"id": i["id"], "fingerprint": i["fingerprint"], "action": "", "author": "", "reason": "",
                 "persist": False, "offer": i.get("effective")} for i in pending]
    save(out / "decisions.template.json", skeleton)
    data = json.dumps(pending, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    head = "演示数据，不能用于市场报价" if result["demo"] else "待复核数据，不代表正式报价"
    markup = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>利率复核</title>
<style>body{font:16px system-ui;max-width:1250px;margin:30px auto;padding:0 24px;color:#18324b;background:#f6f8fb}
article{background:white;padding:22px;margin:18px 0;border:1px solid #d6e0e9;border-radius:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px monospace}
textarea{width:98%;min-height:90px}select,input,button{font:inherit;padding:8px;margin:6px}button{background:#154d70;color:white;border:0;cursor:pointer}.pair{display:grid;grid-template-columns:1fr 1fr;gap:18px}.tag{color:#a34200}</style>
<h1>利率复核</h1><p class="tag">__HEAD__</p><p>查看<a href="__EVIDENCE__">原始证据索引</a>、<a href="updates.html">逐项更新记录</a>和<a href="rainbow.preview.html">彩虹预览</a>。每项比较包括利率、条件、有效期和覆盖；不能仅因为数值相同就通过。</p>
<p>全局采集/覆盖问题只能在核实后选择“确认范围”；报价项请选择路线、有效修正值、替换记录或排除。</p>
<label>复核人<input id="author" placeholder="姓名或工号"></label><button id="download">下载已填写的复核决定</button>
<div id="items"></div><script>
const items=__DATA__;
const root=document.getElementById('items');
items.forEach((i,n)=>{
 const box=document.createElement('article');box.dataset.index=n;
 const title=document.createElement('h2');title.textContent=(n+1)+'. '+i.id;box.append(title);
 const why=document.createElement('p');why.textContent=i.reasons.join('；');box.append(why);
 const pair=document.createElement('div');pair.className='pair';
 ['llm','vlm'].forEach(lane=>{const wrap=document.createElement('div');const label=document.createElement('b');label.textContent=lane.toUpperCase();wrap.append(label);const pre=document.createElement('pre');pre.textContent=JSON.stringify(i[lane],null,2);wrap.append(pre);pair.append(wrap)});box.append(pair);
 const select=document.createElement('select');select.className='action';
 const options=i.effective?{'':'暂不处理',effective:'采用当前有效值（含人工修正）',llm:'采用LLM',vlm:'采用VLM',replace:'使用下面替换记录',exclude:'排除本期报价'}:{'':'暂不处理',acknowledge:'已人工核实范围/缺失原因'};
 Object.entries(options).forEach(([v,t])=>{const o=document.createElement('option');o.value=v;o.textContent=t;select.append(o)});box.append(select);
 const note=document.createElement('textarea');note.className='reason';note.placeholder='必填：核实了哪些证据、为什么采用或排除';box.append(note);
 if(i.effective){const details=document.createElement('details');const s=document.createElement('summary');s.textContent='当前有效值 / 替换记录编辑';details.append(s);const edit=document.createElement('textarea');edit.className='offer';edit.style.minHeight='240px';edit.value=JSON.stringify(i.effective,null,2);details.append(edit);box.append(details);const lab=document.createElement('label');const cb=document.createElement('input');cb.type='checkbox';cb.className='persist';lab.append(cb,' 将本次利率修正跨期保留（产品条件身份须不变）');box.append(lab)}
 root.append(box);
});
document.getElementById('download').onclick=()=>{try{const author=document.getElementById('author').value.trim();if(!author)throw Error('请填写复核人');const values=[];root.querySelectorAll('article').forEach(box=>{const action=box.querySelector('.action').value;if(!action)return;const reason=box.querySelector('.reason').value.trim();if(!reason)throw Error('每个已选动作必须填写理由');const i=items[+box.dataset.index];values.push({id:i.id,fingerprint:i.fingerprint,action,author,reason,persist:box.querySelector('.persist')?.checked||false,offer:action==='replace'?JSON.parse(box.querySelector('.offer').value):null})});const url=URL.createObjectURL(new Blob([JSON.stringify(values,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='decisions.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){alert(e.message)}};
</script></html>'''
    (out / "review.html").write_text(markup.replace("__HEAD__", html.escape(head)).replace("__EVIDENCE__", html.escape(evidence_href, quote=True)).replace("__DATA__", data), encoding="utf8")
    parts = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>SGD彩虹预览</title>',
             '<style>body{font:15px system-ui;margin:30px;color:#17324b}section{display:inline-block;vertical-align:top;width:340px;margin:8px;padding:12px}article{background:#ffffff99;margin:10px 0;padding:12px}p{overflow-wrap:anywhere}.warning{background:#fff0dc;padding:15px}</style>',
             '<h1>SGD促销彩虹预览</h1>', f'<p class="warning">{html.escape(head)}；调研日期{result["as_of"]}；待复核{result["pending"]}项。待复核产品组不参与排名。</p>']
    for tenor in COLORS:
        groups = [g for g in result["groups"] if g["display_tenor"] == tenor]
        if not groups:
            continue
        parts.append(f'<section style="background:#{COLORS[tenor]}"><h2>{tenor}</h2>')
        for group in groups:
            parts.append(f'<article><b>{html.escape(group["bank"])} · {html.escape(group["product_name"])}</b><p>排序值 {group["main_pct"]}%</p>')
            for r in group["details"]:
                parts.append('<p>' + html.escape(f'{r["rate_pct"]}% · {r["audience"]} · 实际{r["tenor_value"]}{r["tenor_unit"]} · {r["amount_currency"]} {r["amount_min"]}–{r["amount_max"] or "无上限"} · {r["channel"]} · {r["conditions"]}') + '</p>')
            parts.append('</article>')
        parts.append('</section>')
    parts.append('</html>')
    (out / "rainbow.preview.html").write_text(''.join(parts), encoding="utf8")
    audit = ['<!doctype html><meta charset="utf-8"><title>逐项更新记录</title><style>body{font:16px system-ui;margin:30px}td,th{padding:12px;border:1px solid #ccd5dd}table{border-collapse:collapse}</style>',
             '<h1>逐项更新记录</h1>', '<p>' + html.escape(head) + '</p>',
             '<table><tr><th>银行/产品</th><th>实际期限</th><th>本期</th><th>上期</th><th>检查结论</th></tr>']
    for u in result.get("updates", []):
        values = [u["bank"] + " / " + u["product_name"], u["actual_tenor"],
                  u["main_pct"] + "%" if u["main_pct"] is not None else "-",
                  u["previous_pct"] + "%" if u["previous_pct"] is not None else "-", u["status"]]
        audit.append('<tr>' + ''.join('<td>' + html.escape(v) + '</td>' for v in values) + '</tr>')
    (out / "updates.html").write_text(''.join(audit) + '</table>', encoding="utf8")
