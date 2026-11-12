"""Player-facing selection and grouping for the wiki table. No game content is stored here.

Evidence of rejected content is written only into work/wiki by the exporter.
"""
from collections import defaultdict
import copy
import json
import re

# These are syntax checks, not a replacement for obtaining names through strings.
FORBIDDEN = (r'\brows?\b', r'\brecords?\b', r'\bids?\b', r'\bcodes?\b', r'\bcolumns?\b',
             r'\.[tT][xX][tT]\b', r'\b(?:mxl2012|d2r):', r'\b\w+_\w+\b',
             r'\b(?:op|stat|prefix|suffix)\s+\d+', r'\b(?:lvlreq|itype|etype|monstats|cubemain|LevelName)\b',
             r'\.(?:ds1|dt1|dcc|dc6|json|bin|dll|toml|mpq|ini|exe|php|css|html)\b',
             r'\b(?:par|ln|dm|stat)\s*\(', r'\bskill\s*\(\s*[\'\"]', r'\bitemtypes?\b',
             r'\b(?:D2RLoader|PlugY|Downloader|plugins?|console|hardcoded)\b',
             r'\b(?:mods|data|Saved Games)[\\/]',
             r'\b(?:grtz|asaa|cm1|cm2|cm3|jewl|weap|armo|misl)\b',
             r'\b(?:SkillPage|SkillRow|SkillColumn|NameStr|TreasureClass)\b',
             r'\b(?:Skills[dn]|strskill)\w+',
             r'\b(?:cypherpunk|desertpeak|epicwhiners|glados|moskvich|downtown|macumba|borgir|charismatic|temple5|temple6|rockisdead|caveroom5)\b')
BAD = re.compile('|'.join(FORBIDDEN), re.I)
CLASSES = {'ama': 'Amazon', 'ass': 'Assassin', 'bar': 'Barbarian', 'dru': 'Druid',
           'nec': 'Necromancer', 'pal': 'Paladin', 'sor': 'Sorceress', 'war': 'Warlock'}
GRANTS = {'oskill', 'skill', 'charged', 'aura', 'hit-skill', 'att-skill', 'gethit-skill',
          'kill-skill', 'death-skill', 'levelup-skill'}


def active(r):
    return r.get('spawnable') == '1' and not r.get('disabled')


def head(cell):
    return cell.split(',')[0].strip().strip('"')


def unique_key(r):
    return r['key'], r['base_code']


