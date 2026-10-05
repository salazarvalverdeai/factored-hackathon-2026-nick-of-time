"""Fill the local .env from AWS SSM Parameter Store without printing any value.

    make env-pull               # fills names that are missing or empty in .env
    make env-pull ARGS=--force  # also overwrites names that already have a value

Reads /nickoftime/prod/<NAME> (top level only; nested paths such as cognito/* passwords are never pulled) with the
team profile and writes NAME=<value>. Prints only the names it touched.
"""
from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
PREFIX = "/nickoftime/prod/"

parser = argparse.ArgumentParser()
parser.add_argument("--force", action="store_true")
parser.add_argument("--profile", default="nickoftime")
parser.add_argument("--region", default="us-east-2")
args = parser.parse_args()

ssm = boto3.Session(profile_name=args.profile, region_name=args.region).client("ssm")
remote: dict[str, str] = {}
for page in ssm.get_paginator("get_parameters_by_path").paginate(Path=PREFIX, Recursive=False, WithDecryption=True):
    for param in page["Parameters"]:
        name = param["Name"][len(PREFIX):]
        if "/" not in name:
            remote[name] = param["Value"]

lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
filled, kept, appended = [], [], []
seen = set()
for i, line in enumerate(lines):
    key, sep, value = line.partition("=")
    key = key.strip()
    if not sep or key.startswith("#") or key not in remote:
        continue
    seen.add(key)
    if value.strip() and not args.force:
        kept.append(key)
        continue
    lines[i] = f"{key}={remote[key]}"
    filled.append(key)
for key in sorted(set(remote) - seen):
    lines.append(f"{key}={remote[key]}")
    appended.append(key)

fd, tmp = tempfile.mkstemp(dir=ROOT, prefix=".env.")
with os.fdopen(fd, "w") as handle:
    handle.write("\n".join(lines) + "\n")
os.chmod(tmp, 0o600)
os.replace(tmp, ENV_FILE)

print(f"filled:   {', '.join(filled) or '—'}")
print(f"appended: {', '.join(appended) or '—'}")
print(f"kept (already set; use --force to overwrite): {', '.join(kept) or '—'}")
