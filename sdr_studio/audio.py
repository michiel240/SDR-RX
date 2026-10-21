"""Optional nonblocking 48-kHz PortAudio output. Imported only on Start."""
import queue
import numpy as np


class AudioOutput:
    def __init__(self, channels=1):
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("Audio vereist: pip install sounddevice") from exc
        self.channels = int(channels)
        if self.channels not in (1,2):
            raise ValueError("Alleen mono of stereo ondersteund")
        self.queue = queue.Queue(maxsize=24)
        self.leftover = np.empty((0, self.channels), dtype=np.float32)

        def callback(outdata, frames, time_info, status):
            output = outdata
            output.fill(0)
            written = 0
            while written < frames:
                if len(self.leftover) == 0:
                    try:
                        self.leftover = self.queue.get_nowait()
                    except queue.Empty:
                        break
                count = min(frames - written, len(self.leftover))
                output[written:written+count] = self.leftover[:count]
                self.leftover = self.leftover[count:]
                written += count

        self.stream = sd.OutputStream(samplerate=48_000, channels=self.channels, blocksize=2048,
                                      dtype="float32", callback=callback)
        self.stream.start()

    def submit(self, samples):
        samples = np.asarray(samples, dtype=np.float32)
        if self.channels == 1:
            samples = samples.reshape(-1,1)
        if samples.ndim != 2 or samples.shape[1] != self.channels:
            raise ValueError('Audiokanalen komen niet overeen met output')
        try:
            self.queue.put_nowait(samples)
        except queue.Full:
            try:
                self.queue.get_nowait()  # discard stale audio instead of growing latency
                self.queue.put_nowait(np.asarray(samples, dtype=np.float32))
            except queue.Empty:
                pass

    def flush(self):
        """Discard buffered audio from the former VFO after a retune.

        Audio callback can still be reading a block: it will finish it before
        using newly queued audio. Avoid manipulating that buffer from another
        thread; clearing the queue is sufficient for bounded switching latency.
        """
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break

    def close(self):
        self.stream.stop()
        self.stream.close()
