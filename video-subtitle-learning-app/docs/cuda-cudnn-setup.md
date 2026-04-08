# CUDA / cuDNN 版本与安装说明

本文记录本项目当前实际使用过、并在本机验证过的一套 GPU 运行环境，主要用于 `faster-whisper`、`ctranslate2` 等推理链路的 CUDA 加速。

## 1. 本项目当前使用的版本

当前这台开发机器上的实际安装结果如下：

- CUDA Toolkit: `12.0`
- CUDA 编译器版本: `V12.0.76`
- `CUDA_PATH`: `G:\NVIDIA GPU Computing Toolkit\CUDA\v12.0`
- cuDNN: `9.20`
- cuDNN DLL: `G:\NVIDIA\CUDNN\v9.20\bin\12.9\x64\cudnn64_9.dll`

说明：

- `nvcc --version` 显示的是本机已安装的 CUDA Toolkit 版本，这里是 `12.0.76`。
- cuDNN 安装目录里出现了 `12.9` 子目录，不表示它只能配合 CUDA `12.9` 使用。
- 根据 NVIDIA 官方 `Support Matrix`，`cuDNN 9.20.0 for CUDA 12.x` 支持 CUDA `12.0` 到 `12.9`。因此，本机这套 `cuDNN 9.20 + CUDA 12.0` 的组合属于兼容范围内。

上面最后一条是基于本机安装路径和 NVIDIA 官方兼容矩阵做出的判断。

## 2. 它们在本项目里是做什么的

- CUDA Toolkit 提供 GPU 运行时、编译器和底层库。
- cuDNN 提供深度学习推理常用的高性能加速库。
- 在本项目里，它们主要用于让本地语音识别链路尽量走 GPU，而不是只靠 CPU。

没有 CUDA / cuDNN 时，项目仍然可以退回 CPU 跑，但会明显更慢，不适合较长视频或较高频率的批量处理。

## 3. 推荐安装方式

本项目目前以 Windows 本地开发和便携式桌面版为主，推荐采用下面这套方式：

1. 安装 NVIDIA 显卡驱动，并确认 `nvidia-smi` 可用。
2. 安装 CUDA Toolkit `12.0`。
3. 安装 cuDNN `9.x for CUDA 12.x`。
4. 把 CUDA 和 cuDNN 的 `bin` 路径加入系统 `Path`。
5. 重新打开终端，检查 `nvcc` 和 `cudnn64_9.dll` 是否能被找到。

## 4. Windows 安装 CUDA Toolkit 12.0

### 4.1 下载入口

建议从 NVIDIA 官方 CUDA Archive 下载：

