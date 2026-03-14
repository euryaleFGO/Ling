#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试浏览器搜索工具
"""
import sys
import os

# 添加项目路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, "src"))

from backend.llm.tools import BrowserSearchTool


def test_search():
    """测试搜索功能"""
    print("=" * 60)
    print("测试浏览器搜索工具")
    print("=" * 60)
    
    # 创建工具实例（显示浏览器窗口）
    tool = BrowserSearchTool(headless=False, timeout=30000)
    
    # 测试 1: 搜索
    print("\n--- 测试 1: 搜索 ---")
    result = tool.execute(
        query="Python Playwright 教程",
        action="search",
        max_results=3
    )
    
    if result.success:
        print(f"✅ 搜索成功!")
        print(f"查询: {result.data['query']}")
        print(f"结果数: {result.data['result_count']}")
        for r in result.data['results']:
            print(f"  [{r['index']}] {r['title']}")
            print(f"      URL: {r['url'][:60]}...")
    else:
        print(f"❌ 搜索失败: {result.error}")
    
    # 测试 2: 读取网页
    print("\n--- 测试 2: 读取网页 ---")
    result2 = tool.execute(
        query="https://www.baidu.com",
        action="read"
    )
    
    if result2.success:
        print(f"✅ 读取成功!")
        print(f"标题: {result2.data['title']}")
        print(f"内容长度: {result2.data['content_length']} 字符")
        print(f"内容预览: {result2.data['content'][:200]}...")
    else:
        print(f"❌ 读取失败: {result2.error}")
    
    # 测试 3: 搜索并提取
    print("\n--- 测试 3: 搜索并提取第一个结果 ---")
    result3 = tool.execute(
        query="什么是 AI Agent",
        action="extract"
    )
    
    if result3.success:
        print(f"✅ 提取成功!")
        if "extracted_content" in result3.data:
            extracted = result3.data['extracted_content']
            print(f"标题: {extracted['title']}")
            print(f"URL: {extracted['url']}")
            print(f"内容预览: {extracted['content'][:300]}...")
        elif "extract_error" in result3.data:
            print(f"⚠️ 提取警告: {result3.data['extract_error']}")
            print("搜索结果:")
            for r in result3.data['search_results']:
                print(f"  [{r['index']}] {r['title']}")
    else:
        print(f"❌ 提取失败: {result3.error}")
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    test_search()
