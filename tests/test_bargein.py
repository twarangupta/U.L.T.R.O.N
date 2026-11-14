"""Barge-in: the user talking over ULTRON stops it; ULTRON's own echo does not."""
import numpy as np

from bargein import BargeInDetector

RNG = np.random.default_rng(0)


def noise(level: float, n: int = 1280) -> np.ndarray:
    return (RNG.normal(0, level, n)).clip(-32768, 32767).astype(np.int16)


def feed(det, level, chunks):
    return [det.feed(noise(level)) for _ in range(chunks)]


def test_echo_alone_never_interrupts():
    det = BargeInDetector(factor=3.0, min_rms=700, needed=4)
    # ULTRON's own voice through laptop speakers, varying a bit
    for level in (900, 1300, 1100, 1500, 1000) * 10:
        assert not det.feed(noise(level))


def test_user_talking_over_echo_interrupts_after_about_a_third_of_a_second():
    det = BargeInDetector(factor=3.0, min_rms=700, needed=4)
    feed(det, 1000, 20)                      # echo baseline
    results = feed(det, 6000, 4)             # user speaks, much louder at the mic
    assert results == [False, False, False, True]


def test_short_bang_does_not_interrupt():
    det = BargeInDetector(factor=3.0, min_rms=700, needed=4)
    feed(det, 1000, 20)
    assert not any(feed(det, 8000, 2))       # a 160 ms knock
    assert not any(feed(det, 1000, 10))


def test_quiet_room_with_headphones_reacts_to_voice():
    det = BargeInDetector(factor=3.0, min_rms=700, needed=4)
    feed(det, 50, 10)                        # no echo: the mic hears almost nothing
    assert feed(det, 2500, 4)[-1]            # normal speech is enough


def test_preroll_keeps_the_words_spoken_over_ulton():
    det = BargeInDetector(needed=4)
    feed(det, 1000, 20)
    feed(det, 6000, 4)
    pre = det.preroll()
    assert 4 <= len(pre) <= 12
    assert np.sqrt(np.mean(pre[-1].astype(np.float32) ** 2)) > 3000
