import asyncio
import tempfile
import os
import wave
import requests
import sounddevice as sd
import numpy as np
from shazamio import Shazam

class MusicRecognizer:
    """
    基于 shazamio 的音乐识别封装库
    支持：麦克风录音识别、本地文件识别、网络链接识别
    """

    def __init__(self):
        self.shazam = Shazam()

    # ---------- 异步核心方法 ----------
    async def recognize_file(self, file_path: str) -> dict:
        """识别本地音频文件（支持 mp3, flac, ogg, wav, m4a 等）"""
        result = await self.shazam.recognize(file_path)
        return self._parse_result(result)

    async def recognize_url(self, url: str) -> dict:
        """识别网络音频链接（自动下载到临时文件）"""
        response = requests.get(url, stream=True)
        response.raise_for_status()
        # 从 URL 中猜测后缀，若无则默认 .mp3
        suffix = os.path.splitext(url)[1] or '.mp3'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name
        try:
            result = await self.shazam.recognize(tmp_path)
            return self._parse_result(result)
        finally:
            os.unlink(tmp_path)  # 清理临时文件

    async def recognize_mic(self, duration: int = 10, samplerate: int = 44100) -> dict:
        """录音指定秒数（默认 10 秒）并识别"""
        print(f"🎤 正在录音 {duration} 秒...")
        recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1)
        sd.wait()  # 等待录音结束
        print("✅ 录音完成，开始识别...")

        # 保存为临时 WAV 文件（shazamio 支持 WAV）
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
            with wave.open(tmp.name, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(samplerate)
                # 将 float [-1,1] 转为 int16
                wf.writeframes((recording * 32767).astype(np.int16).tobytes())
            tmp_path = tmp.name

        try:
            result = await self.shazam.recognize(tmp_path)
            return self._parse_result(result)
        finally:
            os.unlink(tmp_path)

    # ---------- 结果解析 ----------
    @staticmethod
    def _parse_result(result: dict) -> dict:
        """从原始返回中提取标题、艺人等信息"""
        if 'track' in result:
            track = result['track']
            return {
                'title': track.get('title', '未知歌曲'),
                'artist': track.get('subtitle', '未知艺人'),
                'full': result  # 保留完整数据供调试
            }
        else:
            return {
                'error': '未识别到歌曲',
                'full': result
            }

    # ---------- 同步包装（方便调用） ----------
    def recognize_file_sync(self, file_path: str) -> dict:
        return asyncio.run(self.recognize_file(file_path))

    def recognize_url_sync(self, url: str) -> dict:
        return asyncio.run(self.recognize_url(url))

    def recognize_mic_sync(self, duration: int = 10) -> dict:
        return asyncio.run(self.recognize_mic(duration))