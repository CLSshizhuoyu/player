import json
import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

class MediaCrawlerCDP:
    def __init__(self, headless=False):
        """初始化爬虫，配置 Chrome 选项"""
        self.options = Options()
        self.options.add_argument('--disable-gpu')
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--disable-blink-features=AutomationControlled')
        self.options.add_experimental_option('excludeSwitches', ['enable-automation'])
        self.options.add_argument(
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        if headless:
            self.options.add_argument('--headless')

        # 使用 webdriver_manager 自动管理 ChromeDriver
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=self.options)

        # 存储捕获的媒体链接
        self.media_links = {
            'audio': [],
            'video': [],
            'image': [],
            'other': []
        }

        # 用于去重
        self.seen_urls = set()

    def is_media_url(self, url, content_type=''):
        """判断 URL 或 Content-Type 是否属于媒体资源"""
        if not url or url.startswith('data:'):
            return False

        # 基于 Content-Type 判断
        content_type_lower = content_type.lower()
        if 'audio' in content_type_lower or 'video' in content_type_lower or 'image' in content_type_lower:
            return True

        # 基于 URL 扩展名判断
        url_lower = url.lower()
        audio_exts = ('.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma')
        video_exts = ('.mp4', '.webm', '.avi', '.mov', '.mkv', '.flv', '.m3u8')
        image_exts = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.ico')

        if any(url_lower.endswith(ext) for ext in audio_exts):
            return 'audio'
        if any(url_lower.endswith(ext) for ext in video_exts):
            return 'video'
        if any(url_lower.endswith(ext) for ext in image_exts):
            return 'image'

        # 部分 CDN 域名特征（可酌情开启）
        # media_domains = ('cdn', 'media', 'audio', 'video', 'img', 'static')
        # if any(domain in url_lower for domain in media_domains):
        #     return True

        return False

    def classify_and_add(self, url, content_type=''):
        """分类并添加媒体链接"""
        if not url or url in self.seen_urls:
            return

        media_type = self.is_media_url(url, content_type)
        if not media_type:
            return

        self.seen_urls.add(url)

        if media_type == 'audio':
            self.media_links['audio'].append(url)
            print(f"🎵 [音频] {url}")
        elif media_type == 'video':
            self.media_links['video'].append(url)
            print(f"🎬 [视频] {url}")
        elif media_type == 'image':
            self.media_links['image'].append(url)
            print(f"🖼️ [图片] {url}")
        else:
            self.media_links['other'].append(url)
            print(f"📁 [其他媒体] {url}")

    def setup_cdp_listeners(self):
        """通过 CDP 启用网络监听，并注册响应回调"""
        # 启用网络事件
        self.driver.execute_cdp_cmd('Network.enable', {})

        # 注册 responseReceived 事件监听
        self.driver.execute_cdp_cmd('Network.onResponseReceived', {
            'callback': self._on_response_received
        })

        # 部分 Chrome 版本可能需要使用 addListener 方式，这里采用执行 CDP 命令的方式
        # 实际事件回调需要通过 execute_cdp_cmd 的返回或 add_listener 处理
        # 为了更可靠，我们采用轮询日志的方式（见下文），但 CDP 实时监听更优雅。
        # 由于 selenium 的 execute_cdp_cmd 不支持直接注册回调，我们采用备用方案：
        # 使用 driver.get_log('performance') 定期拉取，模拟实时监听。
        pass

    def _on_response_received(self, event_data):
        """CDP 响应回调（示例，实际可能需要调整为适配 selenium 的机制）"""
        # 注意：selenium 的 execute_cdp_cmd 无法直接传递 Python 回调，
        # 此方法仅作为示意。实际我们会用轮询 performance log 的方式。
        pass

    def poll_performance_logs(self, duration=30, interval=1):
        """轮询 performance log 获取网络请求（兼容方案）"""
        print(f"⏳ 开始轮询性能日志，持续 {duration} 秒...")
        start_time = time.time()
        last_log_count = 0

        while time.time() - start_time < duration:
            try:
                logs = self.driver.get_log('performance')
                # 只处理新增的日志
                if len(logs) > last_log_count:
                    for log in logs[last_log_count:]:
                        self._parse_performance_log(log)
                    last_log_count = len(logs)
            except Exception as e:
                print(f"⚠️ 获取性能日志时出错: {e}")

            time.sleep(interval)

        print("✅ 轮询结束")

    def _parse_performance_log(self, log_entry):
        """解析单条 performance log"""
        try:
            message = json.loads(log_entry['message'])
            method = message.get('message', {}).get('method', '')

            if method == 'Network.responseReceived':
                params = message.get('message', {}).get('params', {})
                response = params.get('response', {})
                url = response.get('url', '')
                content_type = response.get('mimeType', '')
                if url:
                    self.classify_and_add(url, content_type)

            elif method == 'Network.requestWillBeSent':
                params = message.get('message', {}).get('params', {})
                request = params.get('request', {})
                url = request.get('url', '')
                # 有些媒体请求可能只有 request 没有 response，也捕获一下
                if url:
                    # 通过 URL 扩展名判断，不依赖 content-type
                    media_type = self.is_media_url(url, '')
                    if media_type:
                        self.classify_and_add(url, '')

        except json.JSONDecodeError:
            pass
        except Exception as e:
            print(f"⚠️ 解析日志时出错: {e}")

    def crawl(self, url, scroll_times=5, scroll_pause=2, poll_duration=30):
        """
        执行爬取主流程
        :param url: 目标 URL
        :param scroll_times: 滚动次数（触发懒加载）
        :param scroll_pause: 每次滚动后等待时间（秒）
        :param poll_duration: 轮询性能日志的总时长（秒）
        """
        print(f"🌐 正在访问: {url}")
        self.driver.get(url)

        # 等待页面基本加载完成
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body'))
            )
            print("✅ 页面加载完成")
        except Exception as e:
            print(f"⚠️ 等待页面加载超时: {e}")

        # 额外等待，让初始请求完成
        time.sleep(3)

        # 开始轮询 performance log
        import threading
        poll_thread = threading.Thread(
            target=self.poll_performance_logs,
            args=(poll_duration, 1)
        )
        poll_thread.daemon = True
        poll_thread.start()

        # 滚动页面以触发懒加载
        print(f"📜 开始滚动页面（共 {scroll_times} 次）...")
        for i in range(scroll_times):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            print(f"  滚动 {i+1}/{scroll_times}")
            time.sleep(scroll_pause)

            # 检查是否已到达底部
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            # 可选：如果高度不再变化，提前结束
            if i > 0 and new_height == getattr(self, '_last_height', 0):
                print("📌 页面高度不再变化，提前结束滚动")
                break
            self._last_height = new_height

        # 等待轮询线程结束
        poll_thread.join(timeout=poll_duration + 2)

        # 额外尝试从页面 DOM 中提取媒体元素
        self._extract_from_dom()

        # 打印统计信息
        self.print_summary()
        return self.media_links

    def _extract_from_dom(self):
        """从页面 DOM 中提取 audio/video/img 标签的 src"""
        print("🔍 从 DOM 中提取媒体元素...")
        try:
            # 提取 audio
            audios = self.driver.find_elements(By.TAG_NAME, 'audio')
            for audio in audios:
                src = audio.get_attribute('src')
                if src:
                    self.classify_and_add(src, 'audio/mpeg')
                # 检查 source 子标签
                sources = audio.find_elements(By.TAG_NAME, 'source')
                for source in sources:
                    src = source.get_attribute('src')
                    if src:
                        self.classify_and_add(src, 'audio/mpeg')

            # 提取 video
            videos = self.driver.find_elements(By.TAG_NAME, 'video')
            for video in videos:
                src = video.get_attribute('src')
                if src:
                    self.classify_and_add(src, 'video/mp4')
                sources = video.find_elements(By.TAG_NAME, 'source')
                for source in sources:
                    src = source.get_attribute('src')
                    if src:
                        self.classify_and_add(src, 'video/mp4')

            # 提取 img
            imgs = self.driver.find_elements(By.TAG_NAME, 'img')
            for img in imgs:
                src = img.get_attribute('src')
                if src:
                    self.classify_and_add(src, 'image/jpeg')

        except Exception as e:
            print(f"⚠️ DOM 提取时出错: {e}")

    def print_summary(self):
        """打印抓取结果摘要"""
        print("\n" + "=" * 60)
        print("📊 抓取结果统计")
        print("=" * 60)
        total = 0
        for category, links in self.media_links.items():
            count = len(links)
            total += count
            icons = {'audio': '🎵', 'video': '🎬', 'image': '🖼️', 'other': '📁'}
            print(f"{icons.get(category, '📄')} {category.capitalize()}: {count} 个")
        print(f"📦 总计: {total} 个")
        print("=" * 60)

        # 显示部分链接示例
        for category, links in self.media_links.items():
            if links:
                print(f"\n📌 {category.upper()} 链接示例（最多显示5个）:")
                for link in links[:5]:
                    print(f"  - {link}")
                if len(links) > 5:
                    print(f"  ... 还有 {len(links) - 5} 个")

    def save_links(self, filename='media_links.txt'):
        """保存所有链接到文件"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("媒体链接抓取结果\n")
            f.write("=" * 60 + "\n\n")
            for category, links in self.media_links.items():
                f.write(f"\n{category.upper()}\n")
                f.write("-" * 40 + "\n")
                for link in links:
                    f.write(f"{link}\n")
        print(f"\n💾 链接已保存到: {filename}")

    def close(self):
        """关闭浏览器"""
        if self.driver:
            self.driver.quit()
            print("🔚 浏览器已关闭")


def main():
    # 创建爬虫实例
    crawler = MediaCrawlerCDP(headless=False)  # headless=True 可无界面运行

    try:
        target_url = "https://higequ.com/player/1028052/"

        # 执行爬取
        media_links = crawler.crawl(
            url=target_url,
            scroll_times=8,        # 滚动次数
            scroll_pause=2,        # 滚动间隔（秒）
            poll_duration=40       # 监听时长（秒）
        )

        # 保存链接
        crawler.save_links()

        # 询问是否下载
        choice = input("\n是否下载第一个音频文件？(y/n): ").strip().lower()
        if choice == 'y' and media_links.get('audio'):
            audio_url = media_links['audio'][0]
            print(f"📥 下载: {audio_url}")
            # 这里可以添加下载逻辑，使用 requests 下载
            # download_file(audio_url, 'downloaded.mp3')

    except KeyboardInterrupt:
        print("\n⏹️ 用户中断")
    except Exception as e:
        print(f"❌ 发生错误: {e}")
    finally:
        crawler.close()


if __name__ == "__main__":
    main()