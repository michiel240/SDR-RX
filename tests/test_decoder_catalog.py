from sdr_studio.decoder_catalog import DECODERS, decoder_template, decoder_description, stream_command


def test_catalog_discloses_external_runtime():
    assert len(DECODERS) >= 17
    assert len({d.label for d in DECODERS}) == len(DECODERS)
    assert all(d.input_hint for d in DECODERS)
    assert sum(bool(d.stream) for d in DECODERS) == 18


def test_rtl433_uses_shared_iq_bridge_on_both_receivers():
    item = DECODERS[0]
    exe, args, rate = stream_command(item, 433_920_000, 'RTL-SDR')
    assert (exe, args, rate) == ('rtl_433', ['-r', '-', '-s', '250000', '-f', '433920000', '-F', 'json'], 250_000)
    assert decoder_template(item, 433_920_000, 'Airspy R2') == (exe, ' '.join(args))
    assert 'IQ/audio-koppeling' in decoder_description(item, 'Airspy R2')


def test_other_stream_profiles_have_correct_sample_rates():
    assert stream_command(DECODERS[1], 162_000_000, 'Airspy R2')[2] == 288_000
    assert stream_command(DECODERS[2], 1_090_000_000, 'RTL-SDR')[2] == 2_000_000
    assert stream_command(DECODERS[3], 144_800_000, 'RTL-SDR')[2] == 48_000


def test_unintegrated_modes_require_configuration():
    for item in DECODERS:
        if item.approach == 'configure' and not item.executable:
            assert decoder_template(item, 145_500_000, 'RTL-SDR') == ('', '')
            assert not item.stream
