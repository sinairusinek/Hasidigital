"""Shared paths and helpers for the motif/Propp experiment (Paris INALCO talk).

The motif indexes are copyrighted and live in private/motif-indexes/ (git-excluded).
Outputs that quote motif titles go to private/motif-experiment/; only scripts and
aggregate numbers live under talks/.
"""
import json
import os
import re
import shutil
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

SAMPLE_TSV = Path(os.environ.get("MOTIF_SAMPLE", HERE / "sample.tsv"))
STEP1_DIR = OUT / "step1"          # per-story events + Propp JSON
STEP2_JSON = OUT / "shortlists.json"
STEP3_DIR = OUT / "step3"          # per-story motif picks JSON

def _find_claude() -> str:
    """Newest Claude Code CLI shipped with the VS Code extension (the path moves on update)."""
    ext = Path.home() / ".vscode" / "extensions"
    cands = sorted(ext.glob("anthropic.claude-code-*/resources/native-binary/claude"))
    if cands:
        return str(cands[-1])
    return shutil.which("claude") or "claude"


CLAUDE_BIN = os.environ.get("CLAUDE_CLI_BIN") or _find_claude()
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
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # Hebrew abbreviations quoted unescaped inside a JSON string (מו"ה, ז"ל):
        # a " between two Hebrew letters becomes gershayim
        return json.loads(re.sub(r'(?<=[א-ת])"(?=[א-ת])', "״", s))


def is_heading(code: str) -> bool:
    """Thompson's tens headings: no decimal point, ending in 0 (V0, V220, P340, J1350).
    They group the numbered motifs filed under them. V223 or V223.3 are motifs."""
    c = re.sub(r"#\d+$", "", code.replace("Noy ", ""))
    return bool(re.fullmatch(r"[A-Z]\d*0", c))


LEVELS = ["exact", "broader", "heading", "nothing"]
LEVEL_NAMES = {"exact": "a specific motif fits exactly", "broader": "a broader but specific motif fits",
               "heading": "only a section heading fits", "nothing": "nothing fits, not even a heading"}


def event_level(picks, proposed_branch):
    spec = [p for p in picks if not is_heading(p["code"])]
    if any(p["grade"] == "exact" for p in spec):
        return "exact", ""
    if spec:
        return "broader", ""
    if picks:
        return "heading", "picked"
    if proposed_branch:
        return "heading", "named"
    return "nothing", ""
