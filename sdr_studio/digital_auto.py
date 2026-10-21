"""DIGITAL AUTO RF candidate monitor for SDR Studio RX by M@rcello.

Never identifies DMR/P25/etc by FFT alone. RF morphology is advisory;
protocol identity is only shown after independent decoder output.
No external executable runs merely because a spectral peak exists.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time

import numpy as np


@dataclass(frozen=True)
class RFCandidate:
    frequency_hz: int
    width_hz: int
    peak_dbfs: float
    over_noise_db: float
    kind: str
    hits: int
    evidence: str = 'RF-signaal, protocol onbekend'


def find_rf_candidates(spectrum_dbfs, sample_rate_hz: int, center_hz: int,
                       *, threshold_db: float = 17.0, max_candidates: int = 8) -> list[RFCandidate]:
    """Locate spectral energy clusters without attempting protocol identification.

    FFT input must be center-shifted, evenly spaced from center-rate/2.
    DC bins are rejected because direct-conversion SDR devices have DC spurs.
    """
    s = np.asarray(spectrum_dbfs, dtype=np.float32)
    if s.ndim != 1 or len(s) < 128 or not np.isfinite(s).any():
        return []
    sample_rate_hz = int(sample_rate_hz)
    if sample_rate_hz <= 0:
        return []
    n = len(s)
    clean = np.where(np.isfinite(s), s, -200.0)
    noise = float(np.median(clean))
    resolution = sample_rate_hz / n
    # Only use the central 90% of the receiver passband. At least +/-2kHz
    # around DC are removed to avoid false positives from LO/DC artifacts.
    allowed = np.zeros(n, dtype=bool)
    edge = max(3, math.ceil(n * 0.05))
    allowed[edge:n - edge] = True
    dc_bins = max(1, int(math.ceil(2000.0 / resolution)))
    allowed[n//2 - dc_bins:n//2 + dc_bins + 1] = False
    mask = (clean >= noise + float(threshold_db)) & allowed
    if not mask.any():
        return []
    lefts = np.flatnonzero(mask & ~np.r_[False, mask[:-1]])
    rights = np.flatnonzero(mask & ~np.r_[mask[1:], False])
    found = []
    for left, right in zip(lefts, rights):
        if right < left:
            continue
        section = clean[left:right+1]
        peak_bin = left + int(np.argmax(section))
        peak = float(clean[peak_bin])
        above = peak - noise
        if above < threshold_db or not np.isfinite(peak):
            continue
        width = max(int(round(resolution)), int(round((right-left+1)*resolution)))
        # Channel center is better approximated by the occupied-bin midpoint
        # than by the highest FFT bin (which may be an individual sideband).
        freq = int(round(center_hz + ((left+right)/2-n//2)*resolution))
        if not 10_000 <= freq <= 2_000_000_000:
            continue
        label = ('smalband / drager' if width < 30_000 else
                 'middelbreed' if width < 150_000 else 'breedband')
        found.append(RFCandidate(freq, width, round(peak,1), round(above,1),label,1))
    found.sort(key=lambda x: x.over_noise_db, reverse=True)
    return found[:max(1,int(max_candidates))]


@dataclass
class _Track:
    frequency_hz: int
    width_hz: int
    peak_dbfs: float
    over_noise_db: float
    kind: str
    hits: int
    last_seen: float
    last_reported: float = -1e12


class RFMonitor:
    """Hold off one-off FFT spikes. Emit stable, rate-limited candidates."""
    def __init__(self, *, threshold_db: float = 17.0, min_hits: int = 2,
                 report_interval_sec: float = 25.0, stale_after_sec: float = 6.0):
        self.threshold_db = float(threshold_db)
        self.min_hits = max(2,int(min_hits))
        self.report_interval_sec = float(report_interval_sec)
        self.stale_after_sec = float(stale_after_sec)
        self.tracks: list[_Track] = []

    def reset(self):
        self.tracks.clear()

    def update(self, spectrum_dbfs, sample_rate_hz: int, center_hz: int,
               *, now: float | None = None) -> list[RFCandidate]:
        now = time.monotonic() if now is None else float(now)
        self.tracks = [t for t in self.tracks if now-t.last_seen <= self.stale_after_sec]
        readings = find_rf_candidates(spectrum_dbfs, sample_rate_hz, center_hz,
                                      threshold_db=self.threshold_db)
        emitted = []
        visited = set()
        for reading in readings:
            tolerance = max(2_500, int(2*sample_rate_hz/len(spectrum_dbfs)),
                            reading.width_hz//2)
            available = [(i,t) for i,t in enumerate(self.tracks)
                         if i not in visited and abs(t.frequency_hz-reading.frequency_hz) <= tolerance]
            if available:
                i, t = min(available, key=lambda z: abs(z[1].frequency_hz-reading.frequency_hz))
                visited.add(i)
                # Don't count duplicate observations less than 0.3 seconds apart.
                if now - t.last_seen >= 0.3:
                    t.hits += 1
                t.frequency_hz = reading.frequency_hz
                t.width_hz = reading.width_hz
                t.peak_dbfs = reading.peak_dbfs
                t.over_noise_db = reading.over_noise_db
                t.kind = reading.kind
                t.last_seen = now
            else:
                t = _Track(reading.frequency_hz,reading.width_hz,reading.peak_dbfs,
                           reading.over_noise_db,reading.kind,1,now)
                self.tracks.append(t)
                visited.add(len(self.tracks)-1)
            if t.hits >= self.min_hits and now-t.last_reported >= self.report_interval_sec:
                t.last_reported=now
                emitted.append(RFCandidate(t.frequency_hz,t.width_hz,t.peak_dbfs,
                                           t.over_noise_db,t.kind,t.hits))
        self.tracks = sorted(self.tracks,key=lambda t:t.last_seen,reverse=True)[:35]
        return emitted
