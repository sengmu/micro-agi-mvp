package com.sg.magi;

import android.app.ProgressDialog;
import android.content.Intent;
import android.os.AsyncTask;
import android.os.Bundle;
import android.util.Log;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

public class MainActivity extends AppCompatActivity {
    private static final String TAG = "MainActivity";
    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        
        File appPy = new File(getFilesDir(), "home/micro-agi-mvp/app.py");
        if (!appPy.exists()) {
            new DecompressTask().execute();
        } else {
            initApp();
        }
    }

    private void initApp() {
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

        private void grantPermissions(File file) {
            if (file == null || !file.exists()) return;
            
            if (file.isDirectory()) {
                file.setExecutable(true, false);
                file.setReadable(true, false);
                File[] children = file.listFiles();
                if (children != null) {
                    for (File child : children) {
                        grantPermissions(child);
                    }
                }
            } else {
                String path = file.getAbsolutePath();
                if (path.contains("/bin/") || path.endsWith(".so") || file.getName().contains("python")) {
                    file.setExecutable(true, false);
                    file.setReadable(true, false);
                }
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
