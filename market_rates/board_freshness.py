"""Compare bank publication dates, never demand that banks update every day."""
import re
from collections import defaultdict

def scope(offer):return tuple(offer[k] for k in ['bank','currency','product_id'])

def source_date(offer):
    dates=[date for e in offer.get('evidence',[]) if e.get('locator','').endswith('/source-date') for date in re.findall(r'\d{4}-\d{2}-\d{2}',e['quote'])]
    return max(dates) if dates else offer.get('valid_from')

def compare_publication_dates(previous,current,as_of):
    groups=[]
    for rows in [previous,current]:
        by=defaultdict(list)
        for r in rows:by[scope(r)].append(r)
        groups.append(by)
    old,new=groups;events=[];retain=set()
    for key,rows in new.items():
        prior=old.get(key,[])
        a=max([source_date(o) for o in prior if source_date(o)],default=None)
        b=max([source_date(o) for o in rows if source_date(o)],default=None)
        status='first_observation' if not prior else 'date_unstated' if not a or not b else 'newer' if b>a else 'unchanged_date' if b==a else 'date_regressed'
        # An earlier website version may reappear. Preserve the last verified
        # later quote only while it remains available and unexpired, and label it.
        keep=status=='date_regressed' and all(o['availability']=='available' and (not o.get('valid_from') or o['valid_from']<=as_of) and (not o.get('valid_to') or o['valid_to']>=as_of) for o in prior)
        if keep:retain.add(key)
        events.append(dict(bank=key[0],currency=key[1],product_id=key[2],previous_source_date=a,current_source_date=b,status=status,retained_previous=keep))
    return retain,events


def reconcile_run_dates(previous_root,current_root):
    """Apply publication comparisons to a newly assembled batch before writing Excel.

    Only present, verified scopes are compared. Missing or failed new scopes
    never acquire old numbers through this function.
    """
    from pathlib import Path
    import shutil
    from .common import load,save,digest
    from .pipeline import check_evidence,evidence_index
    from .board_wave import validate_wave
    previous_root=Path(previous_root);current_root=Path(current_root)
    if previous_root.resolve()==current_root.resolve():return
    old=load(previous_root/'run.json');new=load(current_root/'run.json')
    retain,events=compare_publication_dates(old['llm']['offers'],new['llm']['offers'],new['as_of'])
    if retain:
        check_evidence(old,previous_root/'evidence')
        for source in old.get('wide_sources',[]):validate_wave(source)
        page_ids={e['page_id'] for lane in ['llm','vlm'] for o in old[lane]['offers'] if scope(o) in retain for e in o.get('evidence',[])}
        present={p['id']:p for p in new['pages']}
        for page in old['pages']:
            if page['id'] not in page_ids:continue
            if page['id'] in present and present[page['id']]!=page:raise ValueError('Conflicting retained source page')
            if page['id'] not in present:new['pages'].append(page)
        for f in (previous_root/'evidence').iterdir():
            if not f.is_file() or f.name=='index.html':continue
            dest=current_root/'evidence'/f.name
            if dest.exists() and dest.read_bytes()!=f.read_bytes():raise ValueError('Conflicting retained evidence')
            if not dest.exists():shutil.copy2(f,dest)
        for lane in ['llm','vlm']:
            new[lane]['offers']=[o for o in new[lane]['offers'] if scope(o) not in retain]+[o for o in old[lane]['offers'] if scope(o) in retain]
        new['wide_sources']=list(dict.fromkeys(new.get('wide_sources',[])+old.get('wide_sources',[])))
    new['source_date_events']=events
    new['publication_comparison_base']=str(previous_root.resolve())
    new['evidence_hash']=digest(new['pages'])
    save(current_root/'run.json',new)
    evidence_index(new['pages'],current_root/'evidence')
