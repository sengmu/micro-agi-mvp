# AGI-Bot（Micro-AGI 宿主 + 系统桌宠）

> 独立版已通过 Chaquopy 内嵌 Python、白名单资源打包和应用内启动/就绪检查。新包名 debug APK 已在 Seeker 并排安装，主角色与透明无外框桌宠均显示；含高清渲染、扩大拖动范围、钱包底部弹层和备份排除规则的测试包已安装，但这些新版交互尚未全部完成真机回归。内嵌模式会拒绝尚未移植的 Termux/登录/更新路由和 agy 命令，不能将测试包当成上线包。

桌宠已改为透明无外框，真机可见完整角色。针对用户反馈的模糊和拖动命中范围过窄，源码使用最高 3× 画布分辨率，并支持从角色内容区域拖动；新版已安装，**尚待真机手势验收**。关闭入口保留在主界面按钮与前台服务通知栏。

- 新应用 ID：`cloud.relayhub.microagi`；debug 包为 `cloud.relayhub.microagi.debug`。原手机应用 `com.sg.magi` 保留并排安装，Android Java/Kotlin 源码命名空间暂仍为 `com.sg.magi`。
- 主界面：Android 内嵌服务先绑定系统分配的 `127.0.0.1` 回环端口，验证健康响应后 WebView 才加载该地址。
- 系统桌宠：悬浮窗沿用同一已验证端口加载 `/pet.html`，不单独猜测端口。
- 新版已在 Android 进程内启动 Python 服务并渲染主页面与桌宠。桌面/旧版流程仍可单独用 Termux 在 8087 启动服务。`8085` 是旧版 Google OAuth 回调端口，内嵌模式暂不启动它。
- WebView 主页面仅允许停留在已验证的本地端口，外部 HTTP(S) 链接交给系统浏览器；主页面和桌宠的网络子资源也仅允许访问该端口。非回环 HTTP 明文被网络安全配置阻止；仍需真机验证拦截与 Cookie 行为。
- 原生 MWA 已编译入新包；用户此前在真机亲自完成连接、断开和拒绝重连。最新版弹层的同一组操作、进程重启及正式身份验证仍未验收。Solana 路线与上线阻塞项见 [SOLANA_MOBILE_PLAN.md](../SOLANA_MOBILE_PLAN.md)。
- 点击主界面的钱包入口打开原生底部弹层。新包采用经用户批准的 `https://relayhub.cloud/` 与 `favicon.ico`；Manifest 仅接收 `/micro-agi/open` 的 HTTPS App Link。手机上的 `pm get-app-links` 仍显示域名未验证状态；正式版需要同域名 `/.well-known/assetlinks.json`（包含 `cloud.relayhub.microagi` 和最终签名证书指纹）及真机系统关联核验。debug 样例、只读校验命令与域名发布步骤见 [WALLET_IDENTITY.md](WALLET_IDENTITY.md)。此功能不提供签名或转账。

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

此 Windows 工作区可运行 `./android_host/build-local-windows.ps1` 离线构建。脚本使用已有 Android 调试证书，若找不到证书会停止，避免生成签名不兼容、无法覆盖测试版的新 APK。也可传入 `-Task ':app:checkReleaseCsp'` 或 `-Task ':app:lintDebug'`。它只编译/检查，不安装或发布；此脚本针对本机已放入 `.android-tools/` 的 JDK、SDK 与 Gradle。

## 安装后使用

以下是旧版开发流程，不代表独立版已通过验收：

1. 在 Termux 中进入项目目录，运行 `bash start_service.sh`，确认 `http://127.0.0.1:8087/api/health` 返回 `ok: true`  
2. 安装旧版 APK，打开 **AGI-Bot**  
3. 点 **悬浮权限** → 允许「显示在其他应用上层」  
4. 点 **开启系统桌宠**  
5. 通知栏可关闭桌宠  

网页内的 `magi://pet/start` 与 `magi://pet/stop` 只由应用 WebView 拦截，不注册为外部 deep link；外部应用不能用它控制悬浮窗。
