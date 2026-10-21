"""RX-only DSP. Live FIR bandwidth, optional audio AGC, notch and noise gate.

Single channel selected by the *active* VFO. The FFT always uses raw IQ.
No hardware drivers imported, allowing reproducible signal-level tests.
"""
from __future__ import annotations

from fractions import Fraction
import numpy as np
from scipy import signal
from .equalizer import Equalizer

AUDIO_RATE = 48_000
MODES = ('AM', 'NFM', 'WFM', 'USB', 'LSB', 'CW')
BANDWIDTHS = {
    'AM': (4000, 6000, 8000, 10000, 12000, 16000),
    'NFM': (5000, 6250, 8500, 10000, 12500, 15000, 20000, 25000),
    'WFM': (120000, 150000, 180000, 200000),
    'USB': (1200, 1800, 2400, 3000, 3600, 5000, 6000),
    'LSB': (1200, 1800, 2400, 3000, 3600, 5000, 6000),
    'CW': (200, 350, 500, 800, 1200, 2000),
}
DEFAULT_BW = {'AM':8000,'NFM':12500,'WFM':200000,'USB':3000,'LSB':3000,'CW':500}


def valid_bandwidth(mode: str, bandwidth: int):
    if mode not in BANDWIDTHS:
        raise ValueError(f'Unknown mode: {mode}')
    if not 100 <= int(bandwidth) <= 200_000:
        raise ValueError(f'Invalid bandwidth: {bandwidth}')
    # The GUI and region adjust to supported filter limits.
    lo, hi = BANDWIDTHS[mode][0], BANDWIDTHS[mode][-1]
    if not lo <= int(bandwidth) <= hi:
        raise ValueError(f'Bandwidth for {mode} must be {lo}–{hi} Hz')
    return int(bandwidth)


