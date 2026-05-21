from typing import Any, Dict, List

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from app.services.tools import search_knowledge


def retrieve_knowledge_documents(query: str) -> List[Document]:
    retriever = get_knowledge_retriever()
    return retriever.invoke(query)


def get_knowledge_retriever() -> "KnowledgeBaseRetriever":
    return KnowledgeBaseRetriever()


class KnowledgeBaseRetriever(BaseRetriever):
    def _get_relevant_documents(self, query: str) -> List[Document]:
        result = search_knowledge(query)
        return [knowledge_match_to_document(match) for match in result.get("matches", [])]


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
