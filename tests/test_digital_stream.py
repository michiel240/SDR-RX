import json
import sys
import threading
import time
from unittest.mock import patch

import numpy as np
import pytest

from sdr_studio.decoder_catalog import DECODERS
from sdr_studio.digital_stream import (DigitalDecoderWorker, StreamConverter,
                                       parse_decoder_line)


@pytest.mark.parametrize('rate,target,wire', [
    (2_400_000, 250_000, 'cu8'),
    (10_000_000, 288_000, 'cf32'),
    (2_400_000, 2_000_000, 'cu8'),
])
def test_stable_stream_rate_across_blocks(rate,target,wire):
    conv = StreamConverter(rate,target,wire)
    n = 150_000
    x = (0.24 * np.exp(2j*np.pi*2000*np.arange(n)/rate)).astype('complex64')
    raw = conv.convert(x[:65_536]) + conv.convert(x[65_536:131_072]) + conv.convert(x[131_072:])
    bytes_per_sample = 8 if wire == 'cf32' else 2
    # Polyphase stage retains fractional phase in input remainder.
    expected = (n // conv.down) * conv.up
    assert len(raw) == expected * bytes_per_sample
    if wire == 'cu8':
        assert raw and 0 < min(raw) < 255 and 0 < max(raw) < 255
    else:
        a = np.frombuffer(raw, dtype='<f4')
        assert np.isfinite(a).all() and abs(a[0]) <= 1.0


def test_aprs_audio_pcm_stream():
    conv = StreamConverter(2_400_000, 48_000, 'audio16')
    n = 65_536
    samples = (0.25*np.exp(2j*np.pi*1000*np.arange(n)/2_400_000)).astype('complex64')
    raw = conv.convert(samples)
    assert len(raw) > 1_000 and len(raw) % 2 == 0
    assert np.frombuffer(raw, dtype='<i2').dtype.byteorder in ('=', '<')


def test_event_parser_validates_external_lines():
    e = parse_decoder_line('rtl_433 · ISM', json.dumps({'model':'Thermometer','id':42,'temperature_C':21.3}))
    assert e and e.protocol == 'ISM' and 'temperature_C=21.3' in e.detail
    e = parse_decoder_line('AIS-catcher', '!AIVDM,1,1,,A,13aG?P0000,0*76')
    assert e and e.protocol == 'AIS NMEA'
    e = parse_decoder_line('dump1090', '*8D40621D58C382D690C8AC2863A7;')
    assert e and e.protocol == 'Mode S'
    e = parse_decoder_line('Dire Wolf', 'N0CALL>APRS,WIDE1-1:>status')
    assert e and e.protocol == 'APRS/AX.25'
    assert parse_decoder_line('rtl_433', '{malformed') is None
    assert parse_decoder_line('dump1090', 'noise') is None


def test_real_subprocess_pipe_using_synthetic_source():
    """Owns a fake RF source but actually starts and streams to a child process."""
    class FakeSource:
        sample_rate = 2_400_000
        closed = False
        def read(self, n):
            time.sleep(0.018)
            return np.zeros(n, dtype=np.complex64)
        def close(self):
            self.closed = True
    fake = FakeSource()
    ended = threading.Event()
    events, statuses, frames = [], [], []
    child_code = ("import sys\n"
                  "data=sys.stdin.buffer.read(9000)\n"
                  "print('{\\\"model\\\":\\\"Mock sensor\\\",\\\"id\\\":9}',flush=True)\n"
                  "sys.stdin.buffer.read()\n")
    worker = DigitalDecoderWorker(
        profile=DECODERS[0], exe=sys.executable, frequency=433_920_000,
        sample_rate=2_400_000, kind='RTL-SDR', gain=None, device_id=None,
        frame_callback=lambda *x: frames.append(x),
        status_callback=statuses.append, event_callback=events.append,
        ended_callback=ended.set, args_override=['-u', '-c', child_code])
    with patch('sdr_studio.digital_stream.make_source', return_value=fake):
        worker.start()
        deadline = time.monotonic() + 3.0
        while not events and time.monotonic() < deadline:
            time.sleep(0.02)
        worker.stop()
        worker.join(timeout=4)
    assert ended.is_set(), 'worker stopped and signaled GUI'
    assert fake.closed
    assert any(x.protocol == 'ISM' for x in events), statuses
    assert worker.transferred > 0


def test_dsd_neo_audio_modes_and_flags():
    from sdr_studio.decoder_catalog import stream_command
    profiles = [p for p in DECODERS if p.stream == 'voice16']
    assert len(profiles) >= 10
    flags = {p.voice_flag for p in profiles}
    assert {'-fa', '-fs', '-f1', '-f2', '-fi', '-fn', '-fd', '-fy', '-fm', '-fp', '-fz', '-fx'} <= flags
    for p in profiles:
        exe, args, rate = stream_command(p, 145_000_000, 'Airspy R2')
        assert exe == 'dsd-neo' and args[0] == p.voice_flag and rate == 48000
        assert p.voice_channels in (1, 2)


def test_dsd_neo_voice_reader_handles_pcm_binary_without_text_decoding():
    import io
    from unittest.mock import patch
    from sdr_studio.decoder_catalog import Decoder
    class FakeOutput:
        def __init__(self, channels=1):
            self.channels = channels
            self.pcm = []
        def submit(self, a):
            self.pcm.append(a.copy())
    profile = Decoder('DSD-neo · DMR', 'DMR', 'stream', 'dsd-neo',
                      'audio', 'voice16', voice_flag='-fs', voice_channels=2)
    notes = []
    worker = DigitalDecoderWorker(
        profile=profile, exe='unused', frequency=145_000_000,
        sample_rate=2_400_000, kind='Demo (geen hardware)', gain=None, device_id=None,
        frame_callback=lambda *x: None, status_callback=notes.append,
        event_callback=lambda *x: None, ended_callback=lambda: None)
    raw = np.tile(np.array([5000, 0], dtype='<i2'), 400).tobytes()
    with patch('sdr_studio.audio.AudioOutput', FakeOutput):
        worker._voice_reader(io.BytesIO(raw))
    assert worker.voice_bytes == len(raw)
    assert worker.voice_output is not None
    assert worker.voice_output.pcm
    assert max(abs(x).max() for x in worker.voice_output.pcm) > 0
    assert worker.voice_output.channels == 2
    assert worker.voice_output.pcm[0].ndim == 2
    assert worker.voice_output.pcm[0].shape[1] == 2
    assert np.max(np.abs(worker.voice_output.pcm[0][:, 0])) > 0
    assert np.max(np.abs(worker.voice_output.pcm[0][:, 1])) == 0
    assert not notes


@pytest.mark.parametrize('source_rate', [2_400_000, 2_500_000])
def test_dsd_neo_voice16_input_is_real_48khz_pcm(source_rate):
    """Regression: DSD-neo must receive discriminator PCM, not IQ or None.

    This is a synthetic FM transport test, *not* proof of decoding DMR/P25.
    """
    converter = StreamConverter(source_rate, 48_000, 'voice16')
    frames = 65_536
    t = np.arange(frames, dtype=np.float64) / source_rate
    deviation = 2000 * np.sin(2*np.pi*900*t)
    iq = np.exp(1j*2*np.pi*np.cumsum(deviation)/source_rate).astype(np.complex64)
    pcm = converter.convert(iq)
    assert len(pcm) >= 2000 and len(pcm) % 2 == 0
    data = np.frombuffer(pcm, dtype='<i2')
    assert len(data) == pytest.approx(frames * 48_000 / source_rate, abs=3)
    assert np.ptp(data.astype(np.int32)) > 100


def test_dsd_neo_protocol_parser_requires_explicit_sync():
    """An RF peak or a mention of a protocol is not a confirmed frame."""
    assert parse_decoder_line('DSD-neo · Digital Auto', 'possibly DMR detected by FFT') is None
    assert parse_decoder_line('DSD-neo · Digital Auto', 'DMR no sync data') is None
    assert parse_decoder_line('DSD-neo · Digital Auto', 'NXDN sync lost') is None
    event = parse_decoder_line('DSD-neo · Digital Auto', 'DMR sync voice slot 1')
    assert event is not None and event.protocol == 'DMR'


def test_dsd_neo_mono_audio_remains_mono():
    import io
    from sdr_studio.decoder_catalog import Decoder

    class FakeOutput:
        def __init__(self, channels=1):
            self.channels = channels
            self.pcm = []
        def submit(self, a):
            self.pcm.append(a.copy())

    profile = Decoder('DSD-neo · P25 fase I', 'P25', 'stream', 'dsd-neo',
                      'audio', 'voice16', voice_flag='-f1', voice_channels=1)
    worker = DigitalDecoderWorker(
        profile=profile, exe='unused', frequency=145_000_000,
        sample_rate=2_400_000, kind='Demo (geen hardware)', gain=None, device_id=None,
        frame_callback=lambda *x: None, status_callback=lambda *x: None,
        event_callback=lambda *x: None, ended_callback=lambda: None)
    raw = np.full(800, 3000, dtype='<i2').tobytes()
    with patch('sdr_studio.audio.AudioOutput', FakeOutput):
        worker._voice_reader(io.BytesIO(raw))
    assert worker.voice_output.channels == 1
    assert worker.voice_output.pcm[0].ndim == 1
    assert sum(block.shape[0] for block in worker.voice_output.pcm) == 800 * 6
