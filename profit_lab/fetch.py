"""Read-only AHledger snapshot acquisition and persistent item cache."""

import datetime as dt
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from .analysis import DEFAULT_MARKET, analyze_snapshot
from .report import render_html


API_ROOT = "https://api.ahledger.com"
CACHE_MAX_AGE = dt.timedelta(days=7)
MIN_REQUEST_INTERVAL_SECONDS = 1.02
USER_AGENT = "WoW-Trade-Lab-read-only-prototype/0.1"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _iso(value=None):
    return (value or _now()).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except ValueError:
        return None


def _safe_headers(headers):
    allowed = {
        "date", "content-type", "content-length", "age", "cache-control", "etag",
        "last-modified", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset",
        "retry-after", "cf-cache-status", "x-vercel-cache", "x-do-orig-status",
    }
    return {key: value for key, value in headers.items() if key.lower() in allowed}


class _RateLimiter:
    def __init__(self, interval=MIN_REQUEST_INTERVAL_SECONDS):
        self.interval = interval
        self.last_request = None

    def wait(self):
        if self.last_request is not None:
            remaining = self.interval - (time.monotonic() - self.last_request)
            if remaining > 0:
                time.sleep(remaining)
        self.last_request = time.monotonic()


def _retry_delay(headers, attempt):
    retry_after = headers.get("Retry-After") if headers else None
    if retry_after:
        try:
            return max(1.0, min(float(retry_after), 60.0))
        except ValueError:
            try:
                parsed = dt.datetime.strptime(retry_after, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=dt.timezone.utc)
                return max(1.0, min((parsed - _now()).total_seconds(), 60.0))
            except ValueError:
                pass
    return min(2 ** (attempt - 1), 8)


def _get(url, limiter, attempts=3):
    history = []
    for attempt in range(1, attempts + 1):
        limiter.wait()
        requested_at = _iso()
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/plain"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                body = response.read()
                headers = _safe_headers(response.headers)
                history.append({"attempt": attempt, "status": response.status, "headers": headers})
                return {
                    "url": url,
                    "requestedAt": requested_at,
                    "httpStatus": response.status,
                    "responseHeaders": headers,
                    "attempts": history,
                    "body": body,
                }
        except urllib.error.HTTPError as error:
            headers = _safe_headers(error.headers or {})
            history.append({"attempt": attempt, "status": error.code, "headers": headers})
            if error.code not in RETRYABLE_STATUS or attempt == attempts:
                return {
                    "url": url,
                    "requestedAt": requested_at,
                    "httpStatus": error.code,
                    "responseHeaders": headers,
                    "attempts": history,
                    "error": "HTTP {}".format(error.code),
                }
            time.sleep(_retry_delay(headers, attempt))
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            history.append({"attempt": attempt, "error": str(error)})
            if attempt == attempts:
                return {
                    "url": url,
                    "requestedAt": requested_at,
                    "httpStatus": None,
                    "responseHeaders": {},
                    "attempts": history,
                    "error": str(error),
                }
            time.sleep(min(2 ** (attempt - 1), 8))
    raise RuntimeError("unreachable request retry state")


def _write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def _entry(metadata, body, relative_path, **extra):
    return {
        "url": metadata["url"],
        "requestedAt": metadata["requestedAt"],
        "httpStatus": metadata.get("httpStatus"),
        "responseHeaders": metadata.get("responseHeaders", {}),
        "attempts": metadata.get("attempts", []),
        "bytes": len(body) if body is not None else 0,
        "sha256": hashlib.sha256(body).hexdigest() if body is not None else None,
        "snapshotFile": relative_path,
        **extra,
        **({"error": metadata["error"]} if metadata.get("error") else {}),
    }


