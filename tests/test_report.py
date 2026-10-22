import unittest

from profit_lab.report import format_copper, render_html


class ReportTests(unittest.TestCase):
    def test_copper_formatter_preserves_sign_and_integer_unit(self):
        self.assertEqual(format_copper(24), "0g 0s 24c（24 铜）")
        self.assertEqual(format_copper(-58), "−0g 0s 58c（-58 铜）")
        self.assertEqual(format_copper(None), "不可计算")

    def test_html_is_self_contained_and_includes_cost_details_and_controls(self):
        report = render_html({
            "market": "forever.normal.alliance.us",
            "marketSnapshotAt": "2026-10-21T02:20:59.000Z",
            "generatedAt": "2026-10-21T02:30:00Z",
            "snapshotAlignment": {"aligned": True},
            "candidateAudit": {
                "status": "APPLIED", "auditDate": "2026-10-21",
                "foreverDbClientBuild": "1.60.1.70450", "foreverDbExtractedAt": "2026-10-19",
                "source": ".profit-lab/audits/mvp1_1_20261021/audit.json",
            },
            "recipeCount": 1,
            "calculableBothScenariosCount": 1,
            "positiveAnyScenarioCount": 1,
            "priorityCount": 0,
            "potentialCount": 1,
            "missingPriceOrVendorSellCount": 0,
            "npcSellPriceEvidenceCounts": {"conflicted": 1, "gamePriceConfirmed": 1, "unverified": 0},
            "recipes": [{
                "group": "B", "profession": "Engineering", "spellId": 1,
                "recipeName": "Test", "resultId": 2, "resultName": "Product",
                "resultQtyMin": 2, "resultQtyMax": 2, "skillRequired": 1,
                "acquisition": "trainer", "vendorSellUnitCopper": 30,
                "npcIncomeCopper": 60, "profitMinBuyoutCopper": 24,
                "profitMedianCopper": 4, "warnings": ["conditions_unverified"],
                "candidateAudit": {
                    "status": "CONFLICTED", "recordedStatus": "CONFLICTED",
                    "appliesToCurrentSnapshot": True, "npcSellComparison": "conflict",
                    "ahVendorSellUnitCopper": 500, "foreverDbVendorSellUnitCopper": 100,
                    "foreverDbReferenceIncomeCopper": 100,
                    "foreverDbReferenceProfitMedianCopper": -286,
                    "foreverDbReferenceProfitMinBuyoutCopper": -286,
                    "skillComparison": "conflict", "ahSkillRequired": 1,
                    "foreverDbSkillRequired": 5, "sourceComparison": "conflict",
                    "availabilityStatus": "CONFLICTED", "recipeSource": "Recipe source mismatch",
                    "access": "Alliance path unverified", "notes": ["来源字段不一致"],
                    "evidence": ["https://foreverdb.net/item/20744"],
                },
                "npcSellPriceEvidence": {
                    "status": "CONFLICTED", "ahVsForeverDb": "conflict",
                    "ahVsInGame": "conflict", "foreverDbVsInGame": "match",
                    "foreverDbUnitCopper": 100, "inGameUnitCopper": 100,
                    "foreverDbValidity": "build_unknown", "inGameValidity": "current_build_unknown",
                    "foreverDbReferenceProfitMedianCopper": -286,
                    "foreverDbReferenceProfitMinBuyoutCopper": -286,
                    "inGameConfirmedProfitMedianCopper": -286,
                    "inGameConfirmedProfitMinBuyoutCopper": -286,
                    "currentClientBuild": None,
                    "ahledger": {"unitPriceCopper": 500, "requestedAt": "2026-10-21T03:55:34Z",
                                  "url": "https://api.ahledger.com/v1/items/20744?game=forever"},
                    "foreverDb": [{"unitPriceCopper": 100, "observedAt": "2026-10-19",
                                   "clientBuild": "1.60.1.70450", "url": "https://foreverdb.net/item/20744"}],
                    "inGame": [{"unitPriceCopper": 100, "recordedAt": "2026-10-22",
                                "clientBuild": None, "evidence": "用户确认的游戏内观察"}],
                },
                "blockers": [], "reagents": [{"itemId": 3, "name": "Ore", "quantity": 1,
                    "medianUnitCopper": 56, "medianCostCopper": 56,
                    "minBuyoutUnitCopper": 36, "minBuyoutCostCopper": 36}],
            }],
        })
        self.assertIn("th{position:sticky;top:0;", report)
        self.assertNotIn("top:58px", report)
        self.assertIn("data-sort=\"min\"", report)
        self.assertIn("a.cells[2].innerText", report)
        self.assertIn("id=\"profession\"", report)
        self.assertIn("id=\"toggle-all\"", report)
        self.assertIn("data-positive=\"true\"", report)
        self.assertIn("最低买断成本", report)
        self.assertIn("36 铜", report)
        self.assertIn("ForeverDB 参考情景收入", report)
        self.assertIn("−0g 2s 86c（-286 铜）", report)
        self.assertIn("来源字段不一致", report)
        self.assertIn("1.60.1.70450", report)
        self.assertIn("NPC 售价证据（独立于市场快照）", report)
        self.assertIn("NPC 售价证据：1 条来源冲突", report)
        self.assertIn("当前游戏确认价利润", report)
        self.assertIn("用户确认的游戏内观察", report)
        self.assertIn("默认简体中文；候选先按用户观察和审计疑点排序", report)
        self.assertNotIn("<script src=", report)

    def test_html_displays_offline_locale_and_pack_cash_evidence(self):
        report = render_html({
            "market": "forever.normal.alliance.us", "marketSnapshotAt": "2026-10-21T02:20:59Z",
            "generatedAt": "2026-10-22T00:00:00Z", "snapshotAlignment": {"aligned": True},
            "recipeCount": 1, "localizationCoverage": {
                "dataset": {"name": "test locale", "version": "v1", "recordedAt": "2026-10-22",
                            "libItemDB": {"derivedRecipeNames": 1, "englishNameConflictCount": 2}},
                "recipeNames": {"translated": 1, "total": 1, "coveragePercent": 100},
                "resultNames": {"translated": 0, "total": 1, "coveragePercent": 0},
                "materialNames": {"translated": 0, "total": 1, "coveragePercent": 0},
            },
            "npcMaterialPurchaseEvidence": {"coveredMaterialCount": 1, "requiredMaterialCount": 1},
            "recipes": [{
                "group": "C", "profession": "Cooking", "spellId": 6501,
                "recipeName": "Clam Chowder", "recipeNameEnUS": "Clam Chowder",
                "recipeNameZhCN": "蛤蜊杂烩", "resultId": 5526, "resultName": "Clam Chowder",
                "recipeNameTranslationEvidence": {"source": "LibItemDB", "version": "v1",
                    "recordedAt": "2026-10-22", "translationType": "derived_from_result_itemId",
                    "derivedFromResultItemId": 5526, "nameConflictWithAHledger": True,
                    "ahledgerEnglishName": "Clam Chowder Classic"},
                "resultQtyMin": 1, "resultQtyMax": 1, "vendorSellUnitCopper": 75,
                "npcIncomeCopper": 75, "profitMedianCopper": -47, "profitMinBuyoutCopper": -46,
                "mixedOpportunityEligible": False, "mixedWarnings": ["mixed_ah_depth_unknown"],
                "mixedReference": {"craftCount": 1, "materialCostCopper": 25,
                    "profitCopper": 50, "profitPerCraftCopper": 50,
                    "cashOutlayEstimateCopper": 125, "npcCashOutlayCopper": 125,
                    "cashOutlayKnown": True, "materials": []},
                "mixedMinimum": {"craftCount": 1, "materialCostCopper": 25,
                    "profitCopper": 50, "profitPerCraftCopper": 50,
                    "cashOutlayEstimateCopper": 125, "npcCashOutlayCopper": 125,
                    "cashOutlayKnown": True, "materials": []},
                "repeatableMixedReference": {"materialCostPerCraftCopper": 25, "profitPerCraftCopper": 50},
                "repeatableMixedMinimum": {"materialCostPerCraftCopper": 25, "profitPerCraftCopper": 50},
                "outputAuctionMarket": {"medianUnitCopper": 90, "minBuyoutUnitCopper": 80,
                    "listedQuantity": 20, "estimatedSalesPerDay": 2.5},
                "reagents": [{
                    "itemId": 1179, "name": "Ice Cold Milk", "nameEnUS": "Ice Cold Milk",
                    "nameZhCN": "冰镇牛奶", "nameTranslationEvidence": {
                        "source": "test locale", "version": "v1", "recordedAt": "2026-10-22"},
                    "quantity": 1, "medianUnitCopper": 22, "medianCostCopper": 22,
                    "minBuyoutUnitCopper": 22, "minBuyoutCostCopper": 22,
                    "marketQuantity": 100, "estimatedSalesPerDayTimes10": 25,
                    "mixedReference": {"requestedQuantity": 1, "channel": "npc",
                        "unitPriceCopper": 25, "unitPriceExact": "25/1",
                        "allocatedCostCopper": 25, "allocatedCostCopperExact": "25/1",
                        "cashOutlayCopper": 125, "packagesToBuy": 1, "excessQuantity": 4,
                    "reason": "NPC 单位价最低", "npcOptions": [{"usable": True, "referenceUsable": True,
                            "vendorId": 42, "vendorName": "Vendor", "location": "Stormwind",
                            "faction": "alliance", "unitPriceCopper": 25,
                            "packPriceCopper": 125, "packQuantity": 5, "stockType": "unlimited",
                            "conditions": "Alliance vendor", "source": "synthetic test fixture",
                            "sourceUrl": "https://example.invalid/vendor/42", "clientBuild": "1.60.1.70450",
                            "extractedAt": "2026-10-19", "evidenceLevel": "seen_in_forever"}]},
                    "mixedMinimum": {"requestedQuantity": 1, "channel": "npc",
                        "unitPriceCopper": 25, "unitPriceExact": "25/1",
                        "allocatedCostCopper": 25, "allocatedCostCopperExact": "25/1",
                        "cashOutlayCopper": 125, "reason": "NPC 单位价最低", "npcOptions": []},
                }],
                "npcSellPriceEvidence": {"status": "UNVERIFIED"}, "blockers": [], "warnings": [],
            }],
        })
        self.assertIn('data-language="zhCN"', report)
        self.assertIn("English (enUS)", report)
        self.assertIn("test locale；版本 v1；记录时间 2026-10-22", report)
        self.assertIn("配方名称有 1 条由产物 itemId 派生", report)
        self.assertIn("配方名由成品 itemId 5526 派生", report)
        self.assertIn("LibItemDB / AHledger 英文名差异：Clam Chowder Classic", report)
        self.assertIn("蛤蜊杂烩", report)
        self.assertIn("Ice Cold Milk", report)
        self.assertIn("每包 125 铜 / 5 件", report)
        self.assertIn("无限库存", report)
        self.assertIn("1.60.1.70450", report)
        self.assertIn("0g 1s 25c（125 铜）", report)
        self.assertIn("AH 报价缺少该价格档位的可买数量", report)
        self.assertIn("data-sort=" + '"mixedref"', report)
        self.assertNotIn("<script src=", report)

    def test_html_marks_unverified_npc_quote_as_reference_only(self):
        quote = {
            "usable": False, "referenceUsable": True, "reasons": [
                "vendor_reachability_unverified", "purchase_conditions_unverified",
                "client_build_missing", "stock_type_unknown",
            ],
            "vendorId": 66, "vendorName": "Tharynn Bouden", "location": "Elwynn Forest (41.9, 67.1)",
            "faction": "alliance", "unitPriceCopper": 2, "packPriceCopper": 10, "packQuantity": 5,
            "stockType": "unknown", "stockPacks": None,
            "stockSourceLabel": "来源列表无限；商人页库存字段 –，未作游戏确认",
            "conditions": "当前角色可达性、库存和购买条件待游戏内确认",
            "source": "ForeverDB.app public page", "sourceSite": "foreverdb.app",
            "sourceUrl": "https://www.foreverdb.app/en/forever/items/2678/mild-spices",
            "vendorSourceUrl": "https://www.foreverdb.app/en/forever/npcs/66/tharynn-bouden",
            "clientBuild": None, "extractedAt": None, "sourceObservedAt": "2026-10-22",
            "evidenceLevel": "foreverdb_public_page",
        }
        base_quote = {
            "usable": False, "referenceUsable": False,
            "reasons": ["pack_quantity_missing_or_ambiguous", "vendor_identity_missing"],
            "vendorId": None, "vendorName": None, "location": None, "faction": None,
            "packPriceCopper": None, "packQuantity": None, "basePriceCopper": 20,
            "pagePriceCopper": 20, "pagePriceText": "BuyCount 尚未提供，不可归一化。",
            "conditions": "商人、BuyCount 和库存未知。", "source": "LibItemDB Forever base price",
            "sourceSite": "LibItemDB", "clientBuild": "1.60.1.69913",
            "extractedAt": "2026-10-22", "evidenceLevel": "libitemdb_forever_base_price_unscaled",
            "localEvidence": [{"path": "Data/Forever/_core/VendorPrices.lua", "sha256": "vendor-hash"}],
        }
        report = render_html({
            "market": "forever.normal.alliance.us", "marketSnapshotAt": "2026-10-21T11:23:24Z",
            "generatedAt": "2026-10-22T00:00:00Z", "snapshotAlignment": {"aligned": True},
            "recipeCount": 1, "npcMaterialPurchaseEvidence": {
                "referenceCoveredMaterialCount": 3, "coveredMaterialCount": 0, "requiredMaterialCount": 580,
                "libItemDBBasePriceCandidateCount": 54, "libItemDBBuyCountKnownCandidateCount": 0,
                "candidateItemsWithPackQuantityEvidence": 3,
                "candidateItemsWithCurrentInGamePackEvidence": 1,
            },
            "localizationCoverage": {
                "dataset": {"name": "Questie Classic zhCN", "version": "v11.34.0", "recordedAt": "2026-10-22"},
                "recipeNames": {"translated": 1, "total": 1, "coveragePercent": 100},
                "resultNames": {"translated": 1, "total": 1, "coveragePercent": 100},
                "materialNames": {"translated": 1, "total": 1, "coveragePercent": 100},
            },
            "recipes": [{
                "group": "C", "profession": "Cooking", "spellId": 6501,
                "recipeName": "Clam Chowder", "recipeNameEnUS": "Clam Chowder", "recipeNameZhCN": "杂烩蚌肉",
                "resultId": 5526, "resultName": "Clam Chowder", "resultNameEnUS": "Clam Chowder",
                "resultNameZhCN": "杂烩蚌肉", "resultQtyMin": 1, "resultQtyMax": 1,
                "vendorSellUnitCopper": 75, "npcIncomeCopper": 75,
                "profitMedianCopper": -47, "profitMinBuyoutCopper": -46,
                "mixedOpportunityEligible": False,
                "mixedWarnings": ["mixed_npc_purchase_reference_only", "mixed_ah_depth_unknown"],
                "mixedReference": {"craftCount": 1, "materialCostCopper": 44, "profitCopper": 31,
                    "profitPerCraftCopper": 31, "cashOutlayEstimateCopper": 52,
                    "npcCashOutlayCopper": 10, "cashOutlayKnown": False, "materials": []},
                "mixedMinimum": {"craftCount": 1, "materialCostCopper": 43, "profitCopper": 32,
                    "profitPerCraftCopper": 32, "cashOutlayEstimateCopper": 51,
                    "npcCashOutlayCopper": 10, "cashOutlayKnown": False, "materials": []},
                "repeatableMixedReference": {"materialCostPerCraftCopper": 122, "profitPerCraftCopper": -47},
                "repeatableMixedMinimum": {"materialCostPerCraftCopper": 121, "profitPerCraftCopper": -46},
                "outputAuctionMarket": {}, "candidateAudit": None,
                "npcSellPriceEvidence": {"status": "UNVERIFIED"}, "blockers": [], "warnings": [],
                "reagents": [{
                    "itemId": 2678, "name": "Mild Spices", "nameEnUS": "Mild Spices",
                    "nameZhCN": "甜香料", "quantity": 1, "medianUnitCopper": 80,
                    "medianCostCopper": 80, "minBuyoutUnitCopper": 80, "minBuyoutCostCopper": 80,
                    "mixedReference": {"requestedQuantity": 1, "channel": "npc", "unitPriceCopper": 2,
                        "allocatedCostCopper": 2, "cashOutlayCopper": 10, "packagesToBuy": 1,
                        "excessQuantity": 4, "reason": "NPC 页面参考报价", "npcOptions": [quote, base_quote]},
                    "mixedMinimum": {"requestedQuantity": 1, "channel": "npc", "unitPriceCopper": 2,
                        "allocatedCostCopper": 2, "cashOutlayCopper": 10, "packagesToBuy": 1, "excessQuantity": 4,
                        "reason": "NPC 页面参考报价",
                        "npcOptions": [quote]},
                }],
            }],
        })
        self.assertIn("理论混合采购参考利润", report)
        self.assertIn("仅理论参考；不可执行", report)
        self.assertIn("每包 10 铜 / 5 件，单位分摊 2 铜/件", report)
        self.assertIn("需买 1 包，剩余 4 件", report)
        self.assertIn("当前客户端、库存、可达性或购买条件未确认", report)
        self.assertIn("NPC 理论参考价格覆盖（材料）", report)
        self.assertIn("NPC 当前可执行价格覆盖（材料）", report)
        self.assertIn("3/580", report)
        self.assertIn("LibItemDB Forever 基础报价候选：54 / 580 种材料", report)
        self.assertIn("BuyCount 未提供，不按单件或整包计算", report)
        self.assertIn("SHA-256 vendor-hash", report)

    def test_html_separates_user_observation_from_theory_and_highlights_historical_risk(self):
        report = render_html({
            "market": "forever.normal.alliance.us",
            "marketSnapshotAt": "2026-10-21T11:23:24.000Z",
            "generatedAt": "2026-10-22T07:00:00Z",
            "snapshotAlignment": {"aligned": True},
            "candidateAudit": {"status": "UNVERIFIED", "reasons": ["audit_snapshot_mismatch"]},
            "recipeCount": 2227, "mixedExecutableCandidateCount": 0,
            "userReportedObservationCount": 1, "recipes": [{
                "group": "B", "profession": "Cooking", "spellId": 6501,
                "recipeName": "Clam Chowder", "recipeNameEnUS": "Clam Chowder",
                "recipeNameZhCN": "杂烩蚌肉", "resultId": 5526,
                "resultName": "Clam Chowder", "resultNameEnUS": "Clam Chowder",
                "resultNameZhCN": "杂烩蚌肉", "resultQtyMin": 1, "resultQtyMax": 1,
                "skillRequired": 90, "acquisition": "trainer", "vendorSellUnitCopper": 75,
                "npcIncomeCopper": 75, "materialCostMedianCopper": 122,
                "profitMedianCopper": -47, "materialCostMinBuyoutCopper": 121,
                "profitMinBuyoutCopper": -46, "mixedOpportunityEligible": True,
                "mixedReference": {"profitPerCraftCopper": 31, "materials": []},
                "mixedMinimum": {"profitPerCraftCopper": 32, "materials": []},
                "repeatableMixedReference": {}, "repeatableMixedMinimum": {},
                "userObservation": {
                    "status": "user_reported_feasible", "source": "用户反馈",
                    "recordedAt": "2026-10-22", "observedAt": None,
                    "clientBuild": None, "summary": "用户报告游戏内存在实际可行的套利机会。",
                    "limitations": "具体采购数量、完整制作过程及销售证据未提供。",
                },
                "candidateAudit": {
                    "status": "UNVERIFIED", "recordedStatus": "CONFLICTED",
                    "appliesToCurrentSnapshot": False, "skillComparison": "unverified",
                    "sourceComparison": "unverified", "notes": [
                        "AHledger skillRequired=220；ForeverDB pattern 显示 Leatherworking 250。",
                        "ForeverDB 产物页返回 404；当前配方来源仍待核验。",
                        "NPC 回售价缺少独立确认。",
                    ],
                },
                "npcSellPriceEvidence": {"status": "UNVERIFIED", "ahVsForeverDb": "missing"},
                "warnings": [], "blockers": [], "mixedWarnings": [],
                "outputAuctionMarket": {}, "assessmentEvidence": None,
                "reagents": [{
                    "itemId": 2678, "name": "Mild Spices", "nameEnUS": "Mild Spices",
                    "nameZhCN": "甜香料", "quantity": 1, "medianUnitCopper": 80,
                    "medianCostCopper": 80, "minBuyoutUnitCopper": 80,
                    "minBuyoutCostCopper": 80,
                    "mixedReference": {"channel": "npc", "unitPriceCopper": 2,
                        "allocatedCostCopper": 2, "cashOutlayCopper": 10,
                        "packagesToBuy": 1, "excessQuantity": 4, "npcOptions": []},
                    "mixedMinimum": {"channel": "npc", "unitPriceCopper": 2,
                        "allocatedCostCopper": 2, "cashOutlayCopper": 10,
                        "packagesToBuy": 1, "excessQuantity": 4, "npcOptions": []},
                }],
            }],
        })

        self.assertIn("严格自动证据口径下有 0 条候选满足全部执行条件", report)
        self.assertIn("另有 1 条用户报告的游戏内观察支持", report)
        self.assertIn("用户报告游戏内可行（未自动核验）", report)
        self.assertIn("观察时间：未提供；客户端 build：未提供", report)
        self.assertIn("历史审计曾记冲突（不适用于当前快照）：技能要求、配方来源/获取、NPC 回售价", report)
        self.assertIn("混合采购含 NPC 报价：2678", report)
        self.assertIn("具体采购数量、完整制作过程及销售证据未提供。", report)

    def test_html_marks_profit_available_only_at_ah_minimum_buyout(self):
        report = render_html({
            "market": "forever.normal.alliance.us", "snapshotAlignment": {"aligned": True},
            "recipes": [{"spellId": 17551, "recipeName": "Stonescale Oil",
                "resultId": 13423, "resultName": "Stonescale Oil", "group": "B",
                "profitMedianCopper": 0, "profitMinBuyoutCopper": 10,
                "mixedReference": {}, "mixedMinimum": {}, "reagents": [],
                "warnings": [], "blockers": [], "npcSellPriceEvidence": {}}],
        })
        self.assertIn("仅 AH 最低买断情景为正", report)


if __name__ == "__main__":
    unittest.main()
