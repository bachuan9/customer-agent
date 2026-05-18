import os
import re
from typing import Any, Dict, List, Optional

MIN_KNOWLEDGE_SCORE = 3
KNOWLEDGE_KEYWORD_GROUPS = {
    "shipping": [
        "物流",
        "发货",
        "48小时",
        "48 小时",
        "没更新",
        "未更新",
        "延迟",
        "超时",
        "配送",
        "签收",
    ],
    "return": [
        "7天",
        "7 天",
        "七天",
        "退货",
        "无理由",
        "售后",
        "运费",
        "谁承担",
        "商家承担",
        "用户承担",
        "退款",
        "到账",
        "多久到账",
        "质量",
        "质量问题",
        "破损",
        "错发",
        "漏发",
        "换货",
        "质保",
        "维修",
    ],
    "membership": [
        "会员",
        "等级",
        "积分",
        "优惠券",
        "专属客服",
    ],
}
KNOWLEDGE_GROUP_LABELS = {
    "shipping": "物流配送",
    "return": "退货售后",
    "membership": "会员权益",
}
LOGISTICS_ISSUE_SUGGESTION_KEYWORDS = {
    "48小时",
    "48 小时",
    "超时",
    "没发货",
    "未发货",
    "没更新",
    "未更新",
    "延迟",
}
ORDER_ISSUE_SUGGESTION_KEYWORDS = {
    "48小时",
    "48 小时",
    "超时",
    "没发货",
    "未发货",
    "不发货",
    "还没发货",
    "延迟",
}

from app.storage.db import (
    ALLOWED_COMPLAINT_PRIORITIES,
    ALLOWED_LOGISTICS_STATUSES,
    ALLOWED_ORDER_STATUSES,
    delete_complaint_note as db_delete_complaint_note,
    fetch_complaint_notes,
    fetch_complaints,
    fetch_knowledge_articles,
    get_logistics_by_order_no,
    get_complaint_by_id,
    get_logistics_by_tracking_no,
    get_logistics_status,
    get_order_by_no,
    get_order_status,
    insert_complaint as db_insert_complaint,
    insert_complaint_note as db_insert_complaint_note,
    insert_logistics as db_insert_logistics,
    insert_order as db_insert_order,
    update_complaint as db_update_complaint,
    update_complaint_note as db_update_complaint_note,
    update_logistics_status as db_update_logistics_status,
    update_order_status as db_update_order_status,
)


# 1. 查询工具：只读取数据库，不修改数据。
def query_order(order_no: str) -> Dict[str, Any]:
    status = get_order_status(order_no)
    if status is None:
        return {"found": False, "order_no": order_no, "status": None}
    return {"found": True, "order_no": order_no, "status": status}


def query_logistics(tracking_no: str) -> Dict[str, Any]:
    logistics = get_logistics_by_tracking_no(tracking_no)
    if logistics is None:
        return {"found": False, "tracking_no": tracking_no, "status": None}
    return {
        "found": True,
        "tracking_no": tracking_no,
        "order_no": logistics["order_no"],
        "status": logistics["status"],
    }


def query_logistics_by_order(order_no: str) -> Dict[str, Any]:
    logistics = get_logistics_by_order_no(order_no)
    if logistics is None:
        return {"found": False, "order_no": order_no, "tracking_no": None, "status": None}
    return {
        "found": True,
        "tracking_no": logistics["tracking_no"],
        "order_no": logistics["order_no"],
        "status": logistics["status"],
    }


def should_suggest_logistics_complaint(query: str) -> bool:
    return any(keyword in query for keyword in LOGISTICS_ISSUE_SUGGESTION_KEYWORDS)


def should_suggest_order_complaint(query: str) -> bool:
    return any(keyword in query for keyword in ORDER_ISSUE_SUGGESTION_KEYWORDS)


