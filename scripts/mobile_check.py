import json
from playwright.sync_api import sync_playwright

PAGES   = "http://127.0.0.1:8081/"
BACKEND = "http://127.0.0.1:8000/?k=ctrl-72fedb10ad5f5933"
VIEWPORTS = [(320,568,"se"), (360,640,"android"), (390,844,"iphone12"), (414,896,"xr"), (768,1024,"tablet")]

def wide_els(page):
    return page.evaluate("""() => [...document.querySelectorAll('*')]
      .map(e => ({t:e.tagName, c:(e.className||'').toString().slice(0,28),
                  r:e.getBoundingClientRect().right, l:e.getBoundingClientRect().left}))
      .filter(o => o.r > window.innerWidth + 1 || o.l < -1).slice(0,6)""")

with sync_playwright() as pw:
    b = pw.chromium.launch()
    report = []
    for label, url in [("pages", PAGES), ("backend", BACKEND)]:
        for w, h, tag in VIEWPORTS:
            ctx = b.new_context(viewport={"width": w, "height": h},
                                device_scale_factor=2, is_mobile=True, has_touch=True,
                                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                                           "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148")
            pg = ctx.new_page()
            pg.goto(url, wait_until="load", timeout=45000)
            pg.wait_for_timeout(7000)
            sw = pg.evaluate("document.documentElement.scrollWidth")
            cw = pg.evaluate("document.documentElement.clientWidth")
            over = pg.evaluate("document.body.scrollWidth - window.innerWidth")
            wid = wide_els(pg)
            txt = pg.evaluate("document.getElementById('status') ? document.getElementById('status').textContent : ''")
            pg.screenshot(path=f"/workspace/fly/out/m_{label}_{tag}.png", full_page=True)
            report.append(dict(site=label, vp=f"{w}x{h}", doc_scrollWidth=sw, clientWidth=cw,
                               overflow_px=over, widest_offenders=wid, status=txt))
            print(f"{label:8s} {tag:9s} {w}x{h}  scrollW={sw} clientW={cw} overflow={over}px  status={txt[:44]}")
            if wid: print("           offenders:", json.dumps(wid)[:220])
            ctx.close()
    b.close()
    json.dump(report, open("/workspace/fly/out/mobile_report.json","w"), indent=1)
print("screenshots in /workspace/fly/out/")
