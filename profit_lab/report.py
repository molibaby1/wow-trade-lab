"""Single-file, offline HTML report renderer."""

import html
from string import Template


WARNING_TEXT = {
    "recipe_source_unknown": "配方来源未知",
    "conditions_unverified": "专业、技能、来源或绑定条件待核验",
    "variable_yield_uses_minimum": "产量可变；利润按最小产量计算",
    "yield_incomplete": "产量字段不完整",
    "candidate_audit_unverified": "候选审计缺失、过期或不适用于当前快照",
    "audit_npc_sell_conflict": "NPC 回售价冲突；保留 AHledger 与 ForeverDB 两种情景",
    "audit_npc_sell_unverified": "NPC 回售价互证缺失或审计未匹配",
    "audit_skill_conflict": "AHledger 与 ForeverDB 技能要求冲突",
    "audit_source_conflict": "配方来源记录存在冲突",
    "audit_source_unverified": "配方来源或当前版本可获取性尚未核实",
    "npc_sell_price_conflict": "NPC 售价跨来源冲突；请先核验",
    "npc_sell_price_unverified": "NPC 售价尚未交叉验证",
    "npc_sell_price_evidence_stale": "NPC 售价证据已过期或客户端 build 未匹配",
}
MIXED_WARNING_TEXT = {
    "mixed_ah_depth_unknown": "AH 报价缺少该价格档位的可买数量，只能作理论采购参考",
    "mixed_npc_purchase_reference_only": "混合成本包含 NPC 页面参考报价，但当前客户端、库存、可达性或购买条件未确认；不构成可执行利润",
    "mixed_recipe_conditions_unverified": "配方来源、专业、技能或绑定条件仍未核实，不构成可执行机会",
}
PURCHASE_REASON_TEXT = {
    "pack_price_missing_or_invalid": "缺少有效整包售价",
    "pack_quantity_missing_or_ambiguous": "缺少每包数量，单位价有歧义",
    "vendor_id_missing": "缺少商人 ID",
    "vendor_name_missing": "缺少商人名称",
    "vendor_location_missing": "缺少商人位置",
    "vendor_faction_unknown": "商人阵营未知",
    "vendor_faction_mismatch": "商人阵营不适用于当前市场",
    "vendor_reachability_unverified": "商人可达性未确认",
    "purchase_conditions_unverified": "购买条件未确认",
    "purchase_source_missing": "缺少采购来源",
    "purchase_evidence_reference_missing": "缺少可复核证据引用",
    "client_build_missing": "缺少客户端 build",
    "purchase_extraction_time_missing": "缺少提取时间",
    "client_build_mismatch": "数据 build 与当前 build 冲突",
    "evidence_not_current_forever": "仅有 Classic 或未知等级数据，不能用于当前采购计算",
    "current_client_applicability_unverified": "未确认适用于当前客户端",
    "limited_stock_unknown": "限量库存数量未知",
    "limited_stock_insufficient": "限量库存不足以完成本批次",
    "limited_stock_not_repeatable": "限量库存不能作为长期稳定供货",
    "stock_type_unknown": "库存类型未知",
    "same_vendor_price_conflict": "同一商人价格记录冲突",
}
BLOCKER_TEXT = {
    "faction_mismatch": "阵营明确不符",
    "recipe_unavailable": "已核实当前角色无法取得配方",
    "snapshot_misaligned": "配方与价表快照不一致",
    "missing_price_or_vendor_sell": "缺少材料价格或 NPC 收购价",
    "no_positive_margin": "两个市场情景均无正毛利",
    "mixed_evidence_conflict": "混合参考虽有正毛利，但 NPC 售价、配方来源或技能存在冲突",
}


def _esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def format_copper(value):
    if value is None:
        return "不可计算"
    copper = int(value)
    sign = "−" if copper < 0 else ""
    copper = abs(copper)
    gold, rem = divmod(copper, 10000)
    silver, copper = divmod(rem, 100)
    return "{}{}g {}s {}c（{} 铜）".format(sign, gold, silver, copper, "-" + str(abs(int(value))) if int(value) < 0 else str(int(value)))


def _format_copper_value(value, exact=None):
    if value is None:
        return "不可计算"
    if isinstance(value, int) and not isinstance(value, bool):
        return format_copper(value)
    if isinstance(value, (float, int)):
        displayed = ("{:.6f}".format(value)).rstrip("0").rstrip(".")
        exact_text = "；精确值 {}/{} 铜".format(*exact.split("/")) if isinstance(exact, str) and "/" in exact else ""
        return "{} 铜{}".format(displayed, exact_text)
    return "{} 铜".format(_esc(value))


def _localized_span(kind, entity_id, english, chinese, evidence):
    evidence = evidence if isinstance(evidence, dict) else {}
    translated = chinese if chinese and chinese != english else ""
    title_parts = [str(evidence.get(key)) for key in ("source", "version", "recordedAt")
                   if evidence.get(key)]
    if evidence.get("translationType") == "derived_from_result_itemId":
        title_parts.append("配方名由成品 itemId {} 派生".format(evidence.get("derivedFromResultItemId")))
    if evidence.get("nameConflictWithAHledger"):
        title_parts.append("LibItemDB / AHledger 英文名差异：{}".format(evidence.get("ahledgerEnglishName")))
    title = "；".join(title_parts)
    return '<span class="localized-name" data-name-en="{}" data-name-zhcn="{}" data-name-id="{}" title="{}">{}</span>'.format(
        _esc(english), _esc(translated), _esc("{}:{}".format(kind, entity_id) if entity_id is not None else ""),
        _esc(title), _esc(chinese or english or ""),
    )


