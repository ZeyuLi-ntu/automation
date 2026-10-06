"""Append-only human-approved workbook baselines, separate from raw model evidence."""
from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
import shutil
from .common import load,save,digest
from .schema import IDENTITY
from .table_validation import sha
from .xlsx_read import read_xlsx

def identity(row):
    return digest({k:row[k] for k in IDENTITY if k!='conditions'})[:24]

def column_mode(as_of,baseline_date):
    date.fromisoformat(as_of);date.fromisoformat(baseline_date)
    if as_of<baseline_date:raise ValueError('本期日期早于已确认历史，不能倒序滚动')
    return 0 if as_of==baseline_date else 1

def date_value(value):
    if isinstance(value,(date,datetime)):return value.isoformat()[:10]
    try:return (datetime(1899,12,30)+timedelta(days=float(value))).date().isoformat()
    except (ValueError,TypeError):return str(value).replace('/','-')[:10]

def baseline(project):
    root=Path(project)/'history';pointer=root/'latest-approved.json'
    if not pointer.exists():return None
    record=load(pointer);folder=root/record['id'];manifest=load(folder/'approval.json')
    if sha(folder/'approval.json')!=record['sha256']:raise ValueError('已确认历史登记被修改')
    for kind in ['report','rainbow']:
        if sha(manifest[kind])!=manifest[kind+'_sha256']:raise ValueError('已确认历史副本被修改，请先恢复或重新确认')
    manifest['bank_dates']=load(folder/'approved-plan.json')['bank_dates']
    return manifest

def apply_overrides(offers,record):
    result=deepcopy(offers);applied=[]
    for row in result:
        entry=(record or {}).get('overrides',{}).get(identity(row))
        if entry:
            for field,value in entry['fields'].items():row[field]=value
            applied.append(dict(identity=identity(row),bank=row['bank'],product_id=row['product_id'],fields=entry['fields'],reason=entry['reason']))
    return result,applied

def approve(project,output,acknowledgement):
    """Only called after an explicit user approval; never by the draft workflow."""
    project=Path(project).resolve();out=Path(output).resolve();plan=load(out/'table-validation-plan.json')
    checks=load(out/'table-validation-checks.json')
    if checks['passed']!=checks['total']:raise ValueError('文件检查尚未通过，不能登记为历史底稿')
    previous=baseline(project)
    if previous and plan['as_of']<previous['as_of']:raise ValueError('不能将较旧版本设为当前历史底稿')
    if not acknowledgement.strip():raise ValueError('需要明确的人工检查记录')
    report=read_xlsx(plan['report_output'],merge_anchors_only=True)
    rainbow=read_xlsx(plan['rainbow_output'],merge_anchors_only=True)
    current_date=date_value(report['SGD促销']['C3'])
    if current_date!=plan['as_of']:raise ValueError('工作簿日期与检查记录不一致')
    sheet=plan['input_sheet'];overrides=deepcopy((previous or {}).get('overrides',{}));manual_notes=deepcopy((previous or {}).get('manual_notes',{}))
    for row in plan['details']:
        r=row['input_row'];key=identity(row);fields={}
        for field,col,original in [('rate_pct','H',row['rate_pct']),('product_name','B',row['product_name'])]:
            left,right=report[sheet].get(f'{col}{r}'),rainbow[sheet].get(f'{col}{r}')
            if field=='rate_pct':
                left=format((Decimal(str(left))*100).normalize(),'f');right=format((Decimal(str(right))*100).normalize(),'f')
                if not Decimal('0')<=Decimal(left)<=Decimal('25') or not Decimal('0')<=Decimal(right)<=Decimal('25'):raise ValueError('人工利率超出允许范围')
                original=format(Decimal(original).normalize(),'f')
                # Excel caches binary doubles; 1.3500000000000002 is not a human edit.
                if abs(Decimal(left)-Decimal(original))<=Decimal('0.0000000001'):left=original
                if abs(Decimal(right)-Decimal(original))<=Decimal('0.0000000001'):right=original
                old=overrides.get(key,{}).get('fields',{}).get('rate_pct')
                applied={v['identity'] for v in plan.get('manual_applied',[])}
                if old is not None and key not in applied and str(old)!=original and abs(Decimal(old)-Decimal(original))<=Decimal('0.0000000001'):
                    overrides[key]['fields'].pop('rate_pct')
                    if not overrides[key]['fields']:overrides.pop(key)
            # A one-workbook edit is carried to both next time; two different edits are ambiguous.
            changed={str(v) for v in [left,right] if str(v)!=str(original)}
            if len(changed)>1:raise ValueError('两份工作簿的人工修改冲突：'+row['bank']+'/'+str(r))
            if changed:fields[field]=changed.pop()
        if fields:
            prior=overrides.get(key,{}).get('fields',{});prior.update(fields)
            overrides[key]=dict(fields=prior,reason='已人工确认的明细修改',approved_at=datetime.now(timezone.utc).isoformat())
    display_path=out/'rendered-values.json'
    if display_path.exists():
        rendered=load(display_path)
        for g in plan['groups']:
            edits=[]
            for n in range(len(g['details'])):
                address='B'+str(g['report_row']+n);actual=report['SGD促销'].get(address)
                if actual!=rendered.get(address):edits.append(str(actual or ''))
            if edits:manual_notes[g['id']]='\n'.join(edits)
    folder=project/'history'/('approved-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'));folder.mkdir(parents=True)
    record=dict(id=folder.name,as_of=plan['as_of'],approved_at=datetime.now(timezone.utc).isoformat(),acknowledgement=acknowledgement,
      scope='工作簿已展示的产品及人工修改；不批准暂缓产品或未展示报价',banks=plan['banks'],details=len(plan['details']),
      previous_id=(previous or {}).get('id'),source_output=str(out),input_sheet=sheet,groups=plan['groups'],overrides=overrides,manual_notes=manual_notes,bank_dates=plan['bank_dates'])
    for kind in ['report','rainbow']:
        dest=folder/Path(plan[kind+'_output']).name;shutil.copy2(plan[kind+'_output'],dest)
        record[kind]=str(dest);record[kind+'_sha256']=sha(dest)
    shutil.copy2(out/'table-validation-plan.json',folder/'approved-plan.json')
    save(folder/'approval.json',record)
    save(project/'history/latest-approved.json',dict(id=folder.name,sha256=sha(folder/'approval.json')))
    return record
