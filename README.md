# 市场利率调研：SGD促销第一版

2026-09-27 修订：16 家有核验报价的银行，DBS/POSB 保留公开来源状态；MariBank、Trust 已退出后续采集与表格范围。Maybank 改为用户指定的存款组合促销，通过独立官网文字和用户截图核对，本机自动连接仍待修复。新增模型结果精确缓存，见 [节省token与后续扩展](docs/节省token与后续扩展.md)。中文人工入口支持逐条修改、补录、审计、撤销与重新生成，实际覆盖范围见 [SGD全行覆盖与人工修正](docs/SGD全行覆盖与人工修正.md)。以下早期记录保留作为实施过程说明。

这是可运行的第一阶段项目，不是已经接入所有银行的成品。它实现采集、独立文本/视觉提取、逐字段验证、人工复核、跨期修正、排序，以及通过桌面Excel更新模板的流程。

**模型只允许本地Ollama，云端模型入口已禁用，不需要OpenAI API密钥。** 本机RTX 4060 Laptop 8GB、约16GB内存，使用Qwen3.5 4B。文字和视觉请求均已实测GPU参与，但这不保证提取准确率。项目原理见[完全本地运行说明](docs/完全本地运行说明.md)，安装方式见[本地模型操作说明](docs/本地模型操作说明.md)。

已有读取《利率链接.xlsx》D67的[渣打真实试点脚本](docs/渣打真实试点运行说明.md)，会采集产品区域及官网关联PDF，分别调用本地文字/视觉模型，并生成可追溯测评和复核页面。

**当前范围：SGD促销。** USD/RMB挂牌继续保留历史表、其他挂牌继续保留矩阵；本版不会把未实现的币种标成本期已检查。原始工作簿只读，导出到新文件。

## 先运行不需要密钥的演示

在本目录打开终端：

```powershell
python -m market_rates demo --out runs/my-demo
```

打开以下文件：

- `runs/my-demo/review.html`：3条待复核演示记录，其中一条LLM/VLM利率不一致。
- `runs/my-demo/resolved-example/rainbow.preview.html`：示例处理后的排序，Personal 1.70%在前，Premier 1.80%作为同产品明细；全客群最高值仍是1.80%。
- `runs/my-demo/resolved-example/updates.html`：逐项检查状态。首次运行没有已发布基准时明确标示，不伪造历史比较。
- `runs/my-demo/demo-decisions.example.json`：复核决定的格式示例。

演示使用手写的合成数据，不访问银行、不调用OpenAI。示例中的“处理完成”由演示脚本生成，不代表真人核实。演示状态库与正式状态库分开。

当前工作区已经生成 `runs/demo/`，可以直接查看。Windows也可运行下面的启动脚本，它优先使用项目虚拟环境，其次使用本机可用的Python。

```powershell
powershell -NoProfile -File scripts/run.ps1 demo --out runs/my-demo
```

## 代码结构

| 模块 | 作用 |
| --- | --- |
| `market_rates/capture.py` | 浏览器采集、限定官方域名内找链接、文字/HTML/PDF/分段截图归档 |
| `market_rates/model_adapter.py` | 模型服务选择；默认本地Ollama，没有自动云端回退 |
| `market_rates/ollama_adapter.py` | 本地文字/截图独立提取、JSON结构验证、输入大小及模型能力检查 |
| `market_rates/openai_adapter.py` | 旧接口仅保留明确报错，不能发送云端请求 |
| `market_rates/schema.py` | 报价身份、金额边界、币种、客群、渠道、期限、有效期、利率单位 |
| `market_rates/verify.py` | 两路逐字段比较、证据定位、缺失/过期/新产品检查、人工复核门槛 |
| `market_rates/store.py` | SQLite保存人工决定、跨期修正及版本、正式快照、上期排序 |
| `market_rates/rules.py` | Personal优先、全客群最高值、期限归组、产品组排序、色板 |
| `market_rates/review.py` | 本地复核页面、下载人工决定、彩虹预览，不依赖网站服务 |
| `market_rates/export.py` | 先验证模板版本和产品行映射，再生成明确写入计划 |
| `scripts/export_excel.ps1` | 独立隐藏Excel实例，原生插行/插列、更新公式、生成两个新工作簿 |
| `market_rates/xlsx_read.py` | 只读现有Excel，导入链接、读取模板位置，不重存原表 |
| `tests/` | 规则、复核、证据及接口测试；另有真实Excel的合成工作簿测试 |

## 安装与本地模型配置

