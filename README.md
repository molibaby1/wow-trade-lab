# WoW Trade Lab

Forever 普通联盟市场的只读 NPC 制造毛利筛选原型。它用于缩小人工核验范围，不保证材料能按最低报价买到，也不代表已经确认真实利润。

## 运行

需要 Python 3.9+，只使用标准库：

```sh
python3 -m profit_lab update
```

该命令固定请求 `forever.normal.alliance.us`，保存一份 AHledger 原始快照、来源清单、可复核 JSON 和离线 HTML 到 `.profit-lab/snapshots/<UTC时间>/`。最近一次 `<UTC时间>` 目录中的 `report.html` 可直接用浏览器打开。AHledger 物品响应缓存放在 `.profit-lab/item-cache/`，复用时间为 7 天。

当前工作区包含第二轮验证的只读物品响应缓存。首次更新会将匹配的 Forever 物品响应导入原型缓存，不更改 `.validation-round2/`；如果该目录不可用，程序按每秒不超过一次的节奏请求缺失物品，并对限流和服务端错误重试。

离线重算已保存快照：

```sh
python3 -m profit_lab analyze .profit-lab/snapshots/<UTC时间>
```

## 人工核验输入

可将 `manual_inputs.example.json` 复制为 `.profit-lab/manual_inputs.json`，然后仅填入已核验的 NPC 材料采购价格及配方条件。金额为每件整数铜币；每条人工价格必须写明来源和适用条件。未填写、缺少来源或缺少条件的价格不会参与计算。人工采购成本单独显示，不会覆盖 AH 中位价或最低买断价。

`recipeAssessments` 用于记录配方可用性；只有两种 AH 成本情景都为正、且专业、技能、配方来源和绑定限制均有人工核验记录时，配方才会进入 A“优先核验”。它仍然只是优先级，不是实际盈利确认。

`npcSellPriceEvidence` 按物品 ID 记录游戏内 NPC 收购价，可并列保存多个来源。`unitPriceCopper` 必须是整数铜；填入已知的 `observedAt`、`clientBuild` 和证据描述，未知字段留为 `null`，并仅在记录确实适用于当前客户端时设置 `appliesToCurrentClient: true`。可用 `validUntil` 标记明确有效期；设置 `currentClientBuild` 后，build 不匹配、证据缺少 build 或已过期的游戏内价不参与“当前确认价”利润计算。游戏客户端更新后应同步更新 `currentClientBuild` 并复核旧记录；原型不会自动探测游戏 build。缺失 build 会明示为版本未知；数值相同只表示来源间互证，不等于当前客户端权威价。

每次更新都会把 ForeverDB 旧审计中的 NPC 售价按物品 ID 提取，并与人工记录一同留在该次快照的 `npc_sell_price_evidence.json`；重算旧快照优先使用这份副本。当前 AHledger 物品原始响应、请求时间与哈希仍独立保存在快照中。售价冲突不会覆盖 AHledger 毛利，也会阻止进入 A“优先核验”；ForeverDB 参考利润和适用于当前客户端的游戏内确认利润分别显示。

## 口径与限制

- NPC 收入按产物 `vendorSell × qtyMin` 计算；变动产量按保守的最小产量并标记提示。货币计算使用整数铜币。
- 市场成本分别使用同一快照价表中的 `median` 和 `minBuyout`。缺价、缺 `vendorSell` 或时间戳不一致时，利润为 JSON `null`；市场时间错配时不会混算。
- `minBuyout` 是当前最低档报价，公开价表没有该档挂单数量，不能按市场总挂单量推算可采购深度。
- `vendorSell` API 响应没有 build 字段。报告将它作为候选筛选数据，不标记为已验证盈利。
- NPC 单价证据与市场扫描时间分离；ForeverDB 的 build / 提取时间及人工游戏内记录的适用性独立展示。AHledger 与交叉来源仍有冲突时，不推荐为优先核验。
- HTML 是单文件离线报告，支持专业筛选、三种排序和逐配方材料明细。
- 输出数据、缓存和市场快照位于 `.profit-lab/`，已加入 Git 忽略规则；不提交市场数据快照。

## MVP-1.4B：离线语言与混合采购

报告默认用简体中文显示名称，按钮可切换 enUS。配方名按 `spellId`，产物和材料按 `itemId` 查找 `localization.entries`；名称缺失时保留英文并附 ID。每条中文名必须带 `source`、`version` 和 `recordedAt`。快照会保存 `localization.json`，离线重算不请求翻译服务。

