"""Tests for literal documentation references."""
import sys
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401
import check_docs_links as checker


class DocsLinksTests(unittest.TestCase):
    def test_exit_status(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'docs').mkdir()
            doc = root / 'README.md'
            for content, status in (('[broken](missing.md)', 1), ('Plain text', 0)):
                doc.write_text(content, encoding='utf-8')
                with patch.object(sys, 'argv', ['check_docs_links.py', '--root', folder]):
                    with redirect_stdout(StringIO()):
                        self.assertEqual(checker.main(), status)

    def test_links_and_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'docs').mkdir()
            (root / 'tools').mkdir()
            (root / 'tools/ok.py').touch()
            (root / 'docs/target.md').write_text('# Hello, `World`!\n# Hello, `World`!\n', encoding='utf-8')
            doc = root / 'docs/source.md'
            doc.write_text('[ok](target.md#hello-world) [duplicate](target.md#hello-world-1)\n'
                           '[bad](target.md#absent) [gone](gone.md)\n'
                           '`tools/ok.py` `tools/missing.py`\n'
                           '[web](https://example.org/no) `work/generated.txt` `tools/*.py`\n'
                           '```md\n[example](gone.md) `tools/no.py`\n```\n', encoding='utf-8')
            self.assertEqual(checker.findings(root, doc), [
                (2, 'missing file', 'gone.md'), (2, 'missing heading', 'target.md#absent'),
                (3, 'missing repo path', 'tools/missing.py')])

    def test_local_encoded_and_setext_anchors(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            doc = root / 'README.md'
            doc.write_text('A title\n=======\n[local](#a-title) [bad](#no)\n'
                           '[encoded](other%20file.md#heading)\n', encoding='utf-8')
            (root / 'other file.md').write_text('# Heading\n', encoding='utf-8')
            self.assertEqual(checker.findings(root, doc), [(3, 'missing heading', '#no')])

    def test_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'docs').mkdir()
            for name in ('bugs.md', 'unported.md', 'PLAN.md', 'setup.md'):
                (root / 'docs' / name).touch()
            self.assertEqual([p.name for p in checker.documents(root)], ['README.md', 'setup.md'])


if __name__ == '__main__':
    unittest.main()
