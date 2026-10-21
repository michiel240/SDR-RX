"""Offline safeguards for size-optimized Windows packaging configuration."""
from __future__ import annotations
from pathlib import Path

from tools import build_windows_slim as build
from tools import rapport_grootte_windows as report


def test_slim_requirements_have_only_pyside_essentials():
    requirements = (build.ROOT / 'requirements-windows-slim.txt').read_text(encoding='utf-8')
    modules = [line.strip().lower() for line in requirements.splitlines()
               if line.strip() and not line.lstrip().startswith('#')]
    assert any(name.startswith('pyside6_essentials') for name in modules)
    assert not any(name.startswith('pyside6>') or name.startswith('pyside6=') for name in modules)
    assert any(name.startswith('scipy') for name in modules)
    assert any(name.startswith('pyrtlsdr') for name in modules)


def test_slim_keeps_required_native_libraries():
    command = build.build_command()
    for name in ('rtlsdr', 'pyrtlsdrlib', '_sounddevice_data'):
        assert ['--collect-all', name] == command[command.index(name)-1:command.index(name)+1]
    assert '--onedir' in command
    assert '--contents-directory' in command
    for must_keep in ('PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
                      'sounddevice', 'scipy.signal'):
        assert must_keep not in build.EXCLUDED_MODULES
    assert 'pytest' in build.EXCLUDED_MODULES
    assert 'pyqtgraph.opengl' in build.EXCLUDED_MODULES


def test_entry_includes_real_gui_and_audio_smoke_test():
    code = build.ENTRY_CONTENT
    assert "'--slim-selftest'" in code
    assert 'pg.PlotWidget()' in code
    assert 'import sounddevice' in code
    assert 'signal.sosfilt' in code
    assert 'SLIM_SELFTEST_OK' in code
    assert 'from sdr_studio.app import main' in code


def test_complete_decoder_tree_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(build, 'ROOT', tmp_path)
    vendor = tmp_path/'decoders'/'bin'/'dsd-neo'/'bin'
    vendor.mkdir(parents=True)
    (vendor/'dsd-neo.exe').write_bytes(b'dsd-placeholder')
    (vendor/'support.dll').write_bytes(b'support-placeholder')
    drivers = tmp_path/'drivers'
    drivers.mkdir()
    (drivers/'airspy.dll').write_bytes(b'airspy-placeholder')
    dest = tmp_path/'dist'/'SDR-Studio-RX-SLIM'
    build.copy_portable_parts(dest)
    assert (dest/'decoders/bin/dsd-neo/bin/dsd-neo.exe').read_bytes() == b'dsd-placeholder'
    assert (dest/'decoders/bin/dsd-neo/bin/support.dll').read_bytes() == b'support-placeholder'
    assert (dest/'drivers/airspy.dll').read_bytes() == b'airspy-placeholder'


def test_size_report_does_not_delete_files(tmp_path):
    target=tmp_path/'nested'
    target.mkdir()
    original=target/'keep.dll'
    original.write_bytes(b'x' * 2048)
    assert report.tree_size(tmp_path) == 2048
    assert report.describe('TEST', tmp_path)==2048
    assert original.read_bytes()==b'x' * 2048
