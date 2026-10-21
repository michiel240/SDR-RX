"""Tests for the receive thread, independent of USB hardware.

Do not assume that the first FFT/demodulation block completes in 250 ms:
Windows systems can spend longer initializing SciPy and audio backends.
"""
import threading

from sdr_studio.worker import ReceiverWorker


def test_worker_simulates_and_stops_cleanly():
    frames, messages, ended = [], [], []
    got_frame = threading.Event()
    scanner_started = threading.Event()

    def on_frame(*args):
        frames.append(args)
        got_frame.set()

    def on_status(message):
        messages.append(message)
        if message.startswith('Scanner gestart:'):
            scanner_started.set()

    rx = ReceiverWorker('Demo (geen hardware)', 145_500_000, 2_400_000,
                        'NFM', -90, .5, None,
                        on_frame, on_status, lambda: ended.append(True))
    rx.start()
    try:
        assert got_frame.wait(timeout=15), (
            f'Geen FFT-frame binnen 15 seconden; status: {messages!r}')
        rx.command('frequency', 145_600_000)
        rx.command('mode', 'AM')
        rx.command('scan', [{'frequency': 145_500_000, 'mode': 'NFM'}])
        assert scanner_started.wait(timeout=15), (
            f'Scanning niet gestart binnen 15 seconden; status: {messages!r}')
    finally:
        rx.stop()
        rx.join(timeout=15)

    assert not rx.is_alive(), 'Ontvangerthread stopte niet binnen 15 seconden'
    assert ended, 'Eindmelding van de ontvanger ontbreekt'
    assert frames, 'Geen spectrumframes ontvangen'
    assert not any('FOUT:' in m for m in messages), messages
