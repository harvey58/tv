#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_sites.py
合并 18.json 中所有 url 指向文件的 "sites" 部分并去重。

用法:
  python3 merge_sites.py --input 18.json --output files/merged_sites.json

说明:
- 支持 input 为仓库内相对路径（如 18.json）或任意可访问的 URL（raw.githubusercontent.com、gh-proxy、其他）。
- 默认会对每个目标 URL 发起 GET 请求，解析 JSON 或通过正则提取 "sites": [ ... ]。
- 去重依据为 site 对象的规范化 JSON（键排序）；如果你希望按某个字段（比如 site["url"]）去重，请告诉我我会改脚本。
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
from typing import Any, Dict, List, Set
from urllib.parse import urlparse

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; merge-sites-script/1.0)"
}

SITES_REGEX = re.compile(r'"sites"\s*:\s*(\[[\s\S]*?\])', re.IGNORECASE)


def load_input(path_or_url: str) -> Dict[str, Any]:
    p = urlparse(path_or_url)
    if p.scheme in ("http", "https"):
        print(f"[INFO] Fetching input JSON from URL: {path_or_url}")
        r = requests.get(path_or_url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.json()
    else:
        print(f"[INFO] Loading input JSON from local file: {path_or_url}")
        with open(path_or_url, "r", encoding="utf-8") as f:
            return json.load(f)


def normalize_site(item: Any) -> str:
    return json.dumps(item, ensure_ascii=False, sort_keys=True)


def extract_sites_from_text(text: str) -> List[Any]:
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "sites" in obj and isinstance(obj["sites"], list):
            return obj["sites"]
        if isinstance(obj, list):
            # maybe the file is already the sites array
            return obj
    except Exception:
        pass

    m = SITES_REGEX.search(text)
    if m:
        arr_text = m.group(1)
        try:
            arr = json.loads(arr_text)
            if isinstance(arr, list):
                return arr
        except Exception:
            cleaned = re.sub(r",\s*([\]\}])", r"\1", arr_text)
            try:
                arr = json.loads(cleaned)
                if isinstance(arr, list):
                    return arr
            except Exception:
                pass
    return []


def fetch_and_extract(url: str, timeout: int = 25) -> List[Any]:
    if not url:
        return []
    print(f"[INFO] GET {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            print(f"[WARN] {url} returned HTTP {r.status_code}")
            return []
        text = r.text
        # try JSON parse
        try:
            obj = r.json()
            if isinstance(obj, dict) and "sites" in obj and isinstance(obj["sites"], list):
                return obj["sites"]
            if isinstance(obj, list):
                return obj
            if isinstance(obj, dict):
                sites = obj.get("sites")
                if isinstance(sites, list):
                    return sites
        except Exception:
            pass
        # fallback regex extraction
        sites = extract_sites_from_text(text)
        if sites:
            return sites
        print(f"[INFO] No 'sites' found in {url}")
        return []
    except Exception as e:
        print(f"[ERROR] Failed to fetch {url}: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="Merge 'sites' from URLs listed in 18.json")
    parser.add_argument("--input", "-i", default="18.json", help="input 18.json path or raw URL")
    parser.add_argument("--output", "-o", default="files/merged_sites.json", help="output JSON file path")
    parser.add_argument("--delay", "-d", type=float, default=0.5, help="delay seconds between requests")
    parser.add_argument("--max", type=int, default=0, help="max number of urls to process (0 = all)")
    args = parser.parse_args()

    try:
        data = load_input(args.input)
    except Exception as e:
        print(f"[FATAL] Failed to load input: {e}")
        sys.exit(1)

    urls = []
    if isinstance(data, dict) and "urls" in data and isinstance(data["urls"], list):
        for entry in data["urls"]:
            if isinstance(entry, dict):
                u = entry.get("url") or entry.get("Url") or entry.get("link")
                if u:
                    urls.append(u)
            elif isinstance(entry, str):
                urls.append(entry)
    else:
        print("[WARN] Input JSON does not contain top-level 'urls' list. Attempting to find URLs by regex...")
        for m in re.finditer(r"https?://[^\s'\",]+", json.dumps(data)):
            urls.append(m.group(0))

    print(f"[INFO] Found {len(urls)} urls. Processing up to {args.max or 'ALL'}")

    merged: List[Any] = []
    seen: Set[str] = set()
    processed = 0
    for u in urls:
        if args.max and processed >= args.max:
            break
        sites = fetch_and_extract(u)
        for s in sites:
            key = normalize_site(s)
            if key not in seen:
                seen.add(key)
                merged.append(s)
        processed += 1
        time.sleep(args.delay)

    print(f"[INFO] Total unique sites collected: {len(merged)}")

    out = {"sites": merged}
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[INFO] Wrote merged sites to {args.output}")


if __name__ == "__main__":
    main()