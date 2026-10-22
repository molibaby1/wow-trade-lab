"""Safely import the static Forever tables shipped with LibItemDB."""

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
from pathlib import Path


_NAME_ROW = re.compile(r'^\s*\[(\d+)\]\s*=\s*("(?:\\.|[^"\\])*")\s*,?\s*$')
_NUMBER_ROW = re.compile(r"^\s*\[(\d+)\]\s*=\s*(\d+)\s*,?\s*$")
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _decode_lua_string(token):
    """Decode a quoted Lua string without evaluating Lua code."""
    if len(token) < 2 or token[0] != '"' or token[-1] != '"':
        raise ValueError("expected a double-quoted Lua string")
    value = []
    index = 1
    end = len(token) - 1
    simple_escapes = {"a": "\a", "b": "\b", "f": "\f", "n": "\n",
                      "r": "\r", "t": "\t", "v": "\v", "\\": "\\", '"': '"',
                      "'": "'"}
    while index < end:
        char = token[index]
        if char != "\\":
            value.append(char)
            index += 1
            continue
        index += 1
        if index >= end:
            raise ValueError("unterminated Lua escape")
        escaped = token[index]
        if escaped in simple_escapes:
            value.append(simple_escapes[escaped])
            index += 1
        elif escaped.isdigit():
            finish = index
            while finish < min(index + 3, end) and token[finish].isdigit():
                finish += 1
            number = int(token[index:finish], 10)
            if number > 255:
                raise ValueError("Lua decimal escape is outside byte range")
            value.append(chr(number))
            index = finish
        elif escaped == "z":
            index += 1
            while index < end and token[index].isspace():
                index += 1
        else:
            raise ValueError("unsupported Lua escape \\" + escaped)
    return "".join(value)


