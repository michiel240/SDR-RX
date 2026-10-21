"""Streaming three-band peaking audio EQ, -12..+12 dB per band."""
from __future__ import annotations
import numpy as np
from scipy import signal

CENTERS = (180., 1000., 5500.)


def peaking_sos(freq, gain_db, rate=48000, q=.8):
    if not -12 <= float(gain_db) <= 12:
        raise ValueError('EQ versterking buiten ±12 dB')
    a = 10**(float(gain_db)/40)
    omega = 2*np.pi*freq/rate
    alpha = np.sin(omega)/(2*q)
    b = np.array([1+alpha*a, -2*np.cos(omega), 1-alpha*a])
    a0, a1, a2 = 1+alpha/a, -2*np.cos(omega), 1-alpha/a
    return np.array([b[0]/a0, b[1]/a0, b[2]/a0, 1., a1/a0, a2/a0])


class Equalizer:
    def __init__(self, db=(0, 0, 0), rate=48000):
        self.db = tuple(int(x) for x in db)
        if len(self.db) != 3:
            raise ValueError('EQ heeft drie frequentiebanden')
        self.sos = np.array([peaking_sos(f, gain, rate) for f, gain in zip(CENTERS, self.db)])
        self.state = np.zeros((3, 2))

    def process(self, samples):
        if not any(self.db):
            return samples
        out, self.state = signal.sosfilt(self.sos, samples, zi=self.state)
        return out
