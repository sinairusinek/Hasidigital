"""Shared paths and helpers for the motif/Propp experiment (Paris INALCO talk).

The motif indexes are copyrighted and live in private/motif-indexes/ (git-excluded).
Outputs that quote motif titles go to private/motif-experiment/; only scripts and
aggregate numbers live under talks/.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "Authorities" / "integration_tool"))

MOTIFS = REPO / "private" / "motif-indexes"
OUT = REPO / "private" / "motif-experiment"
OUT.mkdir(parents=True, exist_ok=True)

SAMPLE_TSV = HERE / "sample.tsv"
STEP1_DIR = OUT / "step1"          # per-story events + Propp JSON
STEP2_JSON = OUT / "shortlists.json"
STEP3_DIR = OUT / "step3"          # per-story motif picks JSON

CLAUDE_BIN = os.environ.get(
    "CLAUDE_CLI_BIN",
    os.path.expanduser("~/.vscode/extensions/anthropic.claude-code-2.1.325-darwin-arm64/"
                       "resources/native-binary/claude"))
MODEL = os.environ.get("MOTIF_MODEL", "claude-opus-5-5")


def call_claude(system: str, user: str, retries: int = 3, timeout: int = 600) -> dict:
    """claude -p on the Max plan (never the API), no tools; returns parsed JSON."""
    cmd = [CLAUDE_BIN, "-p", "--model", MODEL, "--system-prompt", system,
           "--output-format", "text", "--disallowedTools", "*"]
    err = None
    for a in range(retries):
        try:
            r = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=timeout)
            if r.returncode == 0:
                return parse_json(r.stdout)
            err = f"rc={r.returncode} {r.stderr[-300:]}"
        except Exception as e:  # timeout or bad JSON
            err = repr(e)
        time.sleep(5 * (a + 1))
    raise RuntimeError(err)


def parse_json(s: str) -> dict:
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", s, re.S)
    if m:
        s = m.group(1)
    else:
        s = s[s.find("{"): s.rfind("}") + 1]
    return json.loads(s)