def _seed_legacy_cache(cache_dir, wanted_ids, legacy_file):
    legacy_file = Path(legacy_file)
    if not legacy_file.is_file():
        return 0
    found = 0
    with legacy_file.open(encoding="utf-8") as source:
        for line in source:
            try:
                row = json.loads(line)
                item_id = int(row["id"])
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
            if item_id not in wanted_ids or row.get("httpStatus") not in (200, "200"):
                continue
            cache_file = cache_dir / "{}.json".format(item_id)
            if cache_file.exists():
                continue
            body = row.get("body")
            if not isinstance(body, str):
                continue
            try:
                item = json.loads(body)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict) or item.get("id") != item_id:
                continue
            cache = {
                "itemId": item_id,
                "url": row.get("url") or "{}/v1/items/{}?game=forever".format(API_ROOT, item_id),
                "requestedAt": row.get("requestedAt"),
                "httpStatus": 200,
                "responseHeaders": _safe_headers(row.get("headers") or {}),
                "body": body,
                "cacheOrigin": str(legacy_file),
            }
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            found += 1
    return found


def _load_manual_inputs(root, snapshot_dir):
    source_file = root / "manual_inputs.json"
    if source_file.is_file():
        raw = source_file.read_bytes()
        data = json.loads(raw.decode("utf-8"))
        source = str(source_file)
    else:
        data = {"schemaVersion": 1, "npcMaterialPrices": {}, "recipeAssessments": {},
                "npcSellPriceEvidence": {}}
        raw = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        source = "built-in empty manual inputs"
    _write(snapshot_dir / "manual_inputs.json", raw)
    return data, {"source": source, "snapshotFile": "manual_inputs.json", "sha256": hashlib.sha256(raw).hexdigest()}


def _snapshot_npc_material_evidence(manual_inputs):
    source = manual_inputs.get("npcMaterialPurchaseEvidence", {}) if isinstance(manual_inputs, dict) else {}
    if isinstance(source, list):
        records = source
        current_build = None
        dataset = {}
    elif isinstance(source, dict):
        records = source.get("records", [])
        current_build = source.get("currentClientBuild")
        dataset = source.get("dataset", {})
        if isinstance(records, dict):
            flattened = []
            for item_id, values in records.items():
                for value in values if isinstance(values, list) else [values]:
                    if isinstance(value, dict):
                        flattened.append({"itemId": value.get("itemId", item_id), **value})
            records = flattened
    else:
        records, current_build, dataset = [], None, {}
    return {
        "schemaVersion": 1,
        "dataset": dataset if isinstance(dataset, dict) else {},
        "currentClientBuild": current_build,
        "records": [record for record in records if isinstance(record, dict)] if isinstance(records, list) else [],
    }


