"""Render entrypoint: process-only thread limits, one worker, PORT binding."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def start():
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[key] = '1'
    port = int(os.environ.get('PORT', '10000'))
    if not 1024 <= port <= 65535:
        raise ValueError('Invalid platform PORT')
    import uvicorn
    uvicorn.run('deploy.app:create_public_app', factory=True, host='0.0.0.0', port=port,
                workers=1, limit_concurrency=8, timeout_keep_alive=5)


if __name__ == '__main__':
    start()
