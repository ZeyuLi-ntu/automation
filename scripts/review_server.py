"""Local-only Chinese review form; edits are audited and never overwrite evidence."""
import argparse,json,mimetypes,secrets,socket,subprocess,sys,threading,webbrowser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,unquote,parse_qs
from market_rates.common import load
from market_rates.manual_review import items,record,ledger,add_offer,effective_offers,catalog
from market_rates.common import digest
from market_rates.weekly_history import identity
from market_rates.pipeline import check_evidence
from market_rates.workbook_policy import workbook_policy,bank_in_scope,presentation_currency

ROOT=Path(__file__).resolve().parents[1]

class ReviewHTTPServer(ThreadingHTTPServer):
    allow_reuse_address=False
    def server_bind(self):
        if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()

def running_server(url):
    from urllib.request import urlopen
    try:
        with urlopen(url+'/api/health',timeout=2) as response:return json.load(response).get('app')=='market-rate-review'
    except Exception:return False

class ReviewApp:
    def __init__(self,project=ROOT,output=None,dataset='promo'):
        self.project=Path(project).resolve();self.output=output;self.dataset=dataset;self.token=secrets.token_urlsafe(32);self.lock=threading.Lock();self.job=None
    def context(self):
        pointer={'board':'latest-board-pilot.json','fx':'latest-fx-promo.json'}.get(self.dataset,'latest-workflow.json')
        out=Path(self.output or load(self.project/'outputs'/pointer)['output']).resolve();out.relative_to(self.project/'outputs')
        plan=load(out/'table-validation-plan.json');run_path=Path(plan['source_run']);run_path.resolve().relative_to(self.project/'runs')
        run=load(run_path/'run.json');check_evidence(run,run_path/'evidence');return out,plan,run,run_path
    def data(self):
        out,plan,run,run_path=self.context();data=[i for i in items(run,self.project) if bank_in_scope(i['bank'])];policy=workbook_policy()
        accepted,_,receipts=effective_offers(run,self.project)
        carried={r['id']:r for r in receipts if r.get('carried_forward')}
        current={identity(r):r for r in accepted}
        held={identity(r):r.get('hold_reason') for r in plan.get('details',[]) if r.get('hold_reason')}
        for item in data:
            if item['id'] in carried and item['id'] in current:
                item['effective']=current[item['id']];item['carried_forward']=carried[item['id']]
            r=item['effective'] or item['original']
            item['presentation_currency']=presentation_currency(r['currency'])
            item['excluded_by_policy']=item['product_id'] in policy['deferred_product_ids'] or f"{r['bank']}/{r['product_id']}/{r['tenor_value']}{r['tenor_unit']}" in policy.get('deferred_actual_tenors',[])
            if identity(r) in held:
                item['excluded_by_policy']=True;item['insertion_hold']=held[identity(r)]
            for evidence in item['evidence']:
                evidence['images']=['/file/'+(run_path/'evidence'/name).relative_to(self.project).as_posix() for name in evidence['images']]
        return dict(version=ledger(self.project)['version'],items=data,catalog=[dict(c,id=digest(c)) for c in catalog(run)],as_of=plan['as_of'],bank_dates={b:d for b,d in plan['bank_dates'].items() if bank_in_scope(b)},banks=[b for b in plan['banks'] if bank_in_scope(b)],
            coverage=[c for c in run.get('coverage',[]) if bank_in_scope(c['bank'])]+[dict(bank='本批范围',reason=s) for s in plan.get('limitations',[])],output=str(out),history=ledger(self.project)['revisions'][-40:],job=self.job,
            report='/file/'+Path(plan['report_output']).relative_to(self.project).as_posix(),
            rainbow='/file/'+Path(plan['rainbow_output']).relative_to(self.project).as_posix())
    def regenerate(self):
        if self.job and self.job['status']=='running':raise ValueError('正在重新生成，请等待完成。')
        out,_,_,_=self.context();self.job=dict(status='running',message='正在同步调研、汇总和彩虹表，并检查历史与排序。')
        def task():
            try:
                log_path=self.project/'data/manual-rebuild.log';log_path.parent.mkdir(exist_ok=True)
                with log_path.open('w',encoding='utf8') as log:
                    p=subprocess.run([sys.executable,'-X','utf8','-m','scripts.regenerate_from_review','--output',str(out)],cwd=self.project,stdout=log,stderr=subprocess.STDOUT)
                if p.returncode:raise ValueError('生成未完成；请查看 data/manual-rebuild.log。原文件保留。')
                self.output=None;self.job=dict(status='complete',message='修正版已生成，请刷新并打开工作簿检查。')
            except Exception as e:self.job=dict(status='failed',message=str(e))
        threading.Thread(target=task,daemon=True).start();return self.job

def handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,code,data,kind='application/json; charset=utf-8'):
            if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
        def valid_host(self):return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        def do_GET(self):
            if not self.valid_host():return self.send(403,{'error':'仅允许本机访问'})
            path=unquote(urlsplit(self.path).path)
            try:
                if path=='/api/health':return self.send(200,{'app':'market-rate-review','version':1,'dataset':app.dataset})
                if path=='/':return self.send(200,(ROOT/'market_rates/review_app.html').read_text(encoding='utf8').replace('__TOKEN__',app.token).encode(),'text/html; charset=utf-8')
                if path=='/api/state':return self.send(200,app.data())
                if path.startswith('/file/'):
                    file=(app.project/path[6:]).resolve()
                    if not any(file.is_relative_to(app.project/k) for k in ['outputs','runs']):raise ValueError('文件不在复核范围内')
                    generated_coverage=file.is_relative_to(app.project/'outputs') and file.name=='board-coverage.html'
                    audit_json=file.name in {'board-coverage.json','source.json','run.json'}
                    if file.suffix.lower() not in {'.png','.jpg','.jpeg','.pdf','.txt','.xlsx'} and not generated_coverage and not audit_json:raise ValueError('不支持的证据格式')
                    return self.send(200,file.read_bytes(),mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
                return self.send(404,{'error':'未找到'})
            except Exception as e:return self.send(400,{'error':str(e)})
        def do_POST(self):
            if not self.valid_host() or self.headers.get('X-Review-Token')!=app.token:return self.send(403,{'error':'请从本机复核入口操作'})
            origin=self.headers.get('Origin')
            if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}:return self.send(403,{'error':'来源不匹配'})
            try:
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<200000:raise ValueError('请求大小不合法')
                body=json.loads(self.rfile.read(size))
                with app.lock:
                    if self.path=='/api/save':
                        if app.job and app.job['status']=='running':raise ValueError('生成期间请暂缓编辑，避免混用版本。')
                        _,_,run,_=app.context();record(run,body,app.project);return self.send(200,{'version':ledger(app.project)['version']})
                    if self.path=='/api/add':
                        if app.job and app.job['status']=='running':raise ValueError('生成期间不能补录。')
                        _,_,run,_=app.context();add_offer(run,body,app.project);return self.send(200,{'version':ledger(app.project)['version']})
                    if self.path=='/api/regenerate':
                        if body.get('version')!=ledger(app.project)['version']:raise ValueError('修改版本已变化，请刷新后重新生成。')
                        return self.send(200,app.regenerate())
                    raise ValueError('未知操作')
            except Exception as e:return self.send(400,{'error':str(e)})
    return Handler

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);p.add_argument('--dataset',choices=['promo','board','fx'],default='promo');p.add_argument('--no-open',action='store_true');a=p.parse_args()
    app=ReviewApp(dataset=a.dataset);url=f'http://127.0.0.1:{a.port}'
    if running_server(url):
        print('人工修正入口已在运行：'+url,flush=True)
        if not a.no_open:webbrowser.open(url)
        return
    try:server=ReviewHTTPServer(('127.0.0.1',a.port),handler(app))
    except OSError:
        known=running_server(url)
        if not known:raise ValueError('8765 端口被其他程序占用，请关闭冲突程序或指定另一端口。') from None
        print('人工修正入口已在运行：'+url,flush=True)
        if not a.no_open:webbrowser.open(url)
        return
    print('人工修正入口：'+url+'（关闭此窗口即可停止服务）',flush=True)
    if not a.no_open:webbrowser.open(url)
    try:server.serve_forever()
    finally:server.server_close()

if __name__=='__main__':main()
