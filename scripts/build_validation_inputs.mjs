import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
// Use the installed spreadsheet runtime, supplied explicitly by the launcher.
const {Workbook,SpreadsheetFile}=await import(pathToFileURL(path.join(process.env.MARKET_NODE_MODULES,'@oai/artifact-tool/dist/artifact_tool.mjs')).href);
const out=path.resolve(process.argv[2]);
const p=JSON.parse(await fs.readFile(path.join(out,'table-validation-plan.json'),'utf8'));
const wb=Workbook.create(),s=wb.worksheets.add(p.input_sheet),n=p.details.length+3;
const dates=Object.entries(p.bank_dates).map(([b,d])=>`${b} ${d}`).join('；');
s.getRange('A1:M1').merge();s.getRange('A1').values=[[`${p.collection_label} · SGD促销验证明细（待复核）`]];
s.getRange('A2:M2').merge();s.getRange('A2').values=[[`汇编 ${p.as_of}；证据日期：${dates}。未采集银行保留历史样本，不代表全市场最新排名。`]];
s.getRange('A3:M3').values=[['银行','产品','实际期限','客群','渠道','起存金额(SGD)','单笔上限(SGD)','年利率','新资金要求','开始日','结束日','验证状态','证据日期']];
const chan={online:'在线',branch_or_online:'分行 / 在线',staff_instruction:'分行 / 客户经理指令',branch_or_mobile:'分行 / RHB Mobile',branch_or_instruction:'分行 / 指令表单',hlf_digital:'HLF Digital',unknown:'待核实',branch:'分行','online_banking|sc_mobile':'网银 / SC Mobile'};
const aud={personal:'Personal',preferred:'Preferred',premier:'Premier',private:'Private',premier_elite:'Premier Elite',premier_wealth:'Premier（财富/FX资格）',premier_standard:'Premier（无财富持仓）',all:'所有客群',unknown:'待核实'};
s.getRange(`A4:M${n}`).values=p.details.map(r=>[r.bank,r.product_name,`${r.tenor_value}${r.tenor_unit}`,aud[r.audience]??r.audience,chan[r.channel]??r.channel,r.amount_min===null?'待核实':Number(r.amount_min),r.amount_max===null?'未列明':Number(r.amount_max),Number(r.rate_pct)/100,{yes:'需要',no:'不限新资金',unknown:'见条款待核'}[r.fresh_funds],r.valid_from?new Date(r.valid_from+'T00:00:00Z'):'未列明/待核',r.valid_to?new Date(r.valid_to+'T00:00:00Z'):'未列明',r.manual_reviewed?'已人工处理；见修正记录':r.human_reviewed?'已人工确认；沿用采集结果':(r.rate_basis==='unknown'?'计息口径待人工核实':'核心一致；条款待复核'),p.bank_dates[r.bank]]);
s.getRange('O3:Q3').values=[['产品','官方来源','条件原文/待复核']];
for (const r of p.details.filter(r=>r.reference_quote)) {
 s.getRange(`L${r.input_row}`).values=[['最新公开参考；原公告已截止，保留原期限']];
}
let sr=4;
for(const g of p.groups.filter((g,i,a)=>a.findIndex(x=>x.product_id===g.product_id)===i)){
 s.getRange(`O${sr}:Q${sr}`).values=[[g.product_name,(p.bank_urls[g.bank]??[]).join('\n'),[...new Set(p.details.filter(d=>d.product_id===g.product_id).map(d=>d.conditions))].join('\n')]];sr++;
}
s.getRange(`A1:Q${n}`).format.font={name:'Arial',size:11};
s.getRange('A1:M1').format.font={bold:true,size:15};
s.getRange('A3:M3').format={fill:'#173D54',font:{color:'#FFFFFF',bold:true},wrapText:true};
s.getRange(`A3:M${n}`).format.borders={preset:'all',style:'thin',color:'#CBD5DB'};
s.getRange(`A1:Q${n}`).format.verticalAlignment='center';s.getRange(`A1:Q${n}`).format.wrapText=true;
s.getRange(`A1:Q${n}`).format.rowHeight=42;s.getRange('A2:M2').format.rowHeight=60;
for(const [c,w] of Object.entries({A:8,B:42,C:12,D:15,E:24,F:17,G:17,H:12,I:17,J:15,K:15,L:26,M:15,N:3,O:34,P:80,Q:70}))s.getRange(`${c}1:${c}${n}`).format.columnWidth=w;
s.getRange(`F4:G${n}`).setNumberFormat('#,##0');s.getRange(`H4:H${n}`).setNumberFormat('0.00%');s.getRange(`J4:K${n}`).setNumberFormat('yyyy-mm-dd');
for(const r of p.details){
 if(r.amount_min!==null)s.getRange(`F${r.input_row}`).setNumberFormat(`"${r.min_inclusive?'≥':'>'}"#,##0${Number(r.amount_min)%1?'.00':''}`);
 if(r.amount_max!==null)s.getRange(`G${r.input_row}`).setNumberFormat(`"${r.max_inclusive?'≤':'<'}"#,##0${Number(r.amount_max)%1?'.00':''}`);
}
s.getRange(`L4:L${n}`).format.fill='#FFF2CC';s.showGridLines=false;wb.recalculate();
await fs.writeFile(path.join(out,'input-inspect.jsonl'),(await wb.inspect({kind:'table',range:`${p.input_sheet}!A3:M10`,include:'values,formulas',maxChars:1800})).ndjson);
const picture=await wb.render({sheetName:p.input_sheet,range:'A1:M10',scale:1,format:'png'});
await fs.writeFile(path.join(out,'inputs.png'),new Uint8Array(await picture.arrayBuffer()));
await(await SpreadsheetFile.exportXlsx(wb)).save(path.join(out,'validation-inputs.xlsx'));
console.log('输入明细已生成：',p.details.length);
