将 FFmpeg 放到这个目录下。

当前项目默认优先查找：

- ffmpeg\ffmpeg.exe
- ffmpeg\ffprobe.exe

可选：

- ffmpeg\ffplay.exe

推荐做法：

1. 从 FFmpeg 官方下载页进入 Windows builds：
   https://ffmpeg.org/download.html
2. 下载 Windows 预编译包。
3. 解压后，把以下文件复制到当前目录：
   - ffmpeg.exe
   - ffprobe.exe
   - 可选 ffplay.exe

如果你使用的是桌面便携版，也同样放在 exe 同目录下的 ffmpeg\ 目录里。

更多说明见：

- docs/ffmpeg-setup.md
