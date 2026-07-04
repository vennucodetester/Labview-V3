"""Shared visual constants for the diagram canvas."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPen, QBrush


FONT_FAMILY = "Segoe UI"
COMPONENT_FILL = "#F7FAFC"
COMPONENT_STROKE = "#000000"
COMPONENT_STROKE_WIDTH = 2
COMPONENT_TEXT = "#111111"
SECTION_STROKE = "#AAAAAA"
SECTION_TEXT = "#888888"
VALUE_CHIP_FILL = QColor(255, 255, 255, 150)
VALUE_CHIP_STROKE = QColor(31, 59, 92, 60)

DOT_RADIUS = 6
DOT_DIAMETER = DOT_RADIUS * 2
ROW_HEIGHT = 26
CARD_PADDING = 12
CARD_GUTTER = 18
SECTION_PADDING = 20
INSTRUMENT_CARD_ORDER = [
    "Ambient & Room",
    "Case Electrical",
    "Compressor Electrical",
    "System & Flags",
    "Refrigerant Misc",
    "Other Instruments",
]


def font(size: float, bold: bool = False) -> QFont:
    weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
    qfont = QFont(FONT_FAMILY, int(size), weight)
    qfont.setPointSizeF(float(size))
    return qfont


def component_brush() -> QBrush:
    return QBrush(QColor(COMPONENT_FILL))


def component_pen() -> QPen:
    return QPen(QColor(COMPONENT_STROKE), COMPONENT_STROKE_WIDTH)


def section_pen() -> QPen:
    pen = QPen(QColor(SECTION_STROKE), 2)
    pen.setStyle(Qt.PenStyle.DashLine)
    return pen
