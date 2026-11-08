"""Generate controller-qol tuning from the FINAL built skills/skilldesc tables.

Static suggestions, not evidence of controller play. See docs/controller-support.md.
Output is a seed: never overwrite a player's active profile during an update.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'tools/data'
CATALOG = json.loads((DATA / 'controller_qol_catalog.json').read_text())['sections']
SECTIONS = ('amazon', 'sorceress', 'necromancer', 'barbarian', 'paladin',
            'druid', 'assassin', 'warlock', 'custom')


def read_table(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream, delimiter='\t'))


def scope(mod_root):
    """Match Discovery::Fingerprint(lowercase(canonical generic path + '|mxl2012'))."""
    key = str(Path(mod_root).resolve()).replace('\\', '/') + '|mxl2012'
    key = ''.join(chr(ord(c) + 32) if 'A' <= c <= 'Z' else c for c in key)
    value = 14695981039346656037
    for byte in key.encode('utf-8'):
        value = ((value ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return f'{value:016x}'


def infer(row, desc=None):
    """Return kind, aim value, targeting. Native-only skills remain toggleable."""
    on = lambda key: row.get(key, '').strip() == '1'
    server = row.get('srvdofunc', '').strip()
    missile = any(row.get(k, '').strip() for k in
                  ('srvmissile', 'srvmissilea', 'srvmissileb', 'srvmissilec'))
    if on('passive') or row.get('InGame') == '0':
        return 'passive/inactive', 'disabled', 'snap'
    if on('aura'):
        return 'aura', False, 'ground'
    if any(on(k) for k in ('TargetCorpse', 'TargetItem', 'TargetPet', 'TargetAlly')):
        return 'native-unit', False, 'snap'
    if row.get('range', '').strip() == 'h2h':
        return 'melee', False, 'snap'
    if on('warp') or server in ('27', '76'):
        return 'movement', True, 'ground'
    if row.get('summon') or row.get('pettype'):
        return 'summon', True, 'ground'
    if server in ('22', '68'):
        return 'self-area', False, 'ground'
    # Buff functions can also launch offensive missiles: keep those for review.
    if row.get('aurastate') and server in ('18', '65', '116', '124'):
        return 'self-buff', False, 'ground'
    if server in ('28', '31', '80') or row.get('lob') == '1':
        return 'area/placement', True, 'snap'
    if missile or row.get('range', '').strip() in ('rng', 'both'):
        return 'projectile', True, 'snap'
    if (desc or {}).get('descmissile1'):
        return 'projectile-description', True, 'snap'
    if row.get('auratargetstate'):
        return 'target-area', True, 'snap'
    return 'native-review', False, 'snap'


def generate(rows, descriptions, overrides):
    ids, names = {}, {}
    for row in rows:
        raw = row.get('*Id', '').strip()
        if not raw:
            continue
        number = int(raw)
        if not 0 <= number < 65535 or number in ids:
            raise ValueError(f'invalid/duplicate skill ID: {raw}')
        ids[number] = row
        names.setdefault(row['skill'], []).append(number)
    if not ids:
        raise ValueError('empty skills table')
    descs = {r['skilldesc']: r for r in descriptions}
    selected = {i for i, r in ids.items() if i > 5 and r.get('skilldesc')}
    # Catalog entries exist even if the mod omits/replaces them; clear ALL defaults.
    selected.update(map(int, CATALOG))
    if len(selected) > 1024:
        raise ValueError(f'{len(selected)} entries exceed controller-qol capacity 1024')
    entries = {}
    for number in sorted(selected):
        row = ids.get(number)
        if row and row.get('skilldesc'):
            kind, aim, target = infer(row, descs.get(row['skilldesc']))
            name = row['skill']
        else:
            kind, aim, target, name = 'absent/hidden', 'disabled', 'snap', '(no described skill)'
        entries[number] = dict(id=number, name=name, kind=kind, aim=aim, targeting=target,
                               section=CATALOG.get(str(number), 'custom'))
    for name, override in overrides.items():
        matches = names.get(name, [])
        if len(matches) != 1 or matches[0] not in entries:
            raise ValueError(f'override must match one described skill: {name}')
        if set(override) != {'aim', 'targeting', 'reason'} or not override['reason']:
            raise ValueError(f'invalid override fields: {name}')
        if not (type(override['aim']) is bool or override['aim'] == 'disabled'):
            raise ValueError(f'invalid aim: {name}')
        if override['targeting'] not in ('ground', 'snap'):
            raise ValueError(f'invalid targeting: {name}')
        entry = entries[matches[0]]
        entry.update(override)
        entry['kind'] = 'hand-override'
    lines = ['# Controller QOL skill profile, schema 2.', '# Mod: mxl2012',
             '# Generated suggestions; controller play validation pending.']
    for section in SECTIONS:
        lines += ['', f'[aim.{section}]']
        for entry in entries.values():
            if entry['section'] == section:
                lines.append(f'"{entry["id"]}" = {json.dumps(entry["aim"])}')
    lines += ['', '[aim.targeting]']
    lines += [f'"{i}" = "{e["targeting"]}"' for i, e in entries.items()]
    # Omission inherits vanilla missile tuning, including on Median replacements.
    lines += ['', '[aim.leading]']
    lines += [f'"{i}" = 0' for i in entries]
    lines += ['', '[aim.leading_max_ms]', '"39" = 600', '"45" = 600',
              '', '[aim.leading_max_tiles]', '"39" = 3', '"45" = 3']
    # Vanilla ID 151's pass-through must not accidentally affect a replacement.
    lines += ['', '[aim.whirlwind]', 'whirlwind_pass_through_enabled = false', '']
    text = '\n'.join(lines)
    if len(text.encode('utf-8')) > 65535:
        raise ValueError('profile exceeds controller-qol 65535-byte limit')
    return text, list(entries.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--excel', type=Path, default=ROOT / 'work/mod/data/global/excel')
    parser.add_argument('--overrides', type=Path, default=DATA / 'controller_skill_overrides.json')
    parser.add_argument('--out', type=Path, required=True, help='staging directory, never a live config')
    parser.add_argument('--mod-root', type=Path, help='installation mod directory, used ONLY to name the staged scope file')
    args = parser.parse_args()
    text, entries = generate(read_table(args.excel / 'skills.txt'),
                             read_table(args.excel / 'skilldesc.txt'),
                             json.loads(args.overrides.read_text(encoding='utf-8')))
    args.out.mkdir(parents=True, exist_ok=True)
    stem = scope(args.mod_root) if args.mod_root else 'mxl2012'
    (args.out / f'{stem}.overrides.toml').write_text(text, encoding='utf-8', newline='\n')
    evidence = {'schema': 1, 'source_sha256': hashlib.sha256((args.excel / 'skills.txt').read_bytes()).hexdigest(),
                'catalog_commit': 'df44457e5cfddf9149bc2f623ea5ab1b251e75bf',
                'count': len(entries), 'profile_bytes': len(text.encode('utf-8')), 'skills': entries}
    (args.out / 'mxl2012.skills.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(f'{len(entries)} skills; {evidence["profile_bytes"]} bytes -> {args.out}')


if __name__ == '__main__':
    main()
