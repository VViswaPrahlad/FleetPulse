"""Audit runtime imports, installed lock pins and official Linux wheel metadata."""
from concurrent.futures import ThreadPoolExecutor
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import sys
from urllib.request import urlopen

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import parse_wheel_filename

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.runtime import ROOT

PLATFORMS = [f'manylinux_2_{minor}_x86_64' for minor in range(17, 29)] + ['manylinux2014_x86_64']
TAGS = set(cpython_tags((3, 12), abis=['cp312'], platforms=PLATFORMS)) | set(
    compatible_tags((3, 12), interpreter='cp312', platforms=PLATFORMS))


def compatible_wheel(filename):
    if not filename.endswith('.whl'):
        return False
    return bool(parse_wheel_filename(filename)[3] & TAGS)


def locked_requirements():
    def read(name):
        return [Requirement(line) for line in (ROOT / 'deploy' / name).read_text().splitlines()
                if line and not line.startswith('#')]
    locked = {item.name.lower(): str(item.specifier).removeprefix('==')
              for item in read('requirements-runtime.lock')}
    direct = read('requirements-runtime.txt')
    assert all(item.name.lower() in locked and item.specifier.contains(locked[item.name.lower()])
               for item in direct), 'Direct pins differ from runtime lock'
    env = {**default_environment(), 'sys_platform': 'linux', 'platform_system': 'Linux',
           'platform_machine': 'x86_64', 'os_name': 'posix', 'python_version': '3.12',
           'python_full_version': '3.12.10', 'extra': ''}
    pending, required = list(direct), set()
    while pending:
        item = pending.pop()
        name = item.name.lower().replace('_', '-')
        assert name in locked and item.specifier.contains(locked[name]), 'Incomplete runtime lock'
        if name in required:
            continue
        required.add(name)
        for text in metadata.requires(name) or []:
            dependency = Requirement(text)
            if dependency.marker is None or dependency.marker.evaluate(env):
                pending.append(dependency)
    assert required == set(locked), 'Unused packages in runtime lock'
    return [f'{name}=={version}' for name, version in locked.items()]


def wheel_check(pin):
    name, version = pin.split('==')
    with urlopen(f'https://pypi.org/pypi/{name}/{version}/json', timeout=30) as response:
        release = json.load(response)
    if not SpecifierSet(release['info'].get('requires_python') or '').contains('3.12.10'):
        raise RuntimeError(f'{pin} does not support Python 3.12.10')
    compatible = [row for row in release['urls'] if compatible_wheel(row['filename'])]
    if not compatible:
        raise RuntimeError(f'No CPython 3.12 Linux wheel for {pin}')
    return {'package': name, 'version': version,
            'linux_wheel_candidates': len(compatible),
            'smallest_wheel_bytes': min(row['size'] for row in compatible)}


def main():
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[key] = '1'
    os.environ['FLEETPULSE_FRONTEND_ORIGIN'] = 'https://fleetpulse-dashboard.invalid'
    from deploy.app import create_public_app
    app = create_public_app()
    prohibited = ('pyspark', 'matplotlib', 'pytest', 'py7zr', 'httpx', 'src.ml.train_speed',
                  'src.features.build_speed_dataset', 'src.ingestion', 'src.processing')
    assert not any(name == prefix or name.startswith(prefix + '.')
                   for name in sys.modules for prefix in prohibited)
    pins = locked_requirements()
    for pin in pins:
        name, version = pin.split('==')
        assert metadata.version(name) == version
    with ThreadPoolExecutor(max_workers=4) as pool:
        wheels = list(pool.map(wheel_check, pins))
    result = {'passed': True, 'runtime_locked_packages': len(pins),
              'development_training_imports_absent': True, 'linux_wheel_metadata': wheels,
              'linux_execution_verified': False, 'model_id': app.state.model.identity()}
    destination = ROOT / 'results/deployment/runtime_audit.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'linux_wheel_metadata'}, indent=2))


if __name__ == '__main__':
    main()
