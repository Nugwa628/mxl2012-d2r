from pathlib import Path
import sys
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: F401 (repository-local temporary files)
import controller_skill_profile as profile


def skill(number=500, **values):
    return {'*Id': str(number), 'skill': 'Test', 'skilldesc': 'test', **values}


class ControllerProfileTests(unittest.TestCase):
    def test_inference_precedence(self):
        cases = [({'passive': '1', 'srvmissile': 'bolt'}, ('passive/inactive', 'disabled', 'snap')),
                 ({'aura': '1', 'aurastate': 'aura'}, ('aura', False, 'ground')),
                 ({'TargetCorpse': '1', 'summon': 'pet'}, ('native-unit', False, 'snap')),
                 ({'range': 'h2h', 'srvmissile': 'bolt'}, ('melee', False, 'snap')),
                 ({'warp': '1', 'aurastate': 'buff'}, ('movement', True, 'ground')),
                 ({'summon': 'pet', 'aurastate': 'buff'}, ('summon', True, 'ground')),
                 ({'srvdofunc': '22', 'srvmissilea': 'nova'}, ('self-area', False, 'ground')),
                 ({'srvdofunc': '18', 'aurastate': 'buff'}, ('self-buff', False, 'ground')),
                 ({'srvdofunc': '28', 'srvmissilea': 'trap'}, ('area/placement', True, 'snap')),
                 ({'srvmissileb': 'bolt'}, ('projectile', True, 'snap')),
                 ({'range': 'rng '}, ('projectile', True, 'snap')),
                 ({}, ('native-review', False, 'snap'))]
        for row, expected in cases:
            with self.subTest(row=row):
                self.assertEqual(profile.infer(row), expected)

    def test_schema_catalog_replacement_and_high_id(self):
        text, entries = profile.generate([skill(12), skill(2000, passive='1')], [], {})
        data = tomllib.loads(text)['aim']
        self.assertIs(data['amazon']['12'], False)  # cancels upstream enabled default
        self.assertEqual(data['custom']['2000'], 'disabled')
        self.assertEqual(data['sorceress']['43'], 'disabled')  # absent native-unit special
        self.assertEqual(data['leading']['12'], 0)  # must override shipped leading
        self.assertEqual(data['leading_max_ms']['39'], 600)
        self.assertEqual(data['leading_max_tiles']['45'], 3)
        self.assertEqual(len(entries), 241)  # cap counts union, not maximum ID
        for entry in entries:
            self.assertIn(str(entry['id']), data[entry['section']])
            self.assertEqual(data['targeting'][str(entry['id'])], entry['targeting'])
        self.assertEqual(profile.generate([skill(2000, passive='1'), skill(12)], [], {})[0], text)

    def test_name_override_tracks_id(self):
        tuning = {'Test': {'aim': True, 'targeting': 'ground', 'reason': 'reviewed placement'}}
        for number in (800, 900):
            text, _ = profile.generate([skill(number)], [], tuning)
            self.assertIs(tomllib.loads(text)['aim']['custom'][str(number)], True)
        with self.assertRaises(ValueError):
            profile.generate([skill(800, skill='Renamed')], [], tuning)

    def test_bad_data_and_capacity_fail_closed(self):
        for rows in ([], [skill(0), skill(0)], [skill(65535)], [skill(-1)],
                     [skill(i) for i in range(1000, 1785)]):
            with self.subTest(size=len(rows)), self.assertRaises(ValueError):
                profile.generate(rows, [], {})
        with self.assertRaises(ValueError):
            profile.generate([skill()], [], {'Test': {'aim': 'snap', 'targeting': 'snap', 'reason': 'bad'}})

    def test_related_description(self):
        self.assertEqual(profile.infer({}, {'descmissile1': 'bolt'}),
                         ('projectile-description', True, 'snap'))

    def test_pinned_catalog_shape(self):
        self.assertEqual(len(profile.CATALOG), 240)
        self.assertEqual(profile.CATALOG['151'], 'barbarian')
        self.assertEqual(profile.CATALOG['373'], 'warlock')


if __name__ == '__main__':
    unittest.main()
