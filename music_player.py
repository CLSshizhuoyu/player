# -*- coding: utf-8 -*-
"""
MusicPlayer - 基于 PyQt5 + VLC 的分类音乐播放器
功能：
  1. 给定音乐文件夹，自动扫描音乐文件
  2. 通过 JSON 为每首歌指定唯一编码、分类信息（种类/语言/年代等）、歌词路径
  3. 按分类标准筛选歌曲并播放
  4. 支持显示 LRC 歌词（逐行高亮滚动）
  5. 提供元数据编辑界面
  6. 进度条点击跳转、播放/暂停合一、支持常见音频格式
"""

import sys
import os
import json
import re
import vlc
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QListWidget, QListWidgetItem,
    QFileDialog, QSlider, QTextEdit, QGroupBox, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QSplitter
)
from PyQt5.QtCore import Qt, QTimer, QUrl, QSize, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QTextCharFormat, QTextCursor, QMouseEvent

# ─── 常量 ────────────────────────────────────────────────
SUPPORTED_FORMATS = {".mp3", ".flac", ".aac", ".ogg", ".wav", ".m4a"}
JSON_FILENAME = "music_library.json"

# ─── 自定义进度条（支持点击跳转）─────────────────────────
class ClickableSlider(QSlider):
    """重写鼠标按下事件，使点击轨道直接跳转到点击位置"""
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            # 计算点击位置的比例
            ratio = event.x() / self.width()
            value = self.minimum() + (self.maximum() - self.minimum()) * ratio
            self.setValue(int(value))
            self.sliderMoved.emit(int(value))  # 触发跳转信号
        else:
            super().mousePressEvent(event)

