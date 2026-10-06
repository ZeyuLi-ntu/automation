"""Exact per-lane response reuse after fresh capture, with bounded age."""
from datetime import datetime,timezone
from pathlib import Path
from .common import load,save,digest

ROOT=Path(__file__).resolve().parents[1]

def model_revision(config,model):
    from .ollama_adapter import request_json
    models=request_json(config,'/api/tags').get('models',[])
    row=next((r for r in models if r.get('name',r.get('model'))==model),None)
    if not row or not row.get('digest'):return None
    return dict(model_digest=row['digest'],ollama_version=request_json(config,'/api/version').get('version'))

def cache_key(payload,revision,extractor_hash,lane):
    return digest(dict(payload=payload,model=revision,extractor=extractor_hash,lane=lane))

def read(root,key,max_age_days=28,now=None):
    path=Path(root)/(key+'.json')
    if not path.exists():return None
    now=now or datetime.now(timezone.utc)
    try:
        record=load(path);age=(now-datetime.fromisoformat(record['created_at'])).total_seconds()
        if record['key']!=key or not 0<=age<max_age_days*86400:return None
        if record['response_hash']!=digest(record['response']):return None
        response=record['response']
        if response.get('done') is not True or response.get('done_reason')!='stop':return None
        return response
    except (ValueError,KeyError,TypeError):return None

def write(root,key,response):
    save(Path(root)/(key+'.json'),dict(key=key,created_at=datetime.now(timezone.utc).isoformat(),response=response,response_hash=digest(response)))
