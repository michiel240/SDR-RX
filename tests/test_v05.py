"""New v0.5 features, no GUI / USB drivers needed."""
import numpy as np
import pytest
from scipy import signal

from sdr_studio.dsp import Demodulator, BANDWIDTHS, DEFAULT_BW, valid_bandwidth
from sdr_studio.vfo import VFO, VFOPair
from sdr_studio.scan import ScanConfig, ScanEngine, frequency_range
from sdr_studio.digital_stream import parse_decoder_line


def test_vfo_switch_retains_independent_settings():
    pair = VFOPair()
    pair.current().mode = 'USB'
    pair.current().frequency_hz = 14_240_000
    pair.current().bandwidth_hz = 3000
    pair.select('B')
    assert pair.current().frequency_hz == 145_525_000
    pair.current().frequency_hz = 433_920_000
    assert pair.swap().frequency_hz == 14_240_000
    assert pair.standby().frequency_hz == 433_920_000
    pair.copy_to_other()
    assert pair.standby() == pair.current()
    assert pair.standby() is not pair.current()
    with pytest.raises(ValueError):
        pair.select('C')


def test_bandwidth_and_options_for_all_modes():
    for mode, values in BANDWIDTHS.items():
        assert valid_bandwidth(mode, DEFAULT_BW[mode]) == DEFAULT_BW[mode]
        for rate in (2_400_000, 10_000_000):
            d = Demodulator(rate, mode, bandwidth_hz=values[0], agc=False,
                            notch_hz=1000, noise_reduction=True)
            assert len(d.channel_fir) >= 129
            wav, pwr = d.process(np.full(65_536,.25+.12j,dtype=np.complex64))
            assert np.all(np.isfinite(wav)) and np.isfinite(pwr)
    with pytest.raises(ValueError):
        valid_bandwidth('NFM',200000)


def test_nfm_filter_bandwidth_changes_energy():
    rate=250_000
    n=100000
    t=np.arange(n)/rate
    input_iq = (np.exp(2j*np.pi*1500*t) + np.exp(2j*np.pi*11000*t)).astype(np.complex64)
    narrow=Demodulator(rate,'NFM',bandwidth_hz=5000)
    wide=Demodulator(rate,'NFM',bandwidth_hz=25000)
    a=signal.lfilter(narrow.channel_fir,[1],input_iq)
    b=signal.lfilter(wide.channel_fir,[1],input_iq)
    assert np.mean(np.abs(b[2000:])**2) > np.mean(np.abs(a[2000:])**2)*1.65


def test_notch_attenuates_1000_hz_tone():
    t=np.arange(48_000)/48_000
    sine=np.sin(2*np.pi*1000*t)
    d=Demodulator(240_000, 'AM', notch_hz=1000)
    y, _=signal.lfilter(d.notch_b,d.notch_a,sine,zi=d.notch_state)
    assert np.sqrt(np.mean(y[15000:]**2)) < .1*np.sqrt(np.mean(sine**2))


def test_scan_frequency_range_with_guardrails():
    assert frequency_range(144_000_000,144_050_000,12_500)==[
        144_000_000,144_012_500,144_025_000,144_037_500,144_050_000]
    with pytest.raises(ValueError):
        frequency_range(144_000_000, 200_000_000,100)
    with pytest.raises(ValueError):
        frequency_range(145_000_000, 144_000_000,12_500)


def test_scan_hold_and_dwell():
    a={'frequency':145_500_000,'mode':'NFM'}
    b={'frequency':145_525_000,'mode':'NFM'}
    e=ScanEngine(ScanConfig((a,b),dwell_ms=500,hold_ms=1500))
    assert e.update(0,False)==a
    assert e.update(.4,False) is None
    assert e.update(.6,True) is None
    assert e.update(1.2,False) is None
    assert e.update(2.11,False)==b
    assert e.update(2.3,False) is None
    assert e.update(2.7,False)==a


def test_decoder_events_extract_icao_and_ais_metadata():
    event = parse_decoder_line('dump1090','*8D40621D58C382D690C8AC2863A7;')
    assert event and 'ICAO 40621D' in event.detail
    msg = '!AIVDM,1,1,,A,13aG?P0000,0*76'
    event = parse_decoder_line('AIS-catcher',msg)
    assert event and 'checksum ongeldig' in event.detail
    assert event.protocol == 'AIS NMEA'


def test_scan_does_not_carry_previous_station_hold():
    a={'frequency':100_000_000,'mode':'WFM'}
    b={'frequency':101_000_000,'mode':'WFM'}
    scanner=ScanEngine(ScanConfig((a,b),dwell_ms=200,hold_ms=2000))
    assert scanner.update(0.0, True)==a  # signal measured before tuning a
    assert scanner.update(.25, False)==b  # should not wait 2 seconds