class Sources:
    """Trace content from drops, shops, quests, presets and reachable cube inputs.

    No unique charm is admitted merely because its base or spawnable flag exists.
    Generic unique equipment must have an obtainable base and an eligible level.
    """
    def __init__(self, data):
        import items
        import monsters
        import fxpaths
        from ds1_remap import Ds1
        self.item_data = items.Data()
        self.read = items.read
        self.mondata = monsters.Data()
        self.levels = self.mondata.levels
        self.types = {r['Code']: r for r in items.read('itemtypes.txt') if r.get('Code')}
        # Several hundred Cornerstone definitions share a key; retired copies
        # must not overwrite the 149 enabled definitions selected by items.py.
        self.ur = {}
        for r in items.read('uniqueitems.txt'):
            if r.get('index') and r.get('code'):
                key = r['index'], r['code']
                if key not in self.ur or active(r):
                    self.ur[key] = r
        self.mon = self.mondata.mon
        self.where = defaultdict(set)
        self.super_where = defaultdict(set)
        for mid, diffs in monsters.spawns(self.mondata).items():
            self.where[mid].update(l for group in diffs for l in group)
        for rec in data['monsters']:
            if rec['kind'] == 'superunique' and rec.get('located'):
                for name in {a for d in rec['diff'].values() for a in d['areas']}:
                    lids = {l for l in self.levels if self.area(l) == name}
                    self.where[rec['class']].update(lids)
                    self.super_where[rec['id']].update(lids)
        # These quest bosses are placed by the engine rather than level population lists.
        for mid, lid in {'andariel':37, 'duriel':73, 'radament':49, 'mephisto':102, 'diablo':108,
                         'summoner':74, 'izual':105, 'bloodraven':17, 'griswold':38,
                         'hephasto':107, 'nihlathakboss':124, 'baalcrab':132}.items():
            self.where[mid].add(lid)
        ids = json.loads((items.ROOT / 'work/mod/ds1_ids.json').read_text('utf-8'))
        by_hc = {items.num(r.get('*hcIdx')): mid for mid, r in self.mon.items()}
        # Extracted asset directories can be case-sensitive even on Windows.
        tile_root = fxpaths.MXL / 'tiles'
        tiles = {p.relative_to(tile_root).as_posix().casefold():p for p in tile_root.rglob('*.ds1')}
        presets = defaultdict(list)
        for line in (items.EXCEL / 'monpreset.txt').read_text('utf-8-sig').splitlines()[1:]:
            act, _, place = line.partition('\t')
            if act.isdigit():
                presets[int(act)].append(place.strip())
        supers = {r['Superunique']:r['Class'] for r in self.mondata.supers if r.get('Class')}
        for preset in items.read('lvlprest.txt'):
            lid = items.num(preset.get('LevelId'))
            if not lid:
                lid = next((v for k,v in monsters.SUB_PRESETS.items() if preset['Name'].startswith(k)), 0)
            if not lid or lid not in self.levels:
                continue
            for i in range(1, 7):
                file = preset.get(f'File{i}', '').replace('\\', '/')
                if not file or file == '0':
                    continue
                path = tiles.get(file.casefold())
                if path is None:
                    continue
                ds = Ds1(path.read_bytes())
                for kind, oid, *_ in ds.objects:
                    if kind != 1:
                        continue
                    table = presets[ds.act+1]
                    if 0 <= oid < len(table):
                        place = table[oid]
                        mid = supers.get(place,place)
                        if place in supers:
                            self.super_where[place].add(lid)
                    else:
                        mid = by_hc.get(ids['monster'].get(str(oid), oid))
                    if mid in self.mon:
                        self.where[mid].add(lid)
        # Trace monsters summoned by live monsters and their minion definitions.
        skillrows = {r['skill']: r for r in items.read('skills.txt') if r.get('skill')}
        skillids = {r.get('*Id'):r for r in skillrows.values()}
        missiles = {r['Missile']:r for r in items.read('missiles.txt')}

        def skill_children(skill):
            todo = [v for k,v in skill.items() if k.startswith('srvmissile') and v]
            children, visited = [skill.get('summon')], set()
            while todo:
                name = todo.pop()
                if name in visited or name not in missiles:
                    continue
                visited.add(name)
                m = missiles[name]
                if m.get('pSrvHitFunc') == '6':
                    children.append(by_hc.get(items.num(m.get('sHitPar1'))))
                todo.extend(v for k,v in m.items() if v and ('submissile' in k.lower() or k == 'ExplosionMissile'))
            return children

        summoned = {key:skill_children(r) for key,r in skillrows.items()}
        self.summoned = summoned
        self.omissions = []
        changed = True
        while changed:
            changed = False
            for mid, places in list(self.where.items()):
                r = self.mon.get(mid, {})
                children = [r.get('minion1'), r.get('minion2')]
                for i in range(1, 9):
                    children += summoned.get(r.get(f'Skill{i}'), [])
                prop = self.mondata.monprop.get(r.get('MonProp'), {})
                for suffix in ('',' (N)',' (H)'):
                    for i in range(1,7):
                        if prop.get(f'prop{i}{suffix}') in GRANTS:
                            sk = skillids.get(prop.get(f'par{i}{suffix}'), {})
                            children += summoned.get(sk.get('skill'), [])
                for child in children:
                    if child in self.mon and not places <= self.where[child]:
                        self.where[child].update(places)
                        changed = True
        self.live = {k for k, places in self.where.items() if places and self.mon.get(k, {}).get('enabled') != '0'}
        # Expand referenced treasure classes, including built-in equipment classes.
        tc = {r['Treasure Class']: r for r in items.read('treasureclassex.txt') if r.get('Treasure Class')}
        todo = [v for mid in self.live for k, v in self.mon[mid].items() if k.startswith('TreasureClass') and v]
        todo += [v for r in self.mondata.supers if self.super_where.get(r['Superunique'])
                 for k,v in r.items() if k in ('TC','TC(N)','TC(H)') and v]
        seen, self.tokens = set(), set()
        while todo:
            token = todo.pop()
            if token in seen:
                continue
            seen.add(token)
            if token in tc:
                todo.extend(tc[token].get(f'Item{i}', '') for i in range(1, 11) if tc[token].get(f'Prob{i}', '0') not in ('', '0'))
            else:
                self.tokens.add(head(token))
        # The engine's implicit equipment treasure classes select these bases.
        equipment = [r for n in ('weapons.txt', 'armor.txt') for r in items.read(n) if r.get('spawnable') == '1']
        if any(re.fullmatch(r'(?:weap|armo)\d+', t) for t in self.tokens):
            self.tokens.update(r['code'] for r in equipment)
        for r in self.item_data.bases.values():
            if r.get('spawnable') == '1' and any(k.endswith(('Max', 'MagicMax')) and items.num(v) > 0 for k, v in r.items()):
                self.tokens.add(r['code'])
        # Quest objects supplied by the engine (not random drops), used by cube recipes.
        self.tokens.update(c for c, r in self.item_data.bases.items() if items.num(r.get('quest')))
        self.tokens.update({'leg', 'box', 'msf', 'vip', 'hst', 'qf1', 'qf2', 'qey', 'qhr', 'qbr'})
        self.unique_records = data['uniques']
        self.generic = {unique_key(r) for r in data['uniques'] if self.generic_unique(r)}
        self.tokens.update(k for k, _ in self.generic)
        self.tokens.update(self.ur[(k, c)]['code'] for k, c in self.generic)
        self.recipes = []
        pending = [r for r in data['cube'] if not r.get('decoy')]
        changed = True
        while changed:
            changed = False
            for r in pending[:]:
                if all(self.available(head(cell)) for cell in r['codes']['inputs']):
                    pending.remove(r)
                    self.recipes.append(r)
                    for cell in r['codes']['outputs']:
                        token = head(cell)
                        if token not in {'useitem', 'usetype'} and token not in self.tokens:
                            self.tokens.add(token)
                            changed = True
                    # A named unique drop/output makes its base available too.
                    for (key, code), _ in self.ur.items():
                        if key in self.tokens and code not in self.tokens:
                            self.tokens.add(code)
                            changed = True
        self.uniques = [r for r in data['uniques'] if self.keep_unique(r)]
        self.rejected = [r['name'] for r in data['uniques'] if not self.keep_unique(r)]
        self.rejected += [items.strip(self.item_data.text(r['index']))[0].split('\n')[-1].strip()
                          for r in items.read('uniqueitems.txt') if r.get('index') and not active(r)]
        self.granted = set()
        props = [q for r in self.uniques for q in r.get('props', [])]
        props += [q for s in data['sets'] for r in s['items'] for q in r.get('props', [])]
        props += [q for r in data['runewords'] for q in r.get('props', [])]
        props += [q for g in data['gemwords'] for k in g['kinds'] for c in k['counts'] for q in c.get('props', [])]
        reachable = {r['row'] for r in self.recipes}
        for i,r in enumerate(items.read('cubemain.txt'),1):
            if i in reachable:
                props += [[r.get(f'{prefix}mod {j}'),r.get(f'{prefix}mod {j} param'),r.get(f'{prefix}mod {j} min'),r.get(f'{prefix}mod {j} max')]
                          for prefix in ('','b ','c ') for j in range(1,6)]
        rollable = [self.chain(r.get('type','')) for c,r in self.item_data.bases.items()
                    if c in self.tokens and r.get('spawnable')=='1'
                    and self.chain(r.get('type','')) & {'weap','armo','jewl','ring','amul','misl'}]
        for filename in ('magicprefix.txt', 'magicsuffix.txt', 'automagic.txt'):
            for r in items.read(filename):
                allowed = {v for k,v in r.items() if k.startswith('itype') and v}
                excluded = {v for k,v in r.items() if k.startswith('etype') and v}
                applicable = any((allowed & chain or 'any' in allowed) and not excluded & chain for chain in rollable)
                if r.get('spawnable') == '1' and items.num(r.get('level')) <= 120 and applicable:
                    props += [[r.get(f'mod{i}code'), r.get(f'mod{i}param'), r.get(f'mod{i}min'), r.get(f'mod{i}max')] for i in range(1, 4)]
        for code, par, lo, hi in props:
            if code in GRANTS and par:
                self.granted.add(str(par))
        self.skillrows = skillrows
        self.skill_names = {}
        desc = {r['skilldesc']: r for r in items.read('skilldesc.txt')}
        for r in skillrows.values():
            d = desc.get(r.get('skilldesc'), {})
            text = self.item_data.text(d.get('str name', ''))
            if text:
                self.skill_names[r['skill']] = self.skill_names[str(items.num(r.get('*Id')))] = items.strip(text)[0].split('\n')[-1].strip()
        self.unnamed_skills = {k for k in skillrows if k not in self.skill_names} - set(self.skill_names.values())
        self.unnamed_pattern = re.compile(r'(?<!\w)(?:'+'|'.join(re.escape(n) for n in sorted(self.unnamed_skills,key=len,reverse=True))+r')(?!\w)')

    def chain(self, code):
        todo, seen = [code], set()
        while todo:
            c = todo.pop()
            if c and c not in seen:
                seen.add(c)
                todo.extend(self.types.get(c, {}).get(k, '') for k in ('Equiv1','Equiv2'))
        return seen

    def area(self, lid):
        r = self.levels.get(lid, {})
        import items
        return items.strip(self.item_data.text(r.get('LevelName','')))[0].split('\n')[-1].strip()

    def generic_unique(self, r):
        raw = self.ur.get(unique_key(r), {})
        base = self.item_data.bases.get(r['base_code'], {})
        # Charm/reward definitions need an explicit source, even when spawnable.
        return (active(raw) and r['base_code'] in self.tokens and 'char' not in self.chain(base.get('type',''))
                and r['lvl'] <= 120)

    def keep_unique(self, r):
        raw = self.ur.get(unique_key(r), {})
        return active(raw) and (unique_key(r) in self.generic or r['key'] in self.tokens)

    def available(self, token):
        if token in {'any', 'useitem', 'usetype'} or token in self.tokens:
            return True
        if token in self.types:
            return any(token in self.chain(self.item_data.bases.get(c, {}).get('type','')) for c in self.tokens if c in self.item_data.bases)
        return False

    def label(self, r):
        # A subtitle's item label comes from the actual base tooltip, not ItemType.
        base = self.item_data.bases.get(r['base_code'], {})
        if 'char' in self.chain(base.get('type','')):
            return 'Charm'
        return re.sub(r'\s*\((?:\d+|Sacred)\)$', '', r['base_name']).strip()


