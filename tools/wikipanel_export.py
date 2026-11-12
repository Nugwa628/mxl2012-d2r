"""Build the offline wiki table, without importing any live-wiki client.

Generated Median text stays in work/; the prose snapshot is credited in NOTICE.
MXL_WIKI_PAGES and MXL_WIKI_LAZ optionally override the checked-in prose inputs.
The table describes the build it ships in. A nonempty Unreleased section only prints a note (unreleased_pending).
"""
import argparse
import copy
from collections import Counter
from dataclasses import dataclass, field
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: F401,E402
import localconfig  # noqa: F401,E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'work/mod/data/mxl2012-wiki/wiki.tsv'
CATEGORIES = (('uniq', 'Uniques'), ('set', 'Sets'), ('rw', 'Runewords'), ('gemw', 'Gemwords'),
              ('base', 'Base items'), ('cube', 'Cube recipes'), ('mon', 'Monsters'),
              ('skill', 'Skills'), ('uber', 'Ubers'), ('page', 'Pages'))
COLOURS = set('white grey blue gold green orange red yellow purple tan'.split())
SKIP = {'Main_Page': 'website navigation', 'Installation_of_the_wiki': 'website administration',
        'D2RLoader':'software setup outside the game', 'Installation':'software setup outside the game',
        'Plugins':'software setup outside the game', 'Port_changes':'port implementation and release history'}


def clean(value):
    return ' '.join(re.sub(r'(?:ÿc|\ue07e).', '', str(value)).split())


@dataclass
class Entry:
    category: str
    name: str
    subtitle: str
    lines: list = field(default_factory=list)
    links: list = field(default_factory=list)

    def add(self, text, colour='white'):
        # A stat string may carry several real display lines.
        for line in str(text).splitlines() or ['']:
            self.lines.append((colour if colour in COLOURS else 'blue', clean(line)))


def templates(text):
    """Yield balanced outer template calls, including nested calls in parameter values."""
    start, depth, i = 0, 0, 0
    while i < len(text) - 1:
        pair = text[i:i+2]
        if pair == '{{':
            if depth == 0:
                start = i
            depth += 1
            i += 2
        elif pair == '}}' and depth:
            depth -= 1
            i += 2
            if depth == 0:
                yield start, i, text[start+2:i-2]
        else:
            i += 1


def params(call):
    # Pipes within nested templates or links do not separate parameters.
    parts, current, stack, i = [], [], [], 0
    while i < len(call):
        pair = call[i:i+2]
        if pair in {'{{', '[['}:
            stack.append(pair)
            current.append(pair)
            i += 2
        elif stack and pair == ('}}' if stack[-1] == '{{' else ']]'):
            stack.pop()
            current.append(pair)
            i += 2
        elif call[i] == '|' and not stack:
            parts.append(''.join(current))
            current = []
            i += 1
        else:
            current.append(call[i])
            i += 1
    parts.append(''.join(current))
    fields = {}
    positional = 0
    for part in parts[1:]:
        if '=' in part:
            key, value = part.split('=', 1)
            fields[key.strip().lower()] = value.strip().replace('{{!}}', '|')
        else:
            positional += 1
            fields[str(positional)] = part.strip()
    return parts[0].strip().lower(), fields


