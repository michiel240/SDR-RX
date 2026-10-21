"""Regression checks for user-tunable frequency steps (pure + UI structure)."""
import ast
from fractions import Fraction
from pathlib import Path
import pytest

from sdr_studio.tuning import (
    TUNING_STEPS, DEFAULT_STEP, tuned_frequency_hz, tuning_step_hz
)


@pytest.mark.parametrize('label,hz', [
    ('100 Hz', 100), ('500 Hz', 500), ('1 kHz', 1_000),
    ('2.5 kHz', 2_500), ('5 kHz', 5_000),
    ('6.25 kHz', 6_250), ('10 kHz', 10_000),
    ('12.5 kHz', 12_500), ('25 kHz', 25_000),
    ('100 kHz', 100_000),
])
def test_exact_integer_frequency_step(label, hz):
    start = 145_500_000
    assert tuned_frequency_hz(start, label, 1) == start + hz
    assert tuned_frequency_hz(start, label, -2) == start - (2 * hz)
    assert tuned_frequency_hz(start, label, 1_000) == start + (1_000 * hz)


def test_833_khz_has_no_rounding_drift():
    assert tuning_step_hz('8.33 kHz') == Fraction(25_000, 3)
    anchor = 88_550_000
    assert [tuned_frequency_hz(anchor, '8.33 kHz', n) for n in range(4)] == [
        anchor, anchor + 8_333, anchor + 16_667, anchor + 25_000]
    assert tuned_frequency_hz(anchor, '8.33 kHz', 3_000) == anchor + 25_000_000
    assert tuned_frequency_hz(anchor, '8.33 kHz', -3) == anchor - 25_000
    assert tuned_frequency_hz(anchor, '8.33 kHz', 0) == anchor


def test_steps_have_unique_labels_and_default_present():
    labels = [s.label for s in TUNING_STEPS]
    assert len(labels) == 11
    assert len(labels) == len(set(labels))
    assert DEFAULT_STEP in labels
    with pytest.raises(KeyError):
        tuning_step_hz('9 kHz')


def test_big_frequency_control_and_step_selector_adjacent():
    source = (Path(__file__).resolve().parents[1] / 'sdr_studio' / 'app.py').read_text('utf-8')
    tree = ast.parse(source)
    window = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Window')
    funcs = {m.name: m for m in window.body if isinstance(m, ast.FunctionDef)}
    for name in ('step_changed', 'tune_by_steps', 'frequency_changed', 'refresh_vfo_info'):
        assert name in funcs
    ui = ast.get_source_segment(source, funcs['build_ui'])
    assert 'self.freq = FrequencySpinBox()' in ui
    assert "self.freq.setObjectName('frequencyInput')" in ui
    assert 'self.freq.setMinimumSize(219, 45)' in ui
    assert 'self.freq.valueChanged.connect(self.frequency_changed)' in ui
    assert ui.index('hl.addWidget(self.freq)') < ui.index('hl.addWidget(self.step_combo)')
    assert ui.index('hl.addWidget(self.step_combo)') < ui.index('hl.addWidget(self.tune_down_btn)')
    assert ui.index('hl.addWidget(self.tune_down_btn)') < ui.index('hl.addWidget(self.tune_up_btn)')
    assert "self.settings.value('frequency_step', DEFAULT_STEP)" in ui
    assert 'self.freq.stepRequested.connect(self.tune_by_steps)' in ui
    tune = ast.get_source_segment(source, funcs['tune_by_steps'])
    assert 'self.freq.interpretText()' in tune
    assert 'self.freq.setValue(target_hz / 1_000_000)' in tune
    assert 'self._internal_tune = True' in tune
    assert "self.settings.setValue('frequency_step', name)" in ast.get_source_segment(source, funcs['step_changed'])


def test_frequency_spinbox_keeps_direct_typing_and_keyboard_tuning():
    source = (Path(__file__).resolve().parents[1] / 'sdr_studio' / 'app.py').read_text('utf-8')
    tree = ast.parse(source)
    knob = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FrequencySpinBox')
    methods = {m.name: m for m in knob.body if isinstance(m, ast.FunctionDef)}
    assert {'stepBy', 'keyPressEvent'} <= methods.keys()
    assert 'self.stepRequested.emit(int(steps))' in ast.get_source_segment(source, methods['stepBy'])
    keys = ast.get_source_segment(source, methods['keyPressEvent'])
    assert 'Key_Right' in keys and 'Key_Left' in keys
    assert 'super().keyPressEvent(event)' in keys


def test_tuning_theme_is_styled_in_both_modes():
    from sdr_studio.themes import build_stylesheet
    for mode in ('light', 'dark'):
        css = build_stylesheet(mode)
        for selector in ('QLineEdit#frequencyInput', 'QComboBox#stepSelector', 'QPushButton#tuneButton'):
            assert selector in css
