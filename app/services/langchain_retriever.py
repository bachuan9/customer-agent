from typing import Any, Dict, List

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from app.services.tools import search_knowledge


# langchain_retriever.py 阅读地图：
# 1. retrieve_knowledge_documents(...) 是外部调用入口。
# 2. KnowledgeBaseRetriever 把项目自己的 search_knowledge(...) 适配成 LangChain Retriever。
# 3. knowledge_match_to_document(...) 把知识库 match 转成 LangChain Document。


# 1. 检索入口：外部传入 query，返回 LangChain Document 列表。
def retrieve_knowledge_documents(query: str) -> List[Document]:
    retriever = get_knowledge_retriever()
    return retriever.invoke(query)


# 2. Retriever 工厂：每次返回一个项目知识库检索器。
def get_knowledge_retriever() -> "KnowledgeBaseRetriever":
    return KnowledgeBaseRetriever()


# 3. LangChain Retriever 适配器：内部仍然复用 search_knowledge。
class KnowledgeBaseRetriever(BaseRetriever):
    def _get_relevant_documents(self, query: str) -> List[Document]:
        result = search_knowledge(query)
        return [knowledge_match_to_document(match) for match in result.get("matches", [])]


# 4. 数据格式转换：把项目 match dict 转成 LangChain Document。
def knowledge_match_to_document(match: Dict[str, Any]) -> Document:
    return Document(
        page_content=match.get("content", ""),
        metadata={
            "source": match.get("source"),
            "title": match.get("title"),
            "score": match.get("score"),
            "keyword_score": match.get("keyword_score"),
            "embedding_score": match.get("embedding_score"),
            "matched_keywords": match.get("matched_keywords", []),
            "matched_groups": match.get("matched_groups", []),
            "retrieval_mode": match.get("retrieval_mode"),
        },
    )
