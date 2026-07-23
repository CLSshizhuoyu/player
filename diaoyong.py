from higequ_crawler import HigequCrawler

crawler = HigequCrawler(headless=True)

# 1. 搜索
results = crawler.search("克罗地亚狂想曲")
for idx, item in enumerate(results, 1):
    print(f"{idx}. {item['title']} - {item['artist']} (ID: {item['id']})")

# 2. 获取单个详情（假设选第一个）
if results:
    detail = crawler.get_detail(results[0]['id'])
    print(f"音频: {detail['audio_url']}")
    print(f"封面: {detail['cover_url']}")

# 3. 批量获取多个详情（速度更快）
ids = [r['id'] for r in results[:5]]
details = crawler.get_details_batch(ids)
for d in details:
    print(f"{d['id']}: {d['audio_url']}")

# 4. 释放资源（可选，程序退出时会自动释放）
crawler.close()