def group_entries(entries, Entry):
    groups = {}
    variants = defaultdict(set)
    for e in entries:
        key = e.category, e.name.casefold()
        signature = (e.subtitle,tuple(e.lines))
        if key not in groups:
            groups[key] = copy.deepcopy(e)
        else:
            target = groups[key]
            if signature not in variants[key]:
                if len(variants[key]) == 1:
                    target.lines.insert(0,('gold',target.subtitle))
                target.lines.append(('gold',e.subtitle))
                target.lines.extend(e.lines)
            target.links.extend(e.links)
        variants[key].add(signature)
    return list(groups.values())


def recipe_name(r):
    from wikipanel_families import family_name
    shared = family_name(r)
    if shared:
        return shared
    f = r['family'].lower()
    output = r['outputs'][0]['item'] if r['outputs'] else ''
    if r['section'] == 'Jewelcrafting':
        return 'Craft a jewel'
    if f.startswith('dupe'):
        return 'Duplicate an item'
    actions = [('unique uptier', 'Uptier a unique item'), ('any uptier','Uptier a tiered item'),
               ('shrine crafting','Craft a sacred item'), ('blessings','Bless a sacred item'),
               ('black road','Complete the Black Road Challenge'), ('destruction','Destroy unwanted items'),
               ('disenchant as signet','Disenchant a sacred unique or set item'),
               ('disenchant recipe','Disenchant a unique or set item'), ('shards to container','Make an Arcane Crystal'),
               ('chaos reroll','Chaos reroll'), ('random modifier','Add a random modifier'),
               ('zomghelp','Reroll a magic item with enhanced damage or defense'),
               ('socket creation','Add sockets'), ('white unsocket','Remove sockets'), ('unsocket','Unsocket an item'),
               ('enchant','Make a magic item'), ('affix burn','Make a low quality item'),
               ('upgrade and reroll: low','Make a normal item'), ('upgrade and reroll: normal','Make a superior item'),
               ('gem shatter','Make a rare item'), ('shard shatter','Make a tiered unique item'),
               ('veteran','Upgrade a veteran reward'), ('level challenge','Complete a level challenge'),
               ('class skill challenge','Upgrade a class charm'), ('dragon challenge','Complete the dragon challenge'),
               ('edyrem','Upgrade the summoning reward'), ('toraja','Bless the summoning reward'),
               ('witch challenge','Complete the witch challenge'), ('window challenge','Complete the timed challenge'),
               ('startle challenge','Complete the aura challenge'), ('massacre','Complete the massacre challenge'),
               ('nu-att','Complete the temple challenge'), ('stardragon','Upgrade the dragon reward'),
               ('dogma','Create a skill signet'), ('create quest','Create a challenge reward'),
               ('i am richer',output), ('clue gem','Cycle a Pearl of Wisdom'), ('rip','Add Slain Monsters Rest in Peace')]
    for prefix, name in actions:
        if f.startswith(prefix):
            return name
    if output and not output.lower().startswith(('the item', 'any ')):
        return output
    return 'Upgrade ' + re.sub(r'\s*\([^)]*\)', '', r['inputs'][0])


