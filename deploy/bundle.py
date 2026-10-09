"""Allowlisted, deterministic serving-only artifacts. Never upload anything."""
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.runtime import ROOT, TABLES, local, sha256

DEFAULT = ROOT / 'artifacts/deployment/bundle'
FILES = tuple(f'data/gold/ved/{table}.parquet' for table in TABLES) + (
    'models/day6/hist_gradient_boosting.joblib',
    'models/day6/inference_metadata.json',
    'results/day3/silver_quality.json', 'results/day6/training_run.json',
    'results/day6/cohort_metrics.json', 'results/day6/vehicle_errors.parquet',
    'VED_LICENSE.txt')


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def artifact_path(root, name):
    """Prevent traversal/junctions from reaching original project artifacts."""
    root = local(root)
    target = root / name
    if target.is_symlink() or not target.resolve().is_relative_to(root):
        raise ValueError('Artifact path escapes the dedicated bundle')
    return target


def project(name, value):
    # Select original values only; no recalculation, imputation or invented metrics.
    if name == 'results/day3/silver_quality.json':
        return {key: value[key] for key in ('input_rows', 'retained_rows', 'excluded_rows',
                    'exclusion_reasons', 'retained_null_counts')}
    if name == 'results/day6/training_run.json':
        result = {key: value[key] for key in ('model_sha256', 'metrics',
                    'strongest_baseline', 'improvement_vs_strongest_baseline',
                    'vehicle_cluster_bootstrap')}
        result['selection'] = {key: value['selection'][key] for key in
                               ('selected_candidate', 'selected_parameters', 'random_state')}
        return result
    return value


def verify(root):
    root = local(root)
    manifest = json.loads((root / 'bundle_manifest.json').read_text())
    if set(manifest['files']) != set(FILES) or manifest['version'] != 1:
        raise ValueError('Bundle does not match serving allowlist')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual != set(FILES) | {'bundle_manifest.json'}:
        raise ValueError('Unexpected files in deployment bundle')
    for name, record in manifest['files'].items():
        path = artifact_path(root, name)
        if path.is_symlink() or path.stat().st_size != record['bytes'] or sha256(path) != record['sha256']:
            raise ValueError('Bundle file integrity mismatch')
    return manifest


def build(output=DEFAULT):
    output = local(output)
    if output != DEFAULT:
        raise ValueError('Builder writes only its dedicated generated bundle')
    output.mkdir(parents=True, exist_ok=True)
    source_manifest = json.loads((ROOT / 'data/raw/ved/manifest.json').read_text())
    manifest = {'version': 1, 'files': {}, 'dataset_source': {
        'repository': 'https://github.com/gsoh/VED', 'commit': source_manifest['commit']}}
    for name in FILES:
        source = ROOT / ('data/raw/ved/LICENSE' if name == 'VED_LICENSE.txt' else name)
        target = artifact_path(output, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith('.json') and name.startswith('results/'):
            target.write_bytes(encode(project(name, json.loads(source.read_text()))))
        else:
            shutil.copyfile(source, target)
        manifest['files'][name] = {'bytes': target.stat().st_size,
            'sha256': sha256(target), 'source_sha256': sha256(source),
            'source_path': source.relative_to(ROOT).as_posix()}
    (output / 'bundle_manifest.json').write_bytes(encode(manifest))
    verify(output)
    archive = output.parent / 'fleetpulse-runtime.zip'
    temporary = archive.with_suffix('.zip.pending')
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
        for path in sorted(output.rglob('*')):
            if not path.is_file():
                continue
            info = zipfile.ZipInfo(path.relative_to(output).as_posix(), (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zip_file.writestr(info, path.read_bytes(), compresslevel=9)
    os.replace(temporary, archive)
    with zipfile.ZipFile(archive) as zip_file:
        if zip_file.testzip() is not None:
            raise ValueError('Bundle archive integrity failure')
    return {'bundle_bytes': sum(p.stat().st_size for p in output.rglob('*') if p.is_file()),
            'archive_bytes': archive.stat().st_size, 'archive_sha256': sha256(archive),
            'files': manifest['files']}


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
