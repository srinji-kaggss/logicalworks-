"""
lgwks_site_profile — site configuration profile manager.

Loads custom crawling and DOM parsing configurations from JSON profiles
under `config/sites/` based on target URL hostnames.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROFILES_DIR = ROOT / "config" / "sites"

# Default profile settings
DEFAULT_PROFILE: dict[str, Any] = {
    "host": "*",
    "dom": {
        "chrome_tags": [
            "nav", "header", "footer", "script", "style", "noscript",
            "iframe", "button", "dialog", "form"
        ],
        "chrome_class_patterns": [
            "topnav", "dropdown", "toolbar", "breadcrumb", "sidebar",
            "banner", "cookie", "gdpr", "modal", "popup", "menu",
            "ad-container", "navbar", "social"
        ],
        "heading_tags": ["h1", "h2", "h3", "h4", "h5", "h6"]
    },
    "crawl": {
        "scope_prefix": "",
        "max_depth": 5,
        "delay_s": 1.5,
        "respect_robots": True
    }
}


def _get_host(url: str) -> str:
    """Extract host from URL."""
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    return (parsed.hostname or "").lower()


def load_profile(url_or_host: str) -> dict[str, Any]:
    """Load a site profile matching the URL's host or direct hostname.
    Falls back to default profile if no matching file exists in `config/sites/`.
    """
    host = _get_host(url_or_host) if "://" in url_or_host else url_or_host.lower()

    # Hardening (#154 M6): a direct hostname is attacker-influenced and bypasses
    # urlparse. Strip it to the DNS-legal charset so it cannot carry path
    # separators or `..` and turn the candidate `.exists()` probe into a
    # file-existence oracle for paths outside config/sites/.
    if host and not re.fullmatch(r"[A-Za-z0-9.\-]+", host):
        host = ""

    profiles_root = PROFILES_DIR.resolve()
    # Try exact hostname profile, then parent domains
    profile_path = None
    if host:
        parts = host.split(".")
        # Check subdomains up to root domain (e.g. estandards.fundserv.com, fundserv.com)
        for i in range(len(parts) - 1):
            domain = ".".join(parts[i:])
            candidate = PROFILES_DIR / f"{domain}.json"
            # Defense in depth: never probe outside the profiles directory.
            if not str(candidate.resolve()).startswith(str(profiles_root) + os.sep):
                continue
            if candidate.exists():
                profile_path = candidate
                break
                
    profile = json.loads(json.dumps(DEFAULT_PROFILE))  # deep copy
    
    if profile_path and profile_path.exists():
        try:
            with open(profile_path, "r", encoding="utf-8") as fh:
                custom = json.load(fh)
                
            # Merge dom settings
            if "dom" in custom:
                for k, v in custom["dom"].items():
                    profile["dom"][k] = v
            # Merge crawl settings
            if "crawl" in custom:
                for k, v in custom["crawl"].items():
                    profile["crawl"][k] = v
            profile["host"] = host
            profile["profile_source"] = str(profile_path)
        except Exception:
            pass  # degrade to default profile on load errors
            
    return profile
