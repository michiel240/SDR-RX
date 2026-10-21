"""New v0.7 integration and DSP checks without connecting SDR hardware."""
import json
import sys
import types
import numpy as np
import pytest
from scipy import signal
from sdr_studio.dual_vfo import VFOChannel, DualVFOProcessor, center_and_validate
from sdr_studio.rds import RDSStatus
from sdr_studio.signal_hints import signal_hint
from sdr_studio.audio import AudioOutput
from sdr_studio.digital_stream import parse_decoder_line


def channel(freq, mode='NFM', bw=12500):
    return VFOChannel(freq,mode,bw,-90)


def test_dual_if_center_and_boundaries():
    a,b=channel(145_500_000),channel(145_525_000)
    assert center_and_validate(a,b,2_500_000)==145_512_500
    with pytest.raises(ValueError):
        center_and_validate(a,channel(147_525_000),2_500_000)
    with pytest.raises(ValueError):
        center_and_validate(channel(90_000_000,'WFM',200_000),channel(90_050_000,'WFM',200_000),2_500_000)


def test_dual_distinct_rf_channels_to_independent_audio():
    rate=2_500_000
    fa,fb=145_500_000,145_525_000
    dual=DualVFOProcessor(rate,channel(fa),channel(fb),agc=False)
    # Two independent FM stations with distinct modulation tones 720/1500 Hz.
    blocks=[]
    start=0
    for _ in range(12):
        n=np.arange(start,start+65536,dtype=np.float64)
        phase_a=2*np.pi*720*n/rate
        phase_b=2*np.pi*1500*n/rate
        # integrated instantaneous FM deviation 2600 Hz
        t_a=2*np.pi*2600/(720*2*np.pi)*np.sin(phase_a)
        t_b=2*np.pi*2600/(1500*2*np.pi)*np.sin(phase_b)
        xa=.25*np.exp(1j*(2*np.pi*(-12500)*n/rate+t_a))
        xb=.25*np.exp(1j*(2*np.pi*(12500)*n/rate+t_b))
        audio,_=dual.process((xa+xb).astype(np.complex64))
        blocks.append(audio)
        start+=65536
    stereo=np.concatenate(blocks)[2400:]
    assert stereo.ndim==2 and stereo.shape[1]==2
    def peak(y):
        freqs,p=signal.periodogram(y,fs=48_000)
        band=(freqs>250)&(freqs<2200)
        return float(freqs[band][np.argmax(p[band])])
    assert abs(peak(stereo[:,0])-720)<30
    assert abs(peak(stereo[:,1])-1500)<30


def test_dual_independent_squelch():
    a=VFOChannel(145500000,'NFM',12500,0) # mute left
    b=VFOChannel(145525000,'NFM',12500,-100)
    stereo,_=DualVFOProcessor(2500000,a,b,agc=False).process(
                  (0.4*np.ones(131072)).astype(np.complex64))
    assert np.all(stereo[:,0]==0)


def test_rds_real_json_only():
    state=RDSStatus()
    assert not state.update('not json')
    assert state.update('{"pi":"0xD3C2","ps":"RADIO123","radiotext":"Hallo M@rcello"}')
    assert state.as_dict()['ps']=='RADIO123'
    assert state.as_dict()['text']=='Hallo M@rcello'
    assert not state.update('{}')
    assert state.update('{"radiotext":"Nieuws"}')
    assert state.as_dict()['ps']=='RADIO123'


def test_rf_hint_never_claims_exact_protocol():
    rng=np.random.default_rng(9)
    s=-102+rng.normal(0,1,8192)
    s[4100]=0
    result=signal_hint(s,2_500_000,145_500_000)
    assert result.confidence=='indicatie'
    assert 'DMR' not in result.label and 'P25' not in result.label
    assert 'Geen protocolbevestiging' in result.reason


