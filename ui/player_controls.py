"""播放器控制条：顶部（频道名 + 菜单 + 视频/音频/字幕轨道下拉）与底部（播放控制）。

挂在 PlayerPanel.video_stack_host 上，压在 mpv 原生窗口之上，由 PlayerPanel 负责
定位与"鼠标活动显示 / 静止自动隐藏"。样式沿用应用既有半透明深色调色板。
"""

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.icon_button import IconButton
from ui.apple_tv_control_bar import AppleTVControlBar, SvgIconButton
from utils.i18n import tr


_BAR_QSS = """
QFrame#playerTopBar {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 0, y2: 1,
        stop: 0 rgba(58, 68, 86, 220),
        stop: 1 rgba(22, 28, 37, 226)
    );
    border-bottom: 1px solid rgba(120, 180, 255, 115);
}
QFrame#playerBottomBar {
    background: rgba(14, 20, 27, 0.92);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
}
QFrame#controlCell, QFrame#controlPanel {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(210, 245, 250, 0.16);
    border-radius: 8px;
}
QFrame#controlPanel {
    background: rgba(12, 18, 22, 0.28);
}
QToolButton, QPushButton {
    background: rgba(255, 255, 255, 18);
    color: #e7eef7;
    border: 1px solid rgba(120, 180, 255, 88);
    border-radius: 9px;
    padding: 6px 11px;
    font-size: 14px;
}
QToolButton:hover, QPushButton:hover {
    background: rgba(120, 180, 255, 38);
    border: 1px solid rgba(120, 180, 255, 155);
}
/* 底部播放控制按钮：紧凑、仅图标大小、无背景 */
QPushButton#ctrlBtn {
    background: transparent;
    padding: 0;
    color: #f6f8fb;
    font-size: 20px;
    border-radius: 8px;
}
QPushButton#ctrlBtn:hover { background: rgba(255, 255, 255, 0.15); }
QPushButton#ctrlBtn[primary="true"] {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.08);
}
QPushButton#ctrlBtn[active="true"] {
    background: rgba(48, 132, 255, 0.22);
    color: #ffffff;
}
QToolButton::menu-indicator { image: none; }
QMenu {
    background: #202a39;
    color: #e4e7f0;
    border: 1px solid rgba(120, 180, 255, 120);
    padding: 4px;
}
QMenu::item { padding: 6px 24px 6px 16px; border-radius: 4px; }
QMenu::item:selected { background: rgba(120, 180, 255, 55); }
QMenu::item:checked { color: #8bb8ff; }
QLabel#barTitle { color: #ffffff; font-size: 15px; font-weight: 600; }
QLabel#barSubtitle { color: #a8b3d1; font-size: 12px; }
QLabel#barTime {
    color: #f7f9fc;
    font-size: 11px;
    font-weight: 500;
    min-width: 44px;
}
QComboBox#speedCombo {
    background: transparent;
    color: #f7f9fc;
    border: none;
    padding: 0;
    font-size: 0px;
}
QComboBox#speedCombo:hover {
    background: transparent;
}
QComboBox#speedCombo::drop-down {
    border: none;
    width: 0;
}
QComboBox#speedCombo QAbstractItemView {
    background: #22252f;
    color: #e4e7f0;
    border: 1px solid #353945;
    selection-background-color: #3d5a80;
}
QLabel#liveBadge {
    color: #ffffff; font-size: 15px; font-weight: 700;
    background: transparent;
}
QSlider#barProgress::groove:horizontal {
    height: 4px; background: rgba(255,255,255,0.14); border-radius: 2px;
}
QSlider#barProgress::sub-page:horizontal {
    background: #1688ff; border-radius: 2px;
}
QSlider#barProgress::handle:horizontal {
    background: #ffffff; width: 12px; height: 12px;
    margin: -4px 0; border-radius: 6px;
    border: 2px solid #2d8dff;
}
QSlider#barVolume::groove:horizontal {
    height: 7px; background: rgba(255,255,255,0.16); border-radius: 4px;
}
QSlider#barVolume::sub-page:horizontal { background: #1688ff; border-radius: 4px; }
QSlider#barVolume::handle:horizontal {
    background: #ffffff; width: 15px; height: 15px; margin: -4px 0; border-radius: 8px;
}
QSlider#barVolume::groove:vertical {
    width: 4px; background: rgba(0,0,0,0.48); border-radius: 2px;
}
QSlider#barVolume::sub-page:vertical { background: #d9f1ee; border-radius: 2px; }
QSlider#barVolume::add-page:vertical { background: rgba(255,255,255,0.14); border-radius: 2px; }
QSlider#barVolume::handle:vertical {
    background: #ffffff; width: 10px; height: 10px; margin: 0 -3px; border-radius: 5px;
}
"""


