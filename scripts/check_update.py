#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from _lib import ROOT, latest_stable, parse_ls_remote, query_tags

parser = argparse.ArgumentParser(description="Dry-run upstream stable-tag update check")
parser.add_argument("--remote-file", type=Path)
args = parser.parse_args()
lock = json.loads((ROOT / "provenance.lock.json").read_text())
tags = parse_ls_remote(args.remote_file.read_text()) if args.remote_file else query_tags()
latest, refs = latest_stable(tags)
current_tag = lock["upstream"]["tag"]
current_refs = tags.get(current_tag)
pinned_tag_missing = current_refs is None
pinned_tag_moved = bool(current_refs) and (
    current_refs["commit"] != lock["upstream"]["commit"]
    or current_refs["tag_object"] != lock["upstream"]["tag_object"]
)
print(json.dumps({
    "current_commit": lock["upstream"]["commit"],
    "current_tag": lock["upstream"]["tag"],
    "latest_commit": refs["commit"],
    "latest_tag": latest,
    "pinned_tag_missing": pinned_tag_missing,
    "pinned_tag_moved": pinned_tag_moved,
    "update_available": latest != current_tag,
}, indent=2, sort_keys=True))
if pinned_tag_missing or pinned_tag_moved:
    raise SystemExit(2)
