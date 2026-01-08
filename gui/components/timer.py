from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QProgressBar
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QColor

class TimerComponent(QWidget):
    """Flow State Timer Component."""
    
    def __init__(self):
        super().__init__()
        self.duration = 25 * 60  # 25 minutes default
        self.remaining = self.duration
        self.is_running = False
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_timer)
        self.timer.setInterval(1000)
        
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 25, 20, 25)
        layout.setSpacing(25)
        
        # --- Timer Card ---
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 35, 200);
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(25, 25, 25, 30)
        card_layout.setSpacing(15)
        
        # Header
        lbl = QLabel("FLOW STATE")
        lbl.setStyleSheet("color: #e8eaed; font-size: 14px; font-weight: bold; letter-spacing: 1px; background: transparent; border: none;")
        card_layout.addWidget(lbl)
        
        # Timer Display
        self.time_display = QLabel("25:00")
        self.time_display.setAlignment(Qt.AlignCenter)
        self.time_display.setStyleSheet("""
            color: #bd93f9; 
            font-size: 56px; 
            font-weight: bold;
            font-family: 'Segoe UI', sans-serif;
            background: transparent;
            border: none;
        """)
        # Add a subtle glow via shadow effect in a real app, but for stylesheet only we rely on color
        card_layout.addWidget(self.time_display)
        
        # Start Button
        self.start_btn = QPushButton("START")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setFixedHeight(50)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #bd93f9, stop:1 #4F8EF7);
                color: white;
                border-radius: 25px;
                font-weight: bold;
                font-size: 16px;
                border: none;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #a87df0, stop:1 #3d7be5);
            }
            QPushButton:pressed {
                background: #333;
            }
        """)
        self.start_btn.clicked.connect(self._toggle_timer)
        card_layout.addWidget(self.start_btn)
        
        layout.addWidget(card)
        
        # --- Daily Progress ---
        progress_card = QFrame()
        progress_card.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 35, 200);
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        prog_layout = QVBoxLayout(progress_card)
        prog_layout.setContentsMargins(25, 25, 25, 25)
        prog_layout.setSpacing(15)
        
        prog_lbl = QLabel("Daily Progress")
        prog_lbl.setStyleSheet("color: white; font-size: 15px; font-weight: 600; background: transparent; border: none;")
        prog_layout.addWidget(prog_lbl)
        
        sub_lbl = QLabel("4/8 hours focused")
        sub_lbl.setStyleSheet("color: #9e9e9e; font-size: 13px; background: transparent; border: none;")
        prog_layout.addWidget(sub_lbl)
        
        # Progress Bar
        self.bar = QProgressBar()
        self.bar.setFixedHeight(12)
        self.bar.setValue(50)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255, 255, 255, 0.05);
                border-radius: 6px;
                border: none;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #bd93f9, stop:1 #4F8EF7);
                border-radius: 6px;
            }
        """)
        prog_layout.addWidget(self.bar)
        
        layout.addWidget(progress_card)
        layout.addStretch()
        
    def _toggle_timer(self):
        if self.is_running:
            self.timer.stop()
            self.start_btn.setText("RESUME")
            self.is_running = False
        else:
            self.timer.start()
            self.start_btn.setText("PAUSE")
            self.is_running = True
            
    def _update_timer(self):
        if self.remaining > 0:
            self.remaining -= 1
            m, s = divmod(self.remaining, 60)
            self.time_display.setText(f"{m:02d}:{s:02d}")
        else:
            self.timer.stop()
            self.is_running = False
            self.start_btn.setText("START")
            self.remaining = self.duration
            self.time_display.setText("25:00")
            # Could play sound here
