import sys
import types
import numpy as np
from sdr_studio.devices import RtlSource, AirspySource, make_source
from sdr_studio.hardware import discover


class DummyRtl:
    def __init__(self, device_index=0):
        self.device_index = device_index
        self.sample_rate = None
        self.center_freq = None
        self.gain = None
        self.closed = False

    # Deliberately DO NOT define get_device_count/get_device_name. They are
    # librtlsdr functions, not methods on RtlSdr in current pyrtlsdr.

    def read_samples(self, n):
        return np.ones(n, np.complex64)

    def close(self):
        self.closed = True


def test_rtl_backend_api_and_enumeration(monkeypatch):
    monkeypatch.setitem(sys.modules, 'rtlsdr', types.SimpleNamespace(RtlSdr=DummyRtl))
    fake_lib = types.SimpleNamespace(
        rtlsdr_get_device_count=lambda: 2,
        rtlsdr_get_device_name=lambda i: f'Dummy RTL-{i}'.encode('utf-8'),
    )
    monkeypatch.setitem(sys.modules, 'rtlsdr.librtlsdr', types.SimpleNamespace(librtlsdr=fake_lib))
    devices, message = discover('RTL-SDR')
    assert len(devices) == 2
    assert '2 RTL' in message
    assert devices[1].identifier == 1
    src = make_source('RTL-SDR', 100_000_000, 2_048_000, 20, 1)
    assert src.radio.device_index == 1
    assert src.radio.gain == 20
    assert src.read(1024).dtype == np.complex64
    src.tune(145_000_000)
    assert src.radio.center_freq == 145_000_000
    src.set_gain(None)
    assert src.radio.gain == 'auto'
    dev = src.radio
    src.close()
    assert dev.closed


def test_rtl_no_device_does_not_attempt_capture(monkeypatch):
    from sdr_studio import hardware_test
    fake_lib = types.SimpleNamespace(rtlsdr_get_device_count=lambda: 0)
    monkeypatch.setitem(sys.modules, 'rtlsdr.librtlsdr', types.SimpleNamespace(librtlsdr=fake_lib))
    monkeypatch.setattr(hardware_test, 'make_source', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('USB must not open')))
    import pytest
    with pytest.raises(RuntimeError, match='Geen RTL-SDR gedetecteerd'):
        hardware_test.capture_test('RTL-SDR', seconds=0.3)


def test_airspy_factory_is_defined_and_uses_serial(monkeypatch):
    from sdr_studio import devices
    received = {}
    def fake_airspy(*args, **kwargs):
        received['args'], received['kwargs'] = args, kwargs
        return 'fake_source'
    monkeypatch.setattr(devices, 'AirspyNativeSource', fake_airspy)
    output = devices.make_source('Airspy R2', 100_000_000, 2_500_000, None, 0xDEADBEEF)
    assert output == 'fake_source'
    assert received['args'] == (100_000_000, 2_500_000, None)
    assert received['kwargs'] == {'serial': 0xDEADBEEF}
