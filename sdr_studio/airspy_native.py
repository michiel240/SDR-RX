"""Airspy R0/R2/Mini native receive-only driver via the official libairspy C API.

The library provides IQ32f blocks via a USB-thread callback. We COPY buffers
before returning from that callback: libairspy owns and reuses them. The receive
thread owns the USB handle, and uses a bounded queue so DSP overload cannot
consume unbounded RAM. No SoapySDR/Python Soapy bindings are necessary.

Requires a trusted, x64 build of airspy.dll (or libairspy.dll) and matching dependencies.
API: https://github.com/airspy/airspyone_host/blob/master/libairspy/src/airspy.h
"""
from __future__ import annotations

import ctypes as C
from dataclasses import dataclass
import os
from pathlib import Path
import queue
import sys
import time

import numpy as np


class AirspyError(RuntimeError):
    pass


class Transfer(C.Structure):
    _fields_ = [
        ('device', C.c_void_p), ('ctx', C.c_void_p), ('samples', C.c_void_p),
        ('sample_count', C.c_int), ('dropped_samples', C.c_uint64),
        ('sample_type', C.c_int),
    ]


ReceiveCallback = C.CFUNCTYPE(C.c_int, C.POINTER(Transfer))  # __cdecl on Windows


def library_candidates():
    """No automatic download or untrusted binary installation."""
    env = os.environ.get('SDRSTUDIO_AIRSPY_DLL')
    if env:
        yield env
    app_root = Path(__file__).resolve().parent.parent
    for folder in (app_root / 'drivers', app_root):
        for dll in ('libairspy.dll', 'airspy.dll'):
            path = folder / dll
            if path.is_file():
                yield str(path)
    for dll in ('libairspy.dll', 'airspy.dll'):
        yield dll  # OS DLL search paths; must match 64-bit Python


def load_library():
    errors = []
    seen = set()
    for path in library_candidates():
        if path in seen:
            continue
        seen.add(path)
        search_cookie = None
        try:
            # On Windows Python >=3.8 deliberately does not use PATH/current dir
            # when resolving dependencies of DLLs loaded by absolute path.
            # Register the folder so sibling libusb/pthread DLLs can be loaded.
            local = Path(path)
            if os.name == 'nt' and local.is_file() and hasattr(os, 'add_dll_directory'):
                search_cookie = os.add_dll_directory(str(local.resolve().parent))
            dll = C.CDLL(str(local.resolve()) if local.is_file() else path)
            _bind_api(dll)
            # The directory cookie must stay alive while libairspy is loaded.
            dll._sdrstudio_dll_directory = search_cookie
            return dll
        except (OSError, AttributeError) as exc:
            if search_cookie is not None:
                search_cookie.close()
            errors.append(f'{path}: {exc}')
    folder = Path(__file__).resolve().parent.parent / 'drivers'
    candidates_in_folder = [name for name in ('libairspy.dll', 'airspy.dll')
                            if (folder / name).is_file()]
    if not candidates_in_folder and not os.environ.get('SDRSTUDIO_AIRSPY_DLL'):
        raise AirspyError(
            f'Geen airspy.dll of libairspy.dll gevonden in {folder}. Download de officiële '
            'Windows x64 AirSpy Host Tools (v1.0.10) via '
            'https://github.com/airspy/airspyone_host/releases en kopieer '
            'airspy.dll (of libairspy.dll) met de bijbehorende x64 afhankelijkheden '
            '(zoals libusb-1.0.dll) uit hetzelfde pakket naar de drivers-map.')
    raise AirspyError(
        'Airspy DLL gevonden, maar Windows kan hem niet laden of de API ontbreekt. '
        'Controleer dat het de x64-versie is en dat bijbehorende DLLs uit hetzelfde '
        'Airspy Host Tools-pakket in dezelfde drivers-map staan. Details: ' +
        (' | '.join(errors[-2:]) if errors else 'onbekend'))


def _bind(dll, name, restype, argtypes):
    func = getattr(dll, name)
    func.restype, func.argtypes = restype, argtypes
    return func


