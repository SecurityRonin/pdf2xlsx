import sys
from PySide6.QtWidgets import QApplication
from pdf2xlsx.gui.main_window import MainWindow


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("pdf2xlsx")
    app.setApplicationVersion("0.1.0")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
