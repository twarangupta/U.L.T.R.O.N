"""Voice effect chain: settings, passthrough, pitch, click-free chunking, no speaker needed."""
import numpy as np
import pytest

from ultron.voice.effects import PRESETS, EffectChain, EffectSettings, trim_and_pause

RATE = 22050


def tone(seconds=1.0, hz=180.0, level=0.4):
    t = np.arange(int(seconds * RATE)) / RATE
    return (np.sin(2 * np.pi * hz * t) * level * 32767).astype(np.int16)


def dominant_hz(pcm):
    spec = np.abs(np.fft.rfft(pcm.astype(np.float32) * np.hanning(len(pcm))))
    return np.fft.rfftfreq(len(pcm), 1 / RATE)[int(np.argmax(spec))]


def test_presets_and_overrides():
    assert not EffectSettings.from_env({}).active
    assert not EffectSettings.from_env({"VOICE_PRESET": "none"}).active
    assert EffectSettings.from_env({"VOICE_PRESET": "ultron"}).pitch == PRESETS["ultron"]["pitch"]
    s = EffectSettings.from_env({"VOICE_PRESET": "ultron", "VOICE_PITCH": "2", "VOICE_REVERB": "0"})
    assert (s.pitch, s.reverb, s.metal) == (2.0, 0.0, PRESETS["ultron"]["metal"])
    assert not EffectSettings.from_env({"VOICE_PRESET": "nonsense"}).active
    assert EffectSettings.from_env({"VOICE_METAL": "9", "VOICE_PITCH": "x"}).metal == 1.0


def test_none_is_passthrough():
    pcm = tone()
    chain = EffectChain(EffectSettings(), RATE)
    assert chain.process(pcm) is pcm
    assert len(chain.flush()) == 0
    assert chain.length_scale_factor == 1.0


def test_pitch_goes_down_by_the_requested_semitones():
    chain = EffectChain(EffectSettings(pitch=3.0), RATE)
    out = chain.process(tone(hz=200))
    assert dominant_hz(out) == pytest.approx(200 * 2 ** (-3 / 12), rel=0.03)
    assert len(out) == pytest.approx(RATE * 2 ** (3 / 12), rel=0.01)
    assert chain.length_scale_factor == pytest.approx(2 ** (-3 / 12))


@pytest.mark.parametrize("preset", ["subtle", "ultron", "heavy"])
def test_output_is_bounded_and_not_silent(preset):
    chain = EffectChain(EffectSettings.from_env({"VOICE_PRESET": preset}), RATE)
    out = np.concatenate([chain.process(tone(0.5, level=0.95)), chain.flush()])
    assert out.dtype == np.int16
    assert np.max(np.abs(out)) > 1000
    assert np.max(np.abs(out)) <= 32767


def test_chunk_boundaries_are_click_free():
    """The stateful stages (metal, double, reverb) must give the same audio when a signal is
    split into pieces as when it is processed whole."""
    settings = EffectSettings(pitch=0.0, metal=0.5, reverb=0.4, double=0.3)
    sig = tone(1.0, level=0.5)
    whole = EffectChain(settings, RATE)
    ref = np.concatenate([whole.process(sig), whole.flush()]).astype(np.float32)
    split = EffectChain(settings, RATE)
    cuts = [0, 3001, 9000, len(sig)]
    parts = [split.process(sig[a:b]) for a, b in zip(cuts, cuts[1:])] + [split.flush()]
    got = np.concatenate(parts).astype(np.float32)
    assert len(got) == len(ref)
    assert np.max(np.abs(got - ref)) < 400       # about 1 percent of full scale (limiter rounding)
    # no jump at the seams beyond what the signal itself does
    for seam in cuts[1:-1]:
        assert abs(got[seam] - got[seam - 1]) < 4 * np.max(np.abs(np.diff(ref[seam - 50:seam + 50])))


def test_reset_clears_state_between_texts():
    chain = EffectChain(EffectSettings(reverb=0.5, double=0.3), RATE)
    chain.process(tone(0.3))
    chain.reset()
    assert len(chain.flush()) == 0 or not np.any(chain.flush())
    first = chain.process(tone(0.2))
    chain.reset()
    assert np.array_equal(first, chain.process(tone(0.2)))


def test_reverb_tail_decays():
    chain = EffectChain(EffectSettings(reverb=0.8), RATE)
    chain.process(tone(0.3, level=0.6))
    tail = chain.flush().astype(np.float32)
    assert 0 < len(tail) <= int(0.5 * RATE)
    quarter = len(tail) // 4
    assert np.abs(tail[:quarter]).mean() > 4 * np.abs(tail[-quarter:]).mean()


def test_trim_and_pause():
    pcm = np.concatenate([np.zeros(5000, np.int16), tone(0.1), np.zeros(5000, np.int16)])
    out = trim_and_pause(pcm, RATE, 0.1)
    assert len(out) < len(pcm)
    assert len(out) >= len(tone(0.1)) + int(0.1 * RATE)
