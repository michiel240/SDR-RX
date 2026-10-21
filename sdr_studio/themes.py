"""Qt styles and pyqtgraph colors for SDR Studio RX's two switchable themes.

Pure Python; importing this module never loads USB drivers or Qt.
"""
PALETTES = {
    'dark': {
        'bg': '#091522', 'panel': '#142436', 'card': '#102033',
        'input': '#0B1B2C', 'border': '#2B4963', 'text': '#E4F0FB',
        'muted': '#A3BDD0', 'accent': '#63DFDD', 'accent_dark': '#1A7187',
        'button': '#223B53', 'hover': '#305570', 'selected': '#125D77',
        'positive': '#146B56', 'negative': '#753445', 'plot_bg': '#06111D',
        'plot_fg': '#AAC9D8', 'spectrum': '#69F0E6', 'marker': '#E9A860',
        'waterfall': ('#070E26','#073465','#146FB1','#12BEB4','#F5D548','#FFF5E8'),
    },
    'light': {
        'bg': '#EFF4F9', 'panel': '#FFFFFF', 'card': '#F9FBFD',
        'input': '#FFFFFF', 'border': '#C7D6E4', 'text': '#1B3146',
        'muted': '#536C80', 'accent': '#067A96', 'accent_dark': '#0D7F9F',
        'button': '#E3EDF5', 'hover': '#D1E5F0', 'selected': '#D5EBF6',
        'positive': '#18725F', 'negative': '#A34659', 'plot_bg': '#FFFFFF',
        'plot_fg': '#49657B', 'spectrum': '#077C9A', 'marker': '#B65E10',
        'waterfall': ('#F9FCFF','#C7E6F2','#72B8D8','#2085B6','#E9BD4E','#C95B30'),
    },
}


def colors(theme):
    if theme not in PALETTES:
        raise ValueError('Thema moet dark of light zijn')
    return PALETTES[theme]


def build_stylesheet(theme):
    c = colors(theme)
    return '''
QMainWindow, QWidget#appRoot { background: %(bg)s; color: %(text)s; }
QWidget { color: %(text)s; font: 10pt 'Segoe UI'; }
QLabel { background: transparent; }
QFrame#header, QFrame#dashboard { background: %(panel)s; border:1px solid %(border)s; border-radius:9px; }
QFrame#metricCard { background: %(card)s; border:1px solid %(border)s; border-radius:7px; }
QLabel#frequency { font:bold 29pt 'Consolas'; color:%(accent)s; }
QLineEdit#frequencyInput {
 font:bold 19pt 'Consolas'; color:%(accent)s;
 background:%(input)s; border:2px solid %(accent_dark)s;
 border-radius:7px; padding:4px 8px;
 selection-background-color:%(selected)s; selection-color:%(text)s;
}
QLineEdit#frequencyInput:focus { border:2px solid %(accent)s; }
QComboBox#stepSelector { font:bold 10pt 'Segoe UI'; }
QPushButton#tuneButton { font:bold 16pt 'Segoe UI'; padding:0px; border:1px solid %(accent_dark)s; }
QLabel#cardTitle { color:%(muted)s; font: bold 9pt 'Segoe UI'; }
QLabel#status { color:%(muted)s; font-size:9pt; }
QLabel#meterValue { font:bold 13pt 'Consolas'; color:%(text)s; }
QTabWidget::pane { border:1px solid %(border)s; background:%(panel)s; border-radius:6px; }
QTabBar::tab { background:%(button)s; color:%(muted)s; border:1px solid %(border)s; border-bottom:0; border-radius:5px; padding:8px 8px; margin-right:2px; }
QTabBar::tab:selected { background:%(selected)s; color:%(text)s; font-weight:600; }
QTabBar::tab:hover { background:%(hover)s; }
QSplitter::handle { background:%(border)s; }
QGroupBox { background:%(panel)s; border:1px solid %(border)s; border-radius:7px; margin-top:12px; padding:10px 7px 6px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:10px; color:%(accent)s; padding:0 5px; }
QPushButton { background:%(button)s; color:%(text)s; border:1px solid %(border)s; border-radius:5px; padding:6px 9px; }
QPushButton:hover { background:%(hover)s; }
QPushButton:pressed { background:%(selected)s; }
QPushButton:disabled { color:%(muted)s; }
QPushButton#start { background:%(positive)s; color:white; border-color:%(positive)s; font-weight:700; }
QPushButton#stop { background:%(negative)s; color:white; border-color:%(negative)s; }
QPushButton#themeButton { border-color:%(accent_dark)s; font-weight:600; }
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QListWidget, QPlainTextEdit {
 background:%(input)s; color:%(text)s; border:1px solid %(border)s; border-radius:5px; padding:5px;
 selection-background-color:%(selected)s; selection-color:%(text)s;
}
QComboBox QAbstractItemView { background:%(panel)s; color:%(text)s; selection-background-color:%(selected)s; }
QScrollArea, QScrollArea > QWidget > QWidget { background:%(panel)s; border:0; }
QSlider::groove:horizontal { height:5px; background:%(border)s; border-radius:2px; }
QSlider::handle:horizontal { width:13px; background:%(accent)s; margin:-6px 0; border-radius:6px; }
QProgressBar#signalBar { border:1px solid %(border)s; border-radius:4px; height:9px; background:%(input)s; }
QProgressBar#signalBar::chunk { background:%(accent)s; border-radius:3px; }
QScrollBar:vertical { background:%(panel)s; width:12px; }
QScrollBar::handle:vertical { background:%(border)s; border-radius:5px; min-height:30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
''' % c
