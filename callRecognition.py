from music_recognizer import MusicRecognizer
import json

recognizer = MusicRecognizer()
info = recognizer.recognize_mic_sync(duration=10)  # 可自定义时长
print(f"🎵 歌曲名：{info.get('title')}")
print(f"👤 歌手：{info.get('artist')}")
# 将结果转为缩进2格的JSON字符串，并显示中文
json_str = json.dumps(info, indent=2, ensure_ascii=False)
print(json_str)