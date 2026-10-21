"""Regression for empty frequency entry while receiver keeps tuning."""
import ast
from pathlib import Path
import pytest

from sdr_studio.tuning import format_frequency_mhz, parse_frequency_mhz


@pytest.mark.parametrize('hz, expected', [
    (145_500_000, '145.500000'),
    (146_423_913, '146.423913'),
    (88_550_000, '88.550000'),
    (1_090_000_000, '1090.000000'),
    (24_000_001, '24.000001'),
])
def test_frequency_format(hz, expected):
    assert format_frequency_mhz(hz) == expected


@pytest.mark.parametrize('typed, expected', [
    ('146.423913', 146_423_913),
    ('146,423913', 146_423_913),
    ('88.55', 88_550_000),
    (' 145.5 ', 145_500_000),
    ('1090', 1_090_000_000),
])
def test_frequency_parse_valid(typed, expected):
    assert parse_frequency_mhz(typed, 24_000_000, 1_750_000_000) == expected


@pytest.mark.parametrize('typed', [
    '', '  ', 'abc', '145.1234567', '12 MHz', '-2', '9999', '145..5',
])
def test_frequency_parse_invalid(typed):
    assert parse_frequency_mhz(typed, 24_000_000, 1_750_000_000) is None


def test_frequency_control_writes_visible_text_on_every_update():
    source = (Path(__file__).resolve().parents[1] / 'sdr_studio' / 'app.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FrequencySpinBox')
    assert isinstance(cls.bases[0], ast.Attribute) and cls.bases[0].attr == 'QLineEdit'
    funcs = {m.name: m for m in cls.body if isinstance(m, ast.FunctionDef)}
    update = ast.get_source_segment(source, funcs['setValue'])
    assert 'self.setText(format_frequency_mhz(hz))' in update
    assert update.index('self.setText(') < update.index('if changed:')
    assert 'self.valueChanged.emit' in update
    assert 'self.interpretText()' in ast.get_source_segment(source, funcs['focusOutEvent'])
    for key in ('Key_Up', 'Key_Down', 'Key_Return'):
        assert key in ast.get_source_segment(source, funcs['keyPressEvent'])
