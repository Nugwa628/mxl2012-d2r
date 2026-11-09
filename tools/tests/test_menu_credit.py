import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp
import menu_credit


class MenuCreditTest(unittest.TestCase):
    def test_generated_ribbon_preserves_controls_and_localizes_credit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'ribbon.json'
            source.write_text(json.dumps({'children': [{'name': 'Ribbon', 'children': [
                {'name': 'Settings', 'fields': {'textString': '@OptionsHD', 'rect': {'y': 820}}}]}]}))
            menu_credit.build(source, root)
            panel = json.loads((root / 'global/ui/layouts/mainmenubuttonribbonhd.json').read_text())
            children = {c['name']: c for c in panel['children'][0]['children']}
            credit = children['MedianMenuCredit']['fields']
            self.assertEqual(credit['text'], '@' + menu_credit.KEY)
            self.assertLess(credit['rect']['y'] + credit['rect']['height'], children['Settings']['fields']['rect']['y'])
            self.assertGreater(credit['rect']['y'], 606)
            self.assertEqual(children['Settings']['fields']['textString'], '@d2r:OptionsHD')
            records = json.loads((root / 'local/lng/strings/mxl2012/menu_credit.json').read_text())
            self.assertEqual(records, [{'Key': menu_credit.KEY.split(':', 1)[1], **dict.fromkeys(menu_credit.LANGS, menu_credit.TEXT)}])
            self.assertEqual(len(menu_credit.LANGS), 13)
            self.assertEqual(menu_credit.TEXT.splitlines(), ['Median XL 2012', 'By BrotherLaz', '(D2R Fan Port)'])
            self.assertEqual(credit['style']['options']['newlineHandling'], 'standard')

    def test_ribbon_audit_still_rejects_unresolved_and_unqualified_keys(self):
        import text_audit
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'mainmenubuttonribbonhd.json').write_text(
                '{"text": "@mxl2012:MenuCredit", "bad": "@mxl2012:Absent", "old": "@MenuCredit"}')
            strings = text_audit.Strings({'menucredit': menu_credit.TEXT}, set(), {})
            findings = text_audit.audit_layouts(root, strings)
            self.assertEqual([f.kind for f in findings], ['layout-key-missing', 'layout-at-key'])


if __name__ == '__main__':
    unittest.main()
