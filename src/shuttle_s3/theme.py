from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory


def apply_theme(app: QApplication) -> None:
    """Apply the same dark widget geometry and colors on every platform."""
    app.setStyle(QStyleFactory.create("Fusion"))

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
    for role, color in colors.items():
        palette.setColor(role, QColor(color))

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

    app.setPalette(palette)
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)
