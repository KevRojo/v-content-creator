#!/usr/bin/env python3
"""
🎨 GEMINI WEB IMAGE GENERATOR — Playwright Edition
Genera imágenes usando Gemini Premium web chat (gemini.google.com)
Usa Playwright con perfil Chrome persistente (misma base que uploader.py).

Instalación:
    pip install playwright
    python -m playwright install chromium

Uso standalone:
    python gemini_image_gen.py --login                          # Verificar/setup login
    python gemini_image_gen.py --prompt "dark forest" --output img.png  # Generar una imagen
"""

import os
import sys
import time
import json
import argparse
import base64
import re
import shutil
import urllib.request
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding
import io
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
elif sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── Configuración ──────────────────────────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Reutiliza el mismo perfil de Playwright que uploader.py (ya logueado en Google)
PW_GEMINI_PROFILE = os.path.join(os.path.expanduser("~"), ".playwright-youtube")

# URL de Gemini
GEMINI_WEB_URL = "https://gemini.google.com/app"

# Timeouts
IMAGE_GEN_TIMEOUT = 120  # segundos para esperar generación de imagen
PAGE_LOAD_TIMEOUT = 30000  # ms para cargar página

# ── Utilidades ─────────────────────────────────────────────────────────────────

def log(msg, emoji="▸"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"  [{timestamp}] {emoji} {msg}")