_TRACK_POPUP_QSS = """
#trackPopupCard {
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(58, 68, 86, 238),
        stop:1 rgba(22, 28, 37, 238)
    );
    border: 1px solid rgba(120, 180, 255, 145);
    border-radius: 10px;
}
QLabel#tiTitle { color: #edf4ff; font-size: 14px; font-weight: 600; background: transparent; }
QLabel#tiTitleSel { color: #8ed0ff; font-size: 14px; font-weight: 700; background: transparent; }
QLabel#tiSub { color: #9fc9ff; font-size: 11px; background: transparent; }
#trackItem { border-radius: 8px; background: transparent; }
#trackItem:hover { background: rgba(120, 180, 255, 42); }
#trackItemSel { border-radius: 8px; background: rgba(105, 178, 255, 85); }
#trackItemDisabled { border-radius: 8px; background: transparent; }
"""


class TrackItem(QFrame):
    """轨道弹窗中的一项：两行（主标题 + 灰色副说明），可点击。"""
    clicked = Signal(object)

    def __init__(self, title, subtitle, value, selected=False, parent=None):
        super().__init__(parent)
        self._selectable = value is not None
        if selected:
            self.setObjectName("trackItemSel")
        else:
            self.setObjectName("trackItem" if self._selectable else "trackItemDisabled")
        self._value = value
        self.setCursor(Qt.PointingHandCursor if self._selectable else Qt.ArrowCursor)
        if not self._selectable:
            self.setToolTip("")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 7, 12, 7)
        lay.setSpacing(1)
        t = QLabel(title)
        t.setObjectName("tiTitleSel" if selected else "tiTitle")
        lay.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("tiSub")
            lay.addWidget(s)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._selectable:
            self.clicked.emit(self._value)
        super().mousePressEvent(event)


