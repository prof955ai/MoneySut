#!/usr/bin/env python3
"""Paraşüt teklif raporu: Tkinter masaüstü arayüzü, OAuth ve TXT dışa aktarma.

Python 3.9+ standart kütüphanesi dışında paket gerektirmez.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
import tkinter as tk
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

API_HOST = "api.parasut.com"
AUTHORIZE_URL = "https://api.parasut.com/oauth/authorize"
TOKEN_URL = "https://api.parasut.com/oauth/token"
API_BASE = "https://api.parasut.com/v4"
REDIRECT_URI = "http://127.0.0.1:8765/callback"
PAGE_SIZE = 25
MAX_PAGES = 1000
TIMEOUT = 30
CALLBACK_TIMEOUT = 300


class AppError(Exception):
    pass


def token_file() -> Path:
    if os.name == "nt" and os.environ.get("APPDATA"):
        folder = Path(os.environ["APPDATA"]) / "ParasutQuoteExporter"
    else:
        folder = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "parasut-quote-exporter"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "tokens.json"


def load_tokens(path: Path) -> dict:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {}
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


def explain_response(status: int, payload: object) -> str:
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list):
            details = [str(x.get("detail") or x.get("title") or x.get("code"))
                       for x in errors if isinstance(x, dict) and (x.get("detail") or x.get("title") or x.get("code"))]
            if details:
                return "; ".join(details)
        return str(payload.get("error_description") or payload.get("message") or payload.get("error") or f"HTTP {status}")
    return f"HTTP {status}"


def request_json(url: str, *, data: bytes | None = None, headers: dict | None = None) -> dict:
    request = Request(url, data=data, headers={"Accept": "application/json", "User-Agent": "ParasutQuoteExporter/3.0", **(headers or {})})
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read()
        payload = json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = None
        raise AppError(explain_response(exc.code, payload)) from None
    except (URLError, TimeoutError, OSError) as exc:
        raise AppError(f"Bağlantı hatası: {getattr(exc, 'reason', exc)}") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise AppError("Sunucudan geçerli JSON yanıtı alınamadı.") from None
    if not isinstance(payload, dict):
        raise AppError("Sunucu yanıtı beklenen biçimde değil.")
    return payload


def post_token(params: dict[str, str]) -> dict:
    payload = request_json(TOKEN_URL, data=urlencode(params).encode("utf-8"), headers={"Content-Type": "application/x-www-form-urlencoded"})
    if not payload.get("access_token"):
        raise AppError(explain_response(400, payload))
    return payload


def expiry_time(data: dict) -> float:
    try:
        return time.time() + max(0, int(data.get("expires_in", 0)) - 60)
    except (TypeError, ValueError):
        return time.time()


def oauth_login(client_id: str, client_secret: str) -> dict:
    """Run Authorization Code in the user's browser; callback listener is internal."""
    state = secrets.token_urlsafe(32)
    result: dict[str, str] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, _fmt: str, *_args: object) -> None:
            return  # Never write OAuth codes or query strings to logs.

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/callback":
                self.send_error(404)
                return
            query = parse_qs(parsed.query)
            if not secrets.compare_digest(query.get("state", [""])[0], state):
                result["error"] = "OAuth state doğrulanamadı. Güvenlik için işlem iptal edildi."
            elif query.get("error"):
                result["error"] = query.get("error_description", query["error"])[0]
            elif query.get("code", [""])[0]:
                result["code"] = query["code"][0]
            else:
                result["error"] = "OAuth yanıtında authorization code bulunamadı."
            message = "Bağlantı tamamlandı. Bu pencereyi kapatabilirsiniz." if "code" in result else "Bağlantı tamamlanamadı. Uygulamaya dönün."
            body = f"<!doctype html><meta charset='utf-8'><title>Paraşüt</title><p>{message}</p>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    try:
        callback = HTTPServer(("127.0.0.1", 8765), CallbackHandler)
    except OSError as exc:
        raise AppError(f"OAuth bağlantısı başlatılamadı: callback portu 8765 kullanılıyor. {exc}") from None
    callback.timeout = CALLBACK_TIMEOUT
    auth_url = AUTHORIZE_URL + "?" + urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "state": state,
    })
    try:
        opened = webbrowser.open(auth_url)
        if not opened:
            raise AppError("Tarayıcı otomatik açılamadı. Varsayılan tarayıcı ayarını kontrol edin.")
        callback.handle_request()
    finally:
        callback.server_close()
    if "error" in result:
        raise AppError(f"Paraşüt yetkilendirmesi başarısız: {result['error']}")
    if "code" not in result:
        raise AppError("5 dakika içinde Paraşüt dönüşü alınamadı. Tekrar deneyin.")
    return post_token({
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": result["code"],
        "redirect_uri": REDIRECT_URI,
    })


