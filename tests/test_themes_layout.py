"""Low-level themes + AST regression without needing an active Qt display."""
import ast
from pathlib import Path
import pytest
from sdr_studio.themes import PALETTES, build_stylesheet, colors


@pytest.mark.parametrize('theme', ['dark', 'light'])
def test_themes_define_all_required_controls_and_charts(theme):
    color = colors(theme)
    assert color['plot_bg'] != color['plot_fg']
    assert color['spectrum'] != color['plot_bg']
    assert len(color['waterfall']) == 6
    css = build_stylesheet(theme)
    for selector in ['QFrame#header', 'QFrame#dashboard', 'QPushButton#themeButton',
                     'QProgressBar#signalBar', 'QTabWidget::pane', 'QLabel#frequency']:
        assert selector in css
    assert '%(' not in css


def test_light_and_dark_are_visually_distinct():
    assert colors('dark')['bg'] != colors('light')['bg']
    assert colors('dark')['plot_bg'] != colors('light')['plot_bg']
    assert colors('dark')['spectrum'] != colors('light')['spectrum']
    with pytest.raises(ValueError):
        colors('bright')


def test_theme_persists_and_updates_plots_without_restarting_receiver():
    source = (Path(__file__).resolve().parents[1] / 'sdr_studio' / 'app.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Window')
    funcs = {m.name: m for m in cls.body if isinstance(m, ast.FunctionDef)}
    assert {'apply_theme', 'toggle_theme', 'frequency_changed', 'start_receiver'} <= funcs.keys()
    init = ast.get_source_segment(source, funcs['__init__'])
    assert "self.settings.value('theme', 'dark')" in init
    styling = ast.get_source_segment(source, funcs['apply_theme'])
    for name in ('self.settings.setValue', 'self.update_waterfall_palette',
                 'self.curve.setPen', 'self.tune_marker.setPen', 'plot.setBackground'):
        assert name in styling
    assert 'self.worker.stop' not in styling
    ui = ast.get_source_segment(source, funcs['build_ui'])
    assert 'self.theme_button.clicked.connect(self.toggle_theme)' in ui
    assert "self.sidebar.addTab(scanner_tab, 'Scan')" in ui
    assert 'self.tune_marker' in ui and 'self.waterfall_marker' in ui
    assert "self.capture_btn.toggled.connect(self.toggle_recording)" in ui


def test_device_serial_workaround_still_present():
    s = (Path(__file__).resolve().parents[1] / 'sdr_studio' / 'app.py').read_text(encoding='utf-8')
    assert 'encode_device_id(radio.identifier)' in s
    assert 'decode_device_id(self.device_list.currentData())' in s
