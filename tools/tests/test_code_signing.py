"""The downloader's signing set-up stays consistent (the SignPath parts are on hold, kept for a possible application) (docs/code-signing-policy.md): the version resource, the SignPath
artifact configuration and tools/sign_launcher.py name the same product; the GitHub workflow builds from source, keeps the
token in a secret and checks SignPath's result with sign_launcher.py --signed; every file the exe embeds has an
open-source licence recorded in NOTICE.md."""
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import sign_launcher  # noqa: E402

RC = REPO / "launcher" / "res" / "launcher.rc"
# the workflow runs in the downloader's own repository (tools/downloader_repo.py exports downloader-repo/ to its root)
WORKFLOW = REPO / "downloader-repo" / ".github" / "workflows" / "sign-launcher.yml"
DOWNLOADER_NOTICE = REPO / "downloader-repo" / "NOTICE.md"
ARTIFACT_CONFIG = REPO / "launcher" / "signpath-artifact-configuration.xml"
NS = {"sp": "http://signpath.io/artifact-configuration/v1"}


def rc_value(key: str) -> str:
    m = re.search(r'VALUE "' + key + r'", ("[^"]*"|\w+)', RC.read_text(encoding="utf-8"))
    assert m, key
    return m.group(1)


class CodeSigningTest(unittest.TestCase):
    def test_product_name_everywhere(self):
        self.assertEqual(rc_value("ProductName"), f'"{sign_launcher.PRODUCT}"')
        pe = ET.parse(ARTIFACT_CONFIG).getroot().find("sp:zip-file/sp:pe-file", NS)
        self.assertIsNotNone(pe)
        self.assertEqual(pe.get("path"), sign_launcher.NAME)
        self.assertEqual(pe.get("product-name"), sign_launcher.PRODUCT)
        self.assertEqual(pe.get("product-version"), "${version}")
        self.assertIsNotNone(pe.find("sp:authenticode-sign", NS))

    def test_one_version_for_file_and_product(self):
        self.assertEqual(rc_value("FileVersion"), "MXL_LV_STR")
        self.assertEqual(rc_value("ProductVersion"), "MXL_LV_STR")
        self.assertEqual(rc_value("OriginalFilename"), f'"{sign_launcher.NAME}"')

    def test_workflow(self):
        wf = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("runs-on: windows-latest", wf)  # SignPath Foundation: GitHub-hosted runners only
        self.assertIn("cmake -S launcher -B build/launcher", wf)
        self.assertIn("api-token: ${{ secrets.SIGNPATH_API_TOKEN }}", wf)
        self.assertIn("signpath/github-action-submit-signing-request@", wf)
        self.assertIn("github-artifact-id: ${{ steps.upload-unsigned.outputs.artifact-id }}", wf)
        self.assertIn("tools/sign_launcher.py --exe $env:EXE --signed", wf)
        self.assertIn("version: ${{ toJSON(steps.version.outputs.version) }}", wf)
        self.assertIn('python -m unittest discover -s tools -p "test_*.py"', wf)
        self.assertNotIn("paths:", wf)  # the downloader repository is only the downloader: every push builds
        self.assertFalse((REPO / ".github" / "workflows" / "sign-launcher.yml").exists())  # never on the mod's mirror
        # the only SignPath values in the file are references to secrets and variables
        for line in wf.splitlines():
            m = re.match(r"\s*(api-token|organization-id|project-slug|signing-policy-slug):\s*(.*)", line)
            if m:
                self.assertRegex(m.group(2), r"^\$\{\{ (secrets|vars)\.SIGNPATH_[A-Z_]+ \}\}$", line)

    def test_embedded_files_are_open_source(self):
        rc = RC.read_text(encoding="utf-8")
        embedded = re.findall(r'^\d+ (?:\d+|ICON) "([^"]+)"', rc, re.M)
        notice = (REPO / "NOTICE.md").read_text(encoding="utf-8")
        self.assertNotIn("exocet.ttf", embedded)
        for name in embedded:
            self.assertTrue((RC.parent / name).is_file(), name)
        for font in [n for n in embedded if n.endswith(".ttf")]:
            row = next((line for line in notice.splitlines() if line.startswith(f"| `{font}`")), "")
            self.assertRegex(row, r"SIL Open Font License|Apache License 2\.0", font)
            # the downloader repository's own NOTICE lists it too
            row = next((line for line in DOWNLOADER_NOTICE.read_text(encoding="utf-8").splitlines()
                        if line.startswith(f"| `launcher/res/{font}`")), "")
            self.assertRegex(row, r"SIL Open Font License|Apache License 2\.0", font)
        self.assertTrue((RC.parent / "OFL-CinzelDecorative.txt").is_file())
        self.assertNotIn("Font Awesome", (RC.parent / "comment.svg").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
