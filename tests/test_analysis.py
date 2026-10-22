import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from profit_lab.analysis import analyze_snapshot


MARKET = "forever.normal.alliance.us"
SNAPSHOT = "2026-10-21T02:20:59.000Z"
SNAPSHOT_UNIX = int(datetime(2026, 10, 21, 2, 20, 59, tzinfo=timezone.utc).timestamp())


def recipe(spell_id, name, result_id, vendor_sell, qty, reagent_id, reagent_price,
           min_buyout=None, side=None):
    item = {"id": result_id, "name": f"{name} Product", "quality": "COMMON"}
    if vendor_sell is not None:
        item["vendorSell"] = vendor_sell
    recipe_data = {
        "spellId": spell_id,
        "name": name,
        "profession": "Engineering",
        "skillRequired": 1,
        "acquisition": "trainer",
    }
    if side is not None:
        recipe_data["side"] = side
    return {
        "recipe": recipe_data,
        "result": {"id": result_id, "name": item["name"], "qtyMin": qty, "qtyMax": qty},
        "reagents": [{"id": reagent_id, "name": f"Material {reagent_id}", "qty": 1,
                      "price": reagent_price}],
        "item": item,
        "price": {"id": reagent_id, "median": reagent_price, "minBuyout": min_buyout},
    }


def fixture():
    records = [
        recipe(3919, "Rough Dynamite", 3001, 30, 2, 101, 36, 36),
        recipe(6412, "Kaldorei Spider Kabob", 3002, 10, 1, 102, 68, 68),
        recipe(8001, "Median Loss, Min Buyout Profit", 3003, 100, 1, 103, 110, 80),
        recipe(8002, "Missing Prices", 3004, None, 1, 999, None, None),
        recipe(8003, "Horde Only", 3005, 100, 1, 104, 10, 10, side="horde"),
        recipe(8004, "Unverified Conditions", 3006, 100, 1, 105, 10, 10),
        recipe(8005, "Verified Conditions", 3007, 100, 1, 106, 10, 10),
        recipe(8006, "Minor Wizard Oil", 20744, 500, 1, 107, 386, 386),
    ]
    crafting = {
        "market": MARKET,
        "pricesAsOf": SNAPSHOT,
        "generatedAt": "2026-10-21T02:30:00.000Z",
        "recipes": [{key: value for key, value in record.items() if key in ("recipe", "result", "reagents")}
                    for record in records],
    }
    item_bodies = {record["item"]["id"]: record["item"] for record in records}
    prices = {record["price"]["id"]: record["price"] for record in records}
    table = [f"AHL1|forever/normal/alliance/us|{SNAPSHOT_UNIX}|{len(prices)}"]
    table.extend(
        f"{item_id}:{price['median'] if price['median'] is not None else ''}:"
        f"{price['minBuyout'] if price['minBuyout'] is not None else ''}:1:0:0:0:0:0"
        for item_id, price in prices.items()
    )
    return crafting, "\n".join(table), item_bodies