def build_order_issue_suggestion(
    order_result: Dict[str, Any],
    logistics_result: Dict[str, Any],
    knowledge_result: Dict[str, Any],
    suggest_complaint: bool,
) -> str:
    if not order_result.get("found"):
        return "建议先请用户核对订单号；确认订单号无误后，再人工核实订单是否存在或是否属于其他渠道订单。"

    if logistics_result.get("found"):
        if logistics_result.get("status") == "delivered":
            return "建议告知用户订单已有物流记录且显示已送达；如果用户仍反馈未收到，可继续核实签收信息、收货地址和物流签收证明。"
        return "建议告知用户订单已有物流记录，并结合物流状态安抚用户；如物流长时间未更新，可联系仓库或承运商核实。"

    if suggest_complaint:
        return "建议先安抚用户，并核实订单是否已生成物流单；如果确认超过承诺时效仍未发货，可引导用户确认创建投诉并升级处理。"

    if knowledge_result.get("found"):
        return "建议参考命中的平台政策回复用户，并结合订单状态继续核实是否存在预售、定制、大促或仓库延迟。"

    return "建议先人工核实订单和仓库状态；当前知识库没有命中可靠政策，避免直接承诺处理结果。"


def build_logistics_issue_suggestion(
    logistics_result: Dict[str, Any],
    knowledge_result: Dict[str, Any],
    suggest_complaint: bool,
) -> str:
    if not logistics_result.get("found"):
        return "建议先请用户核对物流单号；如果单号无误，再联系仓库或承运商确认是否已生成有效物流轨迹。"

    if logistics_result.get("status") == "delivered":
        return "建议告知用户物流显示已送达；如果用户反馈未收到，应优先核实签收人、签收地址和物流签收证明。"

    if suggest_complaint:
        return "建议先安抚用户，并联系仓库或承运商核实物流长时间未更新原因；如果确认超时，可引导用户确认创建投诉并升级处理。"

    if knowledge_result.get("found"):
        return "建议参考命中的物流政策回复用户，并结合当前物流状态判断是否需要继续跟进。"

    return "建议先人工核实物流轨迹和承运商状态；当前知识库没有命中可靠政策，避免直接承诺赔付或时效。"


def handle_order_issue(order_no: str, query: str) -> Dict[str, Any]:
    order_result = query_order(order_no)
    logistics_result = query_logistics_by_order(order_no)
    knowledge_result = search_knowledge(query)
    suggest_complaint = should_suggest_order_complaint(query)
    agent_suggestion = build_order_issue_suggestion(
        order_result,
        logistics_result,
        knowledge_result,
        suggest_complaint,
    )

    return {
        "found": order_result.get("found", False),
        "order_no": order_no,
        "order_status": order_result.get("status"),
        "order_result": order_result,
        "logistics_result": logistics_result,
        "tracking_no": logistics_result.get("tracking_no"),
        "logistics_status": logistics_result.get("status"),
        "knowledge_result": knowledge_result,
        "knowledge_found": knowledge_result.get("found", False),
        "knowledge_sources": knowledge_result.get("sources", []),
        "suggest_complaint": suggest_complaint,
        "agent_suggestion": agent_suggestion,
        "steps": [
            "调用工具：query_order",
            "调用工具：query_logistics_by_order",
            "调用工具：search_knowledge",
            "生成客服处理建议",
            "判断是否需要建议创建投诉",
        ],
    }


def handle_logistics_issue(tracking_no: str, query: str) -> Dict[str, Any]:
    logistics_result = query_logistics(tracking_no)
    knowledge_result = search_knowledge(query)
    suggest_complaint = should_suggest_logistics_complaint(query)
    agent_suggestion = build_logistics_issue_suggestion(
        logistics_result,
        knowledge_result,
        suggest_complaint,
    )

    return {
        "found": logistics_result.get("found", False),
        "tracking_no": tracking_no,
        "order_no": logistics_result.get("order_no"),
        "logistics_status": logistics_result.get("status"),
        "logistics_result": logistics_result,
        "knowledge_result": knowledge_result,
        "knowledge_found": knowledge_result.get("found", False),
        "knowledge_sources": knowledge_result.get("sources", []),
        "suggest_complaint": suggest_complaint,
        "agent_suggestion": agent_suggestion,
        "steps": [
            "调用工具：query_logistics",
            "调用工具：search_knowledge",
            "生成客服处理建议",
            "判断是否需要建议创建投诉",
        ],
    }


def get_knowledge_dir_path() -> str:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(base_dir, "docs", "knowledge")


def list_knowledge_files() -> List[str]:
    knowledge_dir = get_knowledge_dir_path()
    if not os.path.isdir(knowledge_dir):
        return []
    return [
        os.path.join(knowledge_dir, name)
        for name in sorted(os.listdir(knowledge_dir))
        if name.endswith(".md")
    ]


