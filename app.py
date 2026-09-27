#!/usr/bin/env python3
"""
OS & Browser Agent Backend Altyapısı
====================================
Bu backend uygulaması, Python ve Flask tabanlı bir web sunucusu çalıştırır.
Arka planda Google'ın en güncel `google-genai` SDK'sını ve `gemini-2.5-flash` modelini
kullanarak işletim sistemi komutlarını çalıştıran, GUI etkileşimi kurabilen (klavye/fare)
ve multimodal ekran analizi yapabilen otonom bir Ajan Döngüsü (Agent Loop) yönetir.
"""

import os
import subprocess
import sys
import time
import tempfile
import logging
from flask import Flask, request, jsonify, render_template, send_from_directory
from google import genai
from google.genai import types
from PIL import Image
import pyautogui
from dotenv import load_dotenv

# dotenv ile çevre değişkenlerini yükle (.env dosyası varsa okunur)
load_dotenv()

# Loglama ayarlarını yapılandır
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("OSBrowserAgent")

# PyAutoGUI güvenlik önlemleri
pyautogui.FAILSAFE = True  # Fare ekranın sol üst/sağ üst/sol alt/sağ alt köşesine çekilirse işlemi iptal eder.
pyautogui.PAUSE = 0.5      # Her PyAutoGUI çağrısı arasına yarım saniye gecikme koyar (sistemin tepki vermesi için).

app = Flask(__name__)

# Google GenAI İstemcisi istek anında dinamik olarak başlatılacaktır.



# =====================================================================
# GEMINI AJANINA TANIMLANACAK ARAÇLAR (TOOLS / FUNCTIONS)
# =====================================================================

