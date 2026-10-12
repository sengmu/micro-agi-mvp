"""Exercise both pass and fail paths of the post-build APK privacy gate."""

from io import BytesIO
from pathlib import Path
import runpy
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
checker = runpy.run_path(str(ROOT / "android_host/verify-apk-contents.py"))
verify = checker["verify"]
REQUIRED = checker["REQUIRED"]


class ApkContentsTests(unittest.TestCase):
    def make_apk(self, entries):
        temp = tempfile.TemporaryDirectory()
        apk = Path(temp.name) / "test.apk"
        payload = BytesIO()
        with ZipFile(payload, "w") as inner:
            for name in entries:
                inner.writestr(name, b"test")
        with ZipFile(apk, "w") as outer:
            outer.writestr("assets/chaquopy/app.imy", payload.getvalue())
        self.addCleanup(temp.cleanup)
        return apk

    def test_required_resources_pass(self):
        verify(self.make_apk(REQUIRED))

    def test_missing_background_fails(self):
        with self.assertRaisesRegex(ValueError, "companion-room-night.png"):
            verify(self.make_apk(REQUIRED - {"companion-room-night.png"}))

    def test_private_runtime_file_fails(self):
        for private in (".env", "data/chat.sqlite3", "secrets/wallet.key"):
            with self.subTest(private=private), self.assertRaisesRegex(ValueError, "Private runtime"):
                verify(self.make_apk(REQUIRED | {private}))


if __name__ == "__main__":
    unittest.main()
