"""Source-level Android guardrails; a device build is still required."""

import pathlib
import json
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1] / "android_host" / "app" / "src" / "main"
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"


class AndroidSecurityConfigTests(unittest.TestCase):
    def test_new_application_id_does_not_replace_legacy_app(self):
        gradle = (ROOT.parents[1] / "build.gradle").read_text(encoding="utf-8")
        self.assertRegex(gradle, r'applicationId\s+"cloud\.relayhub\.microagi"')
        self.assertRegex(gradle, r"applicationIdSuffix\s+'\.debug'")
        self.assertNotRegex(gradle, r'applicationId\s+"com\.sg\.magi"')

    def test_manifest_disables_backup_and_global_cleartext(self):
        manifest = ET.parse(ROOT / "AndroidManifest.xml").getroot()
        application = manifest.find("application")
        self.assertEqual(application.get(ANDROID_NS + "allowBackup"), "false")
        self.assertEqual(application.get(ANDROID_NS + "fullBackupContent"),
                         "@xml/full_backup_content")
        self.assertEqual(application.get(ANDROID_NS + "dataExtractionRules"),
                         "@xml/data_extraction_rules")
        self.assertEqual(application.get(ANDROID_NS + "usesCleartextTraffic"), "false")
        self.assertEqual(application.get(ANDROID_NS + "networkSecurityConfig"),
                         "@xml/network_security_config")
        permissions = {node.get(ANDROID_NS + "name")
                       for node in manifest.findall("uses-permission")}
        self.assertNotIn("android.permission.WAKE_LOCK", permissions)

    def test_all_backup_and_device_transfer_domains_are_excluded(self):
        xml_dir = ROOT / "res" / "xml"
        modern = ET.parse(xml_dir / "data_extraction_rules.xml").getroot()
        legacy = ET.parse(xml_dir / "full_backup_content.xml").getroot()
        self.assertEqual(modern.tag, "data-extraction-rules")
        self.assertEqual(legacy.tag, "full-backup-content")
        expected = {("root", "."), ("device_root", "."), ("external", ".")}
        for section in (modern.find("cloud-backup"), modern.find("device-transfer"), legacy):
            self.assertIsNotNone(section)
            self.assertEqual({(node.get("domain"), node.get("path"))
                              for node in section.findall("exclude")}, expected)
            self.assertEqual(section.findall("include"), [])

    def test_only_loopback_has_cleartext_exception(self):
        config = ET.parse(ROOT / "res" / "xml" / "network_security_config.xml").getroot()
        self.assertEqual(config.find("base-config").get("cleartextTrafficPermitted"), "false")
        exceptions = config.findall("domain-config")
        self.assertEqual(len(exceptions), 1)
        self.assertEqual(exceptions[0].get("cleartextTrafficPermitted"), "true")
        self.assertEqual([node.text for node in exceptions[0].findall("domain")], ["127.0.0.1"])
        self.assertEqual(exceptions[0].find("domain").get("includeSubdomains"), "false")

    def test_webviews_do_not_reenable_file_or_mixed_content(self):
        sources = [ROOT / "java" / "com" / "sg" / "magi" / name
                   for name in ("MainActivity.java", "PetOverlayService.java")]
        for source in sources:
            with self.subTest(source=source.name):
                code = source.read_text(encoding="utf-8")
                self.assertIn("setAllowFileAccess(false)", code)
                self.assertIn("setAllowContentAccess(false)", code)
                self.assertIn("setAcceptThirdPartyCookies(webView, false)", code)
                self.assertIn("MIXED_CONTENT_NEVER_ALLOW", code)
                self.assertIn("shouldInterceptRequest(WebView view, WebResourceRequest request)", code)
                self.assertIn("LocalWebViewPolicy.intercept(", code)
                self.assertNotIn("MIXED_CONTENT_ALWAYS_ALLOW", code)
                self.assertNotIn("setAllowFileAccess(true)", code)

    def test_webview_subresources_only_use_verified_loopback_port(self):
        code = (ROOT / "java" / "com" / "sg" / "magi" / "LocalWebViewPolicy.java").read_text(
            encoding="utf-8")
        self.assertIn('"http".equals(uri.getScheme())', code)
        self.assertIn('"127.0.0.1".equals(uri.getHost())', code)
        self.assertIn("uri.getPort() == port", code)
        self.assertIn("uri.getUserInfo() == null", code)
        self.assertIn('403, "Forbidden"', code)
        self.assertNotIn('"https".equals(uri.getScheme())', code)

    def test_external_browser_launch_needs_main_frame_user_gesture(self):
        code = (ROOT / "java" / "com" / "sg" / "magi" / "MainActivity.java").read_text(
            encoding="utf-8")
        modern = code.split("boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request)", 1)[1].split(
            '@SuppressWarnings("deprecation")', 1)[0]
        self.assertIn("if (!request.isForMainFrame()) return false;", modern)
        self.assertIn("LocalWebViewPolicy.isTrusted(uri, backendPort)", modern)
        self.assertIn("!request.hasGesture() || request.isRedirect()", modern)
        legacy = code.split("boolean shouldOverrideUrlLoading(WebView view, String url)", 1)[1].split(
            "startEmbeddedBackend();", 1)[0]
        self.assertIn('if ("http".equals(scheme) || "https".equals(scheme)) return true;', legacy)

    def test_embedded_webview_waits_for_authenticated_local_server(self):
        code = (ROOT / "java" / "com" / "sg" / "magi" / "MainActivity.java").read_text(
            encoding="utf-8")
        self.assertIn('callAttr("start")', code)
        self.assertIn("validEmbeddedHealth(", code)
        self.assertIn('response.optBoolean("ready", false)', code)
        self.assertIn('response.optInt("port", -1) != port', code)
        self.assertIn('"micro-agi-embedded-health-v1"', code)
        self.assertIn('"magi_session=" + sessionToken', code)
        self.assertIn("HttpOnly; SameSite=Strict; Path=/api/", code)
        self.assertIn('String candidateBaseUrl = "http://127.0.0.1:" + port + "/"', code)
        self.assertIn("webView.loadUrl(candidateBaseUrl)", code)
        self.assertNotIn("127.0.0.1:8087", code)

    def test_external_intents_cannot_control_pet_overlay(self):
        manifest = ET.parse(ROOT / "AndroidManifest.xml").getroot()
        main = next(activity for activity in manifest.find("application").findall("activity")
                    if activity.get(ANDROID_NS + "name") == "com.sg.magi.MainActivity")
        actions = [action.get(ANDROID_NS + "name")
                   for intent_filter in main.findall("intent-filter")
                   for action in intent_filter.findall("action")]
        self.assertEqual(actions, ["android.intent.action.MAIN", "android.intent.action.VIEW"])
        filters = main.findall("intent-filter")
        self.assertEqual(len(filters), 2)
        app_link = filters[1]
        self.assertEqual(app_link.get(ANDROID_NS + "autoVerify"), "true")
        categories = {node.get(ANDROID_NS + "name") for node in app_link.findall("category")}
        self.assertEqual(categories, {"android.intent.category.DEFAULT",
                                      "android.intent.category.BROWSABLE"})
        data = app_link.find("data")
        self.assertEqual(data.get(ANDROID_NS + "scheme"), "https")
        self.assertEqual(data.get(ANDROID_NS + "host"), "relayhub.cloud")
        self.assertEqual(data.get(ANDROID_NS + "path"), "/micro-agi/open")
        code = (ROOT / "java" / "com" / "sg" / "magi" / "MainActivity.java").read_text(
            encoding="utf-8")
        self.assertNotIn("handlePetIntent(", code)
        self.assertNotIn('"com.sg.magi.PET_START"', code)
        self.assertNotIn('"com.sg.magi.PET_STOP"', code)
        self.assertIn('"magi".equals(uri.getScheme())', code)
        pet_actions = code.split('if ("magi".equals(uri.getScheme())', 1)[1].split(
            'if ("https".equals(uri.getScheme())', 1)[0]
        self.assertIn('LocalWebViewPolicy.isTrusted(currentPage, backendPort)', pet_actions)
        self.assertLess(pet_actions.index('LocalWebViewPolicy.isTrusted(currentPage, backendPort)'),
                        pet_actions.index('"/start".equals(path)'))
        self.assertIn('"/start".equals(path)', code)
        self.assertIn('"/stop".equals(path)', code)

    def test_pet_start_waits_for_embedded_backend(self):
        code = (ROOT / "java" / "com" / "sg" / "magi" / "MainActivity.java").read_text(
            encoding="utf-8")
        start = code.split("private void tryStartPet()", 1)[1].split("private void stopPet()", 1)[0]
        initialization = code.split("private void initApp()", 1)[1].split(
            "private void showBackendUnavailable()", 1
        )[0]
        self.assertNotIn("maybeRequestNotifPermission();", initialization)
        self.assertLess(start.index("if (!backendReady)"),
                        start.index("PetOverlayService.start(this, backendPort)"))
        self.assertLess(start.index("maybeRequestNotifPermission();"),
                        start.index("PetOverlayService.start(this, backendPort)"))
        self.assertIn("backendReady = true;\n                                                        webView.loadUrl(candidateBaseUrl);\n                                                        if (petWanted) tryStartPet();", code)
        self.assertIn("if (backendReady && petWanted && Settings.canDrawOverlays(this))", code)

    def test_pet_service_never_restarts_into_unverified_local_page(self):
        code = (ROOT / "java" / "com" / "sg" / "magi" / "PetOverlayService.java").read_text(
            encoding="utf-8")
        start = code.split("public int onStartCommand(", 1)[1].split(
            "private void startAsForeground()", 1)[0]
        self.assertIn("if (!ACTION_START.equals(action))", start)
        self.assertIn("stopSelf();\n            return START_NOT_STICKY;", start)
        self.assertIn("return START_NOT_STICKY;", start)
        self.assertNotIn("START_STICKY", start)
        self.assertLess(start.index("if (!ACTION_START.equals(action))"),
                        start.index("showOverlay();"))
        self.assertIn("intent.getIntExtra(EXTRA_BACKEND_PORT, -1)", start)
        self.assertIn('petUrl = "http://127.0.0.1:" + port + "/pet.html"', start)
        self.assertIn("i.putExtra(EXTRA_BACKEND_PORT, port)", code)
        self.assertNotIn("127.0.0.1:8087", code)

    def test_pet_webview_has_no_privileged_javascript_bridge(self):
        code = (ROOT / "java" / "com" / "sg" / "magi" / "PetOverlayService.java").read_text(
            encoding="utf-8")
        self.assertNotIn("addJavascriptInterface", code)
        self.assertNotIn("@JavascriptInterface", code)
        self.assertIn('dragHandle.setBackgroundColor(Color.TRANSPARENT)', code)
        self.assertIn('webView.setOnTouchListener(createDragListener(true))', code)
        self.assertIn('dragHandle.setOnTouchListener(createDragListener(false))', code)
        self.assertIn('ViewConfiguration.get(this).getScaledTouchSlop()', code)
        self.assertIn('v.onTouchEvent(cancel)', code)
        self.assertNotIn('dragHandle.addView(closeButton', code)
        self.assertIn('.addAction(0, "关闭桌宠", stopPi)', code)
        self.assertIn('if (ACTION_STOP.equals(action))', code)

    def test_pet_stops_when_its_main_page_fails_instead_of_retrying_a_reused_port(self):
        code = (ROOT / "java" / "com" / "sg" / "magi" / "PetOverlayService.java").read_text(
            encoding="utf-8")
        self.assertIn("onReceivedError(WebView view, WebResourceRequest request,", code)
        self.assertIn("onReceivedHttpError(WebView view, WebResourceRequest request,", code)
        self.assertEqual(code.count("if (request != null && request.isForMainFrame())"), 2)
        self.assertNotIn("postDelayed", code)

    def test_main_webview_shows_safe_page_for_document_http_errors(self):
        code = (ROOT / "java" / "com" / "sg" / "magi" / "MainActivity.java").read_text(
            encoding="utf-8")
        for callback in ("onReceivedError(WebView view, WebResourceRequest request,",
                         "onReceivedHttpError(WebView view, WebResourceRequest request,"):
            section = code.split(callback, 1)[1].split("}", 1)[0]
            self.assertIn("request != null && request.isForMainFrame()", section)
            self.assertIn("showBackendUnavailable();", section)

    def test_pet_close_clears_requested_state_without_native_toolbar(self):
        main = (ROOT / "java" / "com" / "sg" / "magi" / "MainActivity.java").read_text(
            encoding="utf-8")
        pet = (ROOT / "java" / "com" / "sg" / "magi" / "PetOverlayService.java").read_text(
            encoding="utf-8")
        self.assertIn("private static volatile boolean petWanted = false", main)
        self.assertIn("static void onPetServiceStopped()", main)
        self.assertIn("petWanted = false;", main.split("static void onPetServiceStopped()", 1)[1])
        self.assertNotIn("refreshPetButton", main)
        self.assertNotIn("LinearLayout bar", main)
        self.assertIn('"/manage".equals(path)', main)
        self.assertIn('"/open".equals(path)', main)
        self.assertIn('LocalWebViewPolicy.isTrusted(currentPage, backendPort)', main)
        self.assertIn("MainActivity.onPetServiceStopped();", pet)

    def test_pet_service_start_failures_are_contained_and_stop_does_not_start_service(self):
        code = (ROOT / "java" / "com" / "sg" / "magi" / "PetOverlayService.java").read_text(
            encoding="utf-8")
        self.assertIn('Log.e(TAG, "Unable to start pet foreground service", e)', code)
        self.assertIn('Log.e(TAG, "Unable to request pet service start", e)', code)
        self.assertIn("public static boolean start(Context ctx, int port)", code)
        stop = code.split("public static void stop(Context ctx)", 1)[1]
        self.assertIn("ctx.stopService(i);", stop)
        self.assertNotIn("ctx.startService(i);", stop)

    def test_notification_stop_service_never_launches_an_activity(self):
        main = (ROOT / "java" / "com" / "sg" / "magi" / "MainActivity.java").read_text(
            encoding="utf-8")
        pet = (ROOT / "java" / "com" / "sg" / "magi" / "PetOverlayService.java").read_text(
            encoding="utf-8")
        self.assertIn('.addAction(0, "关闭桌宠", stopPi)', pet)
        self.assertIn('if (ACTION_STOP.equals(action))', pet)
        self.assertNotIn('startActivity(', pet)
        self.assertIn('private void requestOverlayPermission()', main)
        self.assertIn('startActivity(permission);', main)

    def test_both_webviews_dispose_of_a_dead_renderer(self):
        source_dir = ROOT / "java" / "com" / "sg" / "magi"
        for name in ("MainActivity.java", "PetOverlayService.java"):
            with self.subTest(source=name):
                code = (source_dir / name).read_text(encoding="utf-8")
                callback = code.split("boolean onRenderProcessGone(", 1)[1].split("return true;", 1)[0]
                self.assertIn("removeView(view);", callback)
                self.assertIn("view.destroy();", callback)
                self.assertIn("webView = null;", callback)
        main = (source_dir / "MainActivity.java").read_text(encoding="utf-8")
        self.assertIn("backendReady = false;", main.split("boolean onRenderProcessGone(", 1)[1])
        self.assertIn("PetOverlayService.stop(MainActivity.this);", main)
        self.assertIn("if (webView == null) return;", main)
        pet = (source_dir / "PetOverlayService.java").read_text(encoding="utf-8")
        self.assertIn("stopSelf();", pet.split("boolean onRenderProcessGone(", 1)[1])

    def test_wallet_activity_is_private_and_uses_owner_approved_devnet_identity(self):
        manifest = ET.parse(ROOT / "AndroidManifest.xml").getroot()
        activities = manifest.find("application").findall("activity")
        wallet = next(activity for activity in activities
                      if activity.get(ANDROID_NS + "name") == "com.sg.magi.WalletActivity")
        self.assertEqual(wallet.get(ANDROID_NS + "exported"), "false")
        strings = ET.parse(ROOT / "res" / "values" / "strings.xml").getroot()
        values = {node.get("name"): (node.text or "").strip() for node in strings.findall("string")}
        self.assertEqual(values["app_name"], "Micro-AGI")
        self.assertEqual(values["solana_identity_uri"], "https://relayhub.cloud/")
        self.assertEqual(values["solana_icon_path"], "favicon.ico")
        self.assertFalse(values["solana_icon_path"].startswith("http"))
        wallet_code = (ROOT / "java" / "com" / "sg" / "magi" / "WalletActivity.kt").read_text(
            encoding="utf-8")
        self.assertIn("client.connect(", wallet_code)
        self.assertIn("client.disconnect(", wallet_code)
        self.assertIn("sender = ActivityResultSender(this)", wallet_code)
        self.assertIn("adapter?.blockchain = Solana.Devnet", wallet_code)
        self.assertIn('parsed.scheme != "https"', wallet_code)
        self.assertIn("parsed.userInfo != null", wallet_code)
        self.assertIn("parsed.query != null", wallet_code)
        self.assertIn("parsed.fragment != null", wallet_code)
        self.assertIn("parsedIcon.pathSegments.any", wallet_code)
        self.assertIn("parsedIcon.authority != null", wallet_code)
        self.assertIn("parsedIcon.path.isNullOrBlank()", wallet_code)
        self.assertIn("private var sessionAdapter: MobileWalletAdapter? = null", wallet_code)
        self.assertIn("private var sessionPublicKeys: List<String> = emptyList()", wallet_code)
        self.assertIn("adapter = sessionAdapter", wallet_code)
        self.assertIn("disconnectButton.isEnabled = adapter?.authToken != null", wallet_code)
        connect = wallet_code.split("private fun connectWallet()", 1)[1].split(
            "private fun disconnectWallet()", 1)[0]
        self.assertLess(connect.index("sessionPublicKeys = emptyList()"),
                        connect.index("client.connect(sender)"))
        self.assertLess(connect.index("accounts.any { it.publicKey.size != 32 }"),
                        connect.index("Base58.encodeToString(it.publicKey)"))
        self.assertIn("accounts.map { Base58.encodeToString(it.publicKey) }.distinct()", connect)
        self.assertIn("private var verifiedInThisOpening = false", wallet_code)
        self.assertIn('verifiedInThisOpening && sessionPublicKeys.isNotEmpty() -> "已经连接"', wallet_code)
        self.assertIn('sessionPublicKeys.isNotEmpty() -> "授权待核验"', wallet_code)
        self.assertIn("verifiedInThisOpening = false", connect)
        self.assertIn("verifiedInThisOpening = true", connect)
        self.assertIn("请重新连接核验授权", wallet_code)
        self.assertIn("钱包返回的 Solana 公钥无效", connect)
        self.assertIn("如应用已被关闭，可在钱包内撤销旧授权", wallet_code)
        self.assertNotIn("SharedPreferences", wallet_code)
        self.assertNotIn("signAndSendTransactions", wallet_code)
        self.assertNotIn("addJavascriptInterface", wallet_code)

    def test_debug_assetlinks_template_matches_debug_package(self):
        example = pathlib.Path(__file__).resolve().parents[1] / "android_host" \
            / "assetlinks.debug.example.json"
        entries = json.loads(example.read_text(encoding="utf-8"))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["relation"],
                         ["delegate_permission/common.handle_all_urls"])
        target = entries[0]["target"]
        self.assertEqual(target["namespace"], "android_app")
        self.assertEqual(target["package_name"], "cloud.relayhub.microagi.debug")
        self.assertEqual(target["sha256_cert_fingerprints"], [
            "34:59:91:39:84:6B:37:0D:AE:42:85:17:C0:2C:14:FC:CC:7B:1B:1E:47:5A:FD:E2:79:50:8A:60:0A:F8:0A:DC"
        ])


if __name__ == "__main__":
    unittest.main()