def _vendor_evidence_text(options):
    lines = []
    for option in options or []:
        vendor = "{}（ID {}）".format(option.get("vendorName") or "未知商人", option.get("vendorId") or "未知")
        if option.get("referenceUsable"):
            if option.get("stockType") == "unlimited":
                stock = "无限库存（当前证据已核验）" if option.get("usable") else "来源标注无限库存（未确认当前游戏）"
            elif option.get("stockType") == "limited":
                stock = "限量 {} 包（以来源记录为准）".format(option.get("stockPacks") if option.get("stockPacks") is not None else "未知")
            else:
                stock = "库存类型未知"
            status = "当前可执行报价" if option.get("usable") else "仅理论参考；不可执行"
            risk_codes = option.get("reasons", [])
            risk_text = "；未核验：{}".format("、".join(PURCHASE_REASON_TEXT.get(reason, reason) for reason in risk_codes)) if risk_codes else ""
            source_urls = [url for url in (option.get("sourceUrl"), option.get("vendorSourceUrl")) if url]
            source_text = "；".join(source_urls) or option.get("source") or "未提供"
            if option.get("stockSourceLabel"):
                stock += "（{}）".format(option["stockSourceLabel"])
            lines.append("{}，{}，{}；{}；{}；每包 {} 铜 / {} 件，单位分摊 {} 铜/件；条件：{}；来源：{}；build {}，数据提取 {}，观察 {}（{}）{}".format(
                vendor, option.get("location") or "位置未知", option.get("faction") or "阵营未知",
                stock, status, option.get("packPriceCopper"), option.get("packQuantity"), option.get("unitPriceCopper"),
                option.get("conditions") or "未提供", source_text,
                option.get("clientBuild") or "未知", option.get("extractedAt") or "未知",
                option.get("sourceObservedAt") or "未知", option.get("evidenceLevel") or "证据等级未知", risk_text,
            ))
        else:
            reasons = "、".join(PURCHASE_REASON_TEXT.get(reason, reason) for reason in option.get("reasons", []))
            page_price = option.get("pagePriceCopper")
            if option.get("basePriceCopper") is not None:
                price_text = "；LibItemDB 插件基础报价 {} 铜，BuyCount 未提供，不按单件或整包计算".format(
                    option.get("basePriceCopper")
                )
            else:
                price_text = "；页面价 {} 铜但单位未明".format(page_price) if page_price is not None else ""
            source_url = option.get("sourceUrl") or option.get("source") or "未提供"
            local_evidence = option.get("localEvidence") or []
            local_text = "；".join("本地文件 {}（SHA-256 {}）".format(
                evidence.get("path") or "未知", evidence.get("sha256") or "未知"
            ) for evidence in local_evidence if isinstance(evidence, dict))
            level_text = option.get("evidenceLevel") or "证据等级未知"
            lines.append("{}：不用于采购成本（{}{}）；{}；来源 {}；证据等级 {}；build {}，提取 {}，观察 {}{}".format(
                vendor, reasons or "证据不完整", price_text,
                option.get("pagePriceText") or option.get("conditions") or "", source_url,
                level_text, option.get("clientBuild") or "未知", option.get("extractedAt") or "未知",
                option.get("sourceObservedAt") or "未知", "；" + local_text if local_text else "",
            ))
    return "".join("<li>{}</li>".format(_esc(line)) for line in lines) or "<li>没有该材料的 NPC 采购证据。</li>"


def _list_labels(values, mapping):
    return "；".join(mapping.get(value, value) for value in values) if values else "无"


def _historical_audit_summary(audit):
    if not isinstance(audit, dict) or audit.get("appliesToCurrentSnapshot"):
        return None
    status = audit.get("recordedStatus")
    if not status and "audit_candidate_not_found" in (audit.get("reasonCodes") or []):
        return "该配方未列入旧候选审计；当前版本仍未自动核验"
    if status == "CONFLICTED":
        notes = [note for note in audit.get("notes", []) if isinstance(note, str)]
        categories = []
        if any("技能" in note or "skillRequired" in note for note in notes):
            categories.append("技能要求")
        if any(any(term in note for term in ("来源", "配方", "404", "可获取")) for note in notes):
            categories.append("配方来源/获取")
        if any(any(term in note for term in ("回售价", "NPC 售价", "vendorSell")) for note in notes):
            categories.append("NPC 回售价")
        detail = "、".join(categories) if categories else "旧审计记录"
        return "历史审计曾记冲突（不适用于当前快照）：{}".format(detail)
    if status == "CORROBORATED":
        return "旧审计曾记互证，但不适用于当前快照"
    if status:
        return "旧审计状态 {}，未匹配当前快照".format(_audit_status_label(status))
    return "旧审计未匹配当前快照"


def _candidate_status_notes(row):
    notes = []
    if not row.get("userObservation"):
        notes.append("仅理论结果，暂无用户游戏内观察")
    history = _historical_audit_summary(row.get("candidateAudit"))
    if history:
        notes.append(history)
    npc_item_ids = sorted({
        str(reagent.get("itemId"))
        for reagent in row.get("reagents", [])
        if any((reagent.get(scenario) or {}).get("channel") == "npc"
               for scenario in ("mixedReference", "mixedMinimum"))
    })
    if npc_item_ids:
        notes.append("混合采购含 NPC 报价：{}".format("、".join(npc_item_ids)))
    median_profit = row.get("profitMedianCopper")
    min_profit = row.get("profitMinBuyoutCopper")
    if isinstance(median_profit, (int, float)) and isinstance(min_profit, (int, float)) \
            and median_profit <= 0 < min_profit:
        notes.append("仅 AH 最低买断情景为正")
    return notes


def _user_observation_details(row):
    observation = row.get("userObservation")
    if not isinstance(observation, dict):
        return ""
    return (
        '<section class="observation-details"><h4>用户报告的游戏内观察</h4>'
        '<p><strong>状态：</strong>用户报告实际可行；来源：{}；记录时间：{}；观察时间：{}；客户端 build：{}。</p>'
        '<p>{}</p><p>{}</p></section>'
    ).format(
        _esc(observation.get("source") or "用户反馈"),
        _esc(observation.get("recordedAt") or "未知"),
        _esc(observation.get("observedAt") or "未提供"),
        _esc(observation.get("clientBuild") or "未提供"),
        _esc(observation.get("summary") or "用户反馈游戏内存在实际可行的机会。"),
        _esc(observation.get("limitations") or
             "用户观察不补齐自动核验所需的采购、库存、技能、来源或销售证据。"),
    )


