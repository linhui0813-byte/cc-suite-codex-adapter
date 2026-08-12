#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from _lib import ROOT, package_release, query_package_release

parser = argparse.ArgumentParser(description="Dry-run upstream package.json version check")
parser.add_argument("--package-file", type=Path, help="read saved upstream package.json")
parser.add_argument("--commit", help="full upstream commit for --package-file")
args = parser.parse_args()
lock = json.loads((ROOT / "provenance.lock.json").read_text())
if args.package_file:
    if not args.commit:
        parser.error("--package-file requires --commit")
    latest = package_release(args.commit, args.package_file.read_text(encoding="utf-8"))
elif args.commit:
    parser.error("--commit requires --package-file")
else:
    latest = query_package_release()
current_version = lock["upstream"].get("version", lock["upstream"].get("tag", "").removeprefix("v"))
print(json.dumps({
    "current_commit": lock["upstream"]["commit"],
    "current_version": current_version,
    "latest_commit": latest["commit"],
    "latest_ref": latest["ref"],
    "latest_version": latest["version"],
    "source_commit_changed": latest["commit"] != lock["upstream"]["commit"],
    "update_available": latest["version"] != current_version,
}, indent=2, sort_keys=True))
