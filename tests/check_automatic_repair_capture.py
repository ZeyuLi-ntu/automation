"""Local browser smoke test: future capture supplies exact cell geometry."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright
from market_rates.board_capture import BoardCapture
from market_rates.common import load,save,digest
from market_rates.evidence_repair import repair

def check(root):
    root=Path(root);batch=BoardCapture(root)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1000,'height':800},device_scale_factor=2)
        try:
            page.set_content('<style>td{padding:12px;border:0}table{border-collapse:collapse;table-layout:fixed;width:720px}</style>'
                '<table><colgroup><col style="width:120px"><col style="width:240px"><col style="width:360px"></colgroup>'
                '<tr><td>5,000</td><td>0.10%</td><td>0.20%</td></tr></table>')
            record=dict(id='local-test',bank='TEST',images=[],image_hashes={},text='local test')
            rows,ids=batch.table(page,record,'unequal',page.locator('table'),group_size=1)
            task=batch.tasks[0]
            assert task['source_cell_cuts']==[240,720],task
            run=dict(tasks=batch.tasks,pages=[record],sections=[dict(id='s',task_ids=ids)],task_hash=digest(batch.tasks),evidence_hash=digest([record]))
            save(root/'run.json',run)
            save(root/'wave-checks.json',dict(task_hash=run['task_hash'],errors=[dict(task=ids[0],error='Literal source/transcription mismatch')]))
            event=repair(root,'source')
            assert event['actions'][0]['method']=='原网页单元格位置拆图'
            assert load(root/'run.json')['tasks'][0]['expected']==rows
            print('本地浏览器原单元格坐标采集与自动拆图通过。')
        finally:browser.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();check(a.out)
