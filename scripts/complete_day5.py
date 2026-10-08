"""Generate Day 5 outputs and verify byte reproducibility plus cache behavior."""
import argparse
import json
import logging

from src.features.build_speed_dataset import RESULTS,run,save_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-fresh',action='store_true',help='Explicit fresh repeat to verify outputs')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    path=RESULTS/'dataset_manifest.json'
    previous=json.loads(path.read_text()) if path.exists() else None
    result=run(force=args.verify_fresh)
    if not result['cached']:
        save_json(RESULTS/'full_run.json',result)
    reproducibility={'fresh_repeat_requested':args.verify_fresh}
    if previous is not None and args.verify_fresh:
        if previous['outputs']!=result['outputs']:
            raise RuntimeError('Fresh ML output hashes differ')
        save_json(RESULTS/'first_run.json',previous)
        reproducibility['fresh_output_bytes_identical']=True
        reproducibility['matched_output_files']=len(result['outputs'])
    repeat=run()
    if not repeat['cached']:
        raise RuntimeError('Verified cache unexpectedly missed')
    reproducibility['cache_repeat']=repeat
    save_json(RESULTS/'reproducibility.json',reproducibility)
    print(json.dumps({k:v for k,v in result.items() if k not in ('inputs','outputs','config')},indent=2))
    print(json.dumps(reproducibility,indent=2))


if __name__=='__main__':
    main()
