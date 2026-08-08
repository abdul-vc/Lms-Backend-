import urllib.request

ports = [5173, 5174, 8080, 3000, 8000]
for p in ports:
    url = f"http://localhost:{p}/"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        res = urllib.request.urlopen(req, timeout=2)
        print(f"Port {p}: HTTP {res.status}")
    except Exception as e:
        print(f"Port {p}: {e}")