def format_knowledge_source(path: str) -> str:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.relpath(path, base_dir).replace("\\", "/")


def split_knowledge_sections(content: str) -> List[str]:
    sections = re.split(r"\n(?=## )", content)
    return [section.strip() for section in sections if section.strip()]


def extract_knowledge_keywords(query: str) -> List[str]:
    normalized_query = query.lower().replace(" ", "")
    keywords = []
    for group_keywords in KNOWLEDGE_KEYWORD_GROUPS.values():
        for keyword in group_keywords:
            normalized_keyword = keyword.lower().replace(" ", "")
            if normalized_keyword in normalized_query:
                keywords.append(keyword)
    return keywords


def score_knowledge_section(query: str, section: str) -> int:
    keywords = extract_knowledge_keywords(query)
    section_lower = section.lower().replace(" ", "")
    score = 0
    has_keyword_match = False
    for keyword in keywords:
        normalized_keyword = keyword.lower().replace(" ", "")
        if normalized_keyword in section_lower:
            score += 2
            has_keyword_match = True

    if not has_keyword_match:
        return 0

    for char in query:
        if char.strip() and char in section:
            score += 1
    return score


def get_matched_knowledge_keywords(query: str, section: str) -> List[str]:
    section_lower = section.lower().replace(" ", "")
    matched = []
    for keyword in extract_knowledge_keywords(query):
        normalized_keyword = keyword.lower().replace(" ", "")
        if normalized_keyword in section_lower:
            matched.append(keyword)
    return matched


def get_matched_knowledge_groups(query: str, section: str) -> List[str]:
    section_lower = section.lower().replace(" ", "")
    normalized_query = query.lower().replace(" ", "")
    matched_groups = []
    for group_name, group_keywords in KNOWLEDGE_KEYWORD_GROUPS.items():
        for keyword in group_keywords:
            normalized_keyword = keyword.lower().replace(" ", "")
            if normalized_keyword in normalized_query and normalized_keyword in section_lower:
                matched_groups.append(group_name)
                break
    return matched_groups


def build_knowledge_match_reason(score: int, matched_keywords: List[str], matched_groups: List[str], source: str) -> str:
    keyword_text = "、".join(matched_keywords) if matched_keywords else "无明确关键词"
    group_labels = [KNOWLEDGE_GROUP_LABELS.get(group, group) for group in matched_groups]
    group_text = "、".join(group_labels) if group_labels else "未识别业务分类"
    return f"因为用户问题和该知识都包含：{keyword_text}；分类命中：{group_text}；相关度分数：{score}；来源：{source}。"


def search_knowledge(query: str) -> Dict[str, Any]:
    knowledge_files = list_knowledge_files()
    db_articles = fetch_knowledge_articles(include_disabled=False)
    if not knowledge_files and not db_articles:
        return {"found": False, "query": query, "matches": [], "sources": [], "error": "knowledge_not_found"}

    scored_sections = []
    for knowledge_path in knowledge_files:
        with open(knowledge_path, "r", encoding="utf-8") as file:
            content = file.read()

        source = format_knowledge_source(knowledge_path)
        for section in split_knowledge_sections(content):
            score = score_knowledge_section(query, section)
            if score >= MIN_KNOWLEDGE_SCORE:
                matched_keywords = get_matched_knowledge_keywords(query, section)
                matched_groups = get_matched_knowledge_groups(query, section)
                scored_sections.append({
                    "score": score,
                    "matched_keywords": matched_keywords,
                    "matched_groups": matched_groups,
                    "match_reason": build_knowledge_match_reason(score, matched_keywords, matched_groups, source),
                    "content": section,
                    "source": source,
                })

    for article in db_articles:
        article_text = f"{article['title']}\n{article['content']}"
        score = score_knowledge_section(query, article_text)
        if score >= MIN_KNOWLEDGE_SCORE:
            source = f"knowledge_articles:{article['id']}"
            matched_keywords = get_matched_knowledge_keywords(query, article_text)
            matched_groups = get_matched_knowledge_groups(query, article_text)
            scored_sections.append({
                "score": score,
                "matched_keywords": matched_keywords,
                "matched_groups": matched_groups,
                "match_reason": build_knowledge_match_reason(score, matched_keywords, matched_groups, source),
                "content": article_text,
                "source": source,
            })

    scored_sections.sort(key=lambda item: item["score"], reverse=True)
    top_sections = scored_sections[:3]
    matches = [
        {
            "content": item["content"],
            "source": item["source"],
            "score": item["score"],
            "matched_keywords": item["matched_keywords"],
            "matched_groups": item["matched_groups"],
            "match_reason": item["match_reason"],
        }
        for item in top_sections
    ]
    sources = []
    for item in matches:
        if item["source"] not in sources:
            sources.append(item["source"])

    return {
        "found": bool(matches),
        "query": query,
        "matches": matches,
        "sources": sources,
        "source": sources[0] if sources else None,
    }


