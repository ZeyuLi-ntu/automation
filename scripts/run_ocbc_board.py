"""One local OCBC refresh: capture, dual verification, merge and Excel output."""
import argparse, os, subprocess, sys
from pathlib import Path
from datetime import datetime
from market_rates.common import load, save
from market_rates.board_wave import replace_verified_sections

ROOT=Path(__file__).resolve().parents[1]

def main():
    a=argparse.ArgumentParser();a.add_argument('--resume');a.add_argument('--verified-wave');a.add_argument('--no-open',action='store_true');x=a.parse_args();os.chdir(ROOT)
    folder=Path(x.resume).resolve() if x.resume else ROOT/'runs'/('ocbc-refresh-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    manifest=folder/'workflow.json'
    if x.resume:state=load(manifest)
    else:
        folder.mkdir();previous=load(ROOT/'outputs/latest-board-pilot.json')
        state=dict(status='running',completed=[],base_output=previous['output'],base_run=previous['source_run'],wave=str(Path(x.verified_wave).resolve()) if x.verified_wave else str(folder/'capture'),combined=str(folder/'combined'))
        if x.verified_wave:state['completed'].append('采集')
        save(manifest,state)
    def step(label,module,*args):
        if label in state['completed']:return
        subprocess.run([sys.executable,'-X','utf8','-m',module,*args],check=True,cwd=ROOT)
        state['completed'].append(label);save(manifest,state)
    try:
        step('采集','scripts.capture_ocbc_board','--out',state['wave'])
        subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/start_local_model.ps1'],check=True,cwd=ROOT)
        step('本地双路核验','scripts.verify_with_repair','--run',state['wave'])
        if '合并' not in state['completed']:
            replace_verified_sections(state['base_run'],state['wave'],state['combined'])
            state['completed'].append('合并');save(manifest,state)
        step('写入Excel并回读','scripts.run_board_wide','--run',state['combined'],'--base-output',state['base_output'],*(['--no-open'] if x.no_open else []))
        state.update(status='complete',output=load(ROOT/'outputs/latest-board-pilot.json')['output']);save(manifest,state)
        print('OCBC 已更新到 Excel：'+state['output'],flush=True)
    except Exception as exc:
        state.update(status='failed',error=str(exc));save(manifest,state);raise

if __name__=='__main__':main()