def markup(text):
    """Return display lines and raw link targets. Fixtures use original, non-Median prose."""
    links = []
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    for start, end, call in reversed(list(templates(text))):
        kind, fields = params(call)
        keep = []
        if kind == 'cube recipe':
            keep = ['| ' + ' || '.join(fields.get(key, '').replace('\n', '; ')
                                      for key in ('recipe', 'inputs', 'output', 'notes'))]
        elif kind in {'uber', 'item', 'notice', 'note', 'warning', 'port note', 'port_note'}:
            for key, value in fields.items():
                if key in {'name', 'location', 'reward', 'summon', 'notes', 'meta', 'stats', 'flavour', 'text', '1',
                           'hatred', 'terror', 'destruction', 'difficulty', 'setbonus', 'fullset', 'lvlreq',
                           'base', 'type', 'footer'}:
                    keep.append((key.title() + ': ' if key not in {'text', '1', 'stats', 'flavour'} else '') +
                                value.replace('\n', '\n\n'))
            if not fields and '|' in call:
                keep = [call.split('|', 1)[1]]
        text = text[:start] + '\n\n' + '\n\n'.join(keep) + '\n\n' + text[end:]

    def link(m):
        target, _, label = m.group(1).partition('|')
        if target.lower().startswith(('file:', 'image:', 'category:')):
            return ''
        links.append(target.split('#')[0].replace('_', ' '))
        return label or target.split('#')[-1].replace('_', ' ')

    text = re.sub(r'\[\[([^\]]+)\]\]', link, text)
    text = re.sub(r'\[https?://[^\s\]]+\s*([^\]]*)\]', r'\1', text)
    text = re.sub(r'<br\s*/?>|</p>|</div>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text).replace("'''", '').replace("''", '')
    out, paragraph, row = [], [], []
    hidden_columns = set()

    def flush():
        if paragraph:
            out.append(('white', clean(' '.join(paragraph))))
            paragraph.clear()

    def flush_row():
        if row:
            out.append(('white', ' | '.join(cell for i, cell in enumerate(row) if i not in hidden_columns)))
            row.clear()

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(('{|', '|-', '|}')):
            flush(); flush_row()
            if line.startswith('{|'):
                hidden_columns.clear()
        elif line.startswith(('|', '!')):
            flush()
            cells = [clean(re.sub(r'^.*?\|\s*', '', cell) if re.match(r'^(?:style|rowspan|colspan|class)=', cell.strip()) else cell)
                     for cell in re.split(r'\|\||!!', line[1:])]
            if line.startswith('!'):
                hidden_columns.update(len(row)+i for i, cell in enumerate(cells) if cell.lower() == 'rows')
            row.extend(cells)
        elif not line:
            flush(); flush_row()
        elif re.match(r'^=+.*=+$', line):
            flush(); flush_row()
            out.append(('gold', clean(line.strip('='))))
        elif line.startswith(('*', '#', ';', ':')):
            flush(); flush_row()
            out.append(('white', '- ' + clean(line.lstrip('*#;:'))))
        else:
            flush_row()
            paragraph.append(line)
    flush(); flush_row()
    return [(c, t) for c, t in out if t], links


def unreleased_pending(changelog):
    """True when CHANGELOG has entries under Unreleased: a build of this tree then describes features not yet released."""
    section = re.search(r'^## Unreleased\s*\n(.*?)(?=^## |\Z)', changelog, re.M | re.S)
    return bool(section and section.group(1).strip())


def external(env, suffix):
    return Path(os.environ.get(env) or ROOT / suffix)


def generate(laz_path):
    for module in ('items', 'setwords', 'bases', 'cube', 'monsters'):
        subprocess.run([sys.executable, str(ROOT / 'tools/wiki' / (module + '.py'))], check=True, cwd=ROOT)
    # Use local cached Laz prose only. No fetch, network client or login helper is called.
    sys.path.insert(0, str(ROOT / 'tools/wiki'))
    import laz
    import skills
    laz.LAZ = laz_path
    old = sys.argv
    try:
        sys.argv = ['skills.py']
        skills.main()
    finally:
        sys.argv = old
    result = {name: json.loads((ROOT / 'work/wiki' / (name + '.json')).read_text('utf-8'))
            for name in ('uniques', 'sets', 'runewords', 'gemwords', 'bases', 'cube', 'monsters', 'skills')}
    import items
    import setwords
    built = items.Data()
    rows, _, _ = setwords.word_rows()
    for r in result['runewords']:
        r['sequences'] = [[setwords.rune_name(built, code) for code in setwords.runes_of(row)]
                          for row in rows[r['key']]]
    return result


def tooltip_base(base, stats):
    """Apply local item stats to a non-ethereal base; preserve rolled ranges."""
    b = copy.deepcopy(base)
    values = {s['stat']: (s['lo'], s['hi']) for s in stats}

    def val(name, index):
        return values.get(name, (0, 0))[index]

    for kind, pair in b.get('damage', {}).items():
        # Damage endpoints and modifier rolls vary independently.
        prefix = 'secondary_' if kind == 'two' else ''
        b['damage'][kind] = [max(1, pair[j] * (100 + val('item_maxdamage_percent', j)) // 100 +
                                      val(prefix + ('mindamage' if j == 0 else 'maxdamage'), j)) for j in (0, 1)]
    if 'defense' in b:
        pair = b['defense']
        enhanced = values.get('item_armor_percent', (0, 0))
        b['defense'] = [max(0, (pair[1] + 1 if any(enhanced) else pair[j]) *
                               (100 + enhanced[j]) // 100 + val('armorclass', j)) for j in (0, 1)]
    for req in ('reqstr', 'reqdex'):
        b[req] = max(0, b.get(req, 0) * (100 + val('item_req_percent', 0)) // 100)
    b['durability'] = max(0, b.get('durability', 0) + val('maxdurability', 0))
    if val('item_indesctructible', 0):
        b['durability'] = 0
    return b


CATEGORY_GUIDES = {'Horadric_Cube':'Cube', 'Base_items':'Base items', 'Runewords':'Runewords',
                   'Set_items':'Sets', 'Unique_items':'Uniques', 'Monsters':'Monsters'}


def guide_prose(stem, text):
    """Keep category introductions and rules; the category owns its member list."""
    # Preserve any hand-written prose after a generated listing as well as before.
    text = re.sub(r'<!-- generated\b.*?-->.*?<!-- end of generated part -->', '', text, flags=re.S)
    text = re.sub(r'\bThe tables below\b.*?(?=\n\s*\n|\Z)', '', text, flags=re.S)
    # Queries are already invisible to markup(), but their empty headings remain.
    # Handle inline/static tables as well, without changing the source pages.
    text = re.sub(r'\{\|.*?\|\}', '', text, flags=re.S)
    for start,end,call in reversed(list(templates(text))):
        kind,_ = params(call)
        if kind in {'cube recipe','item','base','runeword','monster'}:
            text = text[:start]+text[end:]
    text = re.sub(r'Monsters are grouped into families:.*?(?=\n\s*\n|\Z)', '', text, flags=re.S)
    text = text.replace('== Reading the monster pages ==','== Monster levels and resistances ==')
    text = text.replace('== How to read the tables ==','== How recipes work ==')
    lines, links = markup(text)
    # A query-only section has no explanatory prose of its own.
    lines = [(c,t) for i,(c,t) in enumerate(lines) if c!='gold' or
             i+1<len(lines) and lines[i+1][0]!='gold']
    category = CATEGORY_GUIDES[stem]
    lines.append(('white','Look in the '+category+' category for '+('recipes.' if stem=='Horadric_Cube' else 'individual entries.')))
    return lines, links


def entries(data, pages, laz_path=None):
    out = []
    bases = {r['code']: r for r in data['bases']}
    # Same renderer as the wiki, but local damage/defense and requirement stats
    # must also be applied to the base section of a unique or set tooltip.
    sys.path.insert(0, str(ROOT / 'tools/wiki'))
    import items
    import bases as base_module
    import wikipanel_player as player
    source = player.Sources(data)
    original = data
    data = dict(data, uniques=source.uniques, cube=[], monsters=[],
                skills=player.player_skills(source, laz_path or external('MXL_WIKI_LAZ', 'tools/wiki/class-texts')))
    item_data = items.Data()

    def item(r, category, quality):
        e = Entry(category, r['name'], f"{quality} {source.label(r)}, level {r['lvlreq']}")
        e.add(r['name'], 'green' if category == 'set' else 'gold')
        e.add(r['base_name'], 'grey')
        b = bases.get(r['base_code'])
        if b:
            stats, _ = items.item_stats(item_data, r.get('props', []))
            adjusted = tooltip_base(b, stats)
            for line in base_module.meta_lines(item_data, adjusted):
                e.add(line, 'grey')
            if b.get('class'):
                e.add(b['class'], 'white')
        if r['lvlreq']:
            e.add(f"Required Level: {r['lvlreq']}", 'white')
        for i, line in enumerate(r['lines']):
            colours = r.get('colours', [])
            e.add(line, (colours[i] if i < len(colours) else None) or 'blue')
        for line in r.get('flavour', []):
            e.add(line, 'gold')
        for bonus in r.get('bonus', []):
            for line in bonus['lines']:
                e.add(f"{line} ({bonus['items']} Items)", 'green')
        return e

    cornerstone = [r for r in data['uniques'] if r['name'] == 'Cornerstone of the World']
    out.extend(item(r, 'uniq', 'Unique') for r in data['uniques'] if r not in cornerstone)
    if cornerstone:
        e = Entry('uniq', 'Cornerstone of the World', 'Unique Jewel')
        e.add(e.name, 'gold')
        e.add('Jewel', 'grey')
        e.add('Each jewel grants one of the following skills.', 'white')
        by_class = {}
        for r in cornerstone:
            for prop, par, lo, hi in r['props']:
                if prop == 'oskill' and str(par) in source.skill_names:
                    row = next((v for v in source.skillrows.values() if str(items.num(v.get('*Id'))) == str(par)), {})
                    cls = player.CLASSES.get(row.get('charclass'), 'Other skills')
                    skill = source.skill_names[str(par)]
                    by_class.setdefault(cls, set()).add((skill, lo, hi))
                    e.links.append(skill)
        for cls, grants in sorted(by_class.items()):
            e.add(cls, 'gold')
            for skill, lo, hi in sorted(grants):
                e.add(f'+{lo}' + (f'-{hi}' if hi != lo else '') + ' to ' + skill, 'blue')
        # Keep shared tooltip requirements and properties, excluding the variable skill.
        template = item(cornerstone[0], 'uniq', 'Unique')
        skill_name = next((source.skill_names.get(str(q[1]), '') for q in cornerstone[0]['props'] if q[0]=='oskill'), '')
        e.lines[2:2] = [line for line in template.lines[2:] if not skill_name or skill_name not in line[1]]
        out.append(e)
    for r in data['sets']:
        e = Entry('set', r['name'], f"Set, {len(r['items'])} items")
        for piece in r['items']:
            e.lines.extend(item(piece, 'set', 'Set').lines)
            e.add('')
        for b in r['bonus']:
            for line in b['lines']:
                e.add(f"{line} ({b['items']} Items)", 'green')
        e.add('Full set bonuses', 'gold')
        for line in r['full']:
            e.add(line, 'green')
        out.append(e)
    for r in data['runewords']:
        e = Entry('rw', r['name'], f"Runeword, level {r['lvlreq']}")
        e.add(r['name'], 'gold')
        for sequence in r.get('sequences', [r['rune_names']]):
            e.add(' + '.join(sequence), 'white')
        e.add('Allowed bases: ' + ', '.join(r['itypes']), 'grey')
        e.add('Sockets: ' + ', '.join(map(str, r['sockets'])), 'grey')
        if r['etypes']:
            e.add('Excluded bases: ' + ', '.join(r['etypes']), 'grey')
        for line in r['lines']:
            e.add(line, 'blue')
        out.append(e)
    for r in data['gemwords']:
        e = Entry('gemw', r['gem_name'], f"Gemword, level {r['lvlreq']}")
        e.add(r['word'], 'gold')
        for kind in r['kinds']:
            e.add('Allowed bases: ' + ', '.join(kind['itypes']), 'grey')
            if kind['etypes']:
                e.add('Excluded bases: ' + ', '.join(kind['etypes']), 'grey')
            for count in kind['counts']:
                e.add(' + '.join([r['gem_name']] * count['sockets']), 'gold')
                for line in count['lines']:
                    e.add(line, 'blue')
        out.append(e)
    for r in data['bases']:
        if r['code'] not in source.tokens:
            continue
        e = Entry('base', r['name'], f"Base item, level {r['lvlreq']}")
        e.add(r['name'])
        for line in r['meta']:
            e.add(line, 'grey')
        e.add(f"Required Level: {r['lvlreq']}")
        e.add(f"Maximum sockets: {r['sockets']}", 'grey')
        if r.get('class'):
            e.add(r['class'])
        out.append(e)
    for r in data['skills']:
        e = Entry('skill', r['name'], f"{r['class']}, {r['tree']}, level {r['reqlevel']}" if r.get('class') else 'Item skill')
        e.add(r['name'], 'gold')
        for key in ('flavour', 'effect'):
            if r.get('laz', {}).get(key):
                e.add(r['laz'][key])
        for line in r['description']:
            e.add(line)
        if r.get("class"):
            e.add(f"Maximum skill level: {r.get('hard_cap') or r['maxlvl']}")
        for key in ('prereqs', 'synergies'):
            if r[key]:
                e.add(key.title() + ': ' + ', '.join(r[key]))
                e.links.extend(r[key])
        for line in r['lines']:
            if 'values' in line:
                for level, value in zip(r['levels'], line['values']):
                    if value:
                        e.add(f'Level {level}: {value}')
            else:
                if line.get('text'):
                    e.add(line['text'])
            if line.get('note'):
                e.add(line['note'], 'grey')
        out.append(e)
    recipe_entries = player.recipes(source.recipes, Entry)
    out.extend(recipe_entries)
    out.extend(player.monster_entries(original['monsters'], source, Entry))
    skipped = []
    for path in sorted(pages.rglob('*.wiki')):
        if path.parent != pages or path.stem in SKIP:
            skipped.append((path.relative_to(pages).as_posix(), SKIP.get(path.stem, 'website template/module/interface')))
            continue
        text = path.read_text('utf-8')
        title = path.stem.replace('_', ' ')
        if path.stem in CATEGORY_GUIDES:
            lines, links = guide_prose(path.stem,text)
        else:
            lines, links = markup(text)
        if lines:
            out.append(Entry('page', title, 'Guide', lines, links))
        # Include prose following each Uber call, up to the next peer heading.
        for start, end, call in templates(text):
            kind, fields = params(call)
            if kind != 'uber' or not fields.get('name'):
                continue
            e = Entry('uber', fields['name'], fields.get('difficulty', 'Uberquest'))
            for key, value in fields.items():
                if key != 'name':
                    value_lines, value_links = markup(value)
                    e.links.extend(value_links)
                    e.add(key.title() + ': ' + ' '.join(t for _, t in value_lines),
                          'gold' if key in {'hatred', 'terror', 'destruction'} else 'white')
            stop = re.search(r'^==[^=].*?==\s*$', text[end:], re.M)
            extra, targets = markup(text[end:end+stop.start()] if stop else text[end:])
            e.lines.extend(extra)
            e.links += targets + [title, fields.get('reward', '')]
            out.append(e)
    out, dropped = player.finish(out, source, Entry)
    audit = {'dropped': dropped, 'rejected_uniques': sorted(set(source.rejected)),
             'retained_unique_keys': sorted({r['key'] for r in source.uniques}),
             'reachable_recipe_count': len(source.recipes),
             'cornerstone_variants': len(cornerstone)}
    from wikipanel_families import orb_members
    def identity(m):
        return m['name'],m['description'],tuple(sorted(m['recipes']))
    selected = {identity(m):m for m in orb_members([r for r in source.recipes if r.get('orb')])}
    # A definition with no source may still be the same player-visible orb as an
    # obtainable definition. Record that alias only after comparing all effects;
    # it adds no display member, effect or source claim.
    audit['orb_members'] = [dict({k:v for k,v in m.items() if k!='recipes'},
                                obtainable_codes=selected[identity(m)]['codes'])
                           for m in orb_members([r for r in original['cube'] if r.get('orb') and not r.get('decoy')])
                           if identity(m) in selected]
    (ROOT / 'work/wiki/player-audit.json').write_text(json.dumps(audit, indent=2) + '\n', 'utf-8')
    return out, skipped


def serialize(entries):
    repeated = [key for key,n in Counter((e.category,clean(e.name).casefold()) for e in entries).items() if n>1]
    if repeated:
        raise ValueError('Repeated entry names: ' + repr(repeated))
    lines = ['V\t1'] + ['\t'.join(('C', *category)) for category in CATEGORIES]
    names = {clean(e.name).casefold(): clean(e.name) for e in entries}
    for category, _ in CATEGORIES:
        for e in sorted((e for e in entries if e.category == category), key=lambda e: (clean(e.name).casefold(), e.subtitle, e.lines)):
            name, subtitle = clean(e.name), clean(e.subtitle)
            search = clean(' '.join([name, subtitle] + [t for _, t in e.lines])).lower()
            lines.append('\t'.join(('E', category, name, subtitle, search)))
            lines.extend('\t'.join(('L', colour, clean(text))) for colour, text in (e.lines or [('white', name)]))
            targets = {names[t.casefold()] for raw in e.links if (t := clean(raw)) and t.casefold() in names}
            lines.extend('K\t' + target for target in sorted(targets))
    return ('\n'.join(lines) + '\n').encode('utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=OUT)
    ap.add_argument('--pages', type=Path, default=external('MXL_WIKI_PAGES', 'tools/wiki/pages'))
    ap.add_argument('--laz', type=Path, default=external('MXL_WIKI_LAZ', 'tools/wiki/class-texts'))
    args = ap.parse_args()
    if unreleased_pending((ROOT / 'CHANGELOG.md').read_text('utf-8')):
        print('wikipanel_export: CHANGELOG has Unreleased entries; the table describes this tree, not the last release')
    if not args.pages.is_dir() or not args.laz.is_dir():
        ap.error('missing wiki prose inputs: restore tools/wiki/pages and tools/wiki/class-texts, or set MXL_WIKI_PAGES and MXL_WIKI_LAZ')
    data = generate(args.laz)
    result, skipped = entries(data, args.pages, args.laz)
    content = serialize(result)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(content)
    report = {'counts': dict(Counter(e.category for e in result)), 'bytes': len(content), 'skipped': skipped,
              'source_counts': {k: len(v) for k, v in data.items()}}
    (ROOT / 'work/wiki/panel-report.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
    print(json.dumps(report, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
