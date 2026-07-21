#!/usr/bin/env python3
"""Create a Zenodo (sandbox or production) deposition draft and upload the
women-article deposit folder.

Reads the API token from a local untracked file:
  --sandbox  reads .zenodo_token_sandbox  (default: https://sandbox.zenodo.org)
  --prod     reads .zenodo_token          (https://zenodo.org)

What it uploads:
  - README.md
  - CHANGES.md
  - data/topics_9editions.tsv
  - data/women_binary_source.tsv
  - hasidic-women-dataset.zip   (bundles data/editions/*.xml so the 9 TEI files
                                 stay grouped in a single archive)

Metadata comes from zenodo.json (mapped to Zenodo's schema).

Leaves the deposition as a draft. Prints the edit URL — review and publish manually.

Usage:
  python zenodo_upload.py --sandbox
  python zenodo_upload.py --prod
"""
from __future__ import annotations
import argparse
import json
import sys
import zipfile
from pathlib import Path
from urllib import request, error

REPO = Path(__file__).resolve().parents[2]
DEPOSIT = REPO / "topics/women_and_topics/zenodo_deposit"


def http_json(method: str, url: str, token: str, payload=None, raw=False):
    data = None
    headers = {"Authorization": f"Bearer {token}"}
    if payload is not None and not raw:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif raw and payload is not None:
        data = payload
    req = request.Request(url, data=data, method=method, headers=headers)
    try:
        with request.urlopen(req) as resp:
            body = resp.read()
            if not body:
                return None
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return body
    except error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {e.code} {method} {url}\n{body}")


def upload_file(bucket_url: str, name: str, path: Path, token: str):
    url = f"{bucket_url}/{name}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"}
    with path.open("rb") as f:
        req = request.Request(url, data=f.read(), method="PUT", headers=headers)
    try:
        with request.urlopen(req) as resp:
            return json.loads(resp.read())
    except error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} PUT {url}\n{e.read().decode('utf-8', errors='replace')}")


def build_zenodo_metadata(meta_path: Path) -> dict:
    """Map our zenodo.json into the Zenodo deposition metadata schema."""
    m = json.loads(meta_path.read_text(encoding="utf-8"))
    out = {
        "title": m["title"],
        "upload_type": m.get("upload_type", "dataset"),
        "description": m["description"],
        "creators": [{"name": c["name"], "affiliation": c.get("affiliation", "")} for c in m["creators"]],
        "keywords": m.get("keywords", []),
        "access_right": "open",
        "license": m.get("license", "cc-by-4.0").lower().replace("cc-by-4.0", "cc-by-4.0"),
        "language": m.get("language", "heb"),
        "notes": m.get("notes", ""),
    }
    if m.get("related_identifiers"):
        # only include if it's not the TBD placeholder
        rids = [
            r for r in m["related_identifiers"]
            if r.get("identifier") and not r["identifier"].startswith("TBD")
        ]
        if rids:
            out["related_identifiers"] = rids
    return out


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--sandbox", action="store_true")
    g.add_argument("--prod", action="store_true")
    args = ap.parse_args()

    import os
    if args.sandbox:
        base = "https://sandbox.zenodo.org"
        env_var = "ZENODO_SANDBOX_TOKEN"
        token_path = REPO / ".zenodo_token_sandbox"
    else:
        base = "https://zenodo.org"
        env_var = "ZENODO_TOKEN"
        token_path = REPO / ".zenodo_token"

    token = (os.environ.get(env_var) or "").strip()
    src = f"env ${env_var}"
    if not token and token_path.exists():
        token = token_path.read_text(encoding="utf-8").strip()
        src = f"file {token_path}"
    if not token:
        sys.exit(
            f"No Zenodo token. Set ${env_var} or write the token to {token_path}.\n"
            f"Generate one at {base}/account/settings/applications/tokens/new/"
        )
    print(f"Using token from {src}")

    # Build the editions zip on-the-fly (idempotent regen)
    zip_path = DEPOSIT / "hasidic-women-dataset.zip"
    eds_dir = DEPOSIT / "data" / "editions"
    print(f"Building {zip_path.name} from {len(list(eds_dir.glob('*.xml')))} XML files...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for xml in sorted(eds_dir.glob("*.xml")):
            zf.write(xml, arcname=f"editions/{xml.name}")
        # also bundle the two TSVs for redundancy inside the zip
        for tsv in [DEPOSIT / "data" / "topics_9editions.tsv", DEPOSIT / "data" / "women_binary_source.tsv"]:
            zf.write(tsv, arcname=f"data/{tsv.name}")
        zf.write(DEPOSIT / "README.md", arcname="README.md")
        zf.write(DEPOSIT / "CHANGES.md", arcname="CHANGES.md")

    metadata = build_zenodo_metadata(DEPOSIT / "zenodo.json")

    # 1. Create empty deposition
    print(f"Creating draft on {base} ...")
    dep = http_json("POST", f"{base}/api/deposit/depositions", token, payload={})
    dep_id = dep["id"]
    bucket = dep["links"]["bucket"]
    print(f"  Deposition id: {dep_id}")
    print(f"  Bucket: {bucket}")

    # 2. Upload files
    uploads = [
        ("hasidic-women-dataset.zip", zip_path),
        ("README.md", DEPOSIT / "README.md"),
        ("CHANGES.md", DEPOSIT / "CHANGES.md"),
        ("topics_9editions.tsv", DEPOSIT / "data" / "topics_9editions.tsv"),
        ("women_binary_source.tsv", DEPOSIT / "data" / "women_binary_source.tsv"),
    ]
    for name, p in uploads:
        size_kb = p.stat().st_size / 1024
        print(f"  Uploading {name} ({size_kb:.1f} KB)...")
        upload_file(bucket, name, p, token)

    # 3. Update metadata
    print("Setting metadata...")
    http_json("PUT", f"{base}/api/deposit/depositions/{dep_id}", token,
              payload={"metadata": metadata})

    # 4. Report
    edit_url = f"{base}/deposit/{dep_id}"
    print("\nDraft created (NOT published).")
    print(f"  Edit / preview: {edit_url}")
    print(f"  API record: {base}/api/deposit/depositions/{dep_id}")
    print("Review the draft in the browser and click Publish there when satisfied.")


if __name__ == "__main__":
    main()