class TrackPopup(QFrame):
    """玻璃风轨道弹窗（顶层 Popup 窗口），带高度展开动画。"""
    item_selected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(_TRACK_POPUP_QSS)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)  # 给阴影/圆角留边
        self.card = QFrame()
        self.card.setObjectName("trackPopupCard")
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(6, 6, 6, 6)
        self.card_layout.setSpacing(2)
        outer.addWidget(self.card)
        self._anim = None

    def set_items(self, items):
        """items: list of (title, subtitle, value, selected)。"""
        while self.card_layout.count():
            it = self.card_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for title, subtitle, value, selected in items:
            row = TrackItem(title, subtitle, value, selected, self.card)
            row.clicked.connect(self._on_item_clicked)
            self.card_layout.addWidget(row)

    def _on_item_clicked(self, value):
        self.item_selected.emit(value)
        self.close()

    def popup_at(self, global_pos, width=240):
        """在 global_pos 处展开显示（卡片高度从 0 展开的动画）。"""
        self.setFixedWidth(width)
        self.adjustSize()
        self.move(global_pos)
        card_h = self.card.sizeHint().height()
        self.show()
        self.raise_()
        # 卡片展开动画（窗口透明固定，卡片由 0 展开）
        self.card.setMaximumHeight(0)
        self._anim = QPropertyAnimation(self.card, b"maximumHeight", self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.setStartValue(0)
        self._anim.setEndValue(card_h)
        self._anim.finished.connect(lambda: self.card.setMaximumHeight(16777215))
        self._anim.start()


class PlayerTopBar(QFrame):
    """顶部条：频道标题 + 菜单 + 视频/音频/字幕轨道下拉。"""

    menu_clicked = Signal()
    detail_clicked = Signal()
    stop_clicked = Signal()
    fullscreen_clicked = Signal()
    load_epg_clicked = Signal()
    download_epg_clicked = Signal()
    quality_selected = Signal(object)         # 清晰度档位 key
    video_track_selected = Signal(object)     # mpv vid（int 或 "auto"/"no"）
    audio_track_selected = Signal(object)     # mpv aid
    subtitle_track_selected = Signal(object)  # mpv sid（int 或 "no"）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playerTopBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(_BAR_QSS)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(8)

        # 菜单按钮（最左：滑出资源库）
        self.menu_button = SvgIconButton("playlist", 44, self)
        self.menu_button.setToolTip("打开资源面板")
        self.menu_button.clicked.connect(self.menu_clicked.emit)
        layout.addWidget(self.menu_button)

        # 标题区（频道名 + 分组）
        title_box = QWidget()
        tb_layout = QHBoxLayout(title_box)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(10)
        self.title_label = QLabel(tr("player.no_media"))
        self.title_label.setObjectName("barTitle")
        self.subtitle_label = QLabel("")
        self.subtitle_label.setObjectName("barSubtitle")
        tb_layout.addWidget(self.title_label)
        tb_layout.addWidget(self.subtitle_label)
        layout.addWidget(title_box)
        layout.addStretch(1)

        self.stop_button = QPushButton("")
        self.stop_button.setToolTip("")
        self.stop_button.clicked.connect(self.stop_clicked.emit)
        layout.addWidget(self.stop_button)

        self.fullscreen_button = QPushButton("")
        self.fullscreen_button.setToolTip("")
        self.fullscreen_button.clicked.connect(self.fullscreen_clicked.emit)
        layout.addWidget(self.fullscreen_button)

        self.load_epg_button = QPushButton("")
        self.load_epg_button.setToolTip("")
        self.load_epg_button.clicked.connect(self.load_epg_clicked.emit)
        layout.addWidget(self.load_epg_button)

        self.download_epg_button = QPushButton("")
        self.download_epg_button.setToolTip("")
        self.download_epg_button.clicked.connect(self.download_epg_clicked.emit)
        layout.addWidget(self.download_epg_button)

        # 清晰度档位（key, 主标题, 副说明）
        self._quality_presets = [
            ("liu", "", ""),
            ("sd",  "", ""),
            ("hd",  "", ""),
            ("max", "", ""),
        ]
        self._current_quality = "liu"

        # 清晰度按钮（点击弹出玻璃风动画弹窗）
        self.quality_button = QToolButton()
        self.quality_button.setText("")
        self.quality_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.quality_button.clicked.connect(self._open_quality_popup)
        layout.addWidget(self.quality_button)

        # 三个轨道下拉（点击弹出玻璃风动画弹窗）
        self.video_button = self._make_track_button("", self.video_track_selected, "video")
        self.audio_button = self._make_track_button("", self.audio_track_selected, "audio")
        self.subtitle_button = self._make_track_button("", self.subtitle_track_selected, "subtitle")
        layout.addWidget(self.video_button)
        layout.addWidget(self.audio_button)
        layout.addWidget(self.subtitle_button)

        # 频道详情按钮（最右：→ 滑出频道详情）
        self.detail_button = QPushButton("")
        self.detail_button.setToolTip("")
        self.detail_button.clicked.connect(self.detail_clicked.emit)
        layout.addWidget(self.detail_button)

        # 各类轨道的弹窗项缓存：kind -> list[(title, subtitle, value, selected)]
        self._track_items = {"video": [], "audio": [], "subtitle": []}
        self.apply_language()

    def apply_language(self):
        self.stop_button.setText(tr("player.stop"))
        self.fullscreen_button.setText(tr("player.fullscreen_f1"))
        self.load_epg_button.setText(tr("player.load_epg"))
        self.download_epg_button.setText(tr("player.download_epg"))
        self.detail_button.setText(tr("player.detail"))
        self._quality_presets = [
            ("liu", tr("player.quality.smooth"), tr("player.quality.smooth.desc")),
            ("sd", tr("player.quality.sd"), tr("player.quality.sd.desc")),
            ("hd", tr("player.quality.hd"), tr("player.quality.hd.desc")),
            ("max", tr("player.quality.max"), tr("player.quality.max.desc")),
        ]
        self._set_track_button_texts()
        self.set_current_quality(self._current_quality)
        if self.title_label.text() in {"No Media", "未播放"}:
            self.title_label.setText(tr("player.no_media"))

    def _set_track_button_texts(self):
        self.video_button.setText(f"{tr('player.track.video')} ▾")
        self.audio_button.setText(f"{tr('player.track.audio')} ▾")
        self.subtitle_button.setText(f"{tr('player.track.subtitle')} ▾")

    def _make_track_button(self, text, signal, kind):
        btn = QToolButton()
        btn.setText(f"{text} ▾")
        btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        btn.clicked.connect(lambda: self._open_track_popup(btn, signal, kind))
        return btn

    def _open_track_popup(self, button, signal, kind):
        items = self._track_items.get(kind) or []
        if not items:
            return
        popup = TrackPopup(self)
        popup.set_items(items)
        popup.item_selected.connect(signal.emit)
        # 在按钮左下方展开（弹窗左边缘对齐按钮左边缘，留出阴影边距）
        gp = button.mapToGlobal(QPoint(-8, button.height() - 2))
        popup.popup_at(gp, width=240)

    def _open_quality_popup(self):
        items = [
            (name, sub, key, key == self._current_quality)
            for key, name, sub in self._quality_presets
        ]
        popup = TrackPopup(self)
        popup.set_items(items)
        popup.item_selected.connect(self.quality_selected.emit)
        gp = self.quality_button.mapToGlobal(QPoint(-8, self.quality_button.height() - 2))
        popup.popup_at(gp, width=220)

    def set_current_quality(self, key):
        """同步顶部条清晰度高亮 + 按钮文字。"""
        self._current_quality = key
        name = next((n for k, n, _s in self._quality_presets if k == key), None)
        if name:
            self.quality_button.setText(f"{name} ▾")

    def set_title(self, name, subtitle=""):
        self.title_label.setText(name or tr("player.no_media"))
        self.subtitle_label.setText(subtitle or "")

    # ---- 轨道弹窗内容构建 ----
    def populate_tracks(self, track_list):
        track_list = track_list or []
        videos = [t for t in track_list if t.get("type") == "video"]
        audios = [t for t in track_list if t.get("type") == "audio"]
        subs = [t for t in track_list if t.get("type") == "sub"]

        self._track_items["video"] = self._build_items(
            videos, self._video_label,
            auto=(tr("track.auto"), tr("track.auto.video.desc"), "auto"))
        self._track_items["audio"] = self._build_items(
            audios, self._audio_label,
            auto=(tr("track.auto"), tr("track.auto.audio.desc"), "auto"))
        self._track_items["subtitle"] = self._build_items(
            subs, self._sub_label,
            none=(tr("track.subtitle.off"), tr("track.subtitle.off.desc"), "no"))

        self.video_button.setEnabled(bool(self._track_items["video"]))
        self.audio_button.setEnabled(bool(self._track_items["audio"]))
        self.subtitle_button.setEnabled(bool(self._track_items["subtitle"]))

    def _build_items(self, tracks, label_fn, auto=None, none=None):
        """返回 [(title, subtitle, value, selected), ...]。"""
        items = []
        any_selected = any(t.get("selected") for t in tracks)
        # 顶部「自动」(视频/音频) 或「关闭字幕」(字幕)
        head = auto or none
        if head is not None:
            # 自动：无轨道被显式选中时视为选中；关闭字幕：无字幕选中时选中
            items.append((head[0], head[1], head[2], not any_selected))
        for t in tracks:
            title, sub = label_fn(t)
            items.append((title, sub, t.get("playback_id"), bool(t.get("selected"))))
        return items

    @staticmethod
    def _format_number(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number <= 0:
            return None
        return number

    @classmethod
    def _format_bitrate(cls, value):
        number = cls._format_number(value)
        if not number:
            return ""
        if number >= 1_000_000:
            text = f"{number / 1_000_000:.1f}".rstrip("0").rstrip(".")
            return f"{text} Mbps"
        if number >= 1_000:
            text = f"{number / 1_000:.0f}"
            return f"{text} Kbps"
        return f"{int(number)} bps"

    @classmethod
    def _format_rate(cls, value, unit):
        number = cls._format_number(value)
        if not number:
            return ""
        if float(number).is_integer():
            return f"{int(number)}{unit}"
        return f"{number:.2f}".rstrip("0").rstrip(".") + unit

    @classmethod
    def _format_samplerate(cls, value):
        number = cls._format_number(value)
        if not number:
            return ""
        if number >= 1000:
            text = f"{number / 1000:.1f}".rstrip("0").rstrip(".")
            return f"{text} kHz"
        return f"{int(number)} Hz"

    @staticmethod
    def _append_source_hint(parts, track):
        if track.get("source") == "file" and not track.get("playback_id"):
            parts.append(tr("track.file_only"))

    @staticmethod
    def _video_label(t):
        h = t.get("demux-h")
        w = t.get("demux-w")
        codec = (t.get("codec") or "").upper()
        resolution = t.get("resolution") or (f"{w}x{h}" if w and h else "")
        if h:
            title = f"{h}p"
        elif resolution:
            title = str(resolution)
        else:
            title = f"{tr('track.video.id')} {t.get('id')}"
        sub_parts = []
        if resolution:
            sub_parts.append(str(resolution).replace("x", "×"))
        if codec:
            sub_parts.append(codec)
        bitrate = PlayerTopBar._format_bitrate(t.get("demux-bitrate"))
        if bitrate:
            sub_parts.append(bitrate)
        fps = PlayerTopBar._format_rate(t.get("demux-fps"), "fps")
        if fps:
            sub_parts.append(fps)
        if t.get("lang"):
            sub_parts.append(str(t.get("lang")))
        PlayerTopBar._append_source_hint(sub_parts, t)
        return str(title), " · ".join(sub_parts) or tr("track.video")

    @staticmethod
    def _audio_label(t):
        title = t.get("lang") or t.get("title") or f"{tr('track.audio.id')} {t.get('id')}"
        sub_parts = []
        if t.get("lang"):
            sub_parts.append(str(t.get("lang")))
        if t.get("codec"):
            sub_parts.append(str(t.get("codec")).upper())
        bitrate = PlayerTopBar._format_bitrate(t.get("demux-bitrate"))
        if bitrate:
            sub_parts.append(bitrate)
        samplerate = PlayerTopBar._format_samplerate(t.get("demux-samplerate"))
        if samplerate:
            sub_parts.append(samplerate)
        if t.get("demux-channel-count"):
            sub_parts.append(f"{t.get('demux-channel-count')}ch")
        PlayerTopBar._append_source_hint(sub_parts, t)
        return str(title), " · ".join(sub_parts) or tr("track.audio")

    @staticmethod
    def _sub_label(t):
        title = t.get("title") or t.get("lang") or f"{tr('track.subtitle.id')} {t.get('id')}"
        sub_parts = []
        if t.get("lang"):
            sub_parts.append(str(t.get("lang")))
        if t.get("codec"):
            sub_parts.append(str(t.get("codec")).upper())
        PlayerTopBar._append_source_hint(sub_parts, t)
        sub = " · ".join(sub_parts) or tr("track.subtitle")
        return str(title), sub


class PlayerBottomBar(QFrame):
    """Bottom transport console."""

    play_pause_toggled = Signal()
    play_requested = Signal()
    pause_requested = Signal()
    menu_requested = Signal()
    stop_requested = Signal()
    prev_channel = Signal()
    next_channel = Signal()
    skip_requested = Signal(int)        # 相对秒数（±）
    seek_requested = Signal(float)      # 0..1 进度比例
    volume_changed = Signal(int)        # 0..100
    mute_toggled = Signal()
    speed_changed = Signal(float)
    fullscreen_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playerBottomBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(_BAR_QSS)
        self.setFixedHeight(96)

        self._seeking = False
        self._has_duration = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        left_stack = QVBoxLayout()
        left_stack.setContentsMargins(0, 0, 0, 0)
        left_stack.setSpacing(6)
        self.menu_button = self._cell_button("menu", self.menu_requested.emit, cell_size=(44, 38), button_size=(32, 30), icon_scale=0.85)
        self.prev_button = self._cell_button("previous", self.prev_channel.emit, cell_size=(44, 40), button_size=(32, 30), icon_scale=0.85)
        left_stack.addWidget(self.menu_button.parentWidget())
        left_stack.addWidget(self.prev_button.parentWidget())
        layout.addLayout(left_stack)

        play_cell, play_lay = self._make_cell(76, 84)
        self.play_button = self._btn("pause", self.play_pause_toggled.emit, size=(58, 54), icon_scale=1.15)
        play_lay.addStretch(1)
        play_lay.addWidget(self.play_button, 0, Qt.AlignCenter)
        play_lay.addStretch(1)
        layout.addWidget(play_cell)

        center_panel = QFrame(self)
        center_panel.setObjectName("controlPanel")
        center_panel.setMinimumWidth(420)
        center_panel.setFixedHeight(84)
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(10, 5, 10, 5)
        center_layout.setSpacing(2)

        self.current_time_label = QLabel("00:00")
        self.current_time_label.setObjectName("barTime")
        self.current_time_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.progress = QSlider(Qt.Horizontal)
        self.progress.setObjectName("barProgress")
        self.progress.setRange(0, 1000)
        self.progress.sliderPressed.connect(self._on_progress_pressed)
        self.progress.sliderReleased.connect(self._on_progress_released)
        center_layout.addWidget(self.progress)

        self.live_badge = QLabel("LIVE")
        self.live_badge.setObjectName("liveBadge")
        self.live_badge.setAlignment(Qt.AlignCenter)
        self.live_badge.setVisible(False)
        center_layout.addWidget(self.live_badge)

        self.duration_label = QLabel("00:00")
        self.duration_label.setObjectName("barTime")
        self.duration_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        time_row = QHBoxLayout()
        time_row.setContentsMargins(0, 0, 0, 0)
        time_row.setSpacing(8)
        time_row.addWidget(self.current_time_label)
        time_row.addStretch(1)
        time_row.addWidget(self.duration_label)
        center_layout.addLayout(time_row)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        self.stop_button = self._cell_button("stop", self.stop_requested.emit, cell_size=(54, 40), button_size=(36, 32), icon_scale=0.9)
        self.forward_button = self._cell_button("forward10", lambda: self.skip_requested.emit(10), cell_size=(62, 40), button_size=(52, 34), icon_scale=0.78)
        self.rewind_button = self._cell_button("rewind10", lambda: self.skip_requested.emit(-10), cell_size=(62, 40), button_size=(52, 34), icon_scale=0.78)
        self.next_button = self._cell_button("next", self.next_channel.emit, cell_size=(54, 40), button_size=(36, 32), icon_scale=0.9)
        action_row.addWidget(self.stop_button.parentWidget())
        action_row.addWidget(self.forward_button.parentWidget())
        action_row.addStretch(1)
        action_row.addWidget(self.rewind_button.parentWidget())
        action_row.addWidget(self.next_button.parentWidget())
        center_layout.addLayout(action_row)
        layout.addWidget(center_panel, 1)

        speed_cell, speed_lay = self._make_cell(56, 84)
        self.speed_primary_label = QLabel("1x")
        self.speed_primary_label.setObjectName("barTime")
        self.speed_primary_label.setAlignment(Qt.AlignCenter)
        self.speed_secondary_label = QLabel("1.25x")
        self.speed_secondary_label.setObjectName("barTime")
        self.speed_secondary_label.setAlignment(Qt.AlignCenter)
        self.speed_tertiary_label = QLabel("1.5x")
        self.speed_tertiary_label.setObjectName("barTime")
        self.speed_tertiary_label.setAlignment(Qt.AlignCenter)
        self.speed_arrow_label = QLabel("⌄")
        self.speed_arrow_label.setObjectName("barTime")
        self.speed_arrow_label.setAlignment(Qt.AlignCenter)
        self.speed_combo = QComboBox()
        self.speed_combo.setObjectName("speedCombo")
        self.speed_combo.setToolTip("")
        self.speed_combo.setFixedSize(1, 1)
        for speed in (1.0, 1.25, 1.5, 2.0, 2.5, 3.0):
            label = f"{int(speed)}x" if float(speed).is_integer() else f"{speed:g}x"
            self.speed_combo.addItem(label, speed)
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        speed_lay.setContentsMargins(2, 2, 2, 2)
        speed_lay.addWidget(self.speed_primary_label)
        speed_lay.addWidget(self.speed_secondary_label)
        speed_lay.addWidget(self.speed_tertiary_label)
        speed_lay.addWidget(self.speed_arrow_label)
        speed_lay.addWidget(self.speed_combo)
        speed_cell.mousePressEvent = lambda event: self.speed_combo.showPopup()
        layout.addWidget(speed_cell)

        volume_cell, volume_lay = self._make_cell(56, 84)
        self.volume_button = self._btn("volume", self.mute_toggled.emit, size=(34, 28), icon_scale=0.9)
        self.volume_slider = QSlider(Qt.Vertical)
        self.volume_slider.setObjectName("barVolume")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedHeight(40)
        self.volume_slider.valueChanged.connect(self.volume_changed.emit)
        volume_lay.addWidget(self.volume_button, 0, Qt.AlignCenter)
        volume_lay.addWidget(self.volume_slider, 0, Qt.AlignCenter)
        layout.addWidget(volume_cell)

        right_stack = QVBoxLayout()
        right_stack.setContentsMargins(0, 0, 0, 0)
        right_stack.setSpacing(6)
        spacer_cell, _spacer_lay = self._make_cell(44, 38)
        self.fullscreen_button = self._cell_button("fullscreen", self.fullscreen_requested.emit, cell_size=(44, 40), button_size=(32, 30), icon_scale=0.9)
        right_stack.addWidget(spacer_cell)
        right_stack.addWidget(self.fullscreen_button.parentWidget())
        layout.addLayout(right_stack)

        self.set_duration_mode(False)
        self.set_playing(False)

    def _make_cell(self, width, height):
        cell = QFrame(self)
        cell.setObjectName("controlCell")
        cell.setFixedSize(width, height)
        lay = QVBoxLayout(cell)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        return cell, lay

    def _cell_button(self, icon_name, callback, cell_size=(84, 80), button_size=(56, 52), icon_scale=1.0):
        cell, lay = self._make_cell(*cell_size)
        button = self._btn(icon_name, callback, size=button_size, icon_scale=icon_scale)
        lay.addStretch(1)
        lay.addWidget(button, 0, Qt.AlignCenter)
        lay.addStretch(1)
        return button

    def _btn(self, icon_name, callback, variant="plain", size=(42, 42), icon_scale=1.0):
        b = IconButton(icon_name, "", self, size=size, variant=variant, icon_scale=icon_scale)
        b.clicked.connect(callback)
        return b

    def set_duration_mode(self, has_duration):
        self._has_duration = bool(has_duration)
        for w in (
            self.progress,
            self.current_time_label,
            self.duration_label,
            self.stop_button.parentWidget(),
            self.rewind_button.parentWidget(),
            self.forward_button.parentWidget(),
        ):
            w.setVisible(self._has_duration)
        self.live_badge.setVisible(not self._has_duration)
        if not self._has_duration:
            self.progress.setValue(0)

    def update_progress(self, position, duration):
        if self._seeking or not self._has_duration:
            return
        if duration and position is not None and duration > 0:
            self.progress.setValue(int((position / duration) * 1000))
            self.current_time_label.setText(self._format_time(position))
            self.duration_label.setText(self._format_time(duration))

    def set_playing(self, playing):
        self.play_button.set_icon("pause" if playing else "play")
        self._set_button_active(self.play_button, bool(playing))

    def _set_button_active(self, button, active):
        if hasattr(button, "set_active"):
            button.set_active(active)
            return
        button.setProperty("active", "true" if active else "false")
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def set_volume(self, value):
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(int(max(0, min(100, value))))
        self.volume_slider.blockSignals(False)

    def set_muted(self, muted):
        self.volume_button.set_icon("mute" if muted else "volume")

    def reset_speed(self):
        self.set_speed(1.0)

    def set_speed(self, speed):
        try:
            speed_value = float(speed)
        except (TypeError, ValueError):
            speed_value = 1.0
        index = self.speed_combo.findData(speed_value)
        if index < 0:
            index = 0
        label = self.speed_combo.itemText(index) if self.speed_combo.count() else "1x"
        self.speed_primary_label.setText(label)
        self.speed_combo.blockSignals(True)
        self.speed_combo.setCurrentIndex(index)
        self.speed_combo.blockSignals(False)

    def _on_speed_changed(self, _index):
        try:
            speed = float(self.speed_combo.currentData() or 1.0)
        except (TypeError, ValueError):
            speed = 1.0
        self.speed_primary_label.setText(self.speed_combo.currentText() or "1x")
        self.speed_changed.emit(speed)

    def _on_progress_pressed(self):
        self._seeking = True

    def _on_progress_released(self):
        self._seeking = False
        self.seek_requested.emit(self.progress.value() / 1000.0)

    @staticmethod
    def _format_time(seconds):
        if seconds is None or seconds < 0:
            return "00:00"
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


class PlayerBottomBar(AppleTVControlBar):
    """Compatibility wrapper for the Apple TV style control bar."""

    pass
