"""Explicit, versioned IQ capture/replay in interleaved float32 I/Q (CF32LE).

Raw .cf32 files are accompanied by .json with sample-rate, center frequency,
recorded/dropped samples and format. This module does not open radio hardware.
"""
from __future__ import annotations
import json
import queue
import threading
import time
from pathlib import Path
import numpy as np

FORMAT = 'CF32LE'
MAX_BYTES = 2 * 1024**3


def metadata_file(path):
    return Path(path).with_suffix('.json')


class IQRecorder:
    """Asynchronous bounded writer: never block USB receiver on filesystem I/O."""
    def __init__(self, path, sample_rate, center_hz, max_bytes=MAX_BYTES):
        self.path = Path(path)
        if self.path.suffix.lower() != '.cf32':
            raise ValueError('Gebruik .cf32 voor IQ-opname')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.sample_rate, self.center_hz = int(sample_rate), int(center_hz)
        self.max_bytes = int(max_bytes)
        if self.sample_rate <= 0 or self.max_bytes < 8:
            raise ValueError('Ongeldige IQ-opname instellingen')
        self.queue = queue.Queue(maxsize=12)
        self.samples_written = 0
        self.dropped_samples = 0
        self.error = None
        self.limit_reached = False
        self._closed = False
        self._handle = self.path.open('xb')
        self._thread = threading.Thread(target=self._writer, daemon=True, name='IQ-file-writer')
        self._thread.start()

    def submit(self, samples):
        if self._closed or self.limit_reached:
            return
        data = np.asarray(samples, dtype=np.complex64).astype('<c8', copy=False).tobytes()
        try:
            self.queue.put_nowait(data)
        except queue.Full:
            self.dropped_samples += len(data) // 8

    def _writer(self):
        try:
            while True:
                data = self.queue.get()
                if data is None:
                    break
                remaining = self.max_bytes - self.samples_written*8
                if remaining < len(data):
                    data = data[:max(0, remaining - remaining%8)]
                    self.limit_reached = True
                if data:
                    self._handle.write(data)
                    self.samples_written += len(data)//8
                if self.limit_reached:
                    # Continue draining queued blocks so close() cannot deadlock.
                    continue
        except OSError as exc:
            self.error = str(exc)
        finally:
            self._handle.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        # The receive thread is stopped before close() or otherwise this
        # producer must stop submitting. A queue drain here is bounded.
        self.queue.put(None)
        self._thread.join(timeout=15)
        if self._thread.is_alive():
            raise RuntimeError('IQ-schrijver kon niet netjes stoppen')
        data = dict(format=FORMAT, sample_rate=self.sample_rate,
                    center_hz=self.center_hz, samples=self.samples_written,
                    dropped_samples=self.dropped_samples,
                    complete=self.error is None, error=self.error)
        metadata_file(self.path).write_text(json.dumps(data, indent=2), encoding='utf-8')


class IQFileSource:
    """Replay a CF32LE recording in bounded blocks with original sample rate."""
    def __init__(self, path):
        self.path = Path(path)
        info = json.loads(metadata_file(self.path).read_text(encoding='utf-8'))
        if info.get('format') != FORMAT:
            raise ValueError('Bestandsformaat moet CF32LE zijn')
        self.sample_rate = int(info['sample_rate'])
        self.frequency = int(info['center_hz'])
        if not (1 <= self.sample_rate <= 20_000_000 and 10_000 <= self.frequency <= 2_000_000_000):
            raise ValueError('Ongeldige opname-metadata')
        self._handle = self.path.open('rb')
        self._next_frame_at = time.monotonic()

    def tune(self, frequency):
        if int(frequency) != self.frequency:
            raise RuntimeError('IQ-replay is een vaste opname; verander de middenfrequentie niet')

    def set_gain(self, gain):
        pass

    def read(self, n):
        # Replay at capture speed; no repeated spinning on EOF.
        data = self._handle.read(max(1, int(n))*8)
        if not data:
            raise EOFError('Einde van IQ-opname bereikt')
        data = data[:len(data)//8*8]
        samples = np.frombuffer(data, dtype='<c8').copy()
        self._next_frame_at += len(samples)/self.sample_rate
        delay = self._next_frame_at-time.monotonic()
        if delay > 0:
            time.sleep(min(delay, .20))
        return samples

    def close(self):
        self._handle.close()