def test_voice_events_only_from_explicit_decoder_log():
    assert parse_decoder_line('DSD-neo · Digital Auto','P25 sync voice slot 1').protocol.startswith('P25')
    assert parse_decoder_line('DSD-neo · Digital Auto','energy high, perhaps DMR') is None
    assert parse_decoder_line('DSD-neo · Digital Auto','wat is dit?') is None


def test_two_channel_audio_output(monkeypatch):
    class Stream:
        def __init__(self, **kwargs):self.kwargs=kwargs
        def start(self):pass
        def stop(self):pass
        def close(self):pass
    monkeypatch.setitem(sys.modules,'sounddevice',types.SimpleNamespace(OutputStream=Stream))
    out=AudioOutput(channels=2)
    out.submit(np.array([[.1,.2],[.3,.4]],dtype=np.float32))
    data=np.empty((4,2),dtype=np.float32)
    out.stream.kwargs['callback'](data,4,None,None)
    np.testing.assert_allclose(data[:2],[[.1,.2],[.3,.4]])
    np.testing.assert_allclose(data[2:],0)
    out.close()


def test_rds_bridge_receives_json_from_real_child_process(tmp_path):
    """Child-process/stdin/stdout plumbing, not a claim of real RF reception."""
    import time
    import sys
    from pathlib import Path
    from sdr_studio.rds import RDSBridge
    script=tmp_path/'redsea_fake.py'
    script.write_text('#!/usr/bin/env python3\nimport sys\nx=sys.stdin.buffer.read1(200)\nif len(x)==200:\n print(\'{"pi":"0x1234","ps":"TEST FM","radiotext":"RDS test"}\',flush=True)\n',encoding='utf-8')
    script.chmod(0o755)
    events=[]; log=[]
    bridge=RDSBridge([sys.executable, str(script)],250000,events.append,log.append).start()
    try:
        bridge.submit(np.zeros(1000,dtype=np.float32))
        until=time.monotonic()+10
        while not events and time.monotonic()<until:
            time.sleep(.01)
        assert events and events[0]['ps']=='TEST FM'
        assert events[0]['text']=='RDS test'
    finally:
        bridge.close()


def test_worker_stereo_receives_with_one_source(monkeypatch):
    """The hardware mock must be opened once, then one stereo output stream."""
    import time
    from sdr_studio import worker
    from sdr_studio import audio as audio_module
    calls=[]
    class Source:
        sample_rate=2_500_000
        def __init__(self):self.blocks=0
        def tune(self,f):self.frequency=int(f);calls.append(('tune',f))
        def read(self,n):
            self.blocks+=1
            if self.blocks>3:raise EOFError('Klaar')
            return np.full(n,.02+0.01j,dtype=np.complex64)
        def close(self):calls.append(('close',))
    class Output:
        def __init__(self,channels=1):
            calls.append(('output',channels))
        def submit(self,x):calls.append(('shape',np.asarray(x).shape))
        def close(self):pass
        def flush(self):pass
    monkeypatch.setattr(worker,'make_source',lambda *args: (calls.append(('open',)),Source())[1])
    monkeypatch.setattr(audio_module,'AudioOutput',Output)
    c=[dict(frequency_hz=145_500_000,mode='NFM',bandwidth_hz=12500,
            squelch_dbfs=-100,passband_shift_hz=0),
       dict(frequency_hz=145_525_000,mode='NFM',bandwidth_hz=12500,
            squelch_dbfs=-100,passband_shift_hz=0)]
    frames=[];statuses=[];ended=[]
    w=worker.ReceiverWorker('RTL-SDR',145_512_500,2_500_000,'NFM',-100,1.0,None,
         lambda *a:frames.append(a), statuses.append, lambda:ended.append(True),stereo_vfos=c)
    w.start();w.join(4)
    assert not w.is_alive()
    assert calls.count(('open',))==1
    assert ('output',2) in calls
    assert any(item[0]=='shape' and item[1][1]==2 for item in calls)
    assert ended
