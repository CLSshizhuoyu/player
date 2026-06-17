# 🎵 分类音乐播放器 — 使用与打包说明

## 一、环境准备

```bash
pip install PyQt5
# Windows 下播放需要 LAV Filters 或系统自带解码器（mp3/aac 通常自带）
# flac/ogg 可能需要额外解码器，建议安装 LAV Filters:
#   https://github.com/Nevcairiel/LAVFilters/releases
```

## 二、运行

```bash
python music_player.py
```

## 三、JSON 数据结构

在音乐文件夹内放置 `music_library.json`，格式如下：

```json
[
  {
    "id": "001",
    "filename": "song1.mp3",
    "genre": "流行",
    "language": "中文",
    "year": "2020",
    "artist": "张三",
    "lyrics": "song1.lrc"
  }
]
```

| 字段       | 说明                                     |
|------------|------------------------------------------|
| id         | 唯一编码（手动指定，如 "001"）            |
| filename   | 音乐文件名（相对于音乐文件夹）            |
| genre      | 种类（流行/摇滚/古典...）                 |
| language   | 语言（中文/英文/日语/纯音乐...）          |
| year       | 年代                                     |
| artist     | 艺术家                                   |
| lyrics     | 歌词文件路径（.lrc，相对于音乐文件夹），无则留空 |

> 如果没有 JSON，打开软件选择文件夹后会提示自动扫描生成。

## 四、功能说明

1. **选择文件夹** → 自动加载 JSON（或自动生成）
2. **编辑元数据** → 打开表格编辑器，可修改每首歌的分类信息并保存
3. **分类筛选** → 选择「种类/语言/年代/艺术家」+ 对应值，列表自动过滤
4. **双击播放** → 双击列表中歌曲即可播放
5. **歌词显示** → 若 JSON 中 lyrics 指向有效 .lrc 文件，播放时自动逐行高亮滚动
6. **播放控制** → 上一首/播放/暂停/停止/下一首 + 进度条拖拽

## 五、打包为 exe

### 方法：PyInstaller

```bash
pip install pyinstaller

pyinstaller --noconfirm --onedir --windowed ^
  --name "MusicPlayer" ^
  --collect-all PyQt5 ^
  music_player.py
```

### 参数说明

| 参数            | 作用                                      |
|-----------------|-------------------------------------------|
| --onedir        | 生成文件夹形式（启动更快，便于排查问题）    |
| --onefile       | 生成单个 exe（启动慢，但更方便分发）        |
| --windowed      | 不显示控制台黑窗口                         |
| --name          | exe 名称                                   |
| --collect-all PyQt5 | 确保 PyQt5 所有依赖被打包             |

### 注意事项

1. **Windows 编解码器**：PyQt5 的 QMediaPlayer 底层使用 Windows Media Framework。
   - MP3/AAC/WAV 通常开箱即用
   - FLAC/OGG 需要安装 LAV Filters（在打包后的目标机器上也需安装）
2. **LAV Filters 静默安装**（可选）：可将 LAV Filters 安装包随 exe 一起分发
3. **首次运行较慢**：--onefile 模式首次启动需解压到临时目录
4. **图标**：可加 `--icon=app.ico` 指定程序图标
5. **排除不必要的模块**（减小体积）：
   ```
   --exclude-module PyQt5.QtWebEngine --exclude-module PyQt5.QtWebEngineWidgets ^
   --exclude-module PyQt5.QtTest --exclude-module PyQt5.QtSql ^
   --exclude-module PyQt5.QtNetwork --exclude-module PyQt5.QtOpenGL
   ```

### 完整打包命令（推荐）

```bash
pyinstaller --noconfirm --onefile --windowed ^
  --name "MusicPlayer" ^
  --icon=app.ico ^
  --collect-all PyQt5 ^
  --exclude-module PyQt5.QtWebEngine ^
  --exclude-module PyQt5.QtWebEngineWidgets ^
  --exclude-module PyQt5.QtTest ^
  --exclude-module PyQt5.QtSql ^
  --exclude-module PyQt5.QtOpenGL ^
  music_player.py
```

打包结果在 `dist/` 目录下。

## 六、项目文件结构

```
your_project/
├── music_player.py          # 主程序