def _create_gemini_browser(playwright, headless=False):
    """Crea un contexto de Playwright con perfil dedicado para Gemini (stealth mode)."""
    log("Abriendo Chrome con perfil Gemini...", "🌐")
    log(f"Perfil: {PW_GEMINI_PROFILE}", "📂")

    ctx = playwright.chromium.launch_persistent_context(
        user_data_dir=PW_GEMINI_PROFILE,
        channel="chrome",
        headless=headless,
        ignore_default_args=["--enable-automation"],  # Critical: removes automation flag
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            "--disable-extensions",
            "--disable-popup-blocking",
            "--disable-component-update",
            "--window-size=1400,900",
        ],
        viewport={"width": 1400, "height": 900},
        timeout=60000,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )

    if ctx.pages:
        page = ctx.pages[0]
    else:
        page = ctx.new_page()

    # Remove webdriver property from navigator to avoid detection
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        // Remove CDP artifacts
        if (window.chrome) {
            window.chrome.csi = function(){};
            window.chrome.loadTimes = function(){};
        }
    """)

    return ctx, page


def check_gemini_login(page):
    """Verifica si estamos logueados en Gemini."""
    log("Navegando a Gemini...", "🤖")
    try:
        page.goto(GEMINI_WEB_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
        page.wait_for_timeout(4000)
    except Exception as e:
        return False, f"Error navegando a Gemini: {e}"

    current_url = page.url

    # Si redirige a login de Google
    if "accounts.google.com" in current_url:
        return False, "No estás logueado en Google."

    # Si estamos en la página principal de Gemini
    if "gemini.google.com" in current_url:
        # Verificar que el input de chat esté disponible
        try:
            chat_input = _find_chat_input(page, timeout=8000)
            if chat_input:
                return True, "Gemini OK — logueado y listo"
        except:
            pass

        # Puede que haya un botón de "Try Gemini" o similar
        return True, "Gemini cargado (verificar input manualmente)"

    return False, f"URL inesperada: {current_url}"


def _find_chat_input(page, timeout=5000):
    """
    Encuentra el campo de entrada de chat en Gemini.
    Gemini usa varios selectores posibles.
    """
    # Lista de selectores conocidos para el input de Gemini (pueden cambiar)
    selectors = [
        # Rich text editor de Gemini
        "div.ql-editor[contenteditable='true']",
        "div[contenteditable='true'][aria-label*='prompt']",
        "div[contenteditable='true'][aria-label*='message']",
        "div[contenteditable='true'][aria-label*='Enter']",
        "div[contenteditable='true'][data-placeholder]",
        # Fallbacks más genéricos
        ".input-area div[contenteditable='true']",
        "rich-textarea div[contenteditable='true']",
        "div[contenteditable='true'][role='textbox']",
        # Textarea estándar (menos probable)
        "textarea[aria-label*='prompt']",
        "textarea[aria-label*='message']",
    ]

    for sel in selectors:
        try:
            elem = page.locator(sel).first
            if elem.is_visible(timeout=min(timeout, 3000)):
                log(f"Input encontrado: {sel}", "✓")
                return elem
        except:
            continue

    # Último intento: buscar cualquier contenteditable visible
    try:
        all_editable = page.locator("div[contenteditable='true']").all()
        for elem in all_editable:
            try:
                if elem.is_visible(timeout=1000):
                    box = elem.bounding_box()
                    if box and box['height'] > 20 and box['width'] > 200:
                        log("Input encontrado (contenteditable genérico)", "✓")
                        return elem
            except:
                continue
    except:
        pass

    return None


def _find_send_button(page, timeout=3000):
    """Encuentra el botón de enviar en Gemini."""
    selectors = [
        "button[aria-label*='Send']",
        "button[aria-label*='Enviar']",
        "button[aria-label*='send']",
        "button[aria-label*='Submit']",
        "button.send-button",
        # Material icon button
        "button:has(mat-icon)",
        "button[mattooltip*='Send']",
    ]

    for sel in selectors:
        try:
            elem = page.locator(sel).first
            if elem.is_visible(timeout=min(timeout, 2000)):
                return elem
        except:
            continue

    return None


def _start_new_chat(page):
    """Inicia un nuevo chat en Gemini."""
    log("Iniciando nuevo chat...", "💬")

    # Opción 1: navegar directamente a /app (siempre abre chat nuevo)
    try:
        page.goto(GEMINI_WEB_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
        page.wait_for_timeout(3000)
        return True
    except:
        pass

    # Opción 2: buscar botón de "New chat"
    new_chat_selectors = [
        "button[aria-label*='New chat']",
        "button[aria-label*='Nuevo chat']",
        "button[aria-label*='new chat']",
        "a[href='/app']",
        "[data-test-id='new-chat']",
    ]

    for sel in new_chat_selectors:
        try:
            elem = page.locator(sel).first
            if elem.is_visible(timeout=3000):
                elem.click()
                page.wait_for_timeout(2000)
                log("Nuevo chat iniciado", "✓")
                return True
        except:
            continue

    return False


def _send_prompt(page, prompt_text):
    """
    Escribe un prompt en el chat y lo envía.
    Retorna True si se envió exitosamente.
    """
    # Encontrar input
    chat_input = _find_chat_input(page, timeout=10000)
    if not chat_input:
        log("No se encontró el campo de entrada", "❌")
        return False

    # Limpiar y escribir
    try:
        chat_input.click()
        page.wait_for_timeout(500)

        # Limpiar contenido existente
        chat_input.press("Control+a")
        page.wait_for_timeout(200)

        # Escribir el prompt (usar fill para contenteditable o type)
        try:
            chat_input.fill(prompt_text)
        except:
            # Fallback: escribir carácter por carácter (más lento pero más seguro)
            chat_input.type(prompt_text, delay=20)

        page.wait_for_timeout(500)

    except Exception as e:
        log(f"Error escribiendo prompt: {e}", "❌")
        return False

    # Enviar
    # Método 1: Enter
    try:
        chat_input.press("Enter")
        log("Prompt enviado (Enter)", "✓")
        return True
    except:
        pass

    # Método 2: Botón send
    send_btn = _find_send_button(page)
    if send_btn:
        try:
            send_btn.click()
            log("Prompt enviado (botón)", "✓")
            return True
        except:
            pass

    log("No se pudo enviar el prompt", "❌")
    return False


def _wait_for_images(page, prev_response_count=0, timeout_seconds=IMAGE_GEN_TIMEOUT):
    """
    Espera a que Gemini genere imágenes y las muestre.
    Retorna una lista de URLs de las imágenes generadas, o [].
    """
    log(f"Esperando generación de imagen (max {timeout_seconds}s)...", "⏳")

    start_time = time.time()
    last_status = ""
    check_interval = 3  # segundos entre checks

    while time.time() - start_time < timeout_seconds:
        elapsed = int(time.time() - start_time)

        # Verificar si hay indicadores de carga/progreso
        try:
            # Gemini muestra un spinner o "thinking" mientras genera
            is_generating = page.locator("model-response .loading, .thinking-indicator, [aria-label*='Loading'], mat-progress-spinner").first.is_visible(timeout=500)
            if is_generating and elapsed % 10 == 0:
                log(f"Generando... ({elapsed}s)", "⏳")
        except:
            pass

        # Asegurarnos de que ha aparecido una NUEVA respuesta si prev_response_count > 0
        try:
            current_responses = page.locator("model-response, .model-response-text, .response-container").all()
            if prev_response_count > 0 and len(current_responses) <= prev_response_count:
                # Todavía no ha empezado la nueva respuesta
                time.sleep(check_interval)
                continue
            
            # Si hay una nueva respuesta, verifiquemos si está terminada o aún cargando
            if len(current_responses) > prev_response_count:
                last_response = current_responses[-1]
                # Si el estado de la respuesta última parece estar cargando todavía:
                if last_response.locator(".loading, .thinking-indicator, mat-progress-spinner").count() > 0:
                    time.sleep(check_interval)
                    continue
        except:
            pass

        # Esperar un momento adicional para que el DOM renderice la nueva imagen
        if prev_response_count > 0 and len(current_responses) > prev_response_count:
            page.wait_for_timeout(2000)

        # Buscar imágenes en la última respuesta del modelo
        image_urls = _extract_response_images(page)
        if image_urls:
            log(f"¡{len(image_urls)} imagen(es) encontrada(s)! ({elapsed}s)", "🖼️")
            return image_urls

        # Verificar si hay un error o rechazo
        try:
            error_texts = [
                "I can't generate",
                "I'm not able to",
                "no puedo generar",
                "unable to create",
                "I can't create images",
                "can't help with that",
                "against our policies",
            ]
            # Obtener el texto de la última respuesta
            response_elems = page.locator("model-response, .model-response-text, .response-container").all()
            if response_elems:
                last_response = response_elems[-1]
                try:
                    resp_text = last_response.inner_text(timeout=2000)
                    for error in error_texts:
                        if error.lower() in resp_text.lower():
                            log(f"Gemini rechazó la generación: '{error}'", "⚠️")
                            return []
                except:
                    pass
        except:
            pass

        # Verificar si la respuesta ya terminó (sin imágenes)
        try:
            # Si ya hay texto de respuesta completo pero sin imágenes tras 30s, puede que no haya generado
            if elapsed > 30:
                response_complete = False
                # Verificar si el botón de enviar está disponible de nuevo (indica respuesta completa)
                send_btn = _find_send_button(page, timeout=1000)
                chat_input = _find_chat_input(page, timeout=1000)
                if send_btn or chat_input:
                    # Doble-check: buscar imágenes una vez más
                    image_urls = _extract_response_images(page)
                    if image_urls:
                        return image_urls
                    # Si no hay imágenes pero sí hay respuesta, esperar un poco más
                    # (las imágenes pueden tardar en renderizar)
                    if elapsed > 60:
                        log("Respuesta completa pero sin imágenes detectadas", "⚠️")
                        return []
        except:
            pass

        time.sleep(check_interval)

    log(f"Timeout ({timeout_seconds}s) esperando imágenes", "❌")
    return []


def _extract_response_images(page):
    """
    Extrae URLs de imágenes de la ÚLTIMA respuesta de Gemini.
    Retorna lista de URLs.
    """
    image_urls = []

    # Selectores puramente relativos a la respuesta para buscar imágenes generadas
    image_selectors = [
        "img[src*='blob:']",
        "img[src*='lh3.googleusercontent']",
        "img[src*='encrypted']",
        "img[src*='lh3']",
        "img[data-test-id*='image']",
        "img[alt*='Generated']",
        ".generated-image img",
        ".image-container img",
        "img", # Genérico como fallback final
    ]

    seen_urls = set()

    try:
        # Importante: buscar SOLO dentro de la última respuesta para evitar imágenes pasadas
        response_elems = page.locator("model-response, .model-response-text, .response-container").all()
        if response_elems:
            # Seleccionamos la última respuesta válida
            container = response_elems[-1]
        else:
            container = page

        for sel in image_selectors:
            try:
                # Buscar dentro del contenedor específico (última respuesta)
                imgs = container.locator(sel).all()
                for img in imgs:
                    try:
                        src = img.get_attribute("src")
                        if not src:
                            continue

                        # Filtrar imágenes demasiado pequeñas (avatars, icons)
                        try:
                            box = img.bounding_box()
                            if box and (box['width'] < 100 or box['height'] < 100):
                                continue
                        except:
                            pass

                        # Filtrar URLs de sistema/UI (avatars, logos)
                        skip_patterns = [
                            'avatar', 'icon', 'logo', 'favicon', 'emoji',
                            'data:image/svg', 'gstatic.com/og',
                        ]
                        if any(p in src.lower() for p in skip_patterns):
                            continue

                        if src not in seen_urls:
                            seen_urls.add(src)
                            image_urls.append(src)

                    except Exception:
                        continue
            except:
                continue
    except Exception as e:
        log(f"Error extrayendo imágenes: {e}", "⚠️")

    return image_urls


def _download_image(page, img_url, output_path):
    """
    Descarga una imagen desde una URL (blob: o http).
    Para blob URLs necesitamos usar el contexto del navegador.
    """
    try:
        if img_url.startswith("blob:"):
            # Blob URLs requieren fetch dentro del navegador
            log("Descargando imagen (blob URL)...", "⬇️")

            # Usar JavaScript para convertir blob a base64
            b64_data = page.evaluate("""
                async (url) => {
                    try {
                        const response = await fetch(url);
                        const blob = await response.blob();
                        return new Promise((resolve, reject) => {
                            const reader = new FileReader();
                            reader.onloadend = () => resolve(reader.result);
                            reader.onerror = reject;
                            reader.readAsDataURL(blob);
                        });
                    } catch (e) {
                        return 'ERROR: ' + e.message;
                    }
                }
            """, img_url)

            if b64_data and "base64," in b64_data:
                # Extraer datos base64
                raw_b64 = b64_data.split("base64,")[1]
                img_bytes = base64.b64decode(raw_b64)

                if len(img_bytes) > 5000:  # Verificar que no sea una imagen vacía
                    with open(output_path, 'wb') as f:
                        f.write(img_bytes)
                    log(f"Imagen guardada: {os.path.basename(output_path)} ({len(img_bytes)//1024}KB)", "✅")
                    return True
                else:
                    log(f"Imagen demasiado pequeña ({len(img_bytes)} bytes)", "⚠️")
                    return False
            else:
                log(f"No se pudo convertir blob a base64: {b64_data[:100] if b64_data else 'null'}", "⚠️")
                return False

        elif img_url.startswith("http"):
            # URLs HTTP/HTTPS normales (lh3.googleusercontent.com, etc.)
            log("Descargando imagen (HTTP con auth)...", "⬇️")

            # Método 1: Usar el navegador para descargar (mantiene cookies/auth)
            try:
                b64_data = page.evaluate("""
                    async (url) => {
                        try {
                            const response = await fetch(url, { 
                                credentials: 'include',
                                headers: {
                                    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8'
                                }
                            });
                            if (!response.ok) {
                                return 'HTTP_ERROR: ' + response.status;
                            }
                            const blob = await response.blob();
                            return new Promise((resolve, reject) => {
                                const reader = new FileReader();
                                reader.onloadend = () => resolve(reader.result);
                                reader.onerror = reject;
                                reader.readAsDataURL(blob);
                            });
                        } catch (e) {
                            return 'ERROR: ' + e.message;
                        }
                    }
                """, img_url)

                if b64_data and "base64," in b64_data:
                    raw_b64 = b64_data.split("base64,")[1]
                    img_bytes = base64.b64decode(raw_b64)

                    if len(img_bytes) > 5000:
                        with open(output_path, 'wb') as f:
                            f.write(img_bytes)
                        log(f"Imagen guardada: {os.path.basename(output_path)} ({len(img_bytes)//1024}KB)", "✅")
                        return True
                    else:
                        log(f"Imagen demasiado pequeña ({len(img_bytes)} bytes)", "⚠️")
                elif b64_data and (b64_data.startswith("ERROR:") or b64_data.startswith("HTTP_ERROR:")):
                    log(f"Error del navegador al descargar: {b64_data}", "⚠️")
                else:
                    log(f"Respuesta inesperada del navegador: {str(b64_data)[:100]}", "⚠️")
            except Exception as e:
                log(f"Error en fetch del navegador: {e}", "⚠️")

            # Método 2: Intentar obtener URL de alta resolución (modificar parámetros de tamaño)
            try:
                log("Intentando URL de alta resolución...", "🔄")
                # Las URLs de googleusercontent tienen parámetros como =s512, =w512, etc.
                # Podemos modificarlo para obtener la imagen original o mayor tamaño
                high_res_url = re.sub(r'=s\d+', '=s2048', img_url)  # Cambiar tamaño a 2048px
                high_res_url = re.sub(r'=w\d+', '=w2048', high_res_url)  # Cambiar ancho a 2048px
                
                if high_res_url != img_url:
                    b64_data = page.evaluate("""
                        async (url) => {
                            try {
                                const response = await fetch(url, { credentials: 'include' });
                                if (!response.ok) return 'HTTP_ERROR: ' + response.status;
                                const blob = await response.blob();
                                return new Promise((resolve, reject) => {
                                    const reader = new FileReader();
                                    reader.onloadend = () => resolve(reader.result);
                                    reader.onerror = reject;
                                    reader.readAsDataURL(blob);
                                });
                            } catch (e) {
                                return 'ERROR: ' + e.message;
                            }
                        }
                    """, high_res_url)
                    
                    if b64_data and "base64," in b64_data:
                        raw_b64 = b64_data.split("base64,")[1]
                        img_bytes = base64.b64decode(raw_b64)
                        if len(img_bytes) > 5000:
                            with open(output_path, 'wb') as f:
                                f.write(img_bytes)
                            log(f"Imagen alta resolución guardada: {os.path.basename(output_path)} ({len(img_bytes)//1024}KB)", "✅")
                            return True
            except Exception as e:
                log(f"Error descargando alta resolución: {e}", "⚠️")

            # Método 3: Descargar usando el contexto de Playwright (mejor para auth)
            try:
                log("Intentando descarga via Playwright context...", "🔄")
                response = page.request.get(img_url)
                if response.ok:
                    img_bytes = response.body()
                    if len(img_bytes) > 5000:
                        with open(output_path, 'wb') as f:
                            f.write(img_bytes)
                        log(f"Imagen guardada: {os.path.basename(output_path)} ({len(img_bytes)//1024}KB)", "✅")
                        return True
                    else:
                        log(f"Imagen demasiado pequeña ({len(img_bytes)} bytes)", "⚠️")
                else:
                    log(f"Playwright request falló: {response.status}", "⚠️")
            except Exception as e:
                log(f"Error descargando con Playwright: {e}", "⚠️")

            # Método 4: Descargar directamente con urllib (último recurso, suele fallar con 403)
            try:
                log("Intentando descarga directa (urllib)...", "🔄")
                req = urllib.request.Request(img_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                    "Referer": "https://gemini.google.com/",
                })
                with urllib.request.urlopen(req, timeout=30) as resp:
                    img_bytes = resp.read()
                    if len(img_bytes) > 5000:
                        with open(output_path, 'wb') as f:
                            f.write(img_bytes)
                        log(f"Imagen guardada: {os.path.basename(output_path)} ({len(img_bytes)//1024}KB)", "✅")
                        return True
            except Exception as e:
                log(f"Error descargando con urllib: {e}", "⚠️")

            return False

        else:
            log(f"URL no soportada: {img_url[:60]}", "❌")
            return False

    except Exception as e:
        log(f"Error descargando imagen: {e}", "❌")
        return False


def _save_image_via_right_click(page, img_element, output_path):
    """
    Intenta guardar una imagen usando el menú contextual del navegador.
    Alternativa cuando _download_image falla.
    """
    try:
        # Intentar obtener src del elemento directamente
        src = img_element.get_attribute("src")
        if src:
            return _download_image(page, src, output_path)
    except:
        pass

    # Intentar screenshot del elemento como último recurso
    try:
        log("Usando screenshot como fallback...", "📸")
        img_element.screenshot(path=output_path)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 5000:
            log(f"Screenshot guardado: {os.path.basename(output_path)}", "✅")
            return True
    except Exception as e:
        log(f"Error con screenshot: {e}", "⚠️")

    return False


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCIONES PRINCIPALES
# ═══════════════════════════════════════════════════════════════════════════════

def _save_image_via_right_click(page, img_element, output_path):
    """
    Intenta guardar una imagen usando el menú contextual del navegador.
    Alternativa cuando _download_image falla.
    """
    try:
        # Intentar obtener src del elemento directamente
        src = img_element.get_attribute("src")
        if src:
            return _download_image(page, src, output_path)
    except:
        pass

    # Intentar screenshot del elemento como último recurso
    try:
        log("Usando screenshot como fallback...", "📸")
        img_element.screenshot(path=output_path)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 5000:
            log(f"Screenshot guardado: {os.path.basename(output_path)}", "✅")
            return True
    except Exception as e:
        log(f"Error con screenshot: {e}", "⚠️")

    return False


def generate_single_image(page, prompt, output_path, image_index=0, is_short=False):
    """
    Genera una imagen en Gemini web chat y la guarda.

    Args:
        page: Playwright page ya logueada en Gemini
        prompt: Prompt de imagen (en inglés, como los de SDXL)
        output_path: Ruta donde guardar la imagen
        image_index: Índice para seleccionar cuál imagen del resultado (Gemini puede generar varias)
        is_short: Si es True, instruye al modelo a generar en formato vertical (9:16)

    Returns:
        True si la imagen fue generada y guardada exitosamente
    """
    # Prefijo para la generación de imágenes
    if is_short:
        full_prompt = f"Generate a high-quality vertical image (9:16 portrait aspect ratio): {prompt}"
    else:
        full_prompt = f"Generate a high-quality image (16:9 landscape aspect ratio): {prompt}"

    try:
        prev_responses = len(page.locator("model-response, .model-response-text, .response-container").all())
    except:
        prev_responses = 0

    log(f"Prompt: {prompt[:80]}...", "🎨")

    # Enviar prompt
    if not _send_prompt(page, full_prompt):
        log("Fallo al enviar prompt", "❌")
        return False

    # Esperar imágenes de LA NUEVA respuesta
    image_urls = _wait_for_images(page, prev_response_count=prev_responses, timeout_seconds=IMAGE_GEN_TIMEOUT)

    if not image_urls:
        log("No se obtuvieron imágenes", "❌")
        return False

    # Seleccionar la imagen (primera por defecto, o la indicada por índice)
    target_idx = min(image_index, len(image_urls) - 1)
    target_url = image_urls[target_idx]

    log(f"Descargando imagen {target_idx + 1}/{len(image_urls)}...", "⬇️")

    # Intentar descargar
    if _download_image(page, target_url, output_path):
        return True

    # Fallback: screenshot de la imagen directamente
    log("Intentando fallback con screenshot...", "🔄")
    try:
        # Buscar el elemento img con esta URL
        img_elem = page.locator(f"img[src='{target_url}']").first
        if img_elem.is_visible(timeout=3000):
            return _save_image_via_right_click(page, img_elem, output_path)
    except:
        pass

    # Último fallback: screenshot de TODAS las imágenes visibles
    try:
        all_imgs = page.locator("model-response img, .response-container img").all()
        for img in all_imgs:
            try:
                box = img.bounding_box()
                if box and box['width'] > 200 and box['height'] > 200:
                    img.screenshot(path=output_path)
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 5000:
                        log(f"Guardada via screenshot: {os.path.basename(output_path)}", "✅")
                        return True
            except:
                continue
    except:
        pass

    log("No se pudo guardar la imagen", "❌")
    return False


def generate_images_batch(prompts_data, on_progress=None, is_short=False, initial_chat_url=None):
    """
    Genera múltiples imágenes usando Gemini web chat.

    Args:
        prompts_data: Lista de dicts [{'prompt': str, 'output_path': str}, ...]
        on_progress: Callback opcional (index, total, success)
        is_short: Si es True, pasa la bandera de resolución vertical a generate_single_image
        initial_chat_url: Si se provee, la primera imagen intentará usar este chat en lugar de crear uno nuevo.
    
    Returns:
        int: número de imágenes generadas exitosamente
    """
    from playwright.sync_api import sync_playwright

    if not prompts_data:
        return 0

    log(f"Generando {len(prompts_data)} imagen(es) via Gemini Web...", "🎨")

    success_count = 0

    with sync_playwright() as p:
        ctx, page = _create_gemini_browser(p)

        try:
            # Verificar login
            ok, msg = check_gemini_login(page)
            if not ok:
                log(f"Login fallido: {msg}", "❌")
                log("Ejecuta: python gemini_image_gen.py --login", "💡")
                return 0

            log("Login verificado ✓", "✅")

            chat_url = initial_chat_url

            for i, item in enumerate(prompts_data):
                prompt = item['prompt']
                output_path = item['output_path']

                print(f"\n  {'─' * 50}")
                log(f"Imagen {i+1}/{len(prompts_data)}", "🖼️")

                if i == 0:
                    if chat_url:
                        # Reusar el chat donde se generó la historia si se proporcionó uno
                        if page.url != chat_url:
                            log("Volviendo al chat de la historia para las imágenes...", "🔄")
                            page.goto(chat_url, wait_until="domcontentloaded")
                            page.wait_for_timeout(2000)
                    else:
                        # Iniciar nuevo chat solo si no tenemos uno inicial
                        _start_new_chat(page)

                if i > 0:
                    # Mantener el contexto de la historia
                    if chat_url and page.url != chat_url:
                        log("Volviendo al chat de la historia para mantener consistencia...", "🔄")
                        page.goto(chat_url, wait_until="domcontentloaded")
                        page.wait_for_timeout(2000)
                    else:
                        log("Continuando en el chat actual para consistencia de imágenes...", "💬")

                success = generate_single_image(page, prompt, output_path, is_short=is_short)

                if i == 0 and success and not chat_url:
                    # Solo guardar nuevo chat_url si empezamos uno desde cero
                    chat_url = page.url
                    log(f"Link del chat de imágenes guardado: {chat_url}", "🔗")

                if success:
                    success_count += 1

                if on_progress:
                    on_progress(i, len(prompts_data), success)

                # Pausa entre generaciones para no spamear
                if i < len(prompts_data) - 1:
                    page.wait_for_timeout(3000)

        except Exception as e:
            log(f"Error general: {e}", "❌")
        finally:
            ctx.close()
            log("Chrome cerrado", "🔒")

    log(f"Resultado: {success_count}/{len(prompts_data)} imágenes generadas", "📊")
    return success_count


def generate_story_web(prompt_text):
    """
    Genera una historia usando Gemini Web Chat.
    Retorna (texto_historia, chat_url) o (None, None) en caso de error.
    """
    from playwright.sync_api import sync_playwright
    import time

    log("Generando historia via Gemini Web...", "🧠")

    with sync_playwright() as p:
        ctx, page = _create_gemini_browser(p)
        try:
            ok, msg = check_gemini_login(page)
            if not ok:
                log(f"Login fallido: {msg}", "❌")
                return None, None

            _start_new_chat(page)
            page.wait_for_timeout(2000)

            # Guardar el estado previo de las respuestas
            try:
                responses_before = page.locator("model-response, .model-response-text, .response-container").all()
                count_before = len(responses_before)
                text_before = responses_before[-1].inner_text(timeout=1000) if count_before > 0 else ""
            except:
                count_before = 0
                text_before = ""

            log("Enviando prompt de historia...", "📝")
            if not _send_prompt(page, prompt_text):
                log("No se pudo enviar el prompt de historia", "❌")
                return None, None

            # Esperar a que comience la respuesta
            log("Esperando respuesta...", "⏳")
            start_time = time.time()
            check_interval = 2
            timeout_seconds = 180  # Darle suficiente tiempo para historias largas

            last_text = ""
            stable_count = 0

            while time.time() - start_time < timeout_seconds:
                elapsed = int(time.time() - start_time)
                
                try:
                    current_responses = page.locator("model-response, .model-response-text, .response-container").all()
                    if len(current_responses) > count_before or (current_responses and current_responses[-1].inner_text(timeout=1000) != text_before):
                        # Hubo cambio: hay una nueva respuesta escribiéndose
                        last_response = current_responses[-1]
                        current_text = last_response.inner_text(timeout=1000)
                        
                        # Si el texto es sustancial y no ha cambiado en varias iteraciones seguidas
                        if current_text and len(current_text) > 80 and current_text == last_text:
                            stable_count += 1
                        else:
                            last_text = current_text
                            stable_count = 0
                            
                        # 3 iteraciones idénticas (6 segundos) -> generación finalizada
                        if stable_count >= 3:
                            log(f"Historia generada ({len(current_text.split())} palabras)", "✅")
                            chat_url = page.url
                            return current_text, chat_url
                            
                        if elapsed % 4 == 0:
                            log(f"Gemini escribiendo... ({len(current_text.split())} palabras, {elapsed}s)", "✍️")
                except Exception as e:
                    pass

                time.sleep(check_interval)

            log("Timeout esperando la historia", "❌")
            return None, None

        except Exception as e:
            log(f"Error en generate_story_web: {e}", "❌")
            return None, None
        finally:
            ctx.close()


def verify_login_interactive():
    """
    Abre Chrome para que el usuario se loguee en Gemini.
    Similar al flujo de login de YouTube en uploader.py.
    """
    from playwright.sync_api import sync_playwright

    print()
    print("  ═══════════════════════════════════════════════════════════════")
    print("   🤖 GEMINI WEB — Verificación de Login")
    print("  ═══════════════════════════════════════════════════════════════")
    print()

    with sync_playwright() as p:
        ctx, page = _create_gemini_browser(p)

        try:
            ok, msg = check_gemini_login(page)

            if ok:
                log("✅ ¡Estás logueado en Gemini!", "🎉")
                log(msg, "ℹ️")
                log("Tu sesión queda guardada para futuras generaciones", "💾")

                # Test rápido: verificar que podemos escribir
                chat_input = _find_chat_input(page, timeout=5000)
                if chat_input:
                    log("Campo de entrada detectado — ¡Todo listo!", "✅")
                else:
                    log("Campo de entrada no detectado (puede requerir actualizar selectores)", "⚠️")

            else:
                print()
                print("  ╔══════════════════════════════════════════════════════╗")
                print("  ║  PRIMERA VEZ — Necesitas loguearte                  ║")
                print("  ║                                                      ║")
                print("  ║  1. Loguéate con tu cuenta de Google                 ║")
                print("  ║  2. Asegúrate de tener Gemini Premium                ║")
                print("  ║  3. La sesión se guarda automáticamente              ║")
                print("  ╚══════════════════════════════════════════════════════╝")
                print()

                log("Navegando a Google login...", "🔗")
                page.goto("https://accounts.google.com/ServiceLogin",
                           wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)

                log("Loguéate en la ventana de Chrome...", "⏳")
                log("Esperando hasta 3 minutos para que completes el login...", "⏰")

                # Esperar login
                logged_in = False
                for i in range(180):  # 3 minutos
                    time.sleep(1)
                    try:
                        url = page.url
                        if "gemini.google.com" in url or ("google.com" in url and "accounts" not in url and "ServiceLogin" not in url):
                            logged_in = True
                            break
                    except:
                        pass
                    if i % 15 == 0 and i > 0:
                        log(f"Esperando login... ({180-i}s restantes)", "⏳")

                if logged_in:
                    log("✅ ¡Login detectado!", "🎉")
                    # Navegar a Gemini para confirmar
                    page.goto(GEMINI_WEB_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
                    time.sleep(4)
                    log(f"URL: {page.url}", "🔗")
                    log("Tu sesión queda guardada para futuras generaciones", "💾")
                else:
                    log("Timeout esperando login. Inténtalo de nuevo.", "⚠️")

        finally:
            input("\n  Presiona ENTER para cerrar el navegador...")
            ctx.close()
            log("Chrome cerrado", "🔒")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="🎨 Gemini Web Image Generator")
    parser.add_argument("--login", action="store_true", help="Verificar/setup login en Gemini")
    parser.add_argument("--prompt", type=str, help="Prompt para generar imagen")
    parser.add_argument("--output", type=str, default="gemini_output.png", help="Ruta de salida")
    parser.add_argument("--batch", type=str, help="Archivo JSON con lista de prompts [{prompt, output_path}, ...]")
    args = parser.parse_args()

    if args.login:
        verify_login_interactive()
        return

    if args.batch:
        with open(args.batch, 'r', encoding='utf-8') as f:
            prompts = json.load(f)
        count = generate_images_batch(prompts)
        print(f"\n  ✅ {count}/{len(prompts)} imágenes generadas")
        return

    if args.prompt:
        prompts = [{'prompt': args.prompt, 'output_path': args.output}]
        count = generate_images_batch(prompts)
        if count > 0:
            print(f"\n  ✅ Imagen guardada en: {args.output}")
        else:
            print(f"\n  ❌ No se pudo generar la imagen")
        return

    # Si no hay opciones, mostrar ayuda
    parser.print_help()
    print("\n  Ejemplos:")
    print("    python gemini_image_gen.py --login")
    print("    python gemini_image_gen.py --prompt 'dark forest at night, cinematic' --output test.png")


if __name__ == "__main__":
    main()
