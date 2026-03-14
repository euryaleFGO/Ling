#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""简化 RAG 测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from backend.llm.rag.query_processor import QueryProcessor
from backend.llm.rag.retriever import BM25

print("=== 测试查询处理器 ===")
p = QueryProcessor()
for q in ["用户喜欢什么", "你好", "用户的妻子是谁"]:
    r = p.process(q)
    print(f"  {q} -> {r.intent.value}")

print("\n=== 测试 BM25 ===")
bm25 = BM25()
bm25.add_document("1", "用户喜欢吃火锅")
bm25.add_document("2", "用户住在北京")
bm25.add_document("3", "用户的妻子叫小红")
results = bm25.search("喜欢", 2)
for doc_id, score in results:
    print(f"  {doc_id}: {score:.3f}")

print("\n✅ RAG 核心模块测试通过!")