def normalize_input(text):
    text = re.sub(r'\s*\(\d+ Charges?\)', ' with at least 1 charge', text)
    text = re.sub(r'\(\d+\)', '(tiered)', text)
    text = re.sub(r'any Craft Sacred [^(]+\([^)]*\)', 'any sacred weapon or armour', text)
    for before,after in {'any Missile':'any quiver', 'any Tier (1-6)':'any tiered weapon or armour',
                         'any Armor':'any armour','any Weapon':'any weapon'}.items():
        text = text.replace(before,after)
    return text


def recipe_condition(r):
    condition = r.get('condition','')
    if not BAD.search(condition):
        return condition
    if condition == 'item item_upgraded = 0':
        return 'the item has not received this upgrade'
    if 'goodberry_enabled' in condition:
        return 'Requires the Goodberry skill; see the Druid skills.'
    if 'witchberry_lifeheal' in condition:
        return 'Requires the appropriate berry skill.'
    if 'levelchallenge_kill_check' in condition or 'blackroad_kill_check' in condition:
        return 'Requires the matching challenge effect. Transmute while the effect is active; see the linked guide for the task and time limit.'
    # Unknown conditions must never turn into an apparently unrestricted recipe.
    raise ValueError('Untranslated cube condition: ' + condition)


def recipes(records, Entry):
    from wikipanel_families import compact, member
    groups = defaultdict(list)
    for r in records:
        groups[(recipe_name(r), r['section'])].append(r)
    out = []
    for (name, section), members in groups.items():
        shared = compact(name,members,Entry)
        if shared is not None:
            out.append(shared)
            continue
        e = Entry('cube', name, section)
        class_effects = defaultdict(set)
        for r in members:
            if r.get('class'):
                signature = tuple((o['item'],tuple(re.sub(r'to (?:'+'|'.join(CLASSES.values())+r') Skill Levels','to your class Skill Levels',t) for t in o.get('mods',[]))) for o in r['outputs'])
                class_effects[(r['family'],tuple(r['inputs'][1:]),r.get('condition',''))].add(signature)
        if name.startswith('Uptier'):
            unique = 'unique' in name
            e.add('Inputs: any tiered ' + ('unique ' if unique else 'non-ethereal ') + 'weapon or armour + Arcane Crystal' + (' + any rune' if unique else ''))
            e.add('Output: the next tier of the same item' + (' with new unique modifiers' if unique else ', keeping its modifiers'), 'gold')
            e.add('Only tiers below the highest tier can be upgraded. Sacred items cannot be made this way.')
        elif name == 'Destroy unwanted items':
            e.add('Inputs: Catalyst of Destruction + unwanted items')
            e.add('Output: the Catalyst is returned; the other items are destroyed.', 'gold')
            e.add('Your own class charm is returned if it is included.')
        elif name == 'Reroll a magic item with enhanced damage or defense':
            e.add('Inputs: any magic weapon or armour + a magic amulet + a magic ring')
            e.add('Output: the first item rerolled as magic, with enhanced damage for weapons or enhanced defense for armour.', 'gold')
            rolls = []
            for r in members:
                level = int(r['condition'].rsplit(' ',1)[1])
                if level <= 120:
                    value = int(re.search(r'(\d+)%',r['outputs'][0]['mods'][0])[1])
                    rolls.append((level,value))
            rolls = sorted(set(rolls))
            slope = (rolls[-1][1]-rolls[0][1]) // (rolls[-1][0]-rolls[0][0]) if len(rolls)>1 else 0
            if all(v == rolls[0][1] + slope*(lv-rolls[0][0]) for lv,v in rolls):
                e.add(f'Enhanced damage or defense: {rolls[0][1]}% at character level {rolls[0][0]}, increasing by {slope}% per character level ({rolls[-1][1]}% at level {rolls[-1][0]}).','blue')
            else:
                for lv,v in rolls:
                    e.add(f'Character level {lv}: {v}% enhanced damage or defense','blue')
            e.add('The resulting item has item level 1.')
        elif section in {'Shrine crafting', 'Shrine blessings'}:
            blessing = section == 'Shrine blessings'
            e.add('Inputs: any sacred weapon or armour ' + ('(non-ethereal) + a shrine with at least 1 charge + Arcane Crystal' if blessing else '(rare, set, unique or crafted) + a shrine with at least 1 charge'))
            e.add('The shrine loses one charge. Its last charge consumes the shrine.')
            e.add('The item keeps its modifiers and can only be blessed once.' if blessing else 'Output: a crafted item with new modifiers.', 'gold')
            by_shrine = defaultdict(set)
            for r in members:
                reagent = normalize_input(r['inputs'][1])
                mods = tuple(t for o in r['outputs'] if 'Shrine (' not in o['item'] for t in o.get('mods', []))
                by_shrine[reagent].update(t for t in mods if not t.startswith(('Socketed (','Orb Effects Applied')))
            if not blessing:
                e.add('The base limits the number of sockets. Mystic Orb effects on the crafted item are doubled.')
            for reagent, mods in sorted(by_shrine.items()):
                member(e,reagent,['; '.join(sorted(mods))])
        else:
            rules = {}
            for r in members:
                inputs = [normalize_input(t) for t in r['inputs']]
                if r.get('class') and inputs:
                    if inputs[0] in {'Sacred Sunstone','Shadow Vortex','Worldstone Orb','Caoi Dulra Fruit','Soulstone Shard','Eye of Divinity','Nexus Crystal'}:
                        inputs[0] = 'your class charm'
                lines = []
                outputs = defaultdict(int)
                for o in r['outputs']:
                    outputs[(normalize_input(o['item']),tuple(o.get('mods',[])))] += 1
                for (output,mods),qty in outputs.items():
                    if 'Shrine (' in output:
                        continue
                    lines.append(('gold','Output: ' + (f'{qty} x ' if qty>1 else '') + output))
                    lines.extend(('blue',re.sub(r'to (?:'+ '|'.join(CLASSES.values()) +r') Skill Levels', 'to your class Skill Levels',t) if inputs and inputs[0]=='your class charm' else t) for t in mods)
                condition = recipe_condition(r)
                if condition:
                    lines.append(('white', 'Condition: ' + condition))
                if r.get('class'):
                    different = len(class_effects[(r['family'],tuple(r['inputs'][1:]),r.get('condition',''))])>1
                    if inputs and inputs[0]=='your class charm':
                        if different:
                            lines.insert(0,('gold',r['class']))
                    else:
                        lines.append(('white','For '+r['class']))
                if r.get('min_diff'):
                    lines.append(('white', r['min_diff'] + ' or higher'))
                # Keep distinct results within a family; combine equivalent base
                # selections into the same rule rather than repeating its output.
                # Repeated recipe ingredients are alternatives; output details
                # still distinguish effects and preserve their required inputs.
                key = tuple(inputs[1:]),tuple(lines)
                rules.setdefault(key,[])
                if inputs and inputs[0] not in rules[key]:
                    rules[key].append(inputs[0])
            seen_inputs = set()
            for (other_inputs,lines),first_inputs in rules.items():
                input_text = ' + '.join([' / '.join(first_inputs)]+list(other_inputs))
                if input_text not in seen_inputs:
                    e.add('Inputs: ' + input_text)
                    seen_inputs.add(input_text)
                e.lines.extend(lines)
        if 'Challenge' in name or any('challenge effect' in t for _,t in e.lines):
            guide = 'Black Road' if 'Black Road' in name else 'Ennead' if 'class charm' in name else 'Minigames' if any(t in name for t in ('witch','aura','massacre')) else 'Level challenges'
            e.add('Requirements and timing: see ' + guide + '.')
            e.links.append(guide)
        out.append(e)
    return group_entries(out, Entry)


