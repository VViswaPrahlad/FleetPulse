"""Check release Markdown references, Python pins, npm locks and source tracking.

Read-only checks; generated evidence stays in results/day10. External links
are listed for separate verification, not followed by this script.
"""
import importlib.metadata
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def anchors(text):
    headings = re.findall(r'^#{1,6}\s+(.+)$', text, re.MULTILINE)
    return {re.sub(r'[^\w\- ]', '', heading.lower()).replace(' ', '-') for heading in headings}


def main():
    docs = [ROOT / name for name in ['README.md', 'docs/architecture.md',
            'docs/demo_guide.md', 'docs/interview_qa.md', 'docs/day10_report.md']]
    checked, external = 0, set()
    for doc in docs:
        for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', doc.read_text(encoding='utf-8-sig')):
            if target.startswith(('http://', 'https://')):
                external.add(target)
                continue
            parsed = urlsplit(target)
            destination = (doc.parent / unquote(parsed.path)).resolve() if parsed.path else doc
            assert destination.is_relative_to(ROOT), 'Documentation link leaves project'
            assert destination.exists(), f'Broken reference: {doc.name}: {target}'
            if parsed.fragment:
                assert parsed.fragment in anchors(destination.read_text(encoding='utf-8-sig')), target
            checked += 1
    versions = {}
    for line in (ROOT / 'requirements.txt').read_text().splitlines():
        pin = re.match(r'^([\w-]+)==([^\s#]+)', line)
        if pin:
            name, wanted = pin.groups()
            actual = importlib.metadata.version(name)
            assert actual == wanted, f'{name} installed/pin mismatch'
            versions[name] = actual
    package = json.loads((ROOT / 'dashboard/package.json').read_text())
    lock = json.loads((ROOT / 'dashboard/package-lock.json').read_text())
    dependencies = {**package['dependencies'], **package['devDependencies']}
    for name, wanted in dependencies.items():
        assert lock['packages']['node_modules/' + name]['version'] == wanted, name
        section = 'dependencies' if name in package['dependencies'] else 'devDependencies'
        assert lock['packages'][''][section][name] == wanted, name
    tracked = subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).splitlines()
    ts = [name for name in tracked if name.startswith('dashboard/') and name.endswith(('.ts', '.tsx'))]
    assert any(name.endswith('.tsx') for name in ts), 'Actual TSX source is not tracked'
    attributes = (ROOT / '.gitattributes').read_text()
    assert 'linguist-' not in attributes, 'Review language overrides before release'
    result = {'passed': True, 'local_links_checked': checked, 'external_links': sorted(external),
              'installed_python_pins': versions, 'npm_direct_pins_verified': len(dependencies),
              'tracked_typescript_files': ts, 'language_overrides': False}
    destination = ROOT / 'results/day10/documentation_audit.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