class Demodulator:
    """Streamed demodulator with persistent channel and audio filter states."""

    def __init__(self, source_rate: int, mode: str='NFM', bandwidth_hz: int | None=None,
                 agc: bool=True, notch_hz: int=0, noise_reduction: bool=False,
                 passband_shift_hz: int=0, eq_db=(0, 0, 0)):
        if mode not in MODES:
            raise ValueError(f'Unknown mode: {mode}')
        self.source_rate = int(source_rate)
        self.mode = mode
        self.bandwidth_hz = valid_bandwidth(mode, bandwidth_hz or DEFAULT_BW[mode])
        self.agc = bool(agc)
        self.notch_hz = int(notch_hz)
        self.noise_reduction = bool(noise_reduction)
        self.passband_shift_hz = int(passband_shift_hz)
        if abs(self.passband_shift_hz) > 100_000:
            raise ValueError("Passband shift maximaal ±100 kHz")
        self._shift_index = 0
        self.equalizer = Equalizer(eq_db, AUDIO_RATE)
        self.decim = max(1, self.source_rate // 250_000)
        self.if_rate = self.source_rate / self.decim
        self.previous = 1+0j
        self.channel_fir = self._channel_filter()
        self.channel_state = np.zeros(len(self.channel_fir)-1, dtype=np.complex128)
        hp = signal.butter(2, 70 if mode != 'CW' else 120, fs=AUDIO_RATE,
                           btype='highpass', output='sos')
        self.audio_hp = hp
        self.hp_state = signal.sosfilt_zi(hp)*0
        # Retain v0.4.2 audio tone where BW allows it. The RF filter can
        # still be narrowed independently; the audio LP must not widen just
        # because the configured channel BW is wider.
        audio_ceiling = {'WFM':15_000, 'AM':5_500, 'NFM':4_000,
                         'USB':4_000, 'LSB':4_000, 'CW':1_800}[mode]
        high = min(audio_ceiling, 0.45*AUDIO_RATE)
        if mode in ('AM', 'NFM'):
            high = min(high, self.bandwidth_hz*0.42)
        high = max(750, high)
        lp = signal.butter(4, high, fs=AUDIO_RATE, btype='lowpass', output='sos')
        self.audio_lp = lp
        self.lp_state = signal.sosfilt_zi(lp)*0
        self.notch_b = self.notch_a = self.notch_state = None
        if self.notch_hz:
            if not 150 <= self.notch_hz <= 4500:
                raise ValueError('Notch frequency must be between 150–4500 Hz')
            b, a = signal.iirnotch(self.notch_hz, Q=18, fs=AUDIO_RATE)
            self.notch_b, self.notch_a = b, a
            self.notch_state = np.zeros(max(len(a),len(b))-1)
        self._level = 0.25
        self._noise_floor = None
        self.last_mpx = None  # WFM unfiltered multiplex for optional RDS

    def _channel_filter(self):
        # Limiting at half the IF Nyquist gives enough transition room for FIR.
        if self.mode in ('NFM','WFM','AM'):
            # 200-kHz WFM setting reproduces the proven v0.4.2
            # 100-kHz/129-tap IF channel response. Narrower user BW is honored.
            factor = 0.50 if self.mode == 'WFM' else 0.47
            cutoff = min(self.bandwidth_hz*factor, 0.43*self.if_rate)
            return signal.firwin(129, cutoff, fs=self.if_rate)
        if self.mode == 'CW':
            lo, hi = 550-self.bandwidth_hz/2, 550+self.bandwidth_hz/2
        else:
            lo, hi = 150, 150+self.bandwidth_hz
        # Complex FIR selects only the requested sideband.
        center = (lo+hi)/2*(1 if self.mode != 'LSB' else -1)
        halfwidth = (hi-lo)/2
        base = signal.firwin(257, halfwidth, fs=self.if_rate)
        n = np.arange(len(base)) - (len(base)-1)/2
        return base*np.exp(2j*np.pi*center*n/self.if_rate)

    def _denoise(self, audio):
        """Conservative blockwise noise suppressor; no training or network.

        Estimates background spectrum with a slow envelope and attenuates bins
        near the floor, preserving prominent voice/music peaks. Disabled by
        default to avoid artifacts. This is not a learned speech denoiser.
        """
        n = len(audio)
        if n < 128:
            return audio
        spec = np.fft.rfft(audio)
        magnitude = np.abs(spec)
        if self._noise_floor is None or len(self._noise_floor) != len(magnitude):
            self._noise_floor = magnitude.copy()
        else:
            # Allow the noise estimate to fall relatively quickly and rise slowly.
            rate = np.where(magnitude < self._noise_floor, .10, .005)
            self._noise_floor += rate*(magnitude-self._noise_floor)
        floor = self._noise_floor
        gain = np.clip((magnitude - 1.4*floor)/(magnitude+1e-10), .22, 1)
        # Smooth in frequency to avoid musical noise at isolated bins.
        gain = np.convolve(gain, np.ones(7)/7, mode='same')
        return np.fft.irfft(spec*gain, n=n).astype(np.float64)

    def process(self, iq: np.ndarray) -> tuple[np.ndarray, float]:
        iq = np.asarray(iq, dtype=np.complex64)
        if not len(iq):
            return np.empty(0, dtype=np.float32), -120.
        base = signal.resample_poly(iq, 1, self.decim) if self.decim > 1 else iq
        return self.process_if(base)

    def process_if(self, base: np.ndarray) -> tuple[np.ndarray, float]:
        """Demodulate an already-decimated IQ block; used by shared dual VFO."""
        base = np.asarray(base, dtype=np.complex64)
        if not len(base):
            return np.empty(0, dtype=np.float32), -120.
        if self.passband_shift_hz:
            indices = np.arange(len(base), dtype=np.float64) + self._shift_index
            base = base * np.exp(-2j*np.pi*self.passband_shift_hz*indices/self.if_rate)
        self._shift_index += len(base)
        base, self.channel_state = signal.lfilter(self.channel_fir, [1.0], base, zi=self.channel_state)
        power_dbfs = float(20*np.log10(np.sqrt(np.mean(np.abs(base)**2))+1e-12))
        if self.mode in ('NFM','WFM'):
            prev = np.concatenate(([self.previous], base[:-1]))
            self.previous = complex(base[-1])
            delta = np.angle(base*np.conj(prev))
            deviation = 75_000 if self.mode == 'WFM' else 5_000
            demod = delta * (self.if_rate/(2*np.pi*deviation))
            # RDS uses the 57-kHz subcarrier of the FM multiplex, not
            # the 48-kHz audio signal filtered below 15 kHz.
            self.last_mpx = demod if self.mode == 'WFM' else None
        elif self.mode == 'AM':
            demod = np.abs(base)
        else:
            demod = np.real(base)*2
        ratio = Fraction(AUDIO_RATE, int(round(self.if_rate))).limit_denominator(2000)
        audio = signal.resample_poly(demod, ratio.numerator, ratio.denominator)
        audio, self.hp_state = signal.sosfilt(self.audio_hp, audio, zi=self.hp_state)
        audio, self.lp_state = signal.sosfilt(self.audio_lp, audio, zi=self.lp_state)
        if self.notch_b is not None:
            audio, self.notch_state = signal.lfilter(self.notch_b, self.notch_a, audio,
                                                    zi=self.notch_state)
        if self.noise_reduction:
            audio = self._denoise(audio)
        audio = self.equalizer.process(audio)
        if self.agc:
            rms = float(np.sqrt(np.mean(audio*audio)))+1e-9
            self._level = .97*self._level+.03*rms
            scale = min(15, .16/max(.012, self._level))
        else:
            scale = 1
        return np.clip(audio*scale,-.95,.95).astype(np.float32), power_dbfs


def spectrum_dbfs(iq: np.ndarray, fft_size: int=1024) -> np.ndarray:
    if len(iq) < fft_size:
        iq = np.pad(iq, (0,fft_size-len(iq)))
    chunk = iq[-fft_size:]
    window = np.hanning(fft_size)
    spec = np.fft.fftshift(np.fft.fft(chunk*window))
    return (20*np.log10(np.abs(spec)/np.sum(window)+1e-12)).astype(np.float32)
