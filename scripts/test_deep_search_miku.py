"""
测试深度搜索：初音未来
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.backend.llm.tools.browser_search_tool import BrowserSearchTool

def test_deep_search_miku():
    """测试深度搜索：初音未来"""
    print("="*60)
    print("测试深度搜索：初音未来")
    print("="*60)
    
    tool = BrowserSearchTool(
        headless=False,
        manual_captcha=True,
        keep_alive=True,
        filter_ads=True
    )
    
    query = "初音未来"
    print(f"\n📝 搜索关键词: {query}")
    
    # 执行深度搜索，访问前5个结果
    result = tool.execute(
        query=query,
        action="deep_search",
        deep_search_count=5
    )
    
    if result.success:
        data = result.data
        print("\n" + "="*60)
        print("✅ 深度搜索成功")
        print("="*60)
        print(f"搜索到: {data['total_searched']} 个结果")
        print(f"访问了: {data['visited_count']} 个页面")
        print(f"成功: {data['successful_count']} 个，失败: {data['failed_count']} 个")
        
        print("\n" + "="*60)
        print("提取内容统计:")
        print("="*60)
        
        total_chars = 0
        for page in data['extracted_pages']:
            if "error" not in page:
                total_chars += page['content_length']
                print(f"✅ [{page['index']}] {page['title']}")
                print(f"   {page['content_length']} 字符")
            else:
                print(f"❌ [{page['index']}] {page['title']}")
                print(f"   {page['error']}")
        
        print(f"\n📊 总共提取了 {total_chars} 字符的内容")
        
    else:
        print(f"\n❌ 失败: {result.error}")

if __name__ == "__main__":
    test_deep_search_miku()
