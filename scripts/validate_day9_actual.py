"""Day 9 real-artifact reconciliation, bounded API benchmarks and local servers.

No ETL or production model fit. Writes only ignored results/day9 and own
project-local temporary files. --serve retains our children for browser checks.
"""
import argparse
import copy
import ctypes
from ctypes import wintypes
import gzip
import json
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import time

from fastapi.testclient import TestClient
import httpx
import pandas as pd
import pyarrow.parquet as pq

from src.analytics.build_gold import ROOT,sha256,footprint
from src.api.main import create_app
from src.api.settings import Settings
from src.features.build_speed_dataset import save_json
from src.features.speed_windows import FEATURES
from src.ml.inference import load_model,predict_features

RESULTS=ROOT/'results/day9'


def protected():
    files=[]
    for folder in ['data/raw','data/bronze','data/silver','data/gold','data/ml','models',
                   *(f'results/day{day}' for day in range(1,9))]:
        files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file())
    return {p.relative_to(ROOT).as_posix():sha256(p) for p in sorted(files)}


def assert_safe(response):
    text=response.text
    assert str(ROOT) not in text and str(ROOT).replace('\\','/') not in text
    assert 'Traceback' not in text and 'input_sha256' not in text


def wait(client,child,path='/api/v1/health'):
    deadline=time.perf_counter()+30
    while time.perf_counter()<deadline:
        if child.poll() is not None: raise RuntimeError('Own loopback server exited')
        try:
            if client.get(path).status_code==200: return
        except httpx.HTTPError: pass
        time.sleep(.1)
    raise RuntimeError('Local server startup timed out')


def stop_child(child):
    """Stop only our still-running child and its Windows redirector descendants."""
    if child.poll() is not None: return
    subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True,
        timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    child.wait(timeout=10)


