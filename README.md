# Paraşüt Teklif Raporu

Belirli tarih aralığındaki Paraşüt satış tekliflerini listeler ve UTF-8 `.txt` dosyası olarak indirir. Tarayıcı uygulaması Paraşüt API'ye doğrudan bağlanmaz; istekler bu bilgisayarda çalışan Node.js sunucusu üzerinden gider.

## Gereksinimler

- Node.js 18 veya üzeri (`node --version` ile kontrol edin)
- Paraşüt API için geçerli bir `access token`
- Şirketin Paraşüt API `company ID` değeri

## Windows'ta çalıştırma

1. Bu projedeki `index.html`, `server.js` ve `package.json` dosyalarını **aynı klasöre** indirin.
2. Bu klasörü açın. Adres çubuğuna `cmd` yazıp Enter'a basarak Komut İstemi'ni açın. PowerShell de kullanılabilir.
3. Aşağıdaki komutu çalıştırın:

   ```bash
   npm start
   ```

   `npm` bulunamadı hatası alırsanız Node.js 18+ kurun, terminali kapatıp yeniden açın ve komutu tekrar deneyin.

4. Terminalde görünen adresi tarayıcıda açın: <http://127.0.0.1:3000>
5. Company ID ve access token'ı arayüze girin, tarih aralığını seçin ve **Teklifleri getir**'e basın.
6. Sonuçları kaydetmek için **TXT olarak indir**'e basın.
7. İşiniz bittiğinde sunucunun çalıştığı terminal penceresinde `Ctrl+C` tuşlayın.

## Güvenlik ve OAuth notu

- Sunucu yalnızca bu bilgisayarın `127.0.0.1` adresini dinler; ağdaki diğer cihazlara açılmaz.
- Access token arayüzden yerel sunucuya, oradan HTTPS ile Paraşüt'e iletilir. Uygulama token'ı diske yazmaz ve istek başlıklarını günlüğe kaydetmez.
- **Client secret'ı, Paraşüt hesabı şifresini veya refresh token'ı HTML'e ya da GitHub'a koymayın.** Bu araç, OAuth token oluşturma/yenileme işlemini yapmaz; geçerli access token'ı Paraşüt'ün OAuth akışından edinip arayüze geçici olarak girmeniz gerekir.
- Bu bir yerel kişisel kullanım aracıdır. İnternete açık sunucu olarak dağıtmayın.

## Notlar

- API tarih filtresi teklifin `issue_date` alanına uygulanır; başlangıç ve bitiş tarihleri dahildir.
- Teklif metni varsa `name`, `title`, `description` ve `number` alanlarından oluşturulur; hiçbiri yoksa teklif ID'si gösterilir.
- API token geçersiz/sona ermişse Paraşüt'ün döndürdüğü hata ekranda görünür.
- Eski erişim belirteci tehlikeye girdiyse Paraşüt tarafında iptal edip yenisini alın.
