"""Sequential local GPU verification, concise summaries instead of full logs."""
import argparse,subprocess,sys
from pathlib import Path
from market_rates.common import load,save

def main():
    a=argparse.ArgumentParser();a.add_argument('--run',required=True);a.add_argument('--banks',default='DBS,UOB,RHB,SBI,CIMB,HLB');args=a.parse_args();root=Path(args.run)
    results=[]
    subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/start_local_model.ps1'],check=True)
    for bank in args.banks.split(','):
        folder=root/bank
        if not (folder/'run.json').exists():
            results.append(dict(bank=bank,passed=False,error='采集未完成'));continue
        retry=root/(bank+'-layout-retry')
        if (retry/'run.json').exists():
            folder=retry
        with (folder/'verification.log').open('w',encoding='utf8') as log:
            run=subprocess.run([sys.executable,'-X','utf8','-m','scripts.verify_with_repair','--run',str(folder)],stdout=log,stderr=subprocess.STDOUT)
        proof=load(folder/'wave-checks.json') if (folder/'wave-checks.json').exists() else dict(passed=False,checks=[],errors=[dict(error='本地核验未完成')])
        feedback=folder/'自动修复结果.txt'
        if feedback.exists():print(feedback.read_text(encoding='utf-8-sig'),flush=True)
        result=dict(bank=bank,path=str(folder.resolve()),passed=proof['passed'] and run.returncode==0,checks=len(proof['checks']),failed=len(proof['errors']),cache_hits=sum(bool(c.get('cache_hit')) for c in proof['checks']))
        results.append(result);save(root/'verification-summary.json',results);print(result,flush=True)
    save(root/'verification-summary.json',results)
    if not all(r['passed'] for r in results):raise ValueError('部分原图转录需修复，查看各银行本地日志')

if __name__=='__main__':main()
