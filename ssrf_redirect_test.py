import http.server
import threading
import time
import urllib.parse
from lgwks_browser import _remote_allowed

# Test a URL that is "publicly looking" (like a real domain)
# But _remote_allowed will block it if it resolves to a loopback/private IP.
target_url = "http://127.0.0.1.nip.io/foo"

allowed = _remote_allowed(target_url)
print(f"Target: {target_url} | Allowed: {allowed}")

# This tests the RE-resolution guard we added. 
# But the "Real" vulnerability is that even if we block '127.0.0.1.nip.io',
# if we allowed 'google.com' and google.com redirected to 127.0.0.1, 
# the underlying HTTP client (playwright/httpx) might follow it.
