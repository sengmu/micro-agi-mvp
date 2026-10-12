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
import android.os.Build;
import android.os.IBinder;
import android.provider.Settings;
import android.util.DisplayMetrics;
import android.util.Log;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewConfiguration;
import android.view.WindowManager;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceError;
import android.webkit.WebResourceResponse;
import android.webkit.CookieManager;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.RenderProcessGoneDetail;
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
    public static final String ACTION_START = "cloud.relayhub.microagi.action.PET_START";
    public static final String ACTION_STOP = "cloud.relayhub.microagi.action.PET_STOP";
    private static final String EXTRA_BACKEND_PORT = "cloud.relayhub.microagi.extra.BACKEND_PORT";

    private WindowManager windowManager;
    private FrameLayout root;
    private WebView webView;
    private WindowManager.LayoutParams params;
    private volatile String petUrl;
    private volatile int backendPort = -1;

    private int petW;
    private int petH;

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent != null ? intent.getAction() : null;
        if (ACTION_STOP.equals(action)) {
            stopSelf();
            return START_NOT_STICKY;
        }
        // A restarted service may outlive the authenticated embedded server.
        // Never load its WebView without an explicit start after MainActivity's
        // backend health check.
        if (!ACTION_START.equals(action)) {
            stopSelf();
            return START_NOT_STICKY;
        }
        int port = intent.getIntExtra(EXTRA_BACKEND_PORT, -1);
        if (port < 1 || port > 65535) {
            stopSelf();
            return START_NOT_STICKY;
        }
        petUrl = "http://127.0.0.1:" + port + "/pet.html";
        backendPort = port;

        if (!Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "请先授予「显示在其他应用上层」权限", Toast.LENGTH_LONG).show();
            // A foreground service (including its notification STOP action)
            // must never launch an Activity indirectly. MainActivity owns the
            // explicit, user-initiated permission flow.
            stopSelf();
            return START_NOT_STICKY;
        }

        try {
            startAsForeground();
            showOverlay();
        } catch (RuntimeException e) {
            Log.e(TAG, "Unable to start pet foreground service", e);
            stopSelf();
        }
        return START_NOT_STICKY;
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

    private void showOverlay() {
        if (root != null) {
            // already showing — just reload
            if (webView != null) webView.loadUrl(petUrl);
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
        ws.setAllowFileAccess(false);
        ws.setAllowContentAccess(false);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, false);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            ws.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        }
        webView.setBackgroundColor(Color.TRANSPARENT);
        webView.setLayerType(View.LAYER_TYPE_HARDWARE, null);
        // A narrow top handle is hard to hit once its visual bar is gone.
        // Dragging anywhere in the pet window now moves it, while taps still
        // reach Live2D for its touch animation.
        webView.setOnTouchListener(createDragListener(true));
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
                // Remove only this failed WebView; the main Activity may share
                // the same renderer and receives its own callback.
                if (view.getParent() instanceof ViewGroup) {
                    ((ViewGroup) view.getParent()).removeView(view);
                }
                view.destroy();
                if (webView == view) webView = null;
                stopSelf();
                return true;
            }

            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return LocalWebViewPolicy.intercept(
                        request != null ? request.getUrl() : null, backendPort);
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, android.webkit.WebResourceRequest request) {
                return request == null || request.getUrl() == null
                        || !petUrl.equals(request.getUrl().toString());
            }

            @SuppressWarnings("deprecation")
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return !petUrl.equals(url);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request,
                    WebResourceError error) {
                if (request != null && request.isForMainFrame()) {
                    Log.e(TAG, "Pet page network error; stopping overlay");
                    stopSelf();
                }
            }

            @Override
            public void onReceivedHttpError(WebView view, WebResourceRequest request,
                    WebResourceResponse errorResponse) {
                if (request != null && request.isForMainFrame()) {
                    Log.e(TAG, "Pet page HTTP error; stopping overlay");
                    stopSelf();
                }
            }
        });

        // Invisible native drag area: WebView consumes touches, but the pet
        // should appear as the character alone with no surrounding toolbar.
        final float density = getResources().getDisplayMetrics().density;
        final int handleH = (int) (32 * density);
        FrameLayout dragHandle = new FrameLayout(this);
        dragHandle.setBackgroundColor(Color.TRANSPARENT);
        dragHandle.setContentDescription("按住角色顶部拖动桌宠");
        dragHandle.setOnTouchListener(createDragListener(false));

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
            webView.loadUrl(petUrl);
            Toast.makeText(this, "桌宠已开启；从角色顶部拖动，通知栏可关闭", Toast.LENGTH_LONG).show();
        } catch (Exception e) {
            Log.e(TAG, "addView failed", e);
            Toast.makeText(this, "悬浮窗启动失败: " + e.getMessage(), Toast.LENGTH_LONG).show();
            stopSelf();
        }
    }

    private View.OnTouchListener createDragListener(boolean preserveTap) {
        final int touchSlop = ViewConfiguration.get(this).getScaledTouchSlop();
        return new View.OnTouchListener() {
            private float downX, downY;
            private int startX, startY;
            private boolean dragging;

            @Override
            public boolean onTouch(View v, MotionEvent event) {
                switch (event.getActionMasked()) {
                    case MotionEvent.ACTION_DOWN:
                        downX = event.getRawX();
                        downY = event.getRawY();
                        startX = params.x;
                        startY = params.y;
                        dragging = false;
                        return !preserveTap;
                    case MotionEvent.ACTION_MOVE:
                        float dx = event.getRawX() - downX;
                        float dy = event.getRawY() - downY;
                        if (!dragging && Math.hypot(dx, dy) <= touchSlop) {
                            return !preserveTap;
                        }
                        if (!dragging && preserveTap) {
                            MotionEvent cancel = MotionEvent.obtain(event);
                            cancel.setAction(MotionEvent.ACTION_CANCEL);
                            v.onTouchEvent(cancel);
                            cancel.recycle();
                        }
                        dragging = true;
                        DisplayMetrics screen = getResources().getDisplayMetrics();
                        params.x = Math.max(0, Math.min(startX + Math.round(dx),
                                Math.max(0, screen.widthPixels - petW)));
                        params.y = Math.max(0, Math.min(startY + Math.round(dy),
                                Math.max(0, screen.heightPixels - petH)));
                        try {
                            windowManager.updateViewLayout(root, params);
                        } catch (Exception e) {
                            Log.w(TAG, "updateViewLayout failed", e);
                        }
                        return true;
                    case MotionEvent.ACTION_UP:
                    case MotionEvent.ACTION_CANCEL:
                        boolean wasDragging = dragging;
                        dragging = false;
                        return !preserveTap || wasDragging;
                    default:
                        return !preserveTap || dragging;
                }
            }
        };
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
        MainActivity.onPetServiceStopped();
        removeOverlay();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    public static boolean canDrawOverlays(Context ctx) {
        return Settings.canDrawOverlays(ctx);
    }

    public static boolean start(Context ctx, int port) {
        if (port < 1 || port > 65535) return false;
        Intent i = new Intent(ctx, PetOverlayService.class);
        i.setAction(ACTION_START);
        i.putExtra(EXTRA_BACKEND_PORT, port);
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                ctx.startForegroundService(i);
            } else {
                ctx.startService(i);
            }
            return true;
        } catch (RuntimeException e) {
            Log.e(TAG, "Unable to request pet service start", e);
            MainActivity.onPetServiceStopped();
            return false;
        }
    }

    public static void stop(Context ctx) {
        Intent i = new Intent(ctx, PetOverlayService.class);
        ctx.stopService(i);
    }
}
