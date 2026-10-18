"""End-to-end test against the REAL public GitHub Pages site."""
import json, urllib.request
from playwright.sync_api import sync_playwright
CK = "ctrl-72fedb10ad5f5933"
SITE = "https://opendeta.github.io/fly-semulator/?k=" + CK
BACK = "http://127.0.0.1:8000"
def st(): return json.load(urllib.request.urlopen(f"{BACK}/api/state?k={CK}"))

with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_context(viewport={"width":390,"height":844}, is_mobile=True,
                       has_touch=True, device_scale_factor=2).new_page()
    pg.goto(SITE, wait_until="load", timeout=60000)
    pg.wait_for_timeout(11000)
    print("status line :", pg.evaluate("document.getElementById('status').textContent"))
    print("video src   :", pg.evaluate("document.getElementById('vid').src")[:78])
    print("control key :", "set" if pg.evaluate("localStorage.getItem('flyctrl')") else "MISSING")
    print("buttons     :", pg.evaluate("[...document.querySelectorAll('button')].map(b=>b.textContent.trim())"))

    s0 = st(); pg.locator("button").nth(0).click(); pg.wait_for_timeout(2500); s1 = st()
    print(f"light_left  : light.x {s0['light']['x']} -> {s1['light']['x']}   auto {s0['auto']} -> {s1['auto']}")
    print("toast       :", repr(pg.evaluate("document.getElementById('toast').textContent")))

    s0 = st(); pg.locator("button").nth(5).click(); pg.wait_for_timeout(2200); s1 = st()
    print(f"light OFF   : {s0['light']['on']} -> {s1['light']['on']}")
    s0 = st(); pg.locator("button").nth(4).click(); pg.wait_for_timeout(2200); s1 = st()
    print(f"light ON    : {s0['light']['on']} -> {s1['light']['on']}")

    print("state rows  :", pg.evaluate("[...document.querySelectorAll('.row')].map(r=>r.textContent).slice(0,3)"))
    print("overflow    :", pg.evaluate("document.documentElement.scrollWidth - window.innerWidth"), "px")
    pg.screenshot(path="/workspace/fly/out/live_pages_mobile.png", full_page=False)
    pg.screenshot(path="/workspace/fly/out/live_pages_full.png", full_page=True)
    b.close()
print("DONE")
