# FFmpeg 放置说明

本项目默认优先从应用根目录下的 `ffmpeg/` 文件夹查找：

- `ffmpeg.exe`
- `ffprobe.exe`
- `ffplay.exe`（可选）

也就是说：

- 源码运行时，放在项目根目录 `ffmpeg/`
- 便携版运行时，放在桌面程序同目录 `ffmpeg/`

## 推荐目录结构

```text
VideoSubtitleLearning/
  VideoSubtitleLearning.exe
  ffmpeg/
    ffmpeg.exe
    ffprobe.exe
    ffplay.exe
```

## 用户放置步骤

1. 打开 FFmpeg 官方下载页：
   [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)
2. 进入 Windows builds 页面，下载预编译版本
3. 解压压缩包
4. 把 `ffmpeg.exe` 和 `ffprobe.exe` 复制到程序同目录的 `ffmpeg/` 文件夹

## 如何验证

可以在 PowerShell 中执行：

```powershell
.\ffmpeg\ffmpeg.exe -version
.\ffmpeg\ffprobe.exe -version
```

或者直接在应用设置页查看运行时检测结果。

## 建议

- 不建议把 FFmpeg 可执行文件直接提交进 Git 仓库
- 更适合放在便携包里，或由用户按说明手动放置
