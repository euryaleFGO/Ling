"""
测试深度搜索功能
访问多个搜索结果页面
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.backend.llm.tools.browser_search_tool import BrowserSearchTool

def test_deep_search():
    """测试深度搜索"""
    print("="*60)
    print("测试深度搜索功能")
    print("="*60)
    
    # 创建工具实例（非无头模式，可以看到浏览器操作）
    tool = BrowserSearchTool(
        headless=False,
        manual_captcha=True,  # 启用手动验证码处理
        keep_alive=True,       # 保持浏览器打开
        filter_ads=True        # 过滤广告
    )
    
    # 测试查询
    query = "Python asyncio 异步编程"
    print(f"\n📝 搜索关键词: {query}")
    print(f"🔍 将访问前 3 个搜索结果...")
    
    # 执行深度搜索
    result = tool.execute(
        query=query,
        action="deep_search",
        deep_search_count=3  # 访问前3个结果
    )
    
    if result.success:
        data = result.data
        print("\n" + "="*60)
        print("✅ 深度搜索成功")
        print("="*60)
        print(f"搜索关键词: {data['query']}")
        print(f"搜索到的结果数: {data['total_searched']}")
        print(f"尝试访问页面数: {data['visited_count']}")
        print(f"成功提取页面数: {data['successful_count']}")
        print(f"失败页面数: {data['failed_count']}")
        
        # 显示搜索结果列表
        print("\n" + "-"*60)
        print("所有搜索结果:")
        print("-"*60)
        for i, result in enumerate(data['search_results'], 1):
            print(f"\n{i}. {result['title']}")
            print(f"   URL: {result['url']}")
            if result.get('snippet'):
                print(f"   摘要: {result['snippet'][:100]}...")
        
        # 显示提取的页面内容
        print("\n" + "="*60)
        print("已提取的页面内容:")
        print("="*60)
        
        for page in data['extracted_pages']:
            print("\n" + "-"*60)
            print(f"[{page['index']}] {page['title']}")
            print(f"URL: {page['url']}")
            
            if "error" in page:
                print(f"❌ 提取失败: {page['error']}")
            else:
                print(f"✅ 内容长度: {page['content_length']} 字符")
                # 显示前200字符预览
                preview = page['content'][:200].replace('\n', ' ')
                print(f"内容预览: {preview}...")
        
    else:
        print(f"\n❌ 深度搜索失败: {result.error}")

if __name__ == "__main__":
    test_deep_search()
