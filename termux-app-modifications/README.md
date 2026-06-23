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

### 4. 自动解压与首启脚本初始化（Java 已自动化完成）
修改后的 `TermuxActivity.java` 内部已内置了自动化操作，无需手动配置 `.bashrc`：
* **国内镜像优化**：自动检测国内用户网络，首启时非交互式自动将 Termux 软件源切换至 **清华大学开源软件镜像站 (Tsinghua Mirror)**，并将 `pip` 下载源配置为清华大学 Simple 镜像，大幅提升国内用户安装 Python/FFmpeg 的成功率与速度（提升近百倍）。
* **自动化解压**：自动把 APK Assets 里的 `micro-agi-mvp.zip` 释放解压至手机主目录。
* **自启动运行**：自动在 `.bashrc` 底部追加 `tmux` 后台服务拉起脚本，实现应用安装并打开即可无感秒开。

### 5. 编译 APK
在 Android Studio 中打开项目，等待 Gradle 同步完成，然后点击 **`Build -> Build Bundle(s) / APK(s) -> Build APK(s)`**。
编译完成后即可获得一个完全独立的 `.apk` 文件。安装并启动时，用户不会看到终端命令行，而是直接开启您的 Hiyori 智能体主界面，但底层却拥有完整的 Termux 环境与命令执行能力！
