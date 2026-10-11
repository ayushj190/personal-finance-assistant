"""Convenience test runner script ensuring proper environment, encoding, and path."""
import os
import sys
import subprocess


def main() -> int:
    repo_root = os.path.dirname(os.path.abspath(__file__))
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = repo_root

    venv_pytest = os.path.join(repo_root, ".venv", "Scripts", "pytest.exe")
    if os.path.isfile(venv_pytest):
        cmd = [venv_pytest] + sys.argv[1:]
    else:
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests"] + sys.argv[1:]

    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    sys.exit(main())
