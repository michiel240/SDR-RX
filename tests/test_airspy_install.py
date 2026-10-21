from pathlib import Path
import zipfile
import pytest
from sdr_studio.airspy_install import import_vendor_dlls, pe_architecture


def fake_dll(machine):
    data=bytearray(256)
    data[:2]=b'MZ'
    data[0x3c:0x40]=(128).to_bytes(4,'little')
    data[128:132]=b'PE\x00\x00'
    data[132:134]=machine.to_bytes(2,'little')
    return bytes(data)


def test_pe_architecture():
    assert pe_architecture(fake_dll(0x8664))==0x8664
    assert pe_architecture(fake_dll(0x14c))==0x14c
    assert pe_architecture(b'invalid') is None


def test_only_x64_dlls_copied(tmp_path):
    archive=tmp_path/'airspy.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('release/x64/libairspy.dll',fake_dll(0x8664))
        z.writestr('release/x64/libusb-1.0.dll',fake_dll(0x8664))
        z.writestr('release/x86/old.dll',fake_dll(0x14c))
        z.writestr('../../escape.txt','evil')
    result=import_vendor_dlls(archive,tmp_path/'drivers')
    assert result == ['libairspy.dll','libusb-1.0.dll']
    assert (tmp_path/'drivers/libairspy.dll').is_file()
    assert not (tmp_path/'escape.txt').exists()


def test_no_airspy_rejects_zip(tmp_path):
    archive=tmp_path/'wrong.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('release/x64/libusb-1.0.dll',fake_dll(0x8664))
    with pytest.raises(ValueError,match='Geen x64 airspy.dll of libairspy.dll'):
        import_vendor_dlls(archive,tmp_path/'drivers')


def test_different_existing_dll_is_preserved(tmp_path):
    archive=tmp_path/'airspy.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('libairspy.dll',fake_dll(0x8664))
    target=tmp_path/'drivers'
    target.mkdir()
    (target/'libairspy.dll').write_bytes(b'existing')
    with pytest.raises(ValueError,match='bestaat al'):
        import_vendor_dlls(archive,target)
    assert (target/'libairspy.dll').read_bytes()==b'existing'
