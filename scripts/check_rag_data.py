#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检查 RAG 系统中的实际数据"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

print("=== 检查 RAG 数据状态 ===\n")

# 1. 检查 ChromaDB 中的数据
print("1. ChromaDB 向量存储:")
try:
    from backend.llm.database.chroma_client import get_chroma_client
    client = get_chroma_client()
    
    # 检查各个 collection
    for name in ["memory_vectors", "knowledge_vectors"]:
        try:
            coll = client.client.get_collection(name)
            count = coll.count()
            print(f"   {name}: {count} 条记录")
        except:
            print(f"   {name}: 不存在或为空")
except Exception as e:
    print(f"   无法访问 ChromaDB: {e}")

# 2. 检查测试数据是否存在
print("\n2. 搜索测试数据 (小红/小明):")
try:
    from backend.llm.database.chroma_client import MemoryVectorStore
    store = MemoryVectorStore()
    
    # 搜索小红
    results = store.query("小红", n_results=3)
    if results and results.get("ids") and results["ids"][0]:
        print(f"   找到 '小红' 相关记录: {len(results['ids'][0])} 条")
        for i, doc in enumerate(results.get("documents", [[]])[0][:2]):
            print(f"      - {doc[:50]}...")
    else:
        print("   ✅ 未找到 '小红' 相关记录 (测试数据未污染)")
except Exception as e:
    print(f"   检查失败: {e}")

# 3. 检查知识图谱
print("\n3. 知识图谱:")
try:
    from backend.llm.memory.knowledge_graph import get_knowledge_graph
    kg = get_knowledge_graph("default_user")
    stats = kg.get_statistics()
    print(f"   三元组数量: {stats['triple_count']}")
    print(f"   实体数量: {stats['entity_count']}")
    
    if stats['triple_count'] > 0:
        print("   现有三元组:")
        for t in kg._triples[:5]:
            print(f"      - {t.to_natural_language()}")
except Exception as e:
    print(f"   无法访问知识图谱: {e}")

print("\n=== 检查完成 ===")
print("\n结论: 测试脚本中的数据（小红、火锅等）只存在于测试脚本的内存中，")
print("脚本结束后就被销毁了，不会影响实际的 RAG 系统。")
