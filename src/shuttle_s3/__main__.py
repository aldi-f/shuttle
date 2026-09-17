from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication, QStyleFactory
    except ImportError:
        print("PySide6 is required. Install Shuttle with: pip install -e .", file=sys.stderr)
        return 1

    from shuttle_s3.ui import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Shuttle")
    app.setOrganizationName("Shuttle")
    app.setStyle(QStyleFactory.create("Fusion"))
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