def execute_terminal_command(command: str) -> dict:
    """Lokal terminal/shell üzerinde belirtilen komutu çalıştırır ve çıktısını döndürür.
    
    Args:
        command: Terminalde çalıştırılacak shell komutu.
        
    Returns:
        stdout, stderr ve exit kodunu içeren bir sözlük.
    """
    logger.info(f"Terminal Komutu Çalıştırılıyor: {command}")
    try:
        # Komutu çalıştır (30 saniye timeout)
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        return {
            "status": "success",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        logger.error(f"Komut zaman aşımına uğradı: {command}")
        return {
            "status": "error",
            "message": "Command timed out after 30 seconds."
        }
    except Exception as e:
        logger.error(f"Komut çalıştırma hatası: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


def write_local_file(path: str, content: str) -> dict:
    """Belirtilen yerel dosya yoluna metin içeriği yazar veya mevcut dosyayı günceller.
    
    Args:
        path: Dosyanın kaydedileceği mutlak veya göreceli dosya yolu.
        content: Dosya içine yazılacak metin içeriği.
        
    Returns:
        İşlem durumunu belirten bir sözlük.
    """
    logger.info(f"Dosya Yazılıyor: {path}")
    try:
        # Eğer dosyanın üst dizinleri yoksa oluştur
        abs_path = os.path.abspath(path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        return {
            "status": "success",
            "message": f"Dosya başarıyla yazıldı: {abs_path}"
        }
    except Exception as e:
        logger.error(f"Dosya yazma hatası: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


def move_and_click_mouse(x: int, y: int, button: str = "left") -> dict:
    """Fare imlecini belirtilen piksel koordinatlarına götürür ve tıklar.
    
    Args:
        x: Ekrandaki yatay piksel koordinatı (0 en sol kenardır).
        y: Ekrandaki dikey piksel koordinatı (0 en üst kenardır).
        button: Tıklanacak buton ('left' veya 'right'). Varsayılan 'left'.
        
    Returns:
        İşlem durumunu belirten bir sözlük.
    """
    logger.info(f"Fare Hareketi ve Tıklama: ({x}, {y}) - Buton: {button}")
    try:
        x_val = int(x)
        y_val = int(y)
        btn = button.lower()
        if btn not in ["left", "right"]:
            btn = "left"
            
        # Ekran boyutunu kontrol et
        screen_width, screen_height = pyautogui.size()
        if x_val < 0 or x_val >= screen_width or y_val < 0 or y_val >= screen_height:
            return {
                "status": "error",
                "message": f"Koordinatlar ekran sınırları dışında! Ekran boyutu: {screen_width}x{screen_height}. Girilen: ({x_val}, {y_val})"
            }
            
        # Yumuşak bir geçiş için 0.5 saniyede hareket ettir
        pyautogui.moveTo(x_val, y_val, duration=0.5)
        pyautogui.click(button=btn)
        
        return {
            "status": "success",
            "message": f"İmleç ({x_val}, {y_val}) konumuna götürüldü ve '{btn}' tıklandı."
        }
    except pyautogui.FailSafeException:
        logger.error("Fare hareketi sırasında PyAutoGUI Güvenli İptal (FailSafe) tetiklendi!")
        return {
            "status": "error",
            "message": "PyAutoGUI FailSafeException triggered: Mouse was moved to a screen corner to abort action."
        }
    except Exception as e:
        logger.error(f"Fare tıklama hatası: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


def type_keyboard_text(text: str) -> dict:
    """Klavye simülasyonu ile o an odaklanmış olan alana metin yazar.
    
    Args:
        text: Klavyeden yazılacak metin.
        
    Returns:
        İşlem durumunu belirten bir sözlük.
    """
    logger.info(f"Klavye Yazısı Yazılıyor: {text}")
    try:
        # Doğal görünmesi için tuşlar arasına 0.05 saniye gecikme koyuyoruz
        pyautogui.write(text, interval=0.05)
        return {
            "status": "success",
            "message": f"Metin başarıyla yazıldı: {text}"
        }
    except Exception as e:
        logger.error(f"Klavye yazma hatası: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


def capture_screen_state() -> dict:
    """O anki masaüstü ekran görüntüsünü alır ve geçici bir PNG dosyası olarak kaydeder.
    Bu işlem tamamlandığında backend otonom olarak görseli multimodal analiz için sonraki adıma ekler.
    
    Returns:
        Masaüstü ekran görüntüsünün kaydedildiği geçici dosya bilgisi.
    """
    logger.info("Ekran Görüntüsü Alınıyor...")
    try:
        temp_dir = tempfile.gettempdir()
        timestamp = int(time.time() * 1000)
        filename = f"agent_screen_state_{timestamp}.png"
        screenshot_path = os.path.join(temp_dir, filename)
        
        # Ekran görüntüsünü al ve kaydet
        screenshot = pyautogui.screenshot()
        screenshot.save(screenshot_path)
        
        logger.info(f"Ekran görüntüsü kaydedildi: {screenshot_path}")
        return {
            "status": "success",
            "message": "Screen state successfully captured.",
            "screenshot_path": screenshot_path,
            "screenshot_url": f"/screenshots/{filename}",
            "has_image": True
        }
    except Exception as e:
        logger.error(f"Ekran görüntüsü alma hatası: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


# Modelin fonksiyonları tanıyabilmesi için liste
agent_tools = [
    execute_terminal_command,
    write_local_file,
    move_and_click_mouse,
    type_keyboard_text,
    capture_screen_state
]

# =====================================================================
# AJAN SİSTEM TALİMATI (SYSTEM INSTRUCTION)
# =====================================================================
SYSTEM_INSTRUCTION = (
    "You are an advanced, autonomous OS & Browser Agent. Your role is to complete tasks "
    "by interacting directly with the computer operating system. You have tools to execute "
    "shell commands, write local files, move/click the mouse, type text, and take screenshots.\n\n"
    "CRITICAL RULES:\n"
    "1. **Step-by-step execution**: Break down the user's request into minor actionable steps. "
    "Do not execute multiple visual/mouse/keyboard actions in a single turn without checking the visual state.\n"
    "2. **Visual Verification**: Every time you perform a GUI interaction (clicking, typing, opening browser), "
    "you MUST call `capture_screen_state` immediately after. The backend will inject the actual visual screen bytes "
    "into the next turn. Use this to verify that your action succeeded, see what's on the screen, and plan your next click coordinate.\n"
    "3. **Mouse Coordinates**: When you need to click, carefully calculate coordinates from the screen screenshots or use search tool outputs. "
    "If you make a mistake or click the wrong area, analyze the new screenshot, adjust coordinates, and try again.\n"
    "4. **Error handling**: If a command or tool returns an error, do not panic. Read the error message, adapt your plan, and "
    "propose a corrected command or action.\n"
    "5. **Completion**: Once the task is fully achieved, provide a concise summary of the steps you took and the final outcome to the user."
)


# =====================================================================
# FLASK ENDPOINT VE AJAN DÖNGÜSÜ (AGENT LOOP / ReAct)
# =====================================================================

@app.route("/agent", methods=["POST"])
def run_agent():
    """
    Kullanıcıdan gelen ana talimata (prompt) göre Gemini 2.5-Flash ile ReAct
    döngüsü başlatan ana endpoint.
    """
    # API Anahtarını al (Önce header, sonra çevre değişkeni)
    api_key_val = request.headers.get("X-Gemini-API-Key") or os.environ.get("GEMINI_API_KEY")
    if not api_key_val:
        logger.error("GEMINI_API_KEY bulunamadı!")
        return jsonify({
            "status": "error",
            "message": "GEMINI_API_KEY bulunamadı! Lütfen isteğe 'X-Gemini-API-Key' başlığı (header) ekleyin veya sunucu ortamında tanımlayın."
        }), 400

    data = request.get_json() or {}
    user_prompt = data.get("prompt")
    
    if not user_prompt:
        return jsonify({"error": "Lütfen 'prompt' alanını boş bırakmayın."}), 400
        
    logger.info(f"YENİ AJAN GÖREVİ BAŞLADI: '{user_prompt}'")
    
    # Sohbet/Döngü geçmişi (Contents listesi)
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_prompt)]
        )
    ]
    
    # Model yapılandırması
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0.2, # Döngünün stabil ve tutarlı çalışması için düşük sıcaklık
        tools=agent_tools
    )
    
    max_turns = 15 # Sonsuz döngüleri engellemek için maksimum adım sınırı
    turn = 0
    agent_steps_log = [] # Front-end veya API tüketicisi için adım logları
    
    try:
        # İstemciyi API anahtarıyla başlat
        client = genai.Client(api_key=api_key_val)

        while turn < max_turns:
            logger.info(f"--- AJAN ADIMI {turn + 1} ---")
            
            # 1. Gemini'dan yanıt iste
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=config
            )
            
            # Modelin ürettiği içeriği geçmişe ekle
            model_content = response.candidates[0].content
            contents.append(model_content)
            
            # Eğer model herhangi bir fonksiyon çağırmadıysa, döngü sonlanmıştır (Görevi tamamladı)
            if not response.function_calls:
                final_response_text = response.text or "Görev tamamlandı."
                logger.info("Ajan görevi başarıyla sonlandırdı.")
                agent_steps_log.append({
                    "step": turn + 1,
                    "action": "respond_to_user",
                    "response": final_response_text
                })
                break
                
            # 2. Fonksiyon çağrılarını sırayla işle
            tool_parts = []
            screenshot_to_attach = None
            
            for function_call in response.function_calls:
                name = function_call.name
                args = function_call.args
                
                logger.info(f"Model fonksiyon çağırdı: {name} - Argümanlar: {args}")
                
                # Fonksiyonu çalıştır
                if name == "execute_terminal_command":
                    result = execute_terminal_command(**args)
                elif name == "write_local_file":
                    result = write_local_file(**args)
                elif name == "move_and_click_mouse":
                    result = move_and_click_mouse(**args)
                elif name == "type_keyboard_text":
                    result = type_keyboard_text(**args)
                elif name == "capture_screen_state":
                    result = capture_screen_state()
                    # Eğer ekran görüntüsü başarıyla alındıysa, bir sonraki adıma iliştirmek için sakla
                    if result.get("status") == "success" and result.get("has_image"):
                        screenshot_to_attach = result.get("screenshot_path")
                else:
                    result = {"status": "error", "message": f"Bilinmeyen fonksiyon: {name}"}
                
                # Adım detaylarını loga kaydet
                agent_steps_log.append({
                    "step": turn + 1,
                    "action": "function_call",
                    "function_name": name,
                    "arguments": args,
                    "result": result
                })
                
                # Fonksiyon sonucunu Part formatına dönüştür
                part = types.Part.from_function_response(
                    name=name,
                    response=result
                )
                tool_parts.append(part)
                
            # 3. Eğer ekran görüntüsü alındıysa, bu görseli bir sonraki turn'e dahil et
            if screenshot_to_attach and os.path.exists(screenshot_to_attach):
                try:
                    with open(screenshot_to_attach, "rb") as img_file:
                        img_bytes = img_file.read()
                    
                    # Multimodal analiz için görsel Part nesnesi oluştur
                    img_part = types.Part.from_bytes(
                        data=img_bytes,
                        mime_type="image/png"
                    )
                    # Görseli fonksiyon yanıtı veren Content'e ekle
                    tool_parts.append(img_part)
                    logger.info("Ekran görüntüsü (multimodal veri) başarıyla sonraki adıma eklendi.")
                    
                    # Geçici dosyayı temizle (isteğe bağlı, disk dolmasını engellemek için)
                    # os.remove(screenshot_to_attach)
                except Exception as e:
                    logger.error(f"Görsel baytlarını eklerken hata oluştu: {str(e)}")
            
            # Fonksiyon yanıtlarını geçmişe ekle (role 'user' olmalı)
            contents.append(
                types.Content(
                    role="user",
                    parts=tool_parts
                )
            )
            
            turn += 1
            
        else:
            # Döngü sınırı aşıldıysa
            logger.warning("Maksimum ajan adım sınırına (max_turns) ulaşıldı.")
            final_response_text = "Maksimum adım sınırına ulaşıldı. Görev tamamlanamamış olabilir."
            
        return jsonify({
            "status": "success",
            "final_response": final_response_text,
            "steps": agent_steps_log
        })
        
    except Exception as e:
        logger.error(f"Ajan döngüsü sırasında beklenmeyen hata: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Ajan döngüsü sırasında beklenmeyen bir hata oluştu: {str(e)}",
            "steps": agent_steps_log
        }), 500


@app.route("/")
def index():
    """Ajan web kontrol panelini döner."""
    return render_template("index.html")


@app.route("/screenshots/<filename>")
def serve_screenshot(filename):
    """Geçici dizinden kaydedilen ekran görüntülerini servis eder."""
    return send_from_directory(tempfile.gettempdir(), filename)


# =====================================================================
# SİSTEM BİLGİSİ ENDPOINT
# =====================================================================

@app.route("/status", methods=["GET"])
def system_status():
    """Mevcut ekran boyutunu ve servis durumunu döner."""
    try:
        width, height = pyautogui.size()
        return jsonify({
            "status": "active",
            "screen_resolution": f"{width}x{height}",
            "failsafe_enabled": pyautogui.FAILSAFE,
            "python_version": sys.version
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    # Flask sunucusunu yerelde 5001 portunda çalıştır
    app.run(host="0.0.0.0", port=5001, debug=True)