新混合采购输入写在 `.profit-lab/manual_inputs.json` 的 `npcMaterialPurchaseEvidence` 中，更新快照时另存 `npc_material_purchase_evidence.json`。每条记录需要 `itemId`、`vendorId`、`vendorName`、`location.zone`、`faction`、`packPriceCopper`、`packQuantity`、`stockType`、`conditions`、`conditionsVerified`、`reachable`、`source`、`clientBuild`、`extractedAt` 和 `evidenceLevel`。`evidenceLevel` 为 `seen_in_forever` 或当前客户端的 `current_in_game` 才可能用于计算；`classic_data` 可展示，但只作参考。包数量、库存、商人可达性、条件或版本不明时，该记录不会进入确定性成本。记录中的 `sourceUrl` 或 `localEvidence` 用于复核来源。

`stockType` 为 `unlimited` 时可进入长期单位成本；`limited` 还需提供 `stockPacks`，且库存必须够本次批量。限量记录可用于当前批次，但不会被当成长期开工的稳定供应。分析会同时展示单位分摊成本和整包现金支出；只要方案含 AH，现金支出仍标记为估算，因为价表没有对应价格档的可买数量。

离线重算及指定制造批量：

```sh
python3 -m profit_lab analyze .profit-lab/snapshots/<UTC时间> --crafts 5
```

`--crafts` 只改变新增混合采购批次；原 AH-only 结果仍按每次制造计算。NPC 售出价格冲突、配方来源/版本约束和 AH 最低档深度仍单独显示，理论正毛利不代表能采购齐材料或实际成交。

## MVP-1.6：LibItemDB Forever 本地证据

仓库工作副本可在 `AddOns/ItemDB/` 放置 LibItemDB 插件；`AddOns/` 已忽略，插件源文件不会进入默认 Git 分发。导入器只读取 `ItemDB_Camelot.toc` 明确加载的 Forever zhCN/enUS 名称表与 `_core/VendorPrices.lua` 静态字面量，不执行 Lua；生成的本地化和报价副本保存在 `.profit-lab/`。它会把当前 `.profit-lab/manual_inputs.json` 中尚未进入冻结快照的采购证据合并到新副本，并记录该输入文件哈希。当前本地数据为 ItemDB-v1.7.0、客户端数据 build `1.60.1.69913`。插件 `LICENSE` 标示 MIT；保留名称数据时同时保留来源、版本、build、SHA-256 和许可信息。

从冻结快照生成新的本地副本并离线重算：

```sh
python3 -m profit_lab.libitemdb_import \
  --plugin-root AddOns/ItemDB \
  --source-snapshot .profit-lab/snapshots/<冻结快照> \
  --destination .profit-lab/snapshots/<新快照>
python3 -m profit_lab analyze .profit-lab/snapshots/<新快照>
```

日常更新可用一条命令获取新市场快照、导入工作区已有插件，并生成独立的完整报告：

```sh
python3 -m profit_lab update --with-libitemdb
```

最终 `snapshot` 和 `report` 路径会打印在命令输出中；导入结果保存在新快照副本（目录名带 `-libitemdb`），原始 AH 快照不变。命令保留该次快照中的 `.profit-lab/manual_inputs.json`，并分别记录 AHledger 与 LibItemDB 的来源及 SHA-256。若本地 `AddOns/ItemDB/` 缺失、导入失败，或导入后任一名称组的中文覆盖低于未导入报告，命令以错误退出，不把未完成的报告作为成功结果返回。

名称按 itemId 导入；原有人工翻译优先。中文表中仍为英文的值不会被记作翻译。没有独立 spellId 名称的配方会明确标记为由结果 itemId 派生。插件英文名与 AHledger 名称不同时保留冲突记录并在报告名称提示中标出。翻译数据仅存在于被忽略的本地文件和快照中。

Forever `VendorPrices.lua` 是 `itemId → 铜币基础报价`，没有 BuyCount 或具体商人记录；供应交集还来自 Wrath/Cata 模拟器 `npc_vendor` 数据。与当前材料相交的候选报价会在报告中显示为未归一化待核验值，绝不当作单件价或整包价参与单位成本。`SellPrices.lua` 是商人向玩家收购的价格，不用于材料采购。只有其他来源已明确商人、整包价和每包数量的证据（例如现有的游戏内/ForeverDB 逐条观察）才可以进入理论参考成本；当前 build、库存、可达性及购买条件未经核验时，仍不会标为可执行。

本轮本地验收快照的实际覆盖为：材料 **562/580（96.90%）**、产物 **1962/2220（88.38%）**、配方 **1969/2227（88.41%）**。54 个 LibItemDB 基础报价候选中，插件自身含购买数量的为 **0**；3 个材料在独立证据中有明确整包数量，其中只有甜香料 #2678 有一条当前游戏内观察。NPC 理论参考单位价覆盖为 **3/580**，当前可执行覆盖仍为 **0/580**。Clam Chowder 仍为 AH-only −47/−46 铜、理论混合参考 +31/+32 铜；本轮没有相对上一冻结分析新增的可计算配方或利润候选。以上数据只存在于本地 `.profit-lab/snapshots/20261022T061500Z-mvp16-libitemdb/`。
