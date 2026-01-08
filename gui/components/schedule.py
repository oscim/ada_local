from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, 
    QCalendarWidget, QScrollArea, QPushButton, QDialog, QLineEdit, QDateTimeEdit, QTextEdit, QComboBox
)
from PySide6.QtCore import Qt, QDate, QTime, QDateTime, Signal
from PySide6.QtGui import QTextCharFormat, QColor, QFont
from core.calendar import calendar_manager

class ScheduleComponent(QWidget):
    """Component for displaying daily schedule and calendar."""
    
    def __init__(self):
        super().__init__()
        self.selected_date = QDate.currentDate()
        self._setup_ui()
        self.refresh_events()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # --- Timeline Section ---
        timeline_container = QFrame()
        timeline_container.setStyleSheet("background: transparent;")
        timeline_layout = QVBoxLayout(timeline_container)
        
        # Header
        header_layout = QHBoxLayout()
        self.date_label = QLabel(self.selected_date.toString("dddd, MMMM d"))
        self.date_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold; background: transparent;")
        header_layout.addWidget(self.date_label)
        header_layout.addStretch()
        
        add_btn = QPushButton("+")
        add_btn.setFixedSize(30, 30)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet("""
            QPushButton { 
                background: #3d3d3d; 
                color: #bd93f9; 
                border-radius: 15px; 
                border: 1px solid #bd93f9; 
                font-size: 16px; 
            }
            QPushButton:hover { 
                background: rgba(189, 147, 249, 0.2); 
                color: white;
            }
        """)
        add_btn.clicked.connect(self._show_add_event_dialog)
        header_layout.addWidget(add_btn)
        
        timeline_layout.addLayout(header_layout)
        
        # Scrollable Timeline
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.timeline_content = QWidget()
        self.timeline_content.setStyleSheet("background: transparent;")
        self.timeline_layout = QVBoxLayout(self.timeline_content)
        self.timeline_layout.setSpacing(12)
        self.timeline_layout.addStretch()
        
        scroll.setWidget(self.timeline_content)
        timeline_layout.addWidget(scroll, 2) # Stretch factor 2
        
        layout.addWidget(timeline_container, 2)
        
        # --- Calendar Widget ---
        self.calendar = QCalendarWidget()
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.clicked.connect(self._on_date_selected)
        self.calendar.setStyleSheet("""
            QCalendarWidget QWidget { 
                background-color: transparent; 
                color: white; 
            }
            QCalendarWidget QToolButton { 
                color: #e8eaed; 
                font-weight: bold;
                icon-size: 24px; 
                background: transparent;
                border: none;
                margin: 5px;
            }
            QCalendarWidget QToolButton:hover {
                background: #2b2d31;
                border-radius: 4px;
            }
            QCalendarWidget QMenu { 
                background-color: #2b2d31; 
                color: white; 
                border: 1px solid #3d3d3d;
            }
            QCalendarWidget QSpinBox { 
                color: white; 
                background: #3d3d3d; 
                selection-background-color: #bd93f9; 
                border-radius: 4px;
            }
            QCalendarWidget QAbstractItemView:enabled { 
                color: #e8eaed; 
                background: transparent;
                selection-background-color: #bd93f9; 
                selection-color: white; 
                border-radius: 16px; 
            }
            QCalendarWidget QAbstractItemView:disabled { 
                color: #555; 
            }
        """)
        
        layout.addWidget(self.calendar, 1) # Stretch factor 1

    def _on_date_selected(self, date):
        self.selected_date = date
        self.date_label.setText(date.toString("dddd, MMMM d"))
        self.refresh_events()
        
    def refresh_events(self):
        """Clear timeline and load events for selected date."""
        # Clear existing
        while self.timeline_layout.count() > 1: # Keep stretch
            item = self.timeline_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        # Load from DB
        date_str = self.selected_date.toString("yyyy-MM-dd")
        events = calendar_manager.get_events(date_str)
        
        if not events:
            # Empty state
            empty = QLabel("No events scheduled")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #6e6e6e; padding: 20px; font-style: italic;")
            self.timeline_layout.insertWidget(0, empty)
        else:
            for event in events:
                self._add_event_card(event)

    def _add_event_card(self, event):
        """Create a card for a single event."""
        card = QFrame()
        card.setCursor(Qt.PointingHandCursor)
        
        # Color coding based on category
        cat = event['category']
        accent_color = "#bd93f9" if cat == "WORK" else "#4F8EF7" if cat == "PERSONAL" else "#50fa7b"
        
        card.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(255, 255, 255, 0.05);
                border-radius: 8px;
                border-left: 3px solid {accent_color};
            }}
            QFrame:hover {{ background-color: rgba(255, 255, 255, 0.1); }}
        """)
        
        layout = QHBoxLayout(card)
        layout.setContentsMargins(15, 12, 15, 12)
        
        # Time
        start_dt = datetime.strptime(event['start_time'], "%Y-%m-%d %H:%M:%S")
        time_str = start_dt.strftime("%I:%M %p").lstrip("0")
        
        time_lbl = QLabel(time_str)
        time_lbl.setStyleSheet(f"color: {accent_color}; font-weight: bold; font-size: 13px; background: transparent; border: none;")
        time_lbl.setFixedWidth(65)
        layout.addWidget(time_lbl)
        
        # Details
        details = QVBoxLayout()
        details.setSpacing(4)
        
        title_lbl = QLabel(event['title'])
        title_lbl.setStyleSheet("color: white; font-weight: 500; font-size: 14px; background: transparent; border: none;")
        details.addWidget(title_lbl)
        
        cat_lbl = QLabel(cat)
        cat_lbl.setStyleSheet(f"color: {accent_color}; font-size: 10px; background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px;")
        cat_lbl.setFixedWidth(cat_lbl.sizeHint().width() + 15)
        details.addWidget(cat_lbl)
        
        layout.addLayout(details)
        layout.addStretch()
        
        # Delete button
        del_btn = QPushButton("×")
        del_btn.setFixedSize(24, 24)
        del_btn.setStyleSheet("""
            QPushButton { color: #6e6e6e; background: transparent; font-size: 18px; border: none; border-radius: 12px; }
            QPushButton:hover { background: rgba(239, 83, 80, 0.2); color: #ef5350; }
        """)
        del_btn.clicked.connect(lambda: self._delete_event(event['id']))
        layout.addWidget(del_btn)
        
        # Insert before stretch
        self.timeline_layout.insertWidget(self.timeline_layout.count()-1, card)

    def _delete_event(self, event_id):
        calendar_manager.delete_event(event_id)
        self.refresh_events()
        
    def _show_add_event_dialog(self):
        """Show dialog to create a new event."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Event")
        dialog.setStyleSheet("background-color: #2b2d31; color: white;")
        layout = QVBoxLayout(dialog)
        
        # Title
        layout.addWidget(QLabel("Title:"))
        title_edit = QLineEdit()
        title_edit.setStyleSheet("background: #1a1c1e; border: 1px solid #3d3d3d; padding: 5px; color: white;")
        layout.addWidget(title_edit)
        
        # Time
        layout.addWidget(QLabel("Time:"))
        time_edit = QDateTimeEdit(QDateTime.currentDateTime())
        time_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        time_edit.setCalendarPopup(True)
        time_edit.setStyleSheet("background: #1a1c1e; border: 1px solid #3d3d3d; padding: 5px; color: white;")
        layout.addWidget(time_edit)
        
        # Category
        layout.addWidget(QLabel("Category:"))
        cat_edit = QComboBox()
        cat_edit.addItems(["WORK", "PERSONAL", "OTHER"])
        cat_edit.setStyleSheet("background: #1a1c1e; border: 1px solid #3d3d3d; padding: 5px; color: white;")
        layout.addWidget(cat_edit)
        
        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet("background: #4F8EF7; color: white; padding: 8px; border-radius: 4px;")
        save_btn.clicked.connect(dialog.accept)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("background: transparent; color: white; padding: 8px;")
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)
        
        if dialog.exec():
            title = title_edit.text()
            if title:
                dt = time_edit.dateTime()
                start = dt.toString("yyyy-MM-dd HH:mm:ss")
                end = dt.addSecs(3600).toString("yyyy-MM-dd HH:mm:ss") # Default 1h
                cat = cat_edit.currentText()
                
                calendar_manager.add_event(title, start, end, cat)
                self.refresh_events()
from datetime import datetime
