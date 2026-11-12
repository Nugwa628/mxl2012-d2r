"""Compact shared-method cube families. Displayed effects come from built data."""
from collections import defaultdict
import re


def family_name(r):
    section = r['section']
    if section == 'Mystic Orbs':
        if r['family'].lower() == 'full honorifics':
            return 'Create an honorific item'
        reagent = r['inputs'][1]
        if r.get('orb',{}).get('name',reagent) == 'Mystic Orb':
            return 'Mystic Orbs'
        return 'Trophies' if reagent.endswith(' Trophy') else 'Unique Mystic Orbs'
    if section == 'Gems and runes':
        return 'Runes' if 'rune' in r['family'].lower() else 'Upgrade gems'
    if section == 'Alchemy':
        return 'Alchemy'
    if r['family'].lower().startswith('reroll:'):
        return 'Reroll an item'
    if r['family'].lower().startswith('upgrade and reroll:'):
        return 'Improve item quality'
    if r['family'].lower().startswith(('enchant', 'gem shatter')):
        return 'Make a magic or rare item'
    if section == 'Disenchanting' and r['family'].startswith('disenchant'):
        return 'Disenchant items'
    return ''


def kind(text):
    text = re.sub(r'^any ', '', text)
    text = re.sub(r'\s*\([^)]*\)', '', text).lower()
    return {'armor':'armour', 'missile':'quiver'}.get(text, text)


def effects(r):
    return tuple(t for o in r['outputs'] for t in o.get('mods', [])
                 if not re.fullmatch(r'\+\d+ Required Level', t))


def doubled(text):
    """Honorific modifiers double; proc skill levels and poison duration do not."""
    protected = []
    def hold(m):
        protected.append(m[0])
        return '\x00' + chr(65 + len(protected)-1) + '\x00'
    text = re.sub(r'(?<=cast level )\d+|\d+(?:\.\d+)?(?= seconds?\b)', hold, text)
    text = re.sub(r'[+-]?\d+(?:\.\d+)?',
                  lambda m: ('+' if m[0].startswith('+') else '') + format(float(m[0])*2, 'g'), text)
    for i, value in enumerate(protected):
        text = text.replace('\x00'+chr(65+i)+'\x00', value)
    return text


def member(e, name, variants):
    """Keep one member line when short; otherwise put compact effects below it."""
    variants = sorted(set(variants))
    text = name + ': ' + '; '.join(variants)
    if len(text) <= 260:
        e.add(text, 'blue')
    else:
        e.add(name, 'gold')
        for variant in variants:
            # Split on effect boundaries, never inside a tooltip phrase.
            line = ''
            for part in variant.split('; '):
                if line and len(line)+len(part)>220:
                    e.add(line, 'blue')
                    line = ''
                line += ('; ' if line else '') + part
            if line:
                e.add(line, 'blue')


def orb_members(rows):
    """An identity needs both the exact game description and all recipe effects.

    Item codes are provenance only. No editor name, price or source enters this
    comparison. The returned code-to-member relation is also written to the audit.
    """
    by_code = {}
    for r in rows:
        orb = r['orb']
        code = orb['code']
        value = by_code.setdefault(code,dict(orb, recipes=set()))
        if (value['name'],value['description']) != (orb['name'],orb['description']):
            raise ValueError('Inconsistent orb game strings: '+code)
        condition = r.get('condition','')
        if condition not in ('','honorific items only'):
            raise ValueError('Unexpected orb condition: '+condition)
        value['recipes'].add((kind(r['inputs'][0]),condition,
                              tuple(t for o in r['outputs'] for t in o.get('mods',[]))))
    groups = {}
    for code, orb in sorted(by_code.items()):
        signature = orb['description'], tuple(sorted(orb['recipes']))
        member = groups.setdefault(signature, dict(name=orb['name'],description=orb['description'],
                                                   recipes=orb['recipes'],codes=[]))
        if member['name'] != orb['name']:
            raise ValueError('Orb description and effects have conflicting game names')
        member['codes'].append(code)
    return sorted(groups.values(), key=lambda x:(x['name'],x['description'],sorted(x['recipes'])))


