"""`make eval-local`: the real stack for `make eval` on this machine (spec 10 T6). From the repo root:

    PYTHONPATH=packages:apps/api:apps/mcp python -m eval.local [--gold DIR] [--provider bedrock|fake]

One process serves, on 127.0.0.1 only, the store-backed api with the evaluation hooks (:8000) and the real MCP server
(:8001, `mcp_server.__main__.build`, a fresh 48-hex key per start) over ONE in-memory store and gold read-only. It
starts `langgraph dev` (:2024) on `langgraph.json`, so the api reaches the real `dispute_intake` graph through its own
Platform client (`app.platform.HttpPlatform`) and the graph reaches the MCP server through `MCP_URL`, as on Platform.
Ctrl-C stops everything; nothing is written but the in-memory store (and `.langgraph_api/`, git-ignored).

Safety: no `.env` is read and `DATABASE_URL` is dropped, so no database is touched; the MCP URL is local; no Telegram or
e-mail is ever sent (a notifier that refuses every send). S1 reaches Bedrock with the AWS profile (`AWS_PROFILE`,
default `nickoftime`, us-east-2); S0 calls no model. Replay "today" is pinned to 2026-06-01 (ADR 0020).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional
from unittest import mock

import httpx

ROOT = Path(__file__).resolve().parents[2]
LOOPBACK = "127.0.0.1"
DEMO_TODAY = "2026-06-01"            # ADR 0020: the replay "today" the eval cases were derived with
HIGH = "1000000"                     # the abuse guard's hourly limits are for the public demo, not a local eval


class NoChannels:
    """Notifier that never sends: eval sessions have no channel, and a local run must not reach Telegram or Resend."""

    def telegram(self, chat_id: str, text: str) -> Optional[str]:
        from app.notify import ChannelFailed
        raise ChannelFailed("the local eval stack sends nothing")

    def email(self, to: str, subject: str, text: str) -> Optional[str]:
        from app.notify import ChannelFailed
        raise ChannelFailed("the local eval stack sends nothing")


def git_sha() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.strip()
        return sha.stdout.strip() + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return os.getenv("GIT_SHA", "unknown")


def graph_env(mcp_url: str, key: str, provider: str) -> dict[str, str]:
    """The graph process's environment: the local MCP server and the arm's provider; nothing from a `.env`."""
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "MCP_URL", "MCP_API_KEY")}
    env.update({"MCP_URL": mcp_url, "MCP_API_KEY": key, "LLM_PROVIDER": provider, "DEMO_TODAY": DEMO_TODAY,
                "LANGSMITH_TRACING": "false", "LANGCHAIN_TRACING_V2": "false",
                "PYTHONPATH": os.pathsep.join([str(ROOT), str(ROOT / "packages")])})
    if provider == "bedrock":
        env.setdefault("AWS_PROFILE", "nickoftime")
        env.setdefault("AWS_REGION", "us-east-2")
    return env


def start_graph(port: int, env: dict[str, str]) -> subprocess.Popen:
    cli = shutil.which("langgraph", path=str(Path(sys.executable).parent)) or shutil.which("langgraph")
    if cli is None:
        raise SystemExit('langgraph dev is missing: pip install "langgraph-cli[inmem]>=0.4" (requirements.txt note)')
    return subprocess.Popen([cli, "dev", "--config", "langgraph.json", "--host", LOOPBACK, "--port", str(port),
                             "--no-browser", "--no-reload", "--allow-blocking", "--n-jobs-per-worker", "4"],
                            cwd=ROOT, env=env)            # 4 = the harness's default concurrency (spec 10 §5)


def wait_ok(url: str, process: subprocess.Popen, seconds: float = 120) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit(f"langgraph dev exited with {process.returncode}")
        try:
            if httpx.get(f"{url}/ok", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise SystemExit(f"the graph server at {url} did not answer /ok in {seconds:.0f} s")


def build(gold_path: Path, key: str, graph_url: str):
    """(api app, mcp app): one MemoryStore and one Gold shared by the api, the hooks and the MCP server."""
    from app.catalog import GoldCatalog
    from app.live import create_live_app
    from app.platform import HttpPlatform
    from eval.local.hooks import RecordingPlatform, add_eval_routes, run_meta
    from mcp_server import __main__ as entry
    from mcp_server.gold import Gold
    from nick_of_time.policy import load_policies
    from nick_of_time.store.memory import MemoryStore

    store, gold = MemoryStore(), Gold(gold_path)
    with mock.patch.object(entry, "open_store", lambda _env: (store, "memory")), \
            mock.patch.object(entry, "Gold", lambda _path: gold):
        mcp = entry.build({"MCP_API_KEY": key, "GOLD_PATH": str(gold_path)})   # the entry point's own wiring
    platform = RecordingPlatform(HttpPlatform(graph_url, "local-langgraph-dev"))    # langgraph dev checks no key
    catalog = GoldCatalog(gold_path)
    api = create_live_app(store, catalog=catalog, platform=platform, notifier=NoChannels())
    sha, version = git_sha(), load_policies().version
    add_eval_routes(api, store=store, gold=gold, catalog=catalog, platform=platform,
                    meta=lambda arm: run_meta(arm, git_sha=sha, policies_version=version,
                                              platform_revision="local langgraph dev"),
                    now=lambda: dt.datetime.now(dt.timezone.utc))
    return api, mcp


async def serve(api, mcp, api_port: int, mcp_port: int) -> None:
    import uvicorn

    servers = [uvicorn.Server(uvicorn.Config(app, host=LOOPBACK, port=port, log_level="warning", workers=1))
               for app, port in ((mcp, mcp_port), (api, api_port))]
    await asyncio.gather(*(server.serve() for server in servers))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.local", description=__doc__.split("\n\n")[0])
    parser.add_argument("--gold", type=Path, default=Path(os.getenv("GOLD_PATH") or ROOT / "data/gold"))
    parser.add_argument("--provider", choices=("bedrock", "fake"), default="bedrock",
                        help="LLM provider of S1/S2 (S0 calls none); fake answers nothing, so S1 runs as S0")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--mcp-port", type=int, default=8001)
    parser.add_argument("--graph-port", type=int, default=2024)
    args = parser.parse_args(argv)

    gold = args.gold.resolve()
    if "gold_eval" in gold.parts or not (gold / "transactions_enriched.parquet").is_file():
        raise SystemExit(f"{gold} is not a gold folder (make gold-pull); gold_eval is never read")
    os.environ.pop("DATABASE_URL", None)                    # the in-memory store only, never a database
    os.environ.update({"DEMO_TODAY": DEMO_TODAY, "LLM_PROVIDER": args.provider, "RATE_SESSIONS_PER_IP_HOUR": HIGH,
                       "RATE_SESSIONS_GLOBAL_HOUR": HIGH, "RATE_TURNS_PER_IP_HOUR": HIGH,
                       "RATE_TURNS_GLOBAL_HOUR": HIGH})
    key = secrets.token_hex(24)                             # per start, never printed; not a deployed secret
    mcp_url = f"http://{LOOPBACK}:{args.mcp_port}/mcp"
    graph_url = f"http://{LOOPBACK}:{args.graph_port}"
    graph = start_graph(args.graph_port, graph_env(mcp_url, key, args.provider))
    try:
        wait_ok(graph_url, graph)
        api, mcp = build(gold, key, graph_url)
        print(f"eval stack ready: api http://{LOOPBACK}:{args.api_port} (EVAL_MODE hooks) · MCP {mcp_url} · graph "
              f"{graph_url} · gold {gold} · provider {args.provider} · now run `make eval` in another shell", flush=True)
        asyncio.run(serve(api, mcp, args.api_port, args.mcp_port))
    except KeyboardInterrupt:
        pass
    finally:
        if graph.poll() is None:
            graph.terminate()
            try:
                graph.wait(timeout=15)
            except subprocess.TimeoutExpired:
                graph.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
