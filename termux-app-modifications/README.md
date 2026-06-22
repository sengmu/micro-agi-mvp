# Termux 源码改造打包为独立 AGI 安卓 App 指南

本文件夹包含将开源的 **[termux-app](https://github.com/termux/termux-app)** 项目改造成内嵌 WebView 的独立 AGI 智能体 App 的核心文件和修改方案。

---

## 📂 改造文件清单
1. **[activity_termux.xml](file:///data/data/com.termux/files/home/micro-agi-mvp/termux-app-modifications/activity_termux.xml)**: 原生界面布局文件，加入全屏 WebView。
2. **[TermuxActivity.java](file:///data/data/com.termux/files/home/micro-agi-mvp/termux-app-modifications/TermuxActivity.java)**: 主 Activity 代码修改，负责后台启动 Python 服务器并用 WebView 展示 UI。

---

## 🛠️ 打包步骤

### 1. 克隆官方 Termux 源码
在您的电脑（已配置 Android Studio、JDK 和 Android SDK）上克隆官方源码：
```bash
git clone https://github.com/termux/termux-app.git
```

### 2. 替换界面布局文件
把 **`activity_termux.xml`** 拷贝并覆盖至源码中的下述路径：
`app/src/main/res/layout/activity_termux.xml`

### 3. 覆盖主控制器代码
把 **`TermuxActivity.java`** 拷贝并覆盖至源码中的下述路径：
`app/src/main/java/com/termux/app/TermuxActivity.java`

### 4. 配置首启自运行脚本
在打包前，我们需要让终端在初始化后自动进入项目目录并开启服务。
在 Termux 源码的 `app/src/main/assets/` 下（或通过在系统初始化脚本 `termux-login.sh` / `.bashrc` 中写入）：
```bash
# 自动启动 Python 后端与语音唤醒守护进程
if [ ! -f ~/.bootstrapped ]; then
    # 首次启动，安装依赖并做标记
    pkg update -y
    pkg install -y python ffmpeg termux-api git
    pip install speechrecognition requests
    touch ~/.bootstrapped
fi

# 启动 Web 服务
cd ~/micro-agi-mvp
tmux new-session -d -s micro-agi "python app.py"
tmux new-session -d -s micro-agi-wake "python wake_word_daemon.py"
```

### 5. 编译 APK
在 Android Studio 中打开项目，等待 Gradle 同步完成，然后点击 **`Build -> Build Bundle(s) / APK(s) -> Build APK(s)`**。
编译完成后即可获得一个完全独立的 `.apk` 文件。安装并启动时，用户不会看到终端命令行，而是直接开启您的 Hiyori 智能体主界面，但底层却拥有完整的 Termux 环境与命令执行能力！
