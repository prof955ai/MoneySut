# Paraşüt Teklif Raporu

OAuth 2.0 Authorization Code akışını Python ile tamamlar, belirli tarih aralığındaki Paraşüt satış tekliflerini listeler ve UTF-8 `.txt` dosyasına kaydeder. Python sürümü standart kütüphaneyi kullanır; `pip`, `npm` veya ek paket kurulumu gerekmez.

## Önce Paraşüt uygulamasını kaydedin

1. Paraşüt DevHub'daki [OAuth rehberini](https://devhub.parasut.com/oauth-rehberi) izleyerek bir API uygulaması oluşturun.
2. Uygulamanın `client_id` ve `client_secret` bilgilerini alın. `client_secret` gizlidir; kaynak koduna, GitHub'a veya başkalarıyla paylaşmayın.
3. Uygulamanızın izin verilen/callback (redirect) URI listesine aşağıdaki adresi **birebir** kaydedin:

   ```text
   http://127.0.0.1:8765/callback
   ```

   Paraşüt paneli bu URI'yi kabul etmezse kendi belgelerinin izin verdiği localhost callback biçimini kullanın ve programda da tam aynı URI'yi girin. Uygulama yalnızca `127.0.0.1` veya `localhost` HTTP callback'lerini kabul eder.

## Windows'ta çalıştırma

1. `parasut_quotes.py` dosyasını bilgisayarınıza indirin.
2. Python 3.9 veya üzerini kurup kontrol edin: `py --version` (veya `python --version`). Başka paket yüklemeyin.
3. Dosyanın bulunduğu klasörde Komut İstemi açın (klasör adres çubuğuna `cmd` yazıp Enter'a basın).
4. Çalıştırın:

   ```bash
   py parasut_quotes.py
   ```

   Gerekirse `python parasut_quotes.py` kullanın. macOS/Linux'ta `python3 parasut_quotes.py` çalıştırın.
5. Program `client_id`, `client_secret`, kayıtlı callback URI ve Paraşüt `company ID` bilgilerini sorar. Client secret terminalde yazarken görünmez.
6. İlk çalıştırmada tarayıcı Paraşüt'e yönlendirilir. Hesapta oturum açıp uygulama erişimine izin verin. Onaydan sonra `127.0.0.1` callback sayfası açılır; terminale dönün.
7. Başlangıç ve bitiş tarihlerini `YYYY-AA-GG` biçiminde girin. Program teklifleri çeker, ekranda listeler ve belirtilen `.txt` dosyasına yazar.

## OAuth ve token saklama

- Akış: Paraşüt `/oauth/authorize` → doğrulanmış `state` ile localhost callback → `/oauth/token` üzerinde `grant_type=authorization_code` → access/refresh token.
- Access token'ın süresi dolduğunda program `grant_type=refresh_token` ile yenilemeyi dener. Refresh token döndürülmüşse yenisini de saklar; süresi dolmuş/iptal edilmiş token'da yeniden yetki ister.
- Paraşüt client secret her çalıştırmada gizli olarak sorulur; dosyaya kaydedilmez. Token bilgileri script/repository yerine kullanıcının yerel yapılandırma klasöründe saklanır (Windows `%APPDATA%\\ParasutQuoteExporter\\tokens.json`; macOS/Linux `~/.config/parasut-quote-exporter/tokens.json`). Bu dosyayı paylaşmayın veya GitHub'a koymayın; erişimi iptal etmek için dosyayı silip Paraşüt uygulamasındaki izni kaldırın.
- OAuth callback portu `8765` kullanımda olmalı. Başka bir uygulama portu kullanıyorsa kapatın ve callback URI'yi hem geliştirici panelinde hem programda aynı şekilde değiştirin.
- Paraşüt hesabı şifresi bu uygulamaya girilmez; şifre yalnızca Paraşüt'ün kendi giriş sayfasında kullanılır.

## Teklifler

- Tarih aralığı `sales_quotes` listesindeki `issue_date` alanına filtre uygular ve başlangıç/bitiş tarihlerini dahil eder.
- API sayfalaması takip edilir. Teklif metni varsa `name`, `title`, `description` ve `number` alanları kullanılır; yoksa teklif ID'si gösterilir.
- API hataları (ör. yetki yok, yanlış company ID, geçersiz token) terminalde açıklanır.

## Not

Bu araç Paraşüt API'sine doğrudan Python üzerinden HTTPS isteği yapar; tarayıcı CORS sorunu olmaz. OAuth client kaydı ve Paraşüt hesabı izinleri doğru yapılandırılmalıdır. Callback adresinin uygulama kaydında kabul edilmesi hesap/panel ayarlarına bağlı olabilir.
