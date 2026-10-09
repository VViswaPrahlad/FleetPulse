"""Real serving-bundle validation; no deployment, upload, ETL or training."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deploy.bundle import DEFAULT, build, verify
from src.runtime import ROOT, sha256

RESULTS = ROOT / 'results/deployment'


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    first = build()
    assert build()['archive_sha256'] == first['archive_sha256'], 'Bundle is not deterministic'
    verify(DEFAULT)
    # The memory helper enumerates only our own child process tree.
    from scripts.validate_day9_actual import memory_tree, stop_child, wait
    from scripts.validate_day10_release import protected
    before = protected()
    before.update({p.relative_to(ROOT).as_posix(): sha256(p)
                   for p in (ROOT / 'results/day10').rglob('*') if p.is_file()})
    env = {**os.environ, 'PYTHONPATH': str(ROOT), 'PORT': '8011',
           'FLEETPULSE_FRONTEND_ORIGIN': 'https://fleetpulse-dashboard.invalid',
           'FLEETPULSE_SMOKE_DIST': str(ROOT / 'artifacts/deployment/frontend'),
           'FLEETPULSE_SMOKE_PUBLIC_ORIGIN': 'https://fleetpulse-api.invalid',
           'FLEETPULSE_SMOKE_API_URL': 'http://127.0.0.1:8011'}
    import httpx
    from fastapi.testclient import TestClient
    from src.api.main import create_app
    paths = ['/health', '/ready', '/fleet/overview', '/vehicles?limit=25',
             '/trips?limit=25', '/trips?limit=25&offset=25', '/vehicles?powertrain=HEV',
             '/trends/daily?limit=100', '/trends/monthly?limit=100', '/fleet/powertrains',
             '/quality/summary', '/quality/pipeline', '/ml/metrics', '/ml/cohorts',
             '/ml/cohorts?split=validation&dimension=powertrain',
             '/ml/vehicle-errors?limit=25&offset=25', '/ml/features',
             '/trips?vehicle_id=2147483647',
             '/trends/daily?start_date=2017-11-01&end_date=2017-11-30',
             '/ml/cohorts?dimension=powertrain']
    with TestClient(create_app()) as source:
        first_trip = source.get('/api/v1/trips?limit=1').json()['items'][0]
        vehicle, trip = first_trip['vehicle_id'], first_trip['trip_id']
        paths.extend([f'/vehicles/{vehicle}', f'/trips?vehicle_id={vehicle}',
                      f'/vehicles/{vehicle}/trips/{trip}'])
        expected = {path: source.get('/api/v1' + path).json() for path in paths}
    children, logs = [], []
    for port in (8011, 5181):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', port))
    started = time.perf_counter()
    try:
        for name, command, cwd in [
            ('api', [sys.executable, 'deploy/start.py'], ROOT),
            ('frontend', [shutil.which('node'), 'node_modules/vite/bin/vite.js', 'preview',
                          '--port', '5181', '--outDir', '../artifacts/deployment/frontend'], ROOT / 'dashboard')]:
            log = (RESULTS / f'{name}.log').open('w', encoding='utf-8')
            logs.append(log)
            children.append(subprocess.Popen(command, cwd=cwd, env=env, stdout=log,
                stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)))
        with httpx.Client(base_url='http://127.0.0.1:8011', trust_env=False, timeout=20) as api:
            wait(api, children[0])
            startup = time.perf_counter() - started
            for path in paths:
                response = api.get('/api/v1' + path)
                assert response.status_code == 200, (path, response.status_code)
                assert response.json() == expected[path], ('Source/bundle mismatch', path)
            for origin, allowed in [(env['FLEETPULSE_FRONTEND_ORIGIN'], True),
                                     ('http://localhost:5173', False), ('https://other.invalid', False)]:
                response = api.options('/api/v1/ml/predict', headers={
                    'Origin': origin, 'Access-Control-Request-Method': 'POST',
                    'Access-Control-Request-Headers': 'Content-Type'})
                assert (response.headers.get('access-control-allow-origin') == origin) == allowed
            example = json.loads((ROOT / 'docs/examples/day7_prediction_request.json').read_text())
            prediction = api.post('/api/v1/ml/predict', json=example)
            assert prediction.status_code == 200
            assert prediction.json()['predicted_mean_speed_kmh'] == 36.61748855856695
            invalid = api.post('/api/v1/ml/predict', json={'gps': [0, 0]})
            assert invalid.status_code == 422 and str(ROOT) not in invalid.text
            memory = memory_tree(children[0].pid)
            # Four concurrent distinct small queries, cold cache: sample working-set peak.
            cases = ['/trips?powertrain=ICE&offset=100', '/trips?powertrain=HEV&offset=100',
                     '/vehicles?powertrain=PHEV', '/trends/daily?offset=100']
            peak = memory
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(api.get, '/api/v1' + path) for path in cases]
                while not all(f.done() for f in futures):
                    sample = memory_tree(children[0].pid)
                    if sample['working_set_bytes'] > peak['working_set_bytes']:
                        peak = sample
                    time.sleep(.02)
                assert all(f.result().status_code == 200 for f in futures)
        with httpx.Client(base_url='http://127.0.0.1:5181', trust_env=False) as web:
            wait(web, children[1], '/')
        smoke = subprocess.run([shutil.which('node'), 'scripts/smoke-built.mjs', 'http://127.0.0.1:5181'],
            cwd=ROOT / 'dashboard', env=env, capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        (RESULTS / 'public_build_dom.log').write_text(smoke.stdout + smoke.stderr, encoding='utf-8')
        assert smoke.returncode == 0, 'Public-build DOM flow failed; inspect ignored log'
        dom = json.loads(smoke.stdout)
        assert dom['pages'] == 5 and all(r['origin'] == env['FLEETPULSE_SMOKE_PUBLIC_ORIGIN']
                                        for r in dom['api_requests'])
        stop_child(children[0])
        unavailable = subprocess.run([shutil.which('node'), 'scripts/smoke-built.mjs',
                'http://127.0.0.1:5181', '--unavailable'], cwd=ROOT / 'dashboard', env=env,
                capture_output=True, text=True, timeout=60,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        (RESULTS / 'public_unavailable_dom.log').write_text(
            unavailable.stdout + unavailable.stderr, encoding='utf-8')
        assert unavailable.returncode == 0, 'Public unavailable-state DOM flow failed'
        after = protected()
        after.update({p.relative_to(ROOT).as_posix(): sha256(p)
                      for p in (ROOT / 'results/day10').rglob('*') if p.is_file()})
        assert after == before, 'Original artifacts changed'
        result = {'passed': True, 'bundle': first, 'source_contracts_identical': len(paths),
                  'real_prediction_kmh': prediction.json()['predicted_mean_speed_kmh'],
                  'startup_to_health_seconds': startup, 'warm_process_tree_memory': memory,
                  'four_concurrent_query_peak_sample': peak, 'production_dom': dom,
                  'runtime_seconds': time.perf_counter() - started,
                  'public_url_verified': False, 'browser_visual_verified': False,
                  'public_unavailable_pages_checked': 5,
                  'original_files_unchanged': len(before)}
        (RESULTS / 'validation.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({key: value for key, value in result.items() if key not in ('bundle', 'production_dom')}, indent=2))
    finally:
        for child in reversed(children):
            stop_child(child)
        for log in logs:
            log.close()


if __name__ == '__main__':
    main()
