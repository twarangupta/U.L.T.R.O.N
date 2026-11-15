"""Start ULTRON:  python -m ultron   (run_ultron.bat does this for you).

    python -m ultron               run the assistant
    python -m ultron --benchmark   show the hardware profile and how fast it is
    python -m ultron --self-test   check config, commands and hardware profile; no mic, speaker or models
"""
import sys


def main() -> int:
    if "--self-test" in sys.argv:
        from ultron.selftest import run_self_test
        return run_self_test()
    if "--benchmark" in sys.argv:
        from ultron.benchmark import run_benchmark
        return run_benchmark()
    from ultron.app import run
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
