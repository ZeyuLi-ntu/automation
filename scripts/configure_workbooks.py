import argparse
from market_rates.input_workbooks import save_configuration,CONFIG

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['latest','selected'],required=True);p.add_argument('--report',default='');p.add_argument('--rainbow',default='');a=p.parse_args()
    try:
        result=save_configuration(a.mode,a.report,a.rainbow)
        print('已保存。下次新运行会使用：'+('上次完整输出' if a.mode=='latest' else a.report+'；'+a.rainbow))
        print('原文件不覆盖。继续旧任务仍使用旧任务开始时的文件。')
    except Exception as exc:
        print('未保存：'+str(exc));raise SystemExit(1)