def memory(pid):
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD),
            *[(field,ctypes.c_size_t) for field in ('PeakWorkingSetSize','WorkingSetSize',
                'QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage',
                'QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x410,False,pid)
    if not handle: raise ctypes.WinError(ctypes.get_last_error())
    try:
        counters=Counters(); counters.cb=ctypes.sizeof(counters)
        api=ctypes.WinDLL('psapi',use_last_error=True).GetProcessMemoryInfo
        api.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
        if not api(handle,ctypes.byref(counters),counters.cb): raise ctypes.WinError(ctypes.get_last_error())
        return {'working_set_bytes':counters.WorkingSetSize,'peak_working_set_bytes':counters.PeakWorkingSetSize,
                'private_bytes':counters.PrivateUsage}
    finally: kernel.CloseHandle(handle)


def memory_tree(root_pid):
    """Include Windows venv redirector children, not just the tiny launcher."""
    class Entry(ctypes.Structure):
        _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),('th32ProcessID',wintypes.DWORD),
            ('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',wintypes.DWORD),('cntThreads',wintypes.DWORD),
            ('th32ParentProcessID',wintypes.DWORD),('pcPriClassBase',wintypes.LONG),
            ('dwFlags',wintypes.DWORD),('szExeFile',wintypes.WCHAR*260)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    first=kernel.Process32FirstW; first.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
    next_entry=kernel.Process32NextW; next_entry.argtypes=first.argtypes
    handle=kernel.CreateToolhelp32Snapshot(2,0)
    if handle==ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
    parents={}; entry=Entry(); entry.dwSize=ctypes.sizeof(entry)
    try:
        valid=first(handle,ctypes.byref(entry))
        while valid:
            parents[entry.th32ProcessID]=entry.th32ParentProcessID
            valid=next_entry(handle,ctypes.byref(entry))
    finally: kernel.CloseHandle(handle)
    own={root_pid}
    while True:
        children={pid for pid,parent in parents.items() if parent in own}
        if children<=own: break
        own|=children
    processes=[{'pid':pid,**memory(pid)} for pid in sorted(own)]
    return {'own_processes':processes,**{key:sum(p[key] for p in processes)
        for key in ('working_set_bytes','private_bytes')}}


def validate(serve=False, api_port=8000, web_port=5173):
    started=time.perf_counter(); RESULTS.mkdir(parents=True,exist_ok=True)
    before=protected(); save_json(RESULTS/'protected_before.json',before)
    example=json.loads((ROOT/'docs/examples/day7_prediction_request.json').read_text())
    model,_=load_model()
    vector=pd.DataFrame([{k:float('nan') if v is None else v for k,v in example['features'].items()}],columns=FEATURES)
    expected=float(predict_features(vector,model)[0])
    paths=['/health','/ready','/fleet/overview','/vehicles?limit=25','/trips?limit=25',
        '/trends/daily?limit=100','/trends/monthly?limit=100','/fleet/powertrains?limit=100',
        '/quality/summary','/quality/pipeline','/ml/metrics','/ml/vehicle-errors?limit=25',
        '/ml/cohorts','/ml/cohorts?dimension=powertrain','/ml/features']
    app=create_app(); contracts={}
    with TestClient(app,raise_server_exceptions=False) as client:
        for path in paths:
            response=client.get('/api/v1'+path); assert response.status_code==200,(path,response.status_code)
            assert_safe(response); contracts[path]=response.json()
        # Compare every projected field in sampled pages with saved Gold rows.
        table_paths={'/fleet/overview':'fleet_overview','/vehicles?limit=25':'vehicle_analytics',
            '/trips?limit=25':'trip_analytics','/trends/daily?limit=100':'daily_fleet',
            '/trends/monthly?limit=100':'monthly_fleet','/fleet/powertrains?limit=100':'powertrain_fleet'}
        compared=0
        for path,table in table_paths.items():
            source=pq.read_table(ROOT/f'data/gold/ved/{table}.parquet').to_pylist()
            rows=contracts[path].get('items',[contracts[path]])
            keys={'vehicle_analytics':('vehicle_id',),'trip_analytics':('vehicle_id','trip_id'),
                'daily_fleet':('trip_start_reference_day',),'monthly_fleet':('trip_start_reference_month',),
                'powertrain_fleet':('engine_type',),'fleet_overview':() }[table]
            def normalize(value):
                return value.isoformat() if hasattr(value,'isoformat') else value
            index={tuple(normalize(row[k]) for k in keys):row for row in source}
            for row in rows:
                original=index[tuple(row[k] for k in keys)]
                for key,value in row.items():
                    assert value==normalize(original[key]),(table,key)
                    compared+=1
            if 'items' in contracts[path]: assert contracts[path]['total']==len(source)
        pipeline=contracts['/quality/pipeline']; overview=contracts['/fleet/overview']
        assert pipeline['bronze_observations']==pipeline['silver_observations']+pipeline['quarantined_observations']
        assert pipeline['silver_observations']==overview['observation_count']==22434106
        quality=json.loads((ROOT/'results/day3/silver_quality.json').read_text())
        assert pipeline['missing_measurements']=={k:quality['retained_null_counts'][k] for k in pipeline['missing_measurements']}
        run=json.loads((ROOT/'results/day6/training_run.json').read_text())
        metrics=contracts['/ml/metrics']
        for split,methods in metrics['metrics'].items():
            for method,values in methods.items():
                for key,value in values.items(): assert value==run['metrics'][split][method][key]
        for dimension,path in [('actual_target_speed_range','/ml/cohorts'),('powertrain','/ml/cohorts?dimension=powertrain')]:
            saved=json.loads((ROOT/'results/day6/cohort_metrics.json').read_text())
            assert contracts[path]['items']==[row for row in saved if row['split']=='test' and row['dimension']==dimension]
        predicted=client.post('/api/v1/ml/predict',json=example)
        assert predicted.status_code==200 and predicted.json()['predicted_mean_speed_kmh']==expected
        invalid=copy.deepcopy(example); invalid['features']['past_gap_max_s']=3
        security_cases={}
        for label,response,code in [
            ('limit',client.get('/api/v1/trips?limit=101'),422),
            ('offset',client.get('/api/v1/trips?offset=100001'),422),
            ('unknown_query',client.get('/api/v1/ml/cohorts?path=C:/private'),422),
            ('wrong_feature',client.post('/api/v1/ml/predict',json={'gps':[0,0]}),422),
            ('gap_policy',client.post('/api/v1/ml/predict',json=invalid),422),
            ('body_limit',client.post('/api/v1/ml/predict',content=b'x'*65537),413),
            ('malformed_json',client.post('/api/v1/ml/predict',content=b'{',headers={'Content-Type':'application/json'}),422)]:
            assert response.status_code==code; assert_safe(response)
            security_cases[label]=code
        for origin,allowed in [('http://127.0.0.1:5173',True),('http://localhost:5173',True),('https://evil.example',False)]:
            response=client.options('/api/v1/ml/predict',headers={'Origin':origin,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'Content-Type'})
            assert (response.headers.get('access-control-allow-origin')==origin)==allowed
            assert 'access-control-allow-credentials' not in response.headers
        empty=ROOT/'data/tmp/day9-missing-artifacts'; empty.mkdir(parents=True,exist_ok=True)
        with TestClient(create_app(Settings(root=empty)),raise_server_exceptions=False) as missing:
            assert missing.get('/api/v1/health').status_code==200
            for path in ['/ready','/fleet/overview','/quality/pipeline','/ml/metrics','/ml/cohorts']:
                response=missing.get('/api/v1'+path); assert response.status_code==503; assert_safe(response)
            assert missing.post('/api/v1/ml/predict',json=example).status_code==503
        query_count=app.state.analytics.query_count
        for _ in range(20): client.get('/api/v1/fleet/overview')
        assert app.state.analytics.query_count==query_count
    save_json(RESULTS/'contracts.json',contracts)
    children=[]; logs=[]; spawn=[]
    env={**os.environ,'PYTHONPATH':str(ROOT),'TEMP':str(ROOT/'data/tmp'),'TMP':str(ROOT/'data/tmp'),
         'FLEETPULSE_API_PORT':str(api_port),'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1',
         'MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1'}
    for port in (api_port,web_port):
        with socket.socket() as sock:
            try: sock.bind(('127.0.0.1',port))
            except OSError: raise RuntimeError(f'Port {port} already in use; no unrelated process stopped') from None
    try:
        commands=[('backend',[sys.executable,'-m','uvicorn','src.api.main:app','--host','127.0.0.1',
            '--port',str(api_port),'--workers','1','--limit-concurrency','32','--timeout-keep-alive','5','--no-access-log'],ROOT),
            ('frontend',[shutil.which('node'),'node_modules/vite/bin/vite.js','--host','127.0.0.1','--port',str(web_port)],ROOT/'dashboard')]
        for name,command,cwd in commands:
            log=(RESULTS/f'{name}.log').open('w',encoding='utf-8'); logs.append(log); spawn.append(time.perf_counter())
            children.append(subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
        with (httpx.Client(base_url=f'http://127.0.0.1:{api_port}',trust_env=False,timeout=20) as api,
              httpx.Client(base_url=f'http://127.0.0.1:{web_port}',trust_env=False,timeout=20) as web):
            wait(api,children[0]); api_start=time.perf_counter()-spawn[0]
            wait(web,children[1],'/'); web_start=time.perf_counter()-spawn[1]
            for path in paths:
                response=web.get('/api/v1'+path); assert response.status_code==200
                assert response.json()==contracts[path]; assert_safe(response)
            dev_module=web.get('/src/pages/Prediction.tsx')
            dev_path_metadata=str(ROOT).replace('\\','/') in dev_module.text or str(ROOT).replace('\\','\\\\') in dev_module.text
            memory_before=memory_tree(children[0].pid)
            timings={}
            for path in ['/fleet/overview','/trips?limit=25','/trends/daily?limit=100','/quality/pipeline','/ml/metrics','/ml/cohorts']:
                api.get('/api/v1'+path)  # warm each endpoint
                samples=[]
                for _ in range(30):
                    tick=time.perf_counter(); response=api.get('/api/v1'+path)
                    samples.append((time.perf_counter()-tick)*1000)
                    assert response.status_code==200
                timings[path]={'samples':30,'median_ms':statistics.median(samples),
                    'p95_ms':sorted(samples)[28],'max_ms':max(samples),'response_bytes':len(response.content)}
            first_prediction_started=time.perf_counter()
            response=api.post('/api/v1/ml/predict',json=example)
            first_prediction_ms=(time.perf_counter()-first_prediction_started)*1000
            assert response.status_code==200 and response.json()['predicted_mean_speed_kmh']==expected
            samples=[]
            for _ in range(30):
                tick=time.perf_counter(); response=api.post('/api/v1/ml/predict',json=example)
                samples.append((time.perf_counter()-tick)*1000)
                assert response.status_code==200 and response.json()['predicted_mean_speed_kmh']==expected
            timings['/ml/predict']={'samples':30,'median_ms':statistics.median(samples),'p95_ms':sorted(samples)[28],
                'max_ms':max(samples),'response_bytes':len(response.content)}
            memory_after=memory_tree(children[0].pid); frontend_memory=memory_tree(children[1].pid)
        smoke=subprocess.run([shutil.which('node'),'scripts/smoke-built.mjs',f'http://127.0.0.1:{web_port}'],
            cwd=ROOT/'dashboard',env=env,capture_output=True,text=True,timeout=90,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (RESULTS/'production_dom.log').write_text(smoke.stdout+smoke.stderr,encoding='utf-8')
        assert smoke.returncode==0,'Production DOM integration failed; inspect ignored Day 9 log'
        dom_result=json.loads(smoke.stdout)
        assert dom_result['pages']==5 and dom_result['prepared_inputs']==31
        assert len(dom_result['api_requests'])==13,'Unexpected production navigation request count'
        stop_child(children[0])
        with httpx.Client(base_url=f'http://127.0.0.1:{web_port}',trust_env=False,timeout=10) as web:
            unavailable_response=web.get('/api/v1/health')
            assert unavailable_response.status_code>=500
            assert_safe(unavailable_response)
        unavailable_dom=subprocess.run([shutil.which('node'),'scripts/smoke-built.mjs',
            f'http://127.0.0.1:{web_port}','--unavailable'],cwd=ROOT/'dashboard',env=env,
            capture_output=True,text=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (RESULTS/'unavailable_dom.log').write_text(unavailable_dom.stdout+unavailable_dom.stderr,encoding='utf-8')
        assert unavailable_dom.returncode==0,'Backend-unavailable UI verification failed'
        assets=[{'file':p.relative_to(ROOT/'dashboard/dist').as_posix(),'bytes':p.stat().st_size,
                 'gzip_bytes':len(gzip.compress(p.read_bytes(),mtime=0))}
                for p in sorted((ROOT/'dashboard/dist').rglob('*')) if p.is_file()]
        from scripts.audit_git_index import PATTERNS
        for asset in (ROOT/'dashboard/dist').rglob('*'):
            if not asset.is_file(): continue
            blob=asset.read_bytes()
            for prefix in (str(ROOT),str(ROOT).replace('\\','/'),str(ROOT).replace('\\','\\\\')):
                assert prefix.encode() not in blob,'Absolute project path in production bundle'
            assert not any(pattern.search(blob) for pattern in PATTERNS.values()),'Recognized secret in production bundle'
        assert protected()==before,'Earlier artifacts changed'
        result={'passed':True,'source_fields_reconciled':compared,'frontend_read_contracts':len(paths),
            'prediction_kmh':expected,'security_cases':security_cases,'cors_checked':True,'missing_artifacts_checked':True,
            'warm_overview_queries_added':0,'api_timings':timings,'first_prediction_ms':first_prediction_ms,
            'backend_memory_before':memory_before,
            'backend_memory_after':memory_after,'frontend_dev_memory':frontend_memory,'build_assets':assets,
            'protected_files_unchanged':len(before),'production_dom_smoke':dom_result,
            'real_backend_unavailable_http_status':unavailable_response.status_code,
            'real_backend_unavailable_dom_checked':True,
            'production_bundle_path_secret_scan_passed':True,'development_source_path_metadata_present':dev_path_metadata,
            'native_threads_limited_before_startup':True,
            'api_startup_seconds':api_start,'frontend_startup_seconds':web_start,
            'runtime_seconds':time.perf_counter()-started,'project_bytes':footprint(),
            'browser_visual_verified':False,'browser_reason':'No enabled browser surfaces; checked separately through computer-use.'}
        save_json(RESULTS/'actual_validation.json',result); print(json.dumps(result,indent=2),flush=True)
        if serve:
            marker=RESULTS/'stop_serving'
            if marker.exists(): marker.unlink()  # disposable project-local coordination marker
            deadline=time.monotonic()+1200
            while not marker.exists() and time.monotonic()<deadline: time.sleep(.25)
        assert protected()==before,'Earlier artifacts changed during serving'
    finally:
        for child in reversed(children):
            stop_child(child)
        for log in logs: log.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--serve',action='store_true')
    validate(parser.parse_args().serve)
