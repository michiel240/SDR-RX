"""Airspy C-ABI tests use fake libairspy; no physical SDR required."""
import ctypes as C
import time
import numpy as np
import pytest

from sdr_studio.airspy_native import AirspyNativeSource, Transfer, enumerate_airspy, AirspyError


class Function:
    def __init__(self, func):
        self.func = func
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.func(*args)


class FakeAirspy:
    def __init__(self, with_device=True):
        self.calls = []
        self.callback = None
        self.closed = False
        self.started = False
        self.with_device = with_device
        self.airspy_open = Function(self.open)
        self.airspy_open_sn = Function(self.open_sn)
        self.airspy_list_devices = Function(self.list_devices)
        self.airspy_close = Function(self.close)
        self.airspy_get_samplerates = Function(self.get_samplerates)
        self.airspy_set_samplerate = Function(self.set_rate)
        self.airspy_set_freq = Function(self.set_freq)
        self.airspy_set_sample_type = Function(lambda dev, kind: self.calls.append(('type', kind)) or 0)
        self.airspy_start_rx = Function(self.start)
        self.airspy_stop_rx = Function(self.stop)
        self.airspy_is_streaming = Function(lambda dev: 1 if self.started else 0)
        self.airspy_set_lna_agc = Function(lambda dev, on: self.calls.append(('lna', on)) or 0)
        self.airspy_set_mixer_agc = Function(lambda dev, on: self.calls.append(('mix', on)) or 0)
        self.airspy_set_linearity_gain = Function(lambda dev, value: self.calls.append(('gain', value)) or 0)

    def open(self, pointer):
        self.calls.append(('open',))
        C.cast(pointer, C.POINTER(C.c_void_p))[0] = 0x1234
        return 0

    def open_sn(self, pointer, serial):
        self.calls.append(('open_sn', serial.value))
        return self.open(pointer)

    def list_devices(self, ptr, length):
        if not self.with_device:
            return 0
        if length == 0:
            return 1
        ptr[0] = 0xCAFEBABE
        return 1

    def get_samplerates(self, dev, ptr, length):
        target = C.cast(ptr, C.POINTER(C.c_uint32))
        if length == 0:
            target[0] = 2
        else:
            target[0], target[1] = 2_500_000, 10_000_000
        return 0

    def set_rate(self, dev, rate):
        self.calls.append(('rate', rate))
        return 0

    def set_freq(self, dev, freq):
        self.calls.append(('freq', freq))
        return 0

    def start(self, dev, callback, user_context):
        self.callback = callback
        self.started = True
        return 0

    def stop(self, dev):
        self.started = False
        self.calls.append(('stop',))
        return 0

    def close(self, dev):
        self.closed = True
        self.calls.append(('close',))
        return 0

    def inject_samples(self, iq):
        # Library reuses the C buffer as soon as the callback returns.
        arr = np.asarray(iq, np.complex64)
        raw = (C.c_float * (2 * len(arr)))(*arr.view('float32'))
        transfer = Transfer(C.c_void_p(0x1234), None, C.cast(raw, C.c_void_p), len(arr), 4, 0)
        assert self.callback(C.pointer(transfer)) == 0
        for j in range(len(raw)):
            raw[j] = 0


def test_airspy_native_stream_callbacks_and_device_selection():
    fake = FakeAirspy()
    src = AirspyNativeSource(100_000_000, 2_500_000, 11, serial=0xCAFEBABE, dll=fake)
    assert ('open_sn', 0xCAFEBABE) in fake.calls
    assert src.sample_rate == 2_500_000
    assert ('rate', 2_500_000) in fake.calls
    assert ('gain', 11) in fake.calls
    fake.inject_samples(np.array([0.3 + 0.4j, 0.1 - 0.2j], np.complex64))
    result = src.read(2)
    assert result.dtype == np.complex64
    assert np.allclose(result, np.array([0.3 + 0.4j, 0.1 - 0.2j]))
    assert src.dropped == (4, 0)
    src.set_gain(None)
    assert ('lna', 1) in fake.calls
    assert ('mix', 1) in fake.calls
    src.tune(145_000_000)
    assert ('freq', 145_000_000) in fake.calls
    with pytest.raises(ValueError):
        src.tune(2_000_000)
    src.close()
    assert fake.closed and not fake.started
    assert fake.calls.index(('stop',)) < fake.calls.index(('close',))


def test_airspy_queue_is_bounded_and_reports_overruns():
    fake = FakeAirspy()
    src = AirspyNativeSource(100_000_000, 10_000_000, None, dll=fake)
    for i in range(20):
        fake.inject_samples(np.array([0.25 + i * 1j], np.complex64))
    assert src.dropped[1] >= 8
    assert src.read(32)[0].imag >= 8
    src.close()


def test_airspy_enumeration(monkeypatch):
    fake = FakeAirspy()
    from sdr_studio import airspy_native
    monkeypatch.setattr(airspy_native, 'load_library', lambda: fake)
    serials, message = enumerate_airspy()
    assert serials == [0xCAFEBABE]
    assert '1 Airspy' in message


def test_airspy_error_closes_device_even_if_configuration_fails():
    fake = FakeAirspy()
    fake.airspy_set_samplerate = Function(lambda dev, rate: -2)
    with pytest.raises(AirspyError, match='Sample-rate'):
        AirspyNativeSource(100_000_000, 2_500_000, None, dll=fake)
    assert fake.closed
