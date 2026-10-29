"""Check README and documentation links; generated paths, game asset namespaces and glob patterns are excluded."""
import argparse
from collections import Counter
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
EXCLUDED = {"bugs.md", "unported.md", "PLAN.md"}
LINK = re.compile(r'(?<!!)\[([^\]\n]*)\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+"[^"]*")?\s*\)')
CODE = re.compile(r'(?<!`)`([^`\n]+)`(?!`)')
REPO_PATH = re.compile(r'(?:\./)?(?:tools|docs|plugin|launcher|data|tests|\.github)/[\w./-]+')


def visible(text):
    """Blank fenced code while preserving offsets and line numbers."""
    lines = text.splitlines(keepends=True)
    fence = None
    for i, line in enumerate(lines):
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if match and fence is None:
            fence = match[1][0]
        elif match and match[1][0] == fence:
            fence = None
            lines[i] = re.sub(r'[^\r\n]', ' ', line)
            continue
        if fence:
            lines[i] = re.sub(r'[^\r\n]', ' ', line)
    return ''.join(lines)


def anchors(path):
    result = set()
    counts = Counter()
    lines = visible(path.read_text(encoding='utf-8')).splitlines()
    for i, line in enumerate(lines):
        match = re.match(r'^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$', line)
        title = match[1] if match else None
        if title is None and i + 1 < len(lines) and re.fullmatch(r'\s*(?:=+|-+)\s*', lines[i + 1]) and line.strip():
            title = line.strip()
        if title is not None:
            title = re.sub(r'\[([^]]+)\]\([^)]*\)', r'\1', title)
            slug = re.sub(r'[^\w\-\s]', '', title.lower()).replace(' ', '-')
            number = counts[slug]
            counts[slug] += 1
            result.add(slug + (f'-{number}' if number else ''))
    result.update(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)', '\n'.join(lines), re.I))
    return result


def findings(root, path):
    text = visible(path.read_text(encoding='utf-8'))
    out = []
    for match in LINK.finditer(text):
        target = match[2].strip('<>')
        url = urlsplit(target)
        if url.scheme or url.netloc or target.startswith('/'):
            continue
        dest = path.parent / unquote(url.path) if url.path else path
        reason = None
        if not dest.exists():
            reason = 'missing file'
        elif url.fragment and dest.is_file() and dest.suffix.lower() == '.md' and unquote(url.fragment) not in anchors(dest):
            reason = 'missing heading'
        if reason:
            out.append((text.count('\n', 0, match.start()) + 1, reason, target))
    for match in CODE.finditer(text):
        target = match[1]
        if (REPO_PATH.fullmatch(target) and not target.startswith(('data/global/', 'data/hd/', 'data/local/'))
                and not (root / target).exists()):
            out.append((text.count('\n', 0, match.start()) + 1, 'missing repo path', target))
    return sorted(out)


def documents(root):
    return [root / 'README.md'] + sorted(p for p in (root / 'docs').glob('*.md') if p.name not in EXCLUDED)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    count = 0
    for path in documents(args.root):
        for line, reason, target in findings(args.root, path):
            print(f'{path.relative_to(args.root).as_posix()}:{line}: {reason}: {target}')
            count += 1
    print(f'{count} findings')
    return int(bool(count))


if __name__ == '__main__':
    raise SystemExit(main())
