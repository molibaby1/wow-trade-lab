"""CLI for the read-only Forever Alliance NPC profit prototype."""

import argparse
import json
from pathlib import Path

from .analysis import DEFAULT_MARKET
from .fetch import _analyze_saved_snapshot, update
from .libitemdb_import import import_snapshot


LIBITEMDB_ROOT = Path(__file__).resolve().parents[1] / "AddOns" / "ItemDB"
LOCALIZATION_GROUPS = ("recipeNames", "resultNames", "materialNames")


def _require_non_decreasing_localization(base_result, imported_result):
    before = base_result.get("localizationCoverage", {})
    after = imported_result.get("localizationCoverage", {})
    for group in LOCALIZATION_GROUPS:
        old_stats = before.get(group, {})
        new_stats = after.get(group, {})
        old_count = old_stats.get("translated", 0)
        new_count = new_stats.get("translated", 0)
        if new_stats.get("total", 0) != old_stats.get("total", 0):
            raise RuntimeError("localization coverage scope changed for {}".format(group))
        if new_count < old_count:
            raise RuntimeError(
                "localization coverage decreased for {} ({} -> {})".format(
                    group, old_count, new_count
                )
            )


def _update_with_libitemdb(root, market, legacy_cache, craft_count):
    if not LIBITEMDB_ROOT.is_dir() or not (LIBITEMDB_ROOT / "ItemDB_Camelot.toc").is_file():
        raise RuntimeError(
            "--with-libitemdb requires the local Forever plugin at {}".format(LIBITEMDB_ROOT)
        )

    source_snapshot, base_result = update(root, market, legacy_cache, craft_count)
    destination = source_snapshot.with_name(source_snapshot.name + "-libitemdb")
    try:
        import_snapshot(source_snapshot, destination, LIBITEMDB_ROOT)
        result = _analyze_saved_snapshot(destination, craft_count=craft_count)
        _require_non_decreasing_localization(base_result, result)
        if not (destination / "libitemdb_import_audit.json").is_file():
            raise RuntimeError("LibItemDB import audit was not generated")
        if not (destination / "report.html").is_file():
            raise RuntimeError("localized report.html was not generated")
    except Exception as error:
        raise RuntimeError(
            "LibItemDB import/report failed; no combined report is being returned. "
            "The fetched AH snapshot is preserved at {}. Cause: {}".format(source_snapshot, error)
        ) from error
    return destination, result


def main():
    parser = argparse.ArgumentParser(description="AHledger Forever Alliance NPC crafting profit screen")
    subparsers = parser.add_subparsers(dest="command", required=True)
    update_parser = subparsers.add_parser("update", help="fetch a snapshot and generate JSON/HTML outputs")
    update_parser.add_argument("--root", default=".profit-lab", help="persistent cache and snapshot directory")
    update_parser.add_argument("--market", default=DEFAULT_MARKET, help="only the fixed Alliance market is supported")
    update_parser.add_argument("--legacy-cache", help="optional previous AHledger item-response JSONL cache")
    update_parser.add_argument("--crafts", type=int, default=1, help="number of crafts for mixed procurement plans")
    update_parser.add_argument("--with-libitemdb", action="store_true",
                               help="import the local AddOns/ItemDB Forever data into a separate report snapshot")
    analyze_parser = subparsers.add_parser("analyze", help="recompute saved raw data offline")
    analyze_parser.add_argument("snapshot", help="snapshot directory produced by update")
    analyze_parser.add_argument("--crafts", type=int, default=1, help="number of crafts for mixed procurement plans")
    args = parser.parse_args()
    if args.command == "update":
        if args.with_libitemdb:
            try:
                snapshot_dir, result = _update_with_libitemdb(
                    args.root, args.market, args.legacy_cache, args.crafts,
                )
            except Exception as error:
                parser.error(str(error))
        else:
            snapshot_dir, result = update(args.root, args.market, args.legacy_cache, args.crafts)
    else:
        snapshot_dir = Path(args.snapshot)
        result = _analyze_saved_snapshot(snapshot_dir, craft_count=args.crafts)
    print(json.dumps({
        "snapshot": str(snapshot_dir),
        "market": result["market"],
        "marketSnapshotAt": result["marketSnapshotAt"],
        "recipeCount": result["recipeCount"],
        "craftCount": result["craftCount"],
        "calculableBothScenariosCount": result["calculableBothScenariosCount"],
        "calculableMedianCount": result["calculableMedianCount"],
        "calculableMinBuyoutCount": result["calculableMinBuyoutCount"],
        "positiveAnyScenarioCount": result["positiveAnyScenarioCount"],
        "priorityCount": result["priorityCount"],
        "potentialCount": result["potentialCount"],
        "blockedOrNonPositiveCount": result["blockedOrNonPositiveCount"],
        "missingPriceOrVendorSellCount": result["missingPriceOrVendorSellCount"],
        "newlyCalculableHybridCount": result["newlyCalculableHybridCount"],
        "mixedPositiveCandidateCount": result["mixedPositiveCandidateCount"],
        "newMixedPositiveCandidateCount": result["newMixedPositiveCandidateCount"],
        "mixedExecutableCandidateCount": result["mixedExecutableCandidateCount"],
        "npcMaterialPurchaseEvidence": result["npcMaterialPurchaseEvidence"],
        "localizationCoverage": result["localizationCoverage"],
        "snapshotAligned": result["snapshotAlignment"]["aligned"],
        "report": str(snapshot_dir / "report.html"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
