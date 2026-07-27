from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor
import time

class HigequCrawler:
    def __init__(self, headless=True):
        self.headless = headless
        self.base_url = "https://higequ.com"
        self._playwright = None
        self._browser = None

    # ---------- 单例浏览器（同步） ----------
    def _ensure_browser(self):
        if self._browser is None:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
        return self._browser

    # ---------- 搜索（同步） ----------
    def search(self, keyword, max_results=30, max_scrolls=5):
        browser = self._ensure_browser()
        page = browser.new_page()
        page.goto(f"{self.base_url}/s/{keyword}/", wait_until='domcontentloaded', timeout=20000)
        page.wait_for_load_state('networkidle')

        try:
            page.wait_for_selector('div#results-container', timeout=5000)
        except:
            pass

        results = []
        last_count = 0
        for _ in range(max_scrolls):
            items = page.query_selector_all('div.result-item')
            current_count = len(items)
            if current_count >= max_results:
                break
            if current_count == last_count:
                break
            last_count = current_count
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            page.wait_for_timeout(1000)

        items = page.query_selector_all('div.result-item')
        for item in items[:max_results]:
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

    # ---------- 获取详情（同步，复用浏览器） ----------
    def get_detail(self, song_id):
        browser = self._ensure_browser()
        page = browser.new_page()
        page.goto(f"{self.base_url}/player/{song_id}/", wait_until='domcontentloaded', timeout=15000)
        try:
            page.wait_for_selector('audio', timeout=3000)
        except:
            pass

        audio_srcs = page.eval_on_selector_all(
            'audio, audio source',
            'els => els.map(el => el.src).filter(s => s)'
        )
        audio_url = audio_srcs[0] if audio_srcs else None

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

    # ---------- 批量获取详情（多线程并发，每个线程独立浏览器） ----------
    def get_details_batch(self, song_ids, max_workers=5):
        """
        并发获取多个歌曲详情，使用线程池，每个任务独立浏览器。
        :param song_ids: ID 列表
        :param max_workers: 最大并发数
        :return: 详情列表（顺序与输入一致）
        """
        def fetch_one(sid):
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                page = browser.new_page()
                page.goto(f"{self.base_url}/player/{sid}/", wait_until='domcontentloaded', timeout=15000)
                try:
                    page.wait_for_selector('audio', timeout=3000)
                except:
                    pass
                audio_srcs = page.eval_on_selector_all(
                    'audio, audio source',
                    'els => els.map(el => el.src).filter(s => s)'
                )
                audio_url = audio_srcs[0] if audio_srcs else None

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
                browser.close()
                return {'id': sid, 'audio_url': audio_url, 'cover_url': cover_url}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(fetch_one, song_ids))

    # ---------- 关闭资源 ----------
    def close(self):
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None