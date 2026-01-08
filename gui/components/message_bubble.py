"""
MessageBubble component - Styled chat message bubble for PySide6.
"""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class MessageBubble(QFrame):
    """A styled message bubble for User or AI."""
    
    def __init__(self, role: str, text: str = "", is_thinking: bool = False, parent=None):
        super().__init__(parent)
        self.role = role
        self.is_thinking = is_thinking
        self._text = text
        
        self.setObjectName("messageBubble")
        self._setup_ui()
        self._apply_style()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(0)
        
        # Use QLabel for all text - simpler and more reliable sizing
        self.content_label = QLabel(self._text)
        self.content_label.setWordWrap(True)
        self.content_label.setTextFormat(Qt.PlainText)
        self.content_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        
        if self.is_thinking:
            self.content_label.setFont(QFont("Consolas", 11))
            self.content_label.setStyleSheet("color: #9e9e9e; font-style: italic;")
        else:
            self.content_label.setFont(QFont("Segoe UI", 11))
            self.content_label.setStyleSheet("color: #e8eaed;")
        
        self.content_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout.addWidget(self.content_label)
    
    def _apply_style(self):
        is_user = self.role == "user"
        
        if self.is_thinking:
            bg_color = "#2a2a2a"
            border_radius = "12px"
        elif is_user:
            bg_color = "#005c4b"
            border_radius = "18px 18px 4px 18px"
        else:
            bg_color = "#363636"
            border_radius = "18px 18px 18px 4px"
        
        self.setStyleSheet(f"""
            QFrame#messageBubble {{
                background-color: {bg_color};
                border-radius: {border_radius};
            }}
        """)
        
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.setMinimumWidth(60)
        self.setMaximumWidth(550)
    
    def set_text(self, text: str):
        """Update the message content (for streaming)."""
        self._text = text
        self.content_label.setText(text)
    
    def append_text(self, text: str):
        """Append text to the message (for streaming)."""
        self._text += text
        self.set_text(self._text)
    
    @property
    def alignment(self):
        """Return the alignment for this bubble."""
        return Qt.AlignRight if self.role == "user" else Qt.AlignLeft
