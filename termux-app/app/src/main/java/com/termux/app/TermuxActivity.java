package com.termux.app;

import android.Manifest;
import android.app.Activity;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.IBinder;
import android.view.WindowManager;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import androidx.annotation.NonNull;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

public class TermuxActivity extends Activity implements ServiceConnection {

    private WebView mWebView;
    private TermuxService mTermuxService;
    private static final int PERMISSION_REQUEST_CODE = 100;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        
        // Keep screen on during speech interaction
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        
        setContentView(R.layout.activity_termux);

        mWebView = findViewById(R.id.agi_webview);
        setupWebView();
        checkPermissions();
        extractAgiAssetsIfNeeded();
        appendStartupToBashrc();

        // Bind Termux background service to run python and command terminal backend
        Intent serviceIntent = new Intent(this, TermuxService.class);
        startService(serviceIntent);
        bindService(serviceIntent, this, Context.BIND_AUTO_CREATE);
    }

    private void extractAgiAssetsIfNeeded() {
        java.io.File targetDir = new java.io.File("/data/data/com.termux/files/home/micro-agi-mvp");
        if (!targetDir.exists()) {
            targetDir.mkdirs();
            try {
                java.io.InputStream is = getAssets().open("micro-agi-mvp.zip");
                unzip(is, "/data/data/com.termux/files/home");
                is.close();
                android.util.Log.d("TermuxActivity", "Assets extracted successfully.");
            } catch (java.io.IOException e) {
                android.util.Log.e("TermuxActivity", "Failed to extract assets", e);
            }
        }
    }

    private void appendStartupToBashrc() {
        java.io.File bashrc = new java.io.File("/data/data/com.termux/files/home/.bashrc");
        try {
            java.io.File parent = bashrc.getParentFile();
            if (parent != null && !parent.exists()) {
                parent.mkdirs();
            }

            boolean alreadyConfigured = false;
            if (bashrc.exists()) {
                java.io.BufferedReader reader = new java.io.BufferedReader(new java.io.FileReader(bashrc));
                String line;
                while ((line = reader.readLine()) != null) {
                    if (line.contains("micro-agi-mvp")) {
                        alreadyConfigured = true;
                        break;
                    }
                }
                reader.close();
            }

            if (!alreadyConfigured) {
                java.io.FileWriter writer = new java.io.FileWriter(bashrc, true); // Append mode
                writer.write("\n# Micro-AGI MVP Auto-Start Configuration\n");
                writer.write("if [ ! -f ~/.bootstrapped ]; then\n");
                writer.write("    echo \"⚙️ 正在首次配置国内清华大学镜像源...\"\n");
                writer.write("    sed -i 's|packages.termux.org|mirrors.tuna.tsinghua.edu.cn/termux|g' /data/data/com.termux/files/usr/etc/apt/sources.list\n");
                writer.write("    sed -i 's|packages.termux.dev|mirrors.tuna.tsinghua.edu.cn/termux|g' /data/data/com.termux/files/usr/etc/apt/sources.list\n");
                writer.write("    pkg update -y\n");
                writer.write("    pkg install -y python ffmpeg termux-api git tmux\n");
                writer.write("    pip install -i https://pypi.tuna.tsinghua.edu.cn/simple speechrecognition requests\n");
                writer.write("    touch ~/.bootstrapped\n");
                writer.write("fi\n\n");
                writer.write("cd /data/data/com.termux/files/home/micro-agi-mvp\n");
                writer.write("tmux has-session -t micro-agi 2>/dev/null || tmux new-session -d -s micro-agi \"bash start_service.sh\"\n");
                writer.write("tmux has-session -t micro-agi-wake 2>/dev/null || tmux new-session -d -s micro-agi-wake \"python wake_word_daemon.py\"\n");
                writer.close();
                android.util.Log.d("TermuxActivity", "Added startup configuration to .bashrc");
            }
        } catch (java.io.IOException e) {
            android.util.Log.e("TermuxActivity", "Failed to write .bashrc", e);
        }
    }

    private static void unzip(java.io.InputStream is, String targetDirPath) throws java.io.IOException {
        java.util.zip.ZipInputStream zis = new java.util.zip.ZipInputStream(new java.io.BufferedInputStream(is));
        java.util.zip.ZipEntry ze;
        byte[] buffer = new byte[4096];
        while ((ze = zis.getNextEntry()) != null) {
            java.io.File file = new java.io.File(targetDirPath, ze.getName());
            if (ze.isDirectory()) {
                file.mkdirs();
            } else {
                java.io.File parent = file.getParentFile();
                if (parent != null) {
                    parent.mkdirs();
                }
                java.io.FileOutputStream fos = new java.io.FileOutputStream(file);
                java.io.BufferedOutputStream bos = new java.io.BufferedOutputStream(fos, buffer.length);
                int count;
                while ((count = zis.read(buffer, 0, buffer.length)) != -1) {
                    bos.write(buffer, 0, count);
                }
                bos.flush();
                bos.close();
                fos.close();
            }
            zis.closeEntry();
        }
        zis.close();
    }

    private void setupWebView() {
        WebSettings settings = mWebView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false); // Enable auto speech TTS
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);

        mWebView.setWebViewClient(new WebViewClient());
        
        // Allow Web Speech API / microphone permissions inside WebView
        mWebView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                request.grant(request.getResources());
            }
        });

        mWebView.loadUrl("http://localhost:8085");
    }

    private void checkPermissions() {
        String[] permissions = {
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.INTERNET,
            Manifest.permission.WRITE_EXTERNAL_STORAGE,
            Manifest.permission.READ_EXTERNAL_STORAGE
        };
        
        boolean hasAll = true;
        for (String perm : permissions) {
            if (ContextCompat.checkSelfPermission(this, perm) != PackageManager.PERMISSION_GRANTED) {
                hasAll = false;
                break;
            }
        }
        
        if (!hasAll) {
            ActivityCompat.requestPermissions(this, permissions, PERMISSION_REQUEST_CODE);
        }
    }

    @Override
    public void onServiceConnected(ComponentName name, IBinder service) {
        mTermuxService = ((TermuxService.LocalBinder) service).service;
        
        // In the background shell session, let's create a new terminal session.
        // It will automatically execute our login / startup commands from ~/.bashrc.
        if (mTermuxService.getTerminalSessions().isEmpty()) {
            mTermuxService.createTerminalSession(
                "/system/bin/sh",
                null,
                new String[]{},
                "/data/data/com.termux/files/home",
                true
            );
        }
    }

    @Override
    public void onServiceDisconnected(ComponentName name) {
        mTermuxService = null;
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        try {
            unbindService(this);
        } catch (Exception e) {
            // Service might already be unbound
        }
    }

    @Override
    public void onBackPressed() {
        if (mWebView.canGoBack()) {
            mWebView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
