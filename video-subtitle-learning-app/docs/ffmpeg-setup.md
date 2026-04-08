# FFmpeg 放置与用户说明

这份文档说明本项目里 `FFmpeg` 应该放在哪里，以及你对外发布时该如何教用户处理。

## 1. 本项目如何查找 FFmpeg

当前项目会优先查找应用根目录下的 `ffmpeg/` 文件夹。

也就是说：

- Web 开发模式下，默认查找项目根目录 `ffmpeg/`
- Tauri 桌面便携版下，默认查找桌面程序同目录 `ffmpeg/`

代码位置：

- `backend/app/services/app_paths.py`

当前查找规则等价于：

```text
应用根目录/
  ffmpeg/
    ffmpeg.exe
    ffprobe.exe
    ffplay.exe   (可选)
```

其中：

- `ffmpeg.exe` 用于音视频处理、导出、字幕轨封装
- `ffprobe.exe` 用于读取媒体信息
- `ffplay.exe` 对当前项目不是硬性必需，但有也没问题

## 2. 用户最容易理解的放置方式

推荐统一告诉用户：

1. 下载 FFmpeg Windows 预编译包
2. 解压
3. 把 `ffmpeg.exe` 和 `ffprobe.exe` 放到程序同目录的 `ffmpeg/` 文件夹里

示例：

```text
VideoSubtitleLearning/
  VideoSubtitleLearning.exe
  ffmpeg/
    ffmpeg.exe
    ffprobe.exe
    ffplay.exe
  models/
  data/
  outputs/
```

如果是源码运行，则对应为：

```text
video-subtitle-learning-app/
  backend/
  frontend/
  ffmpeg/
    ffmpeg.exe
    ffprobe.exe
    ffplay.exe
```

## 3. 推荐下载来源

FFmpeg 官方下载页明确说明：官方主要提供源码，Windows 可执行文件通常来自其页面列出的第三方构建源。

推荐参考：

1. FFmpeg 官方下载页  
   [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)
2. Gyan 的 Windows builds 页面  
   [https://www.gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/)

根据 FFmpeg 官方下载页，目前 Windows 构建源中包含 `gyan.dev` 和 `BtbN`。

## 4. 建议用户下载哪一种

对我们这个项目来说，一般推荐用户下载：

- Windows 64-bit
- 静态构建
- `Essentials` 版本通常就够用

原因：

- 我们主要用到的是常规转封装、探测、字幕轨处理
- 不需要用户一上来就下载最大最全的开发包
- 便携分发时也更容易管理

如果后面我们遇到某些特殊编解码需求，再改为让用户下载 `full` 版本即可。

## 5. 用户放置步骤范例

你可以直接对用户这样写：

### 方式 A：桌面便携版

1. 下载程序压缩包并解压
2. 下载 FFmpeg Windows 版本并解压
3. 在程序目录下创建 `ffmpeg` 文件夹
4. 把 `ffmpeg.exe` 和 `ffprobe.exe` 复制进去

最终结构：

```text
VideoSubtitleLearning/
  VideoSubtitleLearning.exe
  ffmpeg/
    ffmpeg.exe
    ffprobe.exe
```

### 方式 B：源码版

1. 下载本仓库源码
2. 在项目根目录创建 `ffmpeg/`
3. 把 `ffmpeg.exe` 和 `ffprobe.exe` 放进去

最终结构：

```text
video-subtitle-learning-app/
  ffmpeg/
    ffmpeg.exe
    ffprobe.exe
```

## 6. 如何验证是否放对了

项目设置页的运行时检测会检查 FFmpeg。

此外也可以手动检查：

```powershell
.\ffmpeg\ffmpeg.exe -version
.\ffmpeg\ffprobe.exe -version
```

如果这两个命令能输出版本信息，通常就说明放置正确了。

## 7. 是否需要上传到 Git 仓库

不建议把 FFmpeg 可执行文件直接提交进 Git 仓库，原因是：

- 文件体积大
- 不利于仓库保持干净
- 很容易再次触发远端文件大小限制

因此当前仓库已经建议忽略：

- `ffmpeg/*.exe`
- `ffmpeg/*.dll`
- `ffmpeg/*.7z`
- `ffmpeg/*.zip`

更推荐的做法是：

- 仓库里保留 `ffmpeg/README.txt`
- 在 Releases 或发布包里单独提供 FFmpeg
- 或者在发布说明里告诉用户去官方下载并放到指定位置

## 8. 当前项目的推荐分发策略

对这个项目而言，比较稳妥的方式是：

1. Git 仓库放源码、说明文档、模型配置文件
2. 大模型文件用 Releases 单独提供
3. FFmpeg 用以下两种方式之一：
   - 直接放进桌面便携版压缩包
   - 在发布页写清楚下载链接和放置目录

如果你希望“普通用户解压即用”，那最佳做法仍然是：

- 便携包中直接带上 `ffmpeg/ffmpeg.exe`
- 便携包中直接带上 `ffmpeg/ffprobe.exe`

这样用户就不用自己再去额外配置 FFmpeg。

## 9. 参考网页

1. FFmpeg 官方下载页  
   [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)
2. Gyan Windows builds  
   [https://www.gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/)
