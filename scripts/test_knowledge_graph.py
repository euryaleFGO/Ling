#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试知识图谱功能
"""
import sys
import os

# 添加项目路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, "src"))

from backend.llm.memory.knowledge_graph import KnowledgeGraph, get_knowledge_graph
from backend.llm.memory.entity_extractor import EntityRelationExtractor


def test_knowledge_graph():
    """测试知识图谱基本功能"""
    print("=" * 60)
    print("测试知识图谱")
    print("=" * 60)
    
    # 创建知识图谱
    kg = KnowledgeGraph(user_id="test_user")
    
    # 测试 1: 添加三元组
    print("\n--- 测试 1: 添加三元组 ---")
    kg.add_triple("用户", "spouse", "小红", subject_type="person", obj_type="person")
    kg.add_triple("用户", "likes", "编程", subject_type="person", obj_type="concept")
    kg.add_triple("用户", "lives_in", "北京", subject_type="person", obj_type="place")
    kg.add_triple("小红", "likes", "苹果", subject_type="person", obj_type="object")
    kg.add_triple("小红", "works_at", "腾讯", subject_type="person", obj_type="organization")
    
    print(f"添加了 {len(kg._triples)} 个三元组")
    
    # 测试 2: 查询
    print("\n--- 测试 2: 查询 ---")
    
    # 查询用户的所有关系
    user_relations = kg.query_by_subject("用户")
    print(f"用户的关系 ({len(user_relations)} 条):")
    for t in user_relations:
        print(f"  - {t.to_natural_language()}")
    
    # 查询用户的配偶
    spouse = kg.query(subject="用户", relation="spouse")
    if spouse:
        print(f"\n用户的配偶: {spouse[0].obj.name}")
    
    # 查询谁喜欢苹果
    apple_lovers = kg.query(obj="苹果", relation="likes")
    print(f"\n喜欢苹果的人: {[t.subject.name for t in apple_lovers]}")
    
    # 测试 3: 相关实体
    print("\n--- 测试 3: 相关实体 (2跳) ---")
    related = kg.get_related_entities("用户", max_depth=2)
    print(f"与用户相关的实体: {related}")
    
    # 测试 4: 转换为上下文
    print("\n--- 测试 4: 上下文字符串 ---")
    context = kg.to_context_string()
    print(context)
    
    # 测试 5: 统计信息
    print("\n--- 测试 5: 统计 ---")
    stats = kg.get_statistics()
    print(f"三元组数量: {stats['triple_count']}")
    print(f"实体数量: {stats['entity_count']}")
    print(f"关系类型: {stats['relation_types']}")
    
    print("\n" + "=" * 60)


def test_entity_extractor():
    """测试实体关系提取器"""
    print("\n" + "=" * 60)
    print("测试实体关系提取器")
    print("=" * 60)
    
    extractor = EntityRelationExtractor()
    
    # 测试消息
    test_messages = [
        "我的老婆叫小红",
        "我住在北京市海淀区",
        "我喜欢吃火锅",
        "我在字节跳动工作",
        "我有一只猫叫咪咪",
        "我不喜欢加班",
        "我的朋友小明很聪明",
    ]
    
    print("\n--- 规则提取测试 ---")
    for msg in test_messages:
        result = extractor.extract(msg, use_llm=False)
        triples = result.get("triples", [])
        
        print(f"\n消息: {msg}")
        if triples:
            for t in triples:
                print(f"  提取: ({t['subject']}) --[{t['relation']}]--> ({t['object']})")
        else:
            print("  无法提取")
    
    print("\n" + "=" * 60)


def test_integration():
    """测试集成"""
    print("\n" + "=" * 60)
    print("测试知识图谱 + 提取器集成")
    print("=" * 60)
    
    kg = KnowledgeGraph(user_id="integration_test")
    extractor = EntityRelationExtractor()
    
    # 模拟对话
    messages = [
        "我叫张三，今年25岁",
        "我老婆叫李四，她在阿里巴巴工作",
        "我们住在杭州",
        "我喜欢打篮球和写代码",
        "李四喜欢看电影",
    ]
    
    print("\n--- 从对话中提取并构建知识图谱 ---")
    for msg in messages:
        print(f"\n用户: {msg}")
        result = extractor.extract(msg, use_llm=False)
        
        for triple in result.get("triples", []):
            kg.add_triple(
                subject=triple["subject"],
                relation=triple["relation"],
                obj=triple["object"],
                confidence=triple.get("confidence", 0.9)
            )
    
    # 显示构建的知识图谱
    print("\n--- 构建的知识图谱 ---")
    print(kg.to_context_string(max_triples=20))
    
    # 查询测试
    print("\n--- 查询测试 ---")
    
    # 用户的配偶是谁？
    spouse = kg.query(subject="用户", relation="spouse")
    if spouse:
        spouse_name = spouse[0].obj.name
        print(f"用户的配偶: {spouse_name}")
        
        # 配偶在哪工作？
        spouse_work = kg.query(subject=spouse_name, relation="works_at")
        if spouse_work:
            print(f"{spouse_name}工作于: {spouse_work[0].obj.name}")
        
        # 配偶喜欢什么？
        spouse_likes = kg.query(subject=spouse_name, relation="likes")
        if spouse_likes:
            print(f"{spouse_name}喜欢: {[t.obj.name for t in spouse_likes]}")
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    test_knowledge_graph()
    test_entity_extractor()
    test_integration()