def _bind_api(dll):
    P = C.c_void_p
    _bind(dll, 'airspy_open', C.c_int, [C.POINTER(P)])
    if hasattr(dll, 'airspy_open_sn'):
        _bind(dll, 'airspy_open_sn', C.c_int, [C.POINTER(P), C.c_uint64])
    _bind(dll, 'airspy_close', C.c_int, [P])
    _bind(dll, 'airspy_get_samplerates', C.c_int, [P, C.POINTER(C.c_uint32), C.c_uint32])
    _bind(dll, 'airspy_set_samplerate', C.c_int, [P, C.c_uint32])
    _bind(dll, 'airspy_set_freq', C.c_int, [P, C.c_uint32])
    _bind(dll, 'airspy_set_sample_type', C.c_int, [P, C.c_int])
    _bind(dll, 'airspy_start_rx', C.c_int, [P, ReceiveCallback, P])
    _bind(dll, 'airspy_stop_rx', C.c_int, [P])
    _bind(dll, 'airspy_is_streaming', C.c_int, [P])
    _bind(dll, 'airspy_set_lna_agc', C.c_int, [P, C.c_uint8])
    _bind(dll, 'airspy_set_mixer_agc', C.c_int, [P, C.c_uint8])
    _bind(dll, 'airspy_set_linearity_gain', C.c_int, [P, C.c_uint8])
    if hasattr(dll, 'airspy_list_devices'):
        _bind(dll, 'airspy_list_devices', C.c_int, [C.POINTER(C.c_uint64), C.c_int])
    if hasattr(dll, 'airspy_error_name'):
        _bind(dll, 'airspy_error_name', C.c_char_p, [C.c_int])


def check(dll, code, action):
    if code == 0:
        return
    description = str(code)
    if hasattr(dll, 'airspy_error_name'):
        try:
            value = dll.airspy_error_name(code)
            if value:
                description = value.decode('utf-8', errors='replace')
        except Exception:
            pass
    raise AirspyError(f'{action}: {description} (code {code})')


def enumerate_airspy():
    """Returns (serial identifiers, explanation). Doesn't claim USB device ownership."""
    dll = load_library()
    if not hasattr(dll, 'airspy_list_devices'):
        return [], 'Airspy-DLL gevonden, maar apparaatdetectie ontbreekt in deze oudere DLL.'
    count = dll.airspy_list_devices(None, 0)
    if count < 0:
        raise AirspyError(f'Airspy apparaatdetectie mislukt: fout {count}')
    if count == 0:
        return [], 'Geen Airspy R2 gevonden. Controleer USB, WinUSB en andere SDR-programma’s.'
    buf = (C.c_uint64 * min(count, 32))()
    found = dll.airspy_list_devices(buf, len(buf))
    if found < 0:
        raise AirspyError(f'Airspy-serienummers lezen mislukt: {found}')
    return list(map(int, buf[:min(found, len(buf))])), f'{found} Airspy apparaat/apparaten gevonden'


