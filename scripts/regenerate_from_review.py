"""Rebuild a reviewed draft at its original collection date, without refetching."""
from datetime import datetime
from pathlib import Path
import shutil, subprocess,sys
from market_rates.common import load,save

def regenerate(project,output):
    project=Path(project).resolve();out=Path(output).resolve();out.relative_to(project/'outputs')
    plan=load(out/'table-validation-plan.json');source=Path(plan['source_run']);source.relative_to(project/'runs')
    if plan.get('kind')=='fx-promo':
        subprocess.run([sys.executable,'-X','utf8','-m','scripts.run_fx_promo','--run',str(source),'--base-output',str(Path(plan['base_plan']).parent),'--no-open'],cwd=project,check=True)
        return
    if plan.get('kind')=='board-wide':
        subprocess.run([sys.executable,'-X','utf8','-m','scripts.run_board_wide','--run',str(source),'--base-output',str(out),'--no-open'],cwd=project,check=True)
        return
    if plan.get('kind')=='board-batch':
        subprocess.run([sys.executable,'-X','utf8','-m','scripts.run_board_batch','--run',str(source),'--base-output',str(out),'--no-open'],cwd=project,check=True)
        return
    if plan.get('kind')=='board-pilot':
        subprocess.run([sys.executable,'-X','utf8','-m','scripts.run_board_workflow','--run',str(source),'--base-output',str(out),'--no-open'],cwd=project,check=True)
        return
    work=project/'runs'/('manual-rebuild-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'));work.mkdir()
    shutil.copytree(source,work/'combined')
    save(work/'workflow.json',dict(project=str(project),mode='rebuild',completed=['合并银行'],status='running',sources=[],correction_of=str(out)))
    subprocess.run([sys.executable,'-X','utf8','-m','scripts.run_market_workflow','--resume',str(work),'--no-open'],cwd=project,check=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();regenerate(Path(__file__).resolve().parents[1],a.output)
