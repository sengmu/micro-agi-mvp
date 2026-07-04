package com.sg.magi;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

import androidx.core.app.NotificationCompat;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class AGIService extends Service {
    private static final String TAG = "AGIService";
    private static final String CHANNEL_ID = "AGIServiceChannel";
    private Process pythonProcess = null;
    private Thread workerThread = null;

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Intent notificationIntent = new Intent(this, MainActivity.class);
        PendingIntent pendingIntent = PendingIntent.getActivity(this,
                0, notificationIntent, PendingIntent.FLAG_IMMUTABLE);

        Notification notification = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("Micro-AGI 智能体服务")
                .setContentText("智能体后台常驻引擎运行中...")
                .setSmallIcon(android.R.drawable.sym_def_app_icon)
                .setContentIntent(pendingIntent)
                .build();

        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(1, notification, android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        } else {
            startForeground(1, notification);
        }

        // 启动后台 Python 服务器
        if (workerThread == null) {
            workerThread = new Thread(new Runnable() {
                @Override
                public void run() {
                    startPythonServer();
                }
            });
            workerThread.start();
        }

        return START_STICKY;
    }

    private void startPythonServer() {
        try {
            File filesDir = getFilesDir();
            File appPy = new File(filesDir, "home/micro-agi-mvp/app.py");

            if (!appPy.exists()) {
                Log.e(TAG, "Python 核心文件 app.py 不存在！路径: " + appPy.getAbsolutePath());
                return;
            }

            // 直接调用 Termux 下被系统授权且已编译好、具有执行权限的 Python 解释器
            File pythonBin = new File("/data/data/com.termux/files/usr/bin/python");
            if (!pythonBin.exists()) {
                pythonBin = new File("/data/data/com.termux/files/usr/bin/python3");
            }

            Log.i(TAG, "正在借用 Termux 唤起 Python 解释器: " + pythonBin.getAbsolutePath());

            List<String> cmd = new ArrayList<>();
            cmd.add(pythonBin.getAbsolutePath());
            cmd.add(appPy.getAbsolutePath());

            ProcessBuilder pb = new ProcessBuilder(cmd);
            pb.directory(appPy.getParentFile());

            // 注入 Termux 环境变量以保证 Python 正常运行
            Map<String, String> env = pb.environment();
            String termuxUsr = "/data/data/com.termux/files/usr";
            env.put("PATH", termuxUsr + "/bin:" + System.getenv("PATH"));
            env.put("LD_LIBRARY_PATH", termuxUsr + "/lib");
            env.put("PYTHONHOME", termuxUsr);
            env.put("PYTHONPATH", termuxUsr + "/lib/python3.13:" + termuxUsr + "/lib/python3.13/site-packages");
            env.put("HOME", "/data/data/com.termux/files/home");
            env.put("SHELL", termuxUsr + "/bin/sh");

            pb.redirectErrorStream(true);
            pythonProcess = pb.start();

            BufferedReader reader = new BufferedReader(new InputStreamReader(pythonProcess.getInputStream()));
            String line;
            while ((line = reader.readLine()) != null) {
                Log.d("PythonStdout", line);
            }

            int exitCode = pythonProcess.waitFor();
            Log.w(TAG, "Python 服务非正常退出，退出码: " + exitCode);
        } catch (Exception e) {
            Log.e(TAG, "启动 Python 服务发生异常", e);
        }
    }

    @Override
    public void onDestroy() {
        if (pythonProcess != null) {
            pythonProcess.destroy();
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel serviceChannel = new NotificationChannel(
                    CHANNEL_ID,
                    "Micro-AGI Service Channel",
                    NotificationManager.IMPORTANCE_DEFAULT
            );
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(serviceChannel);
            }
        }
    }
}
