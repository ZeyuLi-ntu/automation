import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const {Workbook,SpreadsheetFile}=await import(pathToFileURL(path.join(process.env.MARKET_NODE_MODULES,'@oai/artifact-tool/dist/artifact_tool.mjs')).href);
const out=path.resolve(process.argv[2]),p=JSON.parse(await fs.readFile(path.join(out,'table-validation-plan.json'),'utf8'));
const run=JSON.parse(await fs.readFile(path.join(p.source_run,'run.json'),'utf8')),pages=Object.fromEntries(run.pages.map(x=>[x.id,x]));
const wb=Workbook.create(),s=wb.worksheets.add(p.input_sheet),n=p.details.length+3;
s.getRange('A1:T1').merge();s.getRange('A1').values=[[`${p.as_of} 外币促销明细`]];
s.getRange('A2:T2').merge();s.getRange('A2').values=[['I列为本期展示报价，J列为原始值；DBS的I列=S列挂牌+T列加点。中行按用户确认展示最新公告并保留公告期限，截止后数值为参考。2M投资搭配及模板外项目留明细。CNH按CNY显示。']];
s.getRange('A3:T3').values=[['银行','原币种','展示币种','产品','实际期限','客群 / 渠道','金额下限','金额上限','本期利率','原始利率','金额币种','生效日','截止日','插表状态','条件','来源网址','采集日','核验方式','DBS当期挂牌','DBS促销加点']];
s.getRange(`A4:T${n}`).values=p.details.map(r=>[r.bank,r.currency,r.display_currency,r.product_name,`${r.tenor_value}${r.tenor_unit}`,r.audience+' / '+r.channel,r.amount_min===null?'未列明':Number(r.amount_min),r.amount_max===null?'未列明':Number(r.amount_max),r.insertable?Number(r.rate_pct)/100:'-',Number(r.rate_pct)/100,r.amount_currency+(r.amount_is_equivalent?'等值':''),r.valid_from||'未列明',r.valid_to||'未列截止日',r.insertable?'已核验，可插表':r.hold_reason,r.conditions,[...new Set(r.evidence.map(e=>pages[e.page_id]?.url).filter(Boolean))].join('\n'),p.as_of,r.verification,null,null]);
for(const r of p.details.filter(r=>r.bank==='DBS'&&r.insertable)){
 const m=r.conditions.match(/当期挂牌([\d.]+)%＋加点([\d.]+)%/);if(!m)throw Error('Missing DBS calculation');
 s.getRange(`S${r.input_row}:T${r.input_row}`).values=[[Number(m[1])/100,Number(m[2])/100]];s.getRange(`I${r.input_row}`).formulas=[[`=SUM(S${r.input_row}:T${r.input_row})`]];
}
for(const r of p.details.filter(r=>r.reference_quote)){
 s.getRange(`N${r.input_row}:O${r.input_row}`).values=[['最新公开参考报价；公告已截止',`${r.conditions}；公告期 ${r.valid_from} 至 ${r.valid_to}；按用户确认插表`]];
}
s.getRange(`A1:T${n}`).format={font:{name:'Microsoft YaHei',size:10},wrapText:true,verticalAlignment:'center',rowHeight:64};
s.getRange('A1:T1').format={fill:'#173D54',font:{color:'#FFFFFF',bold:true,size:14},rowHeight:30};s.getRange('A2:T2').format.rowHeight=42;
s.getRange('A3:T3').format={fill:'#DDEBF7',font:{bold:true},rowHeight:32};
for(const [c,w] of Object.entries({A:10,B:10,C:10,D:24,E:10,F:28,G:16,H:16,I:14,J:14,K:14,L:14,M:14,N:40,O:65,P:65,Q:14,R:30,S:16,T:16}))s.getRange(`${c}1:${c}${n}`).format.columnWidth=w;
s.getRange(`G4:H${n}`).setNumberFormat('#,##0.##');s.getRange(`I4:J${n}`).setNumberFormat('0.0000%');s.getRange(`S4:T${n}`).setNumberFormat('0.0000%');s.freezePanes.freezeRows(3);s.showGridLines=false;
const serial=v=>Date.parse(v+'T00:00:00Z')/86400000+25569;
for(const r of p.details){for(const [c,v] of [['L',r.valid_from],['M',r.valid_to],['Q',p.as_of]]){if(v){s.getRange(`${c}${r.input_row}`).values=[[serial(v)]];s.getRange(`${c}${r.input_row}`).setNumberFormat('yyyy-mm-dd');}}}
wb.recalculate();console.log((await wb.inspect({kind:'table',range:`${p.input_sheet}!A3:J7`,include:'values,formulas',tableMaxRows:5,tableMaxCols:10})).ndjson);
await(await SpreadsheetFile.exportXlsx(wb)).save(path.join(out,'fx-inputs.xlsx'));
