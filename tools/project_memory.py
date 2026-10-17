#!/usr/bin/env python3
"""Offline, model-neutral project memory. Python standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / 'docs' / 'project-memory'
TOPICS = {
    'core': ['START_HERE.md', '01_VISION.md', '02_ARCHITECTURE.md'],
    'resume': ['START_HERE.md', '06_DELIVERY.md', '07_RUNBOOK.md'],
    'missoula': ['03_MISSOULA.md', '02_ARCHITECTURE.md', '07_RUNBOOK.md'],
    'numerics': ['04_NUMERICS.md', '08_HISTORY.md'],
    'mnemex': ['05_MNEMEX.md', '02_ARCHITECTURE.md'],
    'history': ['08_HISTORY.md', 'DECISIONS.md'],
    'maintenance': ['09_MEMORY_MAINTENANCE.md'],
}


def safe_file(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if not name or '\\' in name or relative.is_absolute() or '..' in relative.parts:
        raise ValueError(f'Unsafe memory path: {name!r}')
    path = root.joinpath(*relative.parts)
    if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root.parent):
        raise ValueError(f'Symlink memory path: {name!r}')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'Memory path escapes root: {name!r}')
    return path


def read_json(root: Path, name: str):
    return json.loads(safe_file(root, name).read_text(encoding='utf-8'))


def inventory(root: Path):
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Symlink in memory: {path.relative_to(root)}')
        if path.is_file() and path != root / 'MANIFEST.json':
            body = path.read_bytes()
            files[path.relative_to(root).as_posix()] = {
                'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
    return files


def rendered(root: Path):
    decisions = read_json(root, 'DECISIONS.json')['decisions']
    lines = ['# Decision register', '',
             'Generated from [DECISIONS.json](DECISIONS.json). Current instructions and',
             'contracts govern. Status is explicit; a design approval is not production activation.', '']
    for item in decisions:
        sources = ', '.join(f'[{sid}](SOURCE_INDEX.md#{sid.lower()})' for sid in item['sources'])
        lines += [f"## {item['id']}: {item['title']}", '',
                  f"Status: **{item['status']}**. Scope: {item['scope']}. Authority: {item['authority']}.", '',
                  item['decision'], '', f"Rationale: {item['rationale']}", '',
                  f"Consequences: {item['consequences']}", '', f'Sources: {sources}.', '']
    sources = ['# Source index', '',
               'Generated from [SOURCE_CATALOG.json](SOURCE_CATALOG.json). Snapshots are dated',
               'reference material; archived instructions do not override current instructions.', '',
               'Recovery receipts may be normalized to exclude HTTP/session material. Original',
               'receipt hashes remain recorded separately from stored snapshot hashes.', '']
    for item in read_json(root, 'SOURCE_CATALOG.json')['sources']:
        path = quote(item['snapshot'], safe='/')
        sources += [f"## {item['id']}", '',
                    f"[{item['repository']}: {item['original_path']}]({path})", '',
                    f"Revision: `{item['revision'] or 'owner/session or evidence record'}`.", '',
                    item['purpose_and_limits'], '',
                    f"Stored bytes: {item['bytes']}; SHA-256: `{item['sha256']}`.", '']
        if item.get('url'):
            sources += [f"[Pinned original]({item['url']})", '']
        if item.get('original_receipt_sha256'):
            sources += [f"Capture: {item['capture_kind']}; original receipt SHA-256: `{item['original_receipt_sha256']}`.", '']
    return {'DECISIONS.md': '\n'.join(lines), 'SOURCE_INDEX.md': '\n'.join(sources)}


def verify(root: Path):
    manifest = read_json(root, 'MANIFEST.json')
    if manifest.get('schema_version') != 'mnemex.project-memory.manifest.v1':
        raise ValueError('Unsupported memory manifest schema')
    for name in manifest['files']:
        safe_file(root, name)
    if inventory(root) != manifest['files']:
        raise ValueError('Memory inventory/hash mismatch; review changes before refreshing manifest')
    for name, schema in [('SOURCE_CATALOG.json', 'sources'), ('DECISIONS.json', 'decisions'),
                         ('DELIVERY_SNAPSHOT.json', 'delivery')]:
        if read_json(root, name).get('schema_version') != f'mnemex.project-memory.{schema}.v1':
            raise ValueError(f'Unsupported memory schema: {name}')
    sources = read_json(root, 'SOURCE_CATALOG.json')['sources']
    source_ids = set()
    for item in sources:
        if item['id'] in source_ids:
            raise ValueError(f"Duplicate source ID: {item['id']}")
        source_ids.add(item['id'])
        body = safe_file(root, item['snapshot']).read_bytes()
        if len(body) != item['bytes'] or hashlib.sha256(body).hexdigest() != item['sha256']:
            raise ValueError(f"Source snapshot mismatch: {item['id']}")
    decision_ids = set()
    required = {'id', 'title', 'status', 'scope', 'authority', 'decision', 'rationale', 'consequences', 'sources', 'tags'}
    for item in read_json(root, 'DECISIONS.json')['decisions']:
        if not required <= item.keys() or not item['sources'] or not set(item['sources']) <= source_ids:
            raise ValueError(f"Incomplete or uncited decision: {item.get('id')}")
        if item['id'] in decision_ids or item['status'] not in {'current', 'planned', 'superseded', 'blocked'}:
            raise ValueError(f"Duplicate/invalid decision: {item['id']}")
        decision_ids.add(item['id'])
    if not {f'D0-{i}' for i in range(1, 13)} <= decision_ids:
        raise ValueError('Owner D0 decision coverage is incomplete')
    for name, expected in rendered(root).items():
        if safe_file(root, name).read_text(encoding='utf-8') != expected:
            raise ValueError(f'Generated index drift: {name}; run render after review')
    for path in sorted(root.glob('*.md')):
        body = path.read_text(encoding='utf-8')
        if body.count('```') % 2:
            raise ValueError(f'Unclosed code fence: {path.name}')
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', body):
            target = target.strip('<>')
            parsed = urlsplit(target)
            if parsed.scheme or target.startswith('#'):
                continue
            if parsed.path and not safe_file(root, unquote(parsed.path)).is_file():
                raise ValueError(f'Broken local link: {path.name}: {target}')
    return {'status': 'PASS', 'files': len(manifest['files']),
            'sources': len(source_ids), 'decisions': len(decision_ids),
            'scope': 'inventory, source bytes, decision citations, generated indexes and curated links'}


def search(root: Path, query: str, limit: int, include_sources: bool):
    terms = set(re.findall(r'[a-z0-9]+', query.lower())) - {'the', 'a', 'an', 'of', 'in', 'is', 'and', 'why', 'to'}
    if not terms:
        return []
    candidates = []
    for item in read_json(root, 'DECISIONS.json')['decisions']:
        if item['status'] == 'superseded' and not include_sources:
            continue
        body = json.dumps(item, ensure_ascii=False)
        candidates.append({'file': 'DECISIONS.json', 'id': item['id'], 'status': item['status'],
                           'sources': item['sources'], 'text': item['title'] + '\n' + item['decision'] + '\n' + item['rationale'],
                           '_words': body})
    paths = sorted(root.glob('*.md'))
    paths = [p for p in paths if p.name not in {'DECISIONS.md', 'SOURCE_INDEX.md'}]
    if include_sources:
        paths += sorted(p for p in (root / 'snapshots').rglob('*') if p.is_file())
    for path in paths:
        body = safe_file(root, path.relative_to(root).as_posix()).read_text(encoding='utf-8')
        for paragraph in re.split(r'\n\s*\n', body):
            chunks = paragraph.splitlines() if paragraph.startswith('|') else [paragraph]
            for chunk in chunks:
                candidates.append({'file': path.relative_to(root).as_posix(), 'text': chunk,
                                   '_words': chunk, 'archived_source': 'snapshots' in path.parts})
    results = []
    for item in candidates:
        words = set(re.findall(r'[a-z0-9]+', item.pop('_words').lower()))
        count = len(terms & words)
        if count:
            item['score'] = round(count / len(terms), 4)
            results.append(item)
    return sorted(results, key=lambda x: (-x['score'], -int('id' in x), x['file'], x.get('id', '')))[:limit]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--memory-root', type=Path, default=DEFAULT_ROOT)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('verify')
    commands.add_parser('render')
    commands.add_parser('refresh-manifest')
    finder = commands.add_parser('search')
    finder.add_argument('query')
    finder.add_argument('--limit', type=int, choices=range(1, 51), default=5)
    finder.add_argument('--json', action='store_true')
    finder.add_argument('--include-sources', action='store_true')
    context = commands.add_parser('context')
    context.add_argument('--topic', choices=TOPICS, default='core')
    args = parser.parse_args(argv)
    root = args.memory_root.absolute()
    try:
        if root.is_symlink() or not root.is_dir():
            raise ValueError('Memory root must be an existing ordinary directory')
        if args.command == 'render':
            for name, body in rendered(root).items():
                safe_file(root, name).write_text(body, encoding='utf-8', newline='\n')
            print('Rendered decision and source indexes')
        elif args.command == 'refresh-manifest':
            data = {'schema_version': 'mnemex.project-memory.manifest.v1', 'files': inventory(root)}
            safe_file(root, 'MANIFEST.json').write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8', newline='\n')
            print(f"Recorded {len(data['files'])} files; inventory is not an approval signature")
        elif args.command == 'verify':
            print(json.dumps(verify(root), indent=2))
        elif args.command == 'search':
            verify(root)
            results = search(root, args.query, args.limit, args.include_sources)
            if args.json:
                print(json.dumps(results, indent=2, ensure_ascii=False))
            else:
                for item in results:
                    print(f"{item['file']} {item.get('id', '')} [score={item['score']}]\n{item['text']}\n")
        else:
            verify(root)
            for name in TOPICS[args.topic]:
                print(f'<!-- project-memory: {name} -->\n')
                print(safe_file(root, name).read_text(encoding='utf-8'))
        return 0
    except (ValueError, KeyError, OSError) as exc:
        print(f'Project memory refused: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
