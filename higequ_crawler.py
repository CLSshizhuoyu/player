from playwright.sync_api import sync_playwright
import time

class HigequCrawler:
    def __init__(self, headless=True):
        self.headless = headless
        self.base_url = "https://higequ.com"
        self._playwright = None
        self._browser = None
        self._context = None  # 可选，保留上下文可提升速度

    def _ensure_browser(self):
        """确保浏览器已启动（只启动一次）"""
        if self._browser is None:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            # 创建一个持久化上下文，可复用 cookies 等（但当前不需要）
        return self._browser

    def search(self, keyword):
        """同步搜索，返回列表（id, title, artist, album）"""
        browser = self._ensure_browser()
        page = browser.new_page()
        search_url = f"{self.base_url}/s/{keyword}/"
        page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_load_state('networkidle')

        # 等待结果容器
        try:
            page.wait_for_selector('div#results-container', timeout=5000)
        except:
            pass

        # 滚动加载更多
        last_height = page.evaluate('document.body.scrollHeight')
        for _ in range(10):
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            page.wait_for_timeout(1500)
            new_height = page.evaluate('document.body.scrollHeight')
            if new_height == last_height:
                break
            last_height = new_height

        items = page.query_selector_all('div.result-item')
        results = []
        for item in items:
            rid = item.get_attribute('data-rid')
            if rid:
                title_el = item.query_selector('.result-title')
                artist_el = item.query_selector('.result-artist')
                album_el = item.query_selector('.result-album')
                title = title_el.inner_text() if title_el else ''
                artist = artist_el.inner_text() if artist_el else ''
                album_text = album_el.inner_text() if album_el else ''
                album = album_text.replace('专辑：', '').replace('专辑:', '').strip()
                results.append({
                    'id': rid,
                    'title': title.strip(),
                    'artist': artist.strip(),
                    'album': album
                })
        page.close()
        return results

    def get_detail(self, song_id):
        """根据 ID 获取音频和封面"""
        browser = self._ensure_browser()
        page = browser.new_page()
        url = f"{self.base_url}/player/{song_id}/"
        page.goto(url, wait_until='networkidle', timeout=30000)

        try:
            page.wait_for_selector('audio', timeout=10000)
        except:
            pass

        # 提取音频链接
        audio_srcs = page.eval_on_selector_all(
            'audio, audio source',
            'els => els.map(el => el.src).filter(s => s)'
        )
        audio_url = audio_srcs[0] if audio_srcs else None

        # 提取封面
        cover_url = page.evaluate('''() => {
            const meta = document.querySelector('meta[property="og:image"]');
            if (meta) return meta.getAttribute('content');
            const imgs = document.querySelectorAll('img');
            for (let img of imgs) {
                const src = img.src;
                const alt = (img.alt || '').toLowerCase();
                const cls = (img.className || '').toLowerCase();
                if (src && (alt.includes('cover') || alt.includes('album') || cls.includes('cover') || cls.includes('poster'))) {
                    return src;
                }
            }
            let maxArea = 0, best = null;
            for (let img of imgs) {
                const area = img.naturalWidth * img.naturalHeight;
                if (area > maxArea) {
                    maxArea = area;
                    best = img.src;
                }
            }
            return best;
        }''')

        page.close()
        return {
            'id': song_id,
            'audio_url': audio_url,
            'cover_url': cover_url
        }

    def close(self):
        """关闭浏览器，释放资源"""
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    # 可选：批量获取（串行，但可配合多线程加速）
    def get_details_batch(self, song_ids):
        """串行批量获取（可自行改为多线程）"""
        return [self.get_detail(sid) for sid in song_ids]