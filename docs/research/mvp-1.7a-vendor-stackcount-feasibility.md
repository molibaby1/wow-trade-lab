# MVP-1.7A：Forever `VendorStackCount` 可行性与样本核验

日期：2026-10-22

## 结论

**尚未取得 Forever build `1.60.1.69913` 的 `ItemSparse.db2` 记录值，本轮不能用 `VendorStackCount` 自动补齐 54 种 NPC 材料。** WoWDBDefs 能确认目标 build 的表结构包含 `BuyPrice` 和 `VendorStackCount`，但它不是物品数据文件。Wago Tools 指向的目标 CSV 请求返回 HTTP 403；不尝试替代端点或规避访问限制。本机游戏安装为 `wow_classic_titan` build `3.80.2.70522`，版本不符，目录中也没有散装 `ItemSparse.db2`。

## 数据源与可复现信息

| 来源 | 可确认内容 | 限制 |
| --- | --- | --- |
| [WoWDBDefs `ItemSparse.dbd`](https://github.com/wowdev/WoWDBDefs/blob/master/definitions/ItemSparse.dbd#L2763-L2792) | layout `6FCC3191` 覆盖 `1.60.1.69913`；`BuyPrice<u32>`、`VendorStackCount<u32>` 均为无符号 32 位字段。 | 仅定义布局，不含任一 itemId 的值，也没有字段零值说明。 |
| [Wago Tools 的 ItemSparse CSV](https://wago.tools/db2/ItemSparse/csv?build=1.60.1.69913&locale=esES) | Forever 页面将该表链接为客户端数据来源。 | 本轮直接访问得到 HTTP 403；未重试、未改用其他路径。 |
| [WoW Forever ESP #1179](https://wowforeveresp.com/objetos/1179/) | 页面标注 beta build `1.60.1.69913`，显示物品堆叠上限和 NPC 回售价，并链接到 Wago 的 `ItemSparse`。 | 页面没有显示 `BuyPrice` 或 `VendorStackCount`；不能据页面的最大堆叠数推导商人购买包数。该页面的来源说明未给出原始数据集的再分发许可。 |
| 本机 World of Warcraft 安装 | `.build.info` 标注产品 `wow_classic_titan`、build `3.80.2.70522`。 | 与目标 build 不同；安装使用 CASC，未找到散装 `ItemSparse.db2`。不作为 Forever 字段证据。 |
| 本地 LibItemDB v1.7.0 | `ItemDB_Camelot.toc` 加载 Forever `_core/VendorPrices.lua`；该文件说明报价来自 Wago `ItemSparse.BuyPrice` 与 WotLK/Cata 模拟器 `npc_vendor` 的交集。 | 只有 `itemId → 基础报价`，不含 `VendorStackCount`。模拟器供应交集也不证明 Forever 商人实际供应。 |

哈希（SHA-256）：

- WoWDBDefs `ItemSparse.dbd`，从 `raw.githubusercontent.com/wowdev/WoWDBDefs/master/definitions/ItemSparse.dbd` 获取：`e05c7aa8e63f96df1b3be6053d8141986b8fd9118511a39a6cf0b527dbc7176f`。
- `AddOns/ItemDB/ItemDB_Camelot.toc`：`49019c1e98d7eab4105ea958bcb4ed45ec54b3513aaa622cb513cd11e33abe04`。
- `AddOns/ItemDB/Data/Forever/_core/VendorPrices.lua`：`be60c1aa994347f3a11de6f3c532c3cba2c28e8fda5fa43244424b97bbddefc1`。
- **目标 build 的 `ItemSparse.db2` 哈希：无**，因为未取得该记录文件。

## 字段语义与供应边界

WoWDBDefs 只说明字段类型和布局，未定义 `VendorStackCount=0` 的含义。TrinityCore 的公开实现将 `GetBuyCount()` 计算为 `max(VendorStackCount, 1)`，并将该值作为商人商品的 `StackCount` 发送；商人库存数量则来自独立 vendor 记录。其商人报价也单独从 `BuyPrice` 读取并应用折扣。因此，参考实现支持“购买包数由物品字段给出、商人供应/剩余库存由另一组记录决定”；其中零值回退为 1 **只是 TrinityCore 的处理规则，不能当作 Forever 客户端/服务器已核实语义**。[ItemTemplate.h](https://github.com/TrinityCore/TrinityCore/blob/master/src/server/game/Entities/Item/ItemTemplate.h) · [ItemHandler.cpp](https://github.com/TrinityCore/TrinityCore/blob/master/src/server/game/Handlers/ItemHandler.cpp#L3217-L3252)

所以，即使日后读到非零 `VendorStackCount`，它也不能证明商人可达、实际出售、库存无限或符合当前角色条件；零值在取得 Forever 对应运行证据前也不能自动解释成可购买 1 件。

## 三个样本

以下 LibItemDB 数值来自本地 `_core/VendorPrices.lua`；独立报价来自未修改的 `.profit-lab/manual_inputs.json`。目标 build 的 DB2 字段值本轮均未取得。

| itemId | LibItemDB 基础报价 | 现有独立记录 | 核验结论 |
| ---: | ---: | --- | --- |
| 2678 Mild Spices | 10 铜 | 用户游戏内观察：10 铜/5 件；另有 ForeverDB.app 10 铜/5 件参考。 | 报价金额与游戏内记录相符，购买数量有独立游戏内证据；但不能据此声称读到了 `VendorStackCount=5`。库存和当前客户端 build 仍未知。 |
| 1179 Ice Cold Milk | 125 铜 | ForeverDB.app：125 铜/5 件，页面未显示记录适用 build；ForeverDB.net：125 铜但无包数，记录标注 build `1.60.1.70450`。 | 金额相符，但缺少目标 build 字段值；两网站证据不可合并成目标 build 样本。 |
| 3371 Empty Vial | 20 铜 | ForeverDB.app：19 铜/5 件，页面未显示记录适用 build。 | 存在 1 铜报价差异；包数虽见于参考记录，但无法用目标 DB2 判断是折扣、来源差异还是记录错误，保留冲突，不选边。 |

## 数量与下一步判定

- 54 种候选中，能从**本轮取得的目标 build `ItemSparse` 记录**核实购买数量：**0/54**。
- 前三个样本未能从目标 build 的记录表读取，因此按任务条件没有逐条枚举剩余 51 项；`0/54` 表示当前没有可用的目标 build 字段数据，不表示已证明 54 项在客户端中都缺失。
- 现有样本的独立记录里有 3 个 ID 带包数量记录；其中只有 #2678 是用户游戏内观察，#1179 和 #3371 是未标明记录 build 的网页参考。它们不能替代 54 项的目标 build 字段核验。
- 当前证据**不足以进入自动采购成本计算**。可复核的下一步是使用用户合法取得且确认 build 为 `1.60.1.69913` 的客户端数据文件，或在 Wago 授权/访问恢复后取得对应表；先解析 #2678、#1179、#3371 并解释 #3371 差异，再对 54 项做 itemId 对照。商人是否供应仍需独立证据，不能由 `VendorStackCount` 推断。

本轮只新增此研究记录；未改利润逻辑、采购证据输入或冻结快照，未 commit/push。
