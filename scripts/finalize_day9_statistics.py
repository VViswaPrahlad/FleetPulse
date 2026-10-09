"""Final Day 9 storage and artifact-preservation measurement; no ETL."""
import json
from src.analytics.build_gold import ROOT,footprint
from src.features.build_speed_dataset import save_json
from scripts.validate_day9_actual import protected

if __name__=='__main__':
    prior=json.loads((ROOT/'results/day9/protected_before.json').read_text())
    assert protected()==prior,'Earlier artifacts changed'
    size=footprint()
    assert size<10_000_000_000
    result={'project_bytes':size,'gb_decimal':size/1e9,'gib':size/2**30,
        'below_preferred_5gb':size<5_000_000_000,'preserved_files':len(prior),
        'all_earlier_artifacts_unchanged':True}
    save_json(ROOT/'results/day9/storage.json',result)
    print(json.dumps(result,indent=2))
