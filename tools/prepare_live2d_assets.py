"""Restore third-party runtime assets locally from this application's APK."""
import argparse
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with ZipFile(args.apk) as outer:
        with ZipFile(BytesIO(outer.read('assets/chaquopy/app.imy'))) as payload:
            restored = []
            for name in payload.namelist():
                if not (name == 'live2dcubismcore.min.js' or name.startswith('Hiyori/')):
                    continue
                pure = PurePosixPath(name)
                if pure.is_absolute() or '..' in pure.parts or name.endswith('/'):
                    continue
                destination = root.joinpath(*pure.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(payload.read(name))
                restored.append(name)
    if 'live2dcubismcore.min.js' not in restored or 'Hiyori/Hiyori.model3.json' not in restored:
        raise SystemExit('Required Live2D assets missing from the supplied APK')
    print(f'Restored {len(restored)} third-party runtime assets locally. Original terms apply.')

if __name__ == '__main__':
    main()
