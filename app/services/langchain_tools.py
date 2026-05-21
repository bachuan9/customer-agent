from typing import Any, Dict, List

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.services.tools import search_knowledge


class SearchKnowledgeInput(BaseModel):
    query: str = Field(description="用户提出的客服问题，用于检索知识库")


def run_search_knowledge_tool(query: str) -> Dict[str, Any]:
    return search_knowledge(query)


search_knowledge_tool = StructuredTool.from_function(
    func=run_search_knowledge_tool,
    name="search_knowledge",
    description=(
        "检索电商客服知识库，适合回答退款、退货、物流超时、会员权益、"
        "生鲜破损等政策类问题。输入 query 是用户原始问题。"
    ),
    args_schema=SearchKnowledgeInput,
)


def call_langchain_search_knowledge(query: str) -> Dict[str, Any]:
    return search_knowledge_tool.invoke({"query": query})


def list_langchain_tools() -> List[StructuredTool]:
    return [search_knowledge_tool]
