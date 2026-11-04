#!/usr/bin/env bash
set -euo pipefail
mkdir -p keystore
rm -f keystore/testkey.p12
keytool -genkeypair -noprompt -storetype PKCS12 -keystore keystore/testkey.p12 \
  -storepass android -keypass android -alias testkey -keyalg RSA -keysize 2048 \
  -validity 30 -dname 'CN=DroidDeck Custom Disposable Test, O=Local Test, C=ZZ'
printf '%s\n' 'This APK uses a disposable test signing key. Later builds may require uninstalling it, which can remove app data.' >> "$GITHUB_STEP_SUMMARY"
