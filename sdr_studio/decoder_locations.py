"""Safe local path resolution for separately installed upstream decoders.

Keep executables and their sibling DLLs together in separate subfolders of
``decoders/bin``. This module never executes them or searches outside that tree.
"""
from __future__ import annotations
from pathlib import Path
import sys


def decoder_directory():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent / 'decoders' / 'bin'
    return Path(__file__).resolve().parent.parent / 'decoders' / 'bin'


def locate_decoder(name: str):
    if not name:
        return ''
    candidate = Path(name)
    if candidate.is_file():
        return str(candidate.resolve())
    # Do not interpret arbitrary absolute paths/relative traversals as filenames.
    if candidate.name != name or '..' in candidate.parts or candidate.is_absolute():
        return ''
    root = decoder_directory()
    if not root.is_dir():
        return ''
    wanted = name.casefold() if name.lower().endswith('.exe') else (name+'.exe').casefold()
    # Backwards compatibility with decoder binaries directly under decoders/bin.
    direct = root / wanted
    if direct.is_file():
        return str(direct.resolve())
    # Search one tool's directory; do not return unrelated executables.
    sub = root / Path(name).stem
    if sub.is_dir():
        for path in sub.rglob('*.exe'):
            if path.name.casefold() == wanted and len(path.relative_to(sub).parts) <= 6:
                return str(path.resolve())
    # Case-insensitive directory names on some portable copies.
    for folder in root.iterdir():
        if folder.is_dir() and folder.name.casefold() == Path(name).stem.casefold():
            for path in folder.rglob('*.exe'):
                if path.name.casefold() == wanted and len(path.relative_to(folder).parts) <= 6:
                    return str(path.resolve())
    return ''
