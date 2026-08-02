#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import tempfile
from pathlib import Path

from _lib import ROOT, UPSTREAM_WEB, adapter_version, download_archive, latest_stable, load_config, query_tags, sha256_file, write_json
from build_plugin import build
from _lib import extract_archive


def main() -> None:
    parser = argparse.ArgumentParser(description="Pin, fetch, transform, and build cc-suite")
    parser.add_argument("--tag")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--commit")
    parser.add_argument("--tag-object")
    parser.add_argument("--synced-at")
    parser.add_argument("--offline-verified", action="store_true", help="accept caller-supplied verified refs and archive")
    args = parser.parse_args()
    if args.tag and args.commit:
        if not args.offline_verified or not args.archive:
            raise SystemExit("explicit refs require --offline-verified and --archive")
        tag = args.tag
        refs = {"commit": args.commit, "tag_object": args.tag_object or args.commit}
    else:
        tags = query_tags()
        if args.tag:
            if args.tag not in tags:
                raise SystemExit(f"stable tag not found: {args.tag}")
            tag, refs = args.tag, tags[args.tag]
        else:
            tag, refs = latest_stable(tags)
    config = load_config()
    with tempfile.TemporaryDirectory(prefix="cc-suite-sync-") as temp_name:
        temp = Path(temp_name)
        archive = args.archive or temp / f"cc-suite-{tag}.tar.gz"
        if not args.archive:
            download_archive(tag, archive)
        if not args.offline_verified:
            live_refs = query_tags().get(tag)
            if live_refs != refs:
                raise SystemExit(f"upstream tag changed or disappeared during sync: {tag}")
        archive_hash = sha256_file(archive)
        source = extract_archive(archive, tag, temp / "source")
        license_hash = sha256_file(source / "LICENSE")
        synced_at = args.synced_at or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        lock = {
            "adapter": {
                "repository": config["adapter_repository"],
                "revision": config["adapter_revision"],
                "runtime_files": config["runtime_files"],
                "selected_skills": config["selected_skills"],
                "sync_time": synced_at,
                "version": adapter_version(tag, config["adapter_revision"]),
            },
            "artifact": {"plugin_path": f"plugins/{config['plugin_name']}"},
            "schema_version": 1,
            "upstream": {
                "archive_sha256": archive_hash,
                "archive_url": f"{UPSTREAM_WEB}/archive/refs/tags/{tag}.tar.gz",
                "commit": refs["commit"],
                "license_sha256": license_hash,
                "repository": UPSTREAM_WEB,
                "tag": tag,
                "tag_object": refs["tag_object"],
            },
        }
        write_json(ROOT / "provenance.lock.json", lock)
        lock["artifact"]["tree_sha256"] = build(source, lock)
        write_json(ROOT / "provenance.lock.json", lock)
        print(json.dumps(lock, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
