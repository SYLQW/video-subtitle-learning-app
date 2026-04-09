# 视频字幕学习台

一个面向语言学习场景的视频字幕工具。

它的目标不是只做“字幕显示器”，而是把 `视频播放 + 本地转写 + 双语翻译 + 点句解析 + 学习收集` 串成一套完整流程，让用户在看视频时可以边听、边看、边点、边学。

当前项目已经具备可运行的 Web 版开发形态，并且已经接上了 Tauri 桌面壳，正在向“同目录便携版优先”的桌面应用形态推进。

## 项目定位

这个项目主要解决下面这类学习问题：

- 看英文、韩文、日文等视频时，想快速得到可对照的双语字幕
- 不只想看整段翻译，还想点开某一句做更深入的语言分析
- 想把一句话里的关键词、难句收藏起来，形成自己的学习素材库
- 想把模型、翻译服务、API Key 交给用户自己配置，而不是强绑定某一家服务
- 想在本地完成尽可能多的处理，减少长期云端成本

一句话说，这个项目是一个“视频字幕学习工作台”，而不是单一的字幕播放器。

## 目前已经实现的核心能力

### 1. 视频库与播放

- 支持本地视频库
- 支持上传视频
- 支持切换视频
- 支持删除视频
- 支持在应用内直接播放视频

### 2. 字幕处理链路

- 使用 `faster-whisper` 做本地语音转写
- 支持源语言自动识别
- 支持“全量处理”和“仅翻译”两种任务模式
- 支持任务状态轮询，避免刷新页面后丢失处理状态
- 支持防重复提交，同一个视频不会重复开多个相同任务

### 3. 双语字幕与学习模式

- 支持原文字幕
- 支持学习语言字幕
- 支持双语字幕
- 支持播放器内切换字幕轨
- 支持字幕总览区逐句查看
- 支持点击句子联动右侧高亮和解析区展示

### 4. 翻译与模型配置

- 支持 `DeepLX`
- 支持通用 OpenAI 兼容接口
- 支持多份 LLM 配置保存、切换、新增
- 支持用户自行填写：
  - `base_url`
  - `api_key`
  - `model`
  - `api_style`
- 已兼容的典型用法包括：
  - DashScope / Qwen
  - 豆包 Ark Responses
  - 通用中转 OpenAI 兼容接口

### 5. 点句解析 / 高级翻译

- 点击字幕句子可触发单句解析
- 支持流式返回解析内容
- 支持缓存，避免重复分析同一句
- 可展示：
  - 优化译文
  - 更自然的表达
  - 关键词解释
  - 语法点
  - 句子结构说明
  - 学习提示
  - 可继续追问的问题

### 6. 学习收集册

- 支持词语册
- 支持句子册
- 支持从关键词卡片收藏词语
- 支持从字幕句子收藏句子
- 支持附带解析快照保存
- 支持导出收集册

### 7. 字幕与视频导出

- 支持导出原文字幕
- 支持导出学习语言字幕
- 支持导出双语字幕
- 支持导出带字幕轨的视频

当前策略更偏向稳定的软字幕/字幕轨方案，烧录版视频不是当前主路径。

## 技术架构

当前项目采用的是前后端分离 + 桌面壳方案：

- 前端：`React + Vite`
- 桌面壳：`Tauri`
- 后端：`FastAPI`
- 本地转写：`faster-whisper`
- 视频处理：`FFmpeg`
- 数据存储：`SQLite`

### 架构思路

- `React + Vite` 负责界面和交互
- `FastAPI` 负责视频、字幕、转写、翻译、分析、配置、收集册等接口
- `Tauri` 负责把前端包装成桌面应用，并在启动时自动拉起 Python sidecar
- `faster-whisper` 负责本地语音识别
- 第三方翻译 / 大模型服务负责双语翻译和深度语言分析

## 为什么使用这套方案

### React + Vite

适合快速构建复杂交互界面，开发效率高，前端生态成熟。

### Tauri

适合把现有 Web 界面迁移成桌面应用，包体相对轻，能够保留前端开发体验。

### FastAPI

适合把本地模型调用、文件处理、数据库、导出逻辑封装成接口，便于前后端解耦。

### faster-whisper

相比很多云端 ASR 方案：

- 本地可控
- 长期成本更低
- 支持 CPU / GPU
- 适合离线或半离线使用

## 桌面版策略

当前桌面版的核心策略是：

- **同目录便携版优先**
- 程序、模型、FFmpeg、数据库、缓存、导出文件尽量都放在程序同目录
- 不优先依赖 `AppData` 这类系统目录

