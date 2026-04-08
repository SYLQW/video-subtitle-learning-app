# 桌面便携版构建说明

这份说明对应当前项目的“同目录便携版优先”方案。

## 一键构建

在项目根目录执行：

```powershell
npm run build:portable
```

或者直接执行脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-portable.ps1
```

如果想先清空旧产物再重新打包：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-portable.ps1 -CleanOutput
```

## 默认输出目录

脚本会生成：

```text
dist-portable/
  VideoSubtitleLearning/
    VideoSubtitleLearning.exe
    backend/
    .venv/
    ffmpeg/
    models/
    data/
    outputs/
    temp/
    docs/
```

其中：

- `VideoSubtitleLearning.exe` 是 Tauri 桌面壳。
- `backend/` 是 FastAPI sidecar 代码。
- `.venv/` 是当前项目的 Python 运行环境复制品。
- `ffmpeg/` 会优先复制项目内的 `ffmpeg/`；如果项目内没有，就尝试从系统 `PATH` 中找到 `ffmpeg.exe` 所在目录并复制。
- `models/` 会复制当前项目的本地模型目录；如果没有模型，也会创建空目录。
- `data/`、`outputs/`、`temp/` 是便携版运行时目录。

## 可选参数

脚本支持这些参数：

```powershell
-OutputRoot     自定义输出根目录
-PackageName    自定义便携包目录名和 exe 名
-CleanOutput    先删除旧的同名输出目录
-PreserveRuntimeData 保留旧便携目录里的 data / outputs / temp
-SkipFrontendBuild
-SkipTauriBuild
-SkipVenvCopy
-SkipModelCopy
-SkipFFmpegCopy
```

例如：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-portable.ps1 `
  -OutputRoot G:\Builds `
  -PackageName VideoSubtitleLearning-Portable `
  -CleanOutput
```

## 运行方式

直接双击：

```text
dist-portable\VideoSubtitleLearning\VideoSubtitleLearning.exe
```

## 为什么不用 `cargo build --release`

便携版脚本现在会走：

```powershell
npm run tauri -- build --no-bundle
```

而不是直接用：

```powershell
cargo build --release
```

原因是这个项目的桌面壳必须按 Tauri 的正式构建流程产出，才能稳定使用生产模式前端资源。

如果只跑 `cargo build --release`，有可能会出现：

- exe 仍然去连开发期页面地址
- 本地 Vite 关掉后桌面版白屏
- 出现 `127.0.0.1 拒绝连接`

所以后续桌面正式包都应以 `tauri build --no-bundle` 为准。

## 关于“视频、配置被打进包里”

默认情况下，脚本现在会在构建时主动重置便携包里的：

- `data/`
- `outputs/`
- `temp/`

这样发布出来的是一个干净包，不会把你之前在便携目录里跑出来的：

- 数据库
- 设置
- 视频库
- 转写结果
- 翻译结果

一起带出去。

只有在你明确传入下面这个参数时，才会保留旧的运行数据：

```powershell
-PreserveRuntimeData
```

桌面壳启动后会：

1. 以 exe 所在目录作为 `APP_ROOT`
2. 在同目录下查找 `.venv\Scripts\python.exe`
3. 拉起 `backend.app.main:app`
4. 把 `VIDEO_SUBTITLE_APP_ROOT` 显式传给 sidecar
5. 让后端改为真正的“桌面同目录模式”

## 运行时检测

设置页里的运行时检测卡片会检查：

- 是否找到 `FFmpeg`
- 是否找到本地模型
- 是否检测到 `GPU`
- `CUDA / cuDNN` 是否完整
- `faster-whisper` 是否真的能用 `device="cuda"` 初始化

这一步是便携版排障的核心入口。

## 当前限制

- 现在的 MVP 便携包仍然是“复制现有 `.venv`”方案，还不是嵌入式 Python 精简运行时。
- `CUDA` 和 `cuDNN` 不会打进首发包里，仍然走“用户本机环境 + 应用内检测”。
- 如果目标机器没有 `WebView2 Runtime`，还需要额外安装系统运行时。
