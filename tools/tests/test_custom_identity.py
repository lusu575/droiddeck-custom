from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]

class CustomIdentityTest(unittest.TestCase):
    def test_custom_install_cannot_replace_official_package(self):
        gradle = (ROOT / 'app/build.gradle').read_text()
        self.assertIn('applicationId "com.droiddeck.custom"', gradle)
        self.assertIn("namespace 'com.droiddeck.launcher'", gradle)
        self.assertNotIn('applicationId "com.droiddeck.launcher"', gradle)
        variants = (ROOT / 'tools/release/variants.txt').read_text()
        self.assertNotIn('com.droiddeck.launcher', variants)
        self.assertNotIn('com.tencent.ig', variants)

    def test_provider_authorities_remain_package_scoped(self):
        manifest = (ROOT / 'app/src/main/AndroidManifest.xml').read_text()
        self.assertIn('android:label="@string/custom_app_name"', manifest)
        for name in ('logs', 'documents', 'agent'):
            self.assertIn('${applicationId}.' + name, manifest)

    def test_cancelled_offline_feature_is_absent(self):
        self.assertFalse((ROOT / 'app/src/main/java/com/droiddeck/launcher/core/BundledComponents.java').exists())
        self.assertFalse((ROOT / 'tools/offline/stage.py').exists())
        installer = (ROOT / 'app/src/main/java/com/droiddeck/launcher/runtime/LinuxRuntimeInstaller.java').read_text()
        self.assertNotIn('offline/linuxfs.json', installer)
