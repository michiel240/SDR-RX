"""Live receive-only IQ/PCM bridge to independent decoder executables.

No third-party binaries are redistributed or imported. One SDR source is owned
by this thread, and one supervised child process receives a bounded stream.
No keys, decryptors, transmitters, or network listeners are configured here.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass

import numpy as np
from scipy import signal

from .decoder_catalog import Decoder, stream_command
from .dsp import Demodulator, spectrum_dbfs
from .devices import make_source

BLOCK = 65_536
MAX_OUTPUT_LINE = 8_192


class StreamConverter:
    """Resample IQ and convert to the decoder's wire format.

    Keeps the polyphase alignment across read blocks. FIR edge transients at
    boundaries remain; these modes require real-world sensitivity validation.
    """

    def __init__(self, source_rate: int, target_rate: int, output_format: str):
        self.source_rate = int(source_rate)
        self.target_rate = int(target_rate)
        self.output_format = output_format
        if min(self.source_rate, self.target_rate) <= 0:
            raise ValueError('Ongeldige sample-rate')
        gcd = math.gcd(self.source_rate, self.target_rate)
        self.up = self.target_rate // gcd
        self.down = self.source_rate // gcd
        self.remainder = np.empty(0, dtype=np.complex64)
        self.audio_remainder = np.empty(0, dtype=np.float32)
        # Both APRS (audio16) and DSD-neo (voice16) consume NFM discriminator
        # PCM, not raw complex IQ. Previously voice16 left this as None and
        # crashed at the first convert() call (AttributeError).
        # Decoder input should not be volume-pumped by the speaker AGC.
        self.demodulator = (Demodulator(self.source_rate, 'NFM', agc=False)
                            if output_format in ('audio16', 'voice16') else None)

    def convert(self, iq: np.ndarray) -> bytes:
        iq = np.asarray(iq, dtype=np.complex64)
        if self.output_format in ('audio16', 'voice16'):
            # Dire Wolf receives discriminator audio at 48 kHz, not IQ.
            mono, _level = self.demodulator.process(iq)
            if self.target_rate != 48_000:
                # FM demodulator emits 48 kHz; e.g. multimon-ng expects
                # 22.05 kHz raw PCM. Keep an integral resampling boundary
                # across SDR blocks to avoid duration drift.
                divisor = 48_000 // math.gcd(48_000, self.target_rate)
                mono = np.concatenate((self.audio_remainder, mono))
                complete = (len(mono) // divisor) * divisor
                self.audio_remainder = mono[complete:].copy()
                if complete == 0:
                    return b''
                mono = signal.resample_poly(mono[:complete],
                                            self.target_rate // math.gcd(48_000, self.target_rate),
                                            divisor)
            return (np.clip(mono, -1, 1) * 32767).astype('<i2').tobytes()
        if len(self.remainder):
            iq = np.concatenate((self.remainder, iq))
        count = (len(iq) // self.down) * self.down
        if count == 0:
            self.remainder = iq.copy()
            return b''
        self.remainder = iq[count:].copy()
        output = signal.resample_poly(iq[:count], self.up, self.down)
        if self.output_format == 'cf32':
            result = np.empty(len(output) * 2, dtype='<f4')
            result[0::2] = output.real
            result[1::2] = output.imag
            return result.tobytes()
        if self.output_format == 'cu8':
            # Typical rtl-sdr CU8 encoding: unsigned interleaved IQ, 127.5 bias.
            result = np.empty(len(output) * 2, dtype=np.uint8)
            result[0::2] = np.clip(output.real * 127.5 + 127.5, 0, 255).astype(np.uint8)
            result[1::2] = np.clip(output.imag * 127.5 + 127.5, 0, 255).astype(np.uint8)
            return result.tobytes()
        raise ValueError('Onbekend sampleformaat: ' + self.output_format)


@dataclass(frozen=True)
class DecoderEvent:
    protocol: str
    identifier: str
    detail: str
    raw: str


def _ais_details(nmea: str):
    """Read unencrypted AIS header fields, never infer a vessel position.

    Returns message type/MMSI if payload has at least 38 bits. Include
    checksum warning without concealing third-party decoder output.
    """
    fields = nmea.split(',')
    if len(fields) < 7:
        return 'NMEA onvolledig', 'AIS frame'
    payload = fields[5]
    bits = ''.join(format((ord(c)-48) - (8 if ord(c)-48 > 40 else 0), '06b')
                   for c in payload if 48 <= ord(c) <= 119)
    if len(bits) < 38:
        return 'AIS payload te kort', 'AIS frame'
    msgtype = int(bits[0:6],2)
    mmsi = int(bits[8:38],2)
    checksum = ''
    if '*' in nmea:
        body, given = nmea[1:].split('*',1)
        check = 0
        for char in body:
            check ^= ord(char)
        if given[:2].upper() != f'{check:02X}':
            checksum = ' · checksum ongeldig'
    return f'Type {msgtype} · MMSI {mmsi:09d}{checksum}', f'MMSI {mmsi:09d}'


def _modes_details(frame):
    raw = bytes.fromhex(frame.strip('*;'))
    df = raw[0] >> 3
    if df not in (11,17,18):
        return f'DF {df}', 'Mode S'
    icao = raw[1:4].hex().upper()
    description = f'DF {df} · ICAO {icao}'
    if df in (17,18) and len(raw) == 14:
        typecode = raw[4] >> 3
        description += f' · TC {typecode}'
        if 1 <= typecode <= 4:
            chars = []
            value = int.from_bytes(raw[5:11], 'big')
            for shift in range(42, -1, -6):
                ch = (value >> shift) & 0x3f
                if 1 <= ch <= 26:
                    chars.append(chr(64+ch))
                elif 48 <= ch <= 57:
                    chars.append(chr(ch))
                elif ch == 32:
                    chars.append(' ')
                else:
                    chars.append('')
            name = ''.join(chars).strip()
            if name:
                description += ' · vlucht ' + name
    return description, icao


def parse_decoder_line(mode: str, line: str) -> DecoderEvent | None:
    """Display parser only; does not claim a valid decoded frame from text alone."""
    value = line.strip()
    if not value:
        return None
    if 'rtl_433' in mode and value.startswith('{'):
        try:
            data = json.loads(value)
        except (ValueError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        source = str(data.get('model') or data.get('type') or 'Sensor')[:50]
        key = str(data.get('id', data.get('channel', '—')))[:50]
        detail = ', '.join(f'{k}={v}' for k, v in data.items()
                           if k not in ('model', 'type', 'id', 'channel'))[:240]
        return DecoderEvent('ISM', f'{source} / {key}', detail, value)
    if 'AIS-catcher' in mode and (value.startswith('!AIVDM,') or value.startswith('!AIVDO,')):
        info, ident = _ais_details(value)
        return DecoderEvent('AIS NMEA', ident, info + ' · ' + value[:150], value)
    if 'dump1090' in mode and re.fullmatch(r'\*[0-9A-Fa-f]{14}(?:[0-9A-Fa-f]{14})?;', value):
        # Decoding of aircraft identity/position is a separate step.
        info, ident = _modes_details(value)
        return DecoderEvent('Mode S', ident, info, value)
    if 'multimon-ng' in mode:
        match = re.match(r'^(POCSAG(?:512|1200|2400)?|FLEX(?:_NEXT)?)(?:\s*[:\-]\s*|\s+)(.+)$', value, re.I)
        if match and len(match.group(2).strip()) >= 3:
            content = match.group(2).strip()
            address = re.search(r'\b(?:Address|Capcode|RIC|CAP)\s*[:=]\s*(\d+)', content, re.I)
            ident = address.group(1) if address else match.group(1).upper()
            return DecoderEvent(match.group(1).upper(), ident, content[:240], value)
    if 'ACARS' in mode and value.startswith('{'):
        try:
            data = json.loads(value)
        except (TypeError, ValueError):
            return None
        if isinstance(data, dict) and ('label' in data or 'flight' in data) and any(
                key in data for key in ('text', 'msg', 'flight', 'tail')):
            ident = str(data.get('flight') or data.get('tail') or data.get('label') or '?')[:40]
            detail = ' · '.join(f'{k}: {data[k]}' for k in ('label', 'flight', 'tail', 'text', 'msg')
                                if k in data and data[k] is not None)
            return DecoderEvent('ACARS', ident, detail[:240], value)
    if 'Dire Wolf' in mode and ('>' in value and ':' in value):
        return DecoderEvent('APRS/AX.25', value.split('>', 1)[0][:35], value[:240], value)
    if 'DSD-neo' in mode:
        # Report only what the *actual external decoder* explicitly writes.
        # Mere energy or a spectral pattern cannot prove DMR/P25/etc.
        proto = re.search(r'(?<![A-Za-z0-9])(P25(?:[ -]?(?:I{1,2}|1|2))?|DMR|NXDN|D-STAR|YSF|dPMR|M17|ProVoice|X2-TDMA)(?![A-Za-z0-9])',value,re.I)
        evidence = re.search(r'\b(sync(?:ed)?|voice|data|frame|slot|ts[12]|call|nac|ran|cc=)\b',value,re.I)
        # Do not turn explicitly *failed* synchronization into a positive event.
        # Positive log lines still come only from the external decoder.
        sync_failed = re.search(
            r'\b(?:no|lost|without|failed|not)\s+(?:\w+\s+){0,2}sync\b'
            r'|\bsync\s+(?:lost|failed|not\s+found)\b|\bunsynced?\b',
            value, re.I)
        if proto and evidence and not sync_failed:
            return DecoderEvent(proto.group(1).upper(),'DSD-neo AUTO',value[:240],value)
    return None


class DigitalDecoderWorker(threading.Thread):
    """Single owner of the selected SDR while a decoder reads its data.

    A bounded writer queue prevents a blocked child process from accumulating
    unlimited RAM. The status reports discarded blocks when a decoder cannot
    keep up with a 2.4/10 MSPS Airspy or RTL stream.
    """
    def __init__(self, *, profile: Decoder, exe: str, frequency: int, sample_rate: int,
                 kind: str, gain: float | None, device_id: int | None,
                 frame_callback, status_callback, event_callback, ended_callback,
                 line_callback=None,
                 args_override: list[str] | None = None):
        super().__init__(daemon=True, name='SDR-digital-decoder')
        self.profile, self.exe, self.kind = profile, str(exe), str(kind)
        self.frequency, self.sample_rate = int(frequency), int(sample_rate)
        self.gain, self.device_id = gain, device_id
        self.frame_callback = frame_callback
        self.status_callback = status_callback
        self.event_callback = event_callback
        self.line_callback = line_callback or (lambda text: None)
        self.ended_callback = ended_callback
        self.stop_event = threading.Event()
        self.pipe_queue = queue.Queue(maxsize=8)
        self.args_override = args_override
        self.process = None
        self.dropped_blocks = 0
        self.transferred = 0
        self.voice_output = None
        self.voice_bytes = 0

    def stop(self):
        self.stop_event.set()
        # Stop the child first to unblock pipe writes, if present.
        child = self.process
        if child and child.poll() is None:
            try:
                child.terminate()
            except OSError:
                pass

    def _writer(self):
        while not self.stop_event.is_set():
            try:
                chunk = self.pipe_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if chunk is None:
                break
            try:
                if self.process is None or self.process.stdin is None:
                    break
                self.process.stdin.write(chunk)
                self.transferred += len(chunk)
            except (BrokenPipeError, OSError, ValueError):
                self.stop_event.set()
                break

    def _reader(self, stream, parse_events: bool):
        # Binary reads avoid decoding failure on non-UTF8 tool output.
        try:
            for raw in iter(stream.readline, b''):
                if self.stop_event.is_set():
                    break
                line = raw[:MAX_OUTPUT_LINE].decode('utf-8', 'replace').strip()
                if not line:
                    continue
                if parse_events:
                    self.line_callback(line[:400])
                    event = parse_decoder_line(self.profile.label, line)
                    if event:
                        self.event_callback(event)
                    elif line.startswith(('[ERROR]', 'ERROR', 'FATAL')):
                        self.status_callback(line[:350])
                elif any(x in line.lower() for x in ('error', 'device', 'opened', 'sample')):
                    self.status_callback('Decoder: ' + line[:300])
        except (OSError, ValueError):
            pass

    def _voice_reader(self, stdout):
        # DSD-neo publishes signed little-endian 8-kHz audio on stdout.
        # Never decode that binary pipe as text or print it in the GUI.
        channels = self.profile.voice_channels
        try:
            from .audio import AudioOutput
            # DMR/P25 can carry independent left/right slots. Do not mix
            # stereo down to mono before playback; preserve the channel map.
            self.voice_output = AudioOutput(channels=channels)
        except Exception as exc:
            self.status_callback(f'Decoder draait, maar spraakuitgang ontbreekt: {exc}')
        pending = b''
        chunk_bytes = 160 * 2 * channels
        try:
            while not self.stop_event.is_set():
                chunk = stdout.read(chunk_bytes)
                if not chunk:
                    break
                pending += chunk
                aligned = len(pending) - (len(pending) % (2 * channels))
                if aligned <= 0:
                    continue
                data = np.frombuffer(pending[:aligned], dtype='<i2').astype(np.float32) / 32768.0
                pending = pending[aligned:]
                if channels == 2:
                    data = data.reshape(-1, 2)
                # Stereo remains (frames,2); mono remains (frames,). DSD-neo
                # emits digital voice at 8 kHz, while AudioOutput uses 48 kHz.
                audio = signal.resample_poly(data, 6, 1, axis=0).astype(np.float32)
                self.voice_bytes += len(chunk)
                if self.voice_output:
                    self.voice_output.submit(audio)
        except (OSError, ValueError) as exc:
            self.status_callback(f'Decoder-spraakuitgang: {exc}')

    def run(self):
        source = None
        child = None
        readers = []
        writer = None
        try:
            _prog, args, target_rate = stream_command(self.profile, self.frequency, self.kind)
            if self.args_override is not None:
                args = list(self.args_override)
            source = make_source(self.kind, self.frequency, self.sample_rate,
                                 self.gain, self.device_id)
            converter = StreamConverter(int(source.sample_rate), target_rate, self.profile.stream)
            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
            child = subprocess.Popen([self.exe, *args], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     bufsize=0, creationflags=creationflags,
                                     cwd=str(Path(self.exe).resolve().parent) if Path(self.exe).is_file() else None)
            self.process = child
            writer = threading.Thread(target=self._writer, daemon=True, name='decoder-stdin')
            writer.start()
            streams = ([(child.stdout, self._voice_reader, ())] if self.profile.stream == 'voice16'
                       else [(child.stdout, self._reader, (True,))])
            streams.append((child.stderr, self._reader, (True,)))
            for stream, method, extras in streams:
                thread = threading.Thread(target=method, args=(stream, *extras), daemon=True)
                thread.start()
                readers.append(thread)
            self.status_callback(f'Digitale IQ-bridge gestart: {self.profile.label}; '
                                 f'{source.sample_rate} → {target_rate} samples/s; '
                                 f'{self.profile.stream.upper()}')
            last_frame = last_stats = time.monotonic()
            total = 0
            while not self.stop_event.is_set():
                if child.poll() is not None:
                    raise RuntimeError(f'Externe decoder gestopt (exit {child.returncode})')
                iq = source.read(BLOCK)
                if len(iq) == 0:
                    time.sleep(0.005)
                    continue
                total += len(iq)
                payload = converter.convert(iq)
                if payload:
                    try:
                        self.pipe_queue.put_nowait(payload)
                    except queue.Full:
                        self.dropped_blocks += 1
                now = time.monotonic()
                if now - last_frame >= 0.15:
                    # Qt signal marshals the numpy array back to the GUI thread.
                    amplitude = 20 * np.log10(np.sqrt(np.mean(np.abs(iq)**2)) + 1e-12)
                    self.frame_callback(spectrum_dbfs(iq), self.frequency, source.sample_rate,
                                        float(amplitude))
                    last_frame = now
                if now - last_stats >= 3:
                    self.status_callback(f'Digitale stream: {total:,} IQ-samples; '
                                         f'{self.transferred:,} bytes naar decoder; '
                                         f'overloop={self.dropped_blocks} blokken' +
                                         (f'; spraakbytes={self.voice_bytes:,}' if self.profile.stream == 'voice16' else ''))
                    last_stats = now
                if self.kind.startswith('Demo'):
                    time.sleep(len(iq)/source.sample_rate)
        except Exception as exc:
            self.status_callback(f'FOUT digitale decoder: {type(exc).__name__}: {exc}')
        finally:
            self.stop_event.set()
            if child and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=1.0)
            if child:
                for stream in (child.stdin, child.stdout, child.stderr):
                    if stream:
                        try:
                            stream.close()
                        except (OSError, ValueError):
                            pass
            if self.voice_output is not None:
                try:
                    self.voice_output.close()
                except Exception:
                    pass
            if source is not None:
                try:
                    source.close()
                except Exception as exc:
                    self.status_callback(f'Ontvanger sluiten: {exc}')
            self.ended_callback()
