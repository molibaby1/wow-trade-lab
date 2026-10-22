import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from profit_lab import __main__


def result_with_coverage(translated):
    return {
        "market": "forever.normal.alliance.us",
        "marketSnapshotAt": "2026-10-22T00:00:00Z",
        "recipeCount": 1,
        "craftCount": 1,
        "calculableBothScenariosCount": 1,
        "calculableMedianCount": 1,
        "calculableMinBuyoutCount": 1,
        "positiveAnyScenarioCount": 1,
        "priorityCount": 0,
        "potentialCount": 1,
        "blockedOrNonPositiveCount": 0,
        "missingPriceOrVendorSellCount": 0,
        "newlyCalculableHybridCount": 0,
        "mixedPositiveCandidateCount": 0,
        "newMixedPositiveCandidateCount": 0,
        "mixedExecutableCandidateCount": 0,
        "npcMaterialPurchaseEvidence": {},
        "localizationCoverage": {
            "recipeNames": {"translated": translated, "total": 1},
            "resultNames": {"translated": translated, "total": 1},
            "materialNames": {"translated": translated, "total": 1},
        },
        "snapshotAlignment": {"aligned": True},
    }


class UpdateCliTests(unittest.TestCase):
    def test_libitemdb_update_requires_local_plugin_before_fetch(self):
        with tempfile.TemporaryDirectory() as temp:
            missing_plugin = Path(temp) / "missing"
            with patch.object(__main__, "LIBITEMDB_ROOT", missing_plugin), \
                    patch.object(__main__, "update") as fetch:
                with self.assertRaisesRegex(RuntimeError, "requires the local Forever plugin"):
                    __main__._update_with_libitemdb(
                        ".profit-lab", "forever.normal.alliance.us", None, 1,
                    )
            fetch.assert_not_called()

    def test_libitemdb_update_creates_distinct_imported_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "snapshots" / "20261022T120000000000Z"
            plugin = Path(temp) / "ItemDB"
            plugin.mkdir()
            (plugin / "ItemDB_Camelot.toc").touch()
            imported_result = result_with_coverage(1)
            with patch.object(__main__, "LIBITEMDB_ROOT", plugin), \
                    patch.object(__main__, "update", return_value=(base, result_with_coverage(0))) as fetch, \
                    patch.object(__main__, "import_snapshot", side_effect=lambda _src, dest, _plugin: (
                        dest.mkdir(parents=True), (dest / "libitemdb_import_audit.json").touch()
                    )) as importer, \
                    patch.object(__main__, "_analyze_saved_snapshot", side_effect=lambda dest, craft_count: (
                        (dest / "report.html").touch(), imported_result
                    )[1]) as analyze:
                snapshot, result = __main__._update_with_libitemdb(
                    ".profit-lab", "forever.normal.alliance.us", None, 1,
                )

            self.assertEqual(snapshot, base.with_name(base.name + "-libitemdb"))
            fetch.assert_called_once_with(".profit-lab", "forever.normal.alliance.us", None, 1)
            importer.assert_called_once_with(base, snapshot, plugin)
            analyze.assert_called_once_with(snapshot, craft_count=1)
            self.assertIs(result, imported_result)

    def test_libitemdb_update_fails_if_localization_coverage_drops(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "snapshots" / "fresh"
            plugin = Path(temp) / "ItemDB"
            plugin.mkdir()
            (plugin / "ItemDB_Camelot.toc").touch()
            with patch.object(__main__, "LIBITEMDB_ROOT", plugin), \
                    patch.object(__main__, "update", return_value=(base, result_with_coverage(1))), \
                    patch.object(__main__, "import_snapshot", side_effect=lambda _src, dest, _plugin: (
                        dest.mkdir(parents=True), (dest / "libitemdb_import_audit.json").touch()
                    )), \
                    patch.object(__main__, "_analyze_saved_snapshot", side_effect=lambda dest, craft_count: (
                        (dest / "report.html").touch(), result_with_coverage(0)
                    )[1]):
                with self.assertRaisesRegex(RuntimeError, "coverage decreased"):
                    __main__._update_with_libitemdb(
                        ".profit-lab", "forever.normal.alliance.us", None, 1,
                    )

    def test_libitemdb_import_error_is_not_returned_as_a_successful_update(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "snapshots" / "fresh"
            plugin = Path(temp) / "ItemDB"
            plugin.mkdir()
            (plugin / "ItemDB_Camelot.toc").touch()
            with patch.object(__main__, "LIBITEMDB_ROOT", plugin), \
                    patch.object(__main__, "update", return_value=(base, result_with_coverage(0))), \
                    patch.object(__main__, "import_snapshot", side_effect=ValueError("invalid static table")):
                with self.assertRaisesRegex(RuntimeError, "invalid static table") as error:
                    __main__._update_with_libitemdb(
                        ".profit-lab", "forever.normal.alliance.us", None, 1,
                    )
            self.assertIn(str(base), str(error.exception))

    def test_cli_flag_returns_imported_report_path(self):
        snapshot = Path(".profit-lab/snapshots/fresh-libitemdb")
        result = result_with_coverage(1)
        output = io.StringIO()
        with patch.object(sys, "argv", ["profit_lab", "update", "--with-libitemdb"]), \
                patch.object(__main__, "_update_with_libitemdb", return_value=(snapshot, result)):
            with redirect_stdout(output):
                __main__.main()

        self.assertEqual(json.loads(output.getvalue())["report"], str(snapshot / "report.html"))


if __name__ == "__main__":
    unittest.main()
