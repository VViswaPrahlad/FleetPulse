"""Release checks without ETL, training or changes to prior result artifacts.

Use snapshot before tests, browser-session for temporary loopback servers,
validate for real integration, and finalize for preservation/storage checks.
All generated reports belong to ignored results/day10.
"""
import argparse
import json
import os
import socket
import subprocess
import time

import httpx

from scripts import validate_day9_actual as integration
from src.analytics.build_gold import ROOT, footprint, sha256
from src.features.build_speed_dataset import save_json

RESULTS = ROOT / 'results/day10'


def protected():
    folders = ['data/raw', 'data/bronze', 'data/silver', 'data/quarantine',
               'data/gold', 'data/ml', 'models',
               *(f'results/day{day}' for day in range(1, 10))]
    files = sorted(p for folder in folders for p in (ROOT / folder).rglob('*')
                   if p.is_file())
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in files}


def browser_session():
    """Run the real Windows launchers; never stop another process using a port."""
    for port in (8010, 5180):
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
            except OSError:
                raise RuntimeError(f'Port {port} occupied; no other process stopped') from None
    marker = RESULTS / 'stop_browser_session'
    if marker.exists():
        raise RuntimeError('Use a fresh session marker; existing session already stopped')
    children, logs, starts = [], [], []
    env = {**os.environ, 'PYTHONPATH': str(ROOT)}
    try:
        for name in ('backend', 'frontend'):
            log = (RESULTS / f'visual_{name}.log').open('w', encoding='utf-8')
            logs.append(log)
            starts.append(time.perf_counter())
            children.append(subprocess.Popen(
                ['powershell', '-NoProfile', '-File', f'scripts/run_{name}.ps1',
                 '-Port', '8010' if name == 'backend' else '5180',
                 *([] if name == 'backend' else ['-BackendPort', '8010'])],
                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)))
        with httpx.Client(base_url='http://127.0.0.1:8010', trust_env=False, timeout=20) as api:
            integration.wait(api, children[0])
            backend_seconds = time.perf_counter() - starts[0]
            assert api.get('/api/v1/ready').status_code == 200
        with httpx.Client(base_url='http://127.0.0.1:5180', trust_env=False, timeout=20) as web:
            integration.wait(web, children[1], '/')
            frontend_seconds = time.perf_counter() - starts[1]
            assert web.get('/api/v1/fleet/overview').status_code == 200
        save_json(RESULTS / 'launcher_startup.json', {
            'backend_health_seconds': backend_seconds,
            'frontend_html_seconds': frontend_seconds,
            'concurrent_launcher_spawn': True, 'readiness_passed': True,
            'visual_verified': False})
        print('Both loopback launchers ready: 8010 / 5180', flush=True)
        deadline = time.monotonic() + 1200
        while not marker.exists() and time.monotonic() < deadline:
            if any(child.poll() is not None for child in children):
                raise RuntimeError('Own server stopped during browser session')
            time.sleep(.25)
    finally:
        for child in reversed(children):
            integration.stop_child(child)
        for log in logs:
            log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['snapshot', 'browser-session', 'validate', 'finalize'])
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    if args.action == 'snapshot':
        snapshot = RESULTS / 'release_protected_before.json'
        if snapshot.exists():
            raise RuntimeError('Do not overwrite the pre-release preservation snapshot')
        hashes = protected()
        save_json(snapshot, hashes)
        print(f'Protected {len(hashes)} existing artifact files')
    elif args.action == 'browser-session':
        browser_session()
    elif args.action == 'validate':
        # Reuse the existing reconciliation/security/DOM harness, redirecting all
        # reports and expanding preservation to quarantine and Day 9 results.
        integration.RESULTS = RESULTS
        integration.protected = protected
        integration.validate(api_port=8010, web_port=5180)
    else:
        before = json.loads((RESULTS / 'release_protected_before.json').read_text())
        assert protected() == before, 'Prior data/model/result artifacts changed'
        result = {'protected_files_unchanged': len(before), 'project_bytes': footprint()}
        save_json(RESULTS / 'storage.json', result)
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
