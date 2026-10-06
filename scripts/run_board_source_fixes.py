"""Local, resumable HLF/ICBC/HSBC refresh; verified data goes directly to Excel."""
import argparse,os,subprocess,sys
from datetime import datetime
from pathlib import Path
from market_rates.common import load,save
from market_rates.board_wave import replace_verified_sections

ROOT=Path(__file__).resolve().parents[1]

def main():
    a=argparse.ArgumentParser();a.add_argument('--resume');a.add_argument('--no-open',action='store_true');args=a.parse_args();os.chdir(ROOT)
    folder=Path(args.resume).resolve() if args.resume else ROOT/'runs'/('board-source-fixes-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    manifest=folder/'workflow.json'
    if args.resume:state=load(manifest)
    else:
        folder.mkdir();latest=load(ROOT/'outputs/latest-board-pilot.json')
        state=dict(status='running',completed=[],base_run=latest['source_run'],base_output=latest['output']);save(manifest,state)
    def step(name,module,*argv):
        if name in state['completed']:return
        subprocess.run([sys.executable,'-X','utf8','-m',module,*map(str,argv)],cwd=ROOT,check=True)
        state['completed'].append(name);save(manifest,state)
    try:
        step('HSBC官网附件','scripts.probe_board_all','--out',folder/'discovery','--banks','HSBC')
        step('HSBC附件表格','scripts.capture_board_repairs','--discovery',folder/'discovery','--out',folder/'hsbc','--banks','HSBC')
        step('工行标签及HLF','scripts.capture_icbc_hlf_board','--out',folder/'icbc-hlf')
        subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/start_local_model.ps1'],cwd=ROOT,check=True)
        step('HSBC本地核对','scripts.verify_with_repair','--run',folder/'hsbc')
        step('工行HLF本地核对','scripts.verify_with_repair','--run',folder/'icbc-hlf')
        source=state['base_run']
        for key in ['hsbc','icbc-hlf']:
            name=key+'合并';target=folder/(key+'-merged')
            if name not in state['completed']:
                replace_verified_sections(source,folder/key,target);state['completed'].append(name);save(manifest,state)
            source=target
        step('Excel及保存后检查','scripts.run_board_wide','--run',source,'--base-output',state['base_output'],*(['--no-open'] if args.no_open else []))
        state['status']='complete';save(manifest,state)
    except Exception as exc:
        state.update(status='failed',error=str(exc));save(manifest,state);raise

if __name__=='__main__':main()