需要Python 3.11或以上。只有采集和PDF需要额外依赖；核心规则和离线复核使用Python标准库。模板导出需要Windows桌面版Microsoft Excel。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[live]"
.\.venv\Scripts\python -m playwright install chromium
```

本机于2026-09-25修复了不完整的Ollama安装：项目现在使用完整官方CLI 0.34.4，并已验证RTX 4060通过CUDA 12参与文字和图片推理。启动路径固定在`config/ollama.runtime.local.json`，已有模型从`F:\Ollama\Models`读取。详情见[GPU修复记录](docs/Ollama_GPU修复记录.md)。其他电脑可从[Ollama官网](https://ollama.com/download/windows)安装。

```powershell
powershell -NoProfile -File scripts/start_local_model.ps1
powershell -NoProfile -File scripts/run.ps1 doctor --config config/project.local.json
```

`doctor`读取本机模型信息，确认文字/视觉能力，不执行推理。默认不需要任何API密钥。本地推理没有云API调用费，仍消耗本机电力、时间和磁盘空间。

本地文字与视觉两路顺序执行，各自读取独立输入。初期使用同一个4B模型：这是两种输入模态的交叉核对，不代表两个独立模型，更不能证明一致的答案一定正确。后续可单独更换`models.text_model`和`models.vision_model`。不自动下载模型，也不在失败时改用云端。

`config/project.local.json`已准备好模型参数，但预期银行和产品目录仍为空，以免将候选信息误当成已核实来源。正式试点必须补全目录。

本地服务只允许本机地址；默认输入限6000字、2张截图、16K上下文和4K输出预留。超过限制会报告失败；必须完整保留产品表格和关联条款，不能为适应限制而裁掉资格条件。图片token预算为估算，实际漏读风险仍需逐页清单及人工样本验收。

云端入口已经禁用。误配置 `provider=openai` 或直接调用旧接口都会报错，即使本机留有 API 密钥也不发送请求。本地服务故障时停止处理，不回退到任何云端模型。

本地接口依据：[Ollama结构化输出](https://docs.ollama.com/capabilities/structured-outputs)、[Ollama Chat](https://docs.ollama.com/api/chat)、[Qwen3.5 4B](https://ollama.com/library/qwen3.5:4b)。采集依据：[Playwright截图](https://playwright.dev/python/docs/screenshots)。

## 第一次接入真实银行

### 1. 导入现有链接及模板候选

```powershell
python -m market_rates init --links "..\利率链接.xlsx" --template "..\20260916市场利率调研.xlsx" --out config/imported
```

此工作区已完成该步骤，导入46条去重链接、18家银行标签，以及80个SGD模板候选行。重复运行需换输出目录，避免覆盖你已修改的配置。

- `config/imported/sources.json`：来源候选。默认`enabled:false`，因为旧网址可能过期、分类不完整，不把“导入成功”当成“已核实官网”。
- `config/imported/template-candidates.json`：模板SHA256和银行/期限/条件行，默认未确认。**这是候选，不是已确认产品映射。**

选3—5家银行试点，在来源列表中启用对应来源。可以在一项来源中放多个产品页、条件页和目录页。`domains`逐个登记确切官方主机名；`www`与非`www`需要分别列入。已知页面失效时，登记的目录/入口仍会继续采集并发现候选链接；访问失败保留在复核清单中，不自动消失。

`expand_selectors`可配置必须展开的利率折叠面板。未展开、分页、访问验证、超长页面等不能默认为已完整采集；本版会报告限制，但银行专用交互仍需适配。

### 2. 建立产品目录

编辑`config/project.local.json`，启用并核对对应来源，填写`expected_banks`和`products`。也可以复制`config/project.example.json`为自己的配置，把`sources`改为`imported/sources.json`。

以下仅为配置结构示例，产品定义须对照实际官网确认：

```json
{
  "sources": "imported/sources.json",
  "expected_banks": ["RHB"],
  "products": [
    {
      "id": "rhb-sgd-promo",
      "bank": "RHB",
      "name": "需要核实的SGD促销产品名",
      "personal_status": "present",
      "expected_tenors": ["6M", "12M"],
      "expected": true
    }
  ],
  "tenor_map": {},
  "template_bank_aliases": {}
}
```

`personal_status`只允许基于证据设置：`present`表示应有Personal，`absent`表示确认没有，`unknown`表示未明确。只抓到Premier时不能擅自把`present`改成`absent`。

`expected_tenors`登记已确认的实际期限。两路之一漏掉已登记期限或两路逐页报价行数不同，都会进入覆盖复核。目录显示有Personal但本期Personal已过期时，也要人工确认后才允许采用其他客群回退。

实际4M归3M等映射必须限定到产品，例如：

```json
{"tenor_map": {"HLF/已经确认的产品ID/4M": "3M"}}
```

未知产品先进入复核，不自动生成长期身份。产品条件改变可能产生新身份，由人工确认归属；禁止将旧修正套到另一个金额档位或新期限。

### 3. 运行真实采集和模型提取

```powershell
python -m market_rates run --config config/project.local.json --as-of 2026-09-24 --out runs/20260924-first
```

将日期换成实际采集当天。实时模式拒绝用今天的网页生成过去日期的调研，避免把新报价冒充历史报价。

每家银行的证据独立成批；本地模式下LLM/VLM顺序提取，降低显存占用。文字超限、截图超限会失败并报告，不静默删除剩余证据。采集结果、模型原始输出、实际模型名和用量信息会保存；没有“双方一致就无条件通过”的逻辑。

### 4. 人工复核

打开运行目录的`review.html`，再通过`evidence/index.html`查看原文和截图：

1. 选择采用LLM、采用VLM、采用有效修正值、替换完整记录或排除。
2. 填写复核人和原因；需要跨期沿用利率修正时勾选对应项。
3. 下载`decisions.json`，保存到本次运行目录。
4. 导入并刷新：

```powershell
python -m market_rates decide --run runs/20260924-first --file runs/20260924-first/decisions.json
python -m market_rates review --run runs/20260924-first
```

初期所有新增、变化、模型分歧及异常都要检查。全局来源/覆盖异常未解决时，正式排名暂停；产品局部异常会阻止该产品整组参与排名，防止只排除Personal后误用Premier。

审批绑定“本次运行＋当前证据＋配置版本”，旧决定不能用于新证据。目录或期限规则需补充时，修改本次`config.snapshot.json`后运行`review`，相关旧决定会失效，重新核查。正式下一次采集还需同步修改项目配置。

### 5. 跨期人工修正

修正按银行、产品、币种、实际期限、客群、渠道、金额区间及条件身份绑定，不按Excel行号绑定。复核页面支持将利率修正跨期保留；数据接口另外支持产品显示名修正。期限、渠道或条件变更需要新的记录与本期复核。

已有修正继续保留，新原始值不覆盖它。新证据与修正冲突时仍需复核。本期没抓到时，复核页显示保留的修正值和“本期未核实”；在你确认适用性前，不将未知状态纳入正式有效排名。已明确过期或停止的产品不会因旧修正继续排名。

撤销修正：

```powershell
python -m market_rates override-revoke --offer-key "复核记录中的24位身份ID" --author "你的姓名" --reason "修正已失效"
```

### 6. 确认模板映射，生成可检查的写入计划

复制`config/mapping.example.json`为实际映射。按`result.json`里的`groups[].id`关联产品；使用候选中的原银行行号和`expected_bank_label`，人工确认后设置`confirmed:true`。

已有产品用`row`；新增产品用`insert_before`，插入点必须在历史合并块边界。两种定位不能同时存在。文件SHA256必须与已确认模板一致。一个原位置不能映射两个产品。

已有银行的新产品用 `bank_row` 指定同一期限下的银行起始行，新增行扩展该银行的合并区。彩虹表同一期限只显示一次银行名称，内部保留各产品明细；银行排序优先取所有有效 Personal 中最高值，同值沿用上期顺序。

```powershell
python -m market_rates plan --run runs/20260924-first --mapping config/mapping.json --template "..\20260916市场利率调研.xlsx" --rainbow "..\彩虹表_按MarketRateData更新_20260916_17.59.xlsx" --out runs/20260924-first/export
```

查看`export-plan.json`后执行：

```powershell
python -m market_rates export --plan runs/20260924-first/export/export-plan.json
```

导出行为：

- 新文件名包含“SGD试点”，不覆盖原表或已有输出。
- SGD促销在C列新增本期，旧历史右移；新产品增加行。Excel原生插入维护历史合并与跨表引用。
- 当前产品行写Personal优先值，B列保留该产品全部条件明细。不同产品使用不同记录行；不是把一个银行全部产品合成一个报价。
- 周变动公式重新指向“新本期－上期”，而不是错误比较“上期－上上期”。
- 两个输出均增加“本期逐项检查”工作表，记录新增、利率调整、利率未调整、条件变化、停供和未核实。已确认停供保留产品行，当前值为`-`，不参与排名。
- SGD最高汇总采用所有客群/渠道最高有效值。彩虹表按产品组Personal排序、保留其他明细，期限颜色不表示涨跌。
- 本期未采用的旧行显示`-`；旧表其他条件文字、外币与挂牌数据仍可能保留旧期内容，通过“本期更新范围”工作表明确标示。全局旧报告日期不改动，SGD区域单独注明本期日期。
- 首版彩虹Excel导出支持1/3/6/9/12/18/24M七组。新独立期限没有完整模板定义时停止导出，不丢掉该报价。

因此这是**可试用的SGD模板适配器**，不是“全16表自动更新已完成”。新银行没有汇总位置时阻止导出，需要先扩展模板；旧条件多行的精细排版、每家银行独有产品身份仍需核对。不要把候选行号自动当成已确认业务映射。

### 7. 保存本期基准

确认本期结果后保存正式数据快照，供下一期比较和稳定并列顺序使用：

```powershell
python -m market_rates publish --run runs/20260924-first
```

`publish`只保存本地数据库快照，不发送邮件、不上传文件。正式运行使用同一个`--db`路径才能延续修正与排序；备份`data/research.sqlite3`及各运行证据目录。

## 验证方式与尚未接通的部分

```powershell
python -m unittest discover -s tests -v
```

真实Excel的集成测试只创建临时合成工作簿，不打开用户原表：

```powershell
powershell -NoProfile -File tests/smoke_excel.ps1 -Python "你的python.exe完整路径"
```

当前已实现可执行代码和离线测试。真实银行端到端运行还需要：安装并启动Ollama、下载本地模型、Playwright浏览器及PDF依赖、试点来源配置、产品目录、已确认模板映射。模型适配测试使用模拟响应；尚未据此宣称真实本地模型或银行报价提取已通过验收。

2026-09-25本机已完成Ollama/GPU修复，并在渣打冻结样本上完成两路真实提取：三档报价核心字段各3/3匹配，日期冲突及一处条款漏词仍待人工复核，未写入正式Excel。详见[渣打提取修复记录](docs/渣打提取修复记录.md)；全银行产品目录和真实模板映射仍需后续接入。

随后已完成渣打真实模板副本的插表验证：新增日期列、保留历史合并、Personal主报价与全客群最高汇总、彩虹明细及模拟插行检查通过。结果和边界见[渣打插表验证](docs/渣打插表验证.md)。验证副本不代表人工批准，也不会绕过正式导出的复核要求。

2026-09-25继续扩展 **RHB、CIMB、HLF**：8份官方网页/PDF、22张截图，31条报价、18个产品与期限组合。新增实时官方链接发现、逐产品小批次提取、金额含界与条款关联校验；发现并修复了两路模型同时误算金额边界的问题。两路各31/31核心字段通过独立原文基准，仍保留34项人工复核。已生成含11条新增行的调研/彩虹验证副本，未修改原表或批准报价。操作与限制见[三家银行扩展验证](docs/三家银行扩展验证.md)。

2026-09-26按反馈修订：当日变动始终比较最新两期日期列，继续插列后也会同步；缺失一期时显示 `-`。`config/workbook-policy.json` 暂缓 CIMB Why Wait、Preferred 迎新与 HLF Digital 写入所有 Excel 区域，保留采集和复核证据。修正版保留 20 条报价、10 组产品与期限，不新增银行行；两份文件位于 `outputs/01a0d32d-three-bank-revision/`。这次修订继续使用 25 号冻结证据，没有伪装成 26 号重新采集。

第一版没有：绕过验证码/登录、无边界全网搜索、自动确认新产品、模型不一致时自动猜值、所有币种的模板更新。分散页面可同批提取并保留多页证据，但活动关联不明确、口径不一致时必须复核。进一步扩展应沿用当前规则接口，先增加银行样本和测试，再扩大币种范围。

2026-09-26：已接通 SCB、RHB、CIMB、HLF、OCBC、HLB、SBI、UOB、ICBC、BOC 共十家 SGD 促销。新增三家从“利率链接”读取入口、发现当前促销和关联 PDF；本次冻结原文基准两路各 37/37，合并工作簿含 72 条报价、36 个产品与期限组合。中行 2M/5M 只留采集明细，4M→3M、8M/10M→9M 保留实际期限。工行原页未明示年化单位，保留为待人工核实，未当成已确认年化口径。

每周工作簿滚动已接入一键流程：以人工确认的工作簿副本为底稿，同日修订更新当前列，新日期新增列；输入明细独立命名，历史公式不指向新一期明细。使用 `确认本期作为历史底稿.cmd` 登记检查通过的版本，采集或生成本身不会自动批准。详见[每周运行与历史滚动](docs/每周运行与历史滚动.md)。
