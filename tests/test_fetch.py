import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from profit_lab.fetch import (
    _analyze_saved_snapshot,
    _build_npc_sell_price_evidence,
    _write_snapshot_static_evidence,
)


MARKET = "forever.normal.alliance.us"
SNAPSHOT_AT = "2026-10-22T02:20:59.000Z"
SNAPSHOT_UNIX = 1792635659


class FetchEvidenceTests(unittest.TestCase):
    def test_npc_and_locale_evidence_are_snapshotted_with_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp) / "snapshot"
            snapshot.mkdir()
            manual = {
                "npcMaterialPurchaseEvidence": {
                    "currentClientBuild": "1.60.1.70450",
                    "records": [{"itemId": 1179, "packPriceCopper": 25, "packQuantity": 1}],
                },
                "localization": {
                    "dataset": {"name": "sample", "version": "v1", "recordedAt": "2026-10-22"},
                    "entries": [{"kind": "item", "id": 1179, "zhCN": "冰镇牛奶",
                                 "source": "sample", "version": "v1", "recordedAt": "2026-10-22"}],
                },
            }
            manifest = _write_snapshot_static_evidence(snapshot, manual, {"entries": []})
            purchase_path = snapshot / "npc_material_purchase_evidence.json"
            localization_path = snapshot / "localization.json"
            self.assertEqual(manifest["npcMaterialPurchaseEvidence"]["recordCount"], 1)
            self.assertEqual(manifest["npcMaterialPurchaseEvidence"]["sha256"],
                             hashlib.sha256(purchase_path.read_bytes()).hexdigest())
            self.assertEqual(manifest["localization"]["entryCount"], 1)
            self.assertEqual(manifest["localization"]["sha256"],
                             hashlib.sha256(localization_path.read_bytes()).hexdigest())
            self.assertEqual(json.loads(purchase_path.read_text(encoding="utf-8"))["records"][0]["itemId"], 1179)
            self.assertEqual(json.loads(localization_path.read_text(encoding="utf-8"))["entries"][0]["zhCN"], "冰镇牛奶")

    def test_legacy_foreverdb_and_manual_game_evidence_are_item_keyed(self):
        audit = {
            "auditDate": "2026-10-21",
            "summary": {
                "foreverDbClientBuild": "1.60.1.70450",
                "foreverDbExtractedAt": "2026-10-19",
            },
            "candidates": [{
                "resultId": 20744,
                "foreverDbVendorSellUnitCopper": 100,
                "evidence": ["https://foreverdb.net/item/20744"],
                "localEvidence": [{"url": "https://foreverdb.net/item/20744",
                                   "localFile": "foreverdb/items/20744.html", "sha256": "abc"}],
            }],
        }
        evidence = _build_npc_sell_price_evidence(audit, ".profit-lab/audits/audit.json", {
            "currentClientBuild": None,
            "npcSellPriceEvidence": {"20744": [{
                "unitPriceCopper": 100,
                "source": "用户本轮确认的游戏内观察",
                "observedAt": None,
                "recordedAt": "2026-10-22",
                "clientBuild": None,
                "appliesToCurrentClient": True,
                "evidence": "Minor Wizard Oil 当前 NPC 收购价为 100 铜",
            }]},
        })
        self.assertEqual(len(evidence["records"]), 2)
        forever, game = evidence["records"]
        self.assertEqual((forever["itemId"], forever["unitPriceCopper"]), (20744, 100))
        self.assertEqual(forever["clientBuild"], "1.60.1.70450")
        self.assertEqual(forever["observedAt"], "2026-10-19")
        self.assertEqual(forever["url"], "https://foreverdb.net/item/20744")
        self.assertEqual(game["sourceType"], "in_game")
        self.assertIsNone(game["clientBuild"])

    def test_offline_analysis_uses_snapshotted_price_evidence_after_audit_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / ".profit-lab"
            snapshot = root / "snapshots" / "20261022T022059Z"
            raw = snapshot / "raw"
            (raw / "items").mkdir(parents=True)
            crafting = {
                "market": MARKET,
                "pricesAsOf": SNAPSHOT_AT,
                "recipes": [{
                    "recipe": {"spellId": 25124, "name": "Minor Wizard Oil", "profession": "Enchanting",
                               "skillRequired": 1, "acquisition": "trainer"},
                    "result": {"id": 20744, "name": "Minor Wizard Oil", "qtyMin": 1, "qtyMax": 1},
                    "reagents": [{"id": 3371, "name": "Empty Vial", "qty": 1}],
                }],
            }
            (raw / "crafting.json").write_text(json.dumps(crafting), encoding="utf-8")
            table = "AHL1|forever/normal/alliance/us|{}|1\n3371:386:386:1:0:0:0:0:0".format(SNAPSHOT_UNIX)
            (raw / "pricetable.txt").write_text(table, encoding="utf-8")
            (raw / "items" / "20744.json").write_text(
                json.dumps({"id": 20744, "name": "Minor Wizard Oil", "vendorSell": 500}),
                encoding="utf-8",
            )
            (snapshot / "manual_inputs.json").write_text(
                json.dumps({"schemaVersion": 1, "npcMaterialPrices": {}, "recipeAssessments": {},
                            "recipeObservations": {"25124": {
                                "status": "user_reported_feasible", "source": "用户反馈",
                                "recordedAt": "2026-10-22", "observedAt": None,
                                "clientBuild": None, "summary": "用户报告游戏内观察到机会。",
                                "limitations": "build、采购数量和销售明细未提供。",
                            }}}),
                encoding="utf-8",
            )
            price_evidence = {
                "schemaVersion": 1,
                "generatedAt": "2026-10-22T02:21:00Z",
                "currentClientBuild": None,
                "records": [
                    {"itemId": 20744, "sourceType": "foreverdb", "source": "ForeverDB item page",
                     "unitPriceCopper": 100, "observedAt": "2026-10-19",
                     "clientBuild": "1.60.1.70450", "url": "https://foreverdb.net/item/20744"},
                    {"itemId": 20744, "sourceType": "in_game", "source": "游戏内确认",
                     "unitPriceCopper": 100, "recordedAt": "2026-10-22", "clientBuild": None,
                     "appliesToCurrentClient": True, "evidence": "用户确认"},
                ],
            }
            (snapshot / "npc_sell_price_evidence.json").write_text(
                json.dumps(price_evidence), encoding="utf-8",
            )
            purchase_evidence = {
                "schemaVersion": 1, "currentClientBuild": "1.60.1.70450",
                "records": [{
                    "itemId": 3371, "vendorId": 42, "vendorName": "Test vendor",
                    "location": {"zone": "Stormwind City"}, "faction": "alliance",
                    "packPriceCopper": 10, "packQuantity": 5, "stockType": "unlimited",
                    "conditions": "Alliance vendor", "conditionsVerified": True, "reachable": True,
                    "source": "synthetic test fixture; not production evidence",
                    "sourceUrl": "https://example.invalid/vendor/42",
                    "clientBuild": "1.60.1.70450", "extractedAt": "2026-10-19",
                    "evidenceLevel": "seen_in_forever", "appliesToCurrentClient": True,
                }],
            }
            (snapshot / "npc_material_purchase_evidence.json").write_text(
                json.dumps(purchase_evidence), encoding="utf-8",
            )
            localization = {
                "schemaVersion": 1,
                "dataset": {"name": "offline fixture", "version": "v1", "recordedAt": "2026-10-22"},
                "entries": [{"kind": "spell", "id": 25124, "zhCN": "测试配方",
                             "source": "offline fixture", "version": "v1", "recordedAt": "2026-10-22"}],
            }
            (snapshot / "localization.json").write_text(json.dumps(localization, ensure_ascii=False), encoding="utf-8")
            original_crafting_hash = hashlib.sha256((raw / "crafting.json").read_bytes()).hexdigest()

            result = _analyze_saved_snapshot(snapshot)
            row = result["recipes"][0]
            self.assertEqual(row["profitMedianCopper"], 114)
            self.assertEqual(row["npcSellPriceEvidence"]["foreverDbReferenceProfitMedianCopper"], -286)
            self.assertEqual(row["npcSellPriceEvidence"]["inGameConfirmedProfitMedianCopper"], -286)
            self.assertEqual(row["npcSellPriceEvidence"]["status"], "CONFLICTED")
            self.assertEqual(row["mixedReference"]["profitCopper"], 498)
            self.assertEqual(row["recipeNameZhCN"], "测试配方")
            self.assertEqual(row["userObservation"]["status"], "user_reported_feasible")
            self.assertEqual(result["npcMaterialPurchaseEvidence"]["coveredMaterialCount"], 0)
            self.assertEqual(result["npcMaterialPurchaseEvidence"]["referenceCoveredMaterialCount"], 1)
            self.assertEqual(result["localizationCoverage"]["recipeNames"]["translated"], 1)
            self.assertEqual(hashlib.sha256((raw / "crafting.json").read_bytes()).hexdigest(), original_crafting_hash)

    def test_snapshot_update_copies_price_evidence_and_records_manifest_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / ".profit-lab"
            snapshot = root / "snapshots" / "20261022T022059Z"
            raw = snapshot / "raw"
            item_dir = raw / "items"
            item_dir.mkdir(parents=True)
            audit_dir = root / "audits" / "mvp1_1_20261021"
            audit_dir.mkdir(parents=True)
            audit_path = audit_dir / "audit.json"
            audit = {
                "auditDate": "2026-10-21",
                "summary": {
                    "market": MARKET,
                    "marketSnapshotAt": "2026-10-20T02:20:59Z",
                    "generatedAt": "2026-10-21T09:09:24Z",
                    "foreverDbClientBuild": "1.60.1.70450",
                    "foreverDbExtractedAt": "2026-10-19",
                },
                "candidates": [{
                    "spellId": 25124, "resultId": 20744,
                    "ahVendorSellUnitCopper": 500,
                    "foreverDbVendorSellUnitCopper": 100,
                    "npcSellComparison": "conflict",
                    "ahSkillRequired": 1, "foreverDbSkillRequired": 5,
                    "status": "CONFLICTED",
                    "evidence": ["https://foreverdb.net/item/20744"],
                    "localEvidence": [{"url": "https://foreverdb.net/item/20744",
                                       "localFile": "foreverdb/items/20744.html", "sha256": "abc"}],
                }],
            }
            audit_bytes = (json.dumps(audit, ensure_ascii=False) + "\n").encode("utf-8")
            audit_path.write_bytes(audit_bytes)
            crafting = {
                "market": MARKET, "pricesAsOf": SNAPSHOT_AT,
                "recipes": [{
                    "recipe": {"spellId": 25124, "name": "Minor Wizard Oil", "profession": "Enchanting",
                               "skillRequired": 1, "acquisition": "trainer"},
                    "result": {"id": 20744, "name": "Minor Wizard Oil", "qtyMin": 1, "qtyMax": 1},
                    "reagents": [{"id": 3371, "name": "Empty Vial", "qty": 1}],
                }],
            }
            (raw / "crafting.json").write_text(json.dumps(crafting), encoding="utf-8")
            table = "AHL1|forever/normal/alliance/us|{}|1\n3371:386:386:1:0:0:0:0:0".format(SNAPSHOT_UNIX)
            (raw / "pricetable.txt").write_text(table, encoding="utf-8")
            item_body = json.dumps({"id": 20744, "name": "Minor Wizard Oil", "vendorSell": 500})
            (item_dir / "20744.json").write_text(item_body, encoding="utf-8")
            (snapshot / "manual_inputs.json").write_text(json.dumps({
                "schemaVersion": 1, "currentClientBuild": None,
                "npcMaterialPrices": {}, "recipeAssessments": {},
                "npcSellPriceEvidence": {"20744": [{
                    "unitPriceCopper": 100, "sourceType": "in_game", "source": "游戏内确认",
                    "recordedAt": "2026-10-22", "clientBuild": None,
                    "appliesToCurrentClient": True, "evidence": "用户确认",
                }]},
            }), encoding="utf-8")
            (snapshot / "source_manifest.json").write_text(json.dumps({
                "entries": [{"itemId": 20744, "url": "https://api.ahledger.com/v1/items/20744?game=forever",
                             "requestedAt": "2026-10-22T02:20:00Z", "snapshotCopiedAt": "2026-10-22T02:21:00Z",
                             "snapshotFile": "raw/items/20744.json", "sha256": "item-hash"}],
            }), encoding="utf-8")

            result = _analyze_saved_snapshot(snapshot, persist_npc_sell_evidence=True)
            evidence_path = snapshot / "npc_sell_price_evidence.json"
            manifest = json.loads((snapshot / "source_manifest.json").read_text(encoding="utf-8"))
            row = result["recipes"][0]
            self.assertTrue(evidence_path.is_file())
            self.assertEqual(manifest["npcSellPriceEvidence"]["recordCount"], 2)
            self.assertEqual(manifest["npcSellPriceEvidence"]["sha256"],
                             hashlib.sha256(evidence_path.read_bytes()).hexdigest())
            self.assertEqual(result["candidateAudit"]["snapshotMatches"], False)
            self.assertEqual(row["npcSellPriceEvidence"]["ahledger"]["observedAt"], "2026-10-22T02:20:00Z")
            self.assertEqual(row["npcSellPriceEvidence"]["ahledger"]["itemId"], 20744)
            self.assertEqual(row["npcSellPriceEvidence"]["foreverDbReferenceProfitMedianCopper"], -286)
            self.assertEqual(audit_path.read_bytes(), audit_bytes)

            audit_path.unlink()
            offline = _analyze_saved_snapshot(snapshot)
            offline_row = offline["recipes"][0]
            self.assertEqual(offline_row["profitMedianCopper"], 114)
            self.assertEqual(offline_row["npcSellPriceEvidence"]["foreverDbReferenceProfitMedianCopper"], -286)
            self.assertEqual(offline_row["npcSellPriceEvidence"]["inGameConfirmedProfitMedianCopper"], -286)


if __name__ == "__main__":
    unittest.main()
