from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor
import requests
import os
import re
import time

class HigequCrawler:
    def __init__(self, headless=True):
        self.headless = headless
        self.base_url = "https://higequ.com"
        self._playwright = None
        self._browser = None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

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

    # ---------- 提取歌词的辅助方法 ----------
    def _extract_lyrics(self, page):
        """
        从页面中提取歌词，返回格式化的歌词列表和纯文本。
        歌词结构：<div id="lyrics-container">
                    <div class="lyric-line" data-time="秒数">歌词内容</div>
                  </div>
        """
        lyrics_lines = []
        lyrics_text = ""

        # 等待歌词容器加载
        try:
            page.wait_for_selector('#lyrics-container .lyric-line', timeout=5000)
        except:
            return None, None

        # 获取所有歌词行
        line_elements = page.query_selector_all('#lyrics-container .lyric-line')
        for el in line_elements:
            text = el.inner_text().strip()
            if not text:
                continue
            time_str = el.get_attribute('data-time')
            try:
                timestamp = float(time_str) if time_str else 0
            except (ValueError, TypeError):
                timestamp = 0

            lyrics_lines.append({
                'time': timestamp,
                'text': text
            })

        # 按时间排序
        lyrics_lines.sort(key=lambda x: x['time'])

        # 生成纯文本（每行一句）
        lyrics_text = '\n'.join([line['text'] for line in lyrics_lines])

        return lyrics_lines, lyrics_text

    # ---------- 获取详情（同步，复用浏览器） ----------
    def get_detail(self, song_id):
        browser = self._ensure_browser()
        page = browser.new_page()
        page.goto(f"{self.base_url}/player/{song_id}/", wait_until='domcontentloaded', timeout=15000)
        try:
            page.wait_for_selector('audio', timeout=3000)
        except:
            pass

        # 提取音频 URL
        audio_srcs = page.eval_on_selector_all(
            'audio, audio source',
            'els => els.map(el => el.src).filter(s => s)'
        )
        audio_url = audio_srcs[0] if audio_srcs else None

        # 提取封面 URL
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

        lyrics_lines, lyrics_text = self._extract_lyrics(page)

        page.close()
        return {
            'id': song_id,
            'audio_url': audio_url,
            'cover_url': cover_url,
            'lyrics_lines': lyrics_lines,
            'lyrics_text': lyrics_text
        }

    # ---------- 批量获取详情（多线程并发） ----------
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

                # 内联歌词提取
                lyrics_lines = []
                lyrics_text = ""
                try:
                    page.wait_for_selector('#lyrics-container .lyric-line', timeout=5000)
                    line_elements = page.query_selector_all('#lyrics-container .lyric-line')
                    for el in line_elements:
                        text = el.inner_text().strip()
                        if not text:
                            continue
                        time_str = el.get_attribute('data-time')
                        try:
                            timestamp = float(time_str) if time_str else 0
                        except (ValueError, TypeError):
                            timestamp = 0
                        lyrics_lines.append({'time': timestamp, 'text': text})
                    lyrics_lines.sort(key=lambda x: x['time'])
                    lyrics_text = '\n'.join([line['text'] for line in lyrics_lines])
                except:
                    pass

                page.close()
                browser.close()
                return {
                    'id': sid,
                    'audio_url': audio_url,
                    'cover_url': cover_url,
                    'lyrics_lines': lyrics_lines,
                    'lyrics_text': lyrics_text
                }

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(fetch_one, song_ids))

    # ---------- 新增：下载单首歌曲 ----------
    def download_song(self, song_info):
        """
        下载音频和歌词到 ./songs/ 文件夹。
        :param song_info: 字典，必须包含 'id', 'title', 'artist'，可选 'album'
        :return: 下载的文件路径 (audio_path, lrc_path) 或 (None, None) 若失败
        """
        # 获取详情
        detail = self.get_detail(song_info['id'])
        if not detail['audio_url']:
            print(f"❌ 未找到音频链接，歌曲ID: {song_info['id']}")
            return None, None

        # 清理文件名中的非法字符
        def sanitize_filename(name):
            # 替换 Windows/Linux 非法字符
            return re.sub(r'[\\/*?:"<>|]', '', name).strip()

        artist = sanitize_filename(song_info['artist'] or '未知歌手')
        title = sanitize_filename(song_info['title'] or '未知歌名')
        base_name = f"{artist} - {title}"

        # 创建 songs 文件夹
        songs_dir = os.path.join(os.getcwd(), 'songs')
        os.makedirs(songs_dir, exist_ok=True)

        # 下载音频
        audio_path = os.path.join(songs_dir, f"{base_name}.mp3")
        try:
            print(f"⬇️ 正在下载音频: {base_name}")
            resp = self.session.get(detail['audio_url'], stream=True, timeout=30)
            resp.raise_for_status()
            with open(audio_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            print(f"✅ 音频已保存: {audio_path}")
        except Exception as e:
            print(f"❌ 音频下载失败: {e}")
            audio_path = None

        # 保存歌词（如果存在）
        lrc_path = None
        if detail['lyrics_lines']:
            try:
                lrc_path = os.path.join(songs_dir, f"{base_name}.lrc")
                # 转换为 LRC 格式
                with open(lrc_path, 'w', encoding='utf-8') as f:
                    # 可选的元信息
                    f.write(f"[ar:{artist}]\n")
                    f.write(f"[ti:{title}]\n")
                    if song_info.get('album'):
                        f.write(f"[al:{sanitize_filename(song_info['album'])}]\n")
                    f.write("\n")
                    for line in detail['lyrics_lines']:
                        minutes = int(line['time'] // 60)
                        seconds = int(line['time'] % 60)
                        centiseconds = int((line['time'] % 1) * 100)
                        f.write(f"[{minutes:02d}:{seconds:02d}.{centiseconds:02d}]{line['text']}\n")
                print(f"✅ 歌词已保存: {lrc_path}")
            except Exception as e:
                print(f"❌ 歌词保存失败: {e}")
                lrc_path = None
        else:
            print(f"⚠️ 未找到歌词，跳过")

        return audio_path, lrc_path

    # ---------- 批量下载（基于搜索结果） ----------
    def download_search_results(self, results, max_count=5):
        """
        从搜索结果中下载前 max_count 首歌曲。
        :param results: search() 返回的列表
        :param max_count: 最多下载数量
        """
        downloaded = 0
        for i, song in enumerate(results[:max_count], 1):
            print(f"\n🎵 [{i}/{min(max_count, len(results))}] 处理: {song['artist']} - {song['title']}")
            self.download_song(song)
            downloaded += 1
            # 避免请求过快
            time.sleep(1)
        print(f"\n🎉 共下载 {downloaded} 首歌曲")

    # ---------- 关闭资源 ----------
    def close(self):
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None