package com.sg.magi;

import android.Manifest;
import android.app.ProgressDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.AsyncTask;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.util.Log;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.Toast;

import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

public class MainActivity extends AppCompatActivity {
    private static final String TAG = "MainActivity";
    private static final int REQ_OVERLAY = 1001;
    private static final int REQ_NOTIF = 1002;
    private static final String PET_URL = "http://127.0.0.1:8085/pet.html";

    private WebView webView;
    private Button petBtn;
    private boolean petWanted = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        File appPy = new File(getFilesDir(), "home/micro-agi-mvp/app.py");
        if (!appPy.exists()) {
            new DecompressTask().execute();
        } else {
            initApp();
        }

        handlePetIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handlePetIntent(intent);
    }

    private void handlePetIntent(Intent intent) {
        if (intent == null) return;
        Uri data = intent.getData();
        if (data != null && "magi".equals(data.getScheme()) && "pet".equals(data.getHost())) {
            String path = data.getPath(); // /start or /stop
            if (path != null && path.contains("stop")) {
                stopPet();
            } else {
                petWanted = true;
                tryStartPet();
            }
        }
        String action = intent.getAction();
        if ("com.sg.magi.PET_START".equals(action)) {
            petWanted = true;
            tryStartPet();
        } else if ("com.sg.magi.PET_STOP".equals(action)) {
            stopPet();
        }
    }

    private void initApp() {
        Intent serviceIntent = new Intent(this, AGIService.class);
        startService(serviceIntent);

        FrameLayout root = new FrameLayout(this);
        root.setLayoutParams(new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));

        webView = new WebView(this);
        root.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));

        // 顶部桌宠控制条
        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        int pad = dp(8);
        bar.setPadding(pad, pad, pad, pad);
        bar.setBackgroundColor(Color.parseColor("#CC0B0F19"));

        petBtn = new Button(this);
        petBtn.setText("开启系统桌宠");
        petBtn.setAllCaps(false);
        petBtn.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        petBtn.setOnClickListener(v -> {
            if (isPetRunningHint()) {
                stopPet();
            } else {
                petWanted = true;
                tryStartPet();
            }
        });
        bar.addView(petBtn, new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

        Button permBtn = new Button(this);
        permBtn.setText("悬浮权限");
        permBtn.setAllCaps(false);
        permBtn.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        permBtn.setOnClickListener(v -> PetOverlayService.requestOverlayPermission(this));
        bar.addView(permBtn, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        FrameLayout.LayoutParams barLp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.TOP);
        root.addView(bar, barLp);

        // WebView 顶部留出控制条高度
        webView.setPadding(0, dp(48), 0, 0);
        webView.setClipToPadding(false);

        setContentView(root);

        WebSettings webSettings = webView.getSettings();
        webSettings.setJavaScriptEnabled(true);
        webSettings.setDomStorageEnabled(true);
        webSettings.setDatabaseEnabled(true);
        webSettings.setMediaPlaybackRequiresUserGesture(false);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            webSettings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        }

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
                webView.postDelayed(() -> webView.loadUrl("http://127.0.0.1:8085"), 2000);
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (request != null && request.getUrl() != null) {
                    return handleCustomUrl(request.getUrl());
                }
                return false;
            }

            @SuppressWarnings("deprecation")
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                if (url != null) {
                    return handleCustomUrl(Uri.parse(url));
                }
                return false;
            }
        });

        webView.loadUrl("http://127.0.0.1:8085");
        maybeRequestNotifPermission();
        refreshPetButton();
    }

    private boolean handleCustomUrl(Uri uri) {
        if (uri == null) return false;
        if ("magi".equals(uri.getScheme()) && "pet".equals(uri.getHost())) {
            String path = uri.getPath() != null ? uri.getPath() : "";
            if (path.contains("stop")) {
                stopPet();
            } else {
                petWanted = true;
                tryStartPet();
            }
            return true;
        }
        return false;
    }

    private void tryStartPet() {
        if (!Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "请允许「显示在其他应用的上层」", Toast.LENGTH_LONG).show();
            PetOverlayService.requestOverlayPermission(this);
            return;
        }
        PetOverlayService.start(this, PET_URL);
        refreshPetButton();
        Toast.makeText(this, "正在启动系统桌宠…\n请确保 8085 服务已运行", Toast.LENGTH_SHORT).show();
    }

    private void stopPet() {
        petWanted = false;
        PetOverlayService.stop(this);
        refreshPetButton();
        Toast.makeText(this, "桌宠已关闭", Toast.LENGTH_SHORT).show();
    }

    private boolean isPetRunningHint() {
        // 简易状态：用 SharedPreferences 也可；这里用按钮文案/ petWanted 近似
        return petWanted && Settings.canDrawOverlays(this);
    }

    private void refreshPetButton() {
        if (petBtn == null) return;
        boolean on = isPetRunningHint();
        petBtn.setText(on ? "关闭系统桌宠" : "开启系统桌宠");
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
        if (petWanted && Settings.canDrawOverlays(this)) {
            // 用户从设置页返回后自动开启
            PetOverlayService.start(this, PET_URL);
        }
        refreshPetButton();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, @Nullable Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_OVERLAY && petWanted && Settings.canDrawOverlays(this)) {
            PetOverlayService.start(this, PET_URL);
        }
    }

    private int dp(int v) {
        return (int) TypedValue.applyDimension(
                TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics());
    }

    private class DecompressTask extends AsyncTask<Void, Integer, Boolean> {
        private ProgressDialog progressDialog;

        @Override
        protected void onPreExecute() {
            progressDialog = new ProgressDialog(MainActivity.this);
            progressDialog.setTitle("正在初始化 Micro-AGI 运行环境");
            progressDialog.setMessage("首次运行正在静默解压核心组件，请稍候...");
            progressDialog.setProgressStyle(ProgressDialog.STYLE_HORIZONTAL);
            progressDialog.setCancelable(false);
            progressDialog.show();
        }

        @Override
        protected Boolean doInBackground(Void... voids) {
            try {
                InputStream is = getAssets().open("bootstrap.zip");
                ZipInputStream zis = new ZipInputStream(new BufferedInputStream(is));
                ZipEntry ze;

                File destDir = getFilesDir();
                byte[] buffer = new byte[8192];
                int fileCount = 0;

                while ((ze = zis.getNextEntry()) != null) {
                    String filename = ze.getName();
                    File f = new File(destDir, filename);

                    if (ze.isDirectory()) {
                        f.mkdirs();
                        continue;
                    }

                    f.getParentFile().mkdirs();
                    FileOutputStream fos = new FileOutputStream(f);
                    int count;
                    while ((count = zis.read(buffer)) != -1) {
                        fos.write(buffer, 0, count);
                    }
                    fos.close();
                    zis.closeEntry();

                    fileCount++;
                    if (fileCount % 50 == 0) {
                        publishProgress(fileCount);
                    }
                }
                zis.close();
                return true;
            } catch (Exception e) {
                Log.e(TAG, "解压 bootstrap 失败", e);
                return false;
            }
        }

        @Override
        protected void onProgressUpdate(Integer... values) {
            progressDialog.setProgress(values[0] % 100);
        }

        @Override
        protected void onPostExecute(Boolean success) {
            progressDialog.dismiss();
            if (success) {
                Toast.makeText(MainActivity.this, "初始化环境成功！", Toast.LENGTH_SHORT).show();
                initApp();
            } else {
                Toast.makeText(MainActivity.this, "致命错误：初始化环境失败！", Toast.LENGTH_LONG).show();
            }
        }
    }
}
