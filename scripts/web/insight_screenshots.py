"""Spec 12 T7: screenshots of /evaluation, /analytics and /data on the public URL, with a horizontal-overflow check.

Drives a local headless Chrome through the DevTools Protocol (no Playwright): desktop 1280 px and mobile 390 px, the
light and the dark theme (next-themes reads `theme` from localStorage), plus one shot of a chart tooltip opened with the
Tab key (AC-07). Writes PNGs and report.json; `scrollWidth > clientWidth` means the page scrolls sideways (AC-09).

    python scripts/web/insight_screenshots.py OUT_DIR [--base URL]      # needs Google Chrome and `pip install websockets`
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import subprocess
import tempfile
import time
import urllib.request

import websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PAGES = ("/evaluation", "/analytics", "/data")
VIEWS = (("desktop", 1280, 900, False), ("mobile", 390, 844, True))
THEMES = ("light", "dark")
PORT = 9333


class Page:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def call(self, method: str, **params):
        self.n += 1
        await self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            message = json.loads(await self.ws.recv())
            if message.get("id") == self.n:
                return message.get("result", message)

    async def value(self, expression: str):
        return (await self.call("Runtime.evaluate", expression=expression, returnByValue=True))["result"].get("value")

    async def shot(self, path: str, full: bool) -> None:
        data = await self.call("Page.captureScreenshot", format="png", captureBeyondViewport=full)
        with open(path, "wb") as target:
            target.write(base64.b64decode(data["data"]))


async def run(out: str, base: str) -> list[dict]:
    profile = tempfile.mkdtemp(prefix="nick-shots-")
    chrome = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={PORT}", "--disable-gpu",
                               "--hide-scrollbars", f"--user-data-dir={profile}", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                break
            except OSError:
                time.sleep(0.2)
        url = next(t["webSocketDebuggerUrl"] for t in targets if t["type"] == "page")
        async with websockets.connect(url, max_size=50_000_000) as ws:
            page, report = Page(ws), []
            for path in PAGES:
                for view, width, height, mobile in VIEWS:
                    for theme in THEMES:
                        await page.call("Emulation.setDeviceMetricsOverride", width=width, height=height,
                                        deviceScaleFactor=1, mobile=mobile)
                        await page.call("Page.navigate", url=base + path)
                        await asyncio.sleep(2)
                        await page.value(f"localStorage.setItem('theme', '{theme}')")
                        await page.call("Page.reload")
                        await asyncio.sleep(4)
                        size = await page.value("({sw: document.documentElement.scrollWidth, cw: document.documentElement"
                                                ".clientWidth, h: document.documentElement.scrollHeight, dark: document"
                                                ".documentElement.classList.contains('dark')})")
                        await page.call("Emulation.setDeviceMetricsOverride", width=width, height=min(size["h"], 6000),
                                        deviceScaleFactor=1, mobile=mobile)
                        await asyncio.sleep(1)
                        name = f"{path.strip('/')}-{view}-{theme}.png"
                        await page.shot(f"{out}/{name}", full=True)
                        report.append({"page": path, "view": view, "width": width, "theme": theme,
                                       "dark_class": size["dark"], "scroll_width": size["sw"],
                                       "client_width": size["cw"], "overflow_x": size["sw"] > size["cw"],
                                       "file": name})
            await page.call("Emulation.setDeviceMetricsOverride", width=1280, height=900, deviceScaleFactor=1,
                            mobile=False)
            await page.call("Page.navigate", url=base + "/analytics")
            await asyncio.sleep(4)
            label = None
            for _ in range(40):                              # real Tab presses, so :focus-visible and the tooltip fire
                for kind in ("rawKeyDown", "keyUp"):
                    await page.call("Input.dispatchKeyEvent", type=kind, key="Tab", code="Tab",
                                    windowsVirtualKeyCode=9)
                label = await page.value("document.activeElement && document.activeElement.getAttribute('aria-label')")
                if label and "complaints" in label:
                    break
            await asyncio.sleep(1)
            await page.shot(f"{out}/analytics-desktop-dark-keyboard-focus.png", full=False)
            report.append({"page": "/analytics", "view": "desktop", "keyboard_focus": label,
                           "file": "analytics-desktop-dark-keyboard-focus.png"})
            return report
    finally:
        chrome.terminate()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--base", default="https://nickoftime.salazarvalverdeai.com")
    args = parser.parse_args()
    report = asyncio.run(run(args.out, args.base))
    with open(f"{args.out}/report.json", "w", encoding="utf-8") as target:
        json.dump({"base": args.base, "taken_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "shots": report}, target, indent=1)
        target.write("\n")
    bad = [shot for shot in report if shot.get("overflow_x")]
    print(f"{len(report)} shots, {len(bad)} with horizontal overflow")


if __name__ == "__main__":
    main()
