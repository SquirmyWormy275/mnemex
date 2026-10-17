"""A fresh harness can retrieve this memory and detect stale/tampered content."""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / 'tools' / 'project_memory.py'
spec = importlib.util.spec_from_file_location('project_memory', TOOL)
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)


@pytest.fixture
def copied_memory(tmp_path):
    root = tmp_path / 'portable' / 'docs' / 'project-memory'
    shutil.copytree(memory.DEFAULT_ROOT, root)
    return root


def refresh(root):
    manifest = {'schema_version': 'mnemex.project-memory.manifest.v1', 'files': memory.inventory(root)}
    (root / 'MANIFEST.json').write_text(json.dumps(manifest), encoding='utf-8')


def test_pack_verifies_and_relocates_without_site_packages_or_django(copied_memory):
    tool = copied_memory.parents[1] / 'tools' / 'project_memory.py'
    tool.parent.mkdir()
    shutil.copyfile(TOOL, tool)
    result = subprocess.run([sys.executable, '-I', '-S', str(tool), 'verify'],
                            cwd=copied_memory.parent, capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report['status'] == 'PASS' and report['sources'] >= 47
    assert report['decisions'] >= 67
    context = subprocess.run([sys.executable, '-I', '-S', str(tool), 'context', '--topic', 'resume'],
                             capture_output=True, text=True, check=True)
    assert 'First ten minutes' in context.stdout and 'hosted backup' in context.stdout


@pytest.mark.parametrize(('query', 'expected'), [
    ('why no engine fallback', 'ECO-07'),
    ('common count start mark raw duration', 'NUM-01'),
    ('Missoula merge blocked backup recovery key', 'DEL-02'),
    ('prospective 100 ten new competitions', 'EVAL-02'),
    ('D0-12 automatic publication', 'D0-12'),
    ('source credential correction provenance', 'MNE-05'),
    ('Mark-3 ceil180 policy', 'NUM-02'),
])
def test_retrieval_finds_critical_decision_with_sources(query, expected):
    results = memory.search(memory.DEFAULT_ROOT, query, 5, False)
    assert any(item.get('id') == expected and item.get('sources') for item in results)


def test_archived_decisions_are_excluded_until_requested():
    query = 'historical only scraper JSONL canonical store retired'
    assert all(row.get('id') != 'OLD-01' for row in memory.search(memory.DEFAULT_ROOT, query, 50, False))
    assert any(row.get('id') == 'OLD-01' for row in memory.search(memory.DEFAULT_ROOT, query, 50, True))


def test_tampered_source_cannot_be_hidden_by_refreshing_manifest(copied_memory):
    source = memory.read_json(copied_memory, 'SOURCE_CATALOG.json')['sources'][0]
    path = copied_memory / source['snapshot']
    path.write_bytes(path.read_bytes() + b'\nchanged\n')
    with pytest.raises(ValueError, match='inventory/hash mismatch'):
        memory.verify(copied_memory)
    refresh(copied_memory)
    with pytest.raises(ValueError, match='Source snapshot mismatch'):
        memory.verify(copied_memory)


def test_untracked_file_and_generated_index_drift_are_detected(copied_memory):
    surprise = copied_memory / 'unreviewed.txt'
    surprise.write_text('new instructions', encoding='utf-8')
    with pytest.raises(ValueError, match='inventory/hash mismatch'):
        memory.verify(copied_memory)
    surprise.unlink()
    (copied_memory / 'DECISIONS.md').write_text('outdated index', encoding='utf-8')
    refresh(copied_memory)
    with pytest.raises(ValueError, match='Generated index drift'):
        memory.verify(copied_memory)


@pytest.mark.parametrize('bad_path', ['../outside.txt', '/outside.txt', r'..\outside.txt'])
def test_manifest_rejects_paths_outside_pack(copied_memory, bad_path):
    manifest = memory.read_json(copied_memory, 'MANIFEST.json')
    manifest['files'][bad_path] = {'bytes': 0, 'sha256': '0' * 64}
    (copied_memory / 'MANIFEST.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='Unsafe memory path'):
        memory.verify(copied_memory)


def test_symlink_cannot_import_an_external_file(copied_memory, tmp_path):
    outside = tmp_path / 'outside.txt'
    outside.write_text('external content', encoding='utf-8')
    try:
        (copied_memory / 'linked.txt').symlink_to(outside)
    except OSError:
        pytest.skip('Creating symlinks requires platform privileges')
    with pytest.raises(ValueError, match='Symlink'):
        memory.inventory(copied_memory)


def test_uncited_decision_is_rejected_even_with_refreshed_inventory(copied_memory):
    catalog = memory.read_json(copied_memory, 'DECISIONS.json')
    catalog['decisions'][0]['sources'] = ['unknown-source']
    (copied_memory / 'DECISIONS.json').write_text(json.dumps(catalog), encoding='utf-8')
    refresh(copied_memory)
    with pytest.raises(ValueError, match='Incomplete or uncited decision'):
        memory.verify(copied_memory)


def test_unknown_schema_is_not_silently_interpreted(copied_memory):
    catalog = memory.read_json(copied_memory, 'DECISIONS.json')
    catalog['schema_version'] = 'future-incompatible-schema'
    (copied_memory / 'DECISIONS.json').write_text(json.dumps(catalog), encoding='utf-8')
    refresh(copied_memory)
    with pytest.raises(ValueError, match='Unsupported memory schema'):
        memory.verify(copied_memory)


def test_uncatalogued_snapshot_cannot_be_approved_by_manifest_refresh(copied_memory):
    (copied_memory / 'snapshots' / 'uncatalogued.md').write_text('unattributed evidence', encoding='utf-8')
    refresh(copied_memory)
    with pytest.raises(ValueError, match='catalog'):
        memory.verify(copied_memory)


def test_plain_search_prints_decision_status_and_source_references(capsys):
    assert memory.main(['search', 'why no engine fallback', '--limit', '1']) == 0
    output = capsys.readouterr().out
    assert 'ECO-07' in output and 'current' in output
    assert all(source in output for source in ['S01', 'S02', 'S03', 'S24'])


def test_pack_under_symlinked_ancestor_is_portable(copied_memory, tmp_path):
    alias = tmp_path / 'workspace-link'
    try:
        alias.symlink_to(copied_memory.parents[1], target_is_directory=True)
    except OSError:
        pytest.skip('Creating symlinks requires platform privileges')
    assert memory.verify(alias / 'docs' / 'project-memory')['status'] == 'PASS'