def _audit_status_label(value):
    return {
        "CORROBORATED": "已互证",
        "CONFLICTED": "存在冲突",
        "BLOCKED": "已证实不可获取",
        "UNVERIFIED": "未验证",
        "APPLIED": "已匹配此快照",
        "MISSING": "缺少审计",
        "PRIOR_OBSERVATION": "有历史游戏内观察",
    }.get(value, value or "未验证")


def _audit_details(row):
    audit = row.get("candidateAudit")
    if not isinstance(audit, dict):
        return "当前无匹配的候选审计记录。"
    skill = {"match": "数值相同", "conflict": "要求不同", "unverified": "未验证"}.get(
        audit.get("skillComparison"), "未验证"
    )
    source = {"conflict": "发现来源冲突", "no_conflict_recorded": "未记录明确冲突", "unverified": "未验证"}.get(
        audit.get("sourceComparison"), "未验证"
    )
    lines = [
        "<p><strong>候选审计：{}</strong>；记录状态：{}；{}。</p>".format(
            _esc(_audit_status_label(audit.get("status"))),
            _esc(_audit_status_label(audit.get("recordedStatus"))),
            "市场快照匹配" if audit.get("appliesToCurrentSnapshot") else "候选审计未与当前市场快照匹配",
        ),
        "<p>技能对比：{}（AHledger {}；ForeverDB {}）；来源状态：{}；可获取性：{}。</p>".format(
            _esc(skill), _esc(audit.get("ahSkillRequired") if audit.get("ahSkillRequired") is not None else "未知"),
            _esc(audit.get("foreverDbSkillRequired") if audit.get("foreverDbSkillRequired") is not None else "未知"),
            _esc(source), _esc(_audit_status_label(audit.get("availabilityStatus"))),
        ),
        "<p>配方来源：{}；可获取性说明：{}；AHledger acquisition：{}。</p>".format(
            _esc(audit.get("recipeSource") or "未提供"), _esc(audit.get("access") or "未提供"),
            _esc(audit.get("ahAcquisition") or "未提供"),
        ),
    ]
    if audit.get("reasonCodes"):
        lines.append("<p>适用性原因：{}。</p>".format(_esc("；".join(audit["reasonCodes"]))))
    notes = audit.get("notes") or []
    evidence = audit.get("evidence") or []
    local_evidence = audit.get("localEvidence") or []
    evidence_items = ["审计说明：{}".format(note) for note in notes if isinstance(note, str)]
    evidence_items.extend("公开证据：{}".format(value) for value in evidence if isinstance(value, str))
    evidence_items.extend(
        "本地证据：{}（SHA-256 {}）".format(value.get("localFile"), value.get("sha256"))
        for value in local_evidence if isinstance(value, dict)
    )
    if evidence_items:
        lines.append("<ul>{}</ul>".format("".join("<li>{}</li>".format(_esc(value)) for value in evidence_items)))
    return "".join(lines)


def _npc_sell_price_details(row):
    evidence = row.get("npcSellPriceEvidence")
    if not isinstance(evidence, dict):
        return "<p>NPC 售价证据：尚未验证。</p>"

    def source_line(label, record):
        if not isinstance(record, dict):
            return "<li>{}：尚未验证</li>".format(_esc(label))
        observed_at = record.get("observedAt") or record.get("requestedAt")
        time_text = ("观察/提取时间 {}".format(observed_at) if observed_at else
                     "观察时间未知；记录时间 {}".format(record.get("recordedAt") or "未知"))
        return "<li>{}：{}；{}；客户端 build {}；来源：{}</li>".format(
            _esc(label), _esc(format_copper(record.get("unitPriceCopper"))),
            _esc(time_text),
            _esc(record.get("clientBuild") or "未知"),
            _esc(record.get("url") or record.get("evidence") or record.get("source") or "未提供"),
        )

    ah = evidence.get("ahledger", {})
    forever_records = evidence.get("foreverDb") or []
    game_records = evidence.get("inGame") or []
    lines = [source_line("AHledger", ah)]
    if forever_records:
        lines.extend(source_line("ForeverDB", record) for record in forever_records)
    else:
        lines.append("<li>ForeverDB：尚未验证</li>")
    if game_records:
        lines.extend(source_line("游戏内确认", record) for record in game_records)
    else:
        lines.append("<li>游戏内确认：尚未验证</li>")
    comparisons = "；".join((
        "AHledger / ForeverDB：{}".format({"match": "一致", "conflict": "冲突", "missing": "缺失",
                                                  "unverified": "尚未验证"}.get(evidence.get("ahVsForeverDb"), "尚未验证")),
        "AHledger / 游戏内：{}".format({"match": "一致", "conflict": "冲突", "missing": "缺失",
                                               "unverified": "尚未验证"}.get(evidence.get("ahVsInGame"), "尚未验证")),
        "ForeverDB / 游戏内：{}".format({"match": "一致", "conflict": "冲突", "missing": "缺失",
                                               "unverified": "尚未验证"}.get(evidence.get("foreverDbVsInGame"), "尚未验证")),
    ))
    validity_labels = {
        "build_unknown": "ForeverDB build 未知",
        "build_match": "build 匹配",
        "build_mismatch": "build 不匹配",
        "build_missing": "当前客户端 build 已设置，但该证据未记录 build",
        "expired": "证据已过期",
        "invalid_expiry": "有效期格式错误",
        "current_build_unknown": "游戏内价格已确认适用于当前客户端，但 build 未知",
        "not_confirmed_current": "历史记录，未确认适用于当前客户端",
        "missing": "无该来源记录",
    }
    return (
        '<section class="price-evidence"><h4>NPC 售价证据（独立于市场快照）</h4>'
        '<p>状态：<strong>{}</strong>；{}。AHledger 原利润保持为中位价 {}、最低买断价 {}。'
        'ForeverDB 参考情景收入：{}；参考利润：中位价 {}、最低买断价 {}；'
        '当前游戏确认价收入：{}；当前游戏确认价利润：中位价 {}、最低买断价 {}。</p>'
        '<p>ForeverDB 版本有效性：{}；游戏确认价有效性：{}；当前客户端 build：{}。build 未知时只代表已有来源互证，不能视作当前客户端权威值。</p>'
        '<ul>{}</ul></section>'
    ).format(
        _esc(_audit_status_label(evidence.get("status", "UNVERIFIED"))), _esc(comparisons),
        _esc(format_copper(row.get("profitMedianCopper"))),
        _esc(format_copper(row.get("profitMinBuyoutCopper"))),
        _esc(format_copper(evidence.get("foreverDbReferenceIncomeCopper"))),
        _esc(format_copper(evidence.get("foreverDbReferenceProfitMedianCopper"))),
        _esc(format_copper(evidence.get("foreverDbReferenceProfitMinBuyoutCopper"))),
        _esc(format_copper(evidence.get("inGameConfirmedIncomeCopper"))),
        _esc(format_copper(evidence.get("inGameConfirmedProfitMedianCopper"))),
        _esc(format_copper(evidence.get("inGameConfirmedProfitMinBuyoutCopper"))),
        _esc(validity_labels.get(evidence.get("foreverDbValidity"), evidence.get("foreverDbValidity", "未知"))),
        _esc(validity_labels.get(evidence.get("inGameValidity"), evidence.get("inGameValidity", "未知"))),
        _esc(evidence.get("currentClientBuild") or "未知"),
        "".join(lines),
    )


