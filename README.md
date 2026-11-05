# Paraşüt Teklif Raporu

Belirli tarih aralığındaki Paraşüt satış tekliflerini listeler ve UTF-8 `.txt` dosyasına kaydeder. İki seçenek bulunur: Python komut satırı uygulaması (önerilen, ek paket kurmadan çalışır) ve yerel Node.js web arayüzü.

## Python ile çalıştırma (önerilen)

### Gereksinimler

- Python 3.9 veya üzeri (`python --version` ile kontrol edin; bazı Windows kurulumlarında `py --version` kullanılır)
- Paraşüt API için geçerli bir `access token`
- Şirketin Paraşüt API `company ID` değeri

Python sürümü standart kütüphanelerini kullandığı için `pip`, `npm` veya ek paket kurulumu gerekmez.

### Windows

1. `parasut_quotes.py` dosyasını bilgisayarınıza indirin.
2. Dosyanın bulunduğu klasörde Komut İstemi açın (klasör adres çubuğuna `cmd` yazıp Enter'a basabilirsiniz).
3. Şu komutlardan Python kurulumunuza uyanı çalıştırın:

   ```bash
   python parasut_quotes.py
   ```

   veya:

   ```bash
   py parasut_quotes.py
   ```

4. Program sırasıyla Company ID, access token ve tarih aralığını sorar. Token yazarken terminalde karakterlerin görünmemesi normaldir; Enter'a basarak devam edin.
5. İstenen dosya adını girin veya varsayılan adı kullanmak için Enter'a basın. Teklifler listelenir ve TXT dosyası aynı klasöre kaydedilir.

macOS/Linux'ta `python3 parasut_quotes.py` komutunu kullanabilirsiniz.

## OAuth ve güvenlik

- Bu araç OAuth token'ı otomatik oluşturmaz ya da yenilemez; Paraşüt OAuth akışından edinilmiş geçerli `access token` gerekir. Token terminalde gizli olarak istenir, diske kaydedilmez ve ekrana yazdırılmaz.
- Client secret'ı, Paraşüt hesap şifresini veya refresh token'ı kaynak dosyaya ya da GitHub'a koymayın. Access token'ı da kimseyle paylaşmayın.
- Eski erişim belirteci tehlikeye girdiyse Paraşüt tarafında iptal edip yenisini alın.

## Yerel web uygulaması (alternatif)

Node.js 18+ kuruluysa aynı klasördeki `index.html`, `server.js` ve `package.json` dosyalarını kullanabilirsiniz. Klasörde `npm start` çalıştırın ve <http://127.0.0.1:3000> adresini açın. Ayrıntılar yukarıdaki Python sürümünden farklıdır; web formunda access token geçici olarak girilir.

## Notlar

- API tarih filtresi teklifin `issue_date` alanına uygulanır; başlangıç ve bitiş tarihleri dahildir.
- Teklif metni varsa `name`, `title`, `description` ve `number` alanlarından oluşturulur; hiçbiri yoksa teklif ID'si gösterilir.
- API token geçersiz/sona ermişse Paraşüt'ün döndürdüğü hata ekranda görünür.