def _snapshot_localization(manual_inputs):
    source = manual_inputs.get("localization", {}) if isinstance(manual_inputs, dict) else {}
    if not isinstance(source, dict):
        source = {}
    entries = source.get("entries", [])
    return {
        "schemaVersion": 1,
        "dataset": source.get("dataset", {}) if isinstance(source.get("dataset"), dict) else {},
        "entries": [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else [],
    }


def _write_snapshot_static_evidence(snapshot_dir, manual_inputs, manifest):
    purchase_evidence = _snapshot_npc_material_evidence(manual_inputs)
    purchase_raw = (json.dumps(purchase_evidence, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _write(snapshot_dir / "npc_material_purchase_evidence.json", purchase_raw)
    manifest["npcMaterialPurchaseEvidence"] = {
        "snapshotFile": "npc_material_purchase_evidence.json",
        "sha256": hashlib.sha256(purchase_raw).hexdigest(),
        "recordCount": len(purchase_evidence["records"]),
        "currentClientBuild": purchase_evidence["currentClientBuild"],
    }
    localization = _snapshot_localization(manual_inputs)
    localization_raw = (json.dumps(localization, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _write(snapshot_dir / "localization.json", localization_raw)
    manifest["localization"] = {
        "snapshotFile": "localization.json",
        "sha256": hashlib.sha256(localization_raw).hexdigest(),
        "dataset": localization["dataset"],
        "entryCount": len(localization["entries"]),
    }
    _write(snapshot_dir / "source_manifest.json",
           (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return manifest


def _build_npc_sell_price_evidence(candidate_audit, audit_source, manual_inputs):
    """Copy static NPC sell-price evidence into a snapshot-ready, item-keyed file."""
    summary = candidate_audit.get("summary", {}) if isinstance(candidate_audit, dict) else {}
    records = []
    candidates = candidate_audit.get("candidates", []) if isinstance(candidate_audit, dict) else []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        try:
            item_id = int(candidate.get("resultId"))
        except (TypeError, ValueError):
            continue
        price = candidate.get("foreverDbVendorSellUnitCopper")
        price = price if isinstance(price, int) and not isinstance(price, bool) and price >= 0 else None
        item_url = next((url for url in candidate.get("evidence", [])
                         if isinstance(url, str) and url.rstrip("/").endswith("/item/{}".format(item_id))), None)
        local_evidence = [entry for entry in candidate.get("localEvidence", [])
                          if isinstance(entry, dict) and
                          (entry.get("url") == item_url or
                           str(entry.get("localFile", "")).endswith("/{}.html".format(item_id)))]
        records.append({
            "itemId": item_id,
            "sourceType": "foreverdb",
            "source": "ForeverDB item page",
            "unitPriceCopper": price,
            "observedAt": summary.get("foreverDbExtractedAt"),
            "clientBuild": summary.get("foreverDbClientBuild"),
            "url": item_url,
            "evidenceSource": audit_source,
            "auditDate": candidate_audit.get("auditDate"),
            "localEvidence": local_evidence,
            "status": "observed" if price is not None else "missing",
        })

    manual = manual_inputs if isinstance(manual_inputs, dict) else {}
    manual_records = manual.get("npcSellPriceEvidence", {})
    if isinstance(manual_records, dict):
        for item_key, value in manual_records.items():
            values = value if isinstance(value, list) else [value]
            for record in values:
                if not isinstance(record, dict):
                    continue
                try:
                    item_id = int(record.get("itemId", item_key))
                except (TypeError, ValueError):
                    continue
                unit_price = record.get("unitPriceCopper")
                if unit_price is not None and (not isinstance(unit_price, int) or isinstance(unit_price, bool) or unit_price < 0):
                    unit_price = None
                records.append({
                    **record,
                    "itemId": item_id,
                    "sourceType": record.get("sourceType", "in_game"),
                    "source": record.get("source", "游戏内人工确认"),
                    "unitPriceCopper": unit_price,
                })
    return {
        "schemaVersion": 1,
        "generatedAt": _iso(),
        "currentClientBuild": manual.get("currentClientBuild"),
        "evidenceSource": {
            "foreverDbAudit": audit_source if isinstance(candidate_audit, dict) else None,
            "foreverDbBuild": summary.get("foreverDbClientBuild"),
            "foreverDbExtractedAt": summary.get("foreverDbExtractedAt"),
            "manualInputsSnapshot": "manual_inputs.json",
        },
        "records": records,
    }


def _analyze_saved_snapshot(snapshot_dir, manual_inputs=None, persist_npc_sell_evidence=False, craft_count=1):
    snapshot_dir = Path(snapshot_dir)
    root = snapshot_dir.parent.parent
    raw_dir = snapshot_dir / "raw"
    crafting = json.loads((raw_dir / "crafting.json").read_text(encoding="utf-8"))
    price_text = (raw_dir / "pricetable.txt").read_text(encoding="utf-8")
    items = {}
    item_dir = raw_dir / "items"
    if item_dir.exists():
        for path in item_dir.glob("*.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(item, dict) and isinstance(item.get("id"), int):
                    items[str(item["id"])] = item
            except (OSError, json.JSONDecodeError):
                continue
    manifest_path = snapshot_dir / "source_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    item_price_metadata = {
        str(entry.get("itemId")): entry for entry in manifest.get("entries", [])
        if isinstance(entry, dict) and entry.get("itemId") is not None
    }
    manual_inputs = manual_inputs if manual_inputs is not None else json.loads(
        (snapshot_dir / "manual_inputs.json").read_text(encoding="utf-8")
    )
    purchase_path = snapshot_dir / "npc_material_purchase_evidence.json"
    localization_path = snapshot_dir / "localization.json"
    try:
        npc_material_purchase_evidence = json.loads(purchase_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        npc_material_purchase_evidence = _snapshot_npc_material_evidence(manual_inputs)
    try:
        localization = json.loads(localization_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        localization = _snapshot_localization(manual_inputs)
    audit_path = root / "audits" / "mvp1_1_20261021" / "audit.json"
    candidate_audit = None
    candidate_audit_error = None
    if audit_path.is_file():
        try:
            candidate_audit = json.loads(audit_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            candidate_audit_error = str(error)
    evidence_path = snapshot_dir / "npc_sell_price_evidence.json"
    if evidence_path.is_file():
        try:
            npc_sell_price_evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            npc_sell_price_evidence = _build_npc_sell_price_evidence(
                candidate_audit, str(audit_path), manual_inputs
            )
    else:
        npc_sell_price_evidence = _build_npc_sell_price_evidence(
            candidate_audit, str(audit_path), manual_inputs
        )
        if persist_npc_sell_evidence:
            raw_evidence = (json.dumps(npc_sell_price_evidence, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            _write(evidence_path, raw_evidence)
            manifest["npcSellPriceEvidence"] = {
                "snapshotFile": "npc_sell_price_evidence.json",
                "sha256": hashlib.sha256(raw_evidence).hexdigest(),
                "recordCount": len(npc_sell_price_evidence.get("records", [])),
                "currentClientBuild": npc_sell_price_evidence.get("currentClientBuild"),
            }
            _write(manifest_path, (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    result = analyze_snapshot(
        crafting,
        price_text,
        items,
        generated_at=_iso(),
        assessments=manual_inputs.get("recipeAssessments", {}),
        manual_npc_prices=manual_inputs.get("npcMaterialPrices", {}),
        candidate_audit=candidate_audit,
        candidate_audit_source=str(audit_path),
        candidate_audit_error=candidate_audit_error,
        npc_sell_price_evidence=npc_sell_price_evidence,
        item_price_metadata=item_price_metadata,
        npc_material_purchase_evidence=npc_material_purchase_evidence,
        localization=localization,
        craft_count=craft_count,
        observations=manual_inputs.get("recipeObservations", {}),
    )
    (snapshot_dir / "analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (snapshot_dir / "report.html").write_text(render_html(result), encoding="utf-8")
    return result


def update(root=".profit-lab", market=DEFAULT_MARKET, legacy_cache=None, craft_count=1):
    """Fetch one market snapshot, then save raw inputs and offline outputs."""
    if market != DEFAULT_MARKET:
        raise ValueError("this prototype is fixed to {}".format(DEFAULT_MARKET))
    root = Path(root)
    cache_dir = root / "item-cache"
    timestamp = _now().strftime("%Y%m%dT%H%M%S%fZ")
    snapshot_dir = root / "snapshots" / timestamp
    raw_dir = snapshot_dir / "raw"
    (raw_dir / "items").mkdir(parents=True, exist_ok=False)
    limiter = _RateLimiter()
    manifest = {
        "schemaVersion": 1,
        "market": market,
        "generatedAt": _iso(),
        "entries": [],
    }

    path_market = market.replace(".", "/")
    crafting_url = "{}/v1/crafting/{}?all=1&limit=3000".format(API_ROOT, market)
    crafting_meta = _get(crafting_url, limiter)
    if crafting_meta.get("httpStatus") != 200:
        raise RuntimeError("crafting request failed: {}".format(crafting_meta.get("error")))
    _write(raw_dir / "crafting.json", crafting_meta["body"])
    manifest["entries"].append(_entry(crafting_meta, crafting_meta["body"], "raw/crafting.json"))
    crafting = json.loads(crafting_meta["body"].decode("utf-8"))
    recipes = crafting.get("recipes")
    if not isinstance(recipes, list):
        raise ValueError("crafting response does not contain a recipes array")

    table_url = "{}/v1/pricetable/{}".format(API_ROOT, market)
    table_meta = _get(table_url, limiter)
    if table_meta.get("httpStatus") != 200:
        raise RuntimeError("price table request failed: {}".format(table_meta.get("error")))
    _write(raw_dir / "pricetable.txt", table_meta["body"])
    manifest["entries"].append(_entry(table_meta, table_meta["body"], "raw/pricetable.txt"))
    table_text = table_meta["body"].decode("utf-8")
    table_header = table_text.splitlines()[0].split("|") if table_text.splitlines() else []
    if len(table_header) >= 3:
        manifest["entries"][-1]["dataTimestamp"] = int(table_header[2])
    manifest["entries"][0]["dataTimestamp"] = crafting.get("pricesAsOf")

    wanted_ids = {int(row["result"]["id"]) for row in recipes if row.get("result", {}).get("id") is not None}
    cache_dir.mkdir(parents=True, exist_ok=True)
    seed_path = Path(legacy_cache) if legacy_cache is not None else Path(".validation-round2/raw/item_universe_responses.jsonl")
    seeded = _seed_legacy_cache(cache_dir, wanted_ids, seed_path)
    item_values = {}
    item_entries = []
    fetched_items = 0
    cache_hits = 0
    for item_id in sorted(wanted_ids):
        cache_path = cache_dir / "{}.json".format(item_id)
        cached = None
        used_cache = False
        if cache_path.is_file():
            try:
                candidate = json.loads(cache_path.read_text(encoding="utf-8"))
                requested_at = _parse_time(candidate.get("requestedAt"))
                body = candidate.get("body")
                item = json.loads(body) if isinstance(body, str) else None
                if (candidate.get("httpStatus") == 200 and candidate.get("itemId") == item_id
                        and isinstance(item, dict) and item.get("id") == item_id
                        and requested_at is not None and _now() - requested_at <= CACHE_MAX_AGE):
                    cached = candidate
            except (OSError, ValueError, json.JSONDecodeError):
                cached = None
        if cached is None:
            url = "{}/v1/items/{}?game=forever".format(API_ROOT, item_id)
            response = _get(url, limiter)
            body = response.get("body")
            if response.get("httpStatus") == 200 and body is not None:
                try:
                    item = json.loads(body.decode("utf-8"))
                    if not isinstance(item, dict) or item.get("id") != item_id:
                        raise ValueError("item endpoint returned a different item id")
                except (ValueError, UnicodeDecodeError) as error:
                    response.pop("body", None)
                    response["error"] = str(error)
                    response["httpStatus"] = None
                else:
                    fetched_items += 1
                    cached = {
                        "itemId": item_id,
                        "url": response["url"],
                        "requestedAt": response["requestedAt"],
                        "httpStatus": response["httpStatus"],
                        "responseHeaders": response["responseHeaders"],
                        "body": body.decode("utf-8"),
                        "cacheOrigin": "live request",
                    }
                    cache_path.write_text(json.dumps(cached, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if cached is None:
                item_entries.append(_entry(response, response.get("body"), "raw/items/{}.json".format(item_id), itemId=item_id, cacheHit=False))
                continue
        else:
            cache_hits += 1
            used_cache = True
        body = cached["body"].encode("utf-8")
        item = json.loads(body.decode("utf-8"))
        item_values[str(item_id)] = item
        relative = "raw/items/{}.json".format(item_id)
        _write(snapshot_dir / relative, body)
        item_metadata = {
            "url": cached["url"],
            "requestedAt": cached["requestedAt"],
            "httpStatus": cached["httpStatus"],
            "responseHeaders": cached.get("responseHeaders", {}),
            "attempts": [],
        }
        item_entries.append(_entry(
            item_metadata, body, relative, itemId=item_id, cacheHit=used_cache,
            cacheOrigin=cached.get("cacheOrigin"), snapshotCopiedAt=_iso(),
        ))

    manifest["entries"].extend(item_entries)
    manifest["itemCache"] = {
        "cacheDirectory": str(cache_dir),
        "maxAgeDays": CACHE_MAX_AGE.days,
        "uniqueResultItems": len(wanted_ids),
        "cacheHits": cache_hits,
        "liveRequests": fetched_items,
        "legacyCacheSeeded": seeded,
        "vendorSellBuildKnown": False,
    }
    _write(snapshot_dir / "source_manifest.json", (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    manual, manual_manifest = _load_manual_inputs(root, snapshot_dir)
    manifest["manualInputs"] = manual_manifest
    _write_snapshot_static_evidence(snapshot_dir, manual, manifest)
    result = _analyze_saved_snapshot(snapshot_dir, manual, persist_npc_sell_evidence=True,
                                     craft_count=craft_count)
    return snapshot_dir, result
