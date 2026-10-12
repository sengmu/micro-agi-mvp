"""Fail CI if the app-owned Chaquopy payload omits key resources or ships private data."""

from io import BytesIO
from pathlib import Path, PurePosixPath
import re
import sys
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parent
APK = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "app/build/outputs/apk/debug/app-debug.apk"
REQUIRED = {
    "app.py", "mobile_entry.py", "index.html", "script.js",
    "companion-room-night.png", "Hiyori/Hiyori.model3.json",
}
PRIVATE_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".log", ".key", ".jks", ".keystore"}


def verify(apk_path: Path) -> None:
    with ZipFile(apk_path) as outer:
        with ZipFile(BytesIO(outer.read("assets/chaquopy/app.imy"))) as app:
            names = set(app.namelist())
    missing = REQUIRED - names
    if missing:
        raise ValueError(f"Missing app resources: {', '.join(sorted(missing))}")
    private = []
    for name in names:
        if name.endswith("/"):
            continue
        path = PurePosixPath(name)
        if (any(part.startswith(".") for part in path.parts)
                or path.suffix.lower() in PRIVATE_SUFFIXES
                or re.search(r"(?:^|/)\.env(?:\.|$)", name, re.IGNORECASE)):
            private.append(name)
    if private:
        raise ValueError(f"Private runtime files in APK: {', '.join(sorted(private))}")
    print(f"Verified {len(names)} app-owned APK entries; required assets present, no private filenames")


if __name__ == "__main__":
    verify(APK)
