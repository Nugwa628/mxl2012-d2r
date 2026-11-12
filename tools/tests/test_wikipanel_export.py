"""Wiki table contract and converters; fixtures here are original text."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import re
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'wiki'))
import projtemp  # noqa: F401,E402
import wikipanel_export as wiki  # noqa: E402
import wikipanel_player as player  # noqa: E402
import wikipanel_families as families  # noqa: E402


class Converter(unittest.TestCase):
    def test_headings_lists_links_paragraphs(self):
        lines, links = wiki.markup("== Overview ==\nA little\nparagraph.\n\n* [[Destination|Go there]]\n# Next step\n[[File:art.png|picture]]")
        self.assertEqual(lines, [('gold', 'Overview'), ('white', 'A little paragraph.'),
                                 ('white', '- Go there'), ('white', '- Next step')])
        self.assertEqual(links, ['Destination'])

    def test_table_rows(self):
        lines, _ = wiki.markup('{| class="wikitable"\n! Name !! Value\n|-\n| Alpha || One\n|-\n| Beta\n| Two\n|}')
        self.assertEqual([t for _, t in lines], ['Name | Value', 'Alpha | One', 'Beta | Two'])

    def test_rows_column_is_removed_without_losing_player_cells(self):
        lines, _ = wiki.markup('{|\n! Recipe !! Rows !! Output\n|-\n| Polish a stone || 12-99 || Shiny stone\n|}')
        self.assertEqual([t for _,t in lines], ['Recipe | Output','Polish a stone | Shiny stone'])

    def test_player_filter_and_welcome(self):
        source = SimpleNamespace(rejected=['Old prize'], levels={}, area=lambda _: '')
        entry = wiki.Entry('page','Example','Guide', [('white','Useful advice. The file example.txt holds records.'),
                                                 ('white','Old prize cannot be found.'), ('white','More useful advice.')])
        result, dropped = player.finish([entry],source,wiki.Entry)
        text = [t for _,t in result[0].lines]
        self.assertEqual(text,['Useful advice.','More useful advice.'])
        self.assertEqual(len(dropped),2)
        self.assertEqual(result[1].name,'Welcome')
        self.assertEqual(result[1].lines[-1][1],'Median XL is the work of Brother Laz.')

    def test_area_name_resolves_before_display(self):
        source = SimpleNamespace(rejected=[],levels={1:{'Name':'Act 7 - Room'}},area=lambda _: 'Moonlit Garden')
        e = wiki.Entry('mon','Example','Act 7 - Room',[('white','Found in Act 7 - Room.')])
        result,_ = player.finish([e],source,wiki.Entry)
        self.assertEqual(result[0].subtitle,'Moonlit Garden')
        self.assertEqual(result[0].lines,[('white','Found in Moonlit Garden.')])

    def test_grouping_keeps_complete_variant_blocks(self):
        a = wiki.Entry('uniq','Example','Tier one',[('white','Damage: 10'),('blue','Cold: 5')])
        b = wiki.Entry('uniq','Example','Tier two',[('white','Damage: 20'),('blue','Cold: 5')])
        result = player.group_entries([a,b,a],wiki.Entry)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0].lines,[('gold','Tier one')]+a.lines+[('gold','Tier two')]+b.lines)

    def test_charge_variants_and_shrine_results_are_one_rule(self):
        def shrine(charge, name, stat):
            return {'family':'shrine crafting','section':'Shrine crafting',
                    'inputs':['any Craft Sacred Minor (Armor) (crafted)',f'{name} Shrine ({charge} Charges)'],
                    'outputs':[{'item':'the item','mods':[stat,'Socketed (6)']}],'condition':''}
        out = player.recipes([shrine(10,'Example','+5 to Energy'),shrine(9,'Example','+5 to Energy'),
                              shrine(1,'Other','+4 to Strength')],wiki.Entry)
        self.assertEqual(len(out),1)
        text = [t for _,t in out[0].lines]
        self.assertEqual(sum('+5 to Energy' in t for t in text),1)
        self.assertIn('Other Shrine with at least 1 charge: +4 to Strength',text)
        self.assertFalse(any('9 Charges' in t or '10 Charges' in t for t in text))

    def test_tier_and_base_variants_are_one_recipe(self):
        rows = [{'family':'any uptier recipe','section':'Uptier recipes','inputs':[name],
                 'outputs':[{'item':'next tier'}]} for name in ('Example Blade (1)','Other Coat (2)')]
        result = player.recipes(rows,wiki.Entry)
        self.assertEqual(len(result),1)
        self.assertIn('any tiered non-ethereal weapon or armour',result[0].lines[0][1])

    def test_unknown_condition_cannot_be_silently_dropped(self):
        with self.assertRaises(ValueError):
            player.recipe_condition({'condition':'item mystery_flag = 1'})

    def test_disabled_and_unspawnable_are_inactive(self):
        self.assertTrue(player.active({'spawnable':'1'}))
        self.assertFalse(player.active({'spawnable':'1','disabled':'1'}))
        self.assertFalse(player.active({'spawnable':''}))

    def test_shared_orbs_keep_kinds_and_put_method_and_cost_once(self):
        def orb(item,effect,honorific=False):
            return {'family':'affix crystal','section':'Mystic Orbs','inputs':[item,'Mystic Orb'],
                    'orb':{'code':'fixture','name':'Mystic Orb','description':'Fixture modifier'},
                    'outputs':[{'item':'the item','mods':[effect,'+2 Required Level']}],
                    'condition':'honorific items only' if honorific else ''}
        rows=[orb('any Weapon (non-ethereal)','+3 to Energy'),orb('any Armor (non-ethereal)','+3 to Energy'),
              orb('any Weapon (non-ethereal)','+6 to Energy',True),orb('any Ring','Regenerate Mana +4%')]
        result=player.recipes(rows,wiki.Entry)
        self.assertEqual([e.name for e in result],['Mystic Orbs'])
        text=' '.join(t for _,t in result[0].lines)
        self.assertEqual(text.count('+2 Required Level'),1)
        self.assertEqual(text.count('Cube one orb'),1)
        self.assertIn('armour / weapon: +3 to Energy',text)
        self.assertIn('ring: Regenerate Mana +4%',text)
        self.assertNotIn('+6 to Energy',text)

    def test_honorific_only_orbs_keep_their_restriction(self):
        row={'family':'affix crystal','section':'Mystic Orbs','inputs':['any Ring','Mystic Orb'],
             'orb':{'code':'fixture','name':'Mystic Orb','description':'Fixture modifier'},
             'outputs':[{'item':'the item','mods':['+2 to Fixture Skill','+2 Required Level']}],
             'condition':'honorific items only'}
        e=player.recipes([row],wiki.Entry)[0]
        self.assertIn('ring (honorific only): +2 to Fixture Skill',' '.join(t for _,t in e.lines))

    def test_honorific_effect_scaling_preserves_proc_level_and_duration(self):
        self.assertEqual(families.doubled('1% Chance to cast level 7 Fixture on Attack'),
                         '2% Chance to cast level 7 Fixture on Attack')
        self.assertEqual(families.doubled('Adds 5-15 poison damage over 2 seconds'),
                         'Adds 10-30 poison damage over 2 seconds')

    def test_orb_identity_requires_same_description_and_complete_effects(self):
        def orb(code,description,effect):
            return {'inputs':['any Ring','Mystic Orb'],'outputs':[{'mods':[effect,'+2 Required Level']}],
                    'orb':{'code':code,'name':'Mystic Orb','description':description}}
        rows=[orb('one','Fixture description','+1 to Energy'),
              orb('two','Fixture description','+1 to Energy'),
              orb('three','Other description','+1 to Energy'),
              orb('four','Fixture description','+2 to Energy')]
        members=families.orb_members(rows)
        self.assertEqual(len(members),3)
        self.assertIn(['one','two'],[m['codes'] for m in members])
        self.assertEqual(sorted(c for m in members for c in m['codes']),['four','one','three','two'])

    def test_missing_game_name_never_uses_editor_label(self):
        import items
        d=items.Data.__new__(items.Data)
        d.texts={}; d.bases={'fixture':{'name':'Invented editor label','namestr':'missing'}}
        with self.assertRaisesRegex(ValueError,'Missing game name string'):
            d.base_name('fixture')
        d.texts={'resolved':'Actual fixture name'}
        d.bases['fixture']['namestr']='resolved'
        self.assertEqual(d.base_name('fixture'),'Actual fixture name')

    def test_trophies_share_the_method_but_keep_targets_and_effects(self):
        rows=[{'family':'fixture','section':'Mystic Orbs','inputs':[name+' Charm',name+' Trophy'],
               'outputs':[{'item':'the item','mods':[effect]}],'condition':'the item has not been blessed yet'}
              for name,effect in [('First','+3 to Energy'),('Second','+4 to Strength')]]
        e=player.recipes(rows,wiki.Entry)[0]
        self.assertEqual(e.name,'Trophies')
        self.assertEqual(sum('Cube a trophy' in t for _,t in e.lines),1)
        self.assertIn(('blue','First Trophy: First Charm: +3 to Energy'),e.lines)

    def test_unresolved_monster_skill_keeps_its_key_until_player_filter(self):
        import monsters
        d=monsters.Data.__new__(monsters.Data)
        d.skill_by_id={1:'Mon Fixture'}; d.skill_by_key={'Mon Fixture':'Mon Fixture'}
        d.monprop={'fixture':{'prop1':'death-skill','par1':'1','min1':'100','max1':'2',
                              'prop2':'aura','par2':'1','min2':'1','max2':'1'}}
        lines=monsters.props(d,'fixture',0)
        source=SimpleNamespace(live={'fixture'},where={'fixture':{1}},super_where={},
            mon={'fixture':{},'child':{'NameStr':'child-name'}},area=lambda _: 'Fixture Garden',
            item_data=SimpleNamespace(text=lambda key:'Actual summoned name' if key=='child-name' else ''),
            unnamed_pattern=re.compile(r'Mon Fixture'),summoned={'Mon Fixture':['child']},
            omissions=[],skill_names={})
        record={'id':'fixture','kind':'monster','name':'Fixture monster','skills':[],
                'diff':{'Hatred':{'levels':[1,1],'resist':{},'immune':[],'props':lines}}}
        entry=player.monster_entries([record],source,wiki.Entry)[0]
        self.assertIn(('white','100% chance to summon Actual summoned name when it dies'),entry.lines)
        self.assertFalse(any('Fixture aura' in t or 'Mon Fixture' in t for _,t in entry.lines))
        self.assertEqual(len(source.omissions),1)

    def test_gem_chain_keeps_every_grade_and_mixed_method(self):
        names=['Chipped Pebble','Flawed Pebble','Pebble','Flawless Pebble','Perfect Pebble']
        def gem(inputs,output):
            return {'family':'gem upgrade','section':'Gems and runes','inputs':inputs,'outputs':[{'item':output}]}
        rows=[gem(['2 x '+a],b) for a,b in zip(names,names[1:])]
        rows += [gem(['4 x '+names[0]],names[2]),gem(['2 x '+names[0],names[1]],names[2])]
        e=player.recipes(rows,wiki.Entry)[0]
        self.assertEqual(e.name,'Upgrade gems')
        text=' '.join(t for _,t in e.lines)
        for name in names:self.assertIn(name,text)
        self.assertIn('Cube 2 identical gems',text)
        self.assertIn('cube 4 identical',text)
        self.assertIn('2 of one grade with 1 of the next grade',text)
        with self.assertRaises(ValueError):
            families.upgrade_paths(rows+[gem(['3 x '+names[0]],names[2])])

    def test_category_prose_preserves_rules_and_native_credit_not_listings(self):
        text=('Useful introduction.\n\n== Method ==\nUseful rule.\n\n'
              '<!-- generated by fixture -->\n== Items ==\n[[Listed item]]\n<!-- end of generated part -->\n'
              '\nNative credit.\n\n== Empty listing ==\n{{#cargo_query:tables=Fixture}}')
        lines,links=wiki.guide_prose('Base_items',text)
        shown=' '.join(t for _,t in lines)
        for t in ('Useful introduction.','Useful rule.','Native credit.','Base items category'):self.assertIn(t,shown)
        for t in ('Listed item','Items','Empty listing'):self.assertNotIn(t,shown)
        self.assertNotIn('Listed item',links)

    def test_shared_method_cannot_silently_lose_a_condition(self):
        row={'section':'Item quality and modifiers','family':'reroll: magic item',
             'inputs':['any Weapon (magic)','Oil of Renewal'],
             'outputs':[{'item':'the item rerolled (magic)'}],'condition':'character level above 50'}
        with self.assertRaises(ValueError):player.recipes([row],wiki.Entry)

    def test_prose_paths_default_to_this_checkout_and_accept_overrides(self):
        with patch.dict(wiki.os.environ,{'MXL_WIKI_PAGES':'','MXL_WIKI_LAZ':''}):
            self.assertEqual(wiki.external('MXL_WIKI_PAGES','tools/wiki/pages'),wiki.ROOT/'tools/wiki/pages')
            self.assertEqual(wiki.external('MXL_WIKI_LAZ','tools/wiki/class-texts'),wiki.ROOT/'tools/wiki/class-texts')
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(wiki.os.environ,{'MXL_WIKI_PAGES':temp,'MXL_WIKI_LAZ':temp}):
                self.assertEqual(wiki.external('MXL_WIKI_PAGES','tools/wiki/pages'),Path(temp))
                self.assertEqual(wiki.external('MXL_WIKI_LAZ','tools/wiki/class-texts'),Path(temp))

    def test_checked_in_prose_snapshot_is_complete_and_player_only(self):
        pages=wiki.ROOT/'tools/wiki/pages'
        self.assertEqual(len(list(pages.glob('*.wiki'))),29)
        self.assertFalse(any(p.stem in wiki.SKIP for p in pages.glob('*.wiki')))
        self.assertFalse(any(p.is_dir() for p in pages.iterdir()))
        classes=wiki.ROOT/'tools/wiki/class-texts'
        self.assertEqual({p.name for p in classes.iterdir()},
                         {n+'.html' for n in ('amazon','assassin','barbarian','druid','necromancer','paladin','sorceress','itemonly')})

    def test_templates_and_images(self):
        lines, _ = wiki.markup('{{Hidden|image=lost}}\n{{Item|name=Example|stats=First stat\nSecond stat}}\n{{Note|Read this}}')
        text = ' '.join(t for _, t in lines)
        self.assertNotIn('lost', text)
        for phrase in ('Example', 'First stat', 'Second stat', 'Read this'):
            self.assertIn(phrase, text)

    def test_nested_template_parameters(self):
        calls = list(wiki.templates('{{Uber|name=Test|reward=[[Prize|Gift]]|notes=A{{!}}B}}'))
        self.assertEqual(len(calls), 1)
        kind, fields = wiki.params(calls[0][2])
        self.assertEqual(kind, 'uber')
        self.assertEqual(fields['reward'], '[[Prize|Gift]]')
        self.assertEqual(fields['notes'], 'A|B')

    def test_player_facing_templates(self):
        lines, _ = wiki.markup('{{Port note|Read the [[Guide]].}}\n{{Cube recipe|recipe=Example|inputs=One\nTwo|output=Three|notes=Four}}')
        self.assertIn(('white', 'Read the Guide.'), lines)
        self.assertIn(('white', 'Example | One; Two | Three | Four'), lines)

    def test_clean_fields(self):
        self.assertEqual(wiki.clean('ÿc4Hello\tthere\r\nfriend'), 'Hello there friend')

    def test_tooltip_explicit_stat_value(self):
        import tooltip_audit
        row = {'descval': '1', 'descstrpos': 'fixture'}
        text, kind = tooltip_audit.expected(0, 3, row, {'fixture': 'Example'}, 42)
        self.assertEqual((text, kind), ('42 Example', 'text'))

    def test_release_guard(self):
        self.assertFalse(wiki.unreleased_pending('## Unreleased\n\n## Release\n- old'))
        self.assertTrue(wiki.unreleased_pending('## Unreleased\n- pending feature\n## Release\n'))

    def test_base_modifiers(self):
        original = {'damage': {'one': [10, 20]}, 'defense': [10, 20], 'reqstr': 100, 'durability': 20}
        stats = [{'stat': name, 'lo': lo, 'hi': hi} for name, lo, hi in
                 [('item_maxdamage_percent', 100, 200), ('item_armor_percent', 100, 100),
                  ('item_req_percent', -20, -20), ('maxdurability', 5, 5)]]
        result = wiki.tooltip_base(original, stats)
        self.assertEqual(result['damage']['one'], [20, 60])
        self.assertEqual(result['defense'], [42, 42])
        self.assertEqual(result['reqstr'], 80)
        self.assertEqual(result['durability'], 25)
        self.assertEqual(original['defense'], [10, 20])

    def test_serialization_and_links(self):
        a = wiki.Entry('page', 'Zed\nname', 'A\ttitle', [('gold', 'Hello\tworld')], ['Alpha', 'Missing'])
        b = wiki.Entry('uniq', 'Alpha', 'Unique', [('blue', 'Cold damage')])
        raw = wiki.serialize([a, b])
        self.assertEqual(raw, wiki.serialize([b, a]))
        self.assertIn(b'K\tAlpha\n', raw)
        self.assertNotIn(b'Missing', raw)
        check_format(self, raw)

    def test_serialization_refuses_repeated_names(self):
        with self.assertRaisesRegex(ValueError,'Repeated entry names'):
            wiki.serialize([wiki.Entry('page','Example','A'),wiki.Entry('page','example','B')])


def check_format(test, raw):
    test.assertNotIn(b'\r', raw)
    test.assertTrue(raw.endswith(b'\n'))
    categories, entries, links, current, nlines = [], [], [], None, 0
    arities = {'V': 2, 'C': 3, 'E': 5, 'L': 3, 'K': 2}
    for line in raw.decode('utf-8').split('\n')[:-1]:
        fields = line.split('\t')
        kind = fields[0]
        test.assertIn(kind, arities)
        test.assertEqual(len(fields), arities[kind], line)
        if kind == 'V':
            test.assertEqual(fields[1], '1')
        elif kind == 'C':
            categories.append(fields[1])
        elif kind == 'E':
            if current:
                test.assertGreater(nlines, 0)
            test.assertIn(fields[1], categories)
            test.assertEqual(fields[4], fields[4].lower())
            current, nlines = fields[1:], 0
            entries.append(current)
        elif kind == 'L':
            test.assertIsNotNone(current)
            test.assertIn(fields[1], wiki.COLOURS)
            nlines += 1
        elif kind == 'K':
            test.assertIsNotNone(current)
            links.append(fields[1])
    test.assertGreater(nlines, 0)
    names = {e[1] for e in entries}
    test.assertTrue(set(links) <= names)
    test.assertEqual(categories, [c for c, _ in wiki.CATEGORIES])
    for category in categories:
        names = [e[1].casefold() for e in entries if e[0] == category]
        test.assertEqual(names, sorted(names))
    return entries


@unittest.skipUnless(wiki.OUT.exists(), 'needs tools/build.py data build')
class Built(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = wiki.ROOT / 'work/wiki'
        cls.data = {n:json.loads((folder/(n+'.json')).read_text('utf-8'))
                    for n in ('uniques','sets','runewords','gemwords','bases','cube','monsters','skills')}
        sys.path.insert(0,str(wiki.ROOT/'tools/wiki'))
        # Other test modules can import strings_ns before wiki/items initializes
        # its configured baseline path. Match the export subprocess explicitly.
        import fxpaths
        import strings_ns
        baseline = patch.object(strings_ns, 'D2R_LNG', fxpaths.D2R_DATA/'local/lng')
        baseline.start()
        cls.addClassCleanup(baseline.stop)
        cls.source = player.Sources(cls.data)
        cls.entries = []
        for line in wiki.OUT.read_text('utf-8').splitlines():
            f = line.split('\t')
            if f[0]=='E':
                cls.entries.append(wiki.Entry(f[1],f[2],f[3]))
            elif f[0]=='L':
                cls.entries[-1].lines.append((f[1],f[2]))
        cls.audit = json.loads((folder/'player-audit.json').read_text('utf-8'))

    def test_format_and_counts_against_wiki_json(self):
        entries = check_format(self, wiki.OUT.read_bytes())
        counts = wiki.Counter(e[0] for e in entries)
        folder = wiki.ROOT / 'work/wiki'
        for category, filename in [('set', 'sets'), ('rw', 'runewords'), ('gemw', 'gemwords')]:
            data = json.loads((folder / (filename + '.json')).read_text('utf-8'))
            self.assertEqual(counts[category], len(data), category)
        self.assertEqual(counts['uniq'],len({r['name'].casefold() for r in self.source.uniques}))
        self.assertEqual(counts['base'],len({r['name'].casefold() for r in self.data['bases'] if r['code'] in self.source.tokens}))
        self.assertEqual(counts['cube'],len(player.recipes(self.source.recipes,wiki.Entry)))
        self.assertEqual(self.audit['reachable_recipe_count'],len(self.source.recipes))
        self.assertLess(counts['mon'],len(self.data['monsters']))
        self.assertGreater(counts['uber'], 20)
        self.assertGreater(counts['page'], 20)

    def test_no_name_repeats_in_any_category(self):
        counts = wiki.Counter((e.category,e.name.casefold()) for e in self.entries)
        self.assertEqual([k for k,v in counts.items() if v>1],[])

    def test_built_fields_have_no_forbidden_patterns(self):
        # Include the E search field, not just the rendered L lines.
        for line in wiki.OUT.read_text('utf-8').splitlines():
            f = line.split('\t')
            text = ' '.join(f[2:]) if f[0]=='E' else f[2] if f[0]=='L' else ''
            for pattern in player.FORBIDDEN:
                self.assertIsNone(re.search(pattern,text,re.I),(pattern,text[:200]))

    def test_recipes_are_player_families_with_bounded_expansions(self):
        cube = [e for e in self.entries if e.category=='cube']
        self.assertGreater(len(cube),30)
        self.assertLess(len(cube),75)
        self.assertFalse(any(' -> ' in e.name or ' + ' in e.name for e in cube))
        reroll = next(e for e in cube if e.name=='Reroll a magic item with enhanced damage or defense')
        self.assertLess(len(reroll.lines),10)
        for name in ('Craft a sacred item','Bless a sacred item','Uptier a tiered item'):
            self.assertEqual(sum(e.name==name for e in cube),1)

    def test_no_separate_apply_mystic_orb_entries(self):
        self.assertFalse(any(e.category=='cube' and e.name.startswith('Apply Mystic Orb') for e in self.entries))

    def test_mystic_orbs_include_every_member_and_searchable_effect(self):
        e=next(e for e in self.entries if e.category=='cube' and e.name=='Mystic Orbs')
        text=' '.join(t for _,t in e.lines)
        rows=[r for r in self.data['cube'] if not r.get('decoy') and r.get('orb',{}).get('name')=='Mystic Orb']
        self.assertEqual(len({r['orb']['code'] for r in rows}),140)
        for r in rows:
            if not r.get('condition'):
                for effect in families.effects(r):self.assertIn(effect,text)
        search=next(line.split('\t')[4] for line in wiki.OUT.read_text('utf-8').splitlines()
                    if line.startswith('E\tcube\tMystic Orbs\t'))
        for r in rows:
            if not r.get('condition'):
                for effect in families.effects(r):self.assertIn(effect.lower(),search)
        self.assertEqual(sum('+2 Required Level' in t for _,t in e.lines),1)

    def test_no_invented_orb_qualifier_without_a_game_string(self):
        texts=self.source.item_data.texts.values()
        allowed={wiki.clean(t) for t in texts if 'Mystic Orb (' in t}
        self.assertFalse(allowed)  # current game has no qualified ordinary orb name
        for e in self.entries:
            if e.category=='cube':
                self.assertFalse(any('Mystic Orb (' in t for _,t in e.lines),e.name)

    def test_every_recipe_orb_code_has_exactly_one_member_line(self):
        import cube
        expected={cube.cells(c)[0] for r in self.data['cube'] if not r.get('decoy')
                  for c in r['codes']['inputs']
                  if self.source.item_data.bases.get(cube.cells(c)[0],{}).get('type')=='asaa'}
        coverage=wiki.Counter()
        ordinary=unique=0
        for m in self.audit['orb_members']:
            e=next(e for e in self.entries if e.category=='cube' and
                   e.name==('Mystic Orbs' if m['name']=='Mystic Orb' else 'Unique Mystic Orbs'))
            # Distinguishing description words must begin a single real L line.
            words=[s.strip() for s in m['description'].splitlines() if s.strip() and
                   not s.startswith('Cube ') and not re.fullmatch(r'\+\d+ Required Level',s)]
            prefix='; '.join(words)
            if m['name']!='Mystic Orb':prefix=m['name']+': '+prefix
            hits=[t for _,t in e.lines if t.startswith(prefix+': ') or t.startswith(prefix+' (')]
            self.assertEqual(len(hits),1,(m['codes'],prefix))
            for code in m['codes']:
                coverage[code]+=len(hits)
                raw=self.source.item_data.bases[code]
                self.assertEqual(wiki.clean(self.source.item_data.text(raw['spelldescstr'])),wiki.clean(m['description']))
            if m['name']=='Mystic Orb':ordinary+=1
            else:unique+=1
        self.assertEqual(set(coverage),expected)
        self.assertEqual(set(coverage.values()),{1})
        self.assertEqual((ordinary,unique),(70,30))
        life=next(m for m in self.audit['orb_members'] if '&13' in m['codes'])
        wyrd=next(m for m in self.audit['orb_members'] if '18+' in m['codes'])
        self.assertEqual(life['codes'],['&13','13+'])
        self.assertEqual(wyrd['codes'],['&18','18+'])
        self.assertNotEqual(life['description'],wyrd['description'])

    def test_runeword_allowed_bases_are_resolved_game_names(self):
        data=self.source.item_data
        names={re.sub(r'\s*\((?:\d+|Sacred)\)$','',data.base_name(c)) for c in data.bases}
        for r in self.data['runewords']:
            self.assertTrue(set(r['itypes']+r['etypes'])<=names,r['name'])

    def test_gems_include_every_kind_and_grade_in_one_entry(self):
        e=next(e for e in self.entries if e.category=='cube' and e.name=='Upgrade gems')
        text=' '.join(t for _,t in e.lines)
        rows=[r for r in self.data['cube'] if r['section']=='Gems and runes' and 'rune' not in r['family'].lower()]
        names={o['item'] for r in rows for o in r['outputs']}
        names.update(re.sub(r'^\d+ x ','',t) for r in rows for t in r['inputs'])
        self.assertEqual(len(names),60)
        search=next(line.split('\t')[4] for line in wiki.OUT.read_text('utf-8').splitlines()
                    if line.startswith('E\tcube\tUpgrade gems\t'))
        for name in names:
            self.assertIn(name,text)
            self.assertIn(name.lower(),search)
        self.assertFalse(any(e.category=='cube' and e.name in names for e in self.entries))

    def test_other_shared_methods_are_single_entries(self):
        cube=[e for e in self.entries if e.category=='cube']
        for name in ('Unique Mystic Orbs','Trophies','Alchemy','Reroll an item','Improve item quality',
                     'Make a magic or rare item','Disenchant items'):
            self.assertEqual(sum(e.name==name for e in cube),1,name)
        trophies=next(e for e in cube if e.name=='Trophies')
        text=' '.join(t for _,t in trophies.lines)
        for r in self.source.recipes:
            if r['section']=='Mystic Orbs' and r['inputs'][1].endswith(' Trophy'):
                self.assertIn(r['inputs'][1],text)
                self.assertIn(r['inputs'][0],text)

    def test_category_guides_do_not_repeat_member_lists(self):
        for stem in wiki.CATEGORY_GUIDES:
            e=next(e for e in self.entries if e.category=='page' and e.name==stem.replace('_',' '))
            self.assertLess(len(e.lines),35,e.name)
            self.assertTrue(e.lines[-1][1].startswith('Look in the '),e.name)
        cube=next(e for e in self.entries if e.category=='page' and e.name=='Horadric Cube')
        self.assertTrue(any('Crafting Points' in t for _,t in cube.lines))
        self.assertFalse(any(t.startswith('Inputs:') for _,t in cube.lines))

    def test_retired_charms_and_medallion_provenance(self):
        for r in self.source.uniques:
            self.assertTrue(player.active(self.source.ur[player.unique_key(r)]),r['name'])
            self.assertTrue(player.unique_key(r) in self.source.generic or r['key'] in self.source.tokens,r['name'])
        names = {e.name for e in self.entries if e.category=='uniq'}
        self.assertNotIn('Hard Mode Charm',names)
        self.assertNotIn('hard mode charm',wiki.OUT.read_text('utf-8').lower())
        self.assertIn('I Am Rich',names)
        self.assertIn('Crystalline Flame Medallion',names)
        kept = self.audit['retained_unique_keys']
        self.assertIn('mxl2012:Xtalline2',kept)
        self.assertNotIn('mxl2012:XtallineFlameMedaillon',kept)
        self.assertNotIn('mxl2012:JollyRoger',kept)
        self.assertIn('mxl2012:NewSuperGem',kept)

    def test_cornerstone_lists_all_obtainable_skills_once(self):
        entries = [e for e in self.entries if e.category=='uniq' and e.name=='Cornerstone of the World']
        self.assertEqual(len(entries),1)
        self.assertEqual(self.audit['cornerstone_variants'],149)
        self.assertEqual(sum(' to ' in t and t.startswith('+1 to ') for _,t in entries[0].lines),149)
        for name in ('Amazon','Assassin','Barbarian','Druid','Necromancer','Paladin','Sorceress'):
            self.assertIn(('gold',name),entries[0].lines)

    def test_subtitles_use_tooltip_labels(self):
        for e in self.entries:
            if e.category=='uniq':
                self.assertNotRegex(e.subtitle,r'Reward Charm|Challenge Charm|Craft Sacred')
        r = next(r for r in self.source.uniques if r['name']=='Crystalline Flame Medallion')
        self.assertEqual(self.source.label(r),'Charm')

    def test_skills_have_a_real_player_source_and_subtitle(self):
        skills = player.player_skills(self.source,wiki.external('MXL_WIKI_LAZ','tools/wiki/class-texts'))
        for r in skills:
            if not r['class']:
                self.assertTrue(str(r['id']) in self.source.granted or r['key'] in self.source.granted,r['name'])
            else:
                self.assertTrue(r['tree'],r['name'])
        expected = {r['name'] for r in skills}
        actual = {e.name for e in self.entries if e.category=='skill'}
        self.assertEqual(actual,expected)
        for e in self.entries:
            if e.category=='skill':
                self.assertTrue(e.subtitle=='Item skill' or re.fullmatch(r'(?:'+'|'.join(player.CLASSES.values())+r'), .+, level \d+',e.subtitle),e.subtitle)
        for name in ('Ambush',"Devil's Fang Totem",'Javelin'):
            e = next(e for e in self.entries if e.category=='skill' and e.name==name)
            self.assertEqual(e.subtitle,'Item skill')

    def test_monsters_are_located_and_player_relevant(self):
        monsters = [e for e in self.entries if e.category=='mon']
        self.assertGreater(len(monsters),300)
        for e in monsters:
            self.assertTrue(any(t.startswith('Found in: ') for _,t in e.lines),e.name)
            self.assertNotRegex(e.subtitle,r'Normal, Animal|dummy|null_monster')
        e = next(e for e in monsters if e.name=='Uldyssian, Dark Edyrem King')
        self.assertEqual(e.subtitle,'Inner Cloister')
        self.assertTrue(any(t.startswith('Resistances: ') for _,t in e.lines))

    def test_monster_effects_never_fall_back_to_internal_skill_names(self):
        for e in self.entries:
            if e.category=='mon':
                for _,text in e.lines:
                    self.assertIsNone(self.source.unnamed_pattern.search(text),(e.name,text))

    def test_welcome_credit_occurs_only_on_welcome(self):
        credit = 'Median XL is the work of Brother Laz.'
        entries = [e for e in self.entries if any(t==credit for _,t in e.lines)]
        self.assertEqual([(e.category,e.name) for e in entries],[('page','Welcome')])
        self.assertEqual(len(entries[0].lines),3)

    def test_map_labels_are_not_used_as_area_names(self):
        mon = [e for e in self.entries if e.category=='mon']
        areas = {self.source.area(lid) for lid in self.source.levels}-{''}
        for e in mon:
            for _,text in e.lines:
                if text.startswith('Found in: '):
                    self.assertTrue(set(text[10:].split(', ')) <= areas,text)

    def test_two_exports_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = [Path(temp) / name for name in ('one.tsv', 'two.tsv')]
            for path in paths:
                result = subprocess.run([sys.executable, str(wiki.ROOT / 'tools/wikipanel_export.py'), '--out', str(path)],
                                        capture_output=True, cwd=wiki.ROOT)
                self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
            self.assertEqual(paths[0].read_bytes(), paths[1].read_bytes())

    def test_build_order(self):
        import build
        for steps in (build.STEPS,):
            names = [s[0] for s in steps]
            self.assertEqual(names[names.index('devmenu_catalog.py') + 1], 'wikipanel_export.py')

    def test_install_and_package_carry_table(self):
        import install_mod
        import package_release
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source'
            (source / 'global/tiles').mkdir(parents=True)
            relative = Path('mxl2012-wiki/wiki.tsv')
            (source / relative.parent).mkdir()
            content = wiki.OUT.read_bytes()
            (source / relative).write_bytes(content)
            with patch.object(install_mod, 'SRC', source), patch.object(install_mod, 'MXL_GLOBAL', root / 'empty'):
                install_mod.build_data(root / 'installed', root / 'game')
            self.assertEqual((root / 'installed' / relative).read_bytes(), content)
            with patch.object(install_mod, 'write_mod_files'), patch.object(package_release.legacy_fonts, 'check_tree'):
                package_release.stage(root / 'package', 'test', root / 'dummy.dll', root / 'game', data_from=source)
            self.assertEqual((root / 'package' / (package_release.NAME + '.mpq') / 'data' / relative).read_bytes(), content)


if __name__ == '__main__':
    unittest.main()
