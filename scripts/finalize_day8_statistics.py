"""Measure complete project storage and save only ignored Day 8 metadata."""
import json
import os
from pathlib import Path
from src.analytics.build_gold import ROOT,footprint
from src.features.build_speed_dataset import save_json


def directory_bytes(path):
    total=0
    def fail(error):
        raise error
    for base,_,files in os.walk(path,onerror=fail):
        total+=sum((Path(base)/name).stat().st_size for name in files)
    return total


if __name__=='__main__':
    total=footprint()
    assert total<10_000_000_000,'Project storage cap exceeded'
    result={'project_bytes':total,'project_gb_decimal':total/1e9,'project_gib':total/2**30,
        'below_preferred_5gb':total<5_000_000_000,
        'directory_bytes':{name:directory_bytes(ROOT/name) for name in (
            'data','results','models','.venv','dashboard/node_modules','dashboard/dist','docs','.git')}}
    save_json(ROOT/'results/day8/storage.json',result)
    print(json.dumps(result,indent=2))
