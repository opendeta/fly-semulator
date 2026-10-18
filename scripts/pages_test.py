import json, urllib.request
from playwright.sync_api import sync_playwright
CK="ctrl-72fedb10ad5f5933"
with sync_playwright() as pw:
    b=pw.chromium.launch()
    pg=b.new_context(viewport={"width":390,"height":844},is_mobile=True,has_touch=True).new_page()
    pg.goto(f"http://127.0.0.1:8081/?k={CK}", wait_until="load", timeout=45000)
    pg.wait_for_timeout(9000)
    st=pg.evaluate("document.getElementById('status').textContent")
    print("status line:", st)
    print("video src:", pg.evaluate("document.getElementById('vid').src")[:70])
    before=json.load(urllib.request.urlopen(f"{st.split('·')[1].strip().replace('https://','https://')}/api/state?k={CK}")) if False else None
    # click a light button on the PAGES site and verify the backend world changed
    import urllib.request as u
    url="http://127.0.0.1:8000"
    s0=json.load(u.urlopen(f"{url}/api/state?k={CK}"))
    pg.click("text=◀ light"); pg.wait_for_timeout(2500)
    s1=json.load(u.urlopen(f"{url}/api/state?k={CK}"))
    print(f"light.x {s0['light']['x']} -> {s1['light']['x']}   auto {s0['auto']} -> {s1['auto']}")
    print("toast:", repr(pg.evaluate("document.getElementById('toast').textContent")))
    pg.screenshot(path="/workspace/fly/out/pages_after_fix.png", full_page=False)
    b.close()
