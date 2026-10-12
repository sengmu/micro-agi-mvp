"""Keep Android CI triggers aligned with files actually bundled in the APK."""

from fnmatch import fnmatchcase
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
GRADLE = (ROOT / "android_host/app/build.gradle").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github/workflows/build-agi-bot.yml").read_text(
    encoding="utf-8"
)


class AndroidCiTests(unittest.TestCase):
    def test_launcher_uses_project_adaptive_icon(self):
        manifest = ET.parse(ROOT / "android_host/app/src/main/AndroidManifest.xml")
        application = manifest.getroot().find("application")
        android = "{http://schemas.android.com/apk/res/android}"
        self.assertEqual(application.attrib[android + "icon"], "@mipmap/ic_launcher")
        self.assertEqual(application.attrib[android + "roundIcon"], "@mipmap/ic_launcher")
        icon = ET.parse(ROOT / "android_host/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml")
        self.assertEqual(icon.getroot().tag, "adaptive-icon")
        self.assertIsNotNone(icon.getroot().find("monochrome"))
        self.assertTrue((ROOT / "android_host/app/src/main/res/drawable/ic_launcher_foreground.xml").is_file())
        self.assertTrue((ROOT / "android_host/app/src/main/res/drawable/ic_launcher_background.xml").is_file())
        self.assertTrue((ROOT / "android_host/app/src/main/res/drawable/ic_launcher_monochrome.xml").is_file())

    def test_release_build_rejects_temporary_unsafe_eval_policy(self):
        self.assertIn("tasks.register('checkReleaseCsp')", GRADLE)
        self.assertIn("backend.contains(\"'unsafe-eval'\")", GRADLE)
        self.assertIn("it.name == 'preReleaseBuild'", GRADLE)
        self.assertIn("dependsOn(checkReleaseCsp)", GRADLE)

    def test_every_embedded_file_triggers_push_and_pull_request_builds(self):
        bundle = GRADLE.split("def embeddedFiles = [", 1)[1].split("\n]", 1)[0]
        files = re.findall(r"'([^']+)'", bundle)
        self.assertTrue(files)

        push = WORKFLOW.split("  push:\n", 1)[1].split("  pull_request:\n", 1)[0]
        pull = WORKFLOW.split("  pull_request:\n", 1)[1].split("\njobs:\n", 1)[0]
        for event, block in (("push", push), ("pull_request", pull)):
            paths = block.split("    paths:\n", 1)[1].split("    branches:\n", 1)[0]
            patterns = re.findall(r'^      - "([^"]+)"$', paths, re.MULTILINE)
            for file in files:
                with self.subTest(event=event, file=file):
                    self.assertTrue(
                        any(fnmatchcase(file, pattern) for pattern in patterns),
                        f"{file} will not trigger an Android {event} build",
                    )

    def test_embedded_file_list_excludes_private_runtime_data(self):
        bundle = GRADLE.split("def embeddedFiles = [", 1)[1].split("\n]", 1)[0]
        files = re.findall(r"'([^']+)'", bundle)
        self.assertEqual(len(files), len(set(files)))
        for file in files:
            with self.subTest(file=file):
                parts = Path(file).parts
                self.assertFalse(Path(file).is_absolute())
                self.assertNotIn("..", parts)
                self.assertFalse(any(part.startswith(".") for part in parts))
                self.assertFalse(any(part.lower() in {"node_modules", "build", "logs"}
                                     for part in parts))
                self.assertNotIn(Path(file).suffix.lower(),
                                 {".env", ".db", ".sqlite", ".sqlite3", ".log",
                                  ".key", ".pem", ".jks", ".keystore"})

    def test_bundled_javascript_has_ci_syntax_checks(self):
        for file in ("script.js", "solana-wallet.js", "sw.js",
                     "android_host/check-assetlinks.js"):
            self.assertIn(f"node --check {file}", WORKFLOW)

    def test_background_initialization_regression_runs_in_ci(self):
        self.assertIn("node --test tests/test_background_init.js", WORKFLOW)

    def test_android_lint_runs_before_apk_build(self):
        self.assertIn(":app:lintDebug --no-daemon", WORKFLOW)
        self.assertLess(WORKFLOW.index(":app:lintDebug --no-daemon"),
                        WORKFLOW.index(":app:assembleDebug --stacktrace"))

    def test_built_apk_privacy_check_runs_before_upload(self):
        self.assertIn("python3 android_host/verify-apk-contents.py", WORKFLOW)
        self.assertLess(WORKFLOW.index("python3 android_host/verify-apk-contents.py"),
                        WORKFLOW.index("actions/upload-artifact@v4"))

    def test_ci_compiles_unsigned_release_without_uploading_it(self):
        self.assertIn(":app:assembleRelease --no-daemon", WORKFLOW)
        release_apk = "android_host/app/build/outputs/apk/release/app-release-unsigned.apk"
        self.assertIn("python3 android_host/verify-apk-contents.py " + release_apk,
                      WORKFLOW)
        upload = WORKFLOW.split("- name: Upload APK artifact", 1)[1]
        self.assertNotIn("app-release-unsigned.apk", upload)


if __name__ == "__main__":
    unittest.main()
