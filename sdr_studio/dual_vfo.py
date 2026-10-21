"""Two demodulators from ONE SDR stream; A -> left, B -> right.

Not a second hardware receiver. Both passbands must fit inside the IF
Nyquist region; no separate channelization of distant spectrum is claimed.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy import signal
from .dsp import Demodulator, AUDIO_RATE


@dataclass(frozen=True)
class VFOChannel:
    frequency_hz: int
    mode: str
    bandwidth_hz: int
    squelch_dbfs: float
    passband_shift_hz: int = 0


def center_and_validate(a: VFOChannel, b: VFOChannel, source_rate: int) -> int:
    """Ensure both RF filters fit inside the shared ~250 kHz IF passband.

    Decimation is computed identically to Demodulator and kept deliberately
    conservative for anti-alias guard; WFM cannot be paired with distant VFOs.
    """
    decim = max(1, int(source_rate)//250_000)
    if_rate = int(source_rate)/decim
    center = (int(a.frequency_hz)+int(b.frequency_hz))//2
    for ch in (a,b):
        if not 10_000 <= ch.frequency_hz <= 2_000_000_000:
            raise ValueError('VFO buiten ontvangerbereik')
        # SSB and passband shift need additional guard.
        half_width = max(1500, ch.bandwidth_hz * .5)
        offset = abs(ch.frequency_hz - center + ch.passband_shift_hz)
        if offset + half_width + 8_000 > if_rate * .41:
            raise ValueError(f'VFO A en B liggen te ver uit elkaar of de filters zijn te breed '
                             f'(bruikbaar IF-venster ±{if_rate*.41/1000:.0f} kHz). '
                             'Kies twee dichtbije NFM/AM/SSB-frequenties.')
    return center


class DualVFOProcessor:
    """Shared front-end decimation, then independent channel DSP and squelch."""
    def __init__(self, source_rate, a: VFOChannel, b: VFOChannel, *, agc=True,
                 notch_hz=0, noise_reduction=False, eq_db=(0,0,0)):
        self.rate = int(source_rate)
        self.a, self.b = a, b
        self.center = center_and_validate(a,b,self.rate)
        self.decim = max(1,self.rate//250_000)
        common = dict(agc=agc, notch_hz=notch_hz,
                      noise_reduction=noise_reduction,eq_db=eq_db)
        self.left = Demodulator(self.rate, a.mode, a.bandwidth_hz,
                  passband_shift_hz=a.frequency_hz-self.center+a.passband_shift_hz,**common)
        self.right = Demodulator(self.rate, b.mode, b.bandwidth_hz,
                  passband_shift_hz=b.frequency_hz-self.center+b.passband_shift_hz,**common)
        self.levels = (-120.0,-120.0)

    def process(self, iq):
        x = np.asarray(iq,dtype=np.complex64)
        # One costly anti-alias decimator, never open the SDR again.
        base = signal.resample_poly(x,1,self.decim) if self.decim>1 else x
        a,la = self.left.process_if(base)
        b,lb = self.right.process_if(base)
        count = min(len(a),len(b))
        if la < self.a.squelch_dbfs:
            a[:] = 0
        if lb < self.b.squelch_dbfs:
            b[:] = 0
        self.levels=(la,lb)
        return np.column_stack((a[:count],b[:count])).astype(np.float32),max(la,lb)
