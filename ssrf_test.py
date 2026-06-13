import urllib.parse
from lgwks_substrate_crawl import _canonicalize_crawl_url
from lgwks_browser import _remote_allowed

urls = [
    "http://127.0.0.1",
    "http://localhost",
    "http://169.254.169.254/latest/meta-data/",
    "http://metadata.google.internal",
    "file:///etc/passwd",
    "gopher://127.0.0.1:6379",
    "http://2130706433",
    "http://0x7f000001",
    "http://127.0.0.1.xip.io"
]

for u in urls:
    canon = _canonicalize_crawl_url(u)
    allowed = _remote_allowed(canon)
    print(f"URL: {u:40} | Canon: {canon:40} | Allowed: {allowed}")
