package com.sg.magi;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.provider.Settings;
import android.util.DisplayMetrics;
import android.util.Log;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.Toast;

import androidx.core.app.NotificationCompat;

/**
 * 系统级 Live2D 桌宠：悬浮窗 + WebView 加载 /pet.html
 * 需要 SYSTEM_ALERT_WINDOW 权限。
 */
public class PetOverlayService extends Service {
    private static final String TAG = "PetOverlayService";
    private static final String CHANNEL_ID = "PetOverlayChannel";
    private static final int NOTIF_ID = 42;
    public static final String ACTION_START = "com.sg.magi.action.PET_START";
    public static final String ACTION_STOP = "com.sg.magi.action.PET_STOP";
    public static final String EXTRA_URL = "pet_url";

    private WindowManager windowManager;
    private FrameLayout root;
    private WebView webView;
    private WindowManager.LayoutParams params;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    private int petW;
    private int petH;
    private boolean touchOnDragBar = false;

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent != null ? intent.getAction() : ACTION_START;
        if (ACTION_STOP.equals(action)) {
            stopSelf();
            return START_NOT_STICKY;
        }

        if (!Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "请先授予「显示在其他应用上层」权限", Toast.LENGTH_LONG).show();
            Intent perm = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:" + getPackageName()));
            perm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(perm);
            stopSelf();
            return START_NOT_STICKY;
        }

        startAsForeground();
        String url = intent != null ? intent.getStringExtra(EXTRA_URL) : null;
        if (url == null || url.isEmpty()) {
            url = "http://127.0.0.1:8085/pet.html";
        }
        showOverlay(url);
        return START_STICKY;
    }

    private void startAsForeground() {
        Intent open = new Intent(this, MainActivity.class);
        open.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        PendingIntent pi = PendingIntent.getActivity(
                this, 0, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        Intent stop = new Intent(this, PetOverlayService.class);
        stop.setAction(ACTION_STOP);
        PendingIntent stopPi = PendingIntent.getService(
                this, 1, stop,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        Notification notification = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("日和桌宠运行中")
                .setContentText("点击打开 Micro-AGI · 通知栏可关闭桌宠")
                .setSmallIcon(android.R.drawable.ic_menu_myplaces)
                .setContentIntent(pi)
                .addAction(0, "关闭桌宠", stopPi)
                .setOngoing(true)
                .build();

        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIF_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        } else {
            startForeground(NOTIF_ID, notification);
        }
    }

    private void showOverlay(String url) {
        if (root != null) {
            // already showing — just reload
            if (webView != null) webView.loadUrl(url);
            return;
        }

        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        DisplayMetrics dm = getResources().getDisplayMetrics();
        petW = (int) (128 * dm.density);
        petH = (int) (188 * dm.density);

        params = new WindowManager.LayoutParams(
                petW,
                petH,
                Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                        ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                        : WindowManager.LayoutParams.TYPE_PHONE,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
                        | WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,
                PixelFormat.TRANSLUCENT
        );
        params.gravity = Gravity.TOP | Gravity.START;
        params.x = dm.widthPixels - petW - (int) (12 * dm.density);
        params.y = dm.heightPixels - petH - (int) (120 * dm.density);
        params.softInputMode = WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE;

        root = new FrameLayout(this);
        root.setBackgroundColor(Color.TRANSPARENT);

        webView = new WebView(this);
        WebSettings ws = webView.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setMediaPlaybackRequiresUserGesture(false);
        ws.setAllowFileAccess(true);
        ws.setAllowContentAccess(true);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            ws.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        }
        webView.setBackgroundColor(Color.TRANSPARENT);
        webView.setLayerType(View.LAYER_TYPE_HARDWARE, null);
        webView.addJavascriptInterface(new PetBridge(), "PetBridge");
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
                Log.e(TAG, "WebView error: " + description + " url=" + failingUrl);
                mainHandler.postDelayed(() -> {
                    if (webView != null) webView.loadUrl(failingUrl);
                }, 2000);
            }
        });

        // 原生顶栏拖动手柄（WebView 会吃掉触摸，必须原生层处理拖动）
        final float density = getResources().getDisplayMetrics().density;
        final int handleH = (int) (32 * density);
        View dragHandle = new View(this);
        dragHandle.setBackgroundColor(Color.parseColor("#66000000"));
        dragHandle.setContentDescription("拖动桌宠");
        dragHandle.setOnTouchListener(new View.OnTouchListener() {
            private int lastX, lastY, paramX, paramY;

            @Override
            public boolean onTouch(View v, MotionEvent event) {
                switch (event.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        lastX = (int) event.getRawX();
                        lastY = (int) event.getRawY();
                        paramX = params.x;
                        paramY = params.y;
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        int dx = (int) event.getRawX() - lastX;
                        int dy = (int) event.getRawY() - lastY;
                        params.x = paramX + dx;
                        params.y = paramY + dy;
                        try {
                            windowManager.updateViewLayout(root, params);
                        } catch (Exception e) {
                            Log.w(TAG, "updateViewLayout failed", e);
                        }
                        return true;
                    default:
                        return false;
                }
            }
        });

        FrameLayout.LayoutParams webLp = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
        );
        root.addView(webView, webLp);

        FrameLayout.LayoutParams handleLp = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                handleH,
                Gravity.TOP
        );
        root.addView(dragHandle, handleLp);

        try {
            windowManager.addView(root, params);
            webView.loadUrl(url);
            Toast.makeText(this, "桌宠已开启", Toast.LENGTH_SHORT).show();
        } catch (Exception e) {
            Log.e(TAG, "addView failed", e);
            Toast.makeText(this, "悬浮窗启动失败: " + e.getMessage(), Toast.LENGTH_LONG).show();
            stopSelf();
        }
    }

    private void removeOverlay() {
        try {
            if (webView != null) {
                webView.loadUrl("about:blank");
                webView.stopLoading();
                webView.destroy();
                webView = null;
            }
            if (root != null && windowManager != null) {
                windowManager.removeView(root);
            }
        } catch (Exception e) {
            Log.w(TAG, "removeOverlay", e);
        }
        root = null;
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel ch = new NotificationChannel(
                    CHANNEL_ID, "桌宠悬浮窗", NotificationManager.IMPORTANCE_LOW);
            ch.setDescription("Live2D 桌宠前台服务");
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) nm.createNotificationChannel(ch);
        }
    }

    @Override
    public void onDestroy() {
        removeOverlay();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    public class PetBridge {
        @JavascriptInterface
        public void close() {
            mainHandler.post(() -> stopSelf());
        }

        @JavascriptInterface
        public void ready() {
            Log.i(TAG, "pet web ready");
        }

        @JavascriptInterface
        public void setDragging(boolean dragging) {
            touchOnDragBar = dragging;
        }

        @JavascriptInterface
        public void openMain() {
            Intent i = new Intent(PetOverlayService.this, MainActivity.class);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(i);
        }
    }

    public static boolean canDrawOverlays(Context ctx) {
        return Settings.canDrawOverlays(ctx);
    }

    public static void requestOverlayPermission(Context ctx) {
        Intent perm = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:" + ctx.getPackageName()));
        perm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        ctx.startActivity(perm);
    }

    public static void start(Context ctx, String url) {
        Intent i = new Intent(ctx, PetOverlayService.class);
        i.setAction(ACTION_START);
        if (url != null) i.putExtra(EXTRA_URL, url);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            ctx.startForegroundService(i);
        } else {
            ctx.startService(i);
        }
    }

    public static void stop(Context ctx) {
        Intent i = new Intent(ctx, PetOverlayService.class);
        i.setAction(ACTION_STOP);
        ctx.startService(i);
        ctx.stopService(i);
    }
}
