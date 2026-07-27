"""
from higequ_crawler import HigequCrawler
import time

print("Start")

crawler = HigequCrawler(headless=True)

print("Object is OK.")
t1 = time.time()

# 1. 搜索
results = crawler.search("周杰伦", max_results=10)
for idx, item in enumerate(results, 1):
    print(f"{idx}. {item['title']} - {item['artist']} (ID: {item['id']})")

t2 = time.time()
print(f"No.1 is OK.time:{t2 - t1}s")

# 2. 单个详情（复用浏览器）
if results:
    detail = crawler.get_detail(results[0]['id'])
    print(f"音频: {detail['audio_url']}")

t3 = time.time()
print(f"No.2 is OK.time:{t3 - t2}s")

# 3. 批量并发获取（多线程）
ids = [r['id'] for r in results[:5]]
details = crawler.get_details_batch(ids, max_workers=5)
for d in details:
    print(f"{d['id']}: {d['audio_url']}")

print(f"No.3 is OK.time:{time.time() - t3}s.per file:{(time.time() - t3)/5}s")

# 释放资源
crawler.close()
"""
# 初始化爬虫
import higequ_crawler as c
crawler = c.HigequCrawler(headless=True)

# 搜索歌曲
results = crawler.search("周杰伦 七里香")
for song in results:
    print(f"{song['artist']} - {song['title']} (ID: {song['id']})")

# 下载第一首
if results:
    crawler.download_song(results[0])

# 或者批量下载前3首
#crawler.download_search_results(results, max_count=3)

# 关闭资源
crawler.close()