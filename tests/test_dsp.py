import numpy as np
from scipy import signal
from sdr_studio.dsp import Demodulator, spectrum_dbfs
from sdr_studio.devices import SimulatedSource


def test_spectrum_peak():
    rate = 2_400_000
    n = 8192
    iq = np.exp(2j*np.pi*200_000*np.arange(n)/rate).astype(np.complex64)
    spec = spectrum_dbfs(iq, 1024)
    peak_hz = (np.argmax(spec) / 1024 - .5) * rate
    assert abs(peak_hz - 200_000) < 4000


def test_nfm_recovers_tone():
    rate = 240_000
    t = np.arange(rate // 2) / rate
    f_dev = 3200*np.sin(2*np.pi*800*t)
    iq = np.exp(2j*np.pi*np.cumsum(f_dev)/rate).astype(np.complex64)
    d = Demodulator(rate, 'NFM')
    wav, dbfs = d.process(iq)
    freqs, psd = signal.welch(wav, 48_000, nperseg=4096)
    dominant_hz = freqs[np.argmax(psd)]
    assert abs(dominant_hz - 800) < 22
    assert -1 < dbfs < 1
    assert np.max(np.abs(wav)) < 1


def test_am_recovers_tone():
    rate = 240_000
    t = np.arange(rate // 2) / rate
    iq = ((0.4 + 0.2*np.sin(2*np.pi*1000*t)) + 0j).astype(np.complex64)
    wav, _ = Demodulator(rate, 'AM').process(iq)
    freqs, psd = signal.welch(wav, 48_000, nperseg=4096)
    assert abs(freqs[np.argmax(psd)] - 1000) < 22


def test_usb_lsb_filters_opposite_sides():
    fs = 250_000
    freq = 1500
    n = 120_000
    t = np.arange(n)/fs
    usb = np.exp(2j*np.pi*freq*t)
    lsb = np.exp(-2j*np.pi*freq*t)
    for mode, wanted, rejected in [('USB', usb, lsb), ('LSB', lsb, usb)]:
        d = Demodulator(fs, mode)
        w = signal.lfilter(d.channel_fir, 1, wanted)
        r = signal.lfilter(d.channel_fir, 1, rejected)
        assert np.sqrt(np.mean(np.abs(w[2000:])**2)) > 5 * np.sqrt(np.mean(np.abs(r[2000:])**2))


def test_sim_source_and_supported_modes():
    source = SimulatedSource(145_500_000, 2_400_000)
    iq = source.read(65536)
    assert iq.shape == (65536,)
    assert iq.dtype == np.complex64
    for mode in ['AM', 'NFM', 'WFM', 'USB', 'LSB', 'CW']:
        d = Demodulator(2_400_000, mode)
        audio, level = d.process(iq)
        assert len(audio) > 1000
        assert np.all(np.isfinite(audio))
        assert np.isfinite(level)


def test_airspy_rate_10_msps_dsp():
    d = Demodulator(10_000_000, 'WFM')
    assert 200_000 <= d.if_rate <= 300_000
    iq = np.full(65536, 0.15+0j, dtype=np.complex64)
    audio, _ = d.process(iq)
    assert 300 <= len(audio) <= 320
