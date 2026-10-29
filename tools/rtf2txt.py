"""Minimal RTF -> plain text, for static reading of the mod's README.rtf.

Usage: py -3 -I tools/rtf2txt.py <in.rtf> <out.txt>
"""
import re
import sys

DESTS = {'fonttbl', 'colortbl', 'stylesheet', 'info', 'pict', 'object', 'header', 'footer',
         'listtable', 'listoverridetable', 'rsidtbl', 'themedata', 'colorschememapping',
         'datastore', 'latentstyles', 'xmlnstbl', 'generator', 'pgdsctbl', 'filetbl',
         'revtbl', 'mmathPr', 'fldinst'}
TOKEN = re.compile(r"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\(.)", re.S)


def rtf_to_text(s):
    out, stack, ignorable, i, n = [], [], False, 0, len(s)
    while i < n:
        c = s[i]
        if c == '{':
            stack.append(ignorable)
            i += 1
        elif c == '}':
            ignorable = stack.pop() if stack else False
            i += 1
        elif c == '\\':
            m = TOKEN.match(s, i)
            i = m.end()
            if m.group(1):
                w = m.group(1)
                if w in DESTS:
                    ignorable = True
                elif not ignorable:
                    if w in ('par', 'line', 'row'):
                        out.append('\n')
                    elif w in ('tab', 'cell'):
                        out.append('\t')
            elif m.group(3):
                if not ignorable:
                    out.append(bytes([int(m.group(3), 16)]).decode('cp1252', 'replace'))
            else:
                ch = m.group(4)
                if ch == '*':
                    ignorable = True
                elif not ignorable and ch in '{}\\':
                    out.append(ch)
        elif c in '\r\n':
            i += 1
        else:
            if not ignorable:
                out.append(c)
            i += 1
    return ''.join(out)


def main():
    txt = rtf_to_text(open(sys.argv[1], encoding='latin-1').read())
    with open(sys.argv[2], 'w', encoding='utf-8') as f:
        f.write(re.sub(r'\n\s*\n+', '\n\n', txt))


if __name__ == '__main__':
    main()
