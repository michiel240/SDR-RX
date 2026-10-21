"""Two independent tuning memories using one receiver (A/B switching only).

With a single SDR both VFOs are presets; this class does not imply
simultaneous audio decoding. No Qt dependency.
"""
from dataclasses import dataclass


@dataclass
class VFO:
    frequency_hz: int
    mode: str = 'NFM'
    bandwidth_hz: int = 12_500
    squelch_dbfs: int = -60
    passband_shift_hz: int = 0

    def __post_init__(self):
        if not 10_000 <= int(self.frequency_hz) <= 2_000_000_000:
            raise ValueError('VFO-frequency out of bounds')
        if not 100 <= int(self.bandwidth_hz) <= 200_000:
            raise ValueError('VFO-bandwidth out of bounds')
        if abs(int(self.passband_shift_hz)) > 100_000:
            raise ValueError('VFO passband shift out of bounds')


class VFOPair:
    def __init__(self, a=None, b=None):
        self.vfos = {'A': a or VFO(145_500_000), 'B': b or VFO(145_525_000)}
        self.active = 'A'

    def current(self):
        return self.vfos[self.active]

    def standby(self):
        return self.vfos['B' if self.active == 'A' else 'A']

    def select(self, which):
        if which not in self.vfos:
            raise ValueError('Select VFO A or B')
        self.active = which
        return self.current()

    def swap(self):
        return self.select('B' if self.active == 'A' else 'A')

    def copy_to_other(self):
        v = self.current()
        dest = 'B' if self.active == 'A' else 'A'
        self.vfos[dest] = VFO(v.frequency_hz, v.mode, v.bandwidth_hz, v.squelch_dbfs, v.passband_shift_hz)
        return self.vfos[dest]
