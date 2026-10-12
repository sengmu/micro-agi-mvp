package com.sg.magi;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.ViewGroup;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceError;
import android.webkit.WebResourceResponse;
import android.webkit.CookieManager;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.RenderProcessGoneDetail;
import androidx.appcompat.app.AlertDialog;
import android.widget.FrameLayout;
import android.widget.Toast;
import android.widget.TextView;
import android.graphics.Color;
import android.view.Gravity;

import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.json.JSONObject;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class MainActivity extends AppCompatActivity {
    private static final int REQ_OVERLAY = 1001;
    private static final int REQ_NOTIF = 1002;
    private WebView webView;
    private static volatile boolean petWanted = false;
    private volatile boolean backendReady = false;
    private volatile int backendPort = -1;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        initApp();

    }

    private void initApp() {
        FrameLayout root = new FrameLayout(this);
        root.setLayoutParams(new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));

        webView = new WebView(this);
        root.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));

        setContentView(root);

        WebSettings webSettings = webView.getSettings();
        webSettings.setJavaScriptEnabled(true);
        webSettings.setDomStorageEnabled(true);
        webSettings.setDatabaseEnabled(true);
        webSettings.setMediaPlaybackRequiresUserGesture(false);
        webSettings.setAllowFileAccess(false);
        webSettings.setAllowContentAccess(false);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, false);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            webSettings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        }

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
                // A dead renderer cannot be reused; keep the native shell alive
                // and require a fresh launch instead of silently reusing its port.
                backendReady = false;
                backendPort = -1;
                petWanted = false;
                PetOverlayService.stop(MainActivity.this);
                ViewGroup parent = view.getParent() instanceof ViewGroup
                        ? (ViewGroup) view.getParent() : null;
                if (parent != null) parent.removeView(view);
                view.destroy();
                if (webView == view) webView = null;
                if (parent != null) {
                    TextView message = new TextView(MainActivity.this);
                    message.setText("角色画面意外退出，请重新打开应用。");
                    message.setTextColor(Color.WHITE);
                    message.setBackgroundColor(Color.rgb(11, 15, 25));
                    message.setGravity(Gravity.CENTER);
                    parent.addView(message, new ViewGroup.LayoutParams(
                            ViewGroup.LayoutParams.MATCH_PARENT,
                            ViewGroup.LayoutParams.MATCH_PARENT));
                }
                return true;
            }

            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return LocalWebViewPolicy.intercept(
                        request != null ? request.getUrl() : null,
                        backendReady ? backendPort : -1);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request != null && request.isForMainFrame()) {
                    showBackendUnavailable();
                }
            }

            @Override
            public void onReceivedHttpError(WebView view, WebResourceRequest request,
                    WebResourceResponse errorResponse) {
                // HTTP 4xx/5xx on the document is not reported by
                // onReceivedError. Do not leave an authenticated shell showing
                // a blank or stale page when its local backend fails.
                if (request != null && request.isForMainFrame()) {
                    showBackendUnavailable();
                }
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (request == null || request.getUrl() == null) return true;
                if (!request.isForMainFrame()) return false;
                Uri uri = request.getUrl();
                if (backendReady && LocalWebViewPolicy.isTrusted(uri, backendPort)) return false;
                // A server redirect or scripted navigation must not open an
                // external app without a deliberate user tap in this WebView.
                String scheme = uri.getScheme();
                if ("http".equals(scheme) || "https".equals(scheme)) {
                    if (!request.hasGesture() || request.isRedirect()) return true;
                }
                return handleCustomUrl(uri);
            }

            @SuppressWarnings("deprecation")
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                if (url != null) {
                    Uri uri = Uri.parse(url);
                    if (backendReady && LocalWebViewPolicy.isTrusted(uri, backendPort)) return false;
                    // The legacy callback cannot prove a user gesture. Do not
                    // launch an external browser from this fallback path.
                    String scheme = uri.getScheme();
                    if ("http".equals(scheme) || "https".equals(scheme)) return true;
                    return handleCustomUrl(uri);
                }
                return true;
            }
        });

        startEmbeddedBackend();
    }

    private void showBackendUnavailable() {
        backendReady = false;
        backendPort = -1;
        PetOverlayService.stop(this);
        if (webView == null) return;
        String html = "<html><meta name='viewport' content='width=device-width,initial-scale=1'>"
                + "<body style='background:#0b0f19;color:#eef6ff;font-family:sans-serif;padding:72px 24px;text-align:center'>"
                + "<h2>内嵌服务未能启动</h2><p>请重新打开应用；如果仍失败，请记录 Android 日志并反馈。</p>"
                + "</body></html>";
        webView.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null);
    }

    private void startEmbeddedBackend() {
        new Thread(() -> {
            try {
                if (!Python.isStarted()) {
                    Python.start(new AndroidPlatform(getApplicationContext()));
                }
                JSONObject endpoint = new JSONObject(Python.getInstance().getModule("mobile_entry")
                        .callAttr("start").toString());
                String sessionToken = endpoint.optString("token", "");
                int port = endpoint.optInt("port", -1);
                if (sessionToken.length() < 40) throw new IllegalStateException("Invalid session");
                if (port < 1 || port > 65535) throw new IllegalStateException("Invalid port");
                String candidateBaseUrl = "http://127.0.0.1:" + port + "/";
                for (int attempt = 0; attempt < 40; attempt++) {
                    HttpURLConnection connection = null;
                    try {
                        connection = (HttpURLConnection) new URL(candidateBaseUrl + "api/health").openConnection();
                        connection.setConnectTimeout(500);
                        connection.setReadTimeout(500);
                        if (connection.getResponseCode() == 200) {
                            try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                                    connection.getInputStream(), StandardCharsets.UTF_8))) {
                                String body = reader.readLine();
                                if (body != null && validEmbeddedHealth(
                                        sessionToken, port, new JSONObject(body))) {
                                    runOnUiThread(() -> {
                                        if (isDestroyed() || webView == null) return;
                                        CookieManager.getInstance().setCookie(candidateBaseUrl,
                                                "magi_session=" + sessionToken
                                                        + "; HttpOnly; SameSite=Strict; Path=/api/",
                                                accepted -> {
                                                    if (isDestroyed() || webView == null) return;
                                                    if (Boolean.TRUE.equals(accepted)) {
                                                        backendPort = port;
                                                        backendReady = true;
                                                        webView.loadUrl(candidateBaseUrl);
                                                        if (petWanted) tryStartPet();
                                                    } else {
                                                        showBackendUnavailable();
                                                    }
                                                });
                                    });
                                    return;
                                }
                            }
                        }
                    } catch (Exception ignored) {
                        // The embedded server may still be initializing.
                    } finally {
                        if (connection != null) connection.disconnect();
                    }
                    Thread.sleep(250);
                }
            } catch (Exception ignored) {
                // A missing interpreter or backend is surfaced through the safe error page.
            }
            runOnUiThread(() -> {
                if (!isDestroyed()) showBackendUnavailable();
            });
        }, "micro-agi-startup").start();
    }

    private boolean validEmbeddedHealth(String token, int port, JSONObject response) throws Exception {
        if (!response.optBoolean("embedded", false)) return false;
        if (!response.optBoolean("ready", false)) return false;
        if (response.optInt("port", -1) != port) return false;
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(token.getBytes(StandardCharsets.US_ASCII), "HmacSHA256"));
        byte[] expected = mac.doFinal(
                "micro-agi-embedded-health-v1".getBytes(StandardCharsets.US_ASCII));
        char[] digits = "0123456789abcdef".toCharArray();
        char[] hex = new char[expected.length * 2];
        for (int i = 0; i < expected.length; i++) {
            hex[i * 2] = digits[(expected[i] >>> 4) & 0xf];
            hex[i * 2 + 1] = digits[expected[i] & 0xf];
        }
        return MessageDigest.isEqual(new String(hex).getBytes(StandardCharsets.US_ASCII),
                response.optString("proof", "").getBytes(StandardCharsets.US_ASCII));
    }

    private boolean handleCustomUrl(Uri uri) {
        if (uri == null) return false;
        if (backendReady && LocalWebViewPolicy.isTrusted(uri, backendPort)) {
            return false;
        }
        if ("magi".equals(uri.getScheme())
                && ("pet".equals(uri.getHost()) || "wallet".equals(uri.getHost()))) {
            // Page actions are privileged. A data:/about:/external navigation must
            // never be able to control the floating pet through this URL handler.
            Uri currentPage = webView != null && webView.getUrl() != null
                    ? Uri.parse(webView.getUrl()) : null;
            if (!backendReady || !LocalWebViewPolicy.isTrusted(currentPage, backendPort)) {
                return true;
            }
            String path = uri.getPath() != null ? uri.getPath() : "";
            if ("wallet".equals(uri.getHost()) && "/open".equals(path)) {
                startActivity(new Intent(this, WalletActivity.class));
            } else if ("/manage".equals(path) && "pet".equals(uri.getHost())) {
                showPetOptions();
            } else if ("/stop".equals(path) && "pet".equals(uri.getHost())) {
                stopPet();
            } else if ("/start".equals(path) && "pet".equals(uri.getHost())) {
                petWanted = true;
                tryStartPet();
            }
            return true;
        }
        // Never load an external page into the privileged app WebView.
        // Ordinary links may open in the system browser; all other schemes are blocked.
        if ("https".equals(uri.getScheme()) || "http".equals(uri.getScheme())) {
            try {
                Intent browser = new Intent(Intent.ACTION_VIEW, uri);
                browser.addCategory(Intent.CATEGORY_BROWSABLE);
                startActivity(browser);
            } catch (Exception ignored) {
                Toast.makeText(this, "无法打开外部链接", Toast.LENGTH_SHORT).show();
            }
        }
        return true;
    }

    private void showPetOptions() {
        String action = isPetRunningHint() ? "关闭桌宠" : "开启桌宠";
        new AlertDialog.Builder(this)
                .setTitle("桌宠")
                .setItems(new String[]{action, "悬浮权限设置"}, (dialog, which) -> {
                    if (which == 1) {
                        requestOverlayPermission();
                    } else if (isPetRunningHint()) {
                        stopPet();
                    } else {
                        petWanted = true;
                        tryStartPet();
                    }
                })
                .show();
    }

    private void tryStartPet() {
        if (!backendReady) {
            petWanted = true;
            Toast.makeText(this, "正在等待内嵌服务启动…", Toast.LENGTH_SHORT).show();
            return;
        }
        if (!Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "请允许「显示在其他应用的上层」", Toast.LENGTH_LONG).show();
            requestOverlayPermission();
            return;
        }
        maybeRequestNotifPermission();
        boolean requested = PetOverlayService.start(this, backendPort);
        Toast.makeText(this, requested ? "正在启动系统桌宠…" : "桌宠无法启动，请查看系统权限", Toast.LENGTH_SHORT).show();
    }

    private void stopPet() {
        petWanted = false;
        PetOverlayService.stop(this);
        Toast.makeText(this, "桌宠已关闭", Toast.LENGTH_SHORT).show();
    }

    private void requestOverlayPermission() {
        Intent permission = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:" + getPackageName()));
        startActivity(permission);
    }

    static void onPetServiceStopped() {
        petWanted = false;
    }

    private boolean isPetRunningHint() {
        return backendReady && petWanted && Settings.canDrawOverlays(this);
    }

    private void maybeRequestNotifPermission() {
        if (Build.VERSION.SDK_INT >= 33) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                    != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(
                        this,
                        new String[]{Manifest.permission.POST_NOTIFICATIONS},
                        REQ_NOTIF);
            }
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (backendReady && petWanted && Settings.canDrawOverlays(this)) {
            // 用户从设置页返回后自动开启
            PetOverlayService.start(this, backendPort);
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, @Nullable Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_OVERLAY && backendReady && petWanted
                && Settings.canDrawOverlays(this)) {
            PetOverlayService.start(this, backendPort);
        }
    }

}