class AirspyNativeSource:
    """Native streaming Airspy R2 driver. Supports any sample-rate firmware reports."""
    def __init__(self, frequency: int, sample_rate: int, gain: float | None = None,
                 serial: int | None = None, dll=None):
        self.dll = dll if dll is not None else load_library()
        self.device = C.c_void_p()
        self.callback = None
        self.running = False
        self.pending = queue.Queue(maxsize=12)
        self.overflow_blocks = 0
        self.hardware_dropped_samples = 0
        self.sample_rate = 0
        self.last_block = time.monotonic()
        try:
            if serial is not None:
                if not hasattr(self.dll, 'airspy_open_sn'):
                    raise AirspyError('Deze libairspy ondersteunt geen selectie op serienummer')
                result = self.dll.airspy_open_sn(C.byref(self.device), C.c_uint64(serial))
            else:
                result = self.dll.airspy_open(C.byref(self.device))
            check(self.dll, result, 'Airspy USB openen')
            if not self.device.value:
                raise AirspyError('De driver gaf geen geldig Airspy-apparaathandvat terug')

            count = C.c_uint32(0)
            check(self.dll, self.dll.airspy_get_samplerates(self.device, C.byref(count), 0),
                  'Sample-rates opvragen')
            if count.value == 0 or count.value > 128:
                raise AirspyError('Airspy rapporteert een ongeldige lijst sample-rates')
            rates = (C.c_uint32 * count.value)()
            check(self.dll, self.dll.airspy_get_samplerates(self.device, rates, count.value),
                  'Sample-rate lijst lezen')
            chosen = min((int(r) for r in rates), key=lambda r: abs(r - sample_rate))
            check(self.dll, self.dll.airspy_set_sample_type(self.device, 0), 'FLOAT32 IQ instellen')
            check(self.dll, self.dll.airspy_set_samplerate(self.device, chosen), 'Sample-rate instellen')
            self.sample_rate = chosen
            self.tune(frequency)
            self.set_gain(gain)

            @ReceiveCallback
            def on_transfer(transfer_pointer):
                try:
                    transfer = transfer_pointer.contents
                    if transfer.sample_type != 0 or transfer.sample_count <= 0 or not transfer.samples:
                        return 0
                    # Interleaved [I0,Q0,I1,Q1...] float32 = complex64; COPY now.
                    sample_count = int(transfer.sample_count)
                    if sample_count > 4_194_304:
                        return -1  # corrupted transfer; safely stop streaming
                    float_array = (C.c_float * (sample_count * 2)).from_address(transfer.samples)
                    copy = np.frombuffer(float_array, np.complex64).copy()
                    self.hardware_dropped_samples = int(transfer.dropped_samples)
                    self.last_block = time.monotonic()
                    try:
                        self.pending.put_nowait(copy)
                    except queue.Full:
                        self.overflow_blocks += 1
                        try:
                            self.pending.get_nowait()  # keep newest samples
                        except queue.Empty:
                            pass
                        try:
                            self.pending.put_nowait(copy)
                        except queue.Full:
                            pass
                except Exception:
                    # ctypes callback exceptions must not escape into the driver.
                    return -1
                return 0

            self.callback = on_transfer  # prevent garbage collection
            check(self.dll, self.dll.airspy_start_rx(self.device, self.callback, None),
                  'IQ-stream starten')
            self.running = True
        except Exception:
            self.close()
            raise

    def tune(self, frequency):
        if not 24_000_000 <= int(frequency) <= 1_750_000_000:
            raise ValueError('Airspy R2 afstemgebied: 24–1750 MHz')
        check(self.dll, self.dll.airspy_set_freq(self.device, int(frequency)),
              'Airspy frequentie wijzigen')
        self._flush()

    def _flush(self):
        while True:
            try:
                self.pending.get_nowait()
            except queue.Empty:
                break

    def read(self, n):
        try:
            return self.pending.get(timeout=0.30)
        except queue.Empty:
            if self.running and self.dll.airspy_is_streaming(self.device) != 1:
                raise AirspyError('Airspy IQ-stream onverwacht gestopt (USB/firmware/driver)')
            return np.empty(0, dtype=np.complex64)

    def set_gain(self, gain):
        if gain is None:
            # Airspy R2 has LNA/Mixer AGC; no automatic VGA gain.
            check(self.dll, self.dll.airspy_set_linearity_gain(self.device, 12), 'Gain basiswaarde')
            check(self.dll, self.dll.airspy_set_lna_agc(self.device, 1), 'LNA AGC')
            check(self.dll, self.dll.airspy_set_mixer_agc(self.device, 1), 'Mixer AGC')
        else:
            if not 0 <= gain <= 21:
                raise ValueError('Airspy linearity gain: 0–21 stappen (geen dB)')
            check(self.dll, self.dll.airspy_set_lna_agc(self.device, 0), 'LNA AGC uit')
            check(self.dll, self.dll.airspy_set_mixer_agc(self.device, 0), 'Mixer AGC uit')
            check(self.dll, self.dll.airspy_set_linearity_gain(self.device, int(gain)), 'Linearity gain')

    @property
    def dropped(self):
        return self.hardware_dropped_samples, self.overflow_blocks

    def close(self):
        if self.device.value:
            try:
                if self.running:
                    self.dll.airspy_stop_rx(self.device)  # joins libairspy callback thread
            finally:
                self.running = False
                self.dll.airspy_close(self.device)
                self.device = C.c_void_p()
                self.callback = None
