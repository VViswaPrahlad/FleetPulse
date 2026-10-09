"""Read existing artifacts, export API contracts, verify real HTTP/Vite proxy.

Optional --serve keeps only our child servers alive for an interactive browser
smoke test until results/day8/stop_serving exists (or a 20-minute deadline).
No ETL, fit, old-report writes, or dataset regeneration occurs.
"""
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

from fastapi.testclient import TestClient
import httpx
from src.api.main import create_app
from src.analytics.build_gold import ROOT,sha256,footprint
from src.features.build_speed_dataset import save_json

RESULTS=ROOT/'results/day8'


def protected():
    files=[]
    for folder in ['data/raw','data/bronze','data/silver','data/gold','data/ml','models',
                   *(f'results/day{day}' for day in range(1,8))]:
        files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file())
    return {p.relative_to(ROOT).as_posix():sha256(p) for p in sorted(files)}


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


def wait(client,process,path):
    started=time.perf_counter()
    while time.perf_counter()-started<30:
        if process.poll() is not None:
            raise RuntimeError('Local child server exited; inspect ignored Day 8 logs')
        try:
            if client.get(path).status_code==200:
                return time.perf_counter()-started
        except httpx.HTTPError:
            pass
        time.sleep(.1)
    raise RuntimeError('Local server readiness timed out')


