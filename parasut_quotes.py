#!/usr/bin/env python3
"""OAuth-enabled Paraşüt sales quote exporter (Python 3.9+, stdlib only)."""
from __future__ import annotations

import getpass
import json
import os
import re
import secrets
import sys
import time
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

API_HOST = "api.parasut.com"
AUTHORIZE_URL = "https://api.parasut.com/oauth/authorize"
TOKEN_URL = "https://api.parasut.com/oauth/token"
API_BASE = "https://api.parasut.com/v4"
PAGE_SIZE = 25
MAX_PAGES = 1000
TIMEOUT = 30
CALLBACK_TIMEOUT = 180
TOKEN_FILE = Path.home() / ".parasut_quote_exporter_tokens.json"


class AppError(Exception):
    pass


def api_error_text(status: int, payload: object) -> str:
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list):
            details = [str(x.get("detail") or x.get("title") or x.get("code"))
                       for x in errors if isinstance(x, dict) and (x.get("detail") or x.get("title") or x.get("code"))]
            if details:
                return "; ".join(details)
        return str(payload.get("error_description") or payload.get("message") or payload.get("error") or f"HTTP {status}")
    return f"HTTP {status}"


def json_request(url: str, *, data: bytes | None = None, headers: dict | None = None) -> dict:
    request = Request(url, data=data, headers={"Accept": "application/json", "User-Agent": "ParasutQuoteExporter/2.0", **(headers or {})})
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read()
        payload = json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = None
        raise AppError(api_error_text(exc.code, payload)) from None
    except (URLError, TimeoutError, OSError) as exc:
        raise AppError(f"Bağlantı hatası: {getattr(exc, 'reason', exc)}") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise AppError("Sunucudan geçerli JSON yanıtı alınamadı.") from None
    if not isinstance(payload, dict):
        raise AppError("Sunucu yanıtı beklenen biçimde değil.")
    return payload


def token_request(fields: dict[str, str]) -> dict:
    payload = json_request(TOKEN_URL, data=urlencode(fields).encode("utf-8"), headers={"Content-Type": "application/x-www-form-urlencoded"})
    if not payload.get("access_token"):
        raise AppError(api_error_text(400, payload))
    return payload


def config_path() -> Path:
    # Store refresh/access tokens in the user's private config directory, not beside the script/repository.
    if os.name == "nt" and os.environ.get("APPDATA"):
        folder = Path(os.environ["APPDATA"]) / "ParasutQuoteExporter"
    else:
        folder = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "parasut-quote-exporter"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "tokens.json"


