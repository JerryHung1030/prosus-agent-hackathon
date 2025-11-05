# FILE: ./src/tools/rag_tool.py

import os

from crewai.tools import BaseTool
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings


class RagSearchTool(BaseTool):
    name: str = "internal_knowledge_search"
    description: str = (
        "Searches the company's internal knowledge base (Vector DB) "
        "to answer questions about policies, FAQs, and product data. "
        "Use this tool to find internal information."
    )
    _retriever = None

    def _ensure_retriever(self):
        """Lazily initialize the retriever when first used."""
        if self._retriever is not None:
            return

        db_path = "db/"
        if not os.path.exists(db_path):
            raise RuntimeError(
                "Vector store not found. Please run `python ingest.py` to build the database."
            )

        # OpenAIEmbeddings reads API key from env set by src.config
        embeddings = OpenAIEmbeddings()
        vector_store = Chroma(persist_directory=db_path, embedding_function=embeddings)
        self._retriever = vector_store.as_retriever(search_kwargs={"k": 5})
        print("RAG tool: Vector store loaded successfully.")

    def _run(self, query: str) -> str:
        """Executes the RAG search."""
        if self._retriever is None:
            try:
                self._ensure_retriever()
            except Exception as e:
                return f"Error: RAG tool initialization failed. {e}"

        try:
            retriever = self._retriever
            if retriever is None:
                return "RAG retriever is unavailable."
            docs = retriever.invoke(query)
            if not docs:
                return "No internal knowledge found for that query."

            context = "\n---\n".join([doc.page_content for doc in docs])
            return f"Found internal knowledge:\n{context}"

        except Exception as e:
            return f"Error during RAG search: {e}"


# Instantiate the tool for export
rag_search_tool = RagSearchTool()
