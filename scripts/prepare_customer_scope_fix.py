"""Re-use verified local evidence under the user's narrowed customer scope."""
import shutil
from pathlib import Path
from market_rates.common import load,save
from market_rates.workbook_policy import quote_in_scope
from market_rates.fx_promo import normalize_fx
from market_rates.board_wave import validate_wave
from market_rates.pipeline import check_evidence

def prepare():
    for src,dest in [('runs/remaining-board-20260928-combined-v2','runs/board-personal-scope-20260928-a'),('runs/fx-promo-boc-repaired-20260928-a','runs/fx-personal-scope-20260928-a')]:
        source,out=Path(src),Path(dest);r=load(source/'run.json');check_evidence(r,source/'evidence')
        for wave in r.get('wide_sources',r.get('fx_sources',[])):validate_wave(wave)
        shutil.copytree(source,out)
        replacement=None
        if r.get('fx_sources'):
            proof=validate_wave('runs/fx-promo-20260928-i/ICBC')
            replacement=[q for s in proof['sections'] for q in normalize_fx(s)]
            assert len(replacement)==20
        for lane in ['llm','vlm']:
            r[lane]['offers']=[q for q in r[lane]['offers'] if quote_in_scope(q) and not (replacement is not None and q['bank']=='ICBC')]+(replacement or [])
        r['manual_catalog']=[c for c in r['manual_catalog'] if any(q['product_id']==c['product_id'] and q['currency']==c['currency'] for q in r['llm']['offers'])]
        r['id']=out.name;r['scope_revision']='2026-09-28: HSBC Personal only for board/USD promo; ICBC promo two published amount bands, channels in notes.'
        save(out/'run.json',r);check_evidence(r,out/'evidence');print(out,len(r['llm']['offers']))

if __name__=='__main__':prepare()
