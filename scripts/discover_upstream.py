#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from _lib import package_release, query_package_release

parser = argparse.ArgumentParser(description="Discover cc-suite package.json version on upstream main")
parser.add_argument("--package-file", type=Path, help="read saved upstream package.json")
parser.add_argument("--commit", help="full upstream commit for --package-file")
args = parser.parse_args()
if args.package_file:
    if not args.commit:
        parser.error("--package-file requires --commit")
    release = package_release(args.commit, args.package_file.read_text(encoding="utf-8"))
elif args.commit:
    parser.error("--commit requires --package-file")
else:
    release = query_package_release()
print(json.dumps(release, sort_keys=True))
