import subprocess
import sys


def main():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_engine.py"],
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
