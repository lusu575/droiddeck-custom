#!/usr/bin/env bash
set -euo pipefail
apk=${1:?APK path required}
build_tools=$(find "$ANDROID_HOME/build-tools" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -1)
"$build_tools/apksigner" verify --verbose --print-certs "$apk"
"$build_tools/aapt" dump badging "$apk" > /tmp/custom-apk-badging.txt
grep -q "package: name='com.droiddeck.custom'" /tmp/custom-apk-badging.txt
grep -q "native-code: 'arm64-v8a'" /tmp/custom-apk-badging.txt
python3 - "$apk" <<'PY'
import hashlib
from pathlib import Path
import sys
from zipfile import ZipFile
with ZipFile(sys.argv[1]) as apk:
    for name in ('proot', 'directaudio', 'tracking', 'xbox', 'comet', 'butler'):
        expected = Path(f'app/build/packs/{name}.tar.zst').read_bytes()
        actual = apk.read(f'assets/packs/{name}.tar.zst')
        assert hashlib.sha256(actual).digest() == hashlib.sha256(expected).digest(), name
    assert 'lib/arm64-v8a/libdroiddeckstores.so' in apk.namelist()
    assert 'lib/arm64-v8a/libvkbridge_server.so' in apk.namelist()
print('Custom package, embedded packs and native libraries verified.')
PY
sha256sum "$apk" | tee -a "$GITHUB_STEP_SUMMARY"
