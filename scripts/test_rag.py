#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 RAG Pipeline
"""
import sys
import os

# 添加项目路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, "src"))

from backend.llm.rag import (
    RAGPipeline, RAGConfig, get_rag_pipeline,
    QueryProcessor, QueryIntent,
    HybridRetriever, RetrievalSource,
    ContextBuilder
)


def test_query_processor():
    """测试查询处理器"""
    print("=" * 60)
    print("测试查询处理器")
    print("=" * 60)
    
    processor = QueryProcessor()
    
    test_queries = [
        "用户的妻子是谁？",
        "用户喜欢吃什么？",
        "用户住在哪里？",
        "用户今天做了什么？",
        "用户心情怎么样？",
        "你好呀",
        "Python 是什么？",
    ]
    
    for query in test_queries:
        result = processor.process(query)
        print(f"\n查询: {query}")
        print(f"  意图: {result.intent.value} (置信度: {result.confidence:.2f})")
        print(f"  关键词: {result.keywords}")
        print(f"  需要检索: {processor.should_retrieve(result)}")
    
    print("\n" + "=" * 60)


def test_bm25():
    """测试 BM25 检索"""
    print("\n" + "=" * 60)
    print("测试 BM25 检索")
    print("=" * 60)
    
    from backend.llm.rag.retriever import BM25
    
    bm25 = BM25()
    
    # 添加测试文档
    docs = {
        "doc1": "用户喜欢吃火锅和烧烤",
        "doc2": "用户住在北京市海淀区",
        "doc3": "用户的妻子叫小红",
        "doc4": "小红喜欢吃苹果",
        "doc5": "用户在字节跳动工作",
        "doc6": "用户养了一只猫叫咪咪",
        "doc7": "用户喜欢打篮球和写代码",
    }
    
    bm25.add_documents(docs)
    
    # 测试搜索
    queries = ["用户喜欢", "小红", "工作", "猫"]
    
    for query in queries:
        results = bm25.search(query, top_k=3)
        print(f"\n查询: {query}")
        for doc_id, score in results:
            print(f"  {doc_id}: {docs[doc_id][:30]}... (分数: {score:.3f})")
    
    print("\n" + "=" * 60)


def test_hybrid_retriever():
    """测试混合检索器"""
    print("\n" + "=" * 60)
    print("测试混合检索器")
    print("=" * 60)
    
    retriever = HybridRetriever(user_id="test_user")
    
    # 添加测试文档
    test_docs = [
        ("mem1", "用户喜欢吃火锅和烧烤", {"type": "preference", "importance": 0.8}),
        ("mem2", "用户住在北京市海淀区", {"type": "fact", "importance": 0.9}),
        ("mem3", "用户的妻子叫小红", {"type": "fact", "importance": 1.0}),
        ("mem4", "小红喜欢吃苹果和香蕉", {"type": "fact", "importance": 0.7}),
        ("mem5", "用户在字节跳动工作", {"type": "fact", "importance": 0.8}),
        ("mem6", "用户养了一只猫叫咪咪", {"type": "fact", "importance": 0.6}),
        ("mem7", "用户喜欢打篮球和写代码", {"type": "preference", "importance": 0.7}),
        ("mem8", "用户讨厌加班", {"type": "preference", "importance": 0.6}),
    ]
    
    for doc_id, content, metadata in test_docs:
        retriever.index_document(doc_id, content, RetrievalSource.MEMORY, metadata)
    
    print(f"索引统计: {retriever.get_statistics()}")
    
    # 测试检索
    queries = [
        "用户喜欢什么",
        "小红喜欢什么",
        "用户在哪工作",
        "用户有宠物吗",
    ]
    
    for query in queries:
        print(f"\n查询: {query}")
        results = retriever.retrieve(
            query=query,
            sources=[RetrievalSource.MEMORY],
            top_k=3,
            use_vector=False,  # 只用 BM25（因为向量存储可能未初始化）
            use_keyword=True,
        )
        
        for r in results:
            print(f"  [{r.doc_id}] {r.content} (分数: {r.score:.3f})")
    
    print("\n" + "=" * 60)


def test_context_builder():
    """测试上下文构建器"""
    print("\n" + "=" * 60)
    print("测试上下文构建器")
    print("=" * 60)
    
    from backend.llm.rag.retriever import RetrievalResult
    
    builder = ContextBuilder()
    
    # 创建测试结果
    results = [
        RetrievalResult(
            doc_id="1",
            content="用户喜欢吃火锅和烧烤",
            source=RetrievalSource.MEMORY,
            score=0.9,
            metadata={"type": "preference"}
        ),
        RetrievalResult(
            doc_id="2",
            content="用户的妻子叫小红",
            source=RetrievalSource.KNOWLEDGE_GRAPH,
            score=0.85,
            metadata={"type": "fact"}
        ),
        RetrievalResult(
            doc_id="3",
            content="用户住在北京",
            source=RetrievalSource.MEMORY,
            score=0.7,
            metadata={"type": "fact"}
        ),
    ]
    
    # 测试不同格式
    processor = QueryProcessor()
    query = processor.process("用户喜欢什么？")
    
    print("\n--- 自然语言格式 ---")
    context = builder.build(results, query)
    print(context)
    
    print("\n--- 结构化格式 ---")
    from backend.llm.rag.context_builder import ContextConfig
    config = ContextConfig(format_style="structured")
    context = builder.build(results, query, config=config)
    print(context)
    
    print("\n" + "=" * 60)


def test_rag_pipeline():
    """测试完整 RAG Pipeline"""
    print("\n" + "=" * 60)
    print("测试 RAG Pipeline")
    print("=" * 60)
    
    # 创建 pipeline
    config = RAGConfig(
        enable_vector_search=False,  # 只用关键词搜索
        enable_keyword_search=True,
        enable_knowledge_graph=True,
    )
    
    pipeline = RAGPipeline(user_id="test_rag_user", config=config)
    
    # 手动添加一些测试数据
    test_memories = [
        ("mem1", "用户喜欢吃火锅和烧烤", {"type": "preference", "importance": 0.8}),
        ("mem2", "用户住在北京市海淀区", {"type": "fact", "importance": 0.9}),
        ("mem3", "用户的妻子叫小红", {"type": "fact", "importance": 1.0}),
        ("mem4", "小红喜欢吃苹果", {"type": "fact", "importance": 0.7}),
        ("mem5", "用户在字节跳动工作", {"type": "fact", "importance": 0.8}),
    ]
    
    for doc_id, content, metadata in test_memories:
        pipeline.add_memory(doc_id, content, metadata)
    
    # 测试检索
    queries = [
        "用户喜欢吃什么？",
        "用户的妻子是谁？",
        "用户在哪里工作？",
        "你好",  # 闲聊，不应检索
    ]
    
    for query in queries:
        print(f"\n查询: {query}")
        response = pipeline.retrieve_context(query)
        
        print(f"  意图: {response.query.intent.value}")
        print(f"  结果数: {len(response.results)}")
        print(f"  耗时: {response.total_time_ms:.1f}ms")
        
        if response.context:
            print(f"  上下文:")
            for line in response.context.split("\n")[:5]:
                print(f"    {line}")
    
    # 统计信息
    print(f"\n统计: {pipeline.get_statistics()}")
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    test_query_processor()
    test_bm25()
    test_hybrid_retriever()
    test_context_builder()
    test_rag_pipeline()
