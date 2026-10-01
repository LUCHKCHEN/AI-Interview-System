#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""NEWRAG RAG 引擎：LangChain 检索 + FAISS 本地向量库 + DeepSeek 生成。"""

import os
import json
import shutil
import warnings
# langchain 兼容层已进入停用期，统一屏蔽弃用提示，避免运行时刷屏
warnings.simplefilter("ignore", DeprecationWarning)
from pathlib import Path
from typing import Any, List, Optional

from dotenv import load_dotenv
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
import faiss
import numpy as np
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.llms import BaseLLM
from langchain_core.outputs import Generation, LLMResult
from openai import OpenAI

PROJECT_DIR = Path(__file__).resolve().parent
BASE_DIR = PROJECT_DIR.parent
DATA_DIR = BASE_DIR / "data"
ENV_FILE = BASE_DIR / ".env"
INDEX_DIR = PROJECT_DIR / "faiss_index"

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 5

load_dotenv(ENV_FILE, override=True)


class LocalEmbeddings(Embeddings):
    """基于 fastembed 的本地中文向量模型，不调用任何 API。"""

    MODEL_NAME = "BAAI/bge-small-zh-v1.5"

    def __init__(self) -> None:
        self._model = None

    def _get_model(self):
        if self._model is None:
            from fastembed import TextEmbedding
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

            try:
                self._model = TextEmbedding(model_name=self.MODEL_NAME)
            except Exception as exc:
                raise ValueError(
                    "本地向量模型下载失败，请检查网络；也可设置环境变量 HF_ENDPOINT 使用可用镜像后重试。"
                ) from exc
        return self._model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        vectors = []
        for embedding in self._get_model().embed(texts):
            vectors.append(list(embedding))
        return vectors

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


class FaissVectorStore:
    """基于 FAISS 本地持久化的轻量向量存储。"""

    def __init__(self, persist_directory: Path, embedding: Embeddings) -> None:
        self.persist_directory = persist_directory
        self.embedding = embedding
        self._top_k = TOP_K
        self._index_path = persist_directory / "index.faiss"
        self._documents_path = persist_directory / "documents.json"
        self.index = None
        self.documents = []
        self._load()

    def _load(self) -> None:
        if self._index_path.exists() and self._documents_path.exists():
            self.index = faiss.read_index(str(self._index_path))
            with self._documents_path.open("r", encoding="utf-8") as file:
                self.documents = json.load(file)

    @classmethod
    def build_from_documents(
        cls,
        documents: List[Document],
        embedding: Embeddings,
        persist_directory: Path,
    ) -> "FaissVectorStore":
        persist_directory.mkdir(parents=True, exist_ok=True)
        texts = [document.page_content for document in documents]
        metadatas = [document.metadata or {} for document in documents]
        vectors = embedding.embed_documents(texts)
        matrix = np.asarray(vectors, dtype=np.float32)
        faiss.normalize_L2(matrix)
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        faiss.write_index(index, str(persist_directory / "index.faiss"))
        payload = [
            {"text": text, "metadata": metadata}
            for text, metadata in zip(texts, metadatas)
        ]
        with (persist_directory / "documents.json").open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        return cls(persist_directory=persist_directory, embedding=embedding)

    def as_retriever(self, search_kwargs: Optional[dict] = None) -> "FaissVectorStore":
        self._top_k = int((search_kwargs or {}).get("k", TOP_K))
        return self

    def invoke(self, question: str) -> List[Document]:
        if self.index is None or self.index.ntotal == 0:
            return []
        query_vector = np.asarray([self.embedding.embed_query(question)], dtype=np.float32)
        faiss.normalize_L2(query_vector)
        _, indices = self.index.search(query_vector, min(self._top_k, self.index.ntotal))
        documents = []
        for index_value in indices[0]:
            if index_value < 0:
                continue
            item = self.documents[int(index_value)]
            documents.append(
                Document(page_content=item["text"], metadata=item.get("metadata") or {})
            )
        return documents


class DeepSeekLLM(BaseLLM):
    """DeepSeek 文本生成接口的 LangChain LLM 实现。"""

    model_name: str
    temperature: float = 0.2
    client: Any = None

    def __init__(self, client: OpenAI, model_name: str, temperature: float = 0.2) -> None:
        super().__init__(model_name=model_name, temperature=temperature)
        self.client = client

    @property
    def _llm_type(self) -> str:
        return "deepseek"

    def _generate(
        self,
        prompts: List[str],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> LLMResult:
        generations = []
        for prompt in prompts:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=1024,
            )
            text = ""
            if response.choices:
                text = response.choices[0].message.content or ""
            generations.append([Generation(text=text)])
        return LLMResult(generations=generations)