def player_skills(source, laz_path):
    import skills
    import laz
    laz.LAZ = laz_path
    skills.CLASSES.update(CLASSES)
    s = skills.Skills()
    starts = skills.start_skills(s)
    flavour = laz.skill_texts()
    out = []
    for row in s.sk.rows:
        if s.sk.get(row,'InGame') == '0':
            continue
        d = s.desc(row)
        if d is None:
            continue
        key = row[0]
        cls = s.sk.get(row, 'charclass')
        sid = str(skills.num(s.sk.get(row,'*Id')))
        tree = cls in CLASSES and skills.num(s.sd.get(d,'SkillPage')) > 0 and skills.num(s.sk.get(row,'maxlvl')) > 0
        if not tree and key not in starts and sid not in source.granted and key not in source.granted:
            continue
        if not s.name(row) or key not in source.skill_names:
            continue
        r = skills.record(s, row, flavour)
        if key in starts and not tree:
            r['class'], r['tree'] = CLASSES[starts[key]], 'Innate'
        elif not tree:
            r['class'], r['tree'] = '', ''
        if cls == 'war' and tree:
            r['tree'] = source.item_data.text('SkillCategoryWa' + str(r['page']))
        r['name'] = source.skill_names[key]
        out.append(r)
    names = {r['name'] for r in out}
    for r in out:
        for key in ('prereqs','synergies'):
            r[key] = [n for n in r[key] if n in names]
    return out


