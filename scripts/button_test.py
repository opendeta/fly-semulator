"""Click every control button in a real browser and verify the fly world actually changes."""
import json, urllib.request
from playwright.sync_api import sync_playwright

CK = "ctrl-72fedb10ad5f5933"
BASE = "http://127.0.0.1:8000"
def state():
    return json.load(urllib.request.urlopen(f"{BASE}/api/state?k={CK}"))

results = []
def check(name, before, after, key, expect_change=True):
    b, a = before[key], after[key]
    ok = (b != a) if expect_change else (b == a)
    results.append((name, ok, f"{key}: {b} -> {a}"))
    print(("PASS " if ok else "FAIL ") + f"{name:26s} {key}: {b} -> {a}")

with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_context(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True).new_page()
    pg.goto(f"{BASE}/?k={CK}", wait_until="load", timeout=45000)
    pg.wait_for_timeout(9000)

    # 1. manual light move must work (and turn auto-drift off)
    before = state()
    pg.click("text=◀ light"); pg.wait_for_timeout(2500)
    after = state()
    check("light_left moves light", before, after, "light_x" if "light_x" in before else "light")
    check("  auto-drift turned off", {"a":before["auto"]}, {"a":after["auto"]}, "a", expect_change=(before["auto"] is True))
    check("  light.x changed", {"x":before["light"]["x"]}, {"x":after["light"]["x"]}, "x")

    # 2. light ON/OFF
    before = state()
    pg.click("text=⚫ OFF"); pg.wait_for_timeout(2200)
    after = state()
    check("light OFF", {"v":before["light"]["on"]}, {"v":after["light"]["on"]}, "v")
    before = state()
    pg.click("text=💡 ON"); pg.wait_for_timeout(2200)
    after = state()
    check("light ON", {"v":before["light"]["on"]}, {"v":after["light"]["on"]}, "v")

    # 3. auto-drift toggle back on
    before = state()
    pg.click("text=🔄 auto"); pg.wait_for_timeout(2200)
    after = state()
    check("auto-drift toggled", {"v":before["auto"]}, {"v":after["auto"]}, "v")

    # 4. pause / resume
    before = state()
    pg.click("text=⏯ pause"); pg.wait_for_timeout(2500)
    after = state()
    check("pause stops sim clock", {"t":before["t"]}, {"t":after["t"]}, "t", expect_change=False)
    pg.click("text=⏯ pause"); pg.wait_for_timeout(2000)

    # 5. slider command
    before = state()
    pg.evaluate("cmd('speed', 1.7)")
    pg.wait_for_timeout(2500)
    after = state()
    check("speed slider", {"v":before["speed"]}, {"v":after["speed"]}, "v")

    # 6. toast appeared?
    t = pg.evaluate("document.getElementById('toast').textContent")
    print("toast text:", repr(t))
    pg.screenshot(path="/workspace/fly/out/button_test.png", full_page=True)
    b.close()

fails = [r for r in results if not r[1]]
print(f"\n{len(results)-len(fails)}/{len(results)} checks passed")
