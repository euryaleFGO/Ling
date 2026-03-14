"""
浏览器搜索工具（增强版 - 支持实时人机验证检测）
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
    浏览器搜索工具（增强版）
    
    使用 Playwright 自动打开 Edge 浏览器，在 Bing 上搜索，并读取网页内容
    支持实时检测和处理人机验证（滑块、点击验证等）
    """
    
    def __init__(self, headless: bool = False, timeout: int = 30000, manual_captcha: bool = True, keep_alive: bool = True, keep_alive_duration: int = 5000, filter_ads: bool = True):
        """
        Args:
            headless: 是否无头模式（False = 可视化浏览器窗口）
            timeout: 超时时间（毫秒）
            manual_captcha: 遇到人机验证时是否暂停等待手动处理（True = 等待手动，False = 自动尝试）
            keep_alive: 操作完成后是否保持浏览器打开（True = 保持打开，False = 立即关闭）
            keep_alive_duration: 保持浏览器打开的时长（毫秒），仅当keep_alive=True时有效
            filter_ads: 是否过滤广告结果（True = 过滤，False = 不过滤）
        """
        self._headless = headless
        self._timeout = timeout
        self._manual_captcha = manual_captcha
        self._keep_alive = keep_alive
        self._keep_alive_duration = keep_alive_duration
        self._filter_ads = filter_ads
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

