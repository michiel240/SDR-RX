"""RF signal indicator. S-unit readings require a calibration reference."""
from __future__ import annotations
import math
import time


def calibrated_s_reading(dbfs: float, dbm_at_zero_dbfs: float | None):
    """An *estimate* only, unless calibrated with a known RF signal source.

    HF convention: S9 = -73 dBm, 6 dB per S-unit. This convention is NOT
    generally valid for VHF/UHF without choosing the applicable reference.
    """
    if dbm_at_zero_dbfs is None:
        return None
    dbm = float(dbfs) + float(dbm_at_zero_dbfs)
    units = 9 + (dbm + 73)/6
    if units <= 9:
        return f'S{max(0, min(9, int(round(units))))} · {dbm:.0f} dBm (schatting)'
    return f'S9+{max(0, int(round(dbm+73)))} dB · {dbm:.0f} dBm (schatting)'


class PeakMeter:
    def __init__(self, hold_seconds=2.0):
        self.hold_seconds = float(hold_seconds)
        self.peak = -120.0
        self.updated_at = 0.0

    def update(self, value, now=None):
        now = time.monotonic() if now is None else float(now)
        value = float(value)
        if not math.isfinite(value):
            return self.peak
        if value >= self.peak or now - self.updated_at > self.hold_seconds:
            self.peak = value
            self.updated_at = now
        return self.peak