# ─── LRC 歌词解析 ────────────────────────────────────────
def parse_lrc(lrc_path):
    """解析 LRC 文件，返回 [(time_seconds, text), ...] 按时间排序"""
    if not os.path.exists(lrc_path):
        return []
    lines = []
    pattern = re.compile(r'\[(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?\](.*)')
    with open(lrc_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            m = pattern.match(line.strip())
            if m:
                minute = int(m.group(1))
                second = int(m.group(2))
                ms_str = m.group(3) or "0"
                ms = int(ms_str.ljust(3, '0'))
                text = m.group(4).strip()
                total = minute * 60 + second + ms / 1000.0
                if text:
                    lines.append((total, text))
    lines.sort(key=lambda x: x[0])
    return lines

# ─── 元数据编辑对话框 ────────────────────────────────────
class MetadataEditor(QDialog):
    """用于编辑每首歌的 JSON 元数据"""
    def __init__(self, library_data, music_dir, parent=None):
        super().__init__(parent)
        self.library = library_data
        self.music_dir = music_dir
        self.setWindowTitle("元数据编辑器")
        self.resize(900, 500)
        self._build_ui()
        self.last_highlight_start = -1
        self.last_highlight_end = -1

    def _build_ui(self):
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        btn_scan = QPushButton("扫描文件夹（添加新文件）")
        btn_scan.clicked.connect(self._scan_new_files)
        btn_save = QPushButton("保存 JSON")
        btn_save.clicked.connect(self._save_json)
        toolbar.addWidget(btn_scan)
        toolbar.addStretch()
        toolbar.addWidget(btn_save)
        layout.addLayout(toolbar)

        self.table = QTableWidget()
        headers = ["唯一编码", "文件名", "种类", "语言", "年代", "艺术家", "歌词路径"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(len(self.library))
        for row, entry in enumerate(self.library):
            vals = [
                entry.get("id", ""),
                entry.get("filename", ""),
                entry.get("genre", ""),
                entry.get("language", ""),
                entry.get("year", ""),
                entry.get("artist", ""),
                entry.get("lyrics", ""),
            ]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                self.table.setItem(row, col, item)

    def _scan_new_files(self):
        existing = {e["filename"] for e in self.library}
        added = 0
        next_id = max([int(e["id"]) for e in self.library if str(e.get("id", "")).isdigit()] + [0]) + 1
        for f in sorted(os.listdir(self.music_dir)):
            ext = os.path.splitext(f)[1].lower()
            if ext in SUPPORTED_FORMATS and f not in existing:
                self.library.append({
                    "id": str(next_id),
                    "filename": f,
                    "genre": "",
                    "language": "",
                    "year": "",
                    "artist": "",
                    "lyrics": "",
                })
                next_id += 1
                added += 1
        self._refresh_table()
        QMessageBox.information(self, "扫描完成", f"新增 {added} 个文件。")

    def _save_json(self):
        for row in range(self.table.rowCount()):
            entry = self.library[row]
            entry["id"]       = self.table.item(row, 0).text()
            entry["filename"] = self.table.item(row, 1).text()
            entry["genre"]    = self.table.item(row, 2).text()
            entry["language"] = self.table.item(row, 3).text()
            entry["year"]     = self.table.item(row, 4).text()
            entry["artist"]   = self.table.item(row, 5).text()
            entry["lyrics"]   = self.table.item(row, 6).text()
        json_path = os.path.join(self.music_dir, JSON_FILENAME)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.library, f, ensure_ascii=False, indent=2)
        QMessageBox.information(self, "已保存", f"元数据已保存到:\n{json_path}")

# ─── 主窗口 ──────────────────────────────────────────────
class MusicPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎵 分类音乐播放器")
        self.resize(1100, 680)
        self.music_dir = ""
        self.library = []
        self.lrc_lines = []
        self.current_lrc_index = -1
        self.is_playing = False

        # ── VLC 播放器初始化 ──
        self.vlc_instance = vlc.Instance("--no-xlib --quiet")
        self.player = self.vlc_instance.media_player_new()
        self.player.audio_set_volume(80)

        # 定时器轮询进度
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_ui)
        self.update_timer.start(100)

        # 歌词定时器
        self.lrc_timer = QTimer(self)
        self.lrc_timer.timeout.connect(self._update_lyrics)
        self.lrc_timer.start(200)

        self._build_ui()
        self._build_connections()

    # ─── UI 构建 ──────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # 顶部：文件夹选择
        top = QHBoxLayout()
        top.addWidget(QLabel("音乐文件夹:"))
        self.lbl_dir = QLabel("（未选择）")
        self.lbl_dir.setStyleSheet("color: #555;")
        top.addWidget(self.lbl_dir, 1)
        btn_open = QPushButton("选择文件夹")
        btn_open.clicked.connect(self._open_folder)
        top.addWidget(btn_open)
        btn_edit = QPushButton("编辑元数据")
        btn_edit.clicked.connect(self._open_editor)
        top.addWidget(btn_edit)
        root.addLayout(top)

        # 中部：左侧筛选+列表 | 右侧歌词
        splitter = QSplitter(Qt.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        grp_filter = QGroupBox("分类筛选")
        fl = QHBoxLayout(grp_filter)
        fl.addWidget(QLabel("标准:"))
        self.cmb_category = QComboBox()
        self.cmb_category.addItems(["全部", "种类", "语言", "年代", "艺术家"])
        fl.addWidget(self.cmb_category)
        fl.addWidget(QLabel("值:"))
        self.cmb_value = QComboBox()
        fl.addWidget(self.cmb_value, 1)
        left_layout.addWidget(grp_filter)

        grp_list = QGroupBox("歌曲列表")
        ll = QVBoxLayout(grp_list)
        self.list_songs = QListWidget()
        self.list_songs.doubleClicked.connect(self._play_selected)
        ll.addWidget(self.list_songs)

        # 播放控制（合并播放/暂停）
        ctrl = QHBoxLayout()
        self.btn_prev = QPushButton("⏮ 上一首")
        self.btn_play_pause = QPushButton("▶ 播放")
        self.btn_stop = QPushButton("⏹ 停止")
        self.btn_next = QPushButton("⏭ 下一首")
        for b in [self.btn_prev, self.btn_play_pause, self.btn_stop, self.btn_next]:
            ctrl.addWidget(b)
        ll.addLayout(ctrl)

        # 进度条（自定义点击跳转）
        prog = QHBoxLayout()
        self.lbl_time = QLabel("00:00 / 00:00")
        self.slider = ClickableSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self._seek)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px;
                background: #e0e0e0;
                border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: white;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #2196F3;
                width: 16px;
                height: 16px;
                margin: -4px 0;
                border-radius: 8px;
            }
        """)
        prog.addWidget(self.slider, 1)
        prog.addWidget(self.lbl_time)
        ll.addLayout(prog)

        left_layout.addWidget(grp_list, 1)
        splitter.addWidget(left_panel)

        # 右侧：歌词
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("🎼 歌词"))
        self.txt_lyrics = QTextEdit()
        self.txt_lyrics.setReadOnly(True)
        self.txt_lyrics.setAlignment(Qt.AlignCenter)
        self.txt_lyrics.setStyleSheet("""
            font-size: 16px; 
            background: white; 
            color: #333333;
        """)
        right_layout.addWidget(self.txt_lyrics, 1)
        self.lbl_now_playing = QLabel("未播放")
        self.lbl_now_playing.setStyleSheet("font-size: 14px; font-weight: bold; color: #2196F3;")
        self.lbl_now_playing.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self.lbl_now_playing)
        splitter.addWidget(right_panel)

        splitter.setSizes([500, 450])
        root.addWidget(splitter, 1)

        self.setStyleSheet("""
            QMainWindow { background: #f5f5f5; }
            QGroupBox { font-weight: bold; border: 1px solid #ddd; border-radius: 6px; margin-top: 8px; padding-top: 12px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; }
            QPushButton { padding: 6px 14px; border-radius: 4px; background: #2196F3; color: white; font-weight: bold; }
            QPushButton:hover { background: #1976D2; }
            QPushButton:pressed { background: #0D47A1; }
            QListWidget { border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
            QComboBox { padding: 4px; border: 1px solid #ccc; border-radius: 4px; }
        """)

    def _build_connections(self):
        self.cmb_category.currentIndexChanged.connect(self._update_values)
        self.cmb_value.currentIndexChanged.connect(self._filter_songs)
        self.btn_prev.clicked.connect(self._play_prev)
        self.btn_play_pause.clicked.connect(self._toggle_play_pause)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_next.clicked.connect(self._play_next)

    # ─── VLC 播放控制 ─────────────────────────────────────
    def _set_media(self, filepath):
        media = self.vlc_instance.media_new(filepath)
        self.player.set_media(media)
        self.slider.setRange(0, self.player.get_length() or 0)

    def _play(self):
        self.player.play()
        self.is_playing = True
        self.btn_play_pause.setText("⏸ 暂停")

    def _pause(self):
        self.player.pause()
        self.is_playing = False
        self.btn_play_pause.setText("▶ 播放")

    def _toggle_play_pause(self):
        if self.player.get_state() == vlc.State.Playing:
            self._pause()
        else:
            self._play()

    def _stop(self):
        self.player.stop()
        self.is_playing = False
        self.btn_play_pause.setText("▶ 播放")
        self.slider.setValue(0)
        self.lbl_time.setText("00:00 / 00:00")
        self.lbl_now_playing.setText("已停止")
        self.txt_lyrics.clear()
        self.lrc_lines = []
        self.current_lrc_index = -1

    # ─── 修正：正确转换毫秒→播放比例 ─────────────────────
    def _seek(self, pos_ms):
        """定位到指定毫秒位置（根据总时长转换为 0~1 比例）"""
        length = self.player.get_length()
        if length > 0:
            ratio = pos_ms / length
            # 防止因浮点误差超出范围
            ratio = max(0.0, min(1.0, ratio))
            self.player.set_position(ratio)
        # 如果 length 为 0（未加载媒体），则忽略

    # ─── UI 更新（定时器） ────────────────────────────────
    def _update_ui(self):
        if not self.player.get_media():
            return
        length = self.player.get_length()
        if length > 0:
            pos = self.player.get_position() * length
            self.slider.setRange(0, length)
            if not self.slider.isSliderDown():
                self.slider.setValue(int(pos))
            self.lbl_time.setText(f"{self._fmt(int(pos))} / {self._fmt(length)}")
        else:
            self.slider.setRange(0, 0)
            self.lbl_time.setText("00:00 / 00:00")

        # 自动下一首
        if length > 0 and self.player.get_state() == vlc.State.Ended:
            self._play_next()

    # ─── 文件夹 / JSON 加载（保持不变）─────────────────
    def _open_folder(self):
        d = QFileDialog.getExistingDirectory(self, "选择音乐文件夹")
        if not d:
            return
        self.music_dir = d
        self.lbl_dir.setText(d)
        json_path = os.path.join(d, JSON_FILENAME)
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                self.library = json.load(f)
        else:
            ret = QMessageBox.question(
                self, "未找到 JSON",
                f"文件夹中未找到 {JSON_FILENAME}。\n是否自动扫描并生成？",
                QMessageBox.Yes | QMessageBox.No
            )
            if ret == QMessageBox.Yes:
                self._auto_generate_json()
            else:
                self.library = []
        self._update_values()
        self._filter_songs()

    def _auto_generate_json(self):
        self.library = []
        idx = 1
        for f in sorted(os.listdir(self.music_dir)):
            ext = os.path.splitext(f)[1].lower()
            if ext in SUPPORTED_FORMATS:
                lrc_candidate = os.path.splitext(f)[0] + ".lrc"
                lrc_path = lrc_candidate if os.path.exists(os.path.join(self.music_dir, lrc_candidate)) else ""
                self.library.append({
                    "id": str(idx),
                    "filename": f,
                    "genre": "",
                    "language": "",
                    "year": "",
                    "artist": "",
                    "lyrics": lrc_path,
                })
                idx += 1
        json_path = os.path.join(self.music_dir, JSON_FILENAME)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.library, f, ensure_ascii=False, indent=2)
        QMessageBox.information(self, "已生成", f"已生成 {JSON_FILENAME}，请在「编辑元数据」中补充分类信息。")

    def _open_editor(self):
        if not self.music_dir:
            QMessageBox.warning(self, "提示", "请先选择音乐文件夹。")
            return
        dlg = MetadataEditor(self.library, self.music_dir, self)
        dlg.exec_()
        self._update_values()
        self._filter_songs()

    # ─── 筛选逻辑 ────────────────────────────────────────
    CATEGORY_MAP = {
        "种类": "genre",
        "语言": "language",
        "年代": "year",
        "艺术家": "artist",
    }

    def _update_values(self):
        cat = self.cmb_category.currentText()
        self.cmb_value.blockSignals(True)
        self.cmb_value.clear()
        self.cmb_value.addItem("（全部）")
        if cat in self.CATEGORY_MAP:
            key = self.CATEGORY_MAP[cat]
            values = sorted(set(
                e.get(key, "") for e in self.library if e.get(key, "")
            ))
            self.cmb_value.addItems(values)
        self.cmb_value.blockSignals(False)
        self._filter_songs()

    def _filter_songs(self):
        cat = self.cmb_category.currentText()
        val = self.cmb_value.currentText()
        self.list_songs.clear()
        for entry in self.library:
            if cat == "全部" or val == "（全部）":
                pass
            elif cat in self.CATEGORY_MAP:
                key = self.CATEGORY_MAP[cat]
                if entry.get(key, "") != val:
                    continue
            else:
                continue
            display = f"[{entry.get('id','')}] {entry.get('filename','')}"
            if entry.get("artist"):
                display += f"  -  {entry['artist']}"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, entry)
            self.list_songs.addItem(item)

    # ─── 播放控制 ────────────────────────────────────────
    def _get_current_row(self):
        return self.list_songs.currentRow()

    def _play_selected(self, index):
        self._play_row(index.row())

    def _play_row(self, row):
        if row < 0 or row >= self.list_songs.count():
            return
        item = self.list_songs.item(row)
        entry = item.data(Qt.UserRole)
        filepath = os.path.join(self.music_dir, entry["filename"])
        if not os.path.exists(filepath):
            QMessageBox.warning(self, "错误", f"文件不存在:\n{filepath}")
            return
        self._set_media(filepath)
        self._play()
        self.lbl_now_playing.setText(f"正在播放: {entry['filename']}")
        self._load_lyrics(entry)

    def _play_prev(self):
        row = self._get_current_row()
        if row > 0:
            self.list_songs.setCurrentRow(row - 1)
            self._play_row(row - 1)

    def _play_next(self):
        row = self._get_current_row()
        if 0 <= row < self.list_songs.count() - 1:
            self.list_songs.setCurrentRow(row + 1)
            self._play_row(row + 1)

    # ─── 歌词 ────────────────────────────────────────────
    def _load_lyrics(self, entry):
        self.lrc_lines = []
        self.current_lrc_index = -1
        self.last_highlight_start = -1
        self.last_highlight_end = -1
        lrc_rel = entry.get("lyrics", "")
        if lrc_rel:
            lrc_path = os.path.join(self.music_dir, lrc_rel)
            self.lrc_lines = parse_lrc(lrc_path)
        if self.lrc_lines:
            full_text = "\n".join(line[1] for line in self.lrc_lines)
            self.txt_lyrics.setPlainText(full_text)
            # 将全部行设为默认深灰色
            cursor = self.txt_lyrics.textCursor()
            cursor.select(QTextCursor.Document)
            fmt_default = QTextCharFormat()
            fmt_default.setForeground(QColor("#333333"))
            cursor.setCharFormat(fmt_default)
            cursor.clearSelection()
            self.txt_lyrics.setTextCursor(cursor)
        else:
            self.txt_lyrics.setPlainText("（无歌词）")

    def _update_lyrics(self):
        if not self.lrc_lines:
            return
        length = self.player.get_length()
        if length <= 0:
            return
        pos_sec = self.player.get_position() * (length / 1000.0)

        idx = -1
        for i, (t, _) in enumerate(self.lrc_lines):
            if t <= pos_sec:
                idx = i
            else:
                break

        if idx == self.current_lrc_index and idx >= 0:
            return

        doc = self.txt_lyrics.document()

        # 重置旧高亮组
        if self.last_highlight_start >= 0 and self.last_highlight_end >= 0:
            for i in range(self.last_highlight_start, self.last_highlight_end + 1):
                block = doc.findBlockByNumber(i)
                if block.isValid():
                    cur = QTextCursor(block)
                    cur.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)  # ← 修正
                    fmt_default = QTextCharFormat()
                    fmt_default.setForeground(QColor("#333333"))
                    cur.setCharFormat(fmt_default)

        self.current_lrc_index = idx

        if idx == -1:
            self.last_highlight_start = -1
            self.last_highlight_end = -1
            return

        current_time = self.lrc_lines[idx][0]
        start_idx = idx
        while start_idx > 0 and self.lrc_lines[start_idx - 1][0] == current_time:
            start_idx -= 1
        end_idx = idx
        while end_idx < len(self.lrc_lines) - 1 and self.lrc_lines[end_idx + 1][0] == current_time:
            end_idx += 1

        # 高亮新组：第一行黄色，其余绿色
        for i in range(start_idx, end_idx + 1):
            block = doc.findBlockByNumber(i)
            if not block.isValid():
                continue
            cur = QTextCursor(block)
            cur.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)  # ← 修正
            fmt = QTextCharFormat()
            if i == start_idx:
                fmt.setForeground(QColor("#FFD700"))
                fmt.setFontWeight(QFont.Bold)
            else:
                fmt.setForeground(QColor("#32CD32"))
            cur.setCharFormat(fmt)
            cur.clearSelection()

        self.last_highlight_start = start_idx
        self.last_highlight_end = end_idx

        first_block = doc.findBlockByNumber(start_idx)
        if first_block.isValid():
            cursor = QTextCursor(first_block)
            cursor.setPosition(first_block.position())
            self.txt_lyrics.setTextCursor(cursor)
            self.txt_lyrics.ensureCursorVisible()

    @staticmethod
    def _fmt(ms):
        s = ms // 1000
        return f"{s//60:02d}:{s%60:02d}"

# ─── 入口 ────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MusicPlayer()
    window.show()
    sys.exit(app.exec_())