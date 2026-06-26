from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
HISTORY_DIR = DATA_DIR / "history"
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


@dataclass(frozen=True)
class BrandPrice:
    buy: float
    sell: float


@dataclass(frozen=True)
class WorldPrice:
    usd: float
    change: float
    change_pct: float
    vnd_chi: float | None


def _get(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    return response.text


def _number(value: str) -> float:
    cleaned = value.replace(".", "").replace(",", "").replace("đ", "").strip()
    return float(cleaned) if cleaned else 0.0


def _to_chi(value: float) -> float:
    return value / 10 if value > 150_000_000 else value


def _webgia_price(url: str, matchers: tuple[str, ...]) -> BrandPrice | None:
    try:
        soup = BeautifulSoup(_get(url), "html.parser")
        table = soup.select_one("table.table")
        if table is None:
            return None
        for row in table.select("tr"):
            text = row.get_text(" ", strip=True)
            if not any(matcher in text for matcher in matchers):
                continue
            cols = row.select("td")
            if len(cols) < 3:
                continue
            buy = _to_chi(_number(cols[1].get_text()))
            sell = _to_chi(_number(cols[2].get_text()))
            if buy > 0 and sell > 0:
                return BrandPrice(buy=buy, sell=sell)
    except Exception as exc:
        print(f"Failed to fetch {url}: {exc}", file=sys.stderr)
    return None


def fetch_pnj() -> BrandPrice | None:
    return _webgia_price("https://webgia.com/gia-vang/pnj/", ("PNJ",))


def fetch_doji() -> BrandPrice | None:
    return _webgia_price(
        "https://webgia.com/gia-vang/doji/",
        ("Hưng Thịnh Vượng", "Nhẫn tròn 999", "DOJI"),
    )


def fetch_kim_khanh() -> BrandPrice | None:
    try:
        html = _get("https://kimkhanhviethung.vn/tra-cuu-gia-vang.html")
        match = re.search(
            r"Vàng\s+999\.9.*?(\d+[\.,]\d+[\.,]\d+|\d+[\.,]\d+).*?"
            r"(\d+[\.,]\d+[\.,]\d+|\d+[\.,]\d+)",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match is None:
            return None
        buy = _to_chi(_number(match.group(1)))
        sell = _to_chi(_number(match.group(2)))
        return BrandPrice(buy=buy, sell=sell) if buy > 0 and sell > 0 else None
    except Exception as exc:
        print(f"Failed to fetch Kim Khanh Viet Hung: {exc}", file=sys.stderr)
        return None


def fetch_ngoc_thinh() -> BrandPrice | None:
    try:
        html = _get("https://ngocthinh-jewelry.vn/pages/bang-gia-vang")
        match = re.search(
            r"Vàng 9999.*?(\d{1,2}\.\d{3}\.\d{3}).*?"
            r"(\d{1,2}\.\d{3}\.\d{3})",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match is None:
            return None
        buy = _to_chi(_number(match.group(1)))
        sell = _to_chi(_number(match.group(2)))
        return BrandPrice(buy=buy, sell=sell) if buy > 0 and sell > 0 else None
    except Exception as exc:
        print(f"Failed to fetch Ngoc Thinh: {exc}", file=sys.stderr)
        return None


def fetch_world() -> WorldPrice | None:
    try:
        soup = BeautifulSoup(_get("https://giavang.org/the-gioi/"), "html.parser")
        price_el = soup.select_one(".crypto-price")
        price_usd = float(
            (price_el.get_text(strip=True) if price_el else "0").replace(",", "")
        )

        change = 0.0
        change_pct = 0.0
        change_el = soup.select_one(".crypto-change")
        if change_el is not None:
            text = change_el.get_text(" ", strip=True).replace(",", "")
            match = re.search(
                r"([+-]?\d+(?:\.\d+)?)\s*USD\s*"
                r"\(([+-]?\d+(?:\.\d+)?)\s*%\)",
                text,
            ) or re.search(
                r"([+-]?\d+(?:\.\d+)?).*?"
                r"\(([+-]?\d+(?:\.\d+)?)\s*%\)",
                text,
            )
            if match is not None:
                change = float(match.group(1))
                change_pct = float(match.group(2))
            classes = change_el.get("class") or []
            if "cred" in classes:
                change = -abs(change)
                change_pct = -abs(change_pct)

        vnd_chi = None
        box = soup.select_one(".box-content")
        if box is not None:
            match = re.search(
                r"1\s*cây\s*vàng.*?có\s*giá\s*là\s*([\d\.,]+)\s*VNĐ",
                box.get_text(" ", strip=True),
                flags=re.IGNORECASE | re.DOTALL,
            )
            if match is not None:
                vnd_tael = _number(match.group(1))
                if vnd_tael > 0:
                    vnd_chi = vnd_tael / 10

        return (
            WorldPrice(
                usd=price_usd,
                change=change,
                change_pct=change_pct,
                vnd_chi=vnd_chi,
            )
            if price_usd > 0
            else None
        )
    except Exception as exc:
        print(f"Failed to fetch world gold price: {exc}", file=sys.stderr)
        return None


def _read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    now = datetime.now(TZ)
    point_time = now.replace(minute=0, second=0, microsecond=0)
    month_key = point_time.strftime("%Y-%m")

    fetchers = {
        "Kim Khánh Việt Hùng": fetch_kim_khanh,
        "Ngọc Thịnh": fetch_ngoc_thinh,
        "PNJ": fetch_pnj,
        "DOJI": fetch_doji,
    }
    brands: dict[str, dict[str, float]] = {}
    for brand, fetcher in fetchers.items():
        price = fetcher()
        if price is not None:
            brands[brand] = {"buy": price.buy, "sell": price.sell}

    world = fetch_world()
    if not brands and world is None:
        print("No prices fetched; leaving data unchanged.", file=sys.stderr)
        return 1

    point: dict[str, Any] = {
        "time": point_time.isoformat(),
        "fetchedAt": now.isoformat(),
        "brands": brands,
        "world": None
        if world is None
        else {
            "usd": world.usd,
            "change": world.change,
            "changePct": world.change_pct,
            "vndChi": world.vnd_chi,
        },
    }

    latest = {"schemaVersion": 1, "updatedAt": now.isoformat(), "point": point}
    _write_json(DATA_DIR / "latest.json", latest)

    history_path = HISTORY_DIR / f"{month_key}.json"
    history = _read_json(
        history_path,
        {
            "schemaVersion": 1,
            "month": month_key,
            "updatedAt": now.isoformat(),
            "points": [],
        },
    )
    points = [item for item in history.get("points", []) if item.get("time") != point["time"]]
    points.append(point)
    points.sort(key=lambda item: item.get("time", ""))
    history["schemaVersion"] = 1
    history["month"] = month_key
    history["updatedAt"] = now.isoformat()
    history["points"] = points
    _write_json(history_path, history)

    print(f"Wrote {len(brands)} brand prices for {point['time']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
