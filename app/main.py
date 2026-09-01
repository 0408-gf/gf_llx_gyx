from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from app.window import MainWindow


def main() -> int:
    logging.basicConfig(filename="football_jc.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("足球竞彩分析助手")
    app.setOrganizationName("FootballJCAssistant")
    app.setApplicationVersion("0.1.0")
    window = MainWindow(); window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
