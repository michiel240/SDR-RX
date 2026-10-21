"""Advisory RF morphology, NOT protocol decoding or identification.

Actual DMR/P25/NXDN/etc recognition requires a protocol decoder (DSD-neo
external profile); spectrum shape alone cannot determine the protocol.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class SignalHint:
    label: str
    reason: str
    confidence: str = 'indicatie'


def signal_hint(spectrum_dbfs, sample_rate_hz, center_hz) -> SignalHint:
    s=np.asarray(spectrum_dbfs,dtype=np.float32)
    if s.size<128:
        return SignalHint('Geen analyse','Te weinig FFT-punten')
    n=s.size
    noise=float(np.median(s))
    peak=float(np.max(s))
    if peak-noise<13:
        return SignalHint('Geen duidelijk kanaal','Piek niet minstens 13 dB boven ruisvloer')
    p=int(np.argmax(s))
    threshold=max(noise+9,peak-20)
    # Only a contiguous peak neighbourhood, not the full broadband noise.
    l=p
    while l>0 and s[l-1]>threshold:l-=1
    r=p
    while r+1<n and s[r+1]>threshold:r+=1
    bw=max(1,(r-l+1)*sample_rate_hz/n)
    frequency=center_hz+(p-n//2)*sample_rate_hz/n
    if abs(frequency-1090e6)<2e6:
        label='1090 MHz · mogelijk ADS-B'
    elif 87.5e6<=frequency<=108e6 and bw>25_000:
        label='FM-omroepband · mogelijk WFM/RDS'
    elif bw < 30_000:
        label='Smalbandig signaal · analoog of digitaal mogelijk'
    else:
        label='Breedbandig of samengesteld signaal'
    return SignalHint(label, f'Geschatte piek {frequency/1e6:.5f} MHz; '
                            f'boven ruisvloer {peak-noise:.0f} dB; '
                            f'piekbreedte ~{bw/1000:.1f} kHz. '
                            'Geen protocolbevestiging.')
