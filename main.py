"""
Pocket AI - Main Entry Point
"""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from gui.app import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Set default font
    app.setFont(QFont("Segoe UI", 10))
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())
