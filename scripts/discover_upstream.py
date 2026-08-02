#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from _lib import latest_stable, parse_ls_remote, query_tags

parser = argparse.ArgumentParser(description="Discover the latest stable cc-suite tag")
parser.add_argument("--remote-file", type=Path, help="parse saved git ls-remote output")
args = parser.parse_args()
tags = parse_ls_remote(args.remote_file.read_text()) if args.remote_file else query_tags()
tag, refs = latest_stable(tags)
print(json.dumps({"tag": tag, **refs}, sort_keys=True))

