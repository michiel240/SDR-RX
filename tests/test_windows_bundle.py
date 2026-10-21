"""Offline tests for Windows package setup without executing downloaded binaries."""
from pathlib import Path
import io
import zipfile
import importlib.util
import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools' / 'setup_windows_bundle.py'
spec = importlib.util.spec_from_file_location('setup_windows_bundle', TOOLS)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def make_zip(path, content):
    with zipfile.ZipFile(path, 'w') as zip_file:
        for name, data in content.items():
            zip_file.writestr(name, data)


def test_decoder_manifest_pinned_urls_and_sha():
    assert len(module.DECODERS) == 5
    assert len({x['name'] for x in module.DECODERS}) == 5
    assert all(len(x['sha256']) == 64 and x['url'].startswith('https://github.com/') for x in module.DECODERS)


def test_safe_zip_extract(tmp_path):
    src = tmp_path/'good.zip'
    make_zip(src, {'dir/tool.exe': 'dummy', 'dir/license.txt': 'copyright'})
    module.safe_unzip(src, tmp_path/'out')
    assert (tmp_path/'out/dir/tool.exe').read_text() == 'dummy'


def test_safe_zip_blocks_path_traversal(tmp_path):
    src = tmp_path/'bad.zip'
    make_zip(src, {'../escape.exe': 'bad'})
    with pytest.raises(ValueError, match='Onveilig'):
        module.safe_unzip(src, tmp_path/'output')
    assert not (tmp_path/'escape.exe').exists()


def test_sha_file(tmp_path):
    p=tmp_path/'data';p.write_bytes(b'abc')
    assert module.sha256_file(p)=='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'


def test_locate_decoder_portable_subdir(tmp_path, monkeypatch):
    import sdr_studio.decoder_locations as locations
    root=tmp_path/'decoders/bin/rtl_433/release/x64';root.mkdir(parents=True)
    exe=root/'rtl_433.exe';exe.write_bytes(b'MZ')
    monkeypatch.setattr(locations,'decoder_directory',lambda:tmp_path/'decoders/bin')
    assert locations.locate_decoder('rtl_433')==str(exe.resolve())
    assert locations.locate_decoder('')==''
    assert locations.locate_decoder('../outside')==''


def test_pe_architecture(tmp_path):
    import struct
    p=tmp_path/'libairspy.dll';data=bytearray(96);data[:2]=b'MZ';struct.pack_into('<I',data,0x3c,80);data[80:84]=b'PE\0\0';struct.pack_into('<H',data,84,0x8664)
    p.write_bytes(data)
    assert module.pe_architecture(p)==0x8664
    p.write_bytes(b'not dll')
    assert module.pe_architecture(p) is None


def test_install_decoder_keeps_dlls_in_own_directory(tmp_path, monkeypatch):
    release=tmp_path/'release.zip'
    make_zip(release, {'win64/bin/testdecoder.exe':b'MZfake',
                       'win64/bin/special.dll':b'MZdependency',
                       'LICENSE.txt':b'upstream license'})
    import shutil
    def mock_download(url, output, expected_sha256):
        shutil.copy2(release, output)
        return module.sha256_file(output)
    monkeypatch.setattr(module, 'download', mock_download)
    output=tmp_path/'bin'
    tool={'name':'testdecoder','exe':'testdecoder.exe','version':'test','url':'https://github.com/test/project', 'sha256':'0'*64}
    located=module.install_decoder(tool,output,tmp_path)
    assert located is not None and located.is_file()
    assert located.parent.joinpath('special.dll').is_file()
    assert (output/'testdecoder'/'LICENSE.txt').is_file()


def test_install_airspy_official_airspy_dll_name_and_x64_dependencies(tmp_path, monkeypatch):
    """Airspy official x64 release uses airspy.dll, not libairspy.dll."""
    import struct
    import shutil

    def fake_pe(machine):
        data = bytearray(256)
        data[:2] = b'MZ'
        struct.pack_into('<I', data, 0x3c, 128)
        data[128:132] = b'PE\x00\x00'
        struct.pack_into('<H', data, 132, machine)
        return bytes(data)

    release = tmp_path/'airspy-official.zip'
    make_zip(release, {
        'hosttools/x32/airspy.dll': fake_pe(0x14c),
        'hosttools/x32/libusb-1.0.dll': fake_pe(0x14c),
        'hosttools/x64/airspy.dll': fake_pe(0x8664),
        'hosttools/x64/libusb-1.0.dll': fake_pe(0x8664),
        'hosttools/x64/pthreadVC2.dll': fake_pe(0x8664),
    })

    def mock_download(url, output, expected_sha256=None):
        shutil.copy2(release, output)
        return module.sha256_file(output)

    monkeypatch.setattr(module, 'download', mock_download)
    drivers = tmp_path/'drivers'
    assert module.install_airspy(drivers)
    assert module.pe_architecture(drivers/'airspy.dll') == 0x8664
    assert module.pe_architecture(drivers/'libusb-1.0.dll') == 0x8664
    assert module.pe_architecture(drivers/'pthreadVC2.dll') == 0x8664
    assert not (drivers/'libairspy.dll').exists()
    # Second run reuses the x64 library and does not redownload.
    monkeypatch.setattr(module, 'download', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('unexpected download')))
    assert module.install_airspy(drivers)


def test_install_airspy_rejects_only_32bit_dll(tmp_path, monkeypatch):
    import struct
    import shutil
    data = bytearray(256)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 128)
    data[128:132] = b'PE\x00\x00'
    struct.pack_into('<H', data, 132, 0x14c)
    release = tmp_path/'32bit-only.zip'
    make_zip(release, {'release/x32/airspy.dll': bytes(data)})
    monkeypatch.setattr(module, 'download', lambda url, out, sha=None: (shutil.copy2(release, out), module.sha256_file(out))[1])
    assert not module.install_airspy(tmp_path/'drivers')
    assert not (tmp_path/'drivers/airspy.dll').exists()