- CUDA Toolkit Archive:
  [https://developer.nvidia.com/cuda-toolkit-archive](https://developer.nvidia.com/cuda-toolkit-archive)
- CUDA 12.0 Windows 安装文档:
  [https://docs.nvidia.com/cuda/archive/12.0.0/pdf/CUDA_Installation_Guide_Windows.pdf](https://docs.nvidia.com/cuda/archive/12.0.0/pdf/CUDA_Installation_Guide_Windows.pdf)

### 4.2 安装建议

在下载页选择：

- Operating System: `Windows`
- Architecture: `x86_64`
- Version: 按你的系统选择 `10` 或 `11`
- Installer Type: 推荐 `exe (local)` 或图形安装器

如果你和当前这台机器一样，想避开 C 盘，可以在图形安装时选择自定义安装目录，例如：

- `G:\NVIDIA GPU Computing Toolkit\CUDA\v12.0`

### 4.3 安装后检查

PowerShell 中执行：

```powershell
echo $env:CUDA_PATH
nvcc --version
```

正常情况下应当能看到：

- `CUDA_PATH` 指向你的 CUDA 安装目录
- `nvcc --version` 输出 `release 12.0, V12.0.76` 或同系列版本信息

## 5. Windows 安装 cuDNN 9 for CUDA 12.x

### 5.1 下载入口

建议参考 NVIDIA 官方 cuDNN Windows 安装文档：

- cuDNN Windows 安装文档:
  [https://docs.nvidia.com/deeplearning/cudnn/backend/v9.5.1/installation/windows.html](https://docs.nvidia.com/deeplearning/cudnn/backend/v9.5.1/installation/windows.html)
- cuDNN Support Matrix:
  [https://docs.nvidia.com/deeplearning/cudnn/latest/reference/support-matrix.html](https://docs.nvidia.com/deeplearning/cudnn/latest/reference/support-matrix.html)

### 5.2 安装方式

NVIDIA 官方文档给了两种 Windows 方式：

- 图形安装器
- 压缩包解压安装

本项目更推荐以下两种思路之一：

#### 方案 A：图形安装器

优点：

- 安装过程简单
- 可以在安装界面里选择对应的 CUDA 版本
- 更适合普通用户

#### 方案 B：压缩包手动放置

优点：

- 更容易做便携式部署
- 更清楚文件实际放在哪

如果是手动方式，核心就是把以下内容放到某个固定目录：

- `bin\cudnn*.dll`
- `include\cudnn*.h`
- `lib\x64\cudnn*.lib`

本机当前使用的是类似下面的目录结构：

```text
G:\NVIDIA\CUDNN\v9.20\
  bin\12.9\x64\cudnn64_9.dll
  include\12.9\cudnn.h
  lib\12.9\x64\cudnn64_9.lib
```

### 5.3 环境变量

需要确保 cuDNN 的 DLL 目录在系统 `Path` 中，例如：

```text
G:\NVIDIA\CUDNN\v9.20\bin\12.9\x64
```

PowerShell 验证命令：

```powershell
where.exe cudnn64_9.dll
```

若输出的是你刚安装的 DLL 路径，通常就说明动态库查找已经通了。

## 6. 如何判断是否安装成功

建议至少检查下面四项：

### 6.1 显卡驱动

```powershell
nvidia-smi
```

如果这个命令都没有，说明显卡驱动层面还没准备好。

### 6.2 CUDA Toolkit

```powershell
echo $env:CUDA_PATH
nvcc --version
```

### 6.3 cuDNN 动态库

```powershell
where.exe cudnn64_9.dll
```

### 6.4 Path 中是否已有相关目录

```powershell
$env:Path -split ';' | Select-String 'CUDA|CUDNN'
```

本机当前检查结果对应的是：

- CUDA `bin`: `G:\NVIDIA GPU Computing Toolkit\CUDA\v12.0\bin`
- CUDA `libnvvp`: `G:\NVIDIA GPU Computing Toolkit\CUDA\v12.0\libnvvp`
- cuDNN `bin`: `G:\NVIDIA\CUDNN\v9.20\bin\12.9\x64`

## 7. 与本项目的关系

对本项目而言，这套 CUDA / cuDNN 不是“桌面程序必须自带才能运行”的绝对前提，而是“本地 GPU 加速能力”的运行条件。

可以这样理解：

- 只有 Web UI、设置页、字幕浏览这些前后端功能，不依赖 CUDA 才能启动。
- 本地视频转写、批量处理、长视频处理，如果想跑得更快，更适合配置 CUDA / cuDNN。
- 如果未来我们走“同目录便携版优先”的桌面分发策略，CUDA / cuDNN 更适合作为外部运行时依赖来检测，而不是直接打进主程序安装包。

## 8. 版本选择建议

如果后续你要给其他用户写安装教程，建议文档中固定写成下面这种表述：

- 推荐 CUDA: `12.x`
- 当前开发验证版本: `12.0`
- 推荐 cuDNN: `9.x for CUDA 12.x`
- 当前开发验证版本: `9.20`

这样做的好处是：

- 对外说明时不把范围卡得过死
- 仍然保留“当前这台开发机是按什么版本跑通的”这一关键信息
- 兼容未来同属 CUDA 12.x 家族的升级空间

## 9. 官方参考网页

以下是本次整理时使用的官方参考页：

1. CUDA Toolkit Archive  
   [https://developer.nvidia.com/cuda-toolkit-archive](https://developer.nvidia.com/cuda-toolkit-archive)
2. CUDA 12.0 Windows Installation Guide  
   [https://docs.nvidia.com/cuda/archive/12.0.0/pdf/CUDA_Installation_Guide_Windows.pdf](https://docs.nvidia.com/cuda/archive/12.0.0/pdf/CUDA_Installation_Guide_Windows.pdf)
3. cuDNN Windows Installation Guide  
   [https://docs.nvidia.com/deeplearning/cudnn/backend/v9.5.1/installation/windows.html](https://docs.nvidia.com/deeplearning/cudnn/backend/v9.5.1/installation/windows.html)
4. cuDNN Support Matrix  
   [https://docs.nvidia.com/deeplearning/cudnn/latest/reference/support-matrix.html](https://docs.nvidia.com/deeplearning/cudnn/latest/reference/support-matrix.html)