def _reagent_details(row):
    pieces = []
    for reagent in row.get("reagents", []):
        name = _localized_span("item", reagent.get("itemId"),
                               reagent.get("nameEnUS", reagent.get("name")),
                               reagent.get("nameZhCN", reagent.get("name")),
                               reagent.get("nameTranslationEvidence"))
        sales = reagent.get("estimatedSalesPerDayTimes10")
        sales = "{} / 日".format(sales / 10) if isinstance(sales, int) else "未知"
        pieces.append(
            '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
                _esc(reagent.get("itemId")), name,
                _esc(reagent.get("quantity")), _esc(format_copper(reagent.get("medianUnitCopper"))),
                _esc(format_copper(reagent.get("medianCostCopper"))),
                _esc(format_copper(reagent.get("minBuyoutUnitCopper"))),
                _esc(format_copper(reagent.get("minBuyoutCostCopper"))),
                _esc(reagent.get("marketQuantity") if reagent.get("marketQuantity") is not None else "未知"),
                _esc(sales),
            )
        )
    if not pieces:
        pieces.append('<tr><td colspan="9">API 未提供材料行</td></tr>')
    manual = row.get("manualNpcMaterialDetails") or []
    if manual:
        pieces.append('<tr class="manual-heading"><th colspan="9">旧版人工单位价独立情景</th></tr>')
        for reagent in manual:
            evidence = "来源：{}；条件：{}".format(
                reagent.get("source") or "未填写", reagent.get("conditions") or "未填写"
            )
            pieces.append(
                '<tr><td>{}</td><td>{}</td><td>{}</td><td colspan="3">{}</td><td colspan="3">{}</td></tr>'.format(
                    _esc(reagent.get("itemId")), _esc(reagent.get("name")),
                    _esc(reagent.get("quantity")),
                    _esc(format_copper(reagent.get("unitPriceCopper"))), _esc(evidence),
                )
            )
    return "".join(pieces)


def _channel_label(channel):
    return {
        "npc": "NPC 整包采购",
        "ah_median": "AH 中位价",
        "ah_minBuyout": "AH 最低买断价",
    }.get(channel, "无可用渠道")


def _hybrid_purchase_details(row):
    craft_count = row.get("mixedReference", {}).get("craftCount", 1)
    lines = []
    for reagent in row.get("reagents", []):
        reference = reagent.get("mixedReference", {})
        minimum = reagent.get("mixedMinimum", {})
        name = _localized_span("item", reagent.get("itemId"),
                               reagent.get("nameEnUS", reagent.get("name")),
                               reagent.get("nameZhCN", reagent.get("name")),
                               reagent.get("nameTranslationEvidence"))
        reference_packages = "需买 {} 包，剩余 {} 件；".format(
            reference.get("packagesToBuy"), reference.get("excessQuantity")
        ) if reference.get("channel") == "npc" else ""
        minimum_packages = "需买 {} 包，剩余 {} 件；".format(
            minimum.get("packagesToBuy"), minimum.get("excessQuantity")
        ) if minimum.get("channel") == "npc" else ""
        reference_text = "{}；{}；分摊 {}；现金估算 {}；{}{}".format(
            _channel_label(reference.get("channel")), _format_copper_value(reference.get("unitPriceCopper"), reference.get("unitPriceExact")),
            _format_copper_value(reference.get("allocatedCostCopper"), reference.get("allocatedCostCopperExact")),
            _format_copper_value(reference.get("cashOutlayCopper")), reference_packages, reference.get("reason") or "",
        )
        minimum_text = "{}；{}；分摊 {}；现金估算 {}；{}{}".format(
            _channel_label(minimum.get("channel")), _format_copper_value(minimum.get("unitPriceCopper"), minimum.get("unitPriceExact")),
            _format_copper_value(minimum.get("allocatedCostCopper"), minimum.get("allocatedCostCopperExact")),
            _format_copper_value(minimum.get("cashOutlayCopper")), minimum_packages, minimum.get("reason") or "",
        )
        evidence = _vendor_evidence_text(reference.get("npcOptions", []))
        lines.append('<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td><ul>{}</ul></td></tr>'.format(
            _esc(reagent.get("itemId")), name, _esc(reference.get("requestedQuantity")),
            _esc(reference_text), _esc(minimum_text), evidence,
        ))
    if not lines:
        lines.append('<tr><td colspan="6">配方没有材料行。</td></tr>')

    def summary(label, scenario, repeatable):
        return '<p>{}：指定批量 {} 次；重复供货口径每次材料成本 {}、毛利 {}；当前批次材料成本 {}、毛利 {}；现金支出估算 {}（其中 NPC 整包现金 {}）。{}</p>'.format(
            label, craft_count,
            _format_copper_value(repeatable.get("materialCostPerCraftCopper")),
            _format_copper_value(repeatable.get("profitPerCraftCopper")),
            _format_copper_value(scenario.get("materialCostCopper"), scenario.get("materialCostCopperExact")),
            _format_copper_value(scenario.get("profitCopper"), scenario.get("profitCopperExact")),
            _format_copper_value(scenario.get("cashOutlayEstimateCopper")),
            _format_copper_value(scenario.get("npcCashOutlayCopper")),
            "AH 挂单深度或 NPC 供货、可达性及购买条件未核验；现金数值只是按参考报价估算。"
            if not scenario.get("cashOutlayKnown") else "采购数量按已记录的整包与库存约束估算，实际成交仍以游戏内为准。",
        )

    reference = row.get("mixedReference", {})
    minimum = row.get("mixedMinimum", {})
    repeat_reference = row.get("repeatableMixedReference", {})
    repeat_minimum = row.get("repeatableMixedMinimum", {})
    warnings = row.get("mixedWarnings", [])
    warning_html = '<p class="notice">{}</p>'.format(_esc("；".join(MIXED_WARNING_TEXT.get(value, value) for value in warnings))) if warnings else ""
    return (
        '<section class="mixed-details"><h4>理论混合采购参考利润 · 逐项选择</h4>'
        + summary("理论混合采购参考成本（AH 中位价）", reference, repeat_reference)
        + summary("理论混合采购最低成本参考（AH 最低买断价）", minimum, repeat_minimum)
        + warning_html
        + '<table class="detail-table"><thead><tr><th>材料 ID</th><th>材料</th><th>本批需求</th><th>中位价情景渠道 / 分摊 / 现金</th><th>最低买断情景渠道 / 分摊 / 现金</th><th>NPC 商人、整包与条件证据</th></tr></thead><tbody>{}</tbody></table>'
        '<p>最低买断价只代表当前最低档报价；AHledger 未提供该档可买数量。限量 NPC 价格只用于库存足够的本批次，长期重复成本不计入限量供货。</p></section>'
    ).format("".join(lines))


