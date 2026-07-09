# AGI-Bot（Micro-AGI 宿主 + 系统桌宠）

- 应用 ID：`com.sg.magi`
- 主界面：WebView 打开 `http://127.0.0.1:8085/`
- 系统桌宠：悬浮窗加载 `http://127.0.0.1:8085/pet.html`

## 在线编译（GitHub Actions）

1. 把本仓库（含 `android_host/`）推到 GitHub  
2. 打开仓库 → **Actions** → **Build AGI-Bot APK** → **Run workflow**  
3. 跑完后点该次运行 → **Artifacts** → 下载 `agi-bot-debug`  
4. 得到 `app-debug.apk`，传到手机安装  

推送 `android_host/**` 到 `main` 也会自动编译。

## 本机编译

```bash
cd android_host
./gradlew :app:assembleDebug
# 输出：app/build/outputs/apk/debug/app-debug.apk
```

## 安装后使用

1. 手机上 Termux 先保证 `http://127.0.0.1:8085/` 可打开  
2. 安装 APK，打开 **AGI-Bot**  
3. 点 **悬浮权限** → 允许「显示在其他应用上层」  
4. 点 **开启系统桌宠**  
5. 通知栏可关闭桌宠  

Deep link：

- `magi://pet/start` 开启  
- `magi://pet/stop` 关闭  
