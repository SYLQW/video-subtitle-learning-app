# 桌面版运行时策略：CPU/GPU 双模式与 CUDA/cuDNN 方案

## 目标

这份文档记录桌面版的运行时策略，重点解决下面这个问题：

- 应用需要 `faster-whisper`、FFmpeg、SQLite、本地文件读写
- 部分用户希望使用 `CUDA + cuDNN` 获得更快的转写速度
- 但桌面版又希望尽量做到“安装后即可使用”

结论是：

- 首发桌面版必须保证 **CPU 模式可用**
- `CUDA + cuDNN` 作为 **可选加速能力**
- 不能把 GPU 环境作为应用是否可运行的前提

## 总体原则

### 1. 默认可用优先

桌面版安装完成后，即使用户没有：

- NVIDIA 显卡
- CUDA Toolkit
- cuDNN
- 对应版本驱动

应用也必须能够：

- 打开视频
- 进行基础转写
- 生成字幕
- 调用在线翻译与解析模型

只是速度会比 GPU 模式慢。

### 2. GPU 是增强，不是门槛

GPU 模式只负责提升：

- `faster-whisper` 转写速度
- 大视频处理效率
- 批量处理吞吐

如果本机 GPU 环境不完整，应用应自动回退到 CPU，而不是报错退出。

### 3. 先做“能运行”，再做“更快”

桌面版第一阶段优先级：

1. Tauri 桌面壳可运行
2. Python sidecar 可运行
3. CPU 模式完整可用
4. GPU 自动检测与切换
5. 最后再考虑更激进的 GPU 打包策略

## 推荐架构

当前项目推荐采用：

- UI：`React + Vite`
- 桌面壳：`Tauri`
- 本地服务：`FastAPI sidecar`
- 转写：`faster-whisper`
- 视频处理：`FFmpeg`
- 数据库存储：`SQLite`

运行时分层如下：

1. Tauri 负责窗口、应用生命周期、桌面权限、安装包
2. Python sidecar 负责转写、翻译、分析、文件处理
3. 前端通过本地 HTTP API 调 Python sidecar
4. Python sidecar 在启动时决定当前使用 CPU 还是 GPU

## 为什么不能把 CUDA/cuDNN 做成“真正开箱即用”

原因不是我们项目结构的问题，而是 CUDA 生态本身决定的：

- 依赖用户机器上的 NVIDIA 显卡
- 强依赖显卡驱动版本
- 强依赖 CUDA 与 cuDNN 版本匹配
- 还要和 `ctranslate2`、`faster-whisper` 所需版本匹配
- 不同用户电脑差异很大

因此，桌面应用一般不把 CUDA/cuDNN 当成“必装前置条件”，否则会严重影响安装成功率与维护成本。

## 最终产品策略

### 方案选择

推荐采用：

- 单一安装包
- 默认 CPU 可用
- 自动检测 GPU 环境
- 条件满足时自动启用 GPU
- 条件不满足时静默回退 CPU

不推荐：

- 只发布 GPU 版
- 要求所有用户手动先装 CUDA/cuDNN 才能启动

### 用户体验策略

用户安装后首次启动：

1. 应用启动 Python sidecar
2. sidecar 检测本机 GPU 环境
3. 如果检测通过，启用 GPU
4. 如果检测失败，自动切 CPU
5. 前端设置页显示当前状态

前端应明确展示：

- 当前转写模式：`CPU` 或 `GPU`
- 是否检测到 NVIDIA GPU
- 是否检测到 CUDA
- 是否检测到 cuDNN
- 当前实际使用的 `device`
- 当前实际使用的 `compute_type`

## 推荐的运行模式

### 模式 A：CPU 默认模式

适合：

- 所有用户
- 首发桌面版
- 对稳定性要求高的场景

建议默认参数：

- `device = cpu`
- `compute_type = int8`

特点：

- 启动简单
- 环境依赖最少
- 运行最稳
- 速度较慢，但可以接受

### 模式 B：GPU 加速模式

适合：

- 已安装 NVIDIA 驱动
- 已具备可用 CUDA/cuDNN 环境
- 对转写速度敏感的用户

建议默认参数：

- `device = cuda`
- `compute_type = float16`

特点：

- 转写明显更快
- 环境更脆弱
- 需要版本匹配