def render_html(result):
    alignment = result.get("snapshotAlignment", {})
    if alignment.get("aligned"):
        alignment_banner = '<p class="ok">配方与价表 market、扫描秒级时间戳一致。</p>'
    else:
        alignment_banner = '<p class="alert">快照不一致：本报告不混用材料市场价格，相关利润保留为不可计算。</p>'
    audit_meta = result.get("candidateAudit", {})
    if audit_meta.get("status") == "APPLIED":
        audit_banner = (
            '<p class="audit-banner">候选配方审计按 market 与扫描时间匹配到本快照。静态 NPC 售价证据独立按物品 ID 使用。'
            '审计日期：{}；ForeverDB build：{}（提取：{}）；AHledger NPC 价格没有客户端 build。来源：{}</p>'
        ).format(
            _esc(audit_meta.get("auditDate") or "未知"),
            _esc(audit_meta.get("foreverDbClientBuild") or "未知"),
            _esc(audit_meta.get("foreverDbExtractedAt") or "未知"),
            _esc(audit_meta.get("source") or "未记录"),
        )
    else:
        reason = "；".join(audit_meta.get("reasons", [])) or "未提供审计数据"
        audit_banner = '<p class="audit-banner">配方技能/来源审计未匹配当前市场快照（{}；{}）；NPC 售价证据仍按物品 ID 独立核对，详见各候选明细。</p>'.format(
            _esc(_audit_status_label(audit_meta.get("status"))), _esc(reason)
        )
    observation_count = result.get("userReportedObservationCount")
    if observation_count is None:
        observation_count = sum(bool(row.get("userObservation")) for row in result.get("recipes", []))
    executable_count = result.get("mixedExecutableCandidateCount", 0)
    observation_notice = (
        '<p class="notice">严格自动证据口径下有 {} 条候选满足全部执行条件；这表示当前记录尚未同时核实采购、库存、配方条件、当前客户端适用性和销售依据。'
        '另有 {} 条用户报告的游戏内观察支持，已单独展示；用户反馈不会自动补齐 build、AH 可买数量、完整采购/制作过程或销售证据，也不会升级为自动确认的可执行机会。</p>'
    ).format(_esc(executable_count), _esc(observation_count))
    locale_stats = result.get("localizationCoverage", {})
    dataset = locale_stats.get("dataset", {})
    translation_source = "{}；版本 {}；记录时间 {}".format(
        dataset.get("name") or "没有经过验证的本地化数据源",
        dataset.get("version") or "未知",
        dataset.get("recordedAt") or "未知",
    )
    translation_summary = (
        '<section class="translation-summary"><strong>离线名称翻译</strong>：'
        '配方 {}/{}（{}%）；产物 {}/{}（{}%）；材料 {}/{}（{}%）。来源/版本：{}。'
        'zhCN 缺项显示英文和 ID；语言切换只改显示文本。{}'
        '</section>'
    ).format(
        _esc(locale_stats.get("recipeNames", {}).get("translated", 0)),
        _esc(locale_stats.get("recipeNames", {}).get("total", 0)),
        _esc(locale_stats.get("recipeNames", {}).get("coveragePercent", 0)),
        _esc(locale_stats.get("resultNames", {}).get("translated", 0)),
        _esc(locale_stats.get("resultNames", {}).get("total", 0)),
        _esc(locale_stats.get("resultNames", {}).get("coveragePercent", 0)),
        _esc(locale_stats.get("materialNames", {}).get("translated", 0)),
        _esc(locale_stats.get("materialNames", {}).get("total", 0)),
        _esc(locale_stats.get("materialNames", {}).get("coveragePercent", 0)),
        _esc(translation_source),
        _esc("配方名称有 {} 条由产物 itemId 派生；{} 个 LibItemDB/AHledger 英文名差异已记录并在名称提示中标出。".format(
            dataset.get("libItemDB", {}).get("derivedRecipeNames", 0),
            dataset.get("libItemDB", {}).get("englishNameConflictCount", 0),
        )),
    )
    rows = []
    for row in result.get("recipes", []):
        group = row.get("group", "C")
        group_label = {"A": "A · 优先核验", "B": "B · 潜在机会", "C": "C · 阻塞/不盈利"}.get(group, group)
        ah_positive = any(value is not None and value > 0 for value in
                          (row.get("profitMedianCopper"), row.get("profitMinBuyoutCopper")))
        if group == "B" and row.get("mixedOpportunityEligible") and not ah_positive:
            group_label = "B · 混合采购参考盈利（待核验）"
        blockers = _list_labels(row.get("blockers", []), BLOCKER_TEXT)
        warnings = _list_labels(row.get("warnings", []), WARNING_TEXT)
        qty = "{}–{}".format(row.get("resultQtyMin"), row.get("resultQtyMax"))
        min_profit = row.get("profitMinBuyoutCopper")
        median_profit = row.get("profitMedianCopper")
        mixed_reference_profit = row.get("mixedReference", {}).get("profitPerCraftCopper")
        mixed_minimum_profit = row.get("mixedMinimum", {}).get("profitPerCraftCopper")
        manual_profit = row.get("manualNpcMaterialProfitCopper")
        audit = row.get("candidateAudit") or {}
        sell_evidence = row.get("npcSellPriceEvidence") or {}
        audit_crosscheck = 'NPC 售价证据：{} · AH/ForeverDB：{} · 技能：{} · 来源：{}'.format(
            _esc(_audit_status_label(sell_evidence.get("status"))),
            _esc({"match": "互证", "conflict": "冲突", "missing": "缺失", "unverified": "未验证"}.get(
                sell_evidence.get("ahVsForeverDb"), "尚未验证"
            )),
            _esc({"match": "一致", "conflict": "冲突", "unverified": "未验证"}.get(
                audit.get("skillComparison"), "未验证"
            )),
            _esc({"conflict": "冲突", "no_conflict_recorded": "未记录冲突", "unverified": "未验证"}.get(
                audit.get("sourceComparison"), "未验证"
            )),
        )
        is_positive = any(value is not None and value > 0 for value in (
            min_profit, median_profit,
            sell_evidence.get("foreverDbReferenceProfitMinBuyoutCopper"),
            sell_evidence.get("foreverDbReferenceProfitMedianCopper"),
            sell_evidence.get("inGameConfirmedProfitMinBuyoutCopper"),
            sell_evidence.get("inGameConfirmedProfitMedianCopper"),
            mixed_reference_profit, mixed_minimum_profit,
        ))
        if row.get("userObservation"):
            primary_status = "用户报告游戏内可行（未自动核验）" if is_positive else "用户报告游戏内可行；当前快照未显示正毛利"
        else:
            primary_status = "理论正毛利（无用户游戏内观察）" if is_positive else "无正毛利或尚不可计算"
        confidence_label = '<strong>{}</strong>{}'.format(
            _esc(primary_status),
            "".join('<small>{}</small>'.format(_esc(note)) for note in _candidate_status_notes(row))
            + '<small>{}</small>'.format(audit_crosscheck),
        )
        output_market = row.get("outputAuctionMarket") or {}
        estimated_sales = output_market.get("estimatedSalesPerDay")
        output_market_text = "成品 AH 参考：中位价 {}；最低买断 {}；挂单量 {}；估算日销 {}。".format(
            _format_copper_value(output_market.get("medianUnitCopper")),
            _format_copper_value(output_market.get("minBuyoutUnitCopper")),
            output_market.get("listedQuantity") if output_market.get("listedQuantity") is not None else "未知",
            "{} 件/日".format(estimated_sales) if estimated_sales is not None else "未知",
        )
        result_name = _localized_span(
            "item", row.get("resultId"), row.get("resultNameEnUS", row.get("resultName")),
            row.get("resultNameZhCN", row.get("resultName")), row.get("resultNameTranslationEvidence"),
        )
        recipe_name = _localized_span(
            "spell", row.get("spellId"), row.get("recipeNameEnUS", row.get("recipeName")),
            row.get("recipeNameZhCN", row.get("recipeName")), row.get("recipeNameTranslationEvidence"),
        )
        detail = (
            '<details><summary>材料与价格来源</summary>'
        '<p>NPC 收购单价：{}；每次收入：{}。材料中位价与最低买断价来源均为 AHledger pricetable。vendorSell 客户端 build 未知，此结果是市场筛选参考。</p>'
            '<p>{} 成交价、挂单量与估算日销仅作市场参考，不代表实际成交。</p>'
            '<table class="detail-table"><thead><tr><th>材料 ID</th><th>材料</th><th>配方数量</th><th>中位单价</th><th>中位成本</th><th>最低买断单价</th><th>最低买断成本</th><th>AH 挂单量</th><th>估算日销</th></tr></thead>'
            '<tbody>{}</tbody></table>'
            '<p>人工配方核验记录：{}</p>'
            '{}'
            '<p>市场最低买断价只是最低档报价；API 未给出该档可买数量，不能代表可按此价批量采购。人工 NPC 材料价利润：{}。</p>'
            '{}'
            '{}'
            '<section class="audit-details"><h4>审计与可获取性</h4>{}</section>'
            '</details>'
        ).format(
            _esc(format_copper(row.get("vendorSellUnitCopper"))),
            _esc(format_copper(row.get("npcIncomeCopper"))),
            _esc(output_market_text),
            _reagent_details(row), _esc(row.get("assessmentEvidence") or "无"),
            _user_observation_details(row), _esc(format_copper(manual_profit)),
            _hybrid_purchase_details(row),
            _npc_sell_price_details(row),
            _audit_details(row),
        )
        row_template = (
            '<tr data-group="{}" data-profession="{}" data-positive="{}" data-min="{}" data-median="{}" data-mixedref="{}" data-mixedmin="{}"{}>'
            '<td>{}</td><td>{}</td><td><strong>{}</strong><small>spellId {} · itemId {}</small></td>'
            + ('<td>{}</td>' * 11)
            + '<td>{}</td><td>{}</td><td>{}</td></tr>'
        )
        rows.append(row_template.format(
                _esc(group), _esc(row.get("profession")), "true" if is_positive else "false",
                "" if min_profit is None else min_profit,
                "" if median_profit is None else median_profit,
                "" if mixed_reference_profit is None else mixed_reference_profit,
                "" if mixed_minimum_profit is None else mixed_minimum_profit,
                "" if is_positive else " hidden",
                _esc(group_label), confidence_label, recipe_name, _esc(row.get("spellId")), _esc(row.get("resultId")),
                _esc(row.get("profession") or "未知"), _esc(row.get("skillRequired") if row.get("skillRequired") is not None else "未知"),
                _esc(row.get("acquisition") or "未知"), result_name, _esc(qty),
                _esc(format_copper(row.get("vendorSellUnitCopper"))),
                _esc(format_copper(row.get("npcIncomeCopper"))),
                _esc(format_copper(min_profit)), _esc(format_copper(median_profit)),
                _esc(_format_copper_value(mixed_reference_profit)),
                _esc(_format_copper_value(mixed_minimum_profit)),
                _esc(warnings), _esc(blockers), detail,
            ))
    profession_options = sorted({row.get("profession") or "未知" for row in result.get("recipes", [])})
    options = ''.join('<option value="{}">{}</option>'.format(_esc(value), _esc(value)) for value in profession_options)
    market_time = result.get("marketSnapshotAt") or "未知"
    generated_at = result.get("generatedAt") or "未知"
    table_rows = "".join(rows) or '<tr><td colspan="17">没有配方记录</td></tr>'
    summary = (
        '<div class="cards">'
        '<div><b>{}</b><span>配方总数</span></div><div><b>{}</b><span>双情景可计算</span></div>'
        '<div><b>{}</b><span>至少一个情景正毛利</span></div><div><b>{}</b><span>A 优先核验</span></div>'
        '<div><b>{}</b><span>B 潜在机会</span></div><div><b>{}</b><span>C 阻塞/不盈利</span></div>'
        '<div><b>{}</b><span>缺价/回售价配方</span></div>'
        '<div><b>{}</b><span>混合采购新增可计算</span></div><div><b>{}</b><span>混合采购正毛利候选</span></div>'
        '<div><b>{}</b><span>混合采购新增盈利候选</span></div><div><b>{}</b><span>条件与价格均可执行</span></div>'
        '<div><b>{}/{}</b><span>NPC 理论参考价格覆盖（材料）</span></div>'
        '<div><b>{}/{}</b><span>NPC 当前可执行价格覆盖（材料）</span></div>'
        '</div>'
    ).format(
        _esc(result.get("recipeCount", 0)), _esc(result.get("calculableBothScenariosCount", 0)),
        _esc(result.get("positiveAnyScenarioCount", 0)), _esc(result.get("priorityCount", 0)),
        _esc(result.get("potentialCount", 0)), _esc(result.get("blockedOrNonPositiveCount", 0)),
        _esc(result.get("missingPriceOrVendorSellCount", 0)),
        _esc(result.get("newlyCalculableHybridCount", 0)), _esc(result.get("mixedPositiveCandidateCount", 0)),
        _esc(result.get("newMixedPositiveCandidateCount", 0)), _esc(result.get("mixedExecutableCandidateCount", 0)),
        _esc(result.get("npcMaterialPurchaseEvidence", {}).get("referenceCoveredMaterialCount", 0)),
        _esc(result.get("npcMaterialPurchaseEvidence", {}).get("requiredMaterialCount", 0)),
        _esc(result.get("npcMaterialPurchaseEvidence", {}).get("coveredMaterialCount", 0)),
        _esc(result.get("npcMaterialPurchaseEvidence", {}).get("requiredMaterialCount", 0)),
    )
    purchase_evidence = result.get("npcMaterialPurchaseEvidence", {})
    purchase_summary = (
        '<p class="price-evidence-summary">LibItemDB Forever 基础报价候选：{} / {} 种材料；插件含 BuyCount 的记录 {} 条。'
        '候选中另有 {} 种材料在独立证据中记录了整包数量（游戏内观察 {} 种）；无 BuyCount 的基础报价只展示，不参与单位成本。</p>'
    ).format(
        _esc(purchase_evidence.get("libItemDBBasePriceCandidateCount", 0)),
        _esc(purchase_evidence.get("requiredMaterialCount", 0)),
        _esc(purchase_evidence.get("libItemDBBuyCountKnownCandidateCount", 0)),
        _esc(purchase_evidence.get("candidateItemsWithPackQuantityEvidence", 0)),
        _esc(purchase_evidence.get("candidateItemsWithCurrentInGamePackEvidence", 0)),
    )
    price_counts = result.get("npcSellPriceEvidenceCounts", {})
    price_summary = (
        '<p class="price-evidence-summary">NPC 售价证据：{} 条来源冲突；{} 条含游戏内确认价；{} 条尚未验证。'
        '冲突项不会列入优先核验；人工确认价格独立保留，并受客户端 build / 有效期限制。</p>'
    ).format(
        _esc(price_counts.get("conflicted", 0)),
        _esc(price_counts.get("gamePriceConfirmed", 0)),
        _esc(price_counts.get("unverified", 0)),
    )
    return Template('''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>WoW Forever NPC 制造利润候选</title>
<style>
:root{color-scheme:light dark;font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}body{margin:0;padding:24px;background:#111827;color:#e5e7eb}main{max-width:1800px;margin:auto}h1{margin:0 0 4px}p,small{color:#aab4c4}.meta,.cards,.toolbar{display:flex;gap:12px;flex-wrap:wrap}.meta span{padding:4px 10px;background:#1f2937;border-radius:6px}.cards{margin:18px 0}.cards div{background:#1f2937;padding:12px 18px;border-radius:8px;min-width:135px}.cards b,.cards span{display:block}.cards b{font-size:20px}.cards span{color:#aab4c4}.alert{padding:10px;background:#7f1d1d;border-radius:6px;color:#fff}.ok{padding:10px;background:#14532d;border-radius:6px;color:#fff}.notice,.audit-banner{padding:12px;background:#292524;border-left:4px solid #f59e0b}.toolbar{position:sticky;top:0;padding:12px;background:#111827;z-index:2}select,button{padding:7px 10px;border-radius:5px;border:1px solid #64748b;background:#1f2937;color:inherit;cursor:pointer}table{border-collapse:collapse;width:100%;background:#1f2937}th,td{padding:8px;border-bottom:1px solid #374151;text-align:left;vertical-align:top}th{position:sticky;top:0;background:#263244;white-space:nowrap}td small{display:block}tbody tr[data-group="A"]>td:first-child{color:#86efac}tbody tr[data-group="B"]>td:first-child{color:#fde68a}tbody tr[data-group="C"]>td:first-child{color:#fca5a5}details{min-width:300px}.audit-details{min-width:380px;max-width:700px}.audit-details h4{margin:8px 0 0}.audit-details ul{padding-left:20px}.audit-details li{overflow-wrap:anywhere}summary{cursor:pointer;color:#93c5fd}.detail-table{margin-top:8px;font-size:12px}.detail-table th{position:static}.detail-table td{white-space:nowrap}.manual-heading th{position:static;color:#fde68a}.wrap{overflow:auto;max-height:72vh;border:1px solid #374151;border-radius:8px}@media(max-width:700px){body{padding:12px}.cards div{flex:1}}
</style></head><body><main>
<h1>WoW Forever NPC 制造利润候选</h1>
<p>用途：缩小人工核验范围。理论毛利不是保证可成交利润；采购包价与整数包数保留原值，单位分摊允许小数铜。</p>
<div class="meta"><span>市场：$market</span><span>价表扫描：<time id="snapshot-time">$market_time</time>（<span id="snapshot-age">计算中</span>）</span><span>报告生成：$generated_at</span></div>
$translation_summary
$alignment
$audit_banner
$observation_notice
$summary
$purchase_summary
$price_summary
<p class="notice">vendorSell 响应没有客户端 build 字段，当前 NPC 收购价无法证明与游戏客户端版本一致。AH 最低买断价不含该价格档挂单深度，AH 理论出售参考价也不代表成交。A 表示优先人工核验，不表示已验证盈利。</p>
<div class="toolbar"><label>专业筛选：<select id="profession"><option value="">全部专业</option>$options</select></label>
<button data-language="zhCN" type="button" aria-pressed="true">简体中文</button><button data-language="enUS" type="button" aria-pressed="false">English (enUS)</button>
<button data-sort="min">AH 最低毛利</button><button data-sort="median">AH 中位毛利</button><button data-sort="mixedref">混合参考毛利</button><button data-sort="mixedmin">混合最低毛利</button><button data-sort="name">按配方名称排序</button>
<button id="toggle-all" type="button">查看全部配方</button><span id="visibility-summary">默认简体中文；候选先按用户观察和审计疑点排序，再按理论毛利排序。展开可看逐项渠道与来源。</span></div>
<div class="wrap"><table id="recipes"><thead><tr><th>分组</th><th>可信度</th><th>配方 / ID</th><th>专业</th><th>技能要求</th><th>配方来源</th><th>产物</th><th>产量/次</th><th>NPC 单价</th><th>NPC 总收入</th><th>AH 最低毛利</th><th>AH 中位毛利</th><th>混合参考毛利</th><th>混合最低毛利</th><th>待核验提示</th><th>阻塞/结果</th><th>材料明细</th></tr></thead><tbody>$table_rows</tbody></table></div>
</main><script>
const body=document.querySelector('#recipes tbody');
let showAll=false;
function setLanguage(language){
  const useChinese=language==='zhCN';
  document.documentElement.lang=useChinese?'zh-CN':'en-US';
  for(const name of document.querySelectorAll('.localized-name')){
    const english=name.dataset.nameEn||'';
    const chinese=name.dataset.nameZhcn||'';
    const key=name.dataset.nameId||'';
    const id=key.includes(':')?key.split(':')[1]:key;
    let displayed=useChinese?(chinese||english):(english||chinese);
    if(useChinese&&!chinese&&id)displayed+=' [中文缺项 · ID '+id+']';
    if(!displayed&&id)displayed='[ID '+id+']';
    name.textContent=displayed;
  }
  for(const button of document.querySelectorAll('[data-language]'))button.setAttribute('aria-pressed',String(button.dataset.language===language));
}
for(const button of document.querySelectorAll('[data-language]'))button.addEventListener('click',()=>setLanguage(button.dataset.language));
setLanguage('zhCN');
function updateVisibility(){
  const profession=document.querySelector('#profession').value;
  for (const row of body.rows) row.hidden = (!showAll && row.dataset.positive !== 'true') || Boolean(profession && row.dataset.profession !== profession);
document.querySelector('#toggle-all').textContent=showAll?'仅看正毛利候选':'查看全部配方';
document.querySelector('#visibility-summary').textContent=showAll?'当前展示全部配方；默认顺序按观察、审计疑点和理论毛利排列。':'当前展示至少一种成本口径正毛利的配方；默认顺序按观察、审计疑点和理论毛利排列。';
}
document.querySelector('#profession').addEventListener('change', updateVisibility);
document.querySelector('#toggle-all').addEventListener('click', () => { showAll=!showAll; updateVisibility(); });
for (const button of document.querySelectorAll('[data-sort]')) {
  button.addEventListener('click', () => {
    const key = button.dataset.sort;
    const rows = [...body.rows];
    rows.sort((a, b) => {
      if (key === 'name') return a.cells[2].innerText.localeCompare(b.cells[2].innerText, document.documentElement.lang);
      const x = a.dataset[key] === '' ? -Infinity : Number(a.dataset[key]);
      const y = b.dataset[key] === '' ? -Infinity : Number(b.dataset[key]);
      const xv = Number.isFinite(x) ? x : -Infinity;
      const yv = Number.isFinite(y) ? y : -Infinity;
      return yv - xv;
    });
    body.append(...rows);
  });
}
const parsed = new Date(document.querySelector('#snapshot-time').textContent);
if (!Number.isNaN(parsed.getTime())) {
  const minutes = Math.floor((Date.now() - parsed.getTime()) / 60000);
  document.querySelector('#snapshot-age').textContent = minutes < 0 ? '时间戳在未来' : (minutes < 60 ? minutes + ' 分钟' : Math.floor(minutes / 60) + ' 小时 ' + (minutes % 60) + ' 分钟');
}
</script></body></html>''').substitute(
        market=_esc(result.get("market")), market_time=_esc(market_time), generated_at=_esc(generated_at),
        alignment=alignment_banner, audit_banner=audit_banner, observation_notice=observation_notice, summary=summary,
        purchase_summary=purchase_summary,
        translation_summary=translation_summary, price_summary=price_summary,
        options=options, table_rows=table_rows,
    )
