"""
浏览器搜索工具
使用 Playwright 自动控制浏览器进行网络搜索并阅读内容
"""
import asyncio
import re
from typing import List, Optional
from .base_tool import BaseTool, ToolParameter, ToolResult

# 延迟导入 Playwright
_playwright_available = None


def _check_playwright():
    """检查 Playwright 是否可用"""
    global _playwright_available
    if _playwright_available is None:
        try:
            from playwright.sync_api import sync_playwright
            _playwright_available = True
        except ImportError:
            _playwright_available = False
    return _playwright_available


class BrowserSearchTool(BaseTool):
    """
    浏览器搜索工具
    
    使用 Playwright 自动打开 Edge 浏览器，在 Bing 上搜索，并读取网页内容
    """
    
    def __init__(self, headless: bool = False, timeout: int = 30000, manual_captcha: bool = True):
        """
        Args:
            headless: 是否无头模式（False = 可视化浏览器窗口）
            timeout: 超时时间（毫秒）
            manual_captcha: 遇到人机验证时是否暂停等待手动处理（True = 等待手动，False = 自动尝试）
        """
        self._headless = headless
        self._timeout = timeout
        self._manual_captcha = manual_captcha
        self._browser = None
        self._playwright = None
    
    @property
    def name(self) -> str:
        return "browser_search"
    
    @property
    def description(self) -> str:
        return """使用浏览器自动搜索网络信息并阅读网页内容。
当用户询问以下问题时使用：
- 需要实时搜索网络获取最新信息
- 需要查找特定网站的内容
- 需要阅读在线文档或网页
- 搜索新闻、技术文章、产品信息等

此工具会打开 Edge 浏览器，自动在 Bing 搜索引擎中搜索，并提取搜索结果或网页内容。"""
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type="string",
                description="搜索关键词或要访问的 URL",
                required=True
            ),
            ToolParameter(
                name="action",
                type="string",
                description="操作类型：search（搜索）、read（阅读指定URL）、extract（搜索并提取第一个结果的内容）",
                required=False,
                enum=["search", "read", "extract"],
                default="search"
            ),
            ToolParameter(
                name="max_results",
                type="number",
                description="最大返回结果数（仅搜索时有效）",
                required=False,
                default=5
            )
        ]
    
    def _ensure_browser(self):
        """确保浏览器已启动"""
        if not _check_playwright():
            raise RuntimeError(
                "Playwright 未安装。请运行以下命令安装：\n"
                "pip install playwright\n"
                "playwright install msedge"
            )
        
        if self._browser is None:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            # 使用 Edge 浏览器
            try:
                self._browser = self._playwright.chromium.launch(
                    headless=self._headless,
                    channel="msedge",  # 使用 Microsoft Edge
                    args=['--disable-blink-features=AutomationControlled']
                )
            except Exception:
                # 如果 Edge 不可用，尝试使用 Chromium
                self._browser = self._playwright.chromium.launch(
                    headless=self._headless,
                    args=['--disable-blink-features=AutomationControlled']
                )
    
    def _close_browser(self):
        """关闭浏览器"""
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
    
    def _detect_captcha(self, page) -> bool:
        """
        检测页面是否出现人机验证
        
        Returns:
            True = 检测到验证，False = 未检测到
        """
        captcha_indicators = [
            # 常见的验证码选择器
            "#captcha",
            ".captcha",
            "iframe[src*='captcha']",
            "iframe[src*='recaptcha']",
            "iframe[title*='reCAPTCHA']",
            ".geetest_radar_tip",  # 极验滑块
            "#nc_1_wrapper",  # 阿里云滑块
            ".yidun",  # 网易易盾
            ".tcaptcha",  # 腾讯验证码
            "[id*='verify']",
            "[class*='verify']",
            "[id*='slider']",
            "[class*='slider']",
        ]
        
        for selector in captcha_indicators:
            try:
                if page.locator(selector).count() > 0:
                    return True
            except:
                continue
        
        # 检测页面文本中的验证提示
        try:
            body_text = page.locator("body").inner_text().lower()
            captcha_keywords = [
                "验证", "captcha", "verification", "人机", 
                "滑块", "slider", "拖动", "点击验证", "请完成安全验证"
            ]
            for keyword in captcha_keywords:
                if keyword in body_text:
                    return True
        except:
            pass
        
        return False
    
    def _handle_captcha(self, page, operation: str = "搜索") -> bool:
        """
        处理人机验证
        
        Args:
            page: Playwright 页面对象
            operation: 操作描述（用于日志）
        
        Returns:
            True = 验证已处理，False = 验证处理失败
        """
        print(f"\n⚠️  检测到人机验证！")
        
        # 尝试自动关闭一些弹窗
        close_selectors = [
            "button:has-text('关闭')",
            "button:has-text('×')",
            ".close",
            "[aria-label='关闭']",
            "[aria-label='Close']",
        ]
        
        for selector in close_selectors:
            try:
                close_btn = page.locator(selector).first
                if close_btn.count() > 0 and close_btn.is_visible():
                    close_btn.click()
                    print(f"✅ 已尝试关闭弹窗")
                    page.wait_for_timeout(1000)
                    return True
            except:
                continue
        
        if self._manual_captcha:
            # 手动处理模式：暂停等待用户操作
            print(f"🔔 请在浏览器窗口中手动完成验证")
            print(f"   等待时间：最多 {self._timeout // 1000} 秒")
            print(f"   完成验证后，页面将自动继续...")
            
            # 等待验证完成（通过检测验证元素消失或URL变化）
            try:
                # 等待一段时间，让用户完成验证
                page.wait_for_timeout(min(60000, self._timeout))  # 最多等待60秒
                
                # 检查验证是否消失
                if not self._detect_captcha(page):
                    print(f"✅ 验证已完成，继续{operation}")
                    return True
                else:
                    print(f"⚠️  验证仍存在，尝试继续...")
                    return False
            except:
                return False
        else:
            # 自动处理模式：尝试一些简单的自动化操作
            print(f"🤖 尝试自动处理验证...")
            
            # 尝试查找并点击滑块
            slider_selectors = [
                ".nc_iconfont",  # 阿里云滑块
                ".geetest_slider_button",  # 极验滑块
                "#nc_1_n1z",
                "[class*='slide']",
            ]
            
            for selector in slider_selectors:
                try:
                    slider = page.locator(selector).first
                    if slider.count() > 0 and slider.is_visible():
                        print(f"🔍 发现滑块，尝试拖动...")
                        
                        # 获取滑块的边界框
                        box = slider.bounding_box()
                        if box:
                            # 从滑块起始位置拖动到终点
                            page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                            page.mouse.down()
                            # 模拟人类拖动：随机速度和轨迹
                            import random
                            distance = 300  # 滑动距离
                            steps = random.randint(20, 30)
                            for i in range(steps):
                                offset = distance * (i + 1) / steps
                                jitter = random.randint(-2, 2)
                                page.mouse.move(
                                    box['x'] + box['width'] / 2 + offset,
                                    box['y'] + box['height'] / 2 + jitter,
                                )
                                page.wait_for_timeout(random.randint(10, 30))
                            page.mouse.up()
                            page.wait_for_timeout(2000)
                            
                            if not self._detect_captcha(page):
                                print(f"✅ 自动验证成功！")
                                return True
                except Exception as e:
                    print(f"   滑块处理失败: {str(e)}")
                    continue
            
            print(f"❌ 自动验证失败，可能需要手动处理")
            return False
    
    def _search_bing(self, query: str, max_results: int = 5) -> dict:
        """
        在 Bing 上搜索
        
        Returns:
            搜索结果字典
        """
        self._ensure_browser()
        
        context = self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        )
        page = context.new_page()
        page.set_default_timeout(self._timeout)
        
        try:
            # 访问 Bing
            page.goto("https://www.bing.com")
            
            # 等待搜索框并输入
            search_box = page.locator('input[name="q"]')
            search_box.fill(query)
            search_box.press("Enter")
            
            # 等待搜索结果加载
            page.wait_for_selector("#b_results", timeout=self._timeout)
            
            # 提取搜索结果
            results = []
            result_items = page.locator("#b_results .b_algo").all()
            
            for i, item in enumerate(result_items[:max_results]):
                try:
                    title_elem = item.locator("h2 a").first
                    title = title_elem.inner_text() if title_elem.count() > 0 else ""
                    url = title_elem.get_attribute("href") if title_elem.count() > 0 else ""
                    
                    # 获取描述
                    desc_elem = item.locator(".b_caption p").first
                    description = desc_elem.inner_text() if desc_elem.count() > 0 else ""
                    
                    if title and url:
                        results.append({
                            "index": i + 1,
                            "title": title,
                            "url": url,
                            "description": description
                        })
                except Exception:
                    continue
            
            return {
                "query": query,
                "result_count": len(results),
                "results": results
            }
        finally:
            context.close()
    
    def _read_page(self, url: str) -> dict:
        """
        读取网页内容
        
        Returns:
            页面内容字典
        """
        self._ensure_browser()
        
        context = self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        )
        page = context.new_page()
        page.set_default_timeout(self._timeout)
        
        try:
            # 检测是否有人机验证
            if self._detect_captcha(page):
                if not self._handle_captcha(page, "阅读"):
                    raise RuntimeError("人机验证未通过，无法继续读取内容")
                # 验证通过后，等待页面稳定
                page.wait_for_timeout(1000)
            
            # 
            # 使用 networkidle 等待页面完全加载
            page.goto(url, wait_until="networkidle", timeout=self._timeout)
            
            # 等待一小段时间确保页面稳定
            page.wait_for_timeout(1000)
            
            # 获取页面标题
            title = page.title()
            
            # 提取主要文本内容
            # 移除脚本、样式等无关元素
            page.evaluate("""
                document.querySelectorAll('script, style, nav, footer, header, aside, iframe, noscript').forEach(el => el.remove());
            """)
            
            # 获取正文内容
            content = ""
            
            # 尝试获取主要内容区域
            main_selectors = [
                "article", "main", ".content", "#content", 
                ".post-content", ".article-content", ".entry-content",
                "[role='main']"
            ]
            
            for selector in main_selectors:
                elem = page.locator(selector).first
                if elem.count() > 0:
                    content = elem.inner_text()
                    break
            
            # 如果没有找到主要内容区域，获取 body 文本
            if not content:
                content = page.locator("body").inner_text()
            
            # 清理内容：移除多余空白、限制长度
            content = re.sub(r'\n\s*\n', '\n\n', content)  # 多个空行变成两个
            content = re.sub(r'[ \t]+', ' ', content)  # 多个空格变成一个
            content = content.strip()
            
            # 限制内容长度（避免太长）
            max_length = 8000
            if len(content) > max_length:
                content = content[:max_length] + "\n\n... [内容已截断]"
            
            return {
                "url": url,
                "title": title,
                "content": content,
                "content_length": len(content)
            }
        finally:
            context.close()
    
    def _search_and_extract(self, query: str) -> dict:
        """
        搜索并提取第一个结果的内容
        
        Returns:
            搜索结果 + 第一个结果的内容
        """
        # 先搜索
        search_result = self._search_bing(query, max_results=3)
        
        if not search_result["results"]:
            return {
                "query": query,
                "error": "没有找到搜索结果"
            }
        
        # 读取第一个结果
        first_url = search_result["results"][0]["url"]
        first_title = search_result["results"][0]["title"]
        
        try:
            page_content = self._read_page(first_url)
            return {
                "query": query,
                "search_results": search_result["results"],
                "extracted_content": {
                    "title": first_title,
                    "url": first_url,
                    "content": page_content["content"]
                }
            }
        except Exception as e:
            return {
                "query": query,
                "search_results": search_result["results"],
                "extract_error": f"读取页面失败: {str(e)}"
            }
    
    def execute(self, query: str, action: str = "search", max_results: int = 5, **kwargs) -> ToolResult:
        """
        执行浏览器操作
        """
        if not _check_playwright():
            return ToolResult(
                success=False,
                error="Playwright 未安装。请运行以下命令安装：\npip install playwright\nplaywright install msedge"
            )
        
        try:
            if action == "search":
                # 搜索模式
                result = self._search_bing(query, max_results)
                return ToolResult(success=True, data=result)
            
            elif action == "read":
                # 阅读模式（query 作为 URL）
                if not query.startswith("http"):
                    query = "https://" + query
                result = self._read_page(query)
                return ToolResult(success=True, data=result)
            
            elif action == "extract":
                # 搜索并提取
                result = self._search_and_extract(query)
                return ToolResult(success=True, data=result)
            
            else:
                return ToolResult(
                    success=False,
                    error=f"未知操作类型: {action}"
                )
        
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"浏览器操作失败: {str(e)}"
            )
        finally:
            # 操作完成后关闭浏览器（可选：保持开启以加速后续操作）
            # self._close_browser()
            pass
    
    def __del__(self):
        """析构时关闭浏览器"""
        self._close_browser()
