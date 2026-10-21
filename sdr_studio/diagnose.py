"""Troubleshooting without GUI; does not open a capture stream."""
import importlib
import platform
import sys
import shutil

from .hardware import discover


def main():
    print('SDRStudio RX v0.2.4 / diagnose')
    print('Python:', sys.version.split()[0], '|', sys.executable)
    print('Platform:', platform.platform(), '| bits:', platform.architecture()[0])
    for module in ['numpy', 'scipy', 'PySide6', 'pyqtgraph', 'sounddevice', 'rtlsdr']:
        try:
            importlib.import_module(module)
            print(f'{module:14} OK')
        except Exception as exc:
            print(f'{module:14} NIET BESCHIKBAAR ({type(exc).__name__}: {exc})')
    for kind in ['RTL-SDR', 'Airspy R2']:
        print(f'\n{kind}:')
        devices, message = discover(kind)
        print(' ', message)
        for dev in devices:
            print(' ', dev.label)
    for app in ['rtl_433', 'AIS-catcher', 'dump1090', 'dsd-fme', 'direwolf']:
        print(f'{app:14}', shutil.which(app) or 'Niet op PATH (optioneel)')


if __name__ == '__main__':
    main()
