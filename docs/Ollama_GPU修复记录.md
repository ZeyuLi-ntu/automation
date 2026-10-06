# Ollama与GPU修复记录

修复时间：2026-09-25。项目服务地址保持`http://127.0.0.1:11434`。

## 结论

项目已切换到完整官方Ollama CLI 0.34.4。RTX 4060 Laptop 8GB通过CUDA 12运行Qwen3.5 4B，日志确认34/34模型层已加载到GPU，文字和图片推理均实际完成。原有566.07显卡驱动可以工作，此次没有更新驱动。

原0.18.2目录只有主程序及`mlx_cuda_v13`中的4个文件，缺少常规NVIDIA推理库；旧服务实际仅使用CPU。安装完整包后，自动选择了`cuda_v12`，解决了GPU识别问题。旧服务需要Windows管理员权限才能停止，已通过一次系统授权关闭；新服务以普通权限启动。

## 安装与启动

- 完整程序：`D:\automation\market_rate_project\data\ollama-repair-20260925\v0.34.4\ollama.exe`。
- 项目启动配置：`config/ollama.runtime.local.json`，固定程序版本与模型目录。
- 模型继续读取`F:\Ollama\Models`，本次没有重新下载模型。
- 旧用户目录下的0.18.2安装保留以便回退；本次安装的是项目使用的官方独立CLI，不是桌面托盘应用升级。
- 服务启动日志及当前进程信息：`data/local-model/`。

以后在项目目录运行：

```powershell
powershell -NoProfile -File scripts/start_local_model.ps1
powershell -NoProfile -File scripts/run.ps1 doctor --config config/project.local.json
```

模型加载期间，`doctor`应显示“GPU参与推理”。空闲卸载后显示没有已加载模型是正常状态。若旧桌面程序重新占用11434端口，项目启动脚本会提示版本不符；先退出旧程序再启动本脚本。

## 验证证据

| 检查 | 结果 |
| --- | --- |
| 官方安装包校验 | GitHub发布资产SHA256一致，主程序数字签名有效，签名者Ollama Inc. |
| GPU识别 | NVIDIA GeForce RTX 4060 Laptop GPU，CUDA 12，34/34层加载到GPU |
| 小型文字请求 | 4.67秒，有效JSON，实际GPU加载 |
| 单张真实银行截图 | 1.22秒，正确识别Personal 1.70%、6个月，实际GPU加载 |
| 冻结网页和完整关联PDF：文字路 | 32.08秒，返回3条结构化记录；业务字段仍有错误 |
| 相同证据：视觉路 | 32.90秒返回；证据页标识校验失败，结果已拦截 |
| 软件回归检查 | 57项通过 |

小请求与完整证据的工作量不同，不将其耗时直接比较。原始冻结证据日期仍为2026-09-24。

完整复测暴露了尚待修正的问题：文字路把原文6个月改成180天，并将Priority Private客群标为premier；视觉路把截图文件名填进证据页ID，还把Personal标为all。运行环境修复完成，但报价提取和交叉验证尚未达到发布标准。本次没有发布利率快照或改写原始Excel。

## 本地记录

- 安装清单与校验：`data/ollama-repair-20260925/package-manifest.json`。
- 独立端口的原始测试响应与GPU记录：`data/ollama-repair-20260925/gpu-check/`。
- 服务切换前后记录：`data/ollama-repair-20260925/activation-before.json`、`activation-after.json`。
- 完整冻结证据复测：`runs/scb-gpu-20260925/`，包含原始模型响应、失败记录、评估与人工复核页面。

官方依据：[Windows独立CLI说明](https://docs.ollama.com/windows)、[0.34.4发行版](https://github.com/ollama/ollama/releases/tag/v0.34.4)、[硬件支持](https://docs.ollama.com/gpu)。

安装包SHA256：`535193f38f3344e5b08f5d1c171c31ce11aa17f0124ff69ae26d8ec7fe06fa62`。
