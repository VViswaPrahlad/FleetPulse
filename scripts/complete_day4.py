"""Build Gold once, validate, then verify the idempotent cache."""
import json
import logging
from src.analytics.build_gold import RESULTS, run

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    result = run()
    print(json.dumps({k:v for k,v in result.items() if k not in ('inputs','bronze_hashes','config')},indent=2))
    if not result['cached']:
        (RESULTS/'gold_full_run.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    repeat = run()
    if not repeat['cached']:
        raise RuntimeError('Repeat unexpectedly missed verified cache')
    (RESULTS/'reproducibility.json').write_text(json.dumps(repeat,indent=2)+'\n',encoding='utf-8')
    print('Verified repeat:',repeat['runtime_seconds'],'seconds')
