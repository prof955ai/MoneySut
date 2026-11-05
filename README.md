# Paraşüt Teklif Raporu — Masaüstü uygulaması

Teklifleri tarih aralığına göre Paraşüt API'den çeker, ekranda listeler ve TXT olarak kaydeder. Bu sürüm **Tkinter masaüstü arayüzüdür**; terminalde komut yazmanız veya yerel web sunucusu başlatmanız gerekmez. API istekleri Python tarafından yapılır, tarayıcı CORS sorunu yaşanmaz. Ek Python paketi, pip veya npm gerekmez.

## İlk kurulum (bir kez)

1. Python 3.9 veya üzerini kurun. Windows'ta Python kurulumunda **tcl/tk (IDLE ve Tkinter)** seçeneği kurulu olmalı.
2. Paraşüt DevHub'da API uygulamanızın `client_id` ve `client_secret` bilgilerini alın.
3. Geliştirici panelindeki Redirect URI / callback adresine şu adresi **birebir** kaydedin:

   ```text
   http://127.0.0.1:8765/callback
   ```

   OAuth standart akışının Paraşüt'ten uygulamaya dönüş yapabilmesi için callback gerekir. Bu adres program tarafından bilgisayarınız içinde arka planda dinlenir; siz tarayıcı adres çubuğuna yazmaz, sunucu çalıştırmaz veya komut penceresi kullanmazsınız.

## Windows'ta çalıştırma

1. `parasut_quotes.py` dosyasını bilgisayarınıza indirin.
2. Dosyaya çift tıklayın. Birlikte açma sorarsa Python ile açın. Konsol penceresi istemiyorsanız dosyayı `.pyw` uzantısıyla kaydedip çift tıklayın; arayüz aynıdır.
3. Program penceresinde `client_id`, `client_secret`, Paraşüt `Company ID` ve tarih aralığını doldurun.
4. **Paraşüt'e bağlan ve teklifleri getir** düğmesine basın. İlk kullanımda tarayıcı Paraşüt giriş/izin sayfasını açar; giriş ve onay sonrasında uygulama otomatik devam eder.
5. Teklifleri tabloda görün. **TXT olarak kaydet** düğmesiyle dosya adını ve kaydedilecek yeri seçin.

macOS'ta Python/Tkinter yüklü olmalıdır; `.py` dosyasını Python Launcher ile açabilirsiniz. Linux dağıtımında Tkinter ayrı paket olarak gerekebilir (ör. Debian/Ubuntu: `python3-tk`).

## Güvenlik ve token yenileme

- `client_secret` parola alanında gizli gösterilir, kaynak koduna yazılmaz ve dosyaya kaydedilmez.
- Access/refresh token'lar kullanıcının yerel yapılandırma alanında tutulur; Windows'ta `%APPDATA%\\ParasutQuoteExporter\\tokens.json`, macOS/Linux'ta `~/.config/parasut-quote-exporter/tokens.json`. Bu dosyay�� paylaşmayın veya GitHub'a yüklemeyin.
- Süresi dolan access token program tarafından OAuth `refresh_token` akışıyla yenilenir. Yenileme başarısızsa yeniden Paraşüt izni ister.
- Hesap şifresi bu uygulamaya girilmez; şifre yalnızca Paraşüt'ün kendi giriş sayfasında kullanılır.
- Callback portu 8765 başka bir uygulama tarafından kullanılıyorsa kapatın. Callback kaydı değişirse geliştirici paneli ve uygulama ayarlarının aynı URI olduğundan emin olun.

## Teklif alanları

Tarih filtresi `sales_quotes` listesindeki `issue_date` alanına uygulanır; başlangıç/bitiş tarihleri dahildir. Görünen teklif bilgisi mevcutsa `name`, `title`, `description` ve `number` alanlarından oluşturulur; hiçbiri yoksa teklif ID'si kullanılır.
