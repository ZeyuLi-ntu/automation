"""Choose and snapshot the user's two existing, compatible workbook templates."""
from pathlib import Path
import re,shutil
from .common import load,save
from .xlsx_read import read_xlsx,merged_ranges
from .table_validation import sha
from .scope import bank_name

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'config/input-workbooks.local.json'
REPORT_SHEETS=['最高报价汇总 ','Bank List','SGD促销','USD促销','CNY促销','其他外币促销利率']+[c+'挂牌' for c in ['SGD','USD','CNY','AUD','NZD','CAD','HKD','EUR','GBP']]
RAINBOW_SHEETS=['SGD Promotional Rate','SGD Board Rate','USD Rate + Other Currency Rates']
KNOWN_BANKS={'BEA','BOC','CIMB','CITI','DBS','DBS/POSB','HLB','HLF','HSBC','ICBC','Maybank','OCBC','RHB','SBI','SCB','SingFinance','Singapura Finance','UOB'}

def configuration(path=CONFIG):
    return load(path) if Path(path).exists() else dict(mode='latest',report='',rainbow='')

def validate(report,rainbow):
    books={}
    for kind,path,required in [('report',report,REPORT_SHEETS),('rainbow',rainbow,RAINBOW_SHEETS)]:
        path=Path(path).resolve()
        if not path.is_file() or path.suffix.lower()!='.xlsx':raise ValueError('请选择存在的 .xlsx 文件：'+str(path))
        book=read_xlsx(path,merge_anchors_only=True)
        missing=[name for name in required if name not in book]
        if missing:raise ValueError(('调研表' if kind=='report' else '彩虹表')+'缺少工作表：'+', '.join(missing)+'。请选择与现有模板相同格式的文件。')
        books[kind]=book
    if Path(report).resolve()==Path(rainbow).resolve():raise ValueError('调研表和彩虹表应选择不同文件。')
    for name,bank,current in [('SGD促销','A','C'),('USD促销','B','D'),('CNY促销','A','C'),('USD挂牌','B','D'),('CNY挂牌','A','C')]:
        s=books['report'][name]
        if not any(re.fullmatch(bank+r'\d+',a) and v in ['银行','Bank','日期'] for a,v in s.items()):raise ValueError(name+'的银行／日期列位置与模板不同。')
    rb=books['rainbow']['USD Rate + Other Currency Rates']
    if not re.search(r'USD.*Board',str(rb.get('A31','')),re.I):raise ValueError('彩虹表的USD挂牌位置与现有模板不同，请保留原工作表结构。')
    return books

def save_configuration(mode,report='',rainbow='',path=CONFIG):
    if mode not in ['latest','selected']:raise ValueError('无效的文件选择方式。')
    if mode=='selected':validate(report,rainbow)
    value=dict(mode=mode,report=str(Path(report).resolve()) if report else '',rainbow=str(Path(rainbow).resolve()) if rainbow else '')
    save(path,value);return value

def prepare_selected_inputs(work,config):
    """Original Excel files are never opened for writing or overwritten."""
    books=validate(config['report'],config['rainbow']);out=Path(work)/'selected-input';out.mkdir()
    source={};files={}
    for kind in ['report','rainbow']:
        origin=Path(config[kind]).resolve();target=out/(kind+'.xlsx');before=sha(origin);shutil.copy2(origin,target)
        if sha(target)!=before or sha(origin)!=before:raise ValueError('选定文件在复制时发生变化，请保存Excel后重试。')
        files[kind+'_output']=str(target.resolve());source[kind]=dict(path=str(origin),sha256=before)
    def last_row(s):return max(int(re.search(r'\d+$',a)[0]) for a,v in s.items() if v not in [None,''])
    matrices=[dict(sheet=c+'挂牌',currency=c,end=last_row(books['report'][c+'挂牌'])) for c in ['SGD','AUD','NZD','CAD','HKD','EUR','GBP']]
    histories=[dict(currency=c,sheet=c+'挂牌',max_row=last_row(books['report'][c+'挂牌'])) for c in ['USD','CNY']]
    # Only bank blocks define the SGD rainbow extent; unrelated headings do not.
    s=books['rainbow']['SGD Board Rate'];end=max(int(re.search(r'\d+$',a)[0]) for a,v in s.items() if bank_name(v) in KNOWN_BANKS)
    for address in merged_ranges(files['rainbow_output'])['SGD Board Rate']:
        if bank_name(s.get(address.split(':')[0],'')) in KNOWN_BANKS:end=max(end,int(re.search(r'\d+$',address)[0]))
    layout=out/'selected-board-layout.json';save(layout,dict(kind='board-wide',matrices=matrices,histories=histories,rainbow_blocks=[dict(currency='SGD',end=end)],**files))
    save(out/'table-validation-plan.json',dict(kind='selected-input',output=str(out.resolve()),inherited_board_plan=str(layout.resolve()),original_inputs=source,**files))
    return str(out.resolve())
