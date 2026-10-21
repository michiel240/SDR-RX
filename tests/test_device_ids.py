"""Regression tests for the Airspy R2 large-serial PySide6 overflow."""
import ast
from pathlib import Path
import pytest
from sdr_studio.device_ids import encode_device_id, decode_device_id


@pytest.mark.parametrize('original', [None, 0, 1, 0x7FFFFFFFFFFFFFFF,
                                       0x8000000000000000, 12051747811854987923,
                                       0xFFFFFFFFFFFFFFFF])
def test_64bit_device_id_roundtrip(original):
    qt_value = encode_device_id(original)
    assert qt_value is None or isinstance(qt_value, str)
    assert decode_device_id(qt_value) == original


def test_prevent_bad_device_identifiers():
    for value in [-1, 1 << 64, True]:
        with pytest.raises(ValueError):
            encode_device_id(value)
    for value in ['-1', '12.0', 'abc', '', '１２３', True, 1 << 64]:
        with pytest.raises((ValueError, TypeError)):
            decode_device_id(value)


def test_ui_always_serializes_qt_combobox_identifier():
    # Test the actual source of the previous crash: do not pass a raw Python
    # int to QComboBox.addItem()'s userData field. Importing Qt on a headless
    # build runner is optional; AST still catches a regression in app.py.
    p = Path(__file__).resolve().parents[1] / 'sdr_studio' / 'app.py'
    root = ast.parse(p.read_text(encoding='utf-8'))
    calls = [n for n in ast.walk(root) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)]
    relevant = [n for n in calls if n.func.attr == 'addItem'
                and isinstance(n.func.value, ast.Attribute)
                and n.func.value.attr == 'device_list'
                and len(n.args) == 2]
    assert any(isinstance(n.args[1], ast.Call)
               and isinstance(n.args[1].func, ast.Name)
               and n.args[1].func.id == 'encode_device_id' for n in relevant)
    assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == 'decode_device_id' for n in ast.walk(root))
