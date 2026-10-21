"""Independent SDR hardware backends. No device is opened until Start is pressed."""
from __future__ import annotations
import numpy as np


class SimulatedSource:
    """A deterministic-looking RF test source; does not pretend to receive RF."""

    def __init__(self, frequency: int, sample_rate: int):
        self.frequency = frequency
        self.sample_rate = sample_rate
        self.sample_index = 0
        self.phase = 0.0
        self.rng = np.random.default_rng(12)

    def tune(self, frequency):
        self.frequency = int(frequency)

    def read(self, n: int) -> np.ndarray:
        k = np.arange(n, dtype=np.float64) + self.sample_index
        t = k / self.sample_rate
        self.sample_index += n
        # Several stations in the observed IF spectrum; primary FM at DC.
        fm_modulation = 1_600 * np.sin(2 * np.pi * 600 * t)
        phase = self.phase + 2 * np.pi * np.cumsum(fm_modulation) / self.sample_rate
        self.phase = float(phase[-1] % (2 * np.pi))
        iq = (0.45 * np.exp(1j * phase)
              + 0.12 * np.exp(2j * np.pi * 135_000 * t)
              + 0.09 * np.exp(-2j * np.pi * 340_000 * t))
        iq += 0.02 * (self.rng.standard_normal(n) + 1j * self.rng.standard_normal(n))
        return iq.astype(np.complex64)

    def set_gain(self, gain):
        pass

    def close(self):
        pass


class RtlSource:
    """RTL2832U receiver using pyrtlsdr + librtlsdr."""

    def __init__(self, frequency: int, sample_rate: int, gain: float | None = None,
                 device_index: int = 0):
        try:
            from rtlsdr import RtlSdr
        except Exception as exc:
            raise RuntimeError("RTL backend ontbreekt: installeer pyrtlsdr en de Windows RTL-SDR driver/DLL") from exc
        try:
            self.radio = RtlSdr(device_index=device_index)
        except OSError as exc:
            raise RuntimeError(
                f'RTL-SDR #{device_index} niet te openen: {exc}. '
                'Sluit SDR++/SDR#, controleer de USB-poort en installeer zo nodig '
                'WinUSB via Zadig voor uitsluitend RTL2832U interface 0.'
            ) from exc
        try:
            self.radio.sample_rate = sample_rate
            self.radio.center_freq = frequency
            self.radio.gain = 'auto' if gain is None else float(gain)
            self.sample_rate = int(self.radio.sample_rate)
        except Exception:
            self.radio.close()
            raise

    def tune(self, frequency):
        self.radio.center_freq = int(frequency)

    def read(self, n):
        return np.asarray(self.radio.read_samples(n), dtype=np.complex64)

    def set_gain(self, gain):
        self.radio.gain = 'auto' if gain is None else float(gain)

    def close(self):
        self.radio.close()


# Backwards compatible import name for existing code and tests.
from .airspy_native import AirspyNativeSource

# Backwards compatible import name used by earlier versions/tests.
AirspySource = AirspyNativeSource


def make_source(kind: str, frequency: int, sample_rate: int, gain: float | None,
                device_id: int | None = None):
    if kind == "Demo (geen hardware)":
        return SimulatedSource(frequency, sample_rate)
    if kind == "RTL-SDR":
        return RtlSource(frequency, sample_rate, gain, device_index=int(device_id or 0))
    if kind == "Airspy R2":
        return AirspyNativeSource(frequency, sample_rate, gain, serial=device_id)
    raise ValueError(f"Onbekende bron: {kind}")