class AnalyzeSnapshotTests(unittest.TestCase):
    def analyze(self, **kwargs):
        crafting, table, items = fixture()
        options = {"generated_at": "2026-10-21T02:31:00.000Z"}
        options.update(kwargs)
        return analyze_snapshot(crafting, table, items, **options)

    def row(self, result, spell_id):
        return next(item for item in result["recipes"] if item["spellId"] == spell_id)

    def audit(self, spell_id, result_id, *, status="CORROBORATED", ah_sell=30,
              forever_sell=30, ah_skill=1, forever_skill=1, access="game check"):
        return {
            "auditDate": "2026-10-21",
            "summary": {
                "market": MARKET,
                "marketSnapshotAt": SNAPSHOT,
                "generatedAt": "2026-10-21T09:09:24Z",
                "foreverDbClientBuild": "1.60.1.70450",
                "foreverDbExtractedAt": "2026-10-19",
            },
            "candidates": [{
                "spellId": spell_id,
                "resultId": result_id,
                "recipeName": "Audited recipe",
                "status": status,
                "ahVendorSellUnitCopper": ah_sell,
                "foreverDbVendorSellUnitCopper": forever_sell,
                "npcSellComparison": "missing" if forever_sell is None else (
                    "match" if forever_sell == ah_sell else "conflict"
                ),
                "ahSkillRequired": ah_skill,
                "foreverDbSkillRequired": forever_skill,
                "ahAcquisition": "trainer",
                "recipeSource": "ForeverDB source evidence",
                "access": access,
                "evidence": ["https://foreverdb.net/item/1"],
                "notes": [],
            }],
        }

    def sell_price_evidence(self, item_id, *, forever_price=100, game_price=100,
                            current_build=None, game_build=None, valid_until=None):
        records = [{
            "itemId": item_id,
            "sourceType": "foreverdb",
            "source": "ForeverDB item page",
            "unitPriceCopper": forever_price,
            "observedAt": "2026-10-19",
            "clientBuild": "1.60.1.70450",
            "url": "https://foreverdb.net/item/{}".format(item_id),
            "validUntil": valid_until,
        }]
        if game_price is not None:
            records.append({
                "itemId": item_id,
                "sourceType": "in_game",
                "source": "用户确认的游戏内观察",
                "unitPriceCopper": game_price,
                "observedAt": None,
                "recordedAt": "2026-10-22",
                "clientBuild": game_build,
                "appliesToCurrentClient": True,
                "evidence": "本轮用户确认",
            })
        return {
            "schemaVersion": 1,
            "generatedAt": "2026-10-22T00:00:00Z",
            "currentClientBuild": current_build,
            "records": records,
        }

    def clam_fixture(self):
        crafting, table, items = fixture()
        crafting["recipes"].append({
            "recipe": {"spellId": 6501, "name": "Clam Chowder", "profession": "Cooking",
                       "skillRequired": 90, "acquisition": "trainer"},
            "result": {"id": 5526, "name": "Clam Chowder", "qtyMin": 1, "qtyMax": 1},
            "reagents": [
                {"id": 5503, "name": "Clam Meat", "qty": 1},
                {"id": 1179, "name": "Ice Cold Milk", "qty": 1},
                {"id": 2678, "name": "Mild Spices", "qty": 1},
            ],
        })
        items["5526"] = {"id": 5526, "name": "Clam Chowder", "vendorSell": 75}
        table += "\n5503:20:19:100:20:20:20:20:100:100"
        table += "\n1179:22:22:100:22:22:22:22:100:100"
        table += "\n2678:80:80:100:80:80:80:80:100:100"
        return crafting, table, items

    def valid_purchase_fixture(self, item_id, *, price, pack_quantity=1, stock_type="unlimited",
                               stock_packs=None, reachable=True, conditions_verified=True,
                               evidence_level="seen_in_forever"):
        return {
            "itemId": item_id,
            "vendorId": 100 + item_id,
            "vendorName": "Verified vendor",
            "location": {"zone": "Stormwind City", "x": 50.0, "y": 50.0},
            "faction": "alliance",
            "packPriceCopper": price,
            "packQuantity": pack_quantity,
            "stockType": stock_type,
            "stockPacks": stock_packs,
            "conditions": "Alliance; no reputation discount; reachable by the market character",
            "conditionsVerified": conditions_verified,
            "reachable": reachable,
            "source": "synthetic test fixture; not production evidence",
            "sourceUrl": "https://example.invalid/vendor/{}".format(100 + item_id),
            "clientBuild": "1.60.1.70450",
            "extractedAt": "2026-10-19T00:00:00Z",
            "evidenceLevel": evidence_level,
            "appliesToCurrentClient": True,
        }

    def analyze_clam(self, *, purchases=None, localization=None, craft_count=1,
                     table=None, candidate_audit=None):
        crafting, source_table, items = self.clam_fixture()
        return analyze_snapshot(
            crafting, source_table if table is None else table, items,
            generated_at="2026-10-22T00:00:00Z",
            npc_material_purchase_evidence={
                "schemaVersion": 1, "currentClientBuild": "1.60.1.70450",
                "records": purchases or [],
            },
            localization=localization,
            craft_count=craft_count,
            candidate_audit=candidate_audit,
        )

    def test_clam_chowder_mixes_valid_npc_purchase_fixtures_by_item_id(self):
        result = self.analyze_clam(purchases=[
            self.valid_purchase_fixture(1179, price=20),
            self.valid_purchase_fixture(2678, price=10, pack_quantity=5),
        ])
        row = self.row(result, 6501)
        self.assertEqual(row["profitMedianCopper"], -47)
        self.assertEqual(row["profitMinBuyoutCopper"], -46)
        self.assertEqual(row["mixedReference"]["materialCostCopper"], 42)
        self.assertEqual(row["mixedReference"]["profitCopper"], 33)
        self.assertEqual(row["mixedMinimum"]["materialCostCopper"], 41)
        self.assertEqual(row["mixedMinimum"]["profitCopper"], 34)
        by_id = {item["itemId"]: item for item in row["reagents"]}
        self.assertEqual(by_id[1179]["mixedReference"]["channel"], "npc")
        self.assertEqual(by_id[2678]["mixedReference"]["unitPriceCopper"], 2)

    def test_current_game_vendor_quote_has_priority_over_cheaper_forever_reference(self):
        game_quote = self.valid_purchase_fixture(
            2678, price=10, pack_quantity=5, evidence_level="current_in_game",
        )
        game_quote["vendorId"] = 1286
        game_quote["vendorName"] = "Current game vendor"
        forever_quote = self.valid_purchase_fixture(
            2678, price=5, pack_quantity=5, evidence_level="seen_in_forever",
        )
        forever_quote["vendorId"] = 66
        forever_quote["vendorName"] = "Forever reference vendor"
        result = self.analyze_clam(purchases=[forever_quote, game_quote])
        row = self.row(result, 6501)
        spices = next(item for item in row["reagents"] if item["itemId"] == 2678)
        self.assertEqual(spices["mixedReference"]["channel"], "npc")
        self.assertEqual(spices["mixedReference"]["unitPriceCopper"], 2)
        self.assertEqual(spices["mixedReference"]["selectedNpcEvidence"]["evidenceLevel"], "current_in_game")

    def test_unscaled_libitemdb_base_price_does_not_enter_unit_cost(self):
        raw_quote = {
            "itemId": 2678, "vendorId": None, "vendorName": None, "location": None,
            "faction": None, "packPriceCopper": None, "packQuantity": None,
            "basePriceCopper": 10, "pagePriceCopper": 10,
            "pagePriceText": "LibItemDB vendor base price; BuyCount is not shipped.",
            "stockType": "unknown", "conditions": "Vendor and BuyCount are unknown.",
            "conditionsVerified": False, "reachable": False,
            "source": "LibItemDB Forever VendorPrices.lua", "sourceSite": "LibItemDB",
            "sourceObservedAt": "2026-10-22", "recordedAt": "2026-10-22",
            "extractedAt": "2026-10-22", "clientBuild": "1.60.1.69913",
            "evidenceLevel": "libitemdb_forever_base_price_unscaled",
            "priceApplicability": "BuyCount unknown; not a unit price.",
            "localEvidence": [{"path": "AddOns/ItemDB/Data/Forever/_core/VendorPrices.lua", "sha256": "abc"}],
        }
        result = self.analyze_clam(purchases=[raw_quote])
        row = self.row(result, 6501)
        spices = next(item for item in row["reagents"] if item["itemId"] == 2678)
        self.assertEqual(row["mixedReference"]["profitCopper"], -47)
        self.assertEqual(spices["mixedReference"]["channel"], "ah_median")
        self.assertFalse(spices["mixedReference"]["npcOptions"][0]["referenceUsable"])
        self.assertEqual(spices["mixedReference"]["npcOptions"][0]["basePriceCopper"], 10)

    def test_checked_in_foreverdb_and_questie_samples_recalculate_clam_chowder(self):
        example_path = Path(__file__).resolve().parents[1] / "manual_inputs.example.json"
        evidence = json.loads(example_path.read_text(encoding="utf-8"))
        purchases = evidence["npcMaterialPurchaseEvidence"]["records"]
        localization = evidence["localization"]
        result = self.analyze_clam(purchases=purchases, localization=localization)
        row = self.row(result, 6501)

        self.assertEqual(row["recipeNameZhCN"], "杂烩蚌肉")
        self.assertEqual(row["resultNameZhCN"], "杂烩蚌肉")
        self.assertEqual(row["profitMedianCopper"], -47)
        self.assertEqual(row["profitMinBuyoutCopper"], -46)
        self.assertEqual(row["mixedReference"]["materialCostCopper"], 44)
        self.assertEqual(row["mixedReference"]["profitCopper"], 31)
        self.assertEqual(row["mixedMinimum"]["materialCostCopper"], 43)
        self.assertEqual(row["mixedMinimum"]["profitCopper"], 32)
        self.assertEqual(row["group"], "B")
        self.assertTrue(row["mixedOpportunityEligible"])
        self.assertNotIn("no_positive_margin", row["blockers"])
        self.assertFalse(row["mixedExecutableOpportunity"])

        reagents = {entry["itemId"]: entry for entry in row["reagents"]}
        self.assertEqual(reagents[5503]["mixedReference"]["channel"], "ah_median")
        self.assertEqual(reagents[1179]["mixedReference"]["channel"], "ah_median")
        self.assertEqual(reagents[2678]["mixedReference"]["channel"], "npc")
        milk_quotes = reagents[1179]["mixedReference"]["npcOptions"]
        milk_app = next(option for option in milk_quotes if option.get("sourceSite") == "foreverdb.app")
        milk_net = next(option for option in milk_quotes if option.get("sourceSite") == "foreverdb.net")
        self.assertTrue(milk_app["referenceUsable"])
        self.assertEqual(milk_app["unitPriceCopper"], 25)
        self.assertFalse(milk_net["referenceUsable"])
        self.assertIsNone(milk_net["unitPriceCopper"])
        spices = reagents[2678]["mixedReference"]
        self.assertEqual(spices["unitPriceCopper"], 2)
        self.assertEqual(spices["cashOutlayCopper"], 10)
        self.assertEqual(spices["excessQuantity"], 4)
        selected = spices["selectedNpcEvidence"]
        self.assertTrue(selected["referenceUsable"])
        self.assertFalse(selected["usable"])
        self.assertEqual(selected["stockType"], "unknown")
        self.assertFalse(row["mixedExecutableOpportunity"])

        english = self.analyze_clam(purchases=purchases)
        english_row = self.row(english, 6501)
        self.assertEqual(english_row["recipeNameEnUS"], "Clam Chowder")
        self.assertEqual(english_row["mixedReference"]["profitCopper"], row["mixedReference"]["profitCopper"])
        self.assertEqual(english_row["mixedMinimum"]["profitCopper"], row["mixedMinimum"]["profitCopper"])

        self.assertEqual(len([entry for entry in localization["entries"] if entry["kind"] == "item"]), 11)
        self.assertEqual(len([entry for entry in localization["entries"] if entry["kind"] == "spell"]), 3)

    def test_npc_pack_unit_allocation_and_cash_spend_are_separate(self):
        crafting, table, _ = self.clam_fixture()
        table = "\n".join(line for line in table.splitlines()
                           if not line.startswith(("1179:", "2678:")))
        result = self.analyze_clam(
            purchases=[self.valid_purchase_fixture(1179, price=125, pack_quantity=5)],
            table=table,
        )
        row = self.row(result, 6501)
        milk = next(item for item in row["reagents"] if item["itemId"] == 1179)
        self.assertEqual(milk["mixedReference"]["unitPriceCopper"], 25)
        self.assertEqual(milk["mixedReference"]["allocatedCostCopper"], 25)
        self.assertEqual(milk["mixedReference"]["cashOutlayCopper"], 125)
        self.assertEqual(milk["mixedReference"]["packagesToBuy"], 1)
        self.assertEqual(milk["mixedReference"]["excessQuantity"], 4)

    def test_one_npc_material_and_other_ah_materials_can_be_mixed(self):
        result = self.analyze_clam(purchases=[self.valid_purchase_fixture(1179, price=20)])
        row = self.row(result, 6501)
        channels = {item["itemId"]: item["mixedReference"]["channel"] for item in row["reagents"]}
        self.assertEqual(channels[1179], "npc")
        self.assertEqual(channels[5503], "ah_median")
        self.assertEqual(channels[2678], "ah_median")
        self.assertFalse(row["mixedReference"]["cashOutlayKnown"])

    def test_ah_missing_material_can_use_valid_npc_price(self):
        _, table, _ = self.clam_fixture()
        table = "\n".join(line for line in table.splitlines() if not line.startswith("1179:"))
        result = self.analyze_clam(
            purchases=[self.valid_purchase_fixture(1179, price=20)], table=table,
        )
        row = self.row(result, 6501)
        self.assertIsNone(row["profitMedianCopper"])
        self.assertIsNotNone(row["mixedReference"]["profitCopper"])
        self.assertEqual(row["mixedReference"]["profitCopper"], -45)

    def test_ambiguous_unreachable_and_insufficient_npc_records_do_not_price_materials(self):
        records = [
            self.valid_purchase_fixture(1179, price=125, pack_quantity=None),
            self.valid_purchase_fixture(2678, price=10, pack_quantity=5, reachable=False),
            self.valid_purchase_fixture(5503, price=100, pack_quantity=1,
                                   stock_type="limited", stock_packs=0),
        ]
        _, table, _ = self.clam_fixture()
        table = "\n".join(line for line in table.splitlines()
                           if not line.startswith(("1179:", "2678:", "5503:")))
        result = self.analyze_clam(purchases=records, table=table)
        row = self.row(result, 6501)
        self.assertIsNone(row["mixedReference"]["materialCostCopper"])
        self.assertIsNone(row["mixedReference"]["profitCopper"])

    def test_known_limited_stock_can_support_one_batch_but_not_repeatable_cost(self):
        result = self.analyze_clam(purchases=[self.valid_purchase_fixture(
            1179, price=20, stock_type="limited", stock_packs=1,
        )])
        row = self.row(result, 6501)
        milk = next(item for item in row["reagents"] if item["itemId"] == 1179)
        self.assertEqual(milk["mixedReference"]["channel"], "npc")
        self.assertEqual(milk["repeatableMixedReference"]["channel"], "ah_median")

    def test_specified_batch_reports_package_count_and_total_cash(self):
        _, table, _ = self.clam_fixture()
        table = "\n".join(line for line in table.splitlines() if not line.startswith("1179:"))
        result = self.analyze_clam(
            purchases=[self.valid_purchase_fixture(1179, price=125, pack_quantity=5)],
            table=table, craft_count=3,
        )
        row = self.row(result, 6501)
        milk = next(item for item in row["reagents"] if item["itemId"] == 1179)
        self.assertEqual(row["mixedReference"]["craftCount"], 3)
        self.assertEqual(milk["mixedReference"]["requestedQuantity"], 3)
        self.assertEqual(milk["mixedReference"]["allocatedCostCopper"], 75)
        self.assertEqual(milk["mixedReference"]["cashOutlayCopper"], 125)
        self.assertEqual(milk["mixedReference"]["excessQuantity"], 2)

    def test_localized_names_fall_back_by_id_and_do_not_change_economics(self):
        localized = {
            "schemaVersion": 1,
            "dataset": {"name": "test fixture", "version": "1", "recordedAt": "2026-10-22"},
            "entries": [
                {"kind": "spell", "id": 6501, "zhCN": "蛤蜊杂烩",
                 "source": "test fixture", "version": "1", "recordedAt": "2026-10-22"},
                {"kind": "item", "id": 5526, "englishName": "Clam Chowder", "zhCN": "Clam Chowder",
                 "source": "test fixture", "version": "1", "recordedAt": "2026-10-22"},
            ],
        }
        result = self.analyze_clam(localization=localized)
        row = self.row(result, 6501)
        self.assertEqual(row["recipeNameEnUS"], "Clam Chowder")
        self.assertEqual(row["recipeNameZhCN"], "蛤蜊杂烩")
        self.assertEqual(row["resultNameZhCN"], "Clam Chowder")
        self.assertEqual(row["resultNameFallbackId"], 5526)
        self.assertEqual(result["localizationCoverage"]["resultNames"]["translated"], 0)
        self.assertEqual(row["profitMedianCopper"], -47)
        self.assertEqual(row["mixedReference"]["profitCopper"], row["profitMedianCopper"])

    def test_price_conflict_stays_separate_from_ah_and_hybrid_scenarios(self):
        audit = self.audit(6501, 5526, status="CONFLICTED", ah_sell=75, forever_sell=25)
        result = self.analyze_clam(purchases=[self.valid_purchase_fixture(1179, price=20)],
                                   candidate_audit=audit)
        row = self.row(result, 6501)
        self.assertEqual(row["profitMedianCopper"], -47)
        self.assertEqual(row["mixedReference"]["profitCopper"], -45)
        self.assertEqual(row["npcSellPriceEvidence"]["status"], "CONFLICTED")
        self.assertFalse(row["mixedOpportunityEligible"])

    def test_rough_dynamite_manual_36_copper_cost_yields_24_copper_profit(self):
        result = self.analyze()
        row = self.row(result, 3919)
        self.assertEqual(row["profitMinBuyoutCopper"], 24)
        self.assertEqual(row["profitMedianCopper"], 24)
        self.assertEqual(row["npcIncomeCopper"], 60)

    def test_kaldorei_kabob_at_68_cost_is_negative_and_not_recommended(self):
        result = self.analyze()
        row = self.row(result, 6412)
        self.assertEqual(row["profitMinBuyoutCopper"], -58)
        self.assertEqual(row["profitMedianCopper"], -58)
        self.assertEqual(row["group"], "C")

    def test_minimum_buyout_only_profit_is_potential_not_priority(self):
        result = self.analyze()
        row = self.row(result, 8001)
        self.assertEqual(row["profitMedianCopper"], -10)
        self.assertEqual(row["profitMinBuyoutCopper"], 20)
        self.assertEqual(row["group"], "B")

    def test_missing_material_price_or_vendor_sell_remains_null(self):
        result = self.analyze()
        row = self.row(result, 8002)
        self.assertIsNone(row["materialCostMedianCopper"])
        self.assertIsNone(row["materialCostMinBuyoutCopper"])
        self.assertIsNone(row["profitMedianCopper"])
        self.assertIsNone(row["profitMinBuyoutCopper"])
        self.assertEqual(row["group"], "C")

    def test_explicit_horde_recipe_is_blocked_for_alliance_market(self):
        result = self.analyze()
        row = self.row(result, 8003)
        self.assertEqual(row["group"], "C")
        self.assertIn("faction_mismatch", row["blockers"])

    def test_unknown_assessed_faction_is_unverified_not_assumed_unavailable(self):
        result = self.analyze(assessments={8004: {
            "status": "verified_available",
            "faction": "unknown",
            "professionVerified": True,
            "skillVerified": True,
            "sourceVerified": True,
            "bindingVerified": True,
            "evidence": "partial in-game check",
        }})
        row = self.row(result, 8004)
        self.assertEqual(row["group"], "B")
        self.assertNotIn("faction_mismatch", row["blockers"])
        self.assertIn("conditions_unverified", row["warnings"])

    def test_unverified_conditions_never_become_priority(self):
        result = self.analyze()
        row = self.row(result, 8004)
        self.assertGreater(row["profitMedianCopper"], 0)
        self.assertGreater(row["profitMinBuyoutCopper"], 0)
        self.assertEqual(row["group"], "B")
        self.assertIn("conditions_unverified", row["warnings"])

    def test_verified_conditions_and_both_positive_scenarios_are_priority(self):
        result = self.analyze(assessments={8005: {
            "status": "verified_available",
            "faction": "alliance",
            "professionVerified": True,
            "skillVerified": True,
            "sourceVerified": True,
            "bindingVerified": True,
            "evidence": "test fixture",
        }})
        self.assertEqual(self.row(result, 8005)["group"], "B")

    def test_corroborated_audit_preserves_original_profit_and_allows_priority(self):
        result = self.analyze(
            assessments={3919: {
                "status": "verified_available", "faction": "alliance",
                "professionVerified": True, "skillVerified": True,
                "sourceVerified": True, "bindingVerified": True, "evidence": "in-game"}},
            candidate_audit=self.audit(3919, 3001),
        )
        row = self.row(result, 3919)
        self.assertEqual(row["profitMinBuyoutCopper"], 24)
        self.assertEqual(row["profitMedianCopper"], 24)
        self.assertEqual(row["candidateAudit"]["status"], "CORROBORATED")
        self.assertEqual(row["candidateAudit"]["npcSellComparison"], "match")
        self.assertEqual(row["group"], "A")

    def test_minor_wizard_oil_shows_ah_and_foreverdb_reference_scenarios(self):
        audit = self.audit(8006, 20744, status="CONFLICTED", ah_sell=500,
                           forever_sell=100, ah_skill=1, forever_skill=5)
        result = self.analyze(candidate_audit=audit)
        row = self.row(result, 8006)
        self.assertEqual(row["profitMedianCopper"], 114)
        self.assertEqual(row["profitMinBuyoutCopper"], 114)
        self.assertEqual(row["candidateAudit"]["foreverDbReferenceProfitMedianCopper"], -286)
        self.assertEqual(row["candidateAudit"]["foreverDbReferenceProfitMinBuyoutCopper"], -286)
        self.assertEqual(row["candidateAudit"]["npcSellComparison"], "conflict")
        self.assertEqual(row["candidateAudit"]["skillComparison"], "conflict")
        self.assertEqual(row["group"], "B")

    def test_audit_requires_market_snapshot_and_both_ids_to_match(self):
        audit = self.audit(3919, 9999)
        result = self.analyze(candidate_audit=audit)
        row = self.row(result, 3919)
        self.assertEqual(row["candidateAudit"]["status"], "UNVERIFIED")
        self.assertIsNone(row["candidateAudit"]["foreverDbReferenceProfitMedianCopper"])

        audit = self.audit(3919, 3001)
        audit["summary"]["marketSnapshotAt"] = "2026-10-21T02:21:00Z"
        result = self.analyze(candidate_audit=audit)
        row = self.row(result, 3919)
        self.assertEqual(row["candidateAudit"]["status"], "UNVERIFIED")
        self.assertEqual(row["profitMedianCopper"], 24)
        self.assertIsNone(row["candidateAudit"]["foreverDbReferenceProfitMedianCopper"])

    def test_item_price_evidence_survives_a_different_market_audit_snapshot(self):
        audit = self.audit(8006, 20744, status="CONFLICTED", ah_sell=500,
                           forever_sell=100, ah_skill=1, forever_skill=5)
        audit["summary"]["marketSnapshotAt"] = "2026-10-20T02:20:59Z"
        result = self.analyze(candidate_audit=audit,
                              npc_sell_price_evidence=self.sell_price_evidence(20744))
        row = self.row(result, 8006)
        evidence = row["npcSellPriceEvidence"]
        self.assertEqual(row["profitMedianCopper"], 114)
        self.assertEqual(row["candidateAudit"]["status"], "UNVERIFIED")
        self.assertEqual(evidence["status"], "CONFLICTED")
        self.assertEqual(evidence["ahVsForeverDb"], "conflict")
        self.assertEqual(evidence["ahVsInGame"], "conflict")
        self.assertEqual(evidence["foreverDbReferenceProfitMedianCopper"], -286)
        self.assertEqual(evidence["inGameConfirmedProfitMedianCopper"], -286)
        self.assertEqual(evidence["foreverDbValidity"], "build_unknown")

    def test_missing_cross_source_evidence_is_unverified_not_assumed_matching(self):
        result = self.analyze(npc_sell_price_evidence={"schemaVersion": 1, "records": []})
        evidence = self.row(result, 3919)["npcSellPriceEvidence"]
        self.assertEqual(evidence["status"], "UNVERIFIED")
        self.assertEqual(evidence["ahVsForeverDb"], "unverified")
        self.assertIsNone(evidence["foreverDbReferenceProfitMedianCopper"])
        self.assertIsNone(evidence["inGameConfirmedProfitMedianCopper"])

    def test_expired_or_wrong_build_game_price_is_not_used_as_current_confirmation(self):
        evidence = self.sell_price_evidence(
            20744, current_build="1.60.1.70450", game_build="1.60.1.70449",
            valid_until="2026-10-20",
        )
        result = self.analyze(npc_sell_price_evidence=evidence)
        row = self.row(result, 8006)
        prices = row["npcSellPriceEvidence"]
        self.assertEqual(prices["foreverDbValidity"], "expired")
        self.assertEqual(prices["inGameValidity"], "build_mismatch")
        self.assertIsNone(prices["foreverDbReferenceProfitMedianCopper"])
        self.assertIsNone(prices["inGameConfirmedProfitMedianCopper"])
        self.assertIn("npc_sell_price_evidence_stale", row["warnings"])

        evidence = self.sell_price_evidence(20744, current_build="1.60.1.70450", game_build=None)
        result = self.analyze(npc_sell_price_evidence=evidence)
        prices = self.row(result, 8006)["npcSellPriceEvidence"]
        self.assertEqual(prices["inGameValidity"], "build_missing")
        self.assertIsNone(prices["inGameConfirmedProfitMedianCopper"])
        self.assertIn("npc_sell_price_evidence_stale", self.row(result, 8006)["warnings"])

    def test_audit_skill_or_price_conflict_never_changes_ah_profit(self):
        result = self.analyze(candidate_audit=self.audit(
            8006, 20744, status="CONFLICTED", ah_sell=500, forever_sell=100,
            ah_skill=1, forever_skill=5,
        ))
        row = self.row(result, 8006)
        self.assertEqual(row["profitMedianCopper"], 114)
        self.assertEqual(row["candidateAudit"]["skillComparison"], "conflict")
        self.assertIn("audit_skill_conflict", row["warnings"])

    def test_missing_audit_crosscheck_prevents_priority(self):
        assessment = {8005: {
            "status": "verified_available", "faction": "alliance",
            "professionVerified": True, "skillVerified": True,
            "sourceVerified": True, "bindingVerified": True, "evidence": "in-game"}}
        result = self.analyze(assessments=assessment)
        row = self.row(result, 8005)
        self.assertEqual(row["group"], "B")
        self.assertEqual(row["candidateAudit"]["status"], "UNVERIFIED")

    def test_scarlet_high_theoretical_profit_is_not_priority_without_sell_evidence(self):
        crafting, table, items = fixture()
        source = crafting["recipes"][0]
        source["recipe"].update({"spellId": 1224618, "name": "Scarlet Infiltrator's Bracers",
                                 "skillRequired": 220})
        source["result"].update({"id": 238275, "name": "Scarlet Infiltrator's Bracers",
                                 "qtyMin": 1, "qtyMax": 1})
        items.pop(3001)
        items["238275"] = {"id": 238275, "vendorSell": 20671}
        audit = self.audit(1224618, 238275, status="CONFLICTED", ah_sell=20671,
                           forever_sell=None, ah_skill=220, forever_skill=250)
        assessment = {1224618: {
            "status": "verified_available", "faction": "alliance",
            "professionVerified": True, "skillVerified": True,
            "sourceVerified": True, "bindingVerified": True, "evidence": "test"}}
        result = analyze_snapshot(crafting, table, items, assessments=assessment,
                                  candidate_audit=audit)
        row = next(item for item in result["recipes"] if item["spellId"] == 1224618)
        self.assertGreater(row["profitMedianCopper"], 0)
        self.assertEqual(row["candidateAudit"]["npcSellComparison"], "missing")
        self.assertEqual(row["candidateAudit"]["foreverDbReferenceProfitMedianCopper"], None)
        self.assertEqual(row["group"], "B")

    def test_user_observation_is_separate_from_profit_and_executable_evidence(self):
        observation = {
            "status": "user_reported_feasible",
            "source": "用户反馈",
            "recordedAt": "2026-10-22",
            "observedAt": None,
            "clientBuild": None,
            "summary": "用户报告游戏内存在实际可行的套利机会。",
            "limitations": "具体采购数量、完整制作过程及销售证据未提供。",
        }
        baseline = self.analyze()
        observed = self.analyze(observations={"3919": observation})
        before = self.row(baseline, 3919)
        after = self.row(observed, 3919)

        self.assertEqual(after["userObservation"], observation)
        for field in ("materialCostMedianCopper", "profitMedianCopper",
                      "materialCostMinBuyoutCopper", "profitMinBuyoutCopper",
                      "mixedReference", "mixedMinimum"):
            self.assertEqual(after[field], before[field])
        self.assertFalse(after["mixedExecutableOpportunity"])
        self.assertEqual(observed["mixedExecutableCandidateCount"], baseline["mixedExecutableCandidateCount"])
        self.assertEqual(observed["userReportedObservationCount"], 1)

    def test_user_observed_candidate_precedes_higher_profit_with_stale_conflict_audit(self):
        crafting, table, items = fixture()
        scarlet = crafting["recipes"][0]
        scarlet["recipe"].update({"spellId": 1224618, "name": "Scarlet Infiltrator's Bracers"})
        scarlet["result"].update({"id": 3001, "name": "Scarlet Infiltrator's Bracers"})
        items[3001]["vendorSell"] = 20671
        observed = crafting["recipes"][1]
        observed["recipe"].update({"spellId": 3919, "name": "Seasoned Wolf Kabob"})
        observed["result"].update({"id": 3002, "name": "Seasoned Wolf Kabob Product"})
        items[3002]["vendorSell"] = 100
        old_audit = self.audit(1224618, 3001, status="CONFLICTED", ah_sell=20671,
                               forever_sell=None, ah_skill=220, forever_skill=250)
        old_audit["summary"]["marketSnapshotAt"] = "2026-10-20T02:20:59.000Z"
        old_audit["candidates"][0]["notes"] = [
            "AHledger skillRequired=220；ForeverDB pattern 显示 Leatherworking 250。",
            "ForeverDB 产物页返回 404；当前配方来源仍待核验。",
            "NPC 回售价缺少独立确认。",
        ]
        result = analyze_snapshot(
            crafting, table, items,
            generated_at="2026-10-22T00:00:00Z",
            observations={"3919": {
                "status": "user_reported_feasible", "source": "用户反馈",
                "summary": "用户明确确认实际可行。",
            }},
            candidate_audit=old_audit,
        )

        positive_rows = [row for row in result["recipes"]
                         if row["mixedOpportunityEligible"] and
                         ((row["mixedReference"]["profitCopper"] or 0) > 0 or
                          (row["mixedMinimum"]["profitCopper"] or 0) > 0)]
        self.assertEqual(positive_rows[0]["spellId"], 3919)
        scarlet_row = next(row for row in result["recipes"] if row["spellId"] == 1224618)
        self.assertGreater(scarlet_row["profitMedianCopper"], 10000)
        self.assertFalse(scarlet_row["candidateAudit"]["appliesToCurrentSnapshot"])
        self.assertEqual(scarlet_row["candidateAudit"]["recordedStatus"], "CONFLICTED")

    def test_manual_npc_material_price_is_separate_and_requires_evidence(self):
        result = self.analyze(manual_npc_prices={101: {
            "unitPriceCopper": 20,
            "source": "in-game vendor check",
            "conditions": "Alliance vendor; unlimited stock",
        }})
        row = self.row(result, 3919)
        self.assertEqual(row["manualNpcMaterialCostCopper"], 20)
        self.assertEqual(row["manualNpcMaterialProfitCopper"], 40)
        self.assertEqual(row["materialCostMedianCopper"], 36)
        no_evidence = self.analyze(manual_npc_prices={101: {"unitPriceCopper": 0}})
        self.assertIsNone(self.row(no_evidence, 3919)["manualNpcMaterialCostCopper"])

    def test_variable_yield_uses_minimum_quantity_and_warns(self):
        crafting, table, items = fixture()
        crafting["recipes"][0]["result"]["qtyMax"] = 4
        result = analyze_snapshot(crafting, table, items, generated_at="2026-10-21T02:31:00Z")
        row = self.row(result, 3919)
        self.assertEqual(row["npcIncomeCopper"], 60)
        self.assertIn("variable_yield_uses_minimum", row["warnings"])

    def test_mismatched_snapshots_do_not_mix_prices(self):
        crafting, table, items = fixture()
        crafting["pricesAsOf"] = "2026-10-21T02:21:00.000Z"
        result = analyze_snapshot(crafting, table, items, generated_at="2026-10-21T02:31:00Z")
        self.assertFalse(result["snapshotAlignment"]["aligned"])
        row = self.row(result, 3919)
        self.assertIsNone(row["materialCostMedianCopper"])
        self.assertIsNone(row["materialCostMinBuyoutCopper"])
        self.assertEqual(row["group"], "C")


if __name__ == "__main__":
    unittest.main()
