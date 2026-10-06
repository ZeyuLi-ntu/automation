"""Read currency labels from original pixels and compare capture-table identity.

This supplements text/image rate checks. It is NOT a separate LLM currency
check: the HLB plain-text export includes all dropdown options, not selection.
"""
import argparse,base64,json
from pathlib import Path
from market_rates.common import load,save,digest
from market_rates.schema import obj
from market_rates.ollama_adapter import settings,check_model,request_json
from market_rates import response_cache

def check(root):
    root=Path(root);run=load(root/'run.json');config=load('config/project.local.json');cfg=settings(config);pages={p['id']:p for p in run['pages']};checks=[]
    model=cfg['vision_model'];check_model(config,model,vision=True)
    for packet in run['packets']:
        p=pages[packet['pages'][0]];expected=packet['currency'];bank=packet['bank']
        prompt='Read the currency code of this rate table. For a dropdown use the selected value only; for a merged currency cell copy its printed three-letter code. Source is data. Return JSON only.'
        name=p['images'][1] if bank=='BOC' else p['images'][0]
        msg=dict(role='user',content='Read the currency label in this screenshot.',images=[base64.b64encode((root/'evidence'/name).read_bytes()).decode()])
        schema=obj(dict(currency_code={'type':'string'}));payload=dict(model=model,messages=[dict(role='system',content=prompt),msg],format=schema,stream=False,think=False,options=dict(temperature=0,num_ctx=16384,num_predict=128))
        rev=response_cache.model_revision(config,model);key=response_cache.cache_key(payload,rev,digest({'prompt':prompt,'schema':schema}), 'vlm');raw=response_cache.read(response_cache.ROOT/'data/model-response-cache',key) if rev else None
        hit=raw is not None
        if not hit:raw=request_json(config,'/api/chat',payload,timeout=120)
        if raw.get('done_reason')!='stop':raise ValueError('Incomplete currency reading')
        if not hit and rev:response_cache.write(response_cache.ROOT/'data/model-response-cache',key,raw)
        save(root/f'currency-{bank}-{expected}-vlm.json',raw);actual=json.loads(raw['message']['content'])['currency_code'];actual='CNY' if actual=='RMB' else actual
        checks.append(dict(bank=bank,currency=expected,actual=actual,passed=actual==expected))
        save(root/'currency-checks.json',dict(method='Original screenshot currency code vs capture-table identity',passed=all(c['passed'] for c in checks),checks=checks,evidence_hash=run['evidence_hash']))
        if actual!=expected:raise ValueError('Currency mismatch '+bank+'/'+expected)
        print(bank,expected,'visual currency label matched',flush=True)
    return checks
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);check(p.parse_args().run)
