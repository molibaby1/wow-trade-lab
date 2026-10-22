import unittest

from profit_lab.libitemdb_import import (
    build_localization,
    build_vendor_price_candidates,
    parse_static_lua_table,
)


class LibItemDBImportTests(unittest.TestCase):
    def test_static_table_parser_reads_literals_without_running_lua(self):
        source = '''
-- comment outside the table
lib:LoadNames({
[1179]="冰镇牛奶",
[3034]="Deprecated BKP \\"Impact\\" Shot",
})
'''
        self.assertEqual(parse_static_lua_table(source, "LoadNames", "string"), {
            1179: "冰镇牛奶",
            3034: 'Deprecated BKP "Impact" Shot',
        })

    def test_static_table_parser_rejects_dynamic_or_unrecognized_rows(self):
        source = '''
lib:LoadVendorPrices({
[1179]=GetPrice(),
})
'''
        with self.assertRaisesRegex(ValueError, "unsupported static Lua row"):
            parse_static_lua_table(source, "LoadVendorPrices", "number")

    def test_manual_names_win_and_product_translation_is_marked_derived(self):
        metadata = {
            "name": "LibItemDB Forever zhCN",
            "version": "ItemDB-v1.7.0",
            "clientBuild": "1.60.1.69913",
            "recordedAt": "2026-10-22",
            "license": "MIT",
            "files": {
                "zhCNNames": {"path": "Data/Forever/zhCN/Names.lua", "sha256": "zh-hash"},
                "enUSNames": {"path": "Data/Forever/enUS/Names.lua", "sha256": "en-hash"},
            },
        }
        prior = {
            "schemaVersion": 1,
            "dataset": {"name": "manual", "version": "v1", "recordedAt": "2026-10-22"},
            "entries": [
                {"kind": "item", "id": 100, "zhCN": "人工核验名", "source": "manual",
                 "version": "v1", "recordedAt": "2026-10-22"},
                {"kind": "spell", "id": 10, "zhCN": "人工配方名", "source": "manual",
                 "version": "v1", "recordedAt": "2026-10-22"},
            ],
        }
        crafting = {"recipes": [
            {"recipe": {"spellId": 10, "name": "Recipe A"},
             "result": {"id": 100, "name": "Product A"}},
            {"recipe": {"spellId": 11, "name": "Recipe B"},
             "result": {"id": 102, "name": "Product B"}},
            {"recipe": {"spellId": 12, "name": "Recipe C"},
             "result": {"id": 103, "name": "Product C"}},
            {"recipe": {"spellId": 13, "name": "Recipe D"},
             "result": {"id": 104, "name": "Product D"}},
        ]}
        localized, audit = build_localization(
            crafting, prior, {100: "插件中文名", 102: "产品乙", 103: "炼金石", 104: "Product D"},
            {100: "Product A", 102: "Product B", 103: "Alchemists' Stone", 104: "Product D"},
            metadata, "2026-10-22",
            ah_names={"102": "Different AH name", "103": "Alchemist's Stone"},
        )
        entries = {(entry["kind"], str(entry["id"])): entry for entry in localized["entries"]}
        self.assertEqual(entries[("item", "100")]["zhCN"], "人工核验名")
        self.assertEqual(entries[("spell", "10")]["zhCN"], "人工配方名")
        self.assertEqual(entries[("item", "102")]["zhCN"], "产品乙")
        derived = entries[("spell", "11")]
        self.assertEqual(derived["zhCN"], "产品乙")
        self.assertEqual(derived["translationType"], "derived_from_result_itemId")
        self.assertEqual(derived["derivedFromResultItemId"], 102)
        self.assertEqual(derived["sourceFileSha256"], "zh-hash")
        self.assertEqual([row["itemId"] for row in audit["englishNameConflictsWithAHledger"]], [102])
        self.assertIn(("item", "103"), entries)
        self.assertIn(("spell", "12"), entries)
        self.assertNotIn(("item", "104"), entries)
        self.assertNotIn(("spell", "13"), entries)

    def test_vendor_base_quotes_keep_buy_count_unknown(self):
        metadata = {
            "version": "ItemDB-v1.7.0", "clientBuild": "1.60.1.69913",
            "recordedAt": "2026-10-22", "license": "MIT",
            "files": {"vendorPrices": {"path": "Data/Forever/_core/VendorPrices.lua", "sha256": "vendor-hash"}},
            "vendorPriceProvenance": "Wrath/Cata emulator vendor-list intersection",
        }
        candidates = build_vendor_price_candidates({2678, 1179}, {2678: 10, 1179: 125}, metadata)
        self.assertEqual(len(candidates), 2)
        self.assertTrue(all(row["packPriceCopper"] is None for row in candidates))
        self.assertTrue(all(row["packQuantity"] is None for row in candidates))
        self.assertTrue(all(row["buyCountStatus"] == "not_shipped" for row in candidates))
        self.assertTrue(all(row["pagePriceCopper"] == row["basePriceCopper"] for row in candidates))
        self.assertTrue(all(row["evidenceLevel"] == "libitemdb_forever_base_price_unscaled" for row in candidates))


if __name__ == "__main__":
    unittest.main()
