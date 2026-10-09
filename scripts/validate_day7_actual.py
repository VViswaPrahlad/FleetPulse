"""Exercise real artifacts, all prepared vectors, and a loopback Uvicorn server."""
import importlib.metadata
import json
import math
from pathlib import Path
import socket
import subprocess
import sys
import time

from fastapi.testclient import TestClient
import httpx
import pandas as pd
import pyarrow.parquet as pq

from src.analytics.build_gold import ROOT,sha256,footprint
from src.api.main import create_app
from src.api.schemas.prediction import PredictionRequest
from src.features.speed_windows import FEATURES
from src.ml.inference import load_model,predict_features
from src.features.build_speed_dataset import save_json

RESULTS=ROOT/'results/day7'


def preserved_hashes():
    paths=[]
    for layer in ('raw','bronze','silver','gold','ml'):
        paths.extend(p for p in (ROOT/f'data/{layer}').rglob('*') if p.is_file())
    for day in range(1,7):
        paths.extend(p for p in (ROOT/f'results/day{day}').rglob('*') if p.is_file())
    paths.extend(p for p in (ROOT/'models').rglob('*') if p.is_file())
    return {p.relative_to(ROOT).as_posix():sha256(p) for p in sorted(paths)}


def payload(features):
    return {'input_kind':'prepared_past_features','feature_schema_version':'ved-speed-1',
        'history_seconds':60,'speed_unit':'km/h','acceleration_unit':'m/s^2','time_unit':'s',
        'features':{name:None if pd.isna(value) else float(value) for name,value in features.items()}}


