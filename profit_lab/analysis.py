"""Deterministic analysis of saved AHledger snapshots."""

import datetime as dt
import json
import re
from collections import Counter
from fractions import Fraction


DEFAULT_MARKET = "forever.normal.alliance.us"
_CJK_NAME = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _as_utc_epoch(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return int(parsed.astimezone(dt.timezone.utc).timestamp())
    except (ValueError, OverflowError):
        return None


def _integer(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _fraction_value(value):
    return value.numerator if value.denominator == 1 else float(value)


def _localization_index(localization):
    localization = localization if isinstance(localization, dict) else {}
    entries = localization.get("entries", [])
    index = {}
    conflicts = set()
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or entry.get("kind") not in ("item", "spell"):
            continue
        entity_id = _integer(entry.get("id"))
        zh_name = entry.get("zhCN")
        if entity_id is None or not isinstance(zh_name, str) or not zh_name.strip():
            continue
        english_name = entry.get("englishName")
        if (not _CJK_NAME.search(zh_name)
                or (isinstance(english_name, str)
                    and zh_name.strip().casefold() == english_name.strip().casefold())):
            continue
        if not all(isinstance(entry.get(key), str) and entry[key].strip()
                   for key in ("source", "version", "recordedAt")):
            continue
        key = (entry["kind"], str(entity_id))
        if key in index and index[key].get("zhCN") != zh_name:
            conflicts.add(key)
        else:
            index[key] = entry
    for key in conflicts:
        index.pop(key, None)
    return index, conflicts


def _localized_name(index, kind, entity_id, english_name):
    entry = index.get((kind, str(entity_id))) if entity_id is not None else None
    translated = entry.get("zhCN") if isinstance(entry, dict) else None
    return {
        "enUS": english_name,
        "zhCN": translated or english_name,
        "fallbackId": entity_id if not translated else None,
        "translationEvidence": entry,
    }


def _purchase_records_for(evidence, item_id):
    records = evidence.get("records", []) if isinstance(evidence, dict) else []
    if isinstance(records, dict):
        flattened = []
        for key, values in records.items():
            for value in values if isinstance(values, list) else [values]:
                if isinstance(value, dict):
                    flattened.append({"itemId": value.get("itemId", key), **value})
        records = flattened
    return [record for record in records if isinstance(record, dict)
            and str(record.get("itemId")) == str(item_id)] if isinstance(records, list) else []


def _purchase_location(record):
    location = record.get("location")
    if isinstance(location, str) and location.strip():
        return location.strip()
    if isinstance(location, dict):
        zone = location.get("zone")
        if isinstance(zone, str) and zone.strip():
            coordinates = [location.get("x"), location.get("y")]
            if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in coordinates):
                return "{} ({:.1f}, {:.1f})".format(zone.strip(), coordinates[0], coordinates[1])
            return zone.strip()
    return None


def _purchase_evidence_priority(record, current_build):
    """Prefer current in-game observations before Forever and historical references."""
    level = record.get("evidenceLevel")
    client_build = record.get("clientBuild")
    if level == "current_in_game":
        if record.get("appliesToCurrentClient") is True and not (
                current_build and client_build and current_build != client_build):
            return 0
        return 2
    if level in ("seen_in_forever", "foreverdb_public_page"):
        return 1
    if level in ("classic_data", "simulator_historical", "libitemdb_forever_base_price_unscaled"):
        return 2
    return 3


def _assess_purchase_record(record, requested_quantity, market_faction, current_build,
                            *, repeatable=False):
    reference_reasons = []
    reasons = []
    pack_price = _integer(record.get("packPriceCopper"))
    pack_quantity = _integer(record.get("packQuantity"))
    if pack_price is None or pack_price < 0:
        reference_reasons.append("pack_price_missing_or_invalid")
    if pack_quantity is None or pack_quantity <= 0:
        reference_reasons.append("pack_quantity_missing_or_ambiguous")
    vendor_id = record.get("vendorId")
    has_vendor_id = ((isinstance(vendor_id, int) and not isinstance(vendor_id, bool) and vendor_id > 0)
                     or (isinstance(vendor_id, str) and vendor_id.strip()))
    has_vendor_name = isinstance(record.get("vendorName"), str) and bool(record["vendorName"].strip())
    if not has_vendor_id and not has_vendor_name:
        reference_reasons.append("vendor_identity_missing")
    if not has_vendor_id:
        reasons.append("vendor_id_missing")
    if not has_vendor_name:
        reasons.append("vendor_name_missing")
    location = _purchase_location(record)
    if location is None:
        reasons.append("vendor_location_missing")
    faction = str(record.get("faction") or "").lower()
    if faction not in ("alliance", "horde", "neutral", "both"):
        reasons.append("vendor_faction_unknown")
    elif market_faction not in (faction, "both", "neutral") and faction not in ("both", "neutral"):
        reference_reasons.append("vendor_faction_mismatch")
        reasons.append("vendor_faction_mismatch")
    if record.get("reachable") is not True:
        reasons.append("vendor_reachability_unverified")
    conditions = record.get("conditions")
    if record.get("conditionsVerified") is not True or not isinstance(conditions, str) or not conditions.strip():
        reasons.append("purchase_conditions_unverified")
    source = record.get("source")
    if not isinstance(source, str) or not source.strip():
        reference_reasons.append("purchase_source_missing")
    if not (record.get("sourceUrl") or record.get("localEvidence") or record.get("evidence")):
        reference_reasons.append("purchase_evidence_reference_missing")
    client_build = record.get("clientBuild")
    extracted_at = record.get("extractedAt")
    observed_at = record.get("sourceObservedAt") or extracted_at or record.get("recordedAt")
    if _as_utc_epoch(observed_at) is None:
        reference_reasons.append("purchase_observation_time_missing")
    if not record.get("priceApplicability") and not conditions:
        reference_reasons.append("price_applicability_missing")
    if not isinstance(client_build, str) or not client_build.strip():
        reasons.append("client_build_missing")
    if _as_utc_epoch(extracted_at) is None:
        reasons.append("purchase_extraction_time_missing")
    elif current_build and client_build and current_build != client_build:
        reasons.append("client_build_mismatch")
    level = record.get("evidenceLevel")
    if level != "current_in_game":
        reasons.append("evidence_not_current_forever")
    if level == "current_in_game" and record.get("appliesToCurrentClient") is not True:
        reasons.append("current_client_applicability_unverified")
    stock_type = record.get("stockType")
    stock_packs = _integer(record.get("stockPacks"))
    packages_needed = None
    if stock_type == "unlimited":
        pass
    elif stock_type == "limited":
        if stock_packs is None or stock_packs < 0:
            reasons.append("limited_stock_unknown")
            reference_reasons.append("limited_stock_unknown")
        elif pack_quantity is not None and pack_quantity > 0:
            packages_needed = (max(0, requested_quantity) + pack_quantity - 1) // pack_quantity
            if packages_needed > stock_packs:
                reasons.append("limited_stock_insufficient")
                reference_reasons.append("limited_stock_insufficient")
        if repeatable:
            reasons.append("limited_stock_not_repeatable")
            reference_reasons.append("limited_stock_not_repeatable")
    else:
        reasons.append("stock_type_unknown")
        if repeatable:
            reference_reasons.append("repeatable_stock_unverified")
    reference_usable = (not reference_reasons and pack_price is not None and pack_quantity is not None)
    if reference_usable:
        unit_price = Fraction(pack_price, pack_quantity)
    else:
        unit_price = None
    if not reference_usable:
        reasons.extend(reference_reasons)
    reference_warnings = []
    if not isinstance(client_build, str) or not client_build.strip():
        reference_warnings.append("client_build_missing")
    if faction not in ("alliance", "horde", "neutral", "both"):
        reference_warnings.append("vendor_faction_unknown")
    if record.get("reachable") is not True:
        reference_warnings.append("vendor_reachability_unverified")
    if record.get("conditionsVerified") is not True:
        reference_warnings.append("purchase_conditions_unverified")
    if level != "current_in_game" or record.get("appliesToCurrentClient") is not True:
        reference_warnings.append("current_client_applicability_unverified")
    if _as_utc_epoch(extracted_at) is None:
        reference_warnings.append("purchase_extraction_time_missing")
    return {
        "record": record,
        "usable": unit_price is not None and not reasons,
        "referenceUsable": reference_usable,
        "reasons": sorted(set(reasons)),
        "referenceReasons": sorted(set(reference_reasons)),
        "referenceWarnings": sorted(set(reference_warnings)),
        "unitPrice": unit_price,
        "packPriceCopper": pack_price,
        "packQuantity": pack_quantity,
        "packagesNeeded": packages_needed,
        "stockPacks": stock_packs,
        "stockType": stock_type,
        "vendorLocation": location,
    }


def _npc_purchase_options(evidence, item_id, requested_quantity, market_faction, *, repeatable=False):
    current_build = evidence.get("currentClientBuild") if isinstance(evidence, dict) else None
    assessments = [_assess_purchase_record(
        record, requested_quantity, market_faction, current_build, repeatable=repeatable
    ) for record in _purchase_records_for(evidence, item_id)]
    by_vendor = {}
    for assessment in assessments:
        if not assessment["referenceUsable"]:
            continue
        record = assessment["record"]
        signature = (assessment["packPriceCopper"], assessment["packQuantity"],
                     assessment["stockType"], assessment["stockPacks"])
        vendor_id = record.get("vendorId")
        vendor_key = ("id:{}".format(vendor_id) if vendor_id is not None
                      else "name:{}".format(str(record.get("vendorName") or "").strip().casefold()))
        by_vendor.setdefault(vendor_key, set()).add(signature)
    conflicts = {vendor_id for vendor_id, signatures in by_vendor.items() if len(signatures) > 1}
    for assessment in assessments:
        record = assessment["record"]
        vendor_id = record.get("vendorId")
        vendor_key = ("id:{}".format(vendor_id) if vendor_id is not None
                      else "name:{}".format(str(record.get("vendorName") or "").strip().casefold()))
        if assessment["referenceUsable"] and vendor_key in conflicts:
            assessment["usable"] = False
            assessment["referenceUsable"] = False
            assessment["unitPrice"] = None
            assessment["reasons"].append("same_vendor_price_conflict")
            assessment["referenceReasons"].append("same_vendor_price_conflict")
    return assessments


def _hybrid_scenario(reagents, prices, market_aligned, evidence, income_per_craft,
                     craft_count, market_faction, price_key, *, repeatable=False):
    lines = []
    total_cost = Fraction(0, 1)
    cash_estimate = 0
    npc_cash = 0
    complete = True
    cash_depth_known = True
    for reagent in reagents:
        item_id = reagent.get("itemId")
        quantity_per_craft = reagent.get("quantity")
        quantity = quantity_per_craft * craft_count if isinstance(quantity_per_craft, int) and quantity_per_craft >= 0 else None
        market_price = reagent.get("medianUnitCopper") if price_key == "median" else reagent.get("minBuyoutUnitCopper")
        if not market_aligned:
            market_price = None
        market_price = market_price if isinstance(market_price, int) and market_price >= 0 else None
        options = _npc_purchase_options(evidence, item_id, quantity or 0, market_faction,
                                        repeatable=repeatable)
        usable_npc = [value for value in options if value["referenceUsable"]]
        current_build = evidence.get("currentClientBuild") if isinstance(evidence, dict) else None
        npc_option = min(
            usable_npc,
            key=lambda value: (_purchase_evidence_priority(value["record"], current_build), value["unitPrice"]),
        ) if usable_npc else None
        choices = []
        if quantity is not None:
            if market_price is not None:
                choices.append((Fraction(market_price, 1), "ah_{}".format(price_key), None))
            if npc_option is not None:
                choices.append((npc_option["unitPrice"], "npc", npc_option))
        choices.sort(key=lambda value: (value[0], 0 if value[1] == "npc" else 1))
        selected = choices[0] if choices else None
        record = selected[2]["record"] if selected and selected[2] else None
        unit_price = selected[0] if selected else None
        allocated = unit_price * quantity if unit_price is not None and quantity is not None else None
        line_cash = None
        packs = None
        excess = None
        reason = "no reliable NPC or AH price" if selected is None else ""
        if selected is not None and selected[1] == "npc":
            packs = (quantity + selected[2]["packQuantity"] - 1) // selected[2]["packQuantity"] if quantity else 0
            line_cash = packs * selected[2]["packPriceCopper"]
            excess = packs * selected[2]["packQuantity"] - quantity
            npc_cash += line_cash
            if not selected[2]["usable"]:
                cash_depth_known = False
            reason = "NPC 参考单位价不高于 AH 参考价" if market_price is not None else "仅有可追溯的 NPC 采购参考价"
        elif selected is not None:
            line_cash = quantity * market_price
            cash_depth_known = False
            reason = "AH 参考价不高于 NPC 参考单位价" if npc_option else "没有可用于理论参考的 NPC 报价，采用 AH 参考价"
        if selected is None or allocated is None or quantity is None:
            complete = False
        else:
            total_cost += allocated
            cash_estimate += line_cash
        npc_candidates = [{
            "usable": value["usable"], "referenceUsable": value["referenceUsable"],
            "reasons": value["reasons"], "referenceReasons": value["referenceReasons"],
            "referenceWarnings": value["referenceWarnings"],
            "vendorId": value["record"].get("vendorId"),
            "vendorName": value["record"].get("vendorName"),
            "location": value["vendorLocation"], "faction": value["record"].get("faction"),
            "unitPriceCopper": _fraction_value(value["unitPrice"]) if value["unitPrice"] is not None else None,
            "packPriceCopper": value["packPriceCopper"], "packQuantity": value["packQuantity"],
            "stockType": value["stockType"], "stockPacks": value["stockPacks"],
            "stockSourceLabel": value["record"].get("stockSourceLabel"),
            "conditions": value["record"].get("conditions"),
            "source": value["record"].get("source"), "sourceUrl": value["record"].get("sourceUrl"),
            "sourceSite": value["record"].get("sourceSite"),
            "vendorSourceUrl": value["record"].get("vendorSourceUrl"),
            "pagePriceCopper": value["record"].get("pagePriceCopper"),
            "pagePriceText": value["record"].get("pagePriceText"),
            "basePriceCopper": value["record"].get("basePriceCopper"),
            "buyCountStatus": value["record"].get("buyCountStatus"),
            "localEvidence": value["record"].get("localEvidence"),
            "clientBuild": value["record"].get("clientBuild"),
            "extractedAt": value["record"].get("extractedAt"),
            "sourceObservedAt": value["record"].get("sourceObservedAt"),
            "sourceVersion": value["record"].get("sourceVersion"),
            "priceApplicability": value["record"].get("priceApplicability"),
            "evidenceLevel": value["record"].get("evidenceLevel"),
            "appliesToCurrentClient": value["record"].get("appliesToCurrentClient"),
        } for value in options]
        selected_npc_evidence = None
        if record is not None:
            selected_npc_evidence = next((candidate for candidate in npc_candidates
                                          if str(candidate.get("vendorId")) == str(record.get("vendorId"))
                                          and candidate.get("packPriceCopper") == record.get("packPriceCopper")
                                          and candidate.get("packQuantity") == record.get("packQuantity")
                                          and candidate.get("source") == record.get("source")
                                          and candidate.get("evidenceLevel") == record.get("evidenceLevel")), None)
        lines.append({
            "itemId": item_id, "quantityPerCraft": quantity_per_craft,
            "requestedQuantity": quantity, "channel": selected[1] if selected else None,
            "unitPriceCopper": _fraction_value(unit_price) if unit_price is not None else None,
            "unitPriceExact": "{}/{}".format(unit_price.numerator, unit_price.denominator) if unit_price is not None else None,
            "allocatedCostCopper": _fraction_value(allocated) if allocated is not None else None,
            "allocatedCostCopperExact": "{}/{}".format(allocated.numerator, allocated.denominator) if allocated is not None else None,
            "cashOutlayCopper": line_cash, "packagesToBuy": packs,
            "excessQuantity": excess, "reason": reason,
            "marketUnitPriceCopper": market_price,
            "marketDepthKnown": False if selected and selected[1].startswith("ah_") else None,
            "npcOptions": npc_candidates,
            "selectedNpcEvidence": selected_npc_evidence,
        })
    material_cost = total_cost if complete else None
    income = income_per_craft * craft_count if income_per_craft is not None else None
    profit = income - material_cost if income is not None and material_cost is not None else None
    return {
        "priceScenario": price_key,
        "repeatable": repeatable,
        "craftCount": craft_count,
        "materialCostCopper": _fraction_value(material_cost) if material_cost is not None else None,
        "materialCostCopperExact": "{}/{}".format(material_cost.numerator, material_cost.denominator) if material_cost is not None else None,
        "materialCostPerCraftCopper": _fraction_value(material_cost / craft_count) if material_cost is not None else None,
        "incomeCopper": income,
        "profitCopper": _fraction_value(profit) if profit is not None else None,
        "profitCopperExact": "{}/{}".format(profit.numerator, profit.denominator) if profit is not None else None,
        "profitPerCraftCopper": _fraction_value(profit / craft_count) if profit is not None else None,
        "cashOutlayEstimateCopper": cash_estimate if complete else None,
        "npcCashOutlayCopper": npc_cash if complete else None,
        "cashOutlayKnown": bool(complete and cash_depth_known),
        "ahPurchaseDepthKnown": False,
        "materials": lines,
    }


def parse_pricetable(text):
    lines = text.splitlines()
    if not lines:
        raise ValueError("price table is empty")
    header = lines[0].split("|")
    if len(header) < 4 or header[0] != "AHL1":
        raise ValueError("unsupported price table header")
    try:
        timestamp = int(header[2])
        row_count = int(header[3])
    except ValueError as exc:
        raise ValueError("invalid price table timestamp or row count") from exc
    market_path = header[1]
    market = market_path.replace("/", ".")
    prices = {}
    malformed_rows = 0
    for line in lines[1:]:
        fields = line.split(":")
        if len(fields) < 9:
            malformed_rows += 1
            continue
        try:
            item_id = int(fields[0])
        except ValueError:
            malformed_rows += 1
            continue

        def maybe_int(raw):
            if not raw:
                return None
            try:
                return int(raw)
            except ValueError:
                return None

        prices[item_id] = {
            "median": maybe_int(fields[1]),
            "minBuyout": maybe_int(fields[2]),
            "quantity": maybe_int(fields[3]),
            "median7d": maybe_int(fields[4]),
            "median30d": maybe_int(fields[5]),
            "low30d": maybe_int(fields[6]),
            "high30d": maybe_int(fields[7]),
            "estimatedSalesPerDayTimes10": maybe_int(fields[8]),
        }
    return {
        "market": market,
        "marketPath": market_path,
        "timestamp": timestamp,
        "rowCountHeader": row_count,
        "parsedRowCount": len(prices),
        "malformedRows": malformed_rows,
        "prices": prices,
    }


def _assessment_warnings(assessment, recipe):
    warnings = []
    acquisition = recipe.get("acquisition")
    evidence = assessment.get("evidence") if isinstance(assessment, dict) else None
    source_checked = (
        isinstance(assessment, dict)
        and assessment.get("status") == "verified_available"
        and assessment.get("sourceVerified") is True
        and isinstance(evidence, str)
        and bool(evidence.strip())
    )
    if (not acquisition or acquisition == "unknown") and not source_checked:
        warnings.append("recipe_source_unknown")
    if not isinstance(assessment, dict):
        warnings.append("conditions_unverified")
        return warnings
    if assessment.get("status") != "verified_available":
        warnings.append("conditions_unverified")
        return warnings
    for flag in ("professionVerified", "skillVerified", "sourceVerified", "bindingVerified"):
        if assessment.get(flag) is not True:
            warnings.append("conditions_unverified")
            break
    assessment_faction = str(assessment.get("faction") or "").lower()
    if assessment_faction not in ("alliance", "both", "neutral"):
        warnings.append("conditions_unverified")
    evidence = assessment.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        warnings.append("conditions_unverified")
    return warnings


def _faction_blocker(recipe, market):
    faction = recipe.get("side", recipe.get("faction"))
    if not faction:
        return None
    if isinstance(faction, list):
        factions = {str(value).lower() for value in faction}
    else:
        factions = {str(faction).lower()}
    market_faction = market.split(".")[-2].lower() if market.count(".") >= 3 else None
    if market_faction in factions or "both" in factions or "neutral" in factions:
        return None
    if "horde" in factions:
        return "faction_mismatch"
    return None


def _manual_cost(reagents, manual_prices):
    if not manual_prices:
        return None, []
    total = 0
    complete = True
    rows = []
    for reagent in reagents:
        item_id = reagent.get("id")
        quantity = _integer(reagent.get("qty"))
        entry = manual_prices.get(str(item_id), manual_prices.get(item_id))
        unit = _integer(entry.get("unitPriceCopper")) if isinstance(entry, dict) else None
        source = entry.get("source") if isinstance(entry, dict) else None
        conditions = entry.get("conditions") if isinstance(entry, dict) else None
        if unit is not None and unit < 0:
            unit = None
        if not isinstance(source, str) or not source.strip() or not isinstance(conditions, str) or not conditions.strip():
            unit = None
        row = {
            "itemId": item_id,
            "name": reagent.get("name"),
            "quantity": quantity,
            "unitPriceCopper": unit,
            "costCopper": quantity * unit if quantity is not None and unit is not None else None,
            "source": source,
            "conditions": conditions,
        }
        rows.append(row)
        if quantity is None or unit is None or unit < 0:
            complete = False
        else:
            total += quantity * unit
    return (total if complete else None), rows


def _audit_metadata(candidate_audit, market, snapshot_at, source=None, error=None):
    summary = candidate_audit.get("summary") if isinstance(candidate_audit, dict) else None
    summary = summary if isinstance(summary, dict) else {}
    audit_market = summary.get("market")
    audit_time = summary.get("marketSnapshotAt")
    market_matches = audit_market == market
    timestamps_match = (
        _as_utc_epoch(audit_time) is not None
        and _as_utc_epoch(audit_time) == _as_utc_epoch(snapshot_at)
    )
    reasons = []
    if error:
        reasons.append("audit_unreadable")
    elif not isinstance(candidate_audit, dict):
        reasons.append("audit_missing")
    elif not market_matches:
        reasons.append("audit_market_mismatch")
    if isinstance(candidate_audit, dict) and not timestamps_match:
        reasons.append("audit_snapshot_mismatch")
    aligned = isinstance(candidate_audit, dict) and market_matches and timestamps_match and not error
    return {
        "status": "APPLIED" if aligned else ("MISSING" if not candidate_audit and not error else "UNVERIFIED"),
        "source": source,
        "market": audit_market,
        "marketSnapshotAt": audit_time,
        "marketMatches": market_matches,
        "snapshotMatches": timestamps_match,
        "appliesToCurrentSnapshot": aligned,
        "auditDate": candidate_audit.get("auditDate") if isinstance(candidate_audit, dict) else None,
        "generatedAt": summary.get("generatedAt"),
        "foreverDbClientBuild": summary.get("foreverDbClientBuild"),
        "foreverDbExtractedAt": summary.get("foreverDbExtractedAt"),
        "ahVendorSellBuildKnown": summary.get("ahVendorSellBuildKnown"),
        "sourceEvidence": candidate_audit.get("sourceEvidence") if isinstance(candidate_audit, dict) else None,
        "candidateCount": len(candidate_audit.get("candidates", [])) if isinstance(candidate_audit, dict) and isinstance(candidate_audit.get("candidates"), list) else 0,
        "reasons": reasons,
    }


def _audit_candidate_index(candidate_audit):
    result = {}
    for candidate in (candidate_audit or {}).get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        spell_id = candidate.get("spellId")
        result_id = candidate.get("resultId")
        if spell_id is None or result_id is None:
            continue
        key = (str(spell_id), str(result_id))
        result[key] = candidate if key not in result else None
    return result


def _legacy_price_evidence(candidate_audit):
    """Extract only item-level ForeverDB prices from the older recipe audit."""
    if not isinstance(candidate_audit, dict):
        return {"schemaVersion": 1, "records": []}
    summary = candidate_audit.get("summary") or {}
    records = []
    for candidate in candidate_audit.get("candidates", []):
        if not isinstance(candidate, dict) or _integer(candidate.get("resultId")) is None:
            continue
        item_id = candidate["resultId"]
        item_url = next((url for url in candidate.get("evidence", [])
                         if isinstance(url, str) and url.rstrip("/").endswith("/item/{}".format(item_id))), None)
        local_item_evidence = [entry for entry in candidate.get("localEvidence", [])
                               if isinstance(entry, dict) and
                               (entry.get("url") == item_url or
                                str(entry.get("localFile", "")).endswith("/{}.html".format(item_id)))]
        records.append({
            "itemId": item_id,
            "sourceType": "foreverdb",
            "source": "ForeverDB item page",
            "unitPriceCopper": _integer(candidate.get("foreverDbVendorSellUnitCopper")),
            "observedAt": summary.get("foreverDbExtractedAt"),
            "clientBuild": summary.get("foreverDbClientBuild"),
            "url": item_url,
            "evidenceSource": candidate_audit.get("sourceEvidence"),
            "auditDate": candidate_audit.get("auditDate"),
            "localEvidence": local_item_evidence,
            "status": "missing" if candidate.get("foreverDbVendorSellUnitCopper") is None else "observed",
        })
    return {
        "schemaVersion": 1,
        "generatedAt": summary.get("generatedAt"),
        "currentClientBuild": None,
        "records": records,
    }


def _record_validity(record, source_type, current_build, now_epoch):
    valid_until = record.get("validUntil")
    expiry_epoch = _as_utc_epoch(valid_until)
    if valid_until and expiry_epoch is None:
        return "invalid_expiry"
    if isinstance(valid_until, str) and len(valid_until) == 10 and expiry_epoch is not None:
        expiry_epoch += 86399
    if valid_until and expiry_epoch is not None and now_epoch is not None and expiry_epoch < now_epoch:
        return "expired"
    if source_type == "in_game" and record.get("appliesToCurrentClient") is not True:
        return "not_confirmed_current"
    record_build = record.get("clientBuild")
    if current_build:
        if record_build and str(current_build) != str(record_build):
            return "build_mismatch"
        return "build_match" if record_build else "build_missing"
    if source_type == "foreverdb":
        return "build_match" if current_build and record_build else "build_unknown"
    if source_type == "in_game":
        return "build_match" if current_build and record_build else "current_build_unknown"
    return "unknown"


def _single_price(records, source_type, *, current_build, now_epoch, reference=False):
    source_records = [record for record in records if record.get("sourceType") == source_type]
    values = []
    visible_values = []
    validity = "missing"
    for record in source_records:
        value = _integer(record.get("unitPriceCopper"))
        state = _record_validity(record, source_type, current_build, now_epoch)
        if value is not None and value >= 0:
            visible_values.append(value)
            usable = state not in ("expired", "invalid_expiry") and (reference or state != "build_mismatch")
            if source_type == "in_game":
                usable = (usable and record.get("appliesToCurrentClient") is True
                          and not (current_build and not record.get("clientBuild")))
            if usable:
                values.append(value)
        if state != "unknown":
            validity = state
    distinct = sorted(set(values))
    if len(distinct) > 1:
        return None, "conflict", validity, sorted(set(visible_values))
    if len(distinct) == 1:
        return distinct[0], "observed", validity, sorted(set(visible_values))
    if source_records and not visible_values:
        return None, "missing", validity, []
    if source_records:
        return None, "unusable", validity, sorted(set(visible_values))
    return None, "missing", "missing", []


def _npc_sell_price_view(item_id, vendor_sell, qty_min, median_cost, low_cost,
                         evidence, item_metadata, market_snapshot_at, generated_at):
    evidence = evidence if isinstance(evidence, dict) else {"records": []}
    records = [record for record in evidence.get("records", [])
               if isinstance(record, dict) and str(record.get("itemId")) == str(item_id)]
    current_build = evidence.get("currentClientBuild")
    now_epoch = _as_utc_epoch(generated_at)
    forever_price, forever_status, forever_validity, forever_seen = _single_price(
        records, "foreverdb", current_build=current_build, now_epoch=now_epoch, reference=True
    )
    game_price, game_status, game_validity, game_seen = _single_price(
        records, "in_game", current_build=current_build, now_epoch=now_epoch
    )
    ah_price = vendor_sell if vendor_sell is not None and vendor_sell >= 0 else None

    def compare(left, right):
        if left is None:
            return "unverified"
        if right is None:
            return "unverified"
        return "match" if left == right else "conflict"

    ah_vs_forever = compare(ah_price, forever_price)
    ah_vs_game = compare(ah_price, game_price)
    forever_vs_game = compare(forever_price, game_price)
    distinct_prices = [price for price in (ah_price, forever_price, game_price) if price is not None]
    internal_conflict = forever_status == "conflict" or game_status == "conflict"
    status = "UNVERIFIED"
    if internal_conflict or (len(distinct_prices) > 1 and len(set(distinct_prices)) > 1):
        status = "CONFLICTED"
    elif len(distinct_prices) >= 2:
        status = "CORROBORATED"

    def income_and_profit(unit_price):
        income = unit_price * qty_min if unit_price is not None and qty_min is not None and qty_min >= 0 else None
        median = income - median_cost if income is not None and median_cost is not None else None
        low = income - low_cost if income is not None and low_cost is not None else None
        return income, median, low

    forever_income, forever_median, forever_low = income_and_profit(forever_price)
    game_income, game_median, game_low = income_and_profit(game_price)
    metadata = item_metadata if isinstance(item_metadata, dict) else {}
    source_url = metadata.get("url") or ("https://api.ahledger.com/v1/items/{}?game=forever".format(item_id)
                                         if item_id is not None else None)
    ah_record = {
        "itemId": item_id,
        "source": "AHledger /v1/items/{itemId}?game=forever",
        "unitPriceCopper": ah_price,
        "observedAt": metadata.get("requestedAt"),
        "copiedAt": metadata.get("snapshotCopiedAt"),
        "clientBuild": None,
        "url": source_url,
        "snapshotFile": metadata.get("snapshotFile"),
        "sha256": metadata.get("sha256"),
        "marketSnapshotAt": market_snapshot_at,
        "cacheHit": metadata.get("cacheHit"),
    }
    forever_records = [record for record in records if record.get("sourceType") == "foreverdb"]
    game_records = [record for record in records if record.get("sourceType") == "in_game"]
    return {
        "itemId": item_id,
        "status": status,
        "ahledger": ah_record,
        "foreverDb": forever_records,
        "inGame": game_records,
        "ahVsForeverDb": ah_vs_forever,
        "ahVsInGame": ah_vs_game,
        "foreverDbVsInGame": forever_vs_game,
        "foreverDbUnitCopper": forever_price,
        "inGameUnitCopper": game_price,
        "foreverDbObservedValuesCopper": forever_seen,
        "inGameObservedValuesCopper": game_seen,
        "foreverDbValidity": forever_validity,
        "inGameValidity": game_validity,
        "foreverDbReferenceIncomeCopper": forever_income,
        "foreverDbReferenceProfitMedianCopper": forever_median,
        "foreverDbReferenceProfitMinBuyoutCopper": forever_low,
        "inGameConfirmedIncomeCopper": game_income,
        "inGameConfirmedProfitMedianCopper": game_median,
        "inGameConfirmedProfitMinBuyoutCopper": game_low,
        "currentClientBuild": current_build,
    }


def _candidate_audit_view(record, metadata, spell_id, result_id, vendor_sell,
                          skill_required, qty_min, qty_max, median_cost, low_cost):
    reasons = list(metadata.get("reasons", []))
    if record is None:
        reasons.append("audit_candidate_not_found")
        return {
            "status": "UNVERIFIED", "recordedStatus": None, "appliesToCurrentSnapshot": False,
            "reasonCodes": sorted(set(reasons)), "npcSellComparison": "unverified",
            "skillComparison": "unverified", "sourceComparison": "unverified",
            "availabilityStatus": "UNVERIFIED", "ahVendorSellUnitCopper": None,
            "foreverDbVendorSellUnitCopper": None, "foreverDbReferenceIncomeCopper": None,
            "foreverDbReferenceProfitMedianCopper": None,
            "foreverDbReferenceProfitMinBuyoutCopper": None,
            "foreverDbSkillRequired": None, "ahSkillRequired": None,
            "recipeSource": None, "access": None, "notes": [], "evidence": [],
            "localEvidence": [],
        }

    recorded_status = record.get("status")
    ah_sell = _integer(record.get("ahVendorSellUnitCopper"))
    forever_sell = _integer(record.get("foreverDbVendorSellUnitCopper"))
    ah_skill = _integer(record.get("ahSkillRequired"))
    forever_skill = _integer(record.get("foreverDbSkillRequired"))
    data_matches = metadata.get("appliesToCurrentSnapshot")
    if data_matches and ah_sell != vendor_sell:
        data_matches = False
        reasons.append("audit_vendor_sell_mismatch")
    if data_matches and ah_skill is not None and ah_skill != skill_required:
        data_matches = False
        reasons.append("audit_skill_input_mismatch")
    if data_matches and record.get("resultQtyMin") is not None and record.get("resultQtyMin") != qty_min:
        data_matches = False
        reasons.append("audit_yield_mismatch")
    if data_matches and record.get("resultQtyMax") is not None and record.get("resultQtyMax") != qty_max:
        data_matches = False
        reasons.append("audit_yield_mismatch")

    comparison = "unverified"
    if data_matches:
        comparison = "missing" if forever_sell is None or ah_sell is None else (
            "match" if forever_sell == ah_sell else "conflict"
        )
        if record.get("npcSellComparison") != comparison:
            data_matches = False
            comparison = "unverified"
            reasons.append("audit_price_comparison_inconsistent")

    if data_matches and recorded_status in ("CORROBORATED", "CONFLICTED", "BLOCKED", "UNVERIFIED"):
        status = recorded_status
    else:
        status = "UNVERIFIED"
        if not reasons:
            reasons.append("audit_candidate_not_applicable")

    skill_comparison = "unverified"
    if data_matches and ah_skill is not None and forever_skill is not None:
        skill_comparison = "match" if ah_skill == forever_skill else "conflict"

    notes = record.get("notes") if isinstance(record.get("notes"), list) else []
    source_conflict = any(
        isinstance(note, str) and any(marker in note for marker in
                                      ("来源字段不一致", "来源与技能冲突", "来源冲突"))
        for note in notes
    )
    source_comparison = "unverified"
    if data_matches:
        source_text = " ".join(str(record.get(key) or "") for key in ("recipeSource", "access", "ahAcquisition"))
        source_unverified = any(marker in source_text.lower() for marker in
                                ("unknown", "classic data", "未知", "未核实", "未确认", "尚不清楚", "尚未"))
        if source_conflict:
            source_comparison = "conflict"
        elif not source_unverified and recorded_status == "CORROBORATED":
            source_comparison = "no_conflict_recorded"
    availability = "BLOCKED" if data_matches and status == "BLOCKED" else "UNVERIFIED"
    if data_matches and availability != "BLOCKED" and (skill_comparison == "conflict" or source_conflict):
        availability = "CONFLICTED"
    if data_matches and availability == "UNVERIFIED" and isinstance(record.get("access"), str) and "游戏内可制造观察" in record["access"]:
        availability = "PRIOR_OBSERVATION"

    income = forever_sell * qty_min if data_matches and forever_sell is not None and qty_min is not None and qty_min >= 0 else None
    reference_median = income - median_cost if income is not None and median_cost is not None else None
    reference_low = income - low_cost if income is not None and low_cost is not None else None
    return {
        "status": status,
        "recordedStatus": recorded_status,
        "appliesToCurrentSnapshot": bool(data_matches),
        "reasonCodes": sorted(set(reasons)),
        "npcSellComparison": comparison,
        "ahVendorSellUnitCopper": ah_sell,
        "foreverDbVendorSellUnitCopper": forever_sell,
        "foreverDbReferenceIncomeCopper": income,
        "foreverDbReferenceProfitMedianCopper": reference_median,
        "foreverDbReferenceProfitMinBuyoutCopper": reference_low,
        "skillComparison": skill_comparison,
        "ahSkillRequired": ah_skill,
        "foreverDbSkillRequired": forever_skill,
        "sourceComparison": source_comparison,
        "availabilityStatus": availability,
        "ahAcquisition": record.get("ahAcquisition"),
        "recipeSource": record.get("recipeSource"),
        "access": record.get("access"),
        "notes": notes,
        "evidence": record.get("evidence") if isinstance(record.get("evidence"), list) else [],
        "localEvidence": record.get("localEvidence") if isinstance(record.get("localEvidence"), list) else [],
    }


def analyze_snapshot(crafting, pricetable_text, items_by_id, generated_at=None,
                     assessments=None, manual_npc_prices=None, candidate_audit=None,
                     candidate_audit_source=None, candidate_audit_error=None,
                     npc_sell_price_evidence=None, item_price_metadata=None,
                     npc_material_purchase_evidence=None, localization=None, craft_count=1,
                     observations=None):
    """Analyze all recipes; missing or misaligned market inputs remain null."""
    if _integer(craft_count) is None or craft_count <= 0:
        raise ValueError("craft_count must be a positive integer")
    assessments = assessments or {}
    observations = observations or {}
    manual_npc_prices = manual_npc_prices or {}
    npc_material_purchase_evidence = (npc_material_purchase_evidence
                                      if isinstance(npc_material_purchase_evidence, dict)
                                      else {"records": []})
    localization = localization if isinstance(localization, dict) else {"entries": []}
    localization_index, localization_conflicts = _localization_index(localization)
    table = parse_pricetable(pricetable_text)
    craft_market = crafting.get("market")
    expected_market = DEFAULT_MARKET
    market_matches = craft_market == expected_market and table["market"] == expected_market
    craft_epoch = _as_utc_epoch(crafting.get("pricesAsOf"))
    snapshot_aligned = craft_epoch is not None and craft_epoch == table["timestamp"]
    alignment = {
        "aligned": bool(market_matches and snapshot_aligned),
        "craftingMarket": craft_market,
        "priceTableMarket": table["market"],
        "expectedMarket": expected_market,
        "craftingPricesAsOf": crafting.get("pricesAsOf"),
        "priceTableTimestamp": table["timestamp"],
        "marketMatches": market_matches,
        "timestampsMatch": snapshot_aligned,
    }
    recipe_ids = [str(((row.get("recipe") or {}).get("spellId"))) for row in crafting.get("recipes", [])
                  if ((row.get("recipe") or {}).get("spellId")) is not None]
    result_item_ids = {str((row.get("result") or {}).get("id")) for row in crafting.get("recipes", [])
                       if ((row.get("result") or {}).get("id")) is not None}
    material_item_ids = {str(reagent.get("id")) for row in crafting.get("recipes", [])
                         for reagent in row.get("reagents", []) if reagent.get("id") is not None}
    localized_recipe_count = sum(("spell", item_id) in localization_index for item_id in recipe_ids)
    localized_result_count = sum(("item", item_id) in localization_index for item_id in result_item_ids)
    localized_material_count = sum(("item", item_id) in localization_index for item_id in material_item_ids)
    localization_coverage = {
        "dataset": localization.get("dataset", {}),
        "recipeNames": {"translated": localized_recipe_count, "total": len(recipe_ids)},
        "resultNames": {"translated": localized_result_count, "total": len(result_item_ids)},
        "materialNames": {"translated": localized_material_count, "total": len(material_item_ids)},
        "conflictedEntries": len(localization_conflicts),
    }
    for name_group in ("recipeNames", "resultNames", "materialNames"):
        counts = localization_coverage[name_group]
        counts["coveragePercent"] = round(counts["translated"] * 100 / counts["total"], 2) if counts["total"] else 0
    audit_metadata = _audit_metadata(candidate_audit, expected_market, crafting.get("pricesAsOf"),
                                     candidate_audit_source, candidate_audit_error)
    audit_index = _audit_candidate_index(candidate_audit) if isinstance(candidate_audit, dict) else {}
    price_evidence = (npc_sell_price_evidence if isinstance(npc_sell_price_evidence, dict)
                      else _legacy_price_evidence(candidate_audit))
    item_price_metadata = item_price_metadata or {}
    generated_at = generated_at or dt.datetime.now(dt.timezone.utc).isoformat()
    recipes = []
    profession_counts = Counter()
    for source in crafting.get("recipes", []):
        recipe = source.get("recipe") or {}
        result = source.get("result") or {}
        reagents = source.get("reagents") or []
        spell_id = recipe.get("spellId")
        assessment = assessments.get(str(spell_id), assessments.get(spell_id))
        user_observation = observations.get(str(spell_id), observations.get(spell_id))
        if not isinstance(user_observation, dict):
            user_observation = None
        result_id = result.get("id")
        output_item = items_by_id.get(str(result_id), items_by_id.get(result_id, {})) or {}
        vendor_sell = _integer(output_item.get("vendorSell"))
        if vendor_sell is not None and vendor_sell < 0:
            vendor_sell = None
        qty_min = _integer(result.get("qtyMin"))
        qty_max = _integer(result.get("qtyMax"))
        yield_qty = qty_min
        income = vendor_sell * yield_qty if vendor_sell is not None and yield_qty is not None and yield_qty >= 0 else None
        recipe_name = recipe.get("name")
        result_name = result.get("name")
        recipe_localized = _localized_name(localization_index, "spell", spell_id, recipe_name)
        result_localized = _localized_name(localization_index, "item", result_id, result_name)
        detailed_reagents = []
        median_cost = 0
        low_cost = 0
        median_complete = alignment["aligned"]
        low_complete = alignment["aligned"]
        for reagent in reagents:
            item_id = reagent.get("id")
            quantity = _integer(reagent.get("qty"))
            price = table["prices"].get(item_id, {}) if alignment["aligned"] else {}
            median_unit = _integer(price.get("median"))
            low_unit = _integer(price.get("minBuyout"))
            if median_unit is not None and median_unit < 0:
                median_unit = None
            if low_unit is not None and low_unit < 0:
                low_unit = None
            median_line = quantity * median_unit if quantity is not None and median_unit is not None else None
            low_line = quantity * low_unit if quantity is not None and low_unit is not None else None
            if quantity is None or quantity < 0 or median_unit is None:
                median_complete = False
            else:
                median_cost += median_line
            if quantity is None or quantity < 0 or low_unit is None:
                low_complete = False
            else:
                low_cost += low_line
            detailed_reagents.append({
                "itemId": item_id,
                "name": reagent.get("name"),
                "nameEnUS": reagent.get("name"),
                "nameZhCN": _localized_name(localization_index, "item", item_id, reagent.get("name"))["zhCN"],
                "nameFallbackId": _localized_name(localization_index, "item", item_id, reagent.get("name"))["fallbackId"],
                "nameTranslationEvidence": _localized_name(localization_index, "item", item_id, reagent.get("name"))["translationEvidence"],
                "quantity": quantity,
                "medianUnitCopper": median_unit,
                "medianCostCopper": median_line,
                "minBuyoutUnitCopper": low_unit,
                "minBuyoutCostCopper": low_line,
                "priceSource": "AHledger pricetable" if alignment["aligned"] else None,
                "marketQuantity": _integer(price.get("quantity")),
                "estimatedSalesPerDayTimes10": _integer(price.get("estimatedSalesPerDayTimes10")),
            })
        if not reagents:
            median_complete = alignment["aligned"]
            low_complete = alignment["aligned"]
        median_cost = median_cost if median_complete else None
        low_cost = low_cost if low_complete else None
        median_profit = income - median_cost if income is not None and median_cost is not None else None
        low_profit = income - low_cost if income is not None and low_cost is not None else None
        manual_cost, manual_rows = _manual_cost(reagents, manual_npc_prices)
        manual_profit = income - manual_cost if income is not None and manual_cost is not None else None
        market_faction = expected_market.split(".")[-2]
        mixed_reference = _hybrid_scenario(
            detailed_reagents, table["prices"], alignment["aligned"],
            npc_material_purchase_evidence, income, craft_count, market_faction, "median",
        )
        mixed_minimum = _hybrid_scenario(
            detailed_reagents, table["prices"], alignment["aligned"],
            npc_material_purchase_evidence, income, craft_count, market_faction, "minBuyout",
        )
        repeatable_reference = _hybrid_scenario(
            detailed_reagents, table["prices"], alignment["aligned"],
            npc_material_purchase_evidence, income, craft_count, market_faction, "median", repeatable=True,
        )
        repeatable_minimum = _hybrid_scenario(
            detailed_reagents, table["prices"], alignment["aligned"],
            npc_material_purchase_evidence, income, craft_count, market_faction, "minBuyout", repeatable=True,
        )
        for reagent_index, reagent_row in enumerate(detailed_reagents):
            reagent_row["mixedReference"] = mixed_reference["materials"][reagent_index]
            reagent_row["mixedMinimum"] = mixed_minimum["materials"][reagent_index]
            reagent_row["repeatableMixedReference"] = repeatable_reference["materials"][reagent_index]
            reagent_row["repeatableMixedMinimum"] = repeatable_minimum["materials"][reagent_index]
        output_market = table["prices"].get(result_id, {}) if alignment["aligned"] else {}
        output_market_view = {
            "medianUnitCopper": _integer(output_market.get("median")),
            "minBuyoutUnitCopper": _integer(output_market.get("minBuyout")),
            "listedQuantity": _integer(output_market.get("quantity")),
            "estimatedSalesPerDayTimes10": _integer(output_market.get("estimatedSalesPerDayTimes10")),
            "estimatedSalesPerDay": (output_market.get("estimatedSalesPerDayTimes10") / 10
                                      if isinstance(output_market.get("estimatedSalesPerDayTimes10"), int)
                                      else None),
            "minimumBuyoutDepthKnown": False,
            "marketSnapshotAt": crafting.get("pricesAsOf") if alignment["aligned"] else None,
        }
        npc_sell_evidence = _npc_sell_price_view(
            result_id, vendor_sell, qty_min, median_cost, low_cost,
            price_evidence, item_price_metadata.get(str(result_id), item_price_metadata.get(result_id)),
            crafting.get("pricesAsOf"), generated_at,
        )
        warnings = _assessment_warnings(assessment, recipe)
        mixed_warnings = []
        mixed_positive = any(
            value is not None and value > 0
            for value in (mixed_reference["profitCopper"], mixed_minimum["profitCopper"])
        )
        selected_mixed_channels = [
            line.get("channel") for scenario in (mixed_reference, mixed_minimum)
            for line in scenario["materials"] if line.get("channel")
        ]
        if any(channel.startswith("ah_") for channel in selected_mixed_channels):
            mixed_warnings.append("mixed_ah_depth_unknown")
        selected_npc_evidence = [
            line.get("selectedNpcEvidence") for scenario in (mixed_reference, mixed_minimum)
            for line in scenario["materials"] if line.get("selectedNpcEvidence")
        ]
        if any(not option.get("usable") for option in selected_npc_evidence):
            mixed_warnings.append("mixed_npc_purchase_reference_only")
        if mixed_positive and _assessment_warnings(assessment, recipe):
            mixed_warnings.append("mixed_recipe_conditions_unverified")
        blockers = []
        faction_blocker = _faction_blocker(recipe, expected_market)
        if faction_blocker:
            blockers.append(faction_blocker)
        status = assessment.get("status") if isinstance(assessment, dict) else None
        assessed_faction = assessment.get("faction") if isinstance(assessment, dict) else None
        if assessed_faction and str(assessed_faction).lower() in ("horde", "opposing", "opponent"):
            blockers.append("faction_mismatch")
        if status == "verified_unavailable":
            blockers.append("recipe_unavailable")
        if not alignment["aligned"]:
            blockers.append("snapshot_misaligned")
        evidence_profits = (
            npc_sell_evidence["foreverDbReferenceProfitMedianCopper"],
            npc_sell_evidence["foreverDbReferenceProfitMinBuyoutCopper"],
            npc_sell_evidence["inGameConfirmedProfitMedianCopper"],
            npc_sell_evidence["inGameConfirmedProfitMinBuyoutCopper"],
        )
        is_positive = (
            (median_profit is not None and median_profit > 0)
            or (low_profit is not None and low_profit > 0)
            or any(value is not None and value > 0 for value in evidence_profits)
        )
        audit_record = audit_index.get((str(spell_id), str(result_id)))
        audit_view = None
        if is_positive or mixed_positive or audit_record is not None:
            audit_view = _candidate_audit_view(
                audit_record, audit_metadata, spell_id, result_id, vendor_sell,
                recipe.get("skillRequired"), qty_min, qty_max, median_cost, low_cost,
            )
            if audit_view["status"] == "UNVERIFIED":
                warnings.append("candidate_audit_unverified")
            if audit_view["npcSellComparison"] == "conflict":
                warnings.append("audit_npc_sell_conflict")
            elif audit_view["npcSellComparison"] in ("missing", "unverified"):
                warnings.append("audit_npc_sell_unverified")
            if audit_view["skillComparison"] == "conflict":
                warnings.append("audit_skill_conflict")
            if audit_view["sourceComparison"] == "conflict":
                warnings.append("audit_source_conflict")
            elif audit_view["sourceComparison"] == "unverified":
                warnings.append("audit_source_unverified")
            if audit_view["availabilityStatus"] == "BLOCKED":
                blockers.append("recipe_unavailable")
        if npc_sell_evidence["status"] == "CONFLICTED":
            warnings.append("npc_sell_price_conflict")
        elif npc_sell_evidence["status"] == "UNVERIFIED":
            warnings.append("npc_sell_price_unverified")
        if any(npc_sell_evidence.get(key) in ("build_mismatch", "build_missing", "expired", "invalid_expiry")
               for key in ("foreverDbValidity", "inGameValidity")):
            warnings.append("npc_sell_price_evidence_stale")
        source_or_price_conflict = (
            npc_sell_evidence["status"] == "CONFLICTED"
            or (audit_view is not None and audit_view.get("sourceComparison") == "conflict")
            or (audit_view is not None and audit_view.get("skillComparison") == "conflict")
        )
        mixed_opportunity_eligible = mixed_positive and not source_or_price_conflict
        if (median_profit is None or low_profit is None) and not mixed_opportunity_eligible:
            blockers.append("missing_price_or_vendor_sell")
        if not is_positive and not mixed_opportunity_eligible and not blockers:
            blockers.append("mixed_evidence_conflict" if mixed_positive else "no_positive_margin")
        if blockers:
            group = "C"
        elif median_profit is not None and low_profit is not None and median_profit > 0 and low_profit > 0:
            flags_verified = isinstance(assessment, dict) and assessment.get("status") == "verified_available" and all(
                assessment.get(flag) is True for flag in
                ("professionVerified", "skillVerified", "sourceVerified", "bindingVerified")
            ) and str(assessment.get("faction") or "").lower() in ("alliance", "both", "neutral") and bool(assessment.get("evidence"))
            audit_supports_priority = (
                audit_view is not None
                and audit_view["appliesToCurrentSnapshot"]
                and audit_view["status"] == "CORROBORATED"
                and audit_view["npcSellComparison"] == "match"
                and audit_view["skillComparison"] != "conflict"
                and audit_view["sourceComparison"] != "conflict"
                and npc_sell_evidence["status"] != "CONFLICTED"
                and npc_sell_evidence["foreverDbValidity"] != "build_mismatch"
            )
            group = "A" if flags_verified and audit_supports_priority and not warnings else "B"
        else:
            group = "B"
        if qty_min is not None and qty_max is not None and qty_min != qty_max:
            warnings.append("variable_yield_uses_minimum")
        elif qty_min is None or qty_max is None:
            warnings.append("yield_incomplete")
        verified_assessment = (
            isinstance(assessment, dict)
            and assessment.get("status") == "verified_available"
            and all(assessment.get(flag) is True for flag in
                    ("professionVerified", "skillVerified", "sourceVerified", "bindingVerified"))
            and str(assessment.get("faction") or "").lower() in ("alliance", "both", "neutral")
            and bool(assessment.get("evidence"))
        )
        all_npc_repeatable = all(
            line.get("channel") == "npc"
            and (line.get("selectedNpcEvidence") or {}).get("usable") is True
            and (line.get("selectedNpcEvidence") or {}).get("stockType") == "unlimited"
            for line in mixed_reference["materials"] + mixed_minimum["materials"]
        ) and bool(mixed_reference["materials"])
        material_sources_current = all(
            (line.get("selectedNpcEvidence") or {}).get("usable") is True
            and (line.get("selectedNpcEvidence") or {}).get("evidenceLevel") == "current_in_game"
            and (line.get("selectedNpcEvidence") or {}).get("appliesToCurrentClient") is True
            for line in mixed_reference["materials"] + mixed_minimum["materials"]
        )
        audit_current = (
            audit_view is not None and audit_view.get("appliesToCurrentSnapshot")
            and audit_view.get("status") == "CORROBORATED"
            and audit_view.get("skillComparison") != "conflict"
            and audit_view.get("sourceComparison") not in ("conflict", "unverified")
        )
        current_npc_sale = (
            npc_sell_evidence.get("inGameUnitCopper") is not None
            and npc_sell_evidence.get("inGameValidity") in ("build_match", "current_build_unknown")
        )
        mixed_executable = (
            mixed_opportunity_eligible and verified_assessment and all_npc_repeatable
            and material_sources_current and current_npc_sale and audit_current
        )
        profession = recipe.get("profession")
        profession_counts[profession or "unknown"] += 1
        recipes.append({
            "spellId": spell_id,
            "recipeName": recipe_name,
            "recipeNameEnUS": recipe_localized["enUS"],
            "recipeNameZhCN": recipe_localized["zhCN"],
            "recipeNameFallbackId": recipe_localized["fallbackId"],
            "recipeNameTranslationEvidence": recipe_localized["translationEvidence"],
            "profession": profession,
            "skillRequired": recipe.get("skillRequired"),
            "acquisition": recipe.get("acquisition"),
            "assessmentEvidence": assessment.get("evidence") if isinstance(assessment, dict) else None,
            "userObservation": user_observation,
            "side": recipe.get("side", recipe.get("faction")),
            "resultId": result_id,
            "resultName": result_name,
            "resultNameEnUS": result_localized["enUS"],
            "resultNameZhCN": result_localized["zhCN"],
            "resultNameFallbackId": result_localized["fallbackId"],
            "resultNameTranslationEvidence": result_localized["translationEvidence"],
            "resultQtyMin": qty_min,
            "resultQtyMax": qty_max,
            "vendorSellUnitCopper": vendor_sell,
            "vendorSellSource": output_item.get("source", "AHledger /v1/items/{id}?game=forever") if vendor_sell is not None else None,
            "npcIncomeCopper": income,
            "materialCostMedianCopper": median_cost,
            "profitMedianCopper": median_profit,
            "materialCostMinBuyoutCopper": low_cost,
            "profitMinBuyoutCopper": low_profit,
            "manualNpcMaterialCostCopper": manual_cost,
            "manualNpcMaterialProfitCopper": manual_profit,
            "manualNpcMaterialDetails": manual_rows,
            "mixedReference": mixed_reference,
            "mixedMinimum": mixed_minimum,
            "repeatableMixedReference": repeatable_reference,
            "repeatableMixedMinimum": repeatable_minimum,
            "mixedOpportunityEligible": mixed_opportunity_eligible,
            "mixedExecutableOpportunity": mixed_executable,
            "mixedWarnings": sorted(set(mixed_warnings)),
            "outputAuctionMarket": output_market_view,
            "reagents": detailed_reagents,
            "group": group,
            "candidateAudit": audit_view,
            "npcSellPriceEvidence": npc_sell_evidence,
            "warnings": sorted(set(warnings)),
            "blockers": blockers,
        })
    def sort_margin(*values):
        return max((value for value in values if isinstance(value, (int, float))), default=-10**18)

    recipes.sort(key=lambda row: (
        row["group"],
        0 if row.get("userObservation") else 1,
        1 if (row.get("candidateAudit") or {}).get("recordedStatus") == "CONFLICTED"
        and not (row.get("candidateAudit") or {}).get("appliesToCurrentSnapshot") else 0,
        -sort_margin(row["profitMedianCopper"], row["mixedReference"].get("profitPerCraftCopper")),
        -sort_margin(row["profitMinBuyoutCopper"], row["mixedMinimum"].get("profitPerCraftCopper")),
        str(row["recipeName"] or ""),
    ))
    group_counts = Counter(row["group"] for row in recipes)
    computable_both = sum(
        row["profitMedianCopper"] is not None and row["profitMinBuyoutCopper"] is not None
        for row in recipes
    )
    computable_median = sum(row["profitMedianCopper"] is not None for row in recipes)
    computable_min_buyout = sum(row["profitMinBuyoutCopper"] is not None for row in recipes)
    positive_any = sum(
        (row["profitMedianCopper"] is not None and row["profitMedianCopper"] > 0)
        or (row["profitMinBuyoutCopper"] is not None and row["profitMinBuyoutCopper"] > 0)
        or (row["npcSellPriceEvidence"]["foreverDbReferenceProfitMedianCopper"] is not None
            and row["npcSellPriceEvidence"]["foreverDbReferenceProfitMedianCopper"] > 0)
        or (row["npcSellPriceEvidence"]["foreverDbReferenceProfitMinBuyoutCopper"] is not None
            and row["npcSellPriceEvidence"]["foreverDbReferenceProfitMinBuyoutCopper"] > 0)
        or (row["npcSellPriceEvidence"]["inGameConfirmedProfitMedianCopper"] is not None
            and row["npcSellPriceEvidence"]["inGameConfirmedProfitMedianCopper"] > 0)
        or (row["npcSellPriceEvidence"]["inGameConfirmedProfitMinBuyoutCopper"] is not None
            and row["npcSellPriceEvidence"]["inGameConfirmedProfitMinBuyoutCopper"] > 0)
        for row in recipes
    )
    missing = len(recipes) - computable_both
    newly_calculable_hybrid = sum(
        (row["mixedReference"]["profitCopper"] is not None and row["profitMedianCopper"] is None)
        or (row["mixedMinimum"]["profitCopper"] is not None and row["profitMinBuyoutCopper"] is None)
        for row in recipes
    )
    mixed_positive_count = sum(
        row["mixedOpportunityEligible"] and (
            (row["mixedReference"]["profitCopper"] is not None and row["mixedReference"]["profitCopper"] > 0)
            or (row["mixedMinimum"]["profitCopper"] is not None and row["mixedMinimum"]["profitCopper"] > 0)
        ) for row in recipes
    )
    ah_positive = lambda row: (
        (row["profitMedianCopper"] is not None and row["profitMedianCopper"] > 0)
        or (row["profitMinBuyoutCopper"] is not None and row["profitMinBuyoutCopper"] > 0)
    )
    new_mixed_positive_count = sum(
        row["mixedOpportunityEligible"] and not ah_positive(row) and (
            (row["mixedReference"]["profitCopper"] is not None and row["mixedReference"]["profitCopper"] > 0)
            or (row["mixedMinimum"]["profitCopper"] is not None and row["mixedMinimum"]["profitCopper"] > 0)
        ) for row in recipes
    )
    required_material_ids = {str(reagent.get("itemId")) for row in recipes for reagent in row["reagents"]
                             if reagent.get("itemId") is not None}
    npc_reference_covered_material_ids = {
        str(reagent["itemId"]) for row in recipes for reagent in row["reagents"]
        if any(option.get("referenceUsable") for option in reagent["mixedReference"].get("npcOptions", []))
    }
    npc_executable_covered_material_ids = {
        str(reagent["itemId"]) for row in recipes for reagent in row["reagents"]
        if any(option.get("usable") for option in reagent["mixedReference"].get("npcOptions", []))
    }
    all_purchase_records = npc_material_purchase_evidence.get("records", [])
    if isinstance(all_purchase_records, dict):
        all_purchase_records = [record for values in all_purchase_records.values()
                                for record in (values if isinstance(values, list) else [values])]
    all_purchase_records = all_purchase_records if isinstance(all_purchase_records, list) else []
    plugin_purchase_records = [record for record in all_purchase_records
                               if isinstance(record, dict) and record.get("sourceSite") == "LibItemDB"]
    plugin_candidate_ids = {str(record.get("itemId")) for record in plugin_purchase_records
                            if record.get("itemId") is not None}
    package_evidence_records = [record for record in all_purchase_records
                                if isinstance(record, dict)
                                and str(record.get("itemId")) in plugin_candidate_ids
                                and record.get("sourceSite") != "LibItemDB"
                                and _integer(record.get("packPriceCopper")) is not None
                                and _integer(record.get("packQuantity")) is not None
                                and record.get("packPriceCopper") >= 0
                                and record.get("packQuantity") > 0]
    package_evidence_ids = {str(record.get("itemId")) for record in package_evidence_records}
    current_game_package_ids = {str(record.get("itemId")) for record in package_evidence_records
                                if record.get("evidenceLevel") == "current_in_game"}
    purchase_evidence_stats = {
        "currentClientBuild": npc_material_purchase_evidence.get("currentClientBuild"),
        "recordCount": len([record for record in all_purchase_records if isinstance(record, dict)]),
        "classicReferenceRecordCount": sum(
            isinstance(record, dict) and record.get("evidenceLevel") == "classic_data"
            for record in all_purchase_records
        ),
        "coveredMaterialCount": len(npc_executable_covered_material_ids),
        "requiredMaterialCount": len(required_material_ids),
        "coveragePercent": round(len(npc_executable_covered_material_ids) * 100 / len(required_material_ids), 2)
        if required_material_ids else 0,
        "referenceCoveredMaterialCount": len(npc_reference_covered_material_ids),
        "referenceCoveragePercent": round(len(npc_reference_covered_material_ids) * 100 / len(required_material_ids), 2)
        if required_material_ids else 0,
        "libItemDBBasePriceCandidateCount": len(plugin_candidate_ids),
        "libItemDBBuyCountKnownCandidateCount": sum(
            _integer(record.get("packQuantity")) is not None and record.get("packQuantity") > 0
            for record in plugin_purchase_records
        ),
        "candidateItemsWithPackQuantityEvidence": len(package_evidence_ids),
        "candidateItemsWithCurrentInGamePackEvidence": len(current_game_package_ids),
    }
    return {
        "market": expected_market,
        "marketSnapshotAt": crafting.get("pricesAsOf"),
        "priceTableTimestamp": table["timestamp"],
        "generatedAt": generated_at,
        "snapshotAlignment": alignment,
        "recipeCount": len(recipes),
        "professionCounts": dict(sorted(profession_counts.items())),
        "calculableBothScenariosCount": computable_both,
        "calculableMedianCount": computable_median,
        "calculableMinBuyoutCount": computable_min_buyout,
        "positiveAnyScenarioCount": positive_any,
        "priorityCount": group_counts.get("A", 0),
        "potentialCount": group_counts.get("B", 0),
        "blockedOrNonPositiveCount": group_counts.get("C", 0),
        "missingPriceOrVendorSellCount": missing,
        "craftCount": craft_count,
        "newlyCalculableHybridCount": newly_calculable_hybrid,
        "mixedPositiveCandidateCount": mixed_positive_count,
        "newMixedPositiveCandidateCount": new_mixed_positive_count,
        "mixedExecutableCandidateCount": sum(row["mixedExecutableOpportunity"] for row in recipes),
        "userReportedObservationCount": sum(bool(row.get("userObservation")) for row in recipes),
        "npcMaterialPurchaseEvidence": purchase_evidence_stats,
        "localizationCoverage": localization_coverage,
        "priceTableRowCountHeader": table["rowCountHeader"],
        "priceTableParsedRowCount": table["parsedRowCount"],
        "priceTableMalformedRows": table["malformedRows"],
        "minimumBuyoutDepthAvailable": False,
        "vendorSellBuildKnown": False,
        "candidateAudit": audit_metadata,
        "npcSellPriceEvidenceCounts": {
            "conflicted": sum(row["npcSellPriceEvidence"]["status"] == "CONFLICTED" for row in recipes),
            "corroborated": sum(row["npcSellPriceEvidence"]["status"] == "CORROBORATED" for row in recipes),
            "unverified": sum(row["npcSellPriceEvidence"]["status"] == "UNVERIFIED" for row in recipes),
            "gamePriceConfirmed": sum(row["npcSellPriceEvidence"]["inGameUnitCopper"] is not None for row in recipes),
        },
        "recipes": recipes,
    }


def load_items_from_directory(directory):
    """Read exact item response JSON files saved by the snapshot fetcher."""
    from pathlib import Path

    items = {}
    for path in Path(directory).glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(item, dict) and _integer(item.get("id")) is not None:
                items[str(item["id"])] = item
        except (OSError, ValueError):
            continue
    return items
