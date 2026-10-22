# MVP-1.4C 数据源可行性与样本复核

> **MVP-1.5 更新（2026-10-22）：** 以下原始结论记录的是 MVP-1.4C 当时的状态。本文末尾的 [MVP-1.5 真实样本接入与重算](#mvp-15-真实样本接入与重算) 为当前状态的补充结论，覆盖它之前的零覆盖数字；原始 AH 快照、NPC 售价证据与价格冲突记录均未改写。

**复核日期：** 2026-10-22（Asia/Shanghai）
**结论：** `PARTIAL — 本轮没有确认可合法复用的名称数据或可用于确定性采购的 NPC 价格。` 公开页面能证明部分字段/样本存在，但授权、版本、购买单位或采购条件不完整；未将其复制到生产输入。没有调用 ForeverDB 认证 API，没有绕过访问限制，也没有批量下载来源数据。

## 结论摘要

- 仓库之前没有本报告；本轮将旧审计 [第二轮数据验证报告](../../.validation-round2/analysis/report.md) 与本次逐来源核验合并记录。旧报告只作为历史调查材料，不替代本次授权与版本判断。
- 可见的社区翻译表 `EpochCN/Data/ItemNameMap.lua` 对三组目标配方涉及的 **11 个 itemId 有 11/11 非空条目命中**；它不提供已验证的目标 `spellId` 翻译。该仓库根目录虽标 MIT，但映射表注明混合来自 pfQuest、Questie-Epoch 和本地数据，具体翻译与上游数据的再分发许可没有逐项说明。依照“许可不清则不导入”的要求，可复用名称覆盖仍为 **0**。
- ForeverDB 文档说明商人详情和限量库存可经 API 获得，但 API 需要站方批准密钥。公开物品页面能看到 `Seen in Forever`、商人、地点和标价；本轮五种目标材料中没有一条公开记录同时满足可复核的购买数量、可用库存/供应、条件、可达性及明确的数据再分发许可，正式采购证据覆盖仍为 **0/580**。
- 因没有新增合法输入，离线重算只验证“无新证据时结果不变”，不声称达成新增覆盖。当前快照的混合情景新增可计算配方 **0**、新增盈利候选 **0**。

## 来源审查

| 来源 | 获取与版本 | 许可/使用边界 | 本轮结论 |
|---|---|---|---|
| ForeverDB API | 开发者文档列有物品、商人、配方来源、价格及限量字段；请求需获批 API key。文档当前列出每分钟 60 次、每日 10,000 次限制。API 响应带游戏 build。 | 要求展示可见 ForeverDB 链接，并禁止转售或将数据说成自有；须申请并经批准后方可用 API。 | 未持授权，未调用。批准后可作为 Forever 版本商人/库存研究的优先渠道；仍需核清数据导出与项目离线再分发范围。见 [ForeverDB Developers](https://foreverdb.net/developers)。 |
| ForeverDB 公开页面 | 本次页面显示 build `1.60.1.70450`、客户端提取日期 `2026-10-19`；这些是客户端数据抽取元数据，不是每条商人交易或库存的观测时间。页面将 `Seen in Forever` 与 `Classic data` 分开。 | 开发者页有 API 使用规则，但公开 HTML 数据没有另列通用、明确的离线数据集再分发许可；仅网页可见不足以证明可将页面数据打包进项目。 | 仅作定点人工调查；不将未解决的价格/单位写入正式采购数据。数据来源与标签说明见 [ForeverDB verify](https://foreverdb.net/verify) 和 [About](https://foreverdb.net/about)。 |
| Wowhead zhCN / Forever / Classic 页面 | 可查到不同路径下的中文条目和配方字段；`/forever/`、`/classic/`、`/cn/` 是不同版本数据，不能交叉默认等同。未在样本页面确认一致的 Forever 客户端 build。 | ZAM 条款把 Wowhead 纳入其服务；使用许可限个人、非商业和内部用途，禁止复制、分发、制作衍生数据、数据挖掘及借助非 ZAM 工具下载。 | 可供人工对照 URL 和版本路径；**不导入页面名称或价格**。见 [ZAM 条款](https://corp.fanbyte.com/legal/terms) 与 [Wowhead 站方关于导出数据的回复](https://www.wowhead.com/tbc/ru/forums/topic/export-of-wowhead-data)。 |
| `kaminaris/wow-item-names` | README 声称提供按 itemId 配对的 zhCN 等语言表，来源为提取的 DB2；仓库目前仅见 `retail/` 数据目录，未标出可匹配 Forever 的客户端 build 或提取日期。 | 仓库没有 `LICENSE` 文件。 | 不导入；既无法确认再分发权限，也无法确认旧版本/Forever 适配。见 [README](https://github.com/kaminaris/wow-item-names)。 |
| `shagu/pfQuest` | 项目覆盖 Vanilla `1.12`、TBC `2.4.3`；README 说明 WotLK 插件不随包提供 WotLK 数据。Vanilla 数据源标注 VMaNGOS，TBC 数据来自 CMaNGOS、翻译来自 MaNGOS Extras。仓库已归档。 | 仓库标 MIT，但许可文件针对 software 与关联文档；项目没有单独说明所打包数据库/翻译的上游数据权利。5.13 MB 的 `db/items.lua` 未下载，不能报目标 ID 命中数。 | 版本较旧且有中文发行包的线索，但授权范围、精确覆盖与 Forever 适配均未证实，不导入。见 [README](https://github.com/shagu/pfQuest) 与 [LICENSE](https://github.com/shagu/pfQuest/blob/master/LICENSE)。 |
| `z980944038-dev/EpochCN` | Project Epoch / WoW `3.3.5a` 社区汉化；`Data/Manifest.lua` 记录 `0.8.0-core`、生成日期 `2026-08-06`。 | 根目录 MIT 文本不自动证明混合上游翻译数据均可再分发。README/Manifest 指向 pfQuest、Questie-Epoch、EpochDB/EpochHead 和本地来源；映射行的来源说明不足以逐条确认翻译权利。 | 目标 itemId 可见样本命中 11/11，但它是未授权链清的调查线索，不是可用覆盖；没有已验证的 `6501`、`3919`、`25124` spell 翻译。见 [ItemNameMap](https://github.com/z980944038-dev/EpochCN/blob/main/Data/ItemNameMap.lua)、[Manifest](https://github.com/z980944038-dev/EpochCN/blob/main/Data/Manifest.lua)、[README](https://github.com/z980944038-dev/EpochCN) 与 [LICENSE](https://github.com/z980944038-dev/EpochCN/blob/main/LICENSE)。 |
| `Pimptasty/ItemDB` / LibItemDB | CurseForge 页面列 Vanilla/Classic 和 Forever 客户端名称语言支持；项目称 Forever build `1.60.1`，物品名按语言表离线查询。 | 项目标 MIT，但描述称名称来自 Blizzard 客户端数据/wago.tools，其他字段也有 CMaNGOS、AtlasLoot 等上游；没有证明打包名称表整体均可按 MIT 再分发。 | 有继续核验价值，但目标 ID 的具体 zhCN 命中与数据授权范围未证实；不导入。见 [项目说明](https://www.curseforge.com/wow/addons/libitemdb) 与 [许可证页](https://www.curseforge.com/wow/addons/libitemdb/license)。 |
| ItemNameDB | CurseForge 页面列 Retail/Classic 发行版本。 | 明确标为 `All Rights Reserved unless otherwise explicitly stated`。 | 不复制名称数据。见 [许可页](https://www.curseforge.com/wow/addons/itemnamedb/license)。 |

## 中文样本与覆盖

三组配方的 11 个相关 itemId 为：

- Clam Chowder：`5503`、`1179`、`2678`、`5526`。
- Rough Dynamite：`4357`、`2589`、`4358`。
- Minor Wizard Oil：`3371`、`17034`、`10940`、`20744`。

EpochCN 候选表对这 11 个 ID 均有非空中文条目，但由于来源链/数据许可未确认，报告不复制这些字符串到正式输入。公开 Wowhead 页出现的名称也不纳入，因为其条款不允许据此导出离线名称表。Recipe 名称按 `spellId` 查找；本轮没有找到许可清楚、可按 `spellId` 直接匹配的中文表，三个目标 spellId 的可用覆盖均为 0。

冻结快照实测覆盖：

| 类别 | 当前总量 | 有可复用 zhCN 记录 | 覆盖率 |
|---|---:|---:|---:|
| 配方（spellId） | 2,227 | 0 | 0% |
| 不同产物（itemId） | 2,220 | 0 | 0% |
| 材料（itemId） | 580 | 0 | 0% |

名称显示仍保留原始英文和 ID；本轮没有改写 `AHledger` 原始名称或响应。离线报告的 zhCN 切换机制保持不变，但由于可复用翻译输入仍为空，切换后名称会回退英文并显示原始 ID。

## NPC 采购样本

| itemId | 材料 | 可见证据 | 缺失/冲突 | 是否进入确定性成本 |
|---:|---|---|---|---|
| 1179 | Ice Cold Milk | ForeverDB 页标为 `Seen in WoW Forever`，列出商人、区域/部分阵营和 `1s 25c` 标价。 | 购买包数、限量/无限库存和逐条商人观测时间未显示；客户端 build/提取日不能替代库存观测时间。 | 否 |
| 2678 | Mild Spices | 本轮未获得稳定、可复核的 ForeverDB 商人明细。Wowhead 中文页不作为可复用价格源。 | 商人、价格、数量、阵营、库存、条件和版本均未核实。 | 否 |
| 3371 | Empty Vial | 当前 ForeverDB 页标 `Seen in WoW Forever`，列出 Alliance 商人 18/20 铜标价及区域。旧审计/搜索索引曾记录 `20c for 5`，与当前可见页只显示 `20c` 不一致。 | 购买数量证据冲突；不能据旧片段选用 5 件包，当前页面也未明确库存和购买条件。 | 否 |
| 4357 | Rough Blasting Powder | ForeverDB 参考页列有 `16c` 与 `Limited: 4` 商人记录。 | 该记录标为 Classic data；限量 4 表示库存限制而非包内件数；不适用于当前 Forever 采购计算。 | 否 |
| 2320 | Coarse Thread | 本轮未取得稳定、可核验的 ForeverDB 采购记录。 | Wowhead 条目不可用于导入；商人、整包数量和库存条件未核实。 | 否 |

当前公开页的定点核查参考：[1179 Ice Cold Milk](https://foreverdb.net/item/1179)、[3371 Empty Vial](https://foreverdb.net/item/3371)、[4357 Rough Blasting Powder](https://foreverdb.net/item/4357)。ForeverDB 对 `Seen in Forever` 与 Classic data 有单独标签；单有标价、没有明确购买数量或库存的记录不参与采购模型。五种目标材料合计可确定性使用 **0/5**；全部材料覆盖仍是 **0/580（0%）**。

## 冻结快照离线重算

输入来自已有 `forever.normal.alliance.us` 市场快照，市场时间 `2026-10-21T11:23:24Z`，包含 2,227 条配方。原始快照未改写；本轮把既有离线快照复制到 `.profit-lab/snapshots/20261021T231331Z-mvp14c-audit-rerun/`，只在副本重新生成 `analysis.json` 和单文件 `report.html`。副本中的采购与本地化输入仍为空，来源清单保留原 SHA-256；这次重算没有网络请求。

| 项目 | 离线结果 |
|---|---:|
| AH 中位价与最低买断价均可计算 | 863 / 2,227 |
| AH 两种情景任一毛利为正 | 8 / 2,227 |
| 新增混合采购可计算配方 | 0 |
| 新增混合采购理论盈利候选 | 0 |
| AH 缺价但可被本轮 NPC 证据补齐 | 0 |
| 混合采购可执行机会 | 0 |
| AH 市场最低买断档深度已知 | 否 |

### 目标配方逐项对比

| 配方 | AH 中位成本 / 毛利 | AH 最低买断成本 / 毛利 | 本轮混合情景 | 解释 |
|---|---:|---:|---:|---|
| Clam Chowder `spellId 6501` | 122 / **−47** 铜 | 121 / **−46** 铜 | 122 / **−47**；121 / **−46** | NPC 回款 75 铜；Clam Meat `#5503` 20/19c、Ice Cold Milk `#1179` 22c、Mild Spices `#2678` 80c。两条 NPC 采购价格均无可用证据。 |
| Rough Dynamite `spellId 3919` | 50 / **+10** 铜 | 36 / **+24** 铜 | 与 AH-only 相同 | NPC 回款 60 铜；Rough Blasting Powder `#4357` 的 `16c` 是 Classic 限量参考，不能替换 AH 成本。此处仍是无可买入深度保证的理论毛利。 |
| Minor Wizard Oil `spellId 25124` | 1,325 / **−825** 铜 | 1,276 / **−776** 铜 | 与 AH-only 相同 | NPC 回款 500 铜；`#3371` 没有满足数量与条件要求的采购证据。 |

全量重筛未新增任何此前亏损转正或缺价转可计算的配方。旧报告中的候选审计快照时间为 `2026-10-21T07:32:17Z`，与本次 `11:23:24Z` 市场快照不一致；不能用旧审计把本次候选升级为已确认机会。成品 AH 报价/活跃度仍只代表快照参考，不等于成交或保证利润。

## 证据等级、缺口与可行路径

- **真实来源页面证据：** ForeverDB 公共页和 Wowhead 页可用来发现目标字段与版本冲突；页面可访问不等于许可再分发。
- **人工核验：** 本轮没有游戏内购买窗口/商人背包截图或当前角色可达性观察；`Seen in Forever` 标签也没有代替购买包数、库存余量或条件核验。
- **候选社区数据：** EpochCN 11/11 是候选表行命中，不是可复用覆盖；pfQuest/LibItemDB 的 MIT 声明不足以单独厘清各自打包第三方游戏数据的权利。
- **合成测试：** 现有单元测试里的中文和 NPC 价格均为合成 fixture；它们只验证 ID 查找、整包现金/单位分摊、混合 AH 选择、回退与冲突隔离，不是游戏数据证据。本轮未把测试夹具写入快照。
- **市场证据：** AHledger 快照为离线真实市场响应；中位价是参考，最低买断价无逐档库存深度，均不能当作无限供货或确定成交。

下一步最小路径是：取得 ForeverDB 对目标用途的 API 批准/离线展示许可；或由用户提供当前客户端同一 build 的商人交易窗口证据（商人 ID/名称、位置、阵营、整包价格与数量、库存/限量、购买条件）；名称数据则选择明确把数据表纳入许可证的来源，或取得 EpochCN/LibItemDB 上游数据权利确认。拿到这些证据后可只更新静态输入并重算现有冻结快照，无需改利润模型或报告结构。若来源方不能确认授权，维持英文回退与 AH-only 结果。

## 验证

- 原 MVP-1.4C 文字记载 36 项通过；本轮在同一工作树复跑时为 35/36，唯一失败是 `test_fetch.py` 将“参考覆盖”旧断言误写成“可执行覆盖”。本轮修正口径，并新增两项真实样本/报告回归；当前结果见下方 MVP-1.5 验证，为 38/38 通过。
- `python3 -m profit_lab analyze .profit-lab/snapshots/20261021T231331Z-mvp14c-audit-rerun`：成功，确认快照对齐，2,227 条配方离线重算完成。
- 因没有合法且证据充分的 NPC 样本，验收项“Clam Chowder 将两种已核验 NPC 价格纳入成本”本轮**无法满足**；测试中的 Clam Chowder NPC 数值是合成夹具，不可冒充真实核验。功能测试通过不改变这个数据阻塞结论。

## MVP-1.5 真实样本接入与重算

**复核日期：** 2026-10-22
**离线快照：** `.profit-lab/snapshots/20261022T002754Z-mvp15-reference/`
**结论：** 取得并接入 11 条真实 Classic zhCN 物品翻译、3 条配方显示名别名，以及 3 条包数明确的 ForeverDB.app 单商人页面参考报价。它们进入离线分析，但都不作为当前角色已确认可执行的证据。

### 中文名称来源与覆盖

- 来源是本机 Questie `v11.34.0` Classic `zhCN` 物品表 `Localization/lookups/Classic/lookupItems/zhCN.lua`，Classic 接口版本为 `11508, 11509`；读取文件 SHA-256 为 `a832cec0e32fefc273f6e9f725f27011b8674da5fdc610d81af59f4878a347c2`。
- Questie 项目许可证页声明 GPLv3。名称记录引用对应上游文件并保存版本、许可证与本机源文件哈希；仅接入本轮 11 个目标 `itemId`。三个 `spellId` 名称通过冻结配方 `spellId → result itemId` 关系继承同名产物翻译，记录为别名，不声称来自独立法术翻译表。
- 经典名称只用于显示。Forever 专属字段、当前物品属性和当前客户端名称仍未由此证明。没找到有效条目时，报告继续显示英文与 ID。
- 全量本地表命中评估（仅统计，不导入其余记录）：2,220 个产物 ID 命中 1,412 个（63.60%）；580 个材料 ID 命中 531 个（91.55%）；产物与材料去重后 2,614 个 ID 命中 1,776 个（67.94%）。

本轮导入的目标翻译：

| 类型 / ID | enUS | zhCN | 依据 |
|---|---|---|---|
| spellId `6501` / itemId `5526` | Clam Chowder | 杂烩蚌肉 | 配方名别名到同名产物 |
| spellId `3919` / itemId `4358` | Rough Dynamite | 劣质炸药 | 配方名别名到同名产物 |
| spellId `25124` / itemId `20744` | Minor Wizard Oil | 初级巫师之油 | 配方名别名到同名产物 |
| itemId `5503` | Clam Meat | 蚌肉 | Questie zhCN 物品表 |
| itemId `1179` | Ice Cold Milk | 冰镇牛奶 | Questie zhCN 物品表 |
| itemId `2678` | Mild Spices | 甜香料 | Questie zhCN 物品表 |
| itemId `2589` | Linen Cloth | 亚麻布 | Questie zhCN 物品表 |
| itemId `4357` | Rough Blasting Powder | 劣质火药 | Questie zhCN 物品表 |
| itemId `3371` | Empty Vial | 空瓶 | Questie zhCN 物品表 |
| itemId `17034` | Maple Seed | 枫树种子 | Questie zhCN 物品表 |
| itemId `10940` | Strange Dust | 奇异之尘 | Questie zhCN 物品表 |

由此冻结快照的分类计数为配方 3/2,227（0.13%）、产物 4/2,220（0.18%）、材料 8/580（1.38%）。产物计数为 4，是因为目标的 `1179` 也出现在快照产物集合中；去重目标物品仍为 11 条。上游文件项目页声明 [GPLv3](https://www.curseforge.com/wow/addons/questie/license)，中文映射表位置为 [Questie Classic zhCN lookupItems](https://github.com/Questie/Questie/blob/master/Localization/lookups/Classic/lookupItems/zhCN.lua)。许可证声明针对 Questie 项目；它不改变暴雪对原始游戏内容的权利。

### NPC 页面报价及证据等级

本轮只人工查看了选定物品页与对应商人页，没有调用 ForeverDB API、没有批量抓取。页面核对日记录为 `2026-10-22`；来源没有提供这些逐商人报价的精确观察时间，因此不伪造时分秒。`ForeverDB.app` 当前展示具体 NPC、坐标、阵营、整包价和数量；来源页内商品列表将库存显示为 `Unlimited`，但单个 NPC 的 `Stock` 列是 `–`。因此输入保守记录为 `stockType: unknown`，不虚构当前角色可达性、购买条件、当前客户端 build 或库存确认。

| itemId | 独立页面记录 | 可用于理论单位成本 | 可执行 |
|---:|---|---:|---:|
| `2678` Mild Spices | ForeverDB.app：Tharynn Bouden，NPC `66`，Alliance，Elwynn Forest `(41.9, 67.1)`，10 铜/5 件；该商品页标 Unlimited、NPC 页库存栏为 `–`。 | 2 铜/件 | 否：库存、当前 build、条件和本角色可达性未核验 |
| `1179` Ice Cold Milk | ForeverDB.app：Innkeeper Allison，NPC `6740`，Alliance，Stormwind `(60.5, 75.2)`，125 铜/5 件；商品页标 Unlimited、NPC 页库存栏为 `–`。 | 25 铜/件 | 否：库存、当前 build、条件和本角色可达性未核验 |
| `3371` Empty Vial | ForeverDB.app：Tharynn Bouden，NPC `66`，Alliance，Elwynn Forest `(41.9, 67.1)`，19 铜/5 件；商品页标 Unlimited、NPC 页库存栏为 `–`。 | 3.8 铜/件 | 否：库存、当前 build、条件和本角色可达性未核验 |
| `1179` Ice Cold Milk | 单独记录的 ForeverDB.net 页面观察：页面列出 1s 25c 并说明 Forever beta build `1.60.1.70450`、提取日期 `2026-10-19`；没有精确到该 NPC 的整包数量。 | 否；包数/报价单位不完整 | 否 |

ForeverDB.net 与 ForeverDB.app 分成独立记录，不能将 `.net` 页面价和 `.app` 商人数量拼成一条报价。`.net` 的 125 铜只是原页面价字段，本轮没有把它解释为 5 件包。`.app` 三条完整整包记录的单条 build 均未展示，`currentClientBuild` 仍为 `null`；`Seen in Forever` 或 `forever` 页面标记不等于用户当前游戏内确认。

页面使用条款版本为 2026-10-19。条款禁止会造成干扰或违法的系统性提取，且说明网站使用不会转移其原创软件、设计、编辑内容或品牌权利。本轮限于用户指定目标的少量手工页面核对，没有保存页面副本或进行 API/批量读取；输入保留来源链接和不确定性。未发现授予整站数据再分发的通用许可，所以这批只作为本地离线分析用的最小事实记录，不扩成数据镜像，也不把它包装成可公开再分发数据库。详见 [ForeverDB 使用条款](https://www.foreverdb.app/en/legal/terms) 与 [ForeverDB API 文档](https://foreverdb.net/developers)。

输入位于 `manual_inputs.example.json` 的静态证据节；本机 `.profit-lab/manual_inputs.json` 仅合并新增键，原有 NPC 售价观察与冲突记录原样保留。冻结快照副本写入 `manual_inputs.json`、`npc_material_purchase_evidence.json`、`localization.json` 并在 `source_manifest.json` 记录哈希。原快照 `20261021T231331Z-mvp14c-audit-rerun` 未改写，市场响应哈希也保持相同。

### 全量离线重算

| 指标 | MVP-1.4C 冻结快照 | MVP-1.5 新证据快照 |
|---|---:|---:|
| 配方数 | 2,227 | 2,227 |
| AH-only 双情景可计算 | 863 | 863 |
| AH-only 正毛利配方 | 8 | 8 |
| 混合参考新增可计算配方 | 0 | 0 |
| 混合正毛利候选 | 8 | 12 |
| 新增理论混合正毛利候选 | 0 | 4 |
| NPC 理论参考报价覆盖 | 0/580 | 3/580（0.52%） |
| NPC 当前可执行报价覆盖 | 0/580 | 0/580 |
| 可执行混合采购机会 | 0 | 0 |

新增理论混合正毛利配方为 Clam Chowder（spellId `6501`）、Seasoned Wolf Kabob（`2549`）、Plain Ol' Paletusk（`1295834`）和 Cooked Crab Claw（`2545`）。这些都不是已执行机会；四者均保留配方条件/供货条件警告。没有配方因 NPC 报价补齐原本缺失的市场材料价。

**Clam Chowder 对比（NPC 成品收入 75 铜/批）：**

| 情景 | 材料成本 | 毛利 | 现金估算 | 说明 |
|---|---:|---:|---:|---|
| AH-only 中位价 | 122 铜 | −47 铜 | 理论 122 铜 | AH 参考价 |
| AH-only 最低买断价 | 121 铜 | −46 铜 | 理论 121 铜 | 最低档深度未知 |
| 理论混合采购参考（中位） | 44 铜 | +31 铜 | 52 铜，其中 NPC 10 铜 | 蚌肉 AH 20；牛奶 AH 22（NPC 参考为 25/件）；甜香料 NPC 10/5，分摊 2 铜并余 4 件 |
| 理论混合采购参考（最低） | 43 铜 | +32 铜 | 51 铜，其中 NPC 10 铜 | 蚌肉 AH 19；牛奶 AH 22；甜香料 NPC 同上 |

报告仍显示原 AH-only 毛利并将新数字明确标为“理论混合采购参考利润”。页面中的供货、可达性、当前 build 和配方条件提示都未通过，所以可执行 NPC 覆盖和可执行混合机会仍为 0。AH 的买断价不含深度；成品 AH 参考价与活跃度不代表成交。中文切换只改显示，不改 ID 或经济字段。

原 NPC 售价冲突也未改变：冲突数 1、互证数 11、未验证数 2,215、含游戏内确认价数 1；`20744` 仍为 `CONFLICTED`。AH-only 的 `20744` 利润保持 −825/−776 铜，`5526` 保持 −47/−46 铜，`4358` 保持 +10/+24 铜。

### 验证

- `python3 -m unittest discover -s tests -v`：**38 项通过**，其中新增真实样本回归和参考报价报告展示用例。
- `python3 -m profit_lab analyze .profit-lab/snapshots/20261022T002754Z-mvp15-reference`：离线成功；2,227 配方、快照对齐，输出本地 `report.html`，没有网络请求。
- 浏览器验收未完成：Chrome 安全策略拒绝 `file://` 报告地址，并禁止使用本地 HTTP 或其他浏览器通道绕过。替代静态检查通过：输出含 zhCN/enUS 两个控件、zhCN 默认态、目标中文名、整包 10 铜/5 件及剩余 4 件、来源条件；HTML 仅有内嵌脚本且无 `fetch` / `XMLHttpRequest` 或外部脚本。经济结果不因名称切换改变也由新增回归测试验证。
- `raw/crafting.json` SHA-256 `d544297d61ce9038a88e13d2ac5b3fddee28685b62e62c176b314ef93f3e05d0`；`raw/pricetable.txt` SHA-256 `cc889d22e618bb90bda649ec4d693a264a1f25d3abc7adea010cfb6b1865911c`，与源快照一致。
