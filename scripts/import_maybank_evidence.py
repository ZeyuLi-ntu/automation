"""Import explicit text/image evidence independently; never claim live capture succeeded."""
import argparse,hashlib,shutil
from datetime import datetime,timezone,timedelta
from pathlib import Path
from market_rates.common import load,save,digest
from market_rates.remaining_banks import configuration
from market_rates.model_adapter import extract
from market_rates.pipeline import evaluate,evidence_index
from market_rates.store import Store
from market_rates.consolidate import qualify
from market_rates.table_validation import sha

def main():
    p=argparse.ArgumentParser();p.add_argument('--image',required=True);p.add_argument('--text',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    root=Path(a.out)
    if root.exists():raise ValueError('Use a new evidence folder')
    cfg=configuration('Maybank');root.mkdir(parents=True);e=root/'evidence';e.mkdir()
    pid='maybank-sgd-bundle';image='maybank-user-screenshot.png';text=Path(a.text).read_text(encoding='utf8')
    shutil.copy2(a.image,e/image);(e/'maybank-bundle.txt').write_text(text,encoding='utf8')
    page=dict(id='maybank-bundle',bank='Maybank',url=cfg['official_section_url'],product_ids=[pid],ok=True,complete=True,
        captured_at=datetime.now(timezone.utc).isoformat(),capture_scope='configured_units',text=text,images=[image],
        sha256=hashlib.sha256(text.encode()).hexdigest(),image_hashes={image:sha(e/image)},
        evidence_origin=dict(text='Official webpage text retrieved separately with web tool on 2026-09-27; selected section i only',
            image='User-provided screenshot; original capture timestamp not known',live_crawler_verified=False),
        units=[dict(kind='rates',product_ids=[pid],image=image,text=text)])
    cfg['pilot']['scope']='Maybank selected bundle section, official text + user screenshot; full terms pending review'
    cfg['sources']=[]
    run=dict(id=root.name,as_of=datetime.now(timezone(timedelta(hours=8))).date().isoformat(),demo=False,pages=[page],
      metadata=[],errors=['TERMS_REVIEW: User screenshot does not contain complete campaign terms or dates; not proof of live automatic collection'],
      evidence_hash=digest([page]),pilot=cfg['pilot'])
    save(root/'config.snapshot.json',cfg);save(root/'run.json',run);evidence_index([page],e)
    for lane in ['llm','vlm']:
        result,meta=extract(lane,[page],e,cfg,run['as_of']);run[lane]=result;run['metadata'].append(dict(meta,bank='Maybank'))
        save(root/f'model-Maybank-{lane}.json',dict(result=result,metadata=meta));save(root/'run.json',run)
        print(lane,len(result['offers']),result['unreadable'],flush=True)
    store=Store(root/'pilot.sqlite3')
    try:evaluate(root,store)
    finally:store.close()
    gate=qualify(root,allow_agreement=True)
    save(root/'benchmark.json',dict(kind='dual_agreement_imported_evidence',lanes=gate['lanes'],evidence_hash=run['evidence_hash'],run_sha256=sha(root/'run.json')))
    print('Two routes agreed. Imported evidence only; live automatic retrieval still unverified.',flush=True)

if __name__=='__main__':main()
