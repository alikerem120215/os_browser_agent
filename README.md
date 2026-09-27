# OS & Browser Agent Backend Altyapısı

Bu proje, Python ve Flask kullanarak çalışan gelişmiş bir **"Yazılım ve İşletim Sistemi/Tarayıcı Ajanı" (OS & Browser Agent)** backend altyapısıdır. 

Uygulama, Google'ın en güncel `google-genai` SDK'sını ve `gemini-2.5-flash` modelini kullanarak otonom bir **ReAct (Reasoning and Acting) Ajan Döngüsü (Agent Loop)** çalıştırır. Model, kendisine sağlanan özel araçları (Tools) çağırarak terminal komutlarını çalıştırabilir, yerel dosyalar oluşturabilir/düzenleyebilir, klavye/fare hareketlerini simüle edebilir ve her adım sonrasında ekranın görüntüsünü alıp "görerek" otonom kararlar verebilir.

---

## 🚀 Özellikler

1. **En Güncel google-genai SDK Entegrasyonu**: Eski `google-generativeai` yerine Google'ın resmi ve modern `google-genai` istemci mimarisi (`from google import genai`).
2. **Kapsamlı İşletim Sistemi Araçları (Tools)**:
   - `execute_terminal_command(command)`: Terminal komutları çalıştırır, çıktıyı (stdout/stderr) modele döner.
   - `write_local_file(path, content)`: Belirtilen dizine dosya yazar.
   - `move_and_click_mouse(x, y, button)`: İmleci verilen (x,y) piksel koordinatına götürür ve tıklar.
   - `type_keyboard_text(text)`: Aktif metin alanına klavyeden yazı yazar.
   - `capture_screen_state()`: O anki ekran görüntüsünü PNG formatında kaydeder.
3. **Multimodal Agent Loop**: Ajan `capture_screen_state` aracını çağırdığında, backend ekran görüntüsünün görsel verisini (bytes) otomatik olarak ReAct döngüsünün bir sonraki adımındaki `user` part'ı içine ekler. Böylece Gemini o anki ekranı görerek bir sonraki adımda nereye tıklayacağına karar verir.
4. **Güvenlik ve Kararlılık (Failsafe & Error Handling)**:
   - Düşük `temperature` (0.2) değeri ile istikrarlı ajan kararları.
   - Hatalı komutlarda sunucunun çökmesini önleyen `try-except` yapıları ve hataları modele besleyen hata mekanizmaları.
   - PyAutoGUI `FAILSAFE` modu aktiftir. Fareyi ekranın köşelerine sürükleyerek acil durumlarda otonom kontrolü anında durdurabilirsiniz.

---

## 🛠️ Kurulum ve Çalıştırma

### 1. Gereksinimleri Yükleme

Gerekli paketleri kurmak için projenin ana dizininde terminali açıp şu komutu çalıştırabilirsiniz:

```bash
pip install -r requirements.txt
```

> **Önemli Not (macOS Kullanıcıları İçin):** PyAutoGUI ve ekran resmi alma kütüphanelerinin macOS üzerinde ekranı kontrol edebilmesi ve ekran görüntüsü alabilmesi için Terminal'e (veya kullandığınız IDE/Editor yazılımına) **"Sistem Ayarları > Gizlilik ve Güvenlik > Ekran Kaydı"** ve **"Erişilebilirlik"** izinlerini vermeniz gerekir.

### 2. API Anahtarını Tanımlama

Proje dizininde bir `.env` dosyası oluşturun ve `GEMINI_API_KEY` değerinizi girin:

```env
GEMINI_API_KEY=AIzaSy...your-actual-api-key...
```

### 3. Sunucuyu Başlatma

Sunucuyu yerelde ayağa kaldırmak için:

```bash
python app.py
```

Sunucu varsayılan olarak **`http://localhost:5001`** adresinde çalışmaya başlayacaktır.

---

## 📡 API Uç Noktaları (Endpoints)

### 1. Sistem Durumu (`GET /status`)
Sistemin çalışabilirliğini ve ekran çözünürlüğü gibi donanım bilgilerini doğrulamak için kullanılır.

* **İstek (Request):**
  ```bash
  curl -X GET http://localhost:5001/status
  ```
* **Yanıt (Response):**
  ```json
  {
    "failsafe_enabled": true,
    "python_version": "3.11.5 ...",
    "screen_resolution": "1920x1080",
    "status": "active"
  }
  ```

### 2. Ajanı Çalıştırma (`POST /agent`)
Ajanın otonom döngüsünü başlatacak ana uç noktadır. Göndereceğiniz `prompt` ile ajana talimat verirsiniz.

* **Örnek İstek (Request):**
  ```bash
  curl -X POST http://localhost:5001/agent \
       -H "Content-Type: application/json" \
       -d '{"prompt": "Yerelde status.txt adında bir dosya oluştur, içine bugünün tarihini ve sistem durumunu yaz. Ardından terminalde bu dosyanın içeriğini okut."}'
  ```

* **Örnek Yanıt (Response):**
  ```json
  {
    "status": "success",
    "final_response": "status.txt dosyası başarıyla oluşturuldu ve içerisine sistem durumu yazıldı. Terminal üzerinden cat komutu ile okuma işlemi başarıyla tamamlandı.",
    "steps": [
      {
        "step": 1,
        "action": "function_call",
        "function_name": "write_local_file",
        "arguments": {
          "content": "Sistem Durumu: Aktif\nTarih: 24 Mayıs 2026",
          "path": "status.txt"
        },
        "result": {
          "status": "success",
          "message": "Dosya başarıyla yazıldı: /Users/.../status.txt"
        }
      },
      {
        "step": 2,
        "action": "function_call",
        "function_name": "execute_terminal_command",
        "arguments": {
          "command": "cat status.txt"
        },
        "result": {
          "status": "success",
          "stdout": "Sistem Durumu: Aktif\nTarih: 24 Mayıs 2026\n",
          "stderr": "",
          "returncode": 0
        }
      },
      {
        "step": 3,
        "action": "respond_to_user",
        "response": "status.txt dosyası başarıyla oluşturuldu ve içerisine sistem durumu yazıldı..."
      }
    ]
  }
  ```

---

## 🔒 Güvenlik ve Tavsiyeler

- **İzole Ortam**: Bu sunucu, shell komutlarını yerel makinede çalıştırabildiğinden, güvenliğiniz için uygulamayı izole edilmiş bir geliştirme ortamında veya Docker/sanal makine içerisinde test etmeniz önerilir.
- **FailSafe**: İşlemleri yarıda kesmek isterseniz farenizi hızla ekranın en köşelerinden birine sürükleyin; sunucu işlemi güvenli bir şekilde iptal edecektir.
