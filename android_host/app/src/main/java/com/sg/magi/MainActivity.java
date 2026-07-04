package com.sg.magi;

import android.content.Intent;
import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {
    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        initApp();
    }

    private void initApp() {
        // 启动前台常驻保活服务
        Intent serviceIntent = new Intent(this, AGIService.class);
        startService(serviceIntent);

        webView = new WebView(this);
        setContentView(webView);

        WebSettings webSettings = webView.getSettings();
        webSettings.setJavaScriptEnabled(true);
        webSettings.setDomStorageEnabled(true);
        webSettings.setDatabaseEnabled(true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
                // 如果本地服务尚未启动就绪，延迟 2 秒后自动重试
                webView.postDelayed(new Runnable() {
                    @Override
                    public void run() {
                        webView.loadUrl("http://127.0.0.1:8085");
                    }
                }, 2000);
            }
        });

        webView.loadUrl("http://127.0.0.1:8085");
    }
}
