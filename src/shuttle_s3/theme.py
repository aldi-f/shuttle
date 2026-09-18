from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QPalette, QPen
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle, QStyleFactory

THEME_SETTING = "appearance/theme"
THEMES = ("light", "dark", "auto")
DEFAULT_THEME = "light"


class _ContrastCheckboxStyle(QProxyStyle):
    def drawPrimitive(self, element, option, painter, widget=None) -> None:
        super().drawPrimitive(element, option, painter, widget)
        if element not in (
            QStyle.PE_IndicatorCheckBox,
            QStyle.PE_IndicatorItemViewItemCheck,
        ):
            return
        border = option.palette.color(QPalette.WindowText)
        border.setAlpha(190 if option.state & QStyle.State_Enabled else 90)
        painter.save()
        painter.setPen(QPen(border))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(option.rect.adjusted(0, 0, -1, -1))
        painter.restore()


def saved_theme() -> str:
    theme = str(QSettings().value(THEME_SETTING, DEFAULT_THEME))
    return theme if theme in THEMES else DEFAULT_THEME


def save_theme(theme: str) -> None:
    if theme not in THEMES:
        raise ValueError(f"Unknown theme: {theme}")
    QSettings().setValue(THEME_SETTING, theme)


def apply_theme(app: QApplication, theme: str = DEFAULT_THEME) -> None:
    """Apply a consistent light, dark, or system-selected Fusion palette."""
    if theme not in THEMES:
        theme = DEFAULT_THEME
    app.setStyle(_ContrastCheckboxStyle(QStyleFactory.create("Fusion")))
    effective_theme = _system_theme(app) if theme == "auto" else theme
    app.setPalette(_palette(effective_theme))
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)


def refresh_auto_theme(app: QApplication) -> None:
    if saved_theme() == "auto":
        apply_theme(app, "auto")


def _system_theme(app: QApplication) -> str:
    return (
        "dark"
        if app.styleHints().colorScheme() == Qt.ColorScheme.Dark
        else "light"
    )


def _palette(theme: str) -> QPalette:
    return _dark_palette() if theme == "dark" else _light_palette()


def _light_palette() -> QPalette:
    palette = QPalette()
    colors = {
        QPalette.Window: "#f5f5f5",
        QPalette.WindowText: "#1a1a1a",
        QPalette.Base: "#ffffff",
        QPalette.AlternateBase: "#f2f2f2",
        QPalette.ToolTipBase: "#ffffdc",
        QPalette.ToolTipText: "#1a1a1a",
        QPalette.Text: "#1a1a1a",
        QPalette.Button: "#f0f0f0",
        QPalette.ButtonText: "#1a1a1a",
        QPalette.BrightText: "#ffffff",
        QPalette.Light: "#ffffff",
        QPalette.Midlight: "#e0e0e0",
        QPalette.Mid: "#a8a8a8",
        QPalette.Dark: "#696969",
        QPalette.Shadow: "#404040",
        QPalette.Highlight: "#0067c0",
        QPalette.HighlightedText: "#ffffff",
        QPalette.Accent: "#0067c0",
        QPalette.Link: "#005fb8",
        QPalette.LinkVisited: "#5c2d91",
        QPalette.PlaceholderText: "#666666",
    }
    _set_colors(palette, colors)
    disabled = QColor("#767676")
    for role in (
        QPalette.WindowText,
        QPalette.Text,
        QPalette.ButtonText,
        QPalette.PlaceholderText,
    ):
        palette.setColor(QPalette.Disabled, role, disabled)
    palette.setColor(QPalette.Disabled, QPalette.Base, QColor("#f1f1f1"))
    palette.setColor(QPalette.Disabled, QPalette.Button, QColor("#e5e5e5"))
    palette.setColor(QPalette.Disabled, QPalette.Highlight, QColor("#b5b5b5"))
    palette.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor("#666666"))
    palette.setColor(QPalette.Disabled, QPalette.Accent, QColor("#b5b5b5"))
    return palette


def _dark_palette() -> QPalette:
    palette = QPalette()
    colors = {
        QPalette.Window: "#2b2d30",
        QPalette.WindowText: "#f2f2f2",
        QPalette.Base: "#18191b",
        QPalette.AlternateBase: "#242629",
        QPalette.ToolTipBase: "#35383c",
        QPalette.ToolTipText: "#f2f2f2",
        QPalette.Text: "#f2f2f2",
        QPalette.Button: "#3a3d41",
        QPalette.ButtonText: "#f2f2f2",
        QPalette.BrightText: "#ffffff",
        QPalette.Light: "#50545a",
        QPalette.Midlight: "#45494e",
        QPalette.Mid: "#303338",
        QPalette.Dark: "#1d1f21",
        QPalette.Shadow: "#101112",
        QPalette.Highlight: "#287eb5",
        QPalette.HighlightedText: "#ffffff",
        QPalette.Accent: "#287eb5",
        QPalette.Link: "#69b7ff",
        QPalette.LinkVisited: "#b99cff",
        QPalette.PlaceholderText: "#858a90",
    }
    _set_colors(palette, colors)
    disabled = QColor("#777b80")
    for role in (
        QPalette.WindowText,
        QPalette.Text,
        QPalette.ButtonText,
        QPalette.PlaceholderText,
    ):
        palette.setColor(QPalette.Disabled, role, disabled)
    palette.setColor(QPalette.Disabled, QPalette.Base, QColor("#222427"))
    palette.setColor(QPalette.Disabled, QPalette.Button, QColor("#303236"))
    palette.setColor(QPalette.Disabled, QPalette.Highlight, QColor("#41454a"))
    palette.setColor(QPalette.Disabled, QPalette.HighlightedText, disabled)
    palette.setColor(QPalette.Disabled, QPalette.Accent, QColor("#41454a"))
    return palette


def _set_colors(palette: QPalette, colors: dict[QPalette.ColorRole, str]) -> None:
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
