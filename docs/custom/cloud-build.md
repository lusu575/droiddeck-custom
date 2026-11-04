# Custom cloud test build

`.github/workflows/custom-build.yml` runs on pushes to `main` and on manual dispatch. It derives its component preparation from upstream Droid-Deck/DroidDeck commit `f3650d3d379f32a0d33e7a24249ae76023eab8bc`. The original upstream workflows are preserved unchanged under `docs/upstream-workflows/`, where GitHub does not execute them.

The workflow builds ARM64 Xbox components, the verified Linux runtime components, Syncthing, Android native libraries, the debug APK, and debug unit tests. It retains upstream runtime-input and Android-library checks. The final checks verify application ID `com.droiddeck.custom`, ARM64 libraries, APK signing, and byte-identical embedded add-on packs. The output artifact is `droiddeck-custom-test-apk`.

Only the six bootstrap add-on packs required by this upstream build are embedded: proot, DirectAudio, tracking, Xbox, Comet, and Butler. No complete Linux root filesystem, KDE desktop archive, Proton, or FEX environment archive is added. The Gradle init script adds the packs without changing the app's truthful CI build flag. No packs or releases are published.

Signing uses a new disposable test key generated inside each CI runner. No signing key is uploaded, cached, or committed. The key expires after 30 days; the resulting package is a test build, not a production release. Different runs have different signing certificates, so Android may require uninstalling a previous custom build before installing another, which can delete its app data. Keep needed data backed up separately.

The workflow uses read-only repository permissions and no repository signing secrets or account credentials. It does not run upstream's human-authorship gate, and does not make a human-authorship claim. Upstream component snapshots are used only with their recorded source identity and checksums, with source rebuild fallback.

Local validation covers YAML parsing, shell syntax, recipe references, unchanged workflow archives, component identity calculation, and test-key generation. A successful cloud workflow is still required to establish APK compilation and unit-test results; device behavior needs a real Android test.
