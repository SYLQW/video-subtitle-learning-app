# 安装与使用指南

这份文档把“普通用户使用”和“开发者运行源码”分开说明。

最重要的一句话是：

- 如果用户下载的是你打好的桌面便携包，通常不需要自己安装 `Python`、`npm`、`Node.js`
- 如果用户下载的是 Git 仓库源码，才需要自己配置开发环境

## 1. 普通用户能不能下载后直接用

分两种情况。

### 情况 A：下载桌面便携包

如果你发布的是完整便携包，并且里面已经带了这些内容：

- `VideoSubtitleLearning.exe`
- `backend/`
- `runtime/python/`
- `models/`
- `ffmpeg/`

那么普通用户通常不需要再装：

- Python
- npm
- Node.js
- Rust

他们只需要：

1. 解压便携包
2. 补齐缺失的模型文件 `model.bin`（如果你没有直接打进包）
3. 补齐 `ffmpeg.exe` / `ffprobe.exe`（如果你没有直接打进包）
4. 双击 `VideoSubtitleLearning.exe`

### 情况 B：只下载 Git 仓库源码

这种情况下，普通用户不能算“下载后直接用”。

因为源码仓库里通常不会自带：

- Python 虚拟环境
- `node_modules`
- 本地数据库
- 视频文件
- 大模型文件
- FFmpeg 可执行文件

所以源码下载更适合开发者，不适合普通用户直接拿来双击使用。

## 2. 普通用户推荐的使用方式

推荐你对外分发时使用：

- Git 仓库：只放源码和文档
- Releases / 网盘 / 压缩包：放桌面便携版

对于普通用户，应当优先告诉他们下载：

- 便携版压缩包

而不是：

- 仓库源码 zip

## 3. 便携版用户需要准备什么

### 必需

- 程序主文件
- 后端代码
- Python 运行环境 `runtime/python`
- 本地 Whisper 模型目录
- FFmpeg

### 可选增强

- NVIDIA GPU
- CUDA 12.x
- cuDNN 9

没有 GPU 时，仍然可以跑，只是会更慢。

## 4. 便携版推荐目录结构

推荐目录结构如下：

```text
VideoSubtitleLearning/
  VideoSubtitleLearning.exe
  WebView2Loader.dll
  backend/
  runtime/
    python/
  models/
    faster-whisper-base/
      config.json
      tokenizer.json
      vocabulary.txt
      model.bin
  ffmpeg/
    ffmpeg.exe
    ffprobe.exe
    ffplay.exe
  data/
  outputs/
  temp/
  docs/
```

## 5. 用户第一次使用时应该怎么做

### 第一步：准备模型

当前项目默认从应用根目录下的 `models/` 读取本地模型。

对 `faster-whisper-base`，目录里需要这四个文件：

- `config.json`
- `tokenizer.json`
- `vocabulary.txt`
- `model.bin`

其中：

- 前三个小文件可以跟随仓库或便携包提供
- `model.bin` 可以通过 Releases 单独下载后放进去

放置路径示例：

```text
VideoSubtitleLearning\models\faster-whisper-base\model.bin
```

### 第二步：准备 FFmpeg

把下面文件放到程序同目录的 `ffmpeg/` 里：

- `ffmpeg.exe`
- `ffprobe.exe`

可选：

- `ffplay.exe`

放置路径示例：

```text
VideoSubtitleLearning\ffmpeg\ffmpeg.exe
VideoSubtitleLearning\ffmpeg\ffprobe.exe
```

### 第三步：双击启动

直接运行：

```text
VideoSubtitleLearning.exe
```

### 第四步：在设置页检查运行时状态

设置页会检查：

- 是否找到 `FFmpeg`
- 是否找到模型
- 是否检测到 GPU
- `CUDA / cuDNN` 是否完整

如果某项缺失，优先先补齐这几个基础运行时。

## 6. 普通用户是否需要安装 Python / npm / Node.js

如果你发给他们的是完整便携包：

- 不需要安装 Python
- 不需要安装 npm
- 不需要安装 Node.js

这些是开发环境依赖，不是普通用户使用桌面便携版的前提。

## 7. 哪些情况仍然需要额外安装系统运行时

### 7.1 WebView2 Runtime

Tauri 桌面版依赖系统的 WebView2。

如果目标机器没有安装 WebView2 Runtime，桌面程序可能无法正常显示界面。

### 7.2 CUDA / cuDNN

如果用户希望本地语音识别尽量走 GPU，则还需要安装：

- CUDA 12.x
- cuDNN 9

如果不装，也不是完全不能用，只是会退回 CPU。

## 8. 给普通用户的最简说明模板

你以后完全可以直接把下面这段发给用户：

1. 下载并解压程序压缩包
2. 把 `model.bin` 放到 `models/faster-whisper-base/`
3. 把 `ffmpeg.exe` 和 `ffprobe.exe` 放到 `ffmpeg/`
4. 双击 `VideoSubtitleLearning.exe`
5. 打开设置页，确认模型和 FFmpeg 都已识别

## 9. 开发者运行源码时需要什么

如果对方不是普通用户，而是想参与开发、自己跑源码，那么才需要下面这些环境：

- Python 3.11
- `uv`
- Node.js / npm
- Rust stable-msvc
- WebView2 Runtime

可选：

- FFmpeg
- CUDA 12.x
- cuDNN 9

## 10. 开发者源码运行步骤

### 10.1 Python

```powershell
uv venv --python 3.11
uv sync
```

### 10.2 前端依赖

```powershell
npm install
npm --prefix frontend install
```

### 10.3 启动 Web 开发模式

前端：

```powershell
npm run dev:web
```

后端：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

### 10.4 启动 Tauri 开发模式

```powershell
npm run tauri -- dev
```

## 11. 相关阅读

- `README.md`
- `docs/portable-build-guide.md`
- `docs/desktop-packaging-and-deployment.md`
- `docs/ffmpeg-setup.md`
- `docs/cuda-cudnn-setup.md`
