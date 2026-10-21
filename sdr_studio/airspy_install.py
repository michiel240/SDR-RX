"""Import only x64 DLLs from a user-supplied official Airspy Host Tools ZIP.

No internet downloads, elevation, USB driver changes or arbitrary file extraction.
Only writes in the SDRStudio RX drivers directory.
"""
from __future__ import annotations
import ctypes
import os
from pathlib import Path
import struct
import sys
import zipfile


def pe_architecture(binary: bytes) -> int | None:
    """Read the PE COFF Machine word, not an archive directory name."""
    if len(binary) < 68 or binary[:2] != b'MZ':
        return None
    pe_offset = int.from_bytes(binary[0x3c:0x40], 'little')
    if pe_offset > len(binary)-6 or binary[pe_offset:pe_offset+4] != b'PE\x00\x00':
        return None
    return int.from_bytes(binary[pe_offset+4:pe_offset+6], 'little')


def import_vendor_dlls(archive: str | Path, target_dir: str | Path) -> list[str]:
    """Copy x64 DLLs only; reject collisions and non-Airspy archives."""
    archive, dest = Path(archive), Path(target_dir)
    if not zipfile.is_zipfile(archive):
        raise ValueError('Dit bestand is geen geldig ZIP-archief.')
    copies = {}
    with zipfile.ZipFile(archive) as z:
        for record in z.infolist():
            if record.is_dir() or not record.filename.lower().endswith('.dll'):
                continue
            if record.file_size > 35 * 1024 * 1024:
                raise ValueError('Onverwacht grote DLL in ZIP, import gestopt.')
            name = Path(record.filename.replace('\\', '/')).name
            if name.lower() in copies:
                # Accept same DLL from multiple folders only if bytes match.
                candidate = z.read(record)
                if pe_architecture(candidate) == 0x8664 and copies[name.lower()] != candidate:
                    raise ValueError(f'Meerdere verschillende x64-versies van {name} gevonden.')
                continue
            data = z.read(record)
            if pe_architecture(data) != 0x8664:
                continue
            copies[name.lower()] = data
    if not ({'libairspy.dll', 'airspy.dll'} & copies.keys()):
        raise ValueError('Geen x64 airspy.dll of libairspy.dll gevonden. Download de officiële Windows x64 Host Tools ZIP.')
    dest.mkdir(parents=True, exist_ok=True)
    # Preflight all existing files before writing anything.
    for name, data in copies.items():
        path = dest/name
        if path.exists() and path.read_bytes() != data:
            raise ValueError(f'{name} bestaat al met een andere inhoud. Maak eerst een reservekopie en verplaats het bestand.')
    output = []
    for name, data in copies.items():
        path = dest/name
        if not path.exists():
            path.write_bytes(data)
        output.append(name)
    return sorted(output)


def select_archive():
    if len(sys.argv) > 1:
        return sys.argv[1].strip('"')
    try:
        from tkinter import Tk, filedialog
        tk = Tk()
        tk.withdraw()
        tk.attributes('-topmost', True)
        selected = filedialog.askopenfilename(
            title='Kies de OFFICIËLE Airspy Host Tools x64 ZIP',
            filetypes=[('ZIP archieven', '*.zip')])
        tk.destroy()
        return selected
    except Exception:
        return input('Volledig pad naar de officiële Airspy ZIP: ').strip().strip('"')


def main():
    print('SDRStudio RX — Import officiële Airspy x64 DLLs')
    print('Download op: https://github.com/airspy/airspyone_host/releases/tag/v1.0.10')
    print('Gebruik uitsluitend een archief van het officiële Airspy-project.')
    selected = select_archive()
    if not selected:
        print('Geen bestand geselecteerd.')
        return 1
    drivers = Path(__file__).resolve().parent.parent/'drivers'
    try:
        files = import_vendor_dlls(selected, drivers)
        print('GEÏMPORTEERD naar', drivers)
        for filename in files:
            print('  x64:', filename)
        if os.name == 'nt':
            cookie = os.add_dll_directory(str(drivers))
            try:
                library_name = 'libairspy.dll' if (drivers/'libairspy.dll').exists() else 'airspy.dll'
                ctypes.CDLL(str(drivers/library_name))
                print('PASS: Windows kan de Airspy-library laden.')
            except OSError as error:
                print('LET OP: Library nog niet te laden, ontbrekende afhankelijkheid of verkeerde versie:', error)
                return 2
            finally:
                cookie.close()
        print('Start nu SDRStudio RX en druk op Zoek USB bij Airspy R2.')
        return 0
    except Exception as error:
        print('FOUT:', error)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
