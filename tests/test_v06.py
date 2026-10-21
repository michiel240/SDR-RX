"""v0.6 DSP / offline IQ / safety regression tests (no USB or GUI needed)."""
from __future__ import annotations
import ast
import json
import numpy as np
import pytest
from pathlib import Path
from scipy import signal
from sdr_studio.dsp import Demodulator
from sdr_studio.equalizer import Equalizer
from sdr_studio.signal_meter import PeakMeter, calibrated_s_reading
from sdr_studio.iq_files import IQRecorder, IQFileSource, metadata_file
from sdr_studio.memory_groups import groups, group_members, shortcut_memory
from sdr_studio.vfo import VFO, VFOPair


def test_equalizer_flat_is_bypass():
    inp = np.random.default_rng(10).standard_normal(500)
    assert np.array_equal(Equalizer().process(inp), inp)


@pytest.mark.parametrize('gain', [-9, 0, 9])
def test_equalizer_has_specified_gain_at_middle_band(gain):
    eq = Equalizer((0, gain, 0))
    w, h = signal.sosfreqz(eq.sos, worN=[2*np.pi*1000/48000])
    assert 20*np.log10(abs(h[0])) == pytest.approx(gain, abs=.5)


def test_equalizer_rejects_out_of_range():
    with pytest.raises(ValueError):
        Equalizer((20, 0, 0))


def test_passband_shift_moves_known_rf_tone_into_channel():
    # A narrow AM filter does not pass a 15kHz offset carrier until PBT=15kHz.
    rate = 2_400_000
    x = .6*np.exp(2j*np.pi*15_000*np.arange(131072)/rate).astype(np.complex64)
    a = Demodulator(rate, mode='AM', bandwidth_hz=4000, agc=False)
    b = Demodulator(rate, mode='AM', bandwidth_hz=4000, agc=False, passband_shift_hz=15000)
    _, off_level = a.process(x)
    _, on_level = b.process(x)
    assert on_level > off_level+20


def test_passband_shift_out_of_range_rejected():
    with pytest.raises(ValueError):
        Demodulator(2_400_000, 'NFM', passband_shift_hz=100001)


def test_vfo_copy_preserves_passband_shift():
    pair = VFOPair(a=VFO(145_000_000, 'NFM', 12500, -60, 1200))
    pair.copy_to_other()
    assert pair.vfos['B'].passband_shift_hz == 1200


def test_calibration_not_fake_by_default():
    assert calibrated_s_reading(-50, None) is None
    assert 'schatting' in calibrated_s_reading(-50, 0)


def test_peak_meter_hold_and_expiry():
    p = PeakMeter(hold_seconds=2)
    assert p.update(-40, now=1) == -40
    assert p.update(-70, now=2) == -40
    assert p.update(-65, now=4) == -65


def test_memory_groups_and_shortcuts_preserve_legacy_rows():
    memories = [{'name':'A', 'frequency': 145_500_000, 'mode':'NFM'},
                {'name':'B', 'frequency': 123_000_000, 'mode':'AM', 'group':'Luchtvaart','shortcut':2}]
    assert groups(memories) == ['Algemeen', 'Luchtvaart']
    assert [x['name'] for x in group_members(memories, 'Luchtvaart')] == ['B']
    assert len(group_members(memories, 'Alle groepen')) == 2
    assert shortcut_memory(memories, 2)['name'] == 'B'
    assert shortcut_memory(memories, 1) is None


def test_iq_capture_roundtrip(tmp_path):
    path = tmp_path/'example.cf32'
    x = np.array([1+2j, -0.5-0.7j, 0j, .2+0.3j], dtype=np.complex64)
    writer = IQRecorder(path, 2_500_000, 145_500_000)
    writer.submit(x)
    writer.close()
    assert json.loads(metadata_file(path).read_text())['samples'] == len(x)
    reader = IQFileSource(path)
    assert reader.sample_rate == 2_500_000
    assert reader.frequency == 145_500_000
    assert np.array_equal(reader.read(len(x)), x)
    with pytest.raises(EOFError):
        reader.read(10)
    with pytest.raises(RuntimeError):
        reader.tune(145_525_000)
    reader.close()


def test_iq_file_cap_does_not_write_partial_complex(tmp_path):
    path = tmp_path/'cap.cf32'
    iq = (np.arange(200) + 1j*np.arange(200)).astype(np.complex64)
    rec = IQRecorder(path, 48_000, 100_000_000, max_bytes=160)
    rec.submit(iq)
    rec.close()
    assert path.stat().st_size == 160
    assert IQFileSource(path).read(21).size == 20


def test_iq_metadata_required(tmp_path):
    path = tmp_path/'no_meta.cf32'
    path.write_bytes(b'\0'*8)
    with pytest.raises(FileNotFoundError):
        IQFileSource(path)


def test_gui_contains_replay_pbt_fft_and_waterfall_controls():
    src = (Path(__file__).resolve().parents[1]/'sdr_studio'/'app.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Window')
    names = {m.name for m in cls.body if isinstance(m, ast.FunctionDef)}
    assert {'passband_shift_changed','equalizer_changed','toggle_iq_recording',
            'open_iq_replay','update_waterfall_palette','fft_changed','goto_shortcut'} <= names
    for label in ('self.iq_record_btn', 'self.wf_speed', 'self.wf_colors',
                  'self.pbt_shift', 'self.mem_group', 'self.fft_combo'):
        assert label in src
