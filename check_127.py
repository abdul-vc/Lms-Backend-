import urllib.request

ports = [5173, 5174, 8080, 8000]
for p in ports:
    url = f"http://127.0.0.1:{p}/"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        res = urllib.request.urlopen(req, timeout=1)
        print(f"127.0.0.1:{p}: HTTP {res.status}")
    except Exception as e:
        print(f"127.0.0.1:{p}: {e}")
