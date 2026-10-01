#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""NEWRAG 基础测试，不调用外部 API。"""

import os

# Allow funasr/torch and fastembed to load different OpenMP runtimes in tests.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain.schema import Document
from langchain_core.embeddings import Embeddings

import rag_engine
from rag_engine import DATA_DIR, FaissVectorStore, RagEngine


class FakeEmbeddings(Embeddings):
    """不调用网络的假向量模型，只用于本地测试。"""

    def __init__(self, size: int = 8) -> None:
        self.size = size

    def embed_documents(self, texts: list) -> list:
        vectors = []
        for index, _ in enumerate(texts):
            vector = [0.0] * self.size
            vector[index % self.size] = 1.0
            vectors.append(vector)
        return vectors

    def embed_query(self, text: str) -> list:
        vector = [0.0] * self.size
        vector[0] = 1.0
        return vector


class RagEngineTest(unittest.TestCase):
    def setUp(self):
        self.engine = RagEngine()

    def test_knowledge_base_has_four_module_directories(self):
        expected_modules = [
            "01_核心技术栈",
            "02_场景设计题",
            "03_通用软技能",
            "04_公司风格库",
        ]
        for module in expected_modules:
            self.assertTrue((DATA_DIR / module).is_dir(), module)

    def test_load_documents_finds_data_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "sample.md").write_text("测试内容", encoding="utf-8")
            with patch.object(rag_engine, "DATA_DIR", Path(temp_dir)):
                documents = self.engine.load_documents()
        self.assertEqual(len(documents), 1)

    def test_empty_question_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.ask("   ")

    def test_faiss_build_and_retrieve(self):
        documents = [
            Document(page_content="Transformer 使用自注意力机制", metadata={"source": "a.md"}),
            Document(page_content="卷积神经网络处理图像", metadata={"source": "b.md"}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FaissVectorStore.build_from_documents(
                documents=documents,
                embedding=FakeEmbeddings(),
                persist_directory=Path(temp_dir),
            )
            self.assertEqual(store.index.ntotal, 2)
            results = store.as_retriever(search_kwargs={"k": 1}).invoke("Transformer")
            self.assertEqual(len(results), 1)
            self.assertIn("自注意力", results[0].page_content)

    def test_missing_deepseek_key_message(self):
        self.engine.deepseek_api_key = ""
        with self.assertRaises(ValueError):
            self.engine.prepare()

    def test_placeholder_deepseek_key_message(self):
        self.engine.deepseek_api_key = "在这里填写你的DeepSeek密钥"
        with self.assertRaises(ValueError):
            self.engine.prepare()


if __name__ == "__main__":
    unittest.main()
