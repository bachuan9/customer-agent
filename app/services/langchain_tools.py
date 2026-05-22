from typing import Any, Dict, List

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.services.tools import search_knowledge


# langchain_tools.py 阅读地图：
# 1. SearchKnowledgeInput 定义 LangChain 工具的参数形状。
# 2. run_search_knowledge_tool(...) 包装项目原有 search_knowledge(...)。
# 3. search_knowledge_tool 把普通 Python 函数变成 LangChain StructuredTool。
# 4. list_langchain_tools() 给 LangChain Agent 提供可用工具列表。


# 1. 工具参数：告诉 LangChain 这个工具需要 query。
class SearchKnowledgeInput(BaseModel):
    query: str = Field(description="用户提出的客服问题，用于检索知识库")


# 2. 普通 Python 包装函数：实际仍然调用项目自己的 RAG 检索。
def run_search_knowledge_tool(query: str) -> Dict[str, Any]:
    return search_knowledge(query)


# 3. LangChain 工具对象：把 search_knowledge 注册成 StructuredTool。
search_knowledge_tool = StructuredTool.from_function(
    func=run_search_knowledge_tool,
    name="search_knowledge",
    description=(
        "检索电商客服知识库，适合回答退款、退货、物流超时、会员权益、"
        "生鲜破损等政策类问题。输入 query 是用户原始问题。"
    ),
    args_schema=SearchKnowledgeInput,
)


# 4. 对外入口：给 LangChain Agent 或 RAG 链路调用。
def call_langchain_search_knowledge(query: str) -> Dict[str, Any]:
    return search_knowledge_tool.invoke({"query": query})


def list_langchain_tools() -> List[StructuredTool]:
    return [search_knowledge_tool]