def orb_family(name, rows, Entry):
    e = Entry('cube', name, 'Mystic Orbs')
    e.add('Cube one orb with the item to add its modifiers. The orb is consumed; the item keeps its other modifiers.')
    e.add('Use only the item kinds listed below. Weapons and armour must be non-ethereal.')
    costs = {t for r in rows for o in r['outputs'] for t in o.get('mods', []) if re.fullmatch(r'\+\d+ Required Level', t)}
    if len(costs) != 1:
        raise ValueError('Orb family needs a single shared required-level cost: '+name)
    e.add('Each use adds ' + next(iter(costs)) + '.', 'white')
    e.add('Listed effects are for non-honorific items unless stated otherwise. Honorific items double these modifiers at the same required-level cost; proc skill levels, poison duration and nonnumeric effects stay the same.')
    for orb in orb_members(rows):
        kinds = defaultdict(dict)
        for item_kind,condition,mods in orb['recipes']:
            mode = 'honorific' if condition else 'other'
            value = tuple(t for t in mods if not re.fullmatch(r'\+\d+ Required Level',t))
            if mode in kinds[item_kind] and kinds[item_kind][mode] != value:
                raise ValueError('Conflicting orb effects for '+orb['name'])
            kinds[item_kind][mode] = value
        variants = defaultdict(set)
        for item_kind, modes in kinds.items():
            normal, honorific = modes.get('other'), modes.get('honorific')
            if normal is not None:
                variants['; '.join(normal)].add(item_kind)
            if honorific is not None and (normal is None or tuple(doubled(t) for t in normal) != honorific):
                variants['; '.join(honorific)].add(item_kind+' (honorific only)')
        # The full description remains in the identity/audit. A member's label
        # omits only the shared cubing instruction and required-level cost.
        description = '; '.join(t.strip() for t in orb['description'].splitlines()
                                if t.strip() and not t.startswith('Cube ') and
                                not re.fullmatch(r'\+\d+ Required Level',t))
        label = description if orb['name']=='Mystic Orb' else orb['name']+': '+description
        if not description:
            raise ValueError('Orb has no distinguishing description: '+orb['name'])
        # Exactly one member line, so every source code has one unambiguous home.
        if len(variants) == 1 and next(iter(variants)) == description:
            # The item's own text already is the effect: say it once, then the item kinds it works on.
            e.add(label+' ('+' / '.join(sorted(next(iter(variants.values()))))+')', 'blue')
            continue
        e.add(label+': '+'; '.join(sorted(' / '.join(sorted(kinds))+': '+text
                                        for text,kinds in variants.items())), 'blue')
    return e


def upgrade_paths(rows):
    """Names, ordered by the game's two-for-one upgrade relation."""
    edges = {}
    for r in rows:
        if len(r['inputs'])==1 and r['inputs'][0].startswith('2 x '):
            a,b = r['inputs'][0][4:],r['outputs'][0]['item']
            if a in edges and edges[a] != b:
                raise ValueError('Ambiguous upgrade for '+a)
            edges[a] = b
    paths = []
    visited = set()
    for start in sorted(set(edges)-set(edges.values())):
        path = [start]
        while path[-1] in edges:
            if path[-1] in visited:
                raise ValueError('Upgrade cycle or overlapping paths')
            visited.add(path[-1])
            path.append(edges[path[-1]])
        paths.append(path)
    if visited != set(edges):
        raise ValueError('Upgrade relation is not a set of chains')
    positions = {name:(i,j) for i,path in enumerate(paths) for j,name in enumerate(path)}
    for r in rows:
        output = r['outputs'][0]['item']
        if output not in positions:
            raise ValueError('Missing upgrade path for '+output)
        family,grade = positions[output]
        value = 0
        parts = []
        for text in r['inputs']:
            m = re.fullmatch(r'(?:(\d+) x )?(.+)',text)
            qty,item = int(m[1] or 1),m[2]
            other,rank = positions[item]
            if other != family:
                raise ValueError('Upgrade mixes different kinds')
            parts.append((qty,grade-rank))
            value += qty*2**rank
        if sorted(parts) not in ([(2,1)], [(4,2)], [(1,1),(2,2)]):
            raise ValueError('Unrepresented upgrade method: '+str(parts))
        if value != 2**grade:
            raise ValueError('Unbalanced upgrade')
    return paths