def monster_entries(data, source, Entry):
    import monsters
    have = {r['id'] for r in data if r['kind']=='monster'}
    data = list(data)
    # Include placed/summoned monsters the wiki's boss-or-population rule missed.
    for mid in sorted(source.live-have):
        raw = source.mon[mid]
        if source.item_data.text(raw.get('NameStr','')):
            places = source.where[mid]
            data.append(monsters.monster(source.mondata, raw, [places,places,places]))
    out = []
    for r in data:
        mid = r.get('class',r['id']) if r['kind']=='superunique' else r['id']
        raw = source.mon.get(mid,{})
        places = source.super_where.get(r['id'],()) if r['kind']=='superunique' else source.where.get(mid,())
        areas = sorted({source.area(lid) for lid in places if source.area(lid)})
        if r['kind']=='superunique' and not areas and r.get('located'):
            areas = sorted({a for d in r['diff'].values() for a in d['areas']})
        if not areas or mid not in source.live or raw.get('npc')=='1' or raw.get('killable')=='0' or not r['name']:
            continue
        e = Entry('mon',r['name'],', '.join(areas))
        e.add('Found in: ' + ', '.join(areas), 'gold')
        for diff,d in r['diff'].items():
            e.add(diff,'gold')
            e.add('Level: ' + '-'.join(map(str,d['levels'])))
            if d['resist']:
                e.add('Resistances: ' + ', '.join(f'{k} {v}%' for k,v in d['resist'].items()))
            if d['immune']:
                e.add('Immune: ' + ', '.join(d['immune']))
            for line in d['props']:
                unknown = source.unnamed_pattern.search(line)
                if unknown:
                    name = unknown[0]
                    children = sorted({source.item_data.text(source.mon.get(k,{}).get('NameStr','')) for k in source.summoned.get(name,[]) if k})
                    children = [monsters.COLOUR.sub('',n).split('\n')[-1].strip() for n in children if n]
                    if children and 'chance to cast level ' in line:
                        line = re.sub(r'cast level \d+ '+re.escape(name), 'summon '+', '.join(children),line)
                    else:
                        source.omissions.append({'category':'mon','name':e.name,'reason':'unnamed monster effect','text':line})
                        continue
                e.add(line)
        names = sorted({s['name'] for s in r['skills'] if s['name'] in set(source.skill_names.values())})
        if names:
            e.add('Abilities: ' + ', '.join(names))
        out.append(e)
    return group_entries(out, Entry)


