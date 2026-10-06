# 完整备份

本仓库的源码位于主分支。采集数据、输出表格、本机 Ollama 程序、模型权重以及原始工作簿保存在同一仓库的 Release 分卷附件中。

## 恢复

下载该 Release 的所有 `complete-backup.zip.001`、`.002` 等分卷，以及 `backup-index.json`、`restore_backup.py`，放在同一个文件夹中。

安装 Python 3.11 或更新版本，运行：

```text
python restore_backup.py
```

程序会自动校验分卷、合并、解压到新的 `restored` 目录，并逐个校验恢复文件。请预留至少 20 GB 可用空间。

- `restored/automation`：原 `D:/automation` 中的项目、原始工作簿和文档。
- `restored/Ollama/Models`：原 `F:/Ollama/Models` 中的模型权重和模型清单。

更换电脑后需调整配置中的绝对路径、重新配置 Python 环境，并将 Ollama 模型目录指向恢复后的目录。恢复脚本不会修改现有项目，也不会自动安装系统软件或驱动。

备份仅包含制作时仍存在的文件；此前按要求删除的安装压缩包、核验明细和缓存不在备份中。
