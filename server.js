const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

const HOST = "127.0.0.1";
const PORT = Number(process.env.PORT || 3000);
const PAGE_SIZE = 25;
const MAX_PAGES = 1000;
const INDEX_FILE = path.join(__dirname, "index.html");

function sendJson(response, status, payload) {
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff"
  });
  response.end(JSON.stringify(payload));
}

function validDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00.000Z`);
  return !Number.isNaN(date.valueOf()) && date.toISOString().slice(0, 10) === value;
}

function readJson(request) {
  return new Promise((resolve, reject) => {
    let body = "";
    request.on("data", chunk => {
      body += chunk;
      if (body.length > 10_000) {
        reject(new Error("İstek gövdesi çok büyük."));
        request.destroy();
      }
    });
    request.on("end", () => {
      try { resolve(JSON.parse(body || "{}")); }
      catch { reject(new Error("İstek JSON biçiminde olmalı.")); }
    });
    request.on("error", reject);
  });
}

async function parasutError(response) {
  let message = `Paraşüt API HTTP ${response.status}`;
  try {
    const body = await response.json();
    if (Array.isArray(body.errors) && body.errors.length) {
      message = body.errors
        .map(error => error.detail || error.title || error.code)
        .filter(Boolean)
        .join("; ") || message;
    } else if (body.message) {
      message = body.message;
    }
  } catch { /* JSON olmayan API hatasında HTTP durumunu göster. */ }
  return message;
}

async function fetchQuotes(companyId, token, from, to) {
  const endpoint = `https://api.parasut.com/v4/${encodeURIComponent(companyId)}/sales_quotes`;
  const quotes = [];
  const seenPages = new Set();

  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const url = new URL(endpoint);
    url.searchParams.set("filter[issue_date][gte]", from);
    url.searchParams.set("filter[issue_date][lte]", to);
    url.searchParams.set("page[size]", String(PAGE_SIZE));
    url.searchParams.set("page[number]", String(page));

    const response = await fetch(url, {
      headers: {
        "Authorization": `Bearer ${token}`,
        "Accept": "application/json"
      },
      signal: AbortSignal.timeout(30_000)
    });
    if (!response.ok) throw new Error(await parasutError(response));

    const body = await response.json();
    if (!Array.isArray(body.data)) throw new Error("Paraşüt yanıtında beklenen data listesi bulunamadı.");
    for (const quote of body.data) {
      const key = String(quote.id ?? "");
      if (!key || !seenPages.has(key)) {
        quotes.push(quote);
        if (key) seenPages.add(key);
      }
    }

    // API links.next varsa onu takip et; host ve endpoint kontrolüyle yalnızca
    // Paraşüt'ün aynı sales_quotes listesinin sayfalanmasına izin ver.
    const next = body.links && body.links.next;
    if (next) {
      const nextUrl = new URL(next, url);
      if (nextUrl.origin !== "https://api.parasut.com" || nextUrl.pathname !== new URL(endpoint).pathname) {
        throw new Error("Paraşüt API beklenmeyen bir sayfalama bağlantısı döndürdü.");
      }
      const nextPage = Number(nextUrl.searchParams.get("page[number]"));
      if (!Number.isInteger(nextPage) || nextPage <= page || nextPage > MAX_PAGES) {
        throw new Error("Paraşüt API sayfalama bilgisi geçersiz.");
      }
      page = nextPage - 1;
    } else if (body.data.length < PAGE_SIZE) {
      return quotes;
    }
  }
  throw new Error(`Sayfalama güvenlik sınırına ulaşıldı (${MAX_PAGES} sayfa). Tarih aralığını daraltıp tekrar deneyin.`);
}

const server = http.createServer(async (request, response) => {
  const requestUrl = new URL(request.url, `http://${HOST}:${PORT}`);

  if (request.method === "GET" && requestUrl.pathname === "/") {
    fs.readFile(INDEX_FILE, (error, contents) => {
      if (error) {
        response.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
        response.end("index.html dosyası okunamadı.");
        return;
      }
      response.writeHead(200, {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'self'; connect-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'"
      });
      response.end(contents);
    });
    return;
  }

  if (request.method === "POST" && requestUrl.pathname === "/api/quotes") {
    const auth = request.headers.authorization || "";
    const tokenMatch = auth.match(/^Bearer\s+(.+)$/i);
    if (!tokenMatch) {
      sendJson(response, 401, { error: "Authorization başlığında Bearer access token gerekli." });
      return;
    }

    try {
      const input = await readJson(request);
      const companyId = String(input.companyId || "").trim();
      const from = input.from;
      const to = input.to;
      if (!/^\d+$/.test(companyId)) {
        sendJson(response, 400, { error: "Company ID yalnızca rakamlardan oluşmalı." });
        return;
      }
      if (!validDate(from) || !validDate(to)) {
        sendJson(response, 400, { error: "Başlangıç ve bitiş tarihleri YYYY-AA-GG biçiminde olmalı." });
        return;
      }
      if (from > to) {
        sendJson(response, 400, { error: "Başlangıç tarihi bitiş tarihinden sonra olamaz." });
        return;
      }

      const data = await fetchQuotes(companyId, tokenMatch[1].trim(), from, to);
      sendJson(response, 200, { data });
    } catch (error) {
      const status = error.name === "TimeoutError" ? 504 : 502;
      sendJson(response, status, { error: error.message || "Paraşüt API isteği başarısız oldu." });
    }
    return;
  }

  sendJson(response, 404, { error: "Bulunamadı." });
});

server.listen(PORT, HOST, () => {
  console.log(`Paraşüt Teklif Raporu çalışıyor: http://${HOST}:${PORT}`);
  console.log("Durdurmak için bu pencerede Ctrl+C tuşlayın.");
});
