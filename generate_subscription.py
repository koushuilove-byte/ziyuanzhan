#!/usr/bin/env python3
"""
generate_subscription.py — 从 ziyuanzhan 监测数据生成可用的订阅 JSON
=====================================================================
输入：docs/data/online.json（在线资源站，由 monitor.py 生成）
输出：
  docs/data/subscription-libretv.json  LibreTV / MoonTVPlus 原生订阅（LibreTV-SourceList 格式）
  docs/data/subscription-tvbox.json    TVBOX 配置格式（sites，type=1 JSON 接口）

生成的 JSON 可部署到任意静态托管（GitHub Pages / Gist / 对象存储），
然后在 LibreTV「设置 → 订阅管理」里粘贴 JSON 的 URL 一键导入全部在线采集站。

用法：
  python3 generate_subscription.py

依赖：仅 Python 3.9+ 标准库（无需第三方包）。
"""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
INPUT = os.path.join(HERE, "docs", "data", "online.json")
OUT_LIBRETV = os.path.join(HERE, "docs", "data", "subscription-libretv.json")
OUT_TVBOX = os.path.join(HERE, "docs", "data", "subscription-tvbox.json")

SUBSCRIPTION_NAME = "ziyuanzu-在线资源站"
MAX_VOD_SOURCES = 100  # 与 LibreTV MAX_VOD_SOURCES 对齐

ADULT_TAG_HINTS = ("成人", "av", "porn", "色情")
CMS_API_PATTERN = re.compile(r"/api\.php/provide/vod/?$", re.I)


def is_adult(tags: list) -> bool:
    return any(h in str(t).lower() for t in tags for h in ADULT_TAG_HINTS)


def normalize_api_url(url: str) -> str | None:
    """LibreTV 的 normalizeUrl(trimTrailingSlash=true)：http(s) + 去尾斜杠"""
    if not isinstance(url, str):
        return None
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        return None
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return None
    except Exception:
        return None
    return url.rstrip("/")


def build_vod_sources(records: list[dict]) -> list[dict]:
    """过滤在线 + 有效 api，去重，按评分/资源量排序，生成点播源列表"""
    seen: set[str] = set()
    sources: list[dict] = []
    for r in records:
        if not r.get("health", {}).get("is_alive"):
            continue
        api = normalize_api_url(r.get("api", ""))
        if not api:
            continue
        if api in seen:
            continue
        seen.add(api)
        sources.append(
            {
                "name": (r.get("name") or "").strip() or urlparse(api).hostname or api,
                "url": api,
                "detail": (r.get("description") or "").strip(),
                "isAdult": is_adult(r.get("tags", [])),
                # 排序用内部字段（写出前删除）
                "_rating": r.get("rating") if isinstance(r.get("rating"), (int, float)) else 0,
                "_count": r.get("resource_count") if isinstance(r.get("resource_count"), (int, float)) else 0,
            }
        )
    sources.sort(key=lambda s: (-s.pop("_rating"), -s.pop("_count")))
    return sources[:MAX_VOD_SOURCES]


def build_tvbox_sites(sources: list[dict]) -> list[dict]:
    """LibreTV TVBOX 解析要求：api 为空或 type!=1 但命中 /api.php/provide/vod/ 也能导入；
    显式给出 type=1（JSON）与 searchable=1（可搜索）最稳妥。"""
    sites = []
    key_base = 1
    for s in sources:
        host = urlparse(s["url"]).hostname or "src"
        key = host.replace(".", "").replace("-", "")[:24] or f"src{key_base}"
        if any(site["key"] == key for site in sites):
            key = f"{key}{key_base}"
        sites.append(
            {
                "key": key,
                "name": s["name"],
                "api": s["url"],
                "type": 1,          # 0=XML, 1=JSON
                "searchable": 1,    # 允许搜索
                "filterClass": 0,
                "ext": "",
            }
        )
        key_base += 1
    return sites


def main() -> int:
    if not os.path.exists(INPUT):
        print(f"[ERROR] 找不到 {INPUT}，请先运行 monitor.py 生成在线数据", file=sys.stderr)
        return 1

    with open(INPUT, encoding="utf-8") as f:
        online = json.load(f)
    records = online.get("data", [])
    if not records:
        print("[WARN] online.json 中没有在线资源站", file=sys.stderr)

    sources = build_vod_sources(records)
    print(f"[INFO] 输入在线站点 {len(records)}，生成点播源 {len(sources)} 个")

    libretv_payload = {
        "name": SUBSCRIPTION_NAME,
        "sources": sources,
        "liveSources": [],
    }
    tvbox_payload = {
        "name": SUBSCRIPTION_NAME,
        "sites": build_tvbox_sites(sources),
        "lives": [],
    }

    for path, payload in ((OUT_LIBRETV, libretv_payload), (OUT_TVBOX, tvbox_payload)):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[INFO] 已生成: {path}")

    print("[OK] 订阅 JSON 生成完毕。部署到静态地址后，把 URL 填入 LibreTV 订阅管理即可。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())