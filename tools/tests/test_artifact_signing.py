"""tools/artifact_signing.py: the Azure Artifact Signing set-up for the downloader (docs/launcher.md "Release and signing").
No Azure calls: the account, metadata.json, credential choice, signtool lookup, the pinned dlib package and the command
that tools/sign_launcher.py runs."""
import hashlib
import io
import json
import shlex
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import artifact_signing as az  # noqa: E402

ENV = {"MXL_SIGNING_ENDPOINT": "https://weu.codesigning.azure.net/", "MXL_SIGNING_ACCOUNT": "example-account",
       "MXL_SIGNING_PROFILE": "example-profile"}


class AccountTest(unittest.TestCase):
    def test_from_environment_defaults_to_cli(self):
        acc = az.load_account(environ=ENV)
        self.assertEqual(acc, {"endpoint": ENV["MXL_SIGNING_ENDPOINT"], "account": "example-account",
                               "profile": "example-profile", "auth": "cli"})

    def test_config_file_wins(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "account.json"
            cfg.write_text(json.dumps({"endpoint": "https://eus.codesigning.azure.net", "account": "a", "profile": "p",
                                       "auth": "env"}), encoding="utf-8")
            acc = az.load_account(cfg, environ=ENV)
        self.assertEqual((acc["endpoint"], acc["account"], acc["auth"]), ("https://eus.codesigning.azure.net", "a", "env"))

    def test_refusals(self):
        with self.assertRaisesRegex(az.SigningError, "missing account, profile"):
            az.load_account(environ={"MXL_SIGNING_ENDPOINT": ENV["MXL_SIGNING_ENDPOINT"]})
        for bad in ("http://weu.codesigning.azure.net/", "https://weu.codesigning.azure.net.evil.example/",
                    "https://example.org/"):
            with self.assertRaisesRegex(az.SigningError, "endpoint"):
                az.load_account(environ={**ENV, "MXL_SIGNING_ENDPOINT": bad})
        with self.assertRaisesRegex(az.SigningError, "auth"):
            az.load_account(environ={**ENV, "MXL_SIGNING_AUTH": "browser"})

    def test_metadata_keeps_only_the_chosen_credential(self):
        for auth, keep in (("cli", "AzureCliCredential"), ("env", "EnvironmentCredential")):
            m = az.metadata(az.load_account(environ={**ENV, "MXL_SIGNING_AUTH": auth}))
            self.assertEqual(m["Endpoint"], ENV["MXL_SIGNING_ENDPOINT"])
            self.assertEqual(m["CodeSigningAccountName"], "example-account")
            self.assertEqual(m["CertificateProfileName"], "example-profile")
            self.assertEqual(set(m["ExcludeCredentials"]) | {keep}, set(az.CREDENTIALS))
            self.assertNotIn(keep, m["ExcludeCredentials"])
            self.assertIn("VisualStudioCredential", m["ExcludeCredentials"])  # never another sign-in on the PC
            self.assertIn("InteractiveBrowserCredential", m["ExcludeCredentials"])

    def test_auth_problems(self):
        env_acc = az.load_account(environ={**ENV, "MXL_SIGNING_AUTH": "env"})
        self.assertIn("AZURE_CLIENT_SECRET", az.auth_problems(env_acc, environ={"AZURE_TENANT_ID": "t", "AZURE_CLIENT_ID": "c"})[0])
        self.assertEqual(az.auth_problems(env_acc, environ={"AZURE_TENANT_ID": "t", "AZURE_CLIENT_ID": "c",
                                                           "AZURE_CLIENT_SECRET": "s"}), [])
        cli_acc = az.load_account(environ=ENV)
        self.assertIn("az", az.auth_problems(cli_acc, which=lambda n: None)[0])
        self.assertEqual(az.auth_problems(cli_acc, which=lambda n: "C:/az.cmd"), [])


class ToolsTest(unittest.TestCase):
    def test_find_signtool_takes_the_newest_new_enough_sdk(self):
        with tempfile.TemporaryDirectory() as d:
            kits = Path(d)
            for v in ("10.0.19041.0", "10.0.22621.0", "10.0.26100.0", "10.0.28000.0", "tools"):
                (kits / v / "x64").mkdir(parents=True)
            for v in ("10.0.19041.0", "10.0.22621.0", "10.0.26100.0"):
                (kits / v / "x64" / "signtool.exe").write_bytes(b"MZ")
            self.assertEqual(az.find_signtool(kits, environ={}), kits / "10.0.26100.0" / "x64" / "signtool.exe")
            (kits / "10.0.22621.0" / "x64" / "signtool.exe").unlink()
            (kits / "10.0.26100.0" / "x64" / "signtool.exe").unlink()
            with self.assertRaisesRegex(az.SigningError, "no x64 signtool"):
                az.find_signtool(kits, environ={})
            own = kits / "own-signtool.exe"
            own.write_bytes(b"MZ")
            self.assertEqual(az.find_signtool(kits, environ={"MXL_SIGNTOOL": str(own)}), own)

    def test_dotnet_runtimes(self):
        class R:
            stdout = ("Microsoft.AspNetCore.App 8.0.8 [x]\nMicrosoft.NETCore.App 6.0.36 [C:\\dotnet]\n"
                      "Microsoft.NETCore.App 8.0.8 [C:\\dotnet]\n")
        self.assertEqual(az.dotnet_runtimes(run=lambda *a, **k: R()), ["6.0.36", "8.0.8"])

        def missing(*a, **k):
            raise FileNotFoundError
        self.assertEqual(az.dotnet_runtimes(run=missing), [])

    def test_install_dlib_checks_the_hash_and_takes_only_bin_x64(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("bin/x64/Azure.CodeSigning.Dlib.dll", b"MZ dlib")
            z.writestr("bin/x64/Azure.Core.dll", b"MZ core")
            z.writestr("bin/x86/Azure.CodeSigning.Dlib.dll", b"MZ x86")
            z.writestr("bin/x64/../../evil.dll", b"no")
            z.writestr("lib/net8.0/other.dll", b"no")
        data = buf.getvalue()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(az.SigningError, "sha256"):
                az.install_dlib(data, d, sha="0" * 64)
            out = az.install_dlib(data, d, sha=hashlib.sha256(data).hexdigest())
            self.assertEqual(sorted(p.name for p in out.iterdir()), ["Azure.CodeSigning.Dlib.dll", "Azure.Core.dll"])
            self.assertFalse((Path(d) / "evil.dll").exists())
            self.assertEqual(out, az.dlib_dir(d))

    def test_pinned_package_is_a_net8_build(self):
        self.assertEqual(az.DLIB_PACKAGE, "Microsoft.ArtifactSigning.Client")
        self.assertRegex(az.DLIB_SHA256, r"^[0-9a-f]{64}$")
        self.assertEqual(az.DLIB_RUNTIME, "8.")


class CommandTest(unittest.TestCase):
    def test_sign_launcher_splits_the_command_into_the_signtool_call(self):
        signtool = Path(r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe")
        dlib = Path(r"C:\work dir\bin\x64\Azure.CodeSigning.Dlib.dll")
        meta = Path(r"C:\work dir\metadata.json")
        cmd = az.command(signtool, dlib, meta)
        # what tools/sign_launcher.py does with --command
        parts = [p[1:-1] if len(p) > 1 and p[0] == p[-1] == '"' else p for p in shlex.split(cmd, posix=False)]
        parts = [p.replace("{file}", r"C:\out\D2R-XL-2012-Downloader.exe") for p in parts]
        self.assertEqual(parts, [str(signtool), "sign", "/v", "/fd", "SHA256", "/tr", "http://timestamp.acs.microsoft.com",
                                 "/td", "SHA256", "/dlib", str(dlib), "/dmdf", str(meta),
                                 r"C:\out\D2R-XL-2012-Downloader.exe"])

    def test_metadata_file_is_written_outside_git(self):
        with tempfile.TemporaryDirectory() as d:
            p = az.write_metadata(az.load_account(environ=ENV), d)
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["CodeSigningAccountName"], "example-account")
        self.assertEqual(az.WORK.relative_to(az.ROOT).parts[0], "work")  # git-ignored


class CiTemplateTest(unittest.TestCase):
    TEMPLATE = az.ROOT / "docs" / "ci" / "artifact-signing.github.yml"

    def test_template_is_inactive_and_has_no_ids(self):
        wf = self.TEMPLATE.read_text(encoding="utf-8")
        self.assertTrue(wf.startswith("# NOT ACTIVE."))
        self.assertFalse(list((az.ROOT / ".github" / "workflows").glob("*sign*")))  # nothing signs from .github
        self.assertIn("azure/artifact-signing-action@v", wf)
        self.assertIn("timestamp-rfc3161: http://timestamp.acs.microsoft.com", wf)
        self.assertIn("tools/sign_launcher.py --exe $env:EXE --signed", wf)
        self.assertIn("id-token: write", wf)
        for line in wf.splitlines():
            key = line.split(":", 1)[0].strip()
            if key in ("client-id", "tenant-id", "subscription-id", "endpoint", "signing-account-name",
                       "certificate-profile-name"):
                self.assertRegex(line.split(":", 1)[1].strip(), r"^\$\{\{ (secrets|vars)\.[A-Z_]+ \}\}$", line)


if __name__ == "__main__":
    unittest.main()