def compact(name, rows, Entry):
    section = rows[0]['section']
    if name in ('Mystic Orbs','Unique Mystic Orbs'):
        return orb_family(name,rows,Entry)
    e = Entry('cube',name,section)
    if name in {'Runes','Upgrade gems','Disenchant items','Reroll an item','Improve item quality',
                'Make a magic or rare item','Create an honorific item','Unsocket an item','Add sockets'}:
        if any(r.get('condition') for r in rows):
            raise ValueError('Unrepresented shared-method condition for '+name)
    if name == 'Trophies':
        conditions = {r.get('condition','') for r in rows}
        if conditions != {'the item has not been blessed yet'}:
            raise ValueError('Trophies no longer share one blessing condition')
        e.add('Cube a trophy with its matching reward charm. The trophy is consumed; the charm keeps its other modifiers.')
        e.add('The charm must not have been blessed already. Each charm can receive only one trophy blessing.')
        for r in sorted(rows,key=lambda r:r['inputs'][1]):
            member(e,r['inputs'][1],[r['inputs'][0]+': '+'; '.join(effects(r))])
    elif name in ('Upgrade gems','Runes'):
        upgrades = [r for r in rows if 'downgrade' not in r['family'].lower()]
        paths = upgrade_paths(upgrades)
        noun = 'gems' if name=='Upgrade gems' else 'runes'
        e.add(f'Cube 2 identical {noun} to make 1 of the next grade. All ingredients must be of the same kind.')
        e.add('To skip one grade, cube 4 identical ingredients, or cube 2 of one grade with 1 of the next grade.')
        if name=='Upgrade gems':
            for path in paths:
                member(e,path[len(path)//2],[' / '.join(path)])
        else:
            lower = {r['inputs'][0]:r['outputs'][0]['item'] for r in rows if 'downgrade' in r['family'].lower()}
            e.add('To downgrade, cube 1 rune on its own to receive 1 rune of the preceding grade, where listed.')
            for path in paths:
                for i,rune in enumerate(path):
                    parts = (['upgrades to '+path[i+1]] if i+1<len(path) else [])
                    if rune in lower:
                        parts.append('downgrades to '+lower[rune])
                    member(e,rune,parts)
    elif name == 'Alchemy':
        if {r.get('condition','') for r in rows} != {'more than 500 Crafting Points'}:
            raise ValueError('Alchemy no longer shares one crafting requirement')
        e.add('Cube the listed ingredients to make 3 of the named elixir. Requires more than 500 Crafting Points from equipped items.')
        for r in sorted(rows,key=lambda r:r['outputs'][0]['item']):
            member(e,r['outputs'][0]['item'],[' + '.join(r['inputs'])])
    elif name == 'Disenchant items':
        e.add('Cube a unique or set item with a catalyst to destroy the item and receive the result below. The catalyst is returned.')
        e.add('Works on weapons, armour, jewellery, quivers and jewels.')
        for catalyst in sorted({r['inputs'][1] for r in rows}):
            results = sorted({o['item'] for r in rows if r['inputs'][1]==catalyst for o in r['outputs'] if o['item']!=catalyst})
            member(e,catalyst,results)
    elif name == 'Craft a jewel':
        e.add('Cube a jewel with Oil of Jewelcraft and one of the runes below to reroll it as a crafted jewel with the listed bonus.')
        e.add('Required Crafting Points come from equipped items.')
        for r in sorted(rows,key=lambda r:r['inputs'][2]):
            member(e,r['inputs'][2],['; '.join(effects(r))+'; requires '+r['condition']])
    elif name == 'Add a random modifier':
        if {r.get('condition','') for r in rows} != {'item item_upgraded = 0'}:
            raise ValueError('Unrepresented lucky upgrade condition')
        e.add('Cube the item with Oil of Luck for the chances below. The item keeps its other modifiers.')
        e.add('An item may receive this upgrade only once, even when no bonus appears. Weapons and armour must be non-ethereal.')
        for r in sorted(rows,key=lambda r:kind(r['inputs'][0])):
            member(e,kind(r['inputs'][0]),['; '.join(t for t in effects(r) if t!='Already upgraded!')])
    elif name == 'Add sockets':
        e.add('Cube a non-ethereal weapon or armour with jewels to add sockets. The item must have no sockets already.')
        counts = sorted({int(re.search(r'Socketed \((\d+)\)',t)[1]) for r in rows for t in effects(r)})
        e.add('Use '+', '.join(map(str,counts))+' jewels to add the same number of sockets, limited by the base maximum.')
    elif name == 'Create an honorific item':
        e.add('Cube a magic weapon or armour with Sacrifical Heart and Meditation Candle to create an honorific item.')
        e.add('The item loses its old modifiers and receives sockets, limited by its base maximum.')
        for text in sorted({t for r in rows for t in effects(r) if not t.startswith('Socketed (')}):
            e.add(text,'blue')
    elif name == 'Unsocket an item':
        e.add('Cube a socketed item with Oil of Disjunction to return the item and its socket fillers separately.')
        by_extras = defaultdict(set)
        for r in rows:
            by_extras[tuple(r['inputs'][2:])].add(re.search(r'\(([^)]+)\)',r['inputs'][0])[1].replace(', socketed',''))
        for extras,qualities in sorted(by_extras.items()):
            member(e,' / '.join(sorted(qualities)),['also add '+' + '.join(extras) if extras else 'no other ingredients'])
    elif name == 'Reroll an item':
        e.add('Cube an item with Oil of Renewal to reroll it, keeping its base and quality.')
        by_quality = defaultdict(set)
        for r in rows:
            quality = re.search(r'\(([^)]+)\)',r['inputs'][0])[1]
            by_quality[quality].add(kind(r['inputs'][0]))
        for quality,kinds in sorted(by_quality.items()):
            member(e,quality,[' / '.join(sorted(kinds))])
    elif name in ('Improve item quality','Make a magic or rare item'):
        with_rune = name=='Make a magic or rare item'
        e.add('Cube the item with Oil of Enhancement'+(' and any rune' if with_rune else '')+' to reroll it at the quality below.')
        results = defaultdict(lambda:defaultdict(set))
        for r in rows:
            quality = re.search(r'\(([^)]+)\)',r['outputs'][0]['item'])[1]
            input_quality = re.search(r'\(([^)]+)\)',r['inputs'][0])
            results[quality][kind(r['inputs'][0])].add(input_quality[1] if input_quality else 'normal')
        for quality,inputs in sorted(results.items()):
            by_qualities = defaultdict(set)
            for item_kind,qualities in inputs.items():
                by_qualities[tuple(sorted(qualities))].add(item_kind)
            member(e,quality,[' / '.join(sorted(kinds))+' ('+' / '.join(qualities)+')'
                              for qualities,kinds in by_qualities.items()])
    else:
        return None
    return e