def load_tokens(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_tokens(path: Path, tokens: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    temp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def callback_settings(redirect_uri: str) -> tuple[str, int, str]:
    parsed = urlparse(redirect_uri)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise AppError("Güvenlik için redirect URI http://127.0.0.1 veya http://localhost olmalı.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise AppError("Redirect URI kullanıcı bilgisi, query veya fragment içermemeli.")
    if not parsed.port:
        raise AppError("Redirect URI içinde port belirtin; ör. http://127.0.0.1:8765/callback")
    host = "127.0.0.1" if parsed.hostname == "localhost" else parsed.hostname
    path = parsed.path or "/"
    return host, parsed.port, path


def authorize_and_exchange(client_id: str, client_secret: str, redirect_uri: str) -> dict:
    host, port, callback_path = callback_settings(redirect_uri)
    state = secrets.token_urlsafe(32)
    result: dict = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            # Never log OAuth codes, state, or query strings.
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != callback_path:
                self.send_error(404)
                return
            params = parse_qs(parsed.query)
            returned_state = params.get("state", [""])[0]
            if not secrets.compare_digest(returned_state, state):
                result["error"] = "OAuth state doğrulanamadı. Güvenlik için işlem iptal edildi."
            elif params.get("error"):
                result["error"] = params.get("error_description", params["error"])[0]
            else:
                code = params.get("code", [""])[0]
                if not code:
                    result["error"] = "Paraşüt callback yanıtında authorization code bulunamadı."
                else:
                    result["code"] = code
            text = ("Paraşüt bağlantısı tamamlandı. Bu pencereyi kapatıp programa dönebilirsiniz."
                    if "code" in result else "Paraşüt bağlantısı tamamlanamadı. Bu pencereyi kapatıp terminaldeki mesajı kontrol edin.")
            body = f"<!doctype html><meta charset='utf-8'><title>Paraşüt OAuth</title><p>{text}</p>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    try:
        server = HTTPServer((host, port), CallbackHandler)
    except OSError as exc:
        raise AppError(f"OAuth callback portu açılamadı ({host}:{port}): {exc}") from None
    server.timeout = CALLBACK_TIMEOUT

    query = urlencode({"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "state": state})
    auth_url = f"{AUTHORIZE_URL}?{query}"
    print("\nParaşüt giriş/izin sayfası tarayıcıda açılıyor.")
    print("Açılmazsa aşağıdaki URL'yi tarayıcıya kopyalayın:\n" + auth_url)
    try:
        webbrowser.open(auth_url)
        server.handle_request()
    finally:
        server.server_close()

    if "error" in result:
        raise AppError(f"OAuth başarısız: {result['error']}")
    if "code" not in result:
        raise AppError(f"{CALLBACK_TIMEOUT} saniye içinde OAuth callback alınamadı.")

    return token_request({
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": result["code"],
        "redirect_uri": redirect_uri,
    })


def token_expiry(token_data: dict) -> float:
    try:
        return time.time() + max(0, int(token_data.get("expires_in", 0)) - 60)
    except (TypeError, ValueError):
        return time.time()


def get_access_token(client_id: str, client_secret: str, redirect_uri: str, path: Path) -> tuple[str, dict]:
    cached = load_tokens(path)
    key_matches = cached.get("client_id") == client_id and cached.get("redirect_uri") == redirect_uri
    if key_matches and cached.get("access_token") and float(cached.get("expires_at", 0) or 0) > time.time():
        print("Kaydedilmiş, süresi geçmemiş access token kullanılıyor.")
        return str(cached["access_token"]), cached

    if key_matches and cached.get("refresh_token"):
        print("Access token yenileniyor…")
        try:
            fresh = token_request({
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": str(cached["refresh_token"]),
                "redirect_uri": redirect_uri,
            })
            combined = {**cached, **fresh, "client_id": client_id, "redirect_uri": redirect_uri, "expires_at": token_expiry(fresh)}
            if not combined.get("refresh_token"):
                combined["refresh_token"] = cached["refresh_token"]
            save_tokens(path, combined)
            return str(combined["access_token"]), combined
        except AppError as exc:
            print(f"Token yenilenemedi ({exc}). Yeniden Paraşüt izni istenecek.")

    fresh = authorize_and_exchange(client_id, client_secret, redirect_uri)
    fresh.update({"client_id": client_id, "redirect_uri": redirect_uri, "expires_at": token_expiry(fresh)})
    save_tokens(path, fresh)
    return str(fresh["access_token"]), fresh


def refresh_access_token(client_id: str, client_secret: str, redirect_uri: str, path: Path, tokens: dict) -> str:
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise AppError("Refresh token yok; yeniden yetkilendirme gerekiyor.")
    fresh = token_request({
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": str(refresh_token),
        "redirect_uri": redirect_uri,
    })
    combined = {**tokens, **fresh, "client_id": client_id, "redirect_uri": redirect_uri, "expires_at": token_expiry(fresh)}
    if not combined.get("refresh_token"):
        combined["refresh_token"] = refresh_token
    save_tokens(path, combined)
    tokens.clear()
    tokens.update(combined)
    return str(combined["access_token"])


def valid_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("Tarih YYYY-AA-GG biçiminde olmalı (ör. 2026-03-15).") from None
    if parsed.isoformat() != value:
        raise ValueError("Tarih YYYY-AA-GG biçiminde olmalı (ör. 2026-03-15).")
    return parsed


def fetch_page(url: str, token: str) -> dict:
    return json_request(url, headers={"Authorization": f"Bearer {token}"})


def fetch_quotes(company_id: str, token: str) -> list[dict]:
    start = input("Başlangıç tarihi (YYYY-AA-GG, dahil): ").strip()
    end = input("Bitiş tarihi (YYYY-AA-GG, dahil): ").strip()
    valid_date(start)
    valid_date(end)
    if start > end:
        raise AppError("Başlangıç tarihi bitiş tarihinden sonra olamaz.")

    endpoint = f"{API_BASE}/{company_id}/sales_quotes"
    url = endpoint
    page = 1
    quotes: list[dict] = []
    seen_ids: set[str] = set()
    for _ in range(MAX_PAGES):
        parsed = urlparse(url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        params.update({"filter[issue_date][gte]": [start], "filter[issue_date][lte]": [end], "page[size]": [str(PAGE_SIZE)], "page[number]": [str(page)]})
        current = urlunparse(parsed._replace(query=urlencode(params, doseq=True)))
        payload = fetch_page(current, token)
        data = payload.get("data")
        if not isinstance(data, list):
            raise AppError("Paraşüt yanıtında teklifler listesi (data) bulunamadı.")
        for quote in data:
            if isinstance(quote, dict):
                quote_id = str(quote.get("id", ""))
                if not quote_id or quote_id not in seen_ids:
                    quotes.append(quote)
                    if quote_id:
                        seen_ids.add(quote_id)
        links = payload.get("links") or {}
        next_link = links.get("next") if isinstance(links, dict) else None
        if next_link:
            from urllib.parse import urljoin
            next_url = urljoin(current, str(next_link))
            next_parsed = urlparse(next_url)
            if next_parsed.scheme != "https" or next_parsed.hostname != API_HOST or next_parsed.path != urlparse(endpoint).path:
                raise AppError("Paraşüt beklenmeyen sayfalama bağlantısı döndürdü.")
            try:
                next_page = int(parse_qs(next_parsed.query).get("page[number]", [""])[0])
            except ValueError:
                next_page = 0
            if next_page <= page or next_page > MAX_PAGES:
                raise AppError("Paraşüt sayfalama bilgisi geçersiz.")
            url, page = next_url, next_page
        elif len(data) == PAGE_SIZE:
            page += 1
            url = endpoint
        else:
            return quotes, start, end
        print(f"{len(quotes)} teklif alındı…", end="\r", flush=True)
    raise AppError(f"Sayfalama sınırı ({MAX_PAGES} sayfa) aşıldı; tarih aralığını daraltın.")


def quote_label(quote: dict) -> str:
    attrs = quote.get("attributes") or {}
    values: list[str] = []
    for field in ("name", "title", "description", "number"):
        value = attrs.get(field)
        if value is not None and str(value).strip() and str(value).strip() not in values:
            values.append(str(value).strip())
    return " — ".join(values) or f"Teklif #{quote.get('id', 'bilinmiyor')}"


def main() -> int:
    print("Paraşüt Teklif Raporu — OAuth 2.0 Authorization Code\n")
    print("Önce Paraşüt geliştirici panelinde uygulama oluşturun ve callback adresini birebir kaydedin.")
    client_id = input("OAuth client_id: ").strip()
    if not client_id:
        raise AppError("client_id boş olamaz.")
    client_secret = getpass.getpass("OAuth client_secret (gizli): ").strip()
    if not client_secret:
        raise AppError("client_secret boş olamaz.")
    redirect_uri = input("Kayıtlı redirect URI [http://127.0.0.1:8765/callback]: ").strip() or "http://127.0.0.1:8765/callback"
    callback_settings(redirect_uri)
    company_id = input("Paraşüt company ID: ").strip()
    if not re.fullmatch(r"\d+", company_id):
        raise AppError("Company ID yalnızca rakamlardan oluşmalı.")

    tokens_file = config_path()
    access_token, tokens = get_access_token(client_id, client_secret, redirect_uri, tokens_file)
    try:
        try:
            quotes, start, end = fetch_quotes(company_id, access_token)
        except AppError as first_error:
            if "401" not in str(first_error) or not tokens.get("refresh_token"):
                raise
            print("Access token reddedildi; yenilenip tekrar deneniyor…")
            access_token = refresh_access_token(client_id, client_secret, redirect_uri, tokens_file, tokens)
            quotes, start, end = fetch_quotes(company_id, access_token)
    finally:
        access_token = ""
        client_secret = ""

    quotes.sort(key=lambda q: (q.get("attributes") or {}).get("issue_date") or "", reverse=True)
    default_name = f"parasut-teklifler-{start}-{end}.txt"
    output = Path(input(f"TXT dosya adı [{default_name}]: ").strip() or default_name).expanduser()
    lines = [f"{(q.get('attributes') or {}).get('issue_date') or 'Tarih yok'}\t{quote_label(q)}" for q in quotes]
    content = f"Paraşüt teklifleri ({start} - {end})\n\n" + "\n".join(lines) + ("\n" if lines else "")
    try:
        output.write_text(content, encoding="utf-8-sig")
    except OSError as exc:
        raise AppError(f"TXT dosyası yazılamadı: {exc}") from None
    print(f"\n{len(quotes)} teklif bulundu.")
    for line in lines:
        print(line.replace("\t", "  "))
    print(f"\nDosya kaydedildi: {output.resolve()}")
    print(f"Token bilgileri yerel kullanıcı profilinde saklandı: {tokens_file}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AppError, ValueError) as exc:
        print(f"\nHata: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nİşlem iptal edildi.", file=sys.stderr)
        raise SystemExit(130)
