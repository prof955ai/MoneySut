#!/usr/bin/env python3
"""Fetch Paraşüt sales quotes for a date range and save their names to TXT.

Uses only Python's standard library. Requires Python 3.9+.
"""

from __future__ import annotations

import getpass
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

API_HOST = "api.parasut.com"
PAGE_SIZE = 25
MAX_PAGES = 1000
TIMEOUT_SECONDS = 30


class ApiError(Exception):
    """An API or network error safe to show to the user."""


def valid_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Tarih YYYY-AA-GG biçiminde olmalı (ör. 2026-03-15).") from exc
    if parsed.isoformat() != value:
        raise ValueError("Tarih YYYY-AA-GG biçiminde olmalı (ör. 2026-03-15).")
    return parsed


def quote_label(quote: dict) -> str:
    attributes = quote.get("attributes") or {}
    values = []
    for key in ("name", "title", "description", "number"):
        value = attributes.get(key)
        if value is not None and str(value).strip() and str(value).strip() not in values:
            values.append(str(value).strip())
    return " — ".join(values) or f"Teklif #{quote.get('id', 'bilinmiyor')}"


def error_message(status: int, payload: object) -> str:
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list):
            details = [
                str(item.get("detail") or item.get("title") or item.get("code"))
                for item in errors
                if isinstance(item, dict) and (item.get("detail") or item.get("title") or item.get("code"))
            ]
            if details:
                return "; ".join(details)
        message = payload.get("message") or payload.get("error")
        if message:
            return str(message)
    return f"HTTP {status}"


def request_json(url: str, token: str) -> dict:
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "ParasutQuoteExporter/1.0",
        },
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = None
        raise ApiError(f"Paraşüt API hatası: {error_message(exc.code, payload)}") from None
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise ApiError(f"Paraşüt API'ye bağlanılamadı: {reason}") from None
    except TimeoutError:
        raise ApiError("Paraşüt API isteği zaman aşımına uğradı.") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ApiError("Paraşüt API geçerli JSON yanıtı döndürmedi.") from None

    if not isinstance(payload, dict):
        raise ApiError("Paraşüt API yanıtı beklenen biçimde değil.")
    return payload


def page_number_from_url(url: str, expected_path: str) -> int:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != API_HOST or parsed.path != expected_path:
        raise ApiError("Paraşüt API beklenmeyen bir sayfalama bağlantısı döndürdü.")
    try:
        page = int(parse_qs(parsed.query).get("page[number]", [""])[0])
    except ValueError:
        page = 0
    if page < 1 or page > MAX_PAGES:
        raise ApiError("Paraşüt API sayfalama bilgisi geçersiz.")
    return page


def fetch_quotes(company_id: str, token: str, start: str, end: str) -> list[dict]:
    endpoint = f"https://{API_HOST}/v4/{company_id}/sales_quotes"
    next_url = endpoint
    page = 1
    quotes: list[dict] = []
    seen_ids: set[str] = set()

    while page <= MAX_PAGES:
        parsed = urlparse(next_url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        # Keep the filters and pagination bound to this endpoint, even when following links.next.
        query["filter[issue_date][gte]"] = [start]
        query["filter[issue_date][lte]"] = [end]
        query["page[size]"] = [str(PAGE_SIZE)]
        query["page[number]"] = [str(page)]
        current_url = urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

        payload = request_json(current_url, token)
        data = payload.get("data")
        if not isinstance(data, list):
            raise ApiError("Paraşüt yanıtında beklenen teklifler listesi (data) bulunamadı.")

        for quote in data:
            if not isinstance(quote, dict):
                continue
            quote_id = str(quote.get("id", ""))
            if not quote_id or quote_id not in seen_ids:
                quotes.append(quote)
                if quote_id:
                    seen_ids.add(quote_id)

        links = payload.get("links") or {}
        next_link = links.get("next") if isinstance(links, dict) else None
        if next_link:
            next_url = urljoin(current_url, str(next_link))
            linked_page = page_number_from_url(next_url, urlparse(endpoint).path)
            if linked_page <= page:
                raise ApiError("Paraşüt API sayfalama bağlantısı ilerlemiyor.")
            page = linked_page
        elif len(data) == PAGE_SIZE:
            page += 1
            next_url = endpoint
        else:
            return quotes

    raise ApiError(f"Sayfalama güvenlik sınırına ulaşıldı ({MAX_PAGES} sayfa). Tarih aralığını daraltıp tekrar deneyin.")


def ask_date(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        try:
            valid_date(value)
            return value
        except ValueError as exc:
            print(exc)


def main() -> int:
    print("Paraşüt Teklif Raporu")
    print("Token ekranda görünmez ve dosyaya kaydedilmez. Client secret veya hesap şifresi girmeyin.\n")

    company_id = input("Company ID: ").strip()
    if not re.fullmatch(r"\d+", company_id):
        print("Hata: Company ID yalnızca rakamlardan oluşmalı.", file=sys.stderr)
        return 2

    token = getpass.getpass("Paraşüt access token: ").strip()
    token = re.sub(r"^Bearer\s+", "", token, flags=re.IGNORECASE).strip()
    if not token:
        print("Hata: Access token boş olamaz.", file=sys.stderr)
        return 2

    start = ask_date("Başlangıç tarihi (YYYY-AA-GG, dahil): ")
    end = ask_date("Bitiş tarihi (YYYY-AA-GG, dahil): ")
    if start > end:
        print("Hata: Başlangıç tarihi bitiş tarihinden sonra olamaz.", file=sys.stderr)
        return 2

    default_name = f"parasut-teklifler-{start}-{end}.txt"
    output_name = input(f"TXT dosya adı [{default_name}]: ").strip() or default_name
    output_path = Path(output_name).expanduser()
    if output_path.exists() and output_path.is_dir():
        print("Hata: Çıktı dosyası adı bir klasörü gösteriyor.", file=sys.stderr)
        return 2

    try:
        quotes = fetch_quotes(company_id, token, start, end)
    except (ApiError, ValueError) as exc:
        print(f"\nTeklifler alınamadı: {exc}", file=sys.stderr)
        return 1
    finally:
        # Best effort: avoid retaining the token longer than the request flow requires.
        token = ""

    quotes.sort(key=lambda quote: (quote.get("attributes") or {}).get("issue_date") or "", reverse=True)
    lines = [
        f"{(quote.get('attributes') or {}).get('issue_date') or 'Tarih yok'}\t{quote_label(quote)}"
        for quote in quotes
    ]
    contents = f"Paraşüt teklifleri ({start} - {end})\n\n" + "\n".join(lines)
    if lines:
        contents += "\n"

    try:
        output_path.write_text(contents, encoding="utf-8-sig")
    except OSError as exc:
        print(f"\nTXT dosyası yazılamadı: {exc}", file=sys.stderr)
        return 1

    print(f"\n{len(quotes)} teklif bulundu.")
    for quote in quotes:
        print(f"{(quote.get('attributes') or {}).get('issue_date') or 'Tarih yok'}  {quote_label(quote)}")
    print(f"\nDosya kaydedildi: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nİşlem kullanıcı tarafından durduruldu.", file=sys.stderr)
        raise SystemExit(130)
