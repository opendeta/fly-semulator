#!/usr/bin/env python3
"""Download the public-domain / CC clips the fly is trained on (Wikimedia Commons)."""
import json, os, time, urllib.request

API = "https://commons.wikimedia.org/w/api.php"
WANT = {"File:Moon (30549457916).webm": "moon.webm",
        "File:Flying bee on flower in slow motion V.2.webm": "bee.webm",
        "File:Bumble bees on Joe Pye Weed (36722955862).webm": "bumblebees.webm",
        "File:Moon rising over Joshua Trees (29952161293).webm": "moonrise.webm",
        "File:Bee morning glory visitors.webm": "morningglory.webm"}
OUT = os.environ.get("FLY_VIDEOS_DIR", "/workspace/fly/videos")

def main():
    os.makedirs(OUT, exist_ok=True)
    for title, name in WANT.items():
        dest = os.path.join(OUT, name)
        if os.path.exists(dest):
            print("have", name); continue
        url = API + "?action=query&format=json&prop=imageinfo&iiprop=url&titles=" + urllib.parse.quote(title)
        req = urllib.request.Request(url, headers={"User-Agent": "flylab/1.0"})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        page = list(d["query"]["pages"].values())[0]
        src = page["imageinfo"][0]["url"]
        print("downloading", name)
        data = urllib.request.urlopen(urllib.request.Request(src, headers={"User-Agent": "flylab/1.0"}), timeout=120).read()
        open(dest, "wb").write(data)
        time.sleep(10)          # be polite to Wikimedia

if __name__ == "__main__":
    import urllib.parse
    main()
