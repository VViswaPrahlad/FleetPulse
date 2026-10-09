"""Exercise the actual PowerShell launcher without execution-policy overrides."""
import json
import os
import shutil
import socket
import subprocess
import time
import httpx
from src.analytics.build_gold import ROOT
from src.features.build_speed_dataset import save_json
from scripts.validate_day9_actual import wait,memory_tree,stop_child

if __name__=='__main__':
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    env=dict(os.environ)
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
        env.pop(name,None)  # Only the launcher's own settings should take effect.
    log=(ROOT/'results/day9/launcher.log').open('w',encoding='utf-8')
    started=time.perf_counter()
    child=subprocess.Popen([shutil.which('powershell'),'-NoProfile','-File',
        str(ROOT/'scripts/run_backend.ps1'),'-Port',str(port)],cwd=ROOT,env=env,
        stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=20) as client:
            wait(client,child)
            assert client.get('/api/v1/ready').status_code==200
            example=json.loads((ROOT/'docs/examples/day7_prediction_request.json').read_text())
            response=client.post('/api/v1/ml/predict',json=example)
            assert response.status_code==200
            assert response.json()['predicted_mean_speed_kmh']==36.61748855856695
            result={'passed':True,'actual_powershell_launcher_verified':True,'execution_policy_overridden':False,
                'prediction_kmh':response.json()['predicted_mean_speed_kmh'],
                'process_tree_memory':memory_tree(child.pid),'runtime_seconds':time.perf_counter()-started}
            save_json(ROOT/'results/day9/launcher_validation.json',result)
            print(json.dumps(result,indent=2))
    finally:
        stop_child(child)
        log.close()