## 检测逻辑

### 启动时检测项

Python sidecar 启动时建议检测：

1. 是否存在 NVIDIA GPU
2. 是否能执行 `nvidia-smi`
3. 是否能找到可用 CUDA 运行时
4. 是否能找到 cuDNN 动态库
5. `faster-whisper / ctranslate2` 是否能成功以 `device=cuda` 初始化

### 判定优先级

建议判定流程：

1. 如果用户在设置中强制指定 `cpu`
   - 直接使用 CPU
2. 如果用户选择 `auto`
   - 先检测 GPU 环境
   - 检测通过则 GPU
   - 否则 CPU
3. 如果用户强制指定 `cuda`
   - 尝试 GPU 初始化
   - 失败时提示错误，并允许一键回退到 CPU

### 最可靠的检测方式

不要只靠环境变量判断。

最可靠的做法是：

- 实际尝试初始化 `faster-whisper` 的 CUDA 模式
- 成功就视为 GPU 可用
- 失败就回退 CPU，并记录错误原因

## 设置页设计建议

桌面版设置页建议新增“运行环境”区域。

### 建议字段

- 转写模式：`auto / cpu / cuda`
- 当前实际模式：`cpu` 或 `cuda`
- GPU 检测状态：成功 / 失败
- CUDA 状态：已检测 / 未检测
- cuDNN 状态：已检测 / 未检测
- 错误详情：仅在失败时展开

### 建议提示文案

- `当前使用 CPU 模式，适合所有设备，速度较慢但最稳定。`
- `已检测到可用 GPU 环境，当前启用 CUDA 加速。`
- `未检测到完整 CUDA/cuDNN 环境，已自动回退到 CPU。`

## 打包策略

### 第一阶段

首发版本建议：

- 不把 CUDA/cuDNN 打进安装包
- 安装包只保证 CPU 模式可用
- 若本机已有完整 GPU 环境，则自动启用

优点：

- 安装包体积更小
- 安装成功率更高
- 用户环境问题更少

### 第二阶段

后续如果要优化 GPU 体验，可以考虑：

- 发布单独的“GPU 加速指南”
- 应用内提供“环境检测”按钮
- 在设置页提供“诊断报告导出”

### 不推荐的方式

不建议首版就尝试：

- 在安装包里完整附带 CUDA Toolkit
- 在安装过程中自动全量安装 NVIDIA 依赖
- 做多个极其复杂的 GPU 发行版

这些方案维护成本太高，也容易因为版本不匹配导致支持负担上升。

## 需要落到代码里的改动

### 后端

需要在 Python sidecar 中新增：

- GPU 环境检测模块
- 运行模式选择逻辑：`auto / cpu / cuda`
- `faster-whisper` 初始化探测
- 检测结果缓存
- 环境状态 API

建议新增接口：

- `GET /api/runtime/status`
- `POST /api/runtime/detect`

返回内容建议包含：

- `mode_preference`
- `effective_device`
- `effective_compute_type`
- `nvidia_detected`
- `cuda_available`
- `cudnn_available`
- `whisper_cuda_ready`
- `message`

### 前端

设置页需要新增：

- 运行模式选择项
- 环境状态卡片
- 一键重新检测按钮

### 桌面壳

Tauri 层需要负责：

- 启动 Python sidecar
- 传递应用数据目录
- 在首次启动后触发运行环境检测

## 发布策略建议

### 首发版本

定位：

- “桌面版可用”
- “CPU 开箱即用”
- “GPU 为自动增强”

### 用户说明

对用户应明确说明：

- 没有 CUDA/cuDNN 也能正常使用
- 只是转写速度会较慢
- 如果用户已经配置好 NVIDIA 环境，应用会自动利用 GPU 加速

## 决策结论

本项目桌面版采用以下策略：

1. `CPU 可用` 是发布底线。
2. `GPU 加速` 是可选增强能力。
3. 不把 CUDA/cuDNN 作为应用启动前提。
4. 首版不追求“GPU 开箱即用”，而追求“桌面版整体开箱即用”。
5. GPU 环境由应用自动检测，成功则启用，失败则回退 CPU。

这套策略最适合当前项目阶段，也最符合桌面应用实际交付的稳定性要求。