此工具会打开 Edge 浏览器，自动在 Bing 搜索引擎中搜索，并提取搜索结果或网页内容。
支持实时检测和处理人机验证（滑块、点击验证等）。"""
    
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
                description="操作类型：search（搜索）、read（阅读指定URL）、extract（搜索并提取第一个结果的内容）、deep_search（深度搜索：访问前N个结果并汇总）",
                required=False,
                enum=["search", "read", "extract", "deep_search"],
                default="search"
            ),
            ToolParameter(
                name="max_results",
                type="number",
                description="最大返回结果数（搜索和深度搜索时有效）",
                required=False,
                default=5
            ),
            ToolParameter(
                name="deep_search_count",
                type="number",
                description="深度搜索时访问的网页数量（仅deep_search模式有效，默认3）",
                required=False,
                default=3
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
        处理人机验证（实时检测版）
        
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
            # 手动处理模式：实时检测用户操作
            print(f"🔔 请在浏览器窗口中手动完成验证")
            print(f"   程序会实时检测验证状态（每0.5秒检查一次）")
            print(f"   完成验证后会自动继续，无需等待！")
            print(f"   最长等待: {self._timeout // 1000} 秒")
            
            # 实时检测验证完成状态
            try:
                max_wait = min(60000, self._timeout)  # 最多等待60秒
                check_interval = 500  # 每500毫秒检查一次
                waited = 0
                original_url = page.url
                
                while waited < max_wait:
                    try:
                        # 等待一小段时间
                        page.wait_for_timeout(check_interval)
                        waited += check_interval
                    except Exception as e:
                        # 页面或浏览器被关闭
                        error_msg = str(e).lower()
                        if any(kw in error_msg for kw in ["closed", "target closed", "browser", "context"]):
                            print(f"\n⚠️  浏览器窗口或页面已被关闭")
                            return False
                        raise
                    
                    # 检查验证是否消失
                    try:
                        if not self._detect_captcha(page):
                            print(f"\n✅ 检测到验证已完成！（耗时 {waited/1000:.1f} 秒）")
                            print(f"✅ 继续{operation}...")
                            page.wait_for_timeout(1000)  # 额外等待1秒确保页面稳定
                            return True
                    except Exception as e:
                        error_msg = str(e).lower()
                        if any(kw in error_msg for kw in ["closed", "target closed"]):
                            print(f"\n⚠️  页面在验证过程中被关闭")
                            return False
                    
                    # 检查URL是否发生变化（可能已跳转）
                    try:
                        current_url = page.url
                        if current_url != original_url:
                            print(f"\n✅ 检测到页面跳转（验证可能已完成）")
                            page.wait_for_timeout(1000)
                            if not self._detect_captcha(page):
                                print(f"✅ 确认验证已完成，继续{operation}...")
                                return True
                    except:
                        pass
                    
                    # 每5秒提示一次进度
                    if waited % 5000 == 0:
                        remaining = (max_wait - waited) / 1000
                        print(f"⏳ 仍在等待验证... (剩余 {remaining:.0f} 秒)")
                
                # 超时后最后检查一次
                print(f"\n⏱️  等待超时，最后检查验证状态...")
                if not self._detect_captcha(page):
                    print(f"✅ 验证已完成，继续{operation}")
                    return True
                else:
                    print(f"⚠️  验证仍存在，尝试继续...")
                    return False
            except Exception as e:
                print(f"\n❌ 验证检测异常: {str(e)[:100]}")
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
            
            # 额外等待确保内容完全渲染
            page.wait_for_timeout(2000)
            
            # 检测是否有人机验证
            if self._detect_captcha(page):
                if not self._handle_captcha(page, "搜索"):
                    raise RuntimeError("人机验证未通过，无法继续搜索")
                # 验证通过后，可能需要重新等待结果
                page.wait_for_selector("#b_results", timeout=self._timeout)
                page.wait_for_timeout(2000)
            
            # 提取搜索结果（获取更多以应对广告过滤）
            results = []
            result_items = page.locator("#b_results .b_algo").all()
            
            # 最多遍历max_results * 2个结果，确保过滤广告后仍有足够结果
            for i, item in enumerate(result_items[:max_results * 2]):
                # 如果已经获得足够的有效结果，停止
                if len(results) >= max_results:
                    break
                
                try:
                    # 检查是否为广告（如果启用了过滤）
                    if self._filter_ads:
                        # 广告通常有特殊的class或属性
                        item_html = item.get_attribute("class") or ""
                        if "b_ad" in item_html.lower() or "b_adlabel" in item_html.lower():
                            print(f"⚠️  跳过广告结果 {i+1}")
                            continue
                    
                    # 使用多种方法尝试获取标题和URL
                    title = ""
                    url = ""
                    
                    # 方法1: 尝试 h2 a
                    title_elem = item.locator("h2 a").first
                    if title_elem.count() > 0:
                        title = title_elem.text_content() or title_elem.inner_text() or ""
                        title = title.strip()
                        url = title_elem.get_attribute("href") or ""
                    
                    # 方法2: 如果标题为空，尝试直接获取 h2
                    if not title:
                        h2_elem = item.locator("h2").first
                        if h2_elem.count() > 0:
                            title = h2_elem.text_content() or h2_elem.inner_text() or ""
                            title = title.strip()
                    
                    # 方法3: 如果URL为空，尝试找第一个有效链接
                    if not url:
                        links = item.locator("a[href]").all()
                        for link in links:
                            href = link.get_attribute("href")
                            if href and (href.startswith("http://") or href.startswith("https://")):
                                url = href
                                break
                    
                    # 过滤广告URL（如果启用了过滤）
                    if self._filter_ads and url:
                        ad_indicators = [
                            "click.linksynergy.com",
                            "aff.",
                            "affiliate",
                            "/aclk?",
                            "googlesyndication",
                            "doubleclick",
                            "&ad_",
                            "msads",
                        ]
                        if any(indicator in url.lower() for indicator in ad_indicators):
                            print(f"⚠️  跳过广告链接: {url[:50]}...")
                            continue
                    
                    # 获取描述
                    description = ""
                    desc_elem = item.locator(".b_caption p").first
                    if desc_elem.count() > 0:
                        description = desc_elem.text_content() or desc_elem.inner_text() or ""
                        description = description.strip()
                    
                    # 只有标题和URL都不为空时才添加
                    if title and url:
                        results.append({
                            "index": len(results) + 1,  # 使用实际索引而不是循环索引
                            "title": title,
                            "url": url,
                            "description": description
                        })
                except Exception as e:
                    # 调试：打印错误
                    print(f"⚠️  提取第 {i+1} 个结果时出错: {str(e)[:100]}")
                    continue
            
            return {
                "query": query,
                "result_count": len(results),
                "results": results
            }
        finally:
            if not self._keep_alive:
                context.close()
            else:
                # 保持浏览器打开，让用户有时间查看结果
                print(f"\n👀 浏览器将在 {self._keep_alive_duration/1000:.1f} 秒后关闭...")
                page.wait_for_timeout(self._keep_alive_duration)
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
            # 使用 networkidle 等待页面完全加载
            page.goto(url, wait_until="networkidle", timeout=self._timeout)
            
            # 等待一小段时间确保页面稳定
            page.wait_for_timeout(1000)
            
            # 检测是否有人机验证
            if self._detect_captcha(page):
                if not self._handle_captcha(page, "阅读"):
                    raise RuntimeError("人机验证未通过，无法继续读取内容")
                # 验证通过后，等待页面稳定
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
            if not self._keep_alive:
                context.close()
            else:
                # 保持浏览器打开，让用户有时间查看结果
                print(f"\n👀 浏览器将在 {self._keep_alive_duration/1000:.1f} 秒后关闭...")
                page.wait_for_timeout(self._keep_alive_duration)
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
    
    def _deep_search(self, query: str, count: int = 3) -> dict:
        """
        深度搜索：搜索并访问多个结果页面
        
        Args:
            query: 搜索关键词
            count: 要访问的页面数量，默认3个
        
        Returns:
            搜索结果 + 多个页面的内容列表
        """
        # 先搜索，获取更多结果
        search_result = self._search_bing(query, max_results=max(count, 5))
        
        if not search_result["results"]:
            return {
                "query": query,
                "error": "没有找到搜索结果"
            }
        
        # 读取前 N 个结果
        extracted_pages = []
        results_to_visit = search_result["results"][:count]
        
        print(f"\n🔍 深度搜索模式：将访问前 {len(results_to_visit)} 个结果...")
        
        for i, result in enumerate(results_to_visit, 1):
            url = result["url"]
            title = result["title"]
            print(f"\n[{i}/{len(results_to_visit)}] 正在访问: {title}")
            print(f"    URL: {url}")
            
            try:
                page_content = self._read_page(url)
                extracted_pages.append({
                    "index": i,
                    "title": title,
                    "url": url,
                    "content": page_content["content"],
                    "content_length": page_content["content_length"]
                })
                print(f"    ✅ 成功提取 {page_content['content_length']} 字符")
            except Exception as e:
                print(f"    ❌ 读取失败: {str(e)}")
                extracted_pages.append({
                    "index": i,
                    "title": title,
                    "url": url,
                    "error": f"读取页面失败: {str(e)}"
                })
        
        # 统计
        successful_count = sum(1 for p in extracted_pages if "error" not in p)
        failed_count = len(extracted_pages) - successful_count
        
        return {
            "query": query,
            "total_searched": len(search_result["results"]),
            "visited_count": len(extracted_pages),
            "successful_count": successful_count,
            "failed_count": failed_count,
            "search_results": search_result["results"],
            "extracted_pages": extracted_pages
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
                # 搜索并提取第一个结果
                result = self._search_and_extract(query)
                return ToolResult(success=True, data=result)
            
            elif action == "deep_search":
                # 深度搜索：访问多个结果页面
                deep_search_count = kwargs.get("deep_search_count", 3)
                result = self._deep_search(query, deep_search_count)
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
