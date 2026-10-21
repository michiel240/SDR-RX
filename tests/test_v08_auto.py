import numpy as np
from sdr_studio.digital_auto import RFMonitor, find_rf_candidates


def make_spectrum(n=2048, peaks=()):
    values=np.full(n,-108.,dtype=np.float32)
    for position,width,height in peaks:
        values[position:position+width]=height
    return values


def test_detect_multiple_independent_non_dc_peaks():
    s=make_spectrum(peaks=[(400,7,-67),(1490,10,-60)])
    found=find_rf_candidates(s,2_048_000,145_500_000)
    assert len(found)==2
    assert all(c.evidence.endswith('onbekend') for c in found)
    assert all(c.over_noise_db>=17 for c in found)
    assert found[0].frequency_hz>145_500_000


def test_ignore_dc_spur_and_edge_spikes():
    s=make_spectrum(peaks=[(0,5,-32),(1024,2,-37),(2043,4,-32)])
    assert find_rf_candidates(s,2_048_000,145_500_000)==[]


def test_stable_candidate_requires_repeated_observations_and_rate_limit():
    s=make_spectrum(peaks=[(1500,8,-60)])
    m=RFMonitor(min_hits=2,report_interval_sec=10)
    assert m.update(s,2_048_000,145_500_000,now=1)==[]
    assert m.update(s,2_048_000,145_500_000,now=1.1)==[]
    events=m.update(s,2_048_000,145_500_000,now=2)
    assert len(events)==1 and events[0].hits==2
    assert m.update(s,2_048_000,145_500_000,now=3)==[]
    assert m.update(s,2_048_000,145_500_000,now=7)==[]
    assert len(m.update(s,2_048_000,145_500_000,now=13))==1  # stable re-report


def test_no_activity_and_nonfinite_gracefully_ignored():
    m=RFMonitor()
    assert m.update(np.full(512,-90),2_048_000,145_500_000,now=1)==[]
    assert find_rf_candidates(np.full(128,np.nan),2_048_000,145_500_000)==[]


def test_tuning_center_moving_discards_stale_tracks():
    s=make_spectrum(peaks=[(1500,8,-60)])
    m=RFMonitor()
    assert not m.update(s,2_048_000,145_500_000,now=1)
    assert not m.update(np.full(2048,-110),2_048_000,145_500_000,now=8)
    assert not m.tracks
    assert not m.update(s,2_048_000,146_500_000,now=9)
