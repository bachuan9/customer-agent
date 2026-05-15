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

from app.storage.db import (
    ALLOWED_COMPLAINT_PRIORITIES,
    ALLOWED_LOGISTICS_STATUSES,
    ALLOWED_ORDER_STATUSES,
    delete_complaint_note as db_delete_complaint_note,
    fetch_complaint_notes,
    fetch_complaints,
    fetch_knowledge_articles,
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
    status = get_logistics_status(tracking_no)
    if status is None:
        return {"found": False, "tracking_no": tracking_no, "status": None}
    return {"found": True, "tracking_no": tracking_no, "status": status}


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
    for keyword in keywords:
        normalized_keyword = keyword.lower().replace(" ", "")
        if normalized_keyword in section_lower:
            score += 2

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
                scored_sections.append({
                    "score": score,
                    "matched_keywords": get_matched_knowledge_keywords(query, section),
                    "content": section,
                    "source": source,
                })

    for article in db_articles:
        article_text = f"{article['title']}\n{article['content']}"
        score = score_knowledge_section(query, article_text)
        if score >= MIN_KNOWLEDGE_SCORE:
            source = f"knowledge_articles:{article['id']}"
            scored_sections.append({
                "score": score,
                "matched_keywords": get_matched_knowledge_keywords(query, article_text),
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
def create_complaint(user_id: str, content: str) -> Dict[str, str]:
    complaint_id = db_insert_complaint(user_id, content)
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
