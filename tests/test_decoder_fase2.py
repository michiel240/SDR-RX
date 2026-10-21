"""Decoder-phase 2 compatibility tests. No USB hardware or external binaries needed."""
import json
from pathlib import Path

import numpy as np
import pytest

from sdr_studio.decoder_catalog import DECODERS, decoder_template, stream_command, decoder_description
from sdr_studio.digital_stream import StreamConverter, parse_decoder_line


def find(name):
    return next(p for p in DECODERS if name in p.label)


@pytest.mark.parametrize('name,formats', [
    ('multimon-ng · POCSAG', {'POCSAG512', 'POCSAG1200', 'POCSAG2400'}),
    ('multimon-ng · FLEX', {'FLEX', 'FLEX_NEXT'}),
])
def test_pager_modes_use_real_22050_pcm_stdin(name, formats):
    profile = find(name)
    exe, args, rate = stream_command(profile, 169_650_000, 'RTL-SDR')
    assert (exe, rate) == ('multimon-ng', 22050)
    assert args[:2] == ['-t', 'raw']
    assert args[-1] == '-'
    assert all(v in args for v in formats)
    assert profile.stream == 'audio16'


@pytest.mark.parametrize('rate', [2_400_000, 2_500_000, 10_000_000])
def test_multimon_pcm_resampled_across_blocks(rate):
    converter = StreamConverter(rate, 22_050, 'audio16')
    n = 4 * 65536
    pieces = []
    for i in range(0, n, 65536):
        t = np.arange(i, i + 65536, dtype=np.float64)/rate
        iq = np.exp(1j*2*np.pi*1100*t).astype(np.complex64)
        pieces.append(converter.convert(iq))
    payload = b''.join(pieces)
    values = np.frombuffer(payload, dtype='<i2')
    assert values.size > 100
    # The converter retains <320 of the 48-kHz samples for the next SDR
    # block, i.e. <147 as-yet-unemitted samples at 22.05 kHz.
    assert abs(values.size - n * 22050/rate) < 150
    assert 0 <= len(converter.audio_remainder) < 320
    assert len(payload) % 2 == 0
    assert np.max(np.abs(values)) > 100
    assert np.all(np.isfinite(values))


def test_existing_aprs_pcm_remains_at_48000():
    p = find('Dire Wolf')
    _, args, rate = stream_command(p, 144_800_000, 'RTL-SDR')
    assert rate == 48000
    assert args[-1] == '-'
    assert StreamConverter(2_400_000, rate, 'audio16').target_rate == 48000


@pytest.mark.parametrize('source,expected', [
    ('RTL-SDR', '-o 4 -r 0 131.525'),
    ('Airspy R2', '-o 4 -s 0 131.525'),
    ('Demo (geen hardware)', ''),
])
def test_acars_dec_owns_its_radio(source, expected):
    p = find('ACARS ·')
    assert p.approach == 'external-rtl' and not p.stream
    assert decoder_template(p, 131_525_000, source) == ('acarsdec', expected)
    assert 'eigen' in decoder_description(p, source).lower()
    assert p.preset_hz == 131_525_000


def test_pager_parser_reports_real_lines_only():
    result = parse_decoder_line('multimon-ng · POCSAG', 'POCSAG1200: Address: 21323 Function: 1 Alpha: test')
    assert result and result.protocol == 'POCSAG1200' and result.identifier == '21323'
    result = parse_decoder_line('multimon-ng · FLEX', 'FLEX: Capcode: 123456 message text')
    assert result and result.protocol == 'FLEX' and result.identifier == '123456'
    assert parse_decoder_line('multimon-ng · POCSAG', 'POCSAG1200:') is None
    assert parse_decoder_line('multimon-ng · FLEX', 'RSSI -63 signal') is None


def test_acars_json_parser_requires_decoder_message_fields():
    data = json.dumps({'label': 'H1', 'flight': 'KL1234', 'text': 'TEST'})
    result = parse_decoder_line('ACARS · vliegtuigberichten', data)
    assert result and result.protocol == 'ACARS' and 'KL1234' in result.detail
    assert parse_decoder_line('ACARS', '{"status":"starting"}') is None
    assert parse_decoder_line('ACARS', '{bad') is None


def test_manual_decoder_modes_not_falsely_claimed_as_integrated():
    for word in ('FT8', 'RTTY', 'SSTV', 'NOAA APT', 'VDL Mode 2', 'DAB', 'TETRA'):
        p = find(word)
        assert not p.stream, p.label
        assert 'geen live IQ-koppeling' in decoder_description(p, 'RTL-SDR') or 'geen automatische audio-overdracht' in decoder_description(p, 'RTL-SDR')


def test_gui_supports_external_audio_and_parses_text_output():
    gui = (Path(__file__).resolve().parents[1] / 'sdr_studio' / 'app.py').read_text(encoding='utf-8')
    assert "profile.approach != 'audio/iq'" in gui
    assert 'parse_decoder_line(self._active_external_decoder, line)' in gui
    assert 'self.decoder_project_btn' in gui


def test_dsds_links_go_to_actual_runtime():
    profiles = [x for x in DECODERS if 'DSD-neo' in x.label]
    assert len(profiles) >= 10
    assert all('arancormonk/dsd-neo/releases' in x.link for x in profiles)


def test_multimon_live_process_gets_pcm_and_raises_pocsag_event():
    """End-to-end IPC on a fake decoder, not a real POCSAG RF decode."""
    import sys
    import threading
    import time
    from unittest.mock import patch
    from sdr_studio.digital_stream import DigitalDecoderWorker

    class FakeRF:
        sample_rate = 2_400_000
        def __init__(self):
            self.closed = False
        def read(self, length):
            time.sleep(0.018)
            return np.zeros(length, dtype=np.complex64)
        def close(self):
            self.closed = True

    fake = FakeRF()
    done = threading.Event()
    received = []
    source = ("import sys\n"
              "x=sys.stdin.buffer.read(4000)\n"
              "if len(x)==4000: print('POCSAG1200: Address: 42424 Function: 1 Alpha: TEST', flush=True)\n"
              "sys.stdin.buffer.read()\n")
    worker = DigitalDecoderWorker(
        profile=find('multimon-ng · POCSAG'), exe=sys.executable,
        frequency=169_650_000, sample_rate=2_400_000,
        kind='Demo (geen hardware)', gain=None, device_id=None,
        frame_callback=lambda *args: None, status_callback=lambda *args: None,
        event_callback=received.append, ended_callback=done.set,
        args_override=['-u', '-c', source])
    with patch('sdr_studio.digital_stream.make_source', return_value=fake):
        worker.start()
        deadline = time.monotonic() + 4
        while not received and time.monotonic() < deadline:
            time.sleep(.03)
        worker.stop()
        worker.join(timeout=3)
    assert done.is_set() and fake.closed
    assert received and received[0].protocol == 'POCSAG1200'
    assert worker.transferred >= 4000