def validate(serve=False):
    started=time.perf_counter(); RESULTS.mkdir(parents=True,exist_ok=True)
    before=protected()
    example=json.loads((ROOT/'docs/examples/day7_prediction_request.json').read_text())
    calls={'overview':'/fleet/overview','vehicles':'/vehicles?limit=25','trips':'/trips?limit=25',
        'monthly':'/trends/monthly?limit=100','daily':'/trends/daily?limit=100',
        'powertrains':'/fleet/powertrains?limit=100','quality':'/quality/summary',
        'pipeline':'/quality/pipeline','metrics':'/ml/metrics','features':'/ml/features',
        'vehicle_errors':'/ml/vehicle-errors?limit=25','speed_cohorts':'/ml/cohorts',
        'powertrain_cohorts':'/ml/cohorts?dimension=powertrain'}
    contracts={}
    with TestClient(create_app(),raise_server_exceptions=False) as client:
        for name,path in calls.items():
            response=client.get('/api/v1'+path)
            assert response.status_code==200,(path,response.status_code)
            assert str(ROOT) not in response.text
            contracts[name]=response.json()
        response=client.post('/api/v1/ml/predict',json=example)
        assert response.status_code==200
        contracts['prediction']=response.json()
        assert abs(response.json()['predicted_mean_speed_kmh']-36.61748855856695)<1e-10
        contracts['openapi']=client.get('/openapi.json').json()
    p=contracts['pipeline']; f=contracts['overview']
    assert p['bronze_observations']==p['silver_observations']+p['quarantined_observations']==22436808
    assert p['silver_observations']==p['gold_source_observations']==f['observation_count']==22434106
    assert (f['vehicle_count'],f['trip_count'])==(384,32552)
    assert len(contracts['features']['feature_order'])==31
    save_json(RESULTS/'contracts.json',contracts)
    api_port=port(); frontend_port=port(); dev_port=port()
    env={**os.environ,'PYTHONPATH':str(ROOT),'FLEETPULSE_API_PORT':str(api_port),
        'TEMP':str(ROOT/'data/tmp'),'TMP':str(ROOT/'data/tmp')}
    children=[]; logs=[]; spawn_times=[]
    try:
        for name,command,cwd in [('backend',[sys.executable,'-m','uvicorn','src.api.main:app',
            '--host','127.0.0.1','--port',str(api_port),'--workers','1','--no-access-log'],ROOT),
            ('frontend',[shutil.which('node'),'node_modules/vite/bin/vite.js','preview',
                '--host','127.0.0.1','--port',str(frontend_port)],ROOT/'dashboard'),
            ('frontend_dev',[shutil.which('node'),'node_modules/vite/bin/vite.js',
                '--host','127.0.0.1','--port',str(dev_port)],ROOT/'dashboard')]:
            log=(RESULTS/f'{name}_smoke.log').open('w',encoding='utf-8'); logs.append(log)
            spawn_times.append(time.perf_counter())
            children.append(subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
        with (httpx.Client(base_url=f'http://127.0.0.1:{api_port}',trust_env=False,timeout=15) as api,
             httpx.Client(base_url=f'http://127.0.0.1:{frontend_port}',trust_env=False,timeout=15) as web):
            wait(api,children[0],'/api/v1/health')
            api_start=time.perf_counter()-spawn_times[0]
            wait(web,children[1],'/')
            frontend_start=time.perf_counter()-spawn_times[1]
            assert web.get('/').status_code==200
            for path in calls.values():
                assert web.get('/api/v1'+path).status_code==200,path
            prediction=web.post('/api/v1/ml/predict',json=example)
            assert prediction.status_code==200 and prediction.json()==contracts['prediction']
            for path in ('/driving','/quality','/ml','/prediction'):
                assert '<div id="root">' in web.get(path).text
            assert web.get('/api/v1/trips?limit=25&powertrain=EV').json()['total']>0
            assert web.get('/api/v1/vehicles?limit=25&powertrain=ICE').json()['total']==264
            assert web.get('/api/v1/trends/daily?limit=100&offset=100').json()['offset']==100
            assert web.get('/api/v1/ml/cohorts?dimension=powertrain').json()['total']==12
            assert web.post('/api/v1/ml/predict',json={'gps':[0,0]}).status_code==422
        with httpx.Client(base_url=f'http://127.0.0.1:{dev_port}',trust_env=False,timeout=20) as dev:
            wait(dev,children[2],'/')
            dev_start=time.perf_counter()-spawn_times[2]
            for path in ('/src/main.tsx','/src/App.tsx','/src/styles.css'):
                assert dev.get(path).status_code==200,path
            module=dev.get('/src/pages/Prediction.tsx')
            assert module.status_code==200
            example_import=re.search(r'import example from [\"\']([^\"\']+)',module.text)
            assert example_import,'Example JSON import missing in transformed dev module'
            assert dev.get(example_import.group(1)).status_code==200,'Documented example inaccessible in dev mode'
            assert dev.get('/api/v1/fleet/overview').json()==contracts['overview']
        smoke_started=time.perf_counter()
        smoke=subprocess.run([shutil.which('node'),'scripts/smoke-built.mjs',f'http://127.0.0.1:{frontend_port}'],
            cwd=ROOT/'dashboard',env=env,capture_output=True,text=True,timeout=90,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (RESULTS/'built_dom_smoke.log').write_text(smoke.stdout+smoke.stderr,encoding='utf-8')
        assert smoke.returncode==0,'Built-bundle DOM smoke failed; inspect ignored Day 8 log'
        built_dom_seconds=time.perf_counter()-smoke_started
        unchanged=protected()==before
        assert unchanged,'Prior artifacts changed'
        result={'passed':True,'read_contracts_validated':len(calls),'prediction_kmh':contracts['prediction']['predicted_mean_speed_kmh'],
            'loopback_vite_proxy_verified':True,'all_earlier_artifacts_unchanged':unchanged,
            'protected_files':len(before),'protected_sha256':before,'api_startup_seconds':api_start,
            'frontend_preview_startup_seconds':frontend_start,'runtime_seconds':time.perf_counter()-started,
            'project_bytes':footprint(),'api_port':api_port,'frontend_port':frontend_port,
            'production_bundle_real_api_dom_smoke':True,'built_dom_smoke_seconds':built_dom_seconds,
            'visual_browser_verified':False,'frontend_dev_http_verified':True,
            'frontend_dev_startup_seconds':dev_start}
        save_json(RESULTS/'actual_validation.json',result)
        print(json.dumps({k:v for k,v in result.items() if k!='protected_sha256'},indent=2),flush=True)
        if serve:
            marker=RESULTS/'stop_serving'
            # Remove only this disposable, explicitly scoped coordination marker.
            if marker.exists(): marker.unlink()
            deadline=time.monotonic()+1200
            while not marker.exists() and time.monotonic()<deadline:
                time.sleep(.25)
    finally:
        for process in reversed(children):
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)
        for log in logs: log.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--serve',action='store_true')
    validate(parser.parse_args().serve)
