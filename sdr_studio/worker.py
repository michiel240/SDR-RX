"""Receive thread: sole owner of SDR device, DSP, audio, and WAV writer."""
from __future__ import annotations
import queue
import threading
import time
import wave
import numpy as np

from .devices import make_source
from .dsp import Demodulator, spectrum_dbfs, DEFAULT_BW, valid_bandwidth, MODES
from .scan import ScanConfig, ScanEngine
from .iq_files import IQRecorder, IQFileSource
from .dual_vfo import DualVFOProcessor, VFOChannel, center_and_validate
from .rds import RDSBridge

BLOCK = 65_536


class ReceiverWorker(threading.Thread):
    def __init__(self, kind, frequency, sample_rate, mode, sql, volume, gain,
                 frame_callback, status_callback, ended_callback, device_id=None,
                 tune_callback=None, stereo_vfos=None, rds_executable=None, rds_callback=None):
        super().__init__(daemon=True, name="SDR-receiver")
        self.kind, self.frequency, self.sample_rate = kind, frequency, sample_rate
        self.device_id = device_id
        self.mode, self.sql, self.volume, self.gain = mode, sql, volume, gain
        self.frame_callback = frame_callback
        self.status_callback = status_callback
        self.ended_callback = ended_callback
        self.tune_callback = tune_callback
        self.stop_event = threading.Event()
        self.commands = queue.Queue()
        self.recording = None
        self.audio = None
        self.scan_items = []
        self.scan_cursor = -1
        self.scan_last = 0.0
        self.scan_engine = None
        self.bandwidth_hz = DEFAULT_BW[self.mode]
        self.agc = True
        self.notch_hz = 0
        self.noise_reduction = False
        self.passband_shift_hz = 0
        self.eq_db = (0,0,0)
        self.iq_recorder = None
        self.iq_replay_file = None
        self._fade_in_remaining = 0
        self.fft_size = 8192
        self.stereo_vfos = stereo_vfos
        self.rds_executable = rds_executable
        self.rds_callback = rds_callback or (lambda value: None)
        self.rds_bridge = None

    def _demod(self):
        return Demodulator(self.sample_rate, self.mode,
                           bandwidth_hz=self.bandwidth_hz,
                           agc=self.agc, notch_hz=self.notch_hz,
                           noise_reduction=self.noise_reduction,
                           passband_shift_hz=self.passband_shift_hz, eq_db=self.eq_db)

    def command(self, command, value=None):
        self.commands.put((command, value))

    def _retune(self, src, target, new_mode, new_bw, new_sql, *, reply=None, new_shift=None):
        """Apply a tuning change as one transaction without closing USB/audio.

        Validation and the hardware operation happen *before* publishing state.
        A failed tuner command is reported without ending the receive thread.
        """
        previous = (self.frequency, self.mode, self.bandwidth_hz, self.sql, self.passband_shift_hz)
        try:
            target = int(target)
            new_mode = str(new_mode)
            if new_mode not in MODES:
                raise ValueError(f'Onbekende mode: {new_mode}')
            new_bw = valid_bandwidth(new_mode, int(new_bw))
            new_sql = float(new_sql)
            shift = self.passband_shift_hz if new_shift is None else int(new_shift)
            if abs(shift) > 100_000:
                raise ValueError('Passband shift buiten bereik')
            if not (-120 <= new_sql <= 0):
                raise ValueError('SQL buiten bereik')
            if target != self.frequency and self.iq_recorder:
                self.iq_recorder.close()
                self.status_callback('IQ-opname gestopt bij wijziging middenfrequentie')
                self.iq_recorder = None
            if target != self.frequency:
                src.tune(target)
            self.frequency = target
            self.mode = new_mode
            self.bandwidth_hz = new_bw
            self.sql = new_sql
            self.passband_shift_hz = shift
            if target != previous[0] or new_mode != previous[1] or new_bw != previous[2] or shift != previous[4]:
                if self.audio is not None and hasattr(self.audio, 'flush'):
                    self.audio.flush()
                self._fade_in_remaining = 4_800   # 100 ms at 48 kHz
            if reply is not None:
                self._ack_tune(reply, True, target, '')
            return True
        except Exception as exc:
            self.frequency, self.mode, self.bandwidth_hz, self.sql, self.passband_shift_hz = previous
            self.status_callback(f'Afstemmen mislukt, ontvangst blijft actief: {exc}')
            if reply is not None:
                self._ack_tune(reply, False, previous[0], str(exc))
            return False

    def _ack_tune(self, request, success, actual_frequency, error):
        if self.tune_callback is not None:
            self.tune_callback({'request': dict(request), 'success': success,
                                'frequency_hz': actual_frequency, 'error': error})

    def _fade_audio(self, audio):
        """Briefly fade in after retune to avoid audible pops."""
        left = self._fade_in_remaining
        if left <= 0 or not len(audio):
            return audio
        n = min(len(audio), left)
        pos = 4800 - left
        ramp = np.arange(pos, pos+n, dtype=np.float32)/4800.0
        audio[:n] *= ramp[:, None] if audio.ndim == 2 else ramp
        self._fade_in_remaining -= n
        return audio

    def stop(self):
        self.stop_event.set()

    def run(self):
        src = None
        last_frame = 0.0
        try:
            src = (IQFileSource(self.iq_replay_file) if self.iq_replay_file else
                   make_source(self.kind, self.frequency, self.sample_rate, self.gain, self.device_id))
            if self.iq_replay_file:
                self.frequency = src.frequency
            started = time.monotonic()
            last_samples_at = started
            last_statistics_at = started
            total_samples = 0
            statistics_samples = 0
            warned_overload = False
            self.sample_rate = int(src.sample_rate)
            dual = None
            if self.stereo_vfos:
                a, b = (VFOChannel(**entry) for entry in self.stereo_vfos)
                center = center_and_validate(a,b,self.sample_rate)
                if center != self.frequency:
                    src.tune(center)
                    self.frequency = center
                dual = DualVFOProcessor(self.sample_rate,a,b,agc=self.agc,
                                        notch_hz=self.notch_hz,
                                        noise_reduction=self.noise_reduction,eq_db=self.eq_db)
                dsp = None
                self.status_callback(f'Stereo RX: A {a.frequency_hz/1e6:.6f} MHz links; '
                                     f'B {b.frequency_hz/1e6:.6f} MHz rechts; '
                                     f'midden {center/1e6:.6f} MHz')
            else:
                dsp = self._demod()
            self.status_callback(f"Ontvanger actief: {self.kind}, {self.sample_rate/1e6:g} MSPS")
            try:
                from .audio import AudioOutput
                self.audio = AudioOutput(channels=2 if dual else 1)
            except Exception as exc:
                self.status_callback(f"SDR werkt, maar geen geluid: {exc}")
            while not self.stop_event.is_set():
                while True:
                    try:
                        kind, value = self.commands.get_nowait()
                    except queue.Empty:
                        break
                    if dual is not None and kind in ('vfo','frequency','mode','bandwidth','scan','passband_shift','agc','notch','noise_reduction','equalizer'):
                        self.status_callback('Stereo A/B actief: stop ontvangst om de afstemming te wijzigen.')
                        continue
                    if kind == 'rds':
                        if self.rds_bridge:
                            self.rds_bridge.close()
                            self.rds_bridge = None
                        self.rds_executable = str(value) if value else None
                        if self.rds_executable and not dual and self.mode == 'WFM':
                            try:
                                self.rds_bridge = RDSBridge(self.rds_executable,
                                    dsp.if_rate,self.rds_callback,self.status_callback).start()
                                self.status_callback('RDS: externe redsea-decoder gestart (WFM multiplex)')
                            except (OSError,ValueError) as exc:
                                self.status_callback(f'RDS niet gestart: {exc}')
                        elif self.rds_executable:
                            self.status_callback('RDS werkt alleen bij WFM met enkele VFO.')
                    elif kind == 'vfo':
                        request = dict(value)
                        self.scan_engine = None
                        if self._retune(src, request['frequency_hz'], request['mode'],
                                        request['bandwidth_hz'], request['squelch_dbfs'],
                                        reply=request, new_shift=request.get('passband_shift_hz', 0)):
                            dsp = self._demod()  # rebuild once, not three times
                    elif kind == 'frequency':
                        if self.rds_bridge:
                            self.rds_bridge.status = self.rds_bridge.status.__class__()
                        self.scan_engine = None  # Explicit tuning cancels scanning.
                        if self._retune(src, value, self.mode, self.bandwidth_hz, self.sql):
                            dsp = self._demod()
                    elif kind == 'mode':
                        self.mode = value
                        dsp = self._demod()
                        if self.rds_bridge and self.mode != 'WFM':
                            self.rds_bridge.close()
                            self.rds_bridge = None
                    elif kind == 'gain':
                        try:
                            src.set_gain(value)
                        except Exception as exc:
                            self.status_callback(f'Gain-instelling niet ondersteund: {exc}')
                    elif kind == 'bandwidth':
                        self.bandwidth_hz = int(value)
                        dsp = self._demod()
                    elif kind == 'agc':
                        self.agc = bool(value)
                        dsp = self._demod() if not dual else dsp
                        if dual:dual.left.agc=dual.right.agc=bool(value)
                    elif kind == 'notch':
                        self.notch_hz = int(value)
                        dsp = self._demod()
                    elif kind == 'noise_reduction':
                        self.noise_reduction = bool(value)
                        dsp = self._demod()
                    elif kind == 'passband_shift':
                        self.passband_shift_hz = max(-100_000, min(100_000, int(value)))
                        dsp = self._demod()
                    elif kind == 'equalizer':
                        gains = tuple(int(v) for v in value)
                        if len(gains) == 3 and all(-12 <= v <= 12 for v in gains):
                            self.eq_db = gains
                            dsp = self._demod()
                    elif kind == 'fft_size':
                        if int(value) in (2048,4096,8192,16384):
                            self.fft_size = int(value)
                    elif kind == 'iq_record':
                        if self.iq_recorder:
                            self.iq_recorder.close()
                            self.status_callback(f'IQ-opname gestopt: {self.iq_recorder.samples_written:,} samples; drops={self.iq_recorder.dropped_samples:,}')
                            self.iq_recorder = None
                        if value:
                            self.iq_recorder = IQRecorder(value, self.sample_rate, self.frequency)
                            self.status_callback(f'IQ-opname gestart: {value}')
                    elif kind == 'scan':
                        if value and self.iq_replay_file:
                            self.status_callback('Scanner niet beschikbaar tijdens IQ-replay')
                            continue
                        if value and self.iq_recorder:
                            self.iq_recorder.close()
                            self.iq_recorder = None
                            self.status_callback('IQ-opname gestopt: scanner gestart')
                        if value:
                            if isinstance(value, dict):
                                items = value.get('items', [])
                                dwell = int(value.get('dwell_ms', 700))
                                hold = int(value.get('hold_ms', 1800))
                            else:
                                items, dwell, hold = value, 700, 1800
                            config = ScanConfig(tuple(items), dwell, hold)
                            self.scan_engine = ScanEngine(config)
                            self.status_callback(f'Scanner gestart: {len(items)} kanalen (dwell {dwell} ms, hold {hold} ms)')
                        else:
                            self.scan_engine = None
                            self.status_callback('Scanner gestopt')
                    elif kind == 'squelch':
                        self.sql = float(value)
                    elif kind == 'volume':
                        self.volume = float(value)
                    elif kind == 'record':
                        if self.recording:
                            self.recording.close()
                            self.recording = None
                        if value:
                            writer = wave.open(str(value), 'wb')
                            writer.setnchannels(2 if dual else 1)
                            writer.setsampwidth(2)
                            writer.setframerate(48_000)
                            self.recording = writer
                            self.status_callback(f"Opname gestart: {value}")
                        else:
                            self.status_callback('Opname gestopt')
                iq = src.read(BLOCK)
                if len(iq) < 1000:
                    if time.monotonic() - last_samples_at > 6:
                        raise RuntimeError('Geen IQ-data ontvangen gedurende 6 seconden. Controleer de USB-verbinding.')
                    continue
                last_samples_at = time.monotonic()
                total_samples += len(iq)
                if self.iq_recorder:
                    self.iq_recorder.submit(iq)
                    if self.iq_recorder.limit_reached or self.iq_recorder.error:
                        self.status_callback("IQ-opname gestopt: bestandlimiet of schrijffout")
                        self.iq_recorder.close()
                        self.iq_recorder = None
                statistics_samples += len(iq)
                if last_samples_at - last_statistics_at >= 2.5:
                    elapsed = last_samples_at - last_statistics_at
                    throughput = statistics_samples / elapsed
                    drop = getattr(src, 'dropped', None)
                    suffix = (f'; Airspy USB drops={drop[0]}, wachtrij drops={drop[1]}'
                              if drop is not None else '')
                    if drop is not None and drop[1] and not warned_overload:
                        self.status_callback('LET OP: Airspy-wachtrij loopt over. Probeer 2,5 MSPS voor stabieler geluid.')
                        warned_overload = True
                    self.status_callback(f'IQ ontvangen: {total_samples:,} samples; '
                                         f'{throughput/1e6:.2f} MSPS gemeten{suffix}')
                    statistics_samples = 0
                    last_statistics_at = last_samples_at
                audio, level = dual.process(iq) if dual else dsp.process(iq)
                if self.rds_bridge and dsp and dsp.last_mpx is not None:
                    self.rds_bridge.submit(dsp.last_mpx)
                retuned_scan = False
                if self.scan_engine:
                    item = self.scan_engine.update(time.monotonic(), level >= self.sql)
                    if item is not None:
                        target = int(item['frequency'])
                        next_mode = item.get('mode', self.mode)
                        if target != self.frequency:
                            if self.iq_recorder:
                                self.iq_recorder.close()
                                self.iq_recorder = None
                                self.status_callback('IQ-opname gestopt: scanner heeft afgestemd')
                            src.tune(target)
                            self.frequency = target
                            retuned_scan = True
                        if next_mode != self.mode:
                            self.mode = next_mode
                            self.bandwidth_hz = DEFAULT_BW.get(self.mode, 12_500)
                        dsp = self._demod()
                        self.status_callback(f'Scanner: {self.frequency/1e6:.6f} MHz · {self.mode}')
                if not dual and level < self.sql:
                    audio[:] = 0
                audio *= self.volume
                self._fade_audio(audio)
                if self.audio:
                    self.audio.submit(audio)
                if self.recording:
                    pcm = (np.clip(audio, -1, 1) * 32767).astype('<i2')
                    self.recording.writeframesraw(pcm.tobytes())
                now = time.monotonic()
                # A lower draw rate reduces CPU pressure on 10-MSPS Airspy
                # while keeping the same FFT resolution and DSP audio rate.
                display_interval = .16 if self.sample_rate >= 5_000_000 else .085
                if now - last_frame > display_interval and not retuned_scan:
                    self.frame_callback(spectrum_dbfs(iq, fft_size=self.fft_size), self.frequency,
                                        self.sample_rate, level)
                    last_frame = now
                if self.kind.startswith('Demo'):
                    time.sleep(len(iq) / self.sample_rate)  # real-time simulation
        except EOFError as exc:
            self.status_callback(f'IQ-replay voltooid: {exc}')
        except Exception as exc:
            self.status_callback(f"FOUT: {type(exc).__name__}: {exc}")
        finally:
            if self.rds_bridge:
                self.rds_bridge.close()
            if self.iq_recorder:
                try:
                    self.iq_recorder.close()
                except Exception as exc:
                    self.status_callback(f"IQ-opname sluiten: {exc}")
            if self.recording:
                self.recording.close()
            if self.audio:
                try:
                    self.audio.close()
                except Exception:
                    pass
            if src:
                try:
                    src.close()
                except Exception as exc:
                    self.status_callback(f"Sluiten ontvanger: {exc}")
            self.ended_callback()