def parse_static_lua_table(text, loader_name, value_kind):
    """Read a literal [id] = value table from a LibItemDB loader call.

    Only integer values and double-quoted strings are accepted. Any executable or
    unrecognized table row fails closed; the source is never passed to Lua.
    """
    if value_kind not in ("string", "number"):
        raise ValueError("value_kind must be 'string' or 'number'")
    marker = "lib:{}({{".format(loader_name)
    start = text.find(marker)
    if start < 0:
        raise ValueError("missing {} table".format(loader_name))
    start = text.find("\n", start)
    if start < 0:
        raise ValueError("{} table has no rows".format(loader_name))
    end_match = re.search(r"^\s*}\)\s*$", text[start + 1:], re.M)
    if not end_match:
        raise ValueError("unterminated {} table".format(loader_name))
    body = text[start + 1:start + 1 + end_match.start()]
    row_pattern = _NAME_ROW if value_kind == "string" else _NUMBER_ROW
    result = {}
    for line_number, line in enumerate(body.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        match = row_pattern.fullmatch(line)
        if not match:
            raise ValueError("unsupported static Lua row {}:{}: {}".format(
                loader_name, line_number, stripped[:100]
            ))
        entity_id = int(match.group(1))
        value = _decode_lua_string(match.group(2)) if value_kind == "string" else int(match.group(2))
        if entity_id in result:
            raise ValueError("duplicate ID {} in {} table".format(entity_id, loader_name))
        result[entity_id] = value
    if not result:
        raise ValueError("{} table contains no literal rows".format(loader_name))
    return result


def _table_declared_count(text, phrase):
    match = re.search(phrase, text, re.I)
    return int(match.group(1)) if match else None


def read_libitemdb(plugin_root):
    """Read only the TOC-listed Forever static input files and their provenance."""
    plugin_root = Path(plugin_root)
    toc_path = plugin_root / "ItemDB_Camelot.toc"
    required = {
        "zhCNNames": "Data/Forever/zhCN/Names.lua",
        "enUSNames": "Data/Forever/enUS/Names.lua",
        "vendorPrices": "Data/Forever/_core/VendorPrices.lua",
        "sellPrices": "Data/Forever/_core/SellPrices.lua",
        "library": "LibItemDB-1.0.lua",
        "readme": "README.md",
        "license": "LICENSE",
        "toc": "ItemDB_Camelot.toc",
    }
    toc_text = toc_path.read_text(encoding="utf-8")
    toc_paths = {line.strip().replace("\\", "/").casefold()
                 for line in toc_text.splitlines() if line.strip() and not line.lstrip().startswith("#")}
    for key in ("zhCNNames", "enUSNames", "vendorPrices", "sellPrices", "library"):
        if required[key].casefold() not in toc_paths:
            raise ValueError("Camelot TOC does not load {}".format(required[key]))
    version_match = re.search(r"^## Version:\s*(.+)$", toc_text, re.M)
    if not version_match:
        raise ValueError("ItemDB_Camelot.toc has no plugin version")
    version = version_match.group(1).strip()
    interface_match = re.search(r"^## Interface:\s*(\d+)$", toc_text, re.M)
    interface = interface_match.group(1) if interface_match else None

    paths = {key: plugin_root / value for key, value in required.items()}
    file_metadata = {
        key: {"path": required[key], "sha256": _sha256(path), "sizeBytes": path.stat().st_size}
        for key, path in paths.items()
    }
    license_text = paths["license"].read_text(encoding="utf-8")
    if not license_text.startswith("MIT License"):
        raise ValueError("LibItemDB LICENSE is not the expected MIT license")
    zh_text = paths["zhCNNames"].read_text(encoding="utf-8")
    en_text = paths["enUSNames"].read_text(encoding="utf-8")
    vendor_text = paths["vendorPrices"].read_text(encoding="utf-8")
    zh_build_match = re.search(r"client build\s+([\w.]+)", zh_text, re.I)
    en_build_match = re.search(r"client build\s+([\w.]+)", en_text, re.I)
    vendor_build_match = re.search(r"client build\s+([\w.]+)", vendor_text, re.I)
    client_build = (zh_build_match.group(1) if zh_build_match else
                    vendor_build_match.group(1) if vendor_build_match else None)
    zh_names = parse_static_lua_table(zh_text, "LoadNames", "string")
    en_names = parse_static_lua_table(en_text, "LoadNames", "string")
    vendor_prices = parse_static_lua_table(vendor_text, "LoadVendorPrices", "number")
    if not zh_build_match or not vendor_build_match or zh_build_match.group(1) != vendor_build_match.group(1):
        raise ValueError("Forever zhCN and vendor table build headers do not match")
    return {
        "metadata": {
            "name": "LibItemDB Forever zhCN/enUS names and vendor base prices",
            "version": version,
            "clientBuild": client_build,
            "interface": interface,
            "enUSHeaderBuild": en_build_match.group(1) if en_build_match else None,
            "recordedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "license": "MIT",
            "files": file_metadata,
            "zhCNDeclaredNameCount": _table_declared_count(zh_text, r"-\s*(\d+)\s+names"),
            "enUSDeclaredNameCount": _table_declared_count(en_text, r"-\s*(\d+)\s+names"),
            "vendorPriceDeclaredCount": _table_declared_count(vendor_text, r"-\s*(\d+)\s+of\s+\d+\s+shipped items"),
            "vendorPriceSourceNotes": [line.strip("- ") for line in vendor_text.splitlines()
                                       if line.startswith("-- source ")],
            "vendorPriceProvenance": "wago ItemSparse.BuyPrice intersected with Wrath/Cata-era emulator npc_vendor rows; maxcount=0 and ExtendedCost=0",
            "vendorPriceBuyCountIncluded": False,
            "vendorNamesIncluded": False,
            "sellPricesUsedForProcurement": False,
        },
        "zhCNNames": zh_names,
        "enUSNames": en_names,
        "vendorPrices": vendor_prices,
    }


def _cjk_name(value):
    return isinstance(value, str) and bool(_CJK.search(value))


def _id_text(value):
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return None


def _normalized_english_name(value):
    if not isinstance(value, str):
        return ""
    return "".join(character.casefold() for character in value if character.isalnum())


def _recipe_ids(crafting):
    item_ids = set()
    spell_rows = []
    for row in crafting.get("recipes", []):
        if not isinstance(row, dict):
            continue
        result = row.get("result") or {}
        recipe = row.get("recipe") or {}
        if _id_text(result.get("id")):
            item_ids.add(int(result["id"]))
        spell_rows.append(row)
        for reagent in row.get("reagents", []):
            if isinstance(reagent, dict) and _id_text(reagent.get("id")):
                item_ids.add(int(reagent["id"]))
    return item_ids, spell_rows


def build_localization(crafting, prior_localization, zh_names, en_names, metadata,
                       recorded_at, ah_names=None):
    """Merge itemId translations, preserving previous manual entries before imports."""
    prior_localization = prior_localization if isinstance(prior_localization, dict) else {}
    prior_entries = [entry for entry in prior_localization.get("entries", [])
                     if isinstance(entry, dict)]
    entries = list(prior_entries)
    grouped = {}
    for entry in prior_entries:
        kind = entry.get("kind")
        entity_id = _id_text(entry.get("id"))
        if kind in ("item", "spell") and entity_id:
            grouped.setdefault((kind, entity_id), []).append(entry)

    item_ids, spell_rows = _recipe_ids(crafting)
    source_hash = metadata["files"]["zhCNNames"]["sha256"]
    english_hash = metadata["files"]["enUSNames"]["sha256"]
    source_path = metadata["files"]["zhCNNames"]["path"]
    imported_item_count = 0
    manual_override_count = 0
    manual_name_conflicts = []
    ah_name_conflicts = []
    item_zh = {}
    item_entries = {}

    for item_id in sorted(item_ids):
        key = ("item", str(item_id))
        existing = grouped.get(key, [])
        distinct_prior = {entry.get("zhCN") for entry in existing if _cjk_name(entry.get("zhCN"))}
        plugin_zh = zh_names.get(item_id)
        plugin_en = en_names.get(item_id)
        ah_name = (ah_names or {}).get(str(item_id))
        name_conflict = bool(
            plugin_en and ah_name and not ah_name.casefold().startswith("item ")
            and _normalized_english_name(plugin_en) != _normalized_english_name(ah_name)
        )
        if name_conflict:
            ah_name_conflicts.append({"itemId": item_id, "libItemDBEnUS": plugin_en,
                                      "ahledgerEnUS": ah_name})
        if len(distinct_prior) == 1:
            item_zh[item_id] = next(iter(distinct_prior))
            item_entries[item_id] = existing[0]
            manual_override_count += 1
            if _cjk_name(plugin_zh) and plugin_zh != item_zh[item_id]:
                manual_name_conflicts.append({"itemId": item_id, "manualZhCN": item_zh[item_id],
                                              "libItemDBZhCN": plugin_zh})
            continue
        if len(distinct_prior) > 1:
            continue
        if not _cjk_name(plugin_zh):
            continue
        entry = {
            "kind": "item", "id": item_id, "englishName": plugin_en,
            "zhCN": plugin_zh, "source": "LibItemDB Forever zhCN Names.lua",
            "sourceFile": source_path, "sourceFileSha256": source_hash,
            "englishSourceFile": metadata["files"]["enUSNames"]["path"],
            "englishSourceFileSha256": english_hash,
            "version": "{}; Forever client build {}".format(metadata["version"], metadata["clientBuild"]),
            "clientBuild": metadata["clientBuild"], "recordedAt": recorded_at,
            "license": metadata["license"],
            "nameConflictWithAHledger": name_conflict,
            "ahledgerEnglishName": ah_name if name_conflict else None,
        }
        entries.append(entry)
        grouped[key] = [entry]
        item_zh[item_id] = plugin_zh
        item_entries[item_id] = entry
        imported_item_count += 1

    derived_spell_count = 0
    for row in spell_rows:
        recipe = row.get("recipe") or {}
        result = row.get("result") or {}
        spell_id = _id_text(recipe.get("spellId"))
        result_id = _id_text(result.get("id"))
        if not spell_id or not result_id or grouped.get(("spell", spell_id)):
            continue
        localized_result = item_zh.get(int(result_id))
        if not _cjk_name(localized_result):
            continue
        item_entry = item_entries.get(int(result_id), {})
        entry = {
            "kind": "spell", "id": int(spell_id),
            "englishName": recipe.get("name"), "zhCN": localized_result,
            "source": "派生配方名：使用成品 itemId {} 的本地化名称".format(result_id),
            "sourceFile": item_entry.get("sourceFile"),
            "sourceFileSha256": item_entry.get("sourceFileSha256"),
            "version": item_entry.get("version") or "LibItemDB Forever; local result item translation",
            "clientBuild": item_entry.get("clientBuild") or metadata["clientBuild"],
            "recordedAt": item_entry.get("recordedAt") or recorded_at,
            "license": item_entry.get("license") or metadata["license"],
            "translationType": "derived_from_result_itemId",
            "derivedFromResultItemId": int(result_id),
        }
        if item_entry.get("nameConflictWithAHledger"):
            entry["nameConflictWithAHledger"] = True
            entry["ahledgerEnglishName"] = item_entry.get("ahledgerEnglishName")
        entries.append(entry)
        grouped[("spell", spell_id)] = [entry]
        derived_spell_count += 1

    dataset = {
        "name": "LibItemDB Forever zhCN with preserved manual overrides",
        "version": metadata["version"],
        "recordedAt": recorded_at,
        "source": "Local AddOns/ItemDB files; no network translation or Lua execution",
        "clientBuild": metadata["clientBuild"],
        "license": metadata["license"],
        "previousDataset": prior_localization.get("dataset", {}),
        "libItemDB": {
            "files": metadata["files"],
            "interface": metadata.get("interface"),
            "zhCNDeclaredNameCount": metadata.get("zhCNDeclaredNameCount"),
            "enUSDeclaredNameCount": metadata.get("enUSDeclaredNameCount"),
            "importedItemTranslations": imported_item_count,
            "preservedManualItemTranslations": manual_override_count,
            "derivedRecipeNames": derived_spell_count,
            "englishNameConflictCount": len(ah_name_conflicts),
            "manualTranslationConflictCount": len(manual_name_conflicts),
            "license": metadata["license"],
            "distribution": "local-only; generated files remain under ignored .profit-lab/",
        },
    }
    audit = {
        "englishNameConflictsWithAHledger": sorted(ah_name_conflicts, key=lambda row: row["itemId"]),
        "manualTranslationConflicts": sorted(manual_name_conflicts, key=lambda row: row["itemId"]),
        "conflictedPriorLocalizationKeys": [
            {"kind": key[0], "id": key[1], "values": sorted(str(entry.get("zhCN")) for entry in values)}
            for key, values in sorted(grouped.items())
            if len({entry.get("zhCN") for entry in values}) > 1
        ],
    }
    return {"schemaVersion": 1, "dataset": dataset, "entries": entries}, audit


def build_vendor_price_candidates(material_ids, vendor_prices, metadata, recorded_at=None):
    """Preserve vendor base prices, but leave pack/unit fields unknown without BuyCount."""
    vendor_file = metadata["files"]["vendorPrices"]
    output = []
    for item_id in sorted(set(material_ids) & set(vendor_prices)):
        base_price = vendor_prices[item_id]
        output.append({
            "itemId": item_id,
            "vendorId": None, "vendorName": None, "location": None, "faction": None,
            "packPriceCopper": None, "packQuantity": None,
            "basePriceCopper": base_price, "pagePriceCopper": base_price,
            "buyCountStatus": "not_shipped",
            "pagePriceText": "LibItemDB GetVendorBasePrice={} 铜；VendorPrices.lua 只有 itemId→铜币基础价，没有 BuyCount/购买包数，不能解释为单件价或整包价。".format(base_price),
            "stockType": "unknown", "stockPacks": None,
            "stockSourceLabel": "Wrath/Cata-era emulator npc_vendor 交集记录 maxcount=0；Forever 当前库存未核验",
            "conditions": "插件未提供具体商人、阵营、位置或购买数量；供应筛选部分来自 Wrath/Cata 模拟器数据。不得用于单位成本。",
            "conditionsVerified": False, "reachable": False,
            "source": "LibItemDB Forever VendorPrices.lua; unscaled vendor base price",
            "sourceSite": "LibItemDB",
            "sourceUrl": None, "vendorSourceUrl": None,
            "sourceObservedAt": None, "recordedAt": recorded_at or metadata.get("recordedAt"),
            "extractedAt": recorded_at or metadata.get("recordedAt"),
            "clientBuild": metadata.get("clientBuild"),
            "sourceVersion": "{}; client build {}".format(metadata["version"], metadata.get("clientBuild")),
            "priceApplicability": "Forever ItemSparse 基础报价与 Wrath/Cata-era npc_vendor 供应交集；购买数量、商人身份、当前库存/可达性和 Forever 当前客户端适用性未知。仅待核验展示。",
            "evidenceLevel": "libitemdb_forever_base_price_unscaled",
            "appliesToCurrentClient": False,
            "localEvidence": [{"path": vendor_file["path"], "sha256": vendor_file["sha256"]}],
        })
    return output


def import_snapshot(source_snapshot, destination, plugin_root, recorded_at=None):
    source_snapshot = Path(source_snapshot)
    destination = Path(destination)
    if not source_snapshot.is_dir():
        raise FileNotFoundError("source snapshot not found: {}".format(source_snapshot))
    if destination.exists():
        raise FileExistsError("destination already exists: {}".format(destination))
    plugin_data = read_libitemdb(plugin_root)
    metadata = plugin_data["metadata"]
    recorded_at = recorded_at or metadata["recordedAt"]

    crafting = json.loads((source_snapshot / "raw/crafting.json").read_text(encoding="utf-8"))
    prior_localization = json.loads((source_snapshot / "localization.json").read_text(encoding="utf-8"))
    ah_names = {}
    item_dir = source_snapshot / "raw/items"
    if item_dir.is_dir():
        for path in item_dir.glob("*.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            item_id = _id_text(item.get("id")) if isinstance(item, dict) else None
            if item_id:
                ah_names[item_id] = item.get("name")

    localization, locale_audit = build_localization(
        crafting, prior_localization, plugin_data["zhCNNames"], plugin_data["enUSNames"],
        metadata, recorded_at, ah_names=ah_names,
    )
    existing_evidence_path = source_snapshot / "npc_material_purchase_evidence.json"
    purchase_evidence = json.loads(existing_evidence_path.read_text(encoding="utf-8"))
    manual_inputs_path = source_snapshot.parent.parent / "manual_inputs.json"
    manual_inputs_hash = None
    merged_manual_record_count = 0
    if manual_inputs_path.is_file():
        manual_raw = manual_inputs_path.read_bytes()
        manual_inputs_hash = hashlib.sha256(manual_raw).hexdigest()
        current_manual_inputs = json.loads(manual_raw.decode("utf-8"))
        current_source = current_manual_inputs.get("npcMaterialPurchaseEvidence", {})
        if isinstance(current_source, list):
            current_records = current_source
        elif isinstance(current_source, dict):
            current_records = current_source.get("records", [])
            if isinstance(current_records, dict):
                current_records = [
                    {"itemId": value.get("itemId", item_id), **value}
                    for item_id, values in current_records.items()
                    for value in (values if isinstance(values, list) else [values])
                    if isinstance(value, dict)
                ]
        else:
            current_records = []
        current_records = [record for record in current_records if isinstance(record, dict)]
    else:
        current_records = []
    item_ids, _ = _recipe_ids(crafting)
    material_ids = {int(reagent["id"]) for row in crafting.get("recipes", [])
                    for reagent in row.get("reagents", []) if _id_text(reagent.get("id"))}
    vendor_candidates = build_vendor_price_candidates(
        material_ids, plugin_data["vendorPrices"], metadata, recorded_at
    )
    records = [record for record in purchase_evidence.get("records", []) if isinstance(record, dict)]
    seen_record_signatures = {json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records}
    for record in current_records:
        signature = json.dumps(record, ensure_ascii=False, sort_keys=True)
        if signature not in seen_record_signatures:
            records.append(record)
            seen_record_signatures.add(signature)
            merged_manual_record_count += 1
    plugin_candidate_ids = {record["itemId"] for record in vendor_candidates}
    supported_ids = set()
    in_game_supported_ids = set()
    for record in records:
        if record.get("itemId") not in plugin_candidate_ids:
            continue
        if (isinstance(record.get("packPriceCopper"), int)
                and isinstance(record.get("packQuantity"), int)
                and record["packPriceCopper"] >= 0 and record["packQuantity"] > 0):
            supported_ids.add(record["itemId"])
            if record.get("evidenceLevel") == "current_in_game":
                in_game_supported_ids.add(record["itemId"])
    records.extend(vendor_candidates)
    dataset = purchase_evidence.get("dataset", {})
    if not isinstance(dataset, dict):
        dataset = {}
    dataset["libItemDBVendorPrices"] = {
        "version": metadata["version"], "clientBuild": metadata["clientBuild"],
        "file": metadata["files"]["vendorPrices"],
        "vendorPriceSourceNotes": metadata["vendorPriceSourceNotes"],
        "vendorPriceProvenance": metadata["vendorPriceProvenance"],
        "vendorPriceDeclaredCount": metadata["vendorPriceDeclaredCount"],
        "materialCandidateCount": len(vendor_candidates),
        "buyCountIncludedByPlugin": False,
        "pluginCandidatesWithKnownPackQuantity": 0,
        "candidateItemsWithSeparatePackEvidence": len(supported_ids),
        "candidateItemsWithCurrentInGamePackEvidence": len(in_game_supported_ids),
        "sellPricesUsedForProcurement": False,
        "license": metadata["license"],
    }
    if manual_inputs_hash:
        dataset["currentManualInputs"] = {
            "source": ".profit-lab/manual_inputs.json",
            "sha256": manual_inputs_hash,
            "purchaseRecordsMerged": merged_manual_record_count,
        }
    purchase_evidence = {
        "schemaVersion": purchase_evidence.get("schemaVersion", 1),
        "dataset": dataset,
        "currentClientBuild": purchase_evidence.get("currentClientBuild"),
        "records": records,
    }

    shutil.copytree(source_snapshot, destination)
    localization_raw = (json.dumps(localization, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    purchase_raw = (json.dumps(purchase_evidence, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (destination / "localization.json").write_bytes(localization_raw)
    (destination / "npc_material_purchase_evidence.json").write_bytes(purchase_raw)
    audit = {
        "sourceSnapshot": str(source_snapshot),
        "generatedAt": recorded_at,
        "libItemDB": metadata,
        "counts": {
            "targetMaterialCount": len(material_ids),
            "targetResultCount": len({int(row["result"]["id"]) for row in crafting["recipes"]
                                       if _id_text((row.get("result") or {}).get("id"))}),
            "targetRecipeCount": len({int(row["recipe"]["spellId"]) for row in crafting["recipes"]
                                       if _id_text((row.get("recipe") or {}).get("spellId"))}),
            "vendorPriceRows": len(plugin_data["vendorPrices"]),
            "vendorMaterialCandidates": len(vendor_candidates),
            "candidateItemsWithSeparatePackEvidence": len(supported_ids),
            "candidateItemsWithCurrentInGamePackEvidence": len(in_game_supported_ids),
            "currentManualPurchaseRecordsMerged": merged_manual_record_count,
            "currentManualInputsSha256": manual_inputs_hash,
        },
        "localizationAudit": locale_audit,
    }
    audit_raw = (json.dumps(audit, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (destination / "libitemdb_import_audit.json").write_bytes(audit_raw)
    manifest_path = destination / "source_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    manifest["localization"] = {
        "snapshotFile": "localization.json", "sha256": hashlib.sha256(localization_raw).hexdigest(),
        "dataset": localization["dataset"], "entryCount": len(localization["entries"]),
    }
    manifest["npcMaterialPurchaseEvidence"] = {
        "snapshotFile": "npc_material_purchase_evidence.json",
        "sha256": hashlib.sha256(purchase_raw).hexdigest(),
        "recordCount": len(records), "currentClientBuild": purchase_evidence["currentClientBuild"],
        "libItemDBCandidateCount": len(vendor_candidates),
    }
    manifest["libItemDBImportAudit"] = {
        "snapshotFile": "libitemdb_import_audit.json",
        "sha256": hashlib.sha256(audit_raw).hexdigest(),
    }
    (destination / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return audit


def main():
    parser = argparse.ArgumentParser(description="Import local LibItemDB Forever static data into a copied snapshot")
    parser.add_argument("--plugin-root", default="AddOns/ItemDB")
    parser.add_argument("--source-snapshot", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--recorded-at", help="UTC ISO timestamp for this local import")
    args = parser.parse_args()
    result = import_snapshot(args.source_snapshot, args.destination, args.plugin_root, args.recorded_at)
    print(json.dumps(result["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