def finish(entries, source, Entry):
    """Reject technical prose rather than silently disguising unknown semantics."""
    dropped = list(getattr(source,'omissions',[]))
    retained_names = {e.name for e in entries if e.category=='uniq'}
    retired = set(source.rejected)-retained_names
    # Replace internal map labels with the corresponding effective LevelName.
    maps = {r.get('Name',''):source.area(lid) for lid,r in source.levels.items() if source.area(lid)}
    renames = {k:v for k,v in maps.items() if len(k)>3 and k != v}
    map_pattern = re.compile(r'(?<![\w])(?:'+'|'.join(re.escape(k) for k in sorted(renames,key=len,reverse=True))+r')(?![\w])' if renames else r'(?!)')
    result = []
    for e in entries:
        e.name = maps.get(e.name,e.name)
        e.subtitle = maps.get(e.subtitle,e.subtitle)
        lines = []
        for colour,text in e.lines:
            # Technical tails are often whole explanatory sentences in wiki prose.
            # Keep surrounding player prose when a single sentence can be removed.
            for sentence in re.split(r'(?<=[.!?])\s+(?=[A-Z])',text):
                reason = ''
                if BAD.search(sentence):
                    reason = 'developer syntax or wording'
                elif any(name and name in sentence for name in retired):
                    reason = 'unobtainable content'
                elif any(term in sentence for term in ('Click a column','table\'s search box','Assumes zero:')):
                    reason = 'website or evaluation instructions'
                if reason:
                    dropped.append({'category':e.category,'name':e.name,'reason':reason,'text':sentence})
                else:
                    # Match whole internal map names only, never substrings of player names.
                    sentence = map_pattern.sub(lambda m:renames[m[0]],sentence)
                    lines.append((colour,sentence))
        if BAD.search(e.name+' '+e.subtitle):
            dropped.append({'category':e.category,'name':e.name,'reason':'unresolved name or subtitle'})
            continue
        e.lines = lines or [('white',e.name)]
        result.append(e)
    welcome = Entry('page','Welcome','In-game guide')
    welcome.add('Browse the items, recipes, skills, monsters and guides of D2R-XL 2012.')
    welcome.add('Type to search, pick a category, then click a result to read more.')
    welcome.add('Median XL is the work of Brother Laz.')
    result.append(welcome)
    return group_entries(result,Entry), dropped
