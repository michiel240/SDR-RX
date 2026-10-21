"""v0.5.1 fixes for safe live A/B retuning and WFM audio."""
from pathlib import Path
import ast

import numpy as np
from scipy import signal

from sdr_studio.worker import ReceiverWorker
from sdr_studio.dsp import DEFAULT_BW, Demodulator


class FakeTuner:
    def __init__(self):
        self.calls = []
        self.fail = False

    def tune(self, frequency):
        self.calls.append(frequency)
        if self.fail:
            raise OSError('Afstemfout driver')


class FakeAudio:
    def __init__(self):
        self.flushes = 0

    def flush(self):
        self.flushes += 1


def worker():
    logs, acks = [], []
    rx = ReceiverWorker('Demo (geen hardware)', 145_500_000, 2_500_000,
                        'NFM', -60, .25, None,
                        lambda *args: None, logs.append, lambda: None,
                        tune_callback=acks.append)
    rx.audio = FakeAudio()
    return rx, logs, acks


def test_vfo_switch_is_one_transaction_and_keeps_same_stream():
    rx, logs, acks = worker()
    radio = FakeTuner()
    message = {'name':'B','previous':'A','seq':1}
    assert rx._retune(radio, 145_525_000, 'AM', 8_000, -65, reply=message)
    assert radio.calls == [145_525_000]
    assert (rx.frequency,rx.mode,rx.bandwidth_hz,rx.sql) == (145_525_000,'AM',8_000,-65)
    assert rx.audio.flushes == 1
    assert rx._fade_in_remaining == 4800
    assert acks == [{'request':message,'success':True,'frequency_hz':145_525_000,'error':''}]
    assert not logs


def test_vfo_retune_failure_does_not_kill_receiver_state():
    rx, logs, acks = worker()
    radio = FakeTuner()
    radio.fail = True
    message = {'name':'B','previous':'A','seq':2}
    assert not rx._retune(radio, 145_525_000, 'AM', 8_000, -65, reply=message)
    assert (rx.frequency,rx.mode,rx.bandwidth_hz,rx.sql) == (145_500_000,'NFM',12_500,-60)
    assert rx.audio.flushes == 0
    assert acks[0]['success'] is False
    assert any('ontvangst blijft actief' in line for line in logs)


def test_vfo_equal_frequency_does_not_retune_hardware():
    rx, _, _ = worker()
    radio = FakeTuner()
    assert rx._retune(radio, 145_500_000, 'AM', 8000, -62)
    assert radio.calls == []
    assert rx.mode == 'AM'


def test_vfo_bad_filter_is_rejected_before_hardware_tune():
    rx, _, _ = worker()
    radio = FakeTuner()
    assert not rx._retune(radio, 145_525_000, 'NFM', 200_000, -50)
    assert not radio.calls
    assert rx.frequency == 145_500_000


def test_fade_ramps_without_muting_continuously():
    rx, _, _ = worker()
    rx._fade_in_remaining = 4800
    a = np.ones(2400, dtype=np.float32)
    rx._fade_audio(a)
    assert a[0] == 0
    assert 0.4 < a[-1] < 0.6
    assert rx._fade_in_remaining == 2400
    b = np.ones(2400, dtype=np.float32)
    rx._fade_audio(b)
    assert b[-1] > .99
    assert rx._fade_in_remaining == 0


def test_wfm_default_filter_matches_baseline_cutoff_and_taps():
    d = Demodulator(2_500_000, 'WFM')
    assert DEFAULT_BW['WFM'] == 200_000
    expected = signal.firwin(129, 100_000, fs=d.if_rate)
    np.testing.assert_allclose(d.channel_fir, expected, rtol=0, atol=1e-13)


def test_gui_switch_no_separate_frequency_and_mode_commands():
    src = (Path(__file__).resolve().parents[1] / 'sdr_studio' / 'app.py').read_text(encoding='utf8')
    t = ast.parse(src)
    window = next(n for n in t.body if isinstance(n,ast.ClassDef) and n.name=='Window')
    select = next(n for n in window.body if isinstance(n,ast.FunctionDef) and n.name=='select_vfo')
    cmd_calls = [n for n in ast.walk(select) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='command']
    assert len(cmd_calls)==1
    assert cmd_calls[0].args[0].value == 'vfo'


def test_audio_lp_matches_previous_analog_tone_when_bandwidth_is_wide():
    for mode,bw,expected in [('AM',16_000,5500),('NFM',20_000,4000),
                             ('WFM',200_000,15000),('USB',6000,4000)]:
        d=Demodulator(2_500_000, mode, bandwidth_hz=bw)
        ref=signal.butter(4, expected, fs=48_000, btype='lowpass', output='sos')
        np.testing.assert_allclose(d.audio_lp,ref,atol=1e-12,rtol=0)
        assert d._level==.25
