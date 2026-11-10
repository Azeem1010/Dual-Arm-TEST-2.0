#!/usr/bin/env python3
"""T0 documentation check: relative links and layout statements in Markdown.

Usage: check_docs.py [REPORT.json]

Fails (exit 1) when a relative link or image in a Markdown file points to a
missing file. Statements about the zone order are listed for review only,
because history sections are allowed to quote the old layout; deciding whether
each one is current stays with the reader.

Skipped: third_party/ (upstream, not editable), build/install/log, and the
tester's copied records in docs/evidence/hardware/2026*/, whose links point
into the source repository by design.
"""
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote

REPO = Path(__file__).resolve().parents[2]
SKIP_PARTS = {'.git', 'third_party', 'build', 'install', 'log', 'node_modules', '__pycache__'}
LINK = re.compile(r'!?\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
HTML_SRC = re.compile(r'<img[^>]+src="([^"]+)"')
# Any wording of a zone order, so stale ones are seen; see COORDINATE_FRAMES.md for the current one.
LAYOUT = re.compile(r'([ABC]) ?[|｜、,/] ?([ABC]) ?[|｜、,/] ?([ABC])|Zone [ABC]|[ABC] 區\*{0,2}（[左右中]）')


def skipped(path):
    rel = path.relative_to(REPO)
    if SKIP_PARTS & set(rel.parts):
        return True
    return rel.parts[:3] == ('dual_arm_ws', 'docs', 'evidence') and len(rel.parts) > 4 \
        and rel.parts[3] == 'hardware' and rel.parts[4].startswith('2026')


def code_free(lines):
    """Yield (number, line) outside fenced code blocks."""
    fenced = False
    for number, line in enumerate(lines, 1):
        if line.lstrip().startswith('```'):
            fenced = not fenced
            continue
        if not fenced:
            yield number, line


def main():
    broken, layout = [], []
    files = []
    for directory, subdirs, names in os.walk(REPO):
        subdirs[:] = [d for d in subdirs if d not in SKIP_PARTS]
        files += [Path(directory) / n for n in names if n.endswith('.md')]
    files = sorted(p for p in files if not skipped(p))
    for path in files:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
        for number, line in code_free(lines):
            for target in LINK.findall(line) + HTML_SRC.findall(line):
                if re.match(r'^(https?:|mailto:|#)', target):
                    continue
                file_part = unquote(re.sub(r':\d+(-\d+)?$', '', target.split('#', 1)[0]))
                if file_part and not (path.parent / file_part).exists():
                    broken.append({'file': path.relative_to(REPO).as_posix(), 'line': number, 'target': target})
            if LAYOUT.search(line):
                layout.append({'file': path.relative_to(REPO).as_posix(), 'line': number, 'text': line.strip()[:200]})
    report = {'status': 'FAIL' if broken else 'PASS', 'markdown_files': len(files),
              'broken_links': broken, 'layout_statements_for_review': layout}
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for item in broken:
        print(f"BROKEN {item['file']}:{item['line']} -> {item['target']}")
    print(f"{report['status']}: {len(files)} Markdown files, {len(broken)} broken links, "
          f"{len(layout)} layout statements to review")
    return 1 if broken else 0


if __name__ == '__main__':
    sys.exit(main())