def refresh_token(client_id: str, client_secret: str, tokens: dict, path: Path) -> dict:
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise AppError("Refresh token bulunamadı. Paraşüt'e yeniden bağlanın.")
    updated = post_token({
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": str(refresh),
        "redirect_uri": REDIRECT_URI,
    })
    merged = {**tokens, **updated, "client_id": client_id, "redirect_uri": REDIRECT_URI, "expires_at": expiry_time(updated)}
    if not merged.get("refresh_token"):
        merged["refresh_token"] = refresh
    save_tokens(path, merged)
    return merged


def quote_name(quote: dict) -> str:
    attrs = quote.get("attributes") or {}
    parts: list[str] = []
    for key in ("name", "title", "description", "number"):
        value = attrs.get(key)
        if value is not None and str(value).strip() and str(value).strip() not in parts:
            parts.append(str(value).strip())
    return " — ".join(parts) or f"Teklif #{quote.get('id', 'bilinmiyor')}"


def fetch_quotes(company_id: str, access: str, start: str, end: str, progress) -> list[dict]:
    endpoint = f"{API_BASE}/{company_id}/sales_quotes"
    quotes: list[dict] = []
    seen: set[str] = set()
    page = 1
    url = endpoint
    for _ in range(MAX_PAGES):
        parsed = urlparse(url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        params.update({"filter[issue_date][gte]": [start], "filter[issue_date][lte]": [end], "page[size]": [str(PAGE_SIZE)], "page[number]": [str(page)]})
        current = urlunparse(parsed._replace(query=urlencode(params, doseq=True)))
        payload = request_json(current, headers={"Authorization": f"Bearer {access}"})
        data = payload.get("data")
        if not isinstance(data, list):
            raise AppError("API yanıtında teklifler listesi bulunamadı.")
        for quote in data:
            if isinstance(quote, dict):
                quote_id = str(quote.get("id", ""))
                if not quote_id or quote_id not in seen:
                    quotes.append(quote)
                    if quote_id:
                        seen.add(quote_id)
        progress(f"{len(quotes)} teklif alındı…")
        links = payload.get("links") or {}
        next_link = links.get("next") if isinstance(links, dict) else None
        if next_link:
            from urllib.parse import urljoin
            next_url = urljoin(current, str(next_link))
            next_parsed = urlparse(next_url)
            if next_parsed.scheme != "https" or next_parsed.hostname != API_HOST or next_parsed.path != urlparse(endpoint).path:
                raise AppError("Paraşüt beklenmeyen bir sayfalama bağlantısı döndürdü.")
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
            return quotes
    raise AppError(f"Sayfalama sınırı ({MAX_PAGES}) aşıldı. Tarih aralığını daraltın.")


def parse_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value.strip())
    except ValueError:
        raise AppError("Tarih YYYY-AA-GG biçiminde olmalı (ör. 2026-03-15).") from None
    if parsed.isoformat() != value.strip():
        raise AppError("Tarih YYYY-AA-GG biçiminde olmalı (ör. 2026-03-15).")
    return parsed.isoformat()


class QuoteApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Paraşüt Teklif Raporu")
        self.root.geometry("850x620")
        self.root.minsize(680, 500)
        self.path = token_file()
        self.quotes: list[dict] = []
        self._build_ui()

    def _build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Hint.TLabel", foreground="#555555")
        style.configure("Treeview", rowheight=27)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Paraşüt Teklif Raporu", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Tarih aralığını seçin; teklifler listelensin ve TXT olarak kaydedilsin.", style="Hint.TLabel").pack(anchor="w", pady=(2, 14))

        auth = ttk.LabelFrame(outer, text="Paraşüt API uygulaması", padding=12)
        auth.pack(fill="x", pady=(0, 10))
        auth.columnconfigure(1, weight=1)
        ttk.Label(auth, text="client_id").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        self.client_id = ttk.Entry(auth)
        self.client_id.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(auth, text="client_secret").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        self.client_secret = ttk.Entry(auth, show="●")
        self.client_secret.grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(auth, text="Company ID").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        self.company_id = ttk.Entry(auth)
        self.company_id.grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(auth, text=f"Callback adresi (geliştirici panelinde birebir kayıtlı olmalı): {REDIRECT_URI}", style="Hint.TLabel").grid(row=3, column=0, columnspan=2, sticky="w", pady=(7, 0))

        filters = ttk.LabelFrame(outer, text="Teklif tarihi", padding=12)
        filters.pack(fill="x", pady=(0, 10))
        today = date.today()
        self.start_date = tk.StringVar(value=today.replace(day=1).isoformat())
        self.end_date = tk.StringVar(value=today.isoformat())
        ttk.Label(filters, text="Başlangıç (dahil)").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(filters, textvariable=self.start_date, width=16).grid(row=0, column=1, sticky="w", padx=(0, 18))
        ttk.Label(filters, text="Bitiş (dahil)").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Entry(filters, textvariable=self.end_date, width=16).grid(row=0, column=3, sticky="w")
        ttk.Label(filters, text="Biçim: YYYY-AA-GG", style="Hint.TLabel").grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 10))
        self.fetch_button = ttk.Button(actions, text="Paraşüt'e bağlan ve teklifleri getir", command=self.start_fetch)
        self.fetch_button.pack(side="left")
        self.save_button = ttk.Button(actions, text="TXT olarak kaydet", command=self.save_txt, state="disabled")
        self.save_button.pack(side="left", padx=8)
        self.status = tk.StringVar(value="Hazır. İlk sorguda tarayıcı Paraşüt yetkilendirmesi için açılır.")
        ttk.Label(outer, textvariable=self.status, wraplength=800).pack(fill="x", pady=(0, 8))

        table_frame = ttk.Frame(outer)
        table_frame.pack(fill="both", expand=True)
        self.table = ttk.Treeview(table_frame, columns=("date", "name"), show="headings")
        self.table.heading("date", text="Teklif tarihi")
        self.table.heading("name", text="Teklif adı / açıklama")
        self.table.column("date", width=130, stretch=False)
        self.table.column("name", width=600, stretch=True)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        ttk.Label(outer, text="Client secret kod dosyasına yazılmaz. Token bilgisayardaki kullanıcı profilinde saklanır.", style="Hint.TLabel").pack(anchor="w", pady=(8, 0))

    def ui(self, callback, *args) -> None:
        self.root.after(0, lambda: callback(*args))

    def set_status(self, text: str) -> None:
        self.status.set(text)

    def start_fetch(self) -> None:
        client_id = self.client_id.get().strip()
        client_secret = self.client_secret.get().strip()
        company_id = self.company_id.get().strip()
        if not client_id or not client_secret:
            messagebox.showerror("Eksik bilgi", "Paraşüt uygulamasının client_id ve client_secret bilgilerini girin.")
            return
        if not re.fullmatch(r"\d+", company_id):
            messagebox.showerror("Eksik bilgi", "Company ID yalnızca rakamlardan oluşmalı.")
            return
        try:
            start = parse_date(self.start_date.get())
            end = parse_date(self.end_date.get())
            if start > end:
                raise AppError("Başlangıç tarihi bitiş tarihinden sonra olamaz.")
        except AppError as exc:
            messagebox.showerror("Tarih hatası", str(exc))
            return
        self.fetch_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.table.delete(*self.table.get_children())
        self.quotes = []
        self.status.set("Paraşüt'e bağlanılıyor… Gerekirse tarayıcıda izin verin.")
        threading.Thread(target=self._fetch_worker, args=(client_id, client_secret, company_id, start, end), daemon=True).start()

    def _fetch_worker(self, client_id: str, client_secret: str, company_id: str, start: str, end: str) -> None:
        try:
            tokens = load_tokens(self.path)
            valid_cache = (tokens.get("client_id") == client_id and tokens.get("redirect_uri") == REDIRECT_URI)
            if valid_cache and tokens.get("access_token") and float(tokens.get("expires_at", 0) or 0) > time.time():
                access = str(tokens["access_token"])
            elif valid_cache and tokens.get("refresh_token"):
                self.ui(self.set_status, "Access token yenileniyor…")
                try:
                    tokens = refresh_token(client_id, client_secret, tokens, self.path)
                    access = str(tokens["access_token"])
                except AppError:
                    self.ui(self.set_status, "Yeniden yetkilendirme gerekiyor; tarayıcı açılıyor…")
                    tokens = oauth_login(client_id, client_secret)
                    tokens.update({"client_id": client_id, "redirect_uri": REDIRECT_URI, "expires_at": expiry_time(tokens)})
                    save_tokens(self.path, tokens)
                    access = str(tokens["access_token"])
            else:
                tokens = oauth_login(client_id, client_secret)
                tokens.update({"client_id": client_id, "redirect_uri": REDIRECT_URI, "expires_at": expiry_time(tokens)})
                save_tokens(self.path, tokens)
                access = str(tokens["access_token"])

            try:
                quotes = fetch_quotes(company_id, access, start, end, lambda text: self.ui(self.set_status, text))
            except AppError as exc:
                if "401" not in str(exc) and "Unauthorized" not in str(exc):
                    raise
                self.ui(self.set_status, "Access token yenileniyor ve sorgu tekrarlanıyor…")
                tokens = refresh_token(client_id, client_secret, tokens, self.path)
                access = str(tokens["access_token"])
                quotes = fetch_quotes(company_id, access, start, end, lambda text: self.ui(self.set_status, text))
            quotes.sort(key=lambda q: (q.get("attributes") or {}).get("issue_date") or "", reverse=True)
            self.ui(self._show_results, quotes)
        except Exception as exc:
            self.ui(self._show_error, str(exc))

    def _show_results(self, quotes: list[dict]) -> None:
        self.quotes = quotes
        for quote in quotes:
            attrs = quote.get("attributes") or {}
            self.table.insert("", "end", values=(attrs.get("issue_date") or "—", quote_name(quote)))
        self.status.set(f"{len(quotes)} teklif bulundu.")
        self.save_button.configure(state="normal" if quotes else "disabled")
        self.fetch_button.configure(state="normal")

    def _show_error(self, message: str) -> None:
        self.status.set("İşlem tamamlanamadı.")
        self.fetch_button.configure(state="normal")
        messagebox.showerror("Paraşüt bağlantı hatası", message)

    def save_txt(self) -> None:
        if not self.quotes:
            return
        start = self.start_date.get().strip()
        end = self.end_date.get().strip()
        default = f"parasut-teklifler-{start}-{end}.txt"
        filename = filedialog.asksaveasfilename(
            title="Teklifleri TXT olarak kaydet",
            initialfile=default,
            defaultextension=".txt",
            filetypes=[("Metin dosyası", "*.txt"), ("Tüm dosyalar", "*.*")],
        )
        if not filename:
            return
        lines = [f"{(q.get('attributes') or {}).get('issue_date') or 'Tarih yok'}\t{quote_name(q)}" for q in self.quotes]
        content = f"Paraşüt teklifleri ({start} - {end})\n\n" + "\n".join(lines) + "\n"
        try:
            Path(filename).write_text(content, encoding="utf-8-sig")
        except OSError as exc:
            messagebox.showerror("Dosya kaydedilemedi", str(exc))
            return
        self.status.set(f"Dosya kaydedildi: {filename}")
        messagebox.showinfo("Kaydedildi", f"{len(lines)} teklif dosyaya kaydedildi.")


def main() -> None:
    root = tk.Tk()
    QuoteApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