# 2. 投诉工具：创建、筛选、更新投诉工单。
def create_complaint(
    user_id: str,
    content: str,
    priority: str = "medium",
    handler: str = None,
) -> Dict[str, str]:
    if priority not in ALLOWED_COMPLAINT_PRIORITIES:
        return {"complaint_id": None, "status": "failed", "error": "invalid_priority"}
    complaint_id = db_insert_complaint(user_id, content, priority=priority, handler=handler)
    return {"complaint_id": complaint_id, "status": "created"}


def list_complaints(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    handler: Optional[str] = None,
) -> List[Dict[str, str]]:
    return fetch_complaints(user_id=user_id, status=status, priority=priority, handler=handler)


def get_complaint_detail(complaint_id: str) -> Optional[Dict[str, Any]]:
    complaint = get_complaint_by_id(complaint_id)
    if complaint is None:
        return None
    notes = fetch_complaint_notes(complaint_id) or []
    return {"complaint": complaint, "notes": notes}


# 3. 订单工具：创建订单、校验状态、更新订单。
def create_order(order_no: str, user_id: str, status: str = "pending") -> Dict[str, str]:
    return db_insert_order(order_no, user_id, status)


def update_order(order_no: str, status: str) -> Dict[str, Any]:
    if status not in ALLOWED_ORDER_STATUSES:
        return {"updated": False, "order": None, "error": "invalid_status"}

    updated = db_update_order_status(order_no, status)
    if not updated:
        return {"updated": False, "order": None, "error": "order_not_found"}
    return {"updated": True, "order": get_order_by_no(order_no), "error": None}


# 4. 物流工具：创建物流、校验状态、更新物流。
def create_logistics(tracking_no: str, order_no: str, status: str = "pending") -> Dict[str, str]:
    db_insert_logistics(tracking_no, order_no, status)
    return {"tracking_no": tracking_no, "order_no": order_no, "status": status}


def update_logistics(tracking_no: str, status: str) -> Dict[str, Any]:
    if status not in ALLOWED_LOGISTICS_STATUSES:
        return {"updated": False, "logistics": None, "error": "invalid_status"}

    updated = db_update_logistics_status(tracking_no, status)
    if not updated:
        return {"updated": False, "logistics": None, "error": "logistics_not_found"}
    return {"updated": True, "logistics": get_logistics_by_tracking_no(tracking_no), "error": None}


# 5. 投诉更新工具：包装 db.py 的 update_complaint()。
def update_complaint(
    complaint_id: str,
    *,
    status: Optional[str] = None,
    handler: Optional[str] = None,
    priority: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    if priority is not None and priority not in ALLOWED_COMPLAINT_PRIORITIES:
        raise ValueError("invalid complaint priority")
    return db_update_complaint(complaint_id, status=status, handler=handler, priority=priority)


# 6. 投诉备注工具：添加、查询、修改、删除备注。
def add_complaint_note(
    complaint_id: str,
    content: str,
    author: str = "客服",
) -> Optional[Dict[str, str]]:
    return db_insert_complaint_note(complaint_id, content, author)


def list_complaint_notes(complaint_id: str) -> Optional[List[Dict[str, str]]]:
    return fetch_complaint_notes(complaint_id)


def update_complaint_note(note_id: str, content: str) -> Optional[Dict[str, str]]:
    return db_update_complaint_note(note_id, content)


def delete_complaint_note(note_id: str) -> Dict[str, Any]:
    deleted = db_delete_complaint_note(note_id)
    return {"deleted": deleted, "note_id": note_id}
