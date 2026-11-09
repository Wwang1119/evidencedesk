"""Check the actual staged Git snapshot before publishing. Never prints secrets."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main():
    paths = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").decode().split("\0")
    secrets = []
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and line.split("=",1)[0] in ("NEBIUS_API_KEY", "TAVILY_API_KEY"):
                value = line.split("=",1)[1].strip().strip("\"'")
                if len(value) >= 8:
                    secrets.append(value.encode())
    failures = []
    for path in filter(None, paths):
        if (path.startswith((".local/", ".venv/", "demo/recordings/")) or
            (Path(path).name.startswith(".env") and Path(path).name != ".env.example")):
            failures.append(f"Private path is staged: {path}")
            continue
        content = git("show", ":"+path)
        if any(secret in content for secret in secrets) or re.search(rb"(?:tvly-[A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----)", content):
            failures.append(f"Potential credential in staged file: {path}")
    if git("check-ignore", ".env").strip() != b".env":
        failures.append(".env is not ignored")
    if failures:
        print("\n".join(failures)); return 1
    print(f"Publication preflight passed for {len(list(filter(None,paths)))} staged files. Review the diff before publishing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