class RagEngine:
    """资料加载、向量库构建、检索和回答生成。"""

    def __init__(self) -> None:
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL).strip()
        self.chat_model = os.getenv("DEEPSEEK_CHAT_MODEL", DEEPSEEK_MODEL).strip()
        self.vectorstore = None
        self.retriever = None
        self.llm = None

    def _read_text(self, path: Path) -> str:
        for encoding in ("utf-8-sig", "utf-8", "gbk"):
            try:
                return path.read_text(encoding=encoding)
            except (UnicodeDecodeError, OSError):
                continue
        return ""

    def load_documents(self) -> List[Document]:
        if not DATA_DIR.exists():
            return []
        documents = []
        for path in sorted(DATA_DIR.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
                text = self._read_text(path)
                if text.strip():
                    documents.append(
                        Document(page_content=text, metadata={"source": path.name})
                    )
        return documents

    def _new_embeddings(self) -> LocalEmbeddings:
        return LocalEmbeddings()

    def _new_llm(self) -> DeepSeekLLM:
        client = OpenAI(
            api_key=self.deepseek_api_key,
            base_url=self.deepseek_base_url,
            timeout=60,
            max_retries=1,
        )
        return DeepSeekLLM(client=client, model_name=self.chat_model, temperature=0.2)

    def _has_existing_store(self) -> bool:
        return (INDEX_DIR / "index.faiss").exists() and (INDEX_DIR / "documents.json").exists()

    def _store_has_documents(self) -> bool:
        if self.vectorstore is None:
            return False
        try:
            return self.vectorstore.index is not None and self.vectorstore.index.ntotal > 0
        except Exception:
            return False

    def _is_key_missing(self, key: str) -> bool:
        return not key or key.startswith("在这里填写你的")

    def prepare(self) -> None:
        if self._is_key_missing(self.deepseek_api_key):
            raise ValueError("没有配置 DeepSeek API 密钥，请检查项目根目录 .env。")

        if self._has_existing_store():
            try:
                self.vectorstore = FaissVectorStore(
                    persist_directory=INDEX_DIR,
                    embedding=self._new_embeddings(),
                )
            except Exception:
                self.vectorstore = None
            if not self._store_has_documents():
                self.vectorstore = None
                shutil.rmtree(INDEX_DIR, ignore_errors=True)

        if self.vectorstore is None:
            if INDEX_DIR.exists():
                shutil.rmtree(INDEX_DIR, ignore_errors=True)
            documents = self.load_documents()
            if not documents:
                raise ValueError("data 文件夹没有 Markdown 或 txt 资料。")
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=CHUNK_SIZE,
                chunk_overlap=CHUNK_OVERLAP,
                separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
            )
            chunks = splitter.split_documents(documents)
            if not chunks:
                raise ValueError("资料切分后没有可用的文本片段。")
            self.vectorstore = FaissVectorStore.build_from_documents(
                documents=chunks,
                embedding=self._new_embeddings(),
                persist_directory=INDEX_DIR,
            )

        self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": TOP_K})
        self.llm = self._new_llm()

    def ask(self, question: str) -> dict:
        question = (question or "").strip()
        if not question:
            raise ValueError("问题不能为空。")
        if self.vectorstore is None or self.retriever is None or self.llm is None:
            raise ValueError("知识库还没有准备好，请先构建索引。")

        documents = self.retriever.invoke(question)
        if not documents:
            raise ValueError("没有找到与问题相关的资料片段。")

        context = "\n\n".join(
            f"【来源：{doc.metadata.get('source', '未知')}】\n{doc.page_content}"
            for doc in documents
        )
        prompt = (
            "你是人工智能学习资料问答助手。\n"
            "请优先根据下面的资料片段回答问题，不得编造资料里没有的内容。\n"
            "如果资料不足以回答，请明确说明。回答使用简体中文，尽量分点，简洁清楚。\n\n"
            f"资料片段：\n{context}\n\n问题：{question}"
        )
        answer = self.llm.invoke(prompt)
        if not answer or not answer.strip():
            raise ValueError("大模型返回了空回答，请稍后重试。")

        sources = [
            {
                "file": doc.metadata.get("source", "未知"),
                "excerpt": doc.page_content[:500],
            }
            for doc in documents
        ]
        return {"answer": answer.strip(), "sources": sources}

    def status_text(self) -> str:
        if self._is_key_missing(self.deepseek_api_key):
            return "知识库状态：缺少 DeepSeek API 密钥"
        if self.vectorstore is not None:
            return "知识库状态：已就绪"
        return "知识库状态：未构建，首次提问时会自动建立索引"
