"""Deterministic squelch-based frequency or memory scan controller.

Scanner operates by sequential retuning a *single* physical receiver.
Dwell, detect and hold timing is measured with monotonic timestamps.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ScanConfig:
    items: tuple
    dwell_ms: int = 700
    hold_ms: int = 1800

    def __post_init__(self):
        if not self.items:
            raise ValueError('Scanning requires at least one frequency')
        if not 150 <= self.dwell_ms <= 30_000:
            raise ValueError('Dwell must be between 150 and 30000 ms')
        if not 0 <= self.hold_ms <= 120_000:
            raise ValueError('Hold must be between 0 and 120000 ms')


def frequency_range(start_hz: int, end_hz: int, step_hz: int, limit: int = 3000):
    if not (10_000 <= start_hz <= end_hz <= 2_000_000_000):
        raise ValueError('Invalid scanner frequency range')
    if not 100 <= step_hz <= 1_000_000:
        raise ValueError('Frequency step must be between 100 and 1000000 Hz')
    count = (end_hz - start_hz) // step_hz + 1
    if count > limit:
        raise ValueError(f'Maximum {limit} scan channels; increase step or reduce range')
    return [int(start_hz + i * step_hz) for i in range(count)]


class ScanEngine:
    def __init__(self, config: ScanConfig):
        self.config = config
        self.index = -1
        self.last_tune = None
        self.last_signal = None

    def update(self, now: float, occupied: bool):
        """Return the next scan item on a retune, or None to hold position."""
        if self.index < 0:
            self.index = 0
            self.last_tune = now
            # The first 'occupied' measurement is from the old station, not
            # the first scan channel: never carry its hold timer across.
            self.last_signal = None
            return self.config.items[0]
        if occupied:
            self.last_signal = now
            return None
        if self.last_signal is not None and (now - self.last_signal) * 1000 < self.config.hold_ms:
            return None
        if (now - self.last_tune) * 1000 < self.config.dwell_ms:
            return None
        self.index = (self.index + 1) % len(self.config.items)
        self.last_tune = now
        self.last_signal = None
        return self.config.items[self.index]
