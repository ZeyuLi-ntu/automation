"""Assemble verified FX promotions with current board dependencies and deferred source rows."""
import argparse,shutil,hashlib,re
from pathlib import Path
from market_rates.common import load,save,digest
from market_rates.fx_promo import normalize_fx,numeric
from market_rates.schema import normalize
from market_rates.board_wave import validate_wave
from market_rates.pipeline import check_evidence,evidence_index
from market_rates.rules import active

def prepare(waves,out,board):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);ev=out/'evidence';ev.mkdir();br=load(Path(board)/'run.json');check_evidence(br,Path(board)/'evidence')
    for src in br['wide_sources']:validate_wave(src)
    run=dict(id=out.name,as_of=br['as_of'],pages=[],bank_dates={},fx_sources=[],board_dependency=str(Path(board).resolve()),board_dependency_sha=hashlib.sha256((Path(board)/'run.json').read_bytes()).hexdigest(),errors=[],demo=False,manual_catalog=[],deferred=[])
    def copy_pages(root,pages):
        names={p['id'] for p in run['pages']};run['pages'] += [p for p in pages if p['id'] not in names]
        for f in (Path(root)/'evidence').iterdir():
            if f.is_file() and f.name!='index.html':
                dest=ev/f.name
                if dest.exists() and dest.read_bytes()!=f.read_bytes():raise ValueError('Evidence collision')
                shutil.copy2(f,dest)
    copy_pages(board,br['pages']);offers=[]
    for src in waves:
        r=validate_wave(src);copy_pages(src,r['pages']);run['bank_dates'].update(r['bank_dates']);run['fx_sources'].append(str(Path(src).resolve()))
        for s in r['sections']:offers+=normalize_fx(s,br['llm']['offers'])
    if {r['bank'] for r in offers}!={'BEA','BOC','CIMB','CITI','DBS','HSBC','ICBC','RHB','SBI','SCB'}:
        raise ValueError('Missing FX bank: include the locally verified BOC ordinary notice in --waves')
    # BOC uses the same verified-source path as every other bank. Its actual
    # notice dates come from evidence; insertion as an expired reference is an
    # explicit workbook policy, not a mutation of the source validity fields.
    # Existing user instruction: Citi investment bundles at 2M remain details only.
    # Excluded 2M investment bundles are not carried from a dated discovery
    # folder into a fresh run. Prior raw evidence remains in its original run.
    if len({digest(r) for r in offers})!=len(offers):raise ValueError('Duplicate FX offers')
    for lane in ['llm','vlm']:run[lane]=dict(offers=offers,inventory=[],coverage_complete=True,unreadable=[])
    for r in offers:
        d={k:r[k] for k in ['bank','product_id','currency','rate_type','amount_currency']}
        if d not in run['manual_catalog']:run['manual_catalog'].append(d)
    run['evidence_hash']=digest(run['pages']);save(out/'run.json',run);evidence_index(run['pages'],ev);check_evidence(run,ev);print('Verified FX records',len(offers),'deferred',len(run['deferred']))
    return run
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--waves',nargs='+',required=True);a.add_argument('--out',required=True);a.add_argument('--board',default='runs/remaining-board-20260928-combined-v2');x=a.parse_args();prepare(x.waves,x.out,x.board)
