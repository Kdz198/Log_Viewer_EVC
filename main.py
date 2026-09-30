import sys

from PySide6.QtWidgets import QApplication

from logviewer.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    # allow dropping a file onto the .exe icon / "Open with"
    if len(sys.argv) > 1:
        window.open_path(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
