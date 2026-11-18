"""Opt-in supervisor for this repository's local demo API, never remote clients."""
import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import os
from pathlib import Path
import socket
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]


class LocalSandbox:
    def __init__(self):
        self.process = None
        self.task = None
        self.log = None

    @staticmethod
    def reachable():
        try:
            with socket.create_connection(("127.0.0.1", 8100), timeout=.2): return True
        except OSError: return False

    def start(self):
        if not (ROOT / "data/judging-client.sqlite").exists():
            return  # Never create or replace a client dataset automatically.
        directory = ROOT / "validation/runtime-logs"
        directory.mkdir(parents=True, exist_ok=True)
        name = "managed-client-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8] + ".log"
        self.log = (directory / name).open("x", encoding="utf-8")
        environment = {**os.environ, "CLIENT_DB": str(ROOT / "data/judging-client.sqlite"),
                       "CLIENT_TABLES": "customer_accounts,supplier_directory,warehouse_orders", "CLIENT_INITIALIZE_SAMPLE": "0"}
        try:
            self.process = subprocess.Popen([sys.executable, "-m", "uvicorn", "prototype_client.app:app", "--host", "127.0.0.1", "--port", "8100"],
                                            cwd=ROOT, env=environment, stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError:
            self.log.close();self.log = None
            raise

    async def watch(self):
        delay = 2
        while True:
            if self.process and self.process.poll() is not None:
                self.process = None
                if self.log:self.log.close();self.log = None
                delay = min(30, delay * 2)
            if not self.process and not self.reachable():
                try:self.start()
                except OSError:pass  # Health checks report the real unavailable service.
            if self.reachable():delay = 2
            await asyncio.sleep(delay)

    async def __aenter__(self):
        if os.getenv("AVENTRA_LOCAL_SANDBOX_ENABLED", "false").lower() == "true":
            self.task = asyncio.create_task(self.watch())
            for _ in range(40):
                if self.reachable():break
                await asyncio.sleep(.25)
        return self

    async def __aexit__(self, *args):
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):await self.task
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:await asyncio.to_thread(self.process.wait, timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill();await asyncio.to_thread(self.process.wait, timeout=5)
        if self.log:self.log.close()
