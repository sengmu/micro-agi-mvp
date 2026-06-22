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

        // Bind Termux background service to run python and command terminal backend
        Intent serviceIntent = new Intent(this, TermuxService.class);
        startService(serviceIntent);
        bindService(serviceIntent, this, Context.BIND_AUTO_CREATE);
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
