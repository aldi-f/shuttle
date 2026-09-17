from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 is required. Install Shuttle with: pip install -e .", file=sys.stderr)
        return 1

    from shuttle_s3.theme import apply_theme
    from shuttle_s3.ui import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Shuttle")
    app.setOrganizationName("Shuttle")
    apply_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