这样做的好处是：

- 更符合便携软件习惯
- 更方便备份和迁移
- 更容易让用户理解“哪些文件属于这个程序”

详细说明见：

- [安装与使用指南](docs/user-installation-guide.md)
- [桌面打包与部署](docs/desktop-packaging-and-deployment.md)
- [便携版构建说明](docs/portable-build-guide.md)
- [FFmpeg 放置说明](docs/ffmpeg-setup.md)

## 运行时依赖

项目在完整能力下可能用到这些运行时：

- Python 3.11
- Rust stable-msvc
- WebView2 Runtime
- FFmpeg
- CUDA 12.x
- cuDNN 9

其中：

- `FFmpeg` 用于视频处理、字幕轨导出
- `CUDA / cuDNN` 是可选增强，不是必须
- 没有 GPU 环境时，项目仍然可以退回 CPU

如果你是普通用户，而不是开发者，请优先看：

- [安装与使用指南](docs/user-installation-guide.md)

## 开发环境快速开始

### 1. Python 环境

建议使用 `uv`：

```powershell
uv venv --python 3.11
uv sync
```

### 2. 前端依赖

```powershell
npm install
npm --prefix frontend install
```

### 3. Web 开发模式

前端开发服务器：

```powershell
npm run dev:web
```

后端开发服务器：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

常用检查地址：

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

## 桌面版开发与打包

### Tauri 开发

```powershell
npm run tauri -- dev
```

### 构建便携版

```powershell
npm run build:portable
```

如果希望先清空旧产物再重新打包：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-portable.ps1 -CleanOutput
```

便携版构建脚本会：

- 构建前端生产资源
- 走 `tauri build --no-bundle`
- 复制桌面 exe
- 复制后端代码
- 复制嵌入式 Python 运行时到 `runtime/python`
- 复制 `models`
- 复制 `ffmpeg`
- 重置运行数据目录，生成干净发布包

## 项目目录说明

### 根目录

- `backend/`：FastAPI 后端
- `frontend/`：React 前端
- `src-tauri/`：Tauri 桌面壳
- `scripts/`：辅助脚本
- `docs/`：设计与部署文档
- `models/`：本地模型目录
- `data/`：本地数据库、视频库、日志等运行数据
- `outputs/`：转写、翻译、导出等结果
- `dist-portable/`：便携版构建输出

### 后端核心模块

- `transcription.py`：转写
- `translation.py`：翻译
- `analysis.py`：点句解析
- `video_library.py`：视频库管理
- `database.py`：SQLite 存储
- `runtime_env.py`：运行时检测
- `video_tasks.py`：视频处理任务状态管理
- `app_paths.py`：统一路径层

## 相关设计文档

- [桌面打包与部署](docs/desktop-packaging-and-deployment.md)
- [便携版构建说明](docs/portable-build-guide.md)
- [FFmpeg 放置说明](docs/ffmpeg-setup.md)
- [安装与使用指南](docs/user-installation-guide.md)
- [多语言字幕设计](docs/multilingual-subtitle-design.md)
- [收集册设计](docs/collection-notebook-design.md)
- [收集册 PDF 导出设计](docs/notebook-pdf-export-design.md)
- [图标备选方案](docs/icon-style-ideas.md)

## 隐私与密钥说明

这个项目支持用户自己配置翻译服务和大模型 API。

需要特别注意：

- 用户填写的模型配置、API Key、翻译服务 URL 可能会保存在本地运行数据中
- 当前默认运行数据位于本地 `data/` 目录和桌面便携包对应目录内
- **不要把自己的运行数据目录直接公开分享**
- **不要把带有个人配置的便携包直接发给别人**

如果你要对外分享项目，建议：

- 只分享 Git 仓库代码
- 使用干净的便携发布包
- 在公开演示前清理本地 `data/` 和便携包中的运行数据

## 当前阶段说明

这个项目目前仍在快速迭代中，重点在于：

- 打通完整学习链路
- 提升桌面版稳定性
- 做好多语言学习支持
- 完善便携发布能力

它已经不是单纯的原型页面，而是一个正在逐步具备真实可用性的桌面学习工具。

## 未来计划

接下来适合继续推进的方向包括：

- 更完善的任务进度展示
- 更稳定的句子切分与时间对齐
- 更强的本地模型管理
- 更完整的收集册复习流程
- 更多语言组合支持
- 更统一的品牌与视觉设计

## License

当前仓库尚未添加正式 License。

如果你准备公开发布，建议在后续补充明确的开源协议与第三方依赖说明。