def validate():
    started=time.perf_counter()
    RESULTS.mkdir(parents=True,exist_ok=True)
    before=preserved_hashes()
    if footprint()+100_000_000>=10_000_000_000:
        raise RuntimeError('Day 7 storage budget exceeded')
    frames=[pq.read_table(ROOT/f'data/ml/speed/{split}.parquet',columns=list(FEATURES)).to_pandas()
            for split in ('train','validation','test')]
    feature_frame=pd.concat(frames,ignore_index=True)
    for record in feature_frame.to_dict('records'):
        PredictionRequest.model_validate(payload(record))
    prepared=payload(feature_frame.iloc[0].to_dict())
    model,_=load_model()
    expected=float(predict_features(feature_frame.iloc[:1],model)[0])
    examples=ROOT/'docs/examples'
    examples.mkdir(parents=True,exist_ok=True)
    save_json(examples/'day7_prediction_request.json',prepared)
    app=create_app()
    endpoints={}
    with TestClient(app,raise_server_exceptions=False) as client:
        calls=['/health','/ready','/fleet/overview','/vehicles?limit=3','/trips?limit=3',
            '/trends/daily?limit=3','/trends/monthly?limit=3','/fleet/powertrains',
            '/quality/summary','/ml/metrics','/ml/vehicle-errors?limit=3','/ml/features']
        for suffix in calls:
            request_started=time.perf_counter()
            response=client.get('/api/v1'+suffix)
            if response.status_code!=200:
                raise RuntimeError(f'API verification failed: {suffix}: {response.status_code}')
            if str(ROOT) in response.text or 'input_sha256' in response.text:
                raise RuntimeError('Private metadata in API response')
            endpoints[suffix]={'status':200,'runtime_seconds':time.perf_counter()-request_started,
                'response_bytes':len(response.content)}
        overview=client.get('/api/v1/fleet/overview').json()
        if (overview['observation_count'],overview['vehicle_count'],overview['trip_count'])!=(22434106,384,32552):
            raise RuntimeError('Gold overview reconciliation failed')
        vehicle=client.get('/api/v1/vehicles?limit=1').json()['items'][0]
        detail=client.get(f"/api/v1/vehicles/{vehicle['vehicle_id']}")
        if detail.status_code!=200 or detail.json()!=vehicle:
            raise RuntimeError('Vehicle detail reconciliation failed')
        trip=client.get('/api/v1/trips?limit=1').json()['items'][0]
        detail=client.get(f"/api/v1/vehicles/{trip['vehicle_id']}/trips/{trip['trip_id']}")
        if detail.status_code!=200 or detail.json()!=trip:
            raise RuntimeError('Trip composite-key reconciliation failed')
        if client.get('/api/v1/vehicles?limit=1').json()['total']!=384 or client.get('/api/v1/trips?limit=1').json()['total']!=32552:
            raise RuntimeError('Page-count reconciliation failed')
        if client.get('/api/v1/trends/daily?limit=1').json()['total']!=375 or client.get('/api/v1/trends/monthly?limit=1').json()['total']!=13:
            raise RuntimeError('Trend-count reconciliation failed')
        errors=client.get('/api/v1/ml/vehicle-errors?limit=1').json()
        if errors['total']!=50:
            raise RuntimeError('Test vehicle-error count mismatch')
        request_started=time.perf_counter()
        prediction=client.post('/api/v1/ml/predict',json=prepared)
        if prediction.status_code!=200 or not math.isclose(prediction.json()['predicted_mean_speed_kmh'],expected,abs_tol=1e-12):
            raise RuntimeError('Saved-model API inference mismatch')
        endpoints['/ml/predict']={'status':200,'runtime_seconds':time.perf_counter()-request_started,
            'response_bytes':len(prediction.content)}
        save_json(examples/'day7_prediction_response.json',prediction.json())
        schemas=client.get('/openapi.json').json()
        api_routes=len(schemas['paths'])
        before_query=app.state.analytics.query_count
        client.get('/api/v1/fleet/overview')
        client.get('/api/v1/fleet/overview')
        if app.state.analytics.query_count!=before_query:
            raise RuntimeError('Warm analytics request did not use cache')
    # Real network server, loopback only; terminate only this spawned child.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port=sock.getsockname()[1]
    log=(RESULTS/'uvicorn_smoke.log').open('w',encoding='utf-8')
    network_started=time.perf_counter()
    process=subprocess.Popen([sys.executable,'-m','uvicorn','src.api.main:app','--host','127.0.0.1',
        '--port',str(port),'--workers','1','--limit-concurrency','32','--timeout-keep-alive','5','--no-access-log'],
        cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=15) as client:
            deadline=time.perf_counter()+30
            while True:
                if process.poll() is not None:
                    raise RuntimeError('Uvicorn exited before serving health')
                try:
                    live=client.get('/api/v1/health')
                    if live.status_code==200:
                        break
                except httpx.HTTPError:
                    pass
                if time.perf_counter()>deadline:
                    raise RuntimeError('Uvicorn health startup timed out')
                time.sleep(.1)
            startup_seconds=time.perf_counter()-network_started
            for path in ('/api/v1/ready','/api/v1/fleet/overview','/api/v1/ml/metrics'):
                if client.get(path).status_code!=200:
                    raise RuntimeError('Live HTTP endpoint failed')
            network_prediction=client.post('/api/v1/ml/predict',json=prepared)
            if network_prediction.status_code!=200 or not math.isclose(network_prediction.json()['predicted_mean_speed_kmh'],expected,abs_tol=1e-12):
                raise RuntimeError('Live HTTP inference mismatch')
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        log.close()
    if preserved_hashes()!=before:
        raise RuntimeError('Earlier data, evaluations or model changed')
    result={'passed':True,'prepared_vectors_validated':len(feature_frame),'feature_count':len(FEATURES),
        'versioned_routes':api_routes,'endpoints':endpoints,'all_earlier_artifacts_unchanged':True,
        'preserved_sha256':before,'actual_model_prediction_kmh':expected,
        'api_inference_matches_model':True,'live_uvicorn_http_verified':True,
        'loopback_startup_seconds':startup_seconds,'smoke_child_terminated':process.poll() is not None,
        'total_runtime_seconds':time.perf_counter()-started,'project_bytes':footprint(),
        'versions':{name:importlib.metadata.version(name) for name in (
            'fastapi','starlette','pydantic','uvicorn','httpx','duckdb','scikit-learn','anyio')},
        'backend_code_sha256':{p.relative_to(ROOT).as_posix():sha256(p) for p in sorted((ROOT/'src/api').rglob('*.py'))},
        'startup_launcher_sha256':sha256(ROOT/'scripts/run_backend.ps1')}
    save_json(RESULTS/'actual_validation.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='preserved_sha256'},indent=2))


if __name__=='__main__':
    validate()
