#!/usr/bin/env python3
"""
YouTube Uploader Pro — Playwright Edition v3.0
Sube videos a YouTube Studio usando Chrome perfil guardado.
Incluye menu interactivo para selección de videos.

Instalación:
    pip install playwright
    python -m playwright install chromium

Uso:
    python uploader.py                  # Menú interactivo
    python uploader.py --auto           # Subir todos los pendientes
    python uploader.py --file video.mp4 # Subir un video específico
"""

import os
import sys
import json
import glob
import time
import argparse
from datetime import datetime
from pathlib import Path

# -- Configuración --------------------------------------------------------------
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(PROJECT_DIR, "output")

# Perfil dedicado de Playwright (separado del Chrome principal)
# Chrome bloquea remote debugging en su User Data dir por seguridad
PW_PROFILE = os.path.join(os.path.expanduser("~"), ".playwright-youtube")

# Perfil separado para TikTok (no comparte sesión con YouTube)
PW_TIKTOK_PROFILE = os.path.join(os.path.expanduser("~"), ".playwright-tiktok")
TIKTOK_UPLOADS_FILE = os.path.join(OUT_DIR, "tiktok_uploads.json")

# -- Utilidades -----------------------------------------------------------------
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def log(msg, emoji="▸"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"  [{timestamp}] {emoji} {msg}")

def format_size(size_bytes):
    """Formatea bytes a MB legible"""
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"

def find_all_videos():
    """Encuentra todos los videos con sus metadatos"""
    videos = []
    seen_files = set()

    if not os.path.isdir(OUT_DIR):
        return videos

    for json_file in sorted(glob.glob(os.path.join(OUT_DIR, "*_video_info.json"))):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    info = json.load(f)

                # Encontrar archivo video
                video_path = info.get('video', {}).get('path', '')
                if not os.path.exists(video_path):
                    video_filename = info.get('video', {}).get('filename', '')
                    video_path = os.path.join(out_dir, video_filename)

                if not os.path.exists(video_path):
                    continue

                # Evitar duplicados
                base_name = os.path.basename(video_path)
                if base_name in seen_files:
                    continue
                seen_files.add(base_name)

                file_size = os.path.getsize(video_path)
                uploaded = info.get('upload', {}).get('uploaded', False)
                has_error = bool(info.get('upload', {}).get('last_error'))
                source = "LOCAL"

                is_short = info.get('video', {}).get('is_short', False)

                videos.append({
                    'video': video_path,
                    'info_path': json_file,
                    'data': info,
                    'title': info.get('video', {}).get('title', 'Sin título'),
                    'youtube_title': info.get('video', {}).get('youtube_title', ''),
                    'size': file_size,
                    'uploaded': uploaded,
                    'has_error': has_error,
                    'error_msg': info.get('upload', {}).get('last_error', ''),
                    'url': info.get('upload', {}).get('video_url', ''),
                    'created': info.get('created_at', ''),
                    'source': source,
                    'is_short': is_short,
                })
            except Exception as e:
                continue

    return videos

def update_upload_status(info_path, video_id=None, video_url=None, error=None):
    """Actualiza el estado de upload en el JSON"""
    try:
        with open(info_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if 'upload' not in data:
            data['upload'] = {}

        data['upload']['uploaded'] = error is None
        data['upload']['uploaded_at'] = datetime.now().isoformat() if error is None else None

        if video_id:
            data['upload']['video_id'] = video_id
        if video_url:
            data['upload']['video_url'] = video_url
        if error:
            data['upload']['last_error'] = str(error)
        elif 'last_error' in data['upload']:
            del data['upload']['last_error']

        with open(info_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        log(f"Error actualizando status: {e}", "⚠")
        return False


# -- TikTok Tracking (separado de YouTube) --------------------------------------
def _get_tiktok_uploads_path():
    """Retorna la ruta al archivo de tracking de TikTok"""
    return TIKTOK_UPLOADS_FILE

def load_tiktok_uploads():
    """Carga el registro de uploads a TikTok"""
    path = _get_tiktok_uploads_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"uploaded": {}}

def save_tiktok_upload(video_filename, tiktok_url=None, error=None):
    """Registra un upload (o error) de TikTok sin tocar los JSONs de YouTube"""
    data = load_tiktok_uploads()
    if error:
        data["uploaded"][video_filename] = {
            "uploaded_at": None,
            "tiktok_url": None,
            "last_error": error
        }
    else:
        data["uploaded"][video_filename] = {
            "uploaded_at": datetime.now().isoformat(),
            "tiktok_url": tiktok_url,
            "last_error": None
        }
    path = _get_tiktok_uploads_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def find_tiktok_pending():
    """Encuentra videos pendientes de subir a TikTok (lee JSONs de YouTube, filtra con tracking propio)"""
    all_videos = find_all_videos()
    tiktok_data = load_tiktok_uploads()
    uploaded_files = tiktok_data.get("uploaded", {})

    pending = []
    uploaded = []
    for v in all_videos:
        filename = os.path.basename(v['video'])
        entry = uploaded_files.get(filename, {})
        is_uploaded = entry.get("uploaded_at") is not None
        has_error = bool(entry.get("last_error"))

        v['tiktok_uploaded'] = is_uploaded
        v['tiktok_error'] = has_error
        v['tiktok_error_msg'] = entry.get("last_error", "")
        v['tiktok_url'] = entry.get("tiktok_url", "")

        if is_uploaded:
            uploaded.append(v)
        else:
            pending.append(v)

    return pending, uploaded, all_videos


# -- Playwright Browser ---------------------------------------------------------
def create_browser_context(playwright, headless=False):
    """Crea un contexto de Playwright con perfil dedicado"""
    log("Abriendo Chrome con perfil Playwright...", "🌐")
    log(f"Perfil: {PW_PROFILE}", "📂")

    ctx = playwright.chromium.launch_persistent_context(
        user_data_dir=PW_PROFILE,
        channel="chrome",
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--start-maximized",
        ],
        no_viewport=True,
        timeout=60000,
    )

    # Usar la página que ya viene abierta en vez de crear nueva
    if ctx.pages:
        page = ctx.pages[0]
    else:
        page = ctx.new_page()

    return ctx, page


def check_youtube_login(page):
    """Verifica que estemos logueados en YouTube Studio"""
    log("Navegando a YouTube Studio...", "📺")
    page.goto("https://studio.youtube.com", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    current_url = page.url
    log(f"URL: {current_url}", "🔗")

    if "accounts.google.com" in current_url:
        return False, "No estas logueado. Abre Chrome, loguéate en YouTube, y ciérralo."
    elif "studio.youtube.com" in current_url:
        return True, "YouTube Studio OK"
    else:
        return False, f"URL inesperada: {current_url}"


def upload_single_video(page, video_path, info_data):
    """
    Sube un video a YouTube Studio usando una página ya abierta.
    Retorna (success, video_url, error_message)
    """
    from playwright.sync_api import TimeoutError as PWTimeout

    video_info = info_data.get('video', {})
    production_info = info_data.get('production', {})
    title = video_info.get('youtube_title', video_info.get('title', 'Relato de Terror'))
    description = video_info.get('description', '')
    tags = video_info.get('tags', [])
    privacy = video_info.get('privacy', 'public')
    thumbnail_path = production_info.get('thumbnail_source', '')

    # Truncar título si es necesario (límite de YouTube: 100 chars)
    if len(title) > 100:
        title = title[:97] + "..."

    try:
        # Asegurarnos de estar en YouTube Studio
        if "studio.youtube.com" not in page.url:
            page.goto("https://studio.youtube.com", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

        # -- Clic en botón CREATE --
        log("Buscando botón CREATE...", "[BUSCAR]")
        create_clicked = False

        create_selectors = [
            "#create-icon",
            "ytcp-button#create-icon",
            "[aria-label='Create']",
            "[aria-label='Crear']",
            "button#create-icon",
        ]
        for sel in create_selectors:
            try:
                elem = page.locator(sel).first
                if elem.is_visible(timeout=3000):
                    elem.click()
                    create_clicked = True
                    log(f"CREATE encontrado con selector: {sel}", "✓")
                    break
            except:
                continue

        if not create_clicked:
            # Intentar por texto
            try:
                page.get_by_role("button", name="Create").click(timeout=5000)
                create_clicked = True
                log("CREATE encontrado por role button", "✓")
            except:
                pass

        if not create_clicked:
            return False, None, "No se encontro el botón CREATE. ¿Estás en YouTube Studio?"

        page.wait_for_timeout(1500)

        # -- Clic en "Upload videos" --
        log("Buscando opción 'Upload videos'...", "[BUSCAR]")
        upload_clicked = False

        upload_selectors = [
            "tp-yt-paper-item:has-text('Upload videos')",
            "tp-yt-paper-item:has-text('Subir vídeos')",
            "tp-yt-paper-item:has-text('Subir videos')",
            "#text-item-0",
            "ytcp-text-menu tp-yt-paper-item:first-child",
        ]
        for sel in upload_selectors:
            try:
                elem = page.locator(sel).first
                if elem.is_visible(timeout=3000):
                    elem.click()
                    upload_clicked = True
                    log(f"Upload encontrado con: {sel}", "✓")
                    break
            except:
                continue

        if not upload_clicked:
            # Intentar por texto genérico
            try:
                page.get_by_text("Upload videos").click(timeout=5000)
                upload_clicked = True
            except:
                try:
                    page.get_by_text("Subir").first.click(timeout=5000)
                    upload_clicked = True
                except:
                    pass

        if not upload_clicked:
            return False, None, "No se pudo seleccionar 'Upload videos'"

        page.wait_for_timeout(2000)

        # -- Seleccionar archivo de video --
        log(f"Subiendo archivo: {os.path.basename(video_path)}", "📁")

        # Buscar el input file (puede estar oculto)
        file_input = page.locator("input[type='file']").first
        file_input.set_input_files(video_path)

        # -- Esperar que cargue el editor de detalles --
        log("Esperando editor de detalles (puede tardar)...", "⏳")

        # Esperar a que aparezca el campo de título
        title_appeared = False
        title_selectors = [
            "#title-textarea",
            "ytcp-social-suggestions-textbox#title-textarea",
            "#textbox[aria-label*='title']",
            "#textbox[aria-label*='título']",
        ]

        for sel in title_selectors:
            try:
                page.wait_for_selector(sel, timeout=60000)
                title_appeared = True
                break
            except:
                continue

        if not title_appeared:
            # Verificar si hay algún error de upload
            try:
                error_elem = page.locator(".error-short").first
                if error_elem.is_visible(timeout=3000):
                    error_text = error_elem.inner_text()
                    return False, None, f"Error de YouTube: {error_text}"
            except:
                pass
            return False, None, "El editor de detalles no apareció después de 60s"

        page.wait_for_timeout(2000)

        # -- Llenar título --
        log(f"Título: {title[:60]}...", "✏")

        title_box_selectors = [
            "#title-textarea #textbox",
            "#title-textarea div[contenteditable='true']",
            "ytcp-social-suggestions-textbox#title-textarea #textbox",
        ]

        title_filled = False
        for sel in title_box_selectors:
            try:
                title_field = page.locator(sel).first
                if title_field.is_visible(timeout=3000):
                    title_field.click()
                    page.wait_for_timeout(300)
                    title_field.press("Control+a")
                    page.wait_for_timeout(200)
                    title_field.fill(title)
                    title_filled = True
                    log("Título llenado", "✓")
                    break
            except:
                continue

        if not title_filled:
            log("No se pudo llenar el título, continuando...", "⚠")

        page.wait_for_timeout(500)

        # -- Llenar descripción --
        if description:
            log("Agregando descripción...", "✏")
            desc_selectors = [
                "#description-textarea #textbox",
                "#description-textarea div[contenteditable='true']",
            ]

            for sel in desc_selectors:
                try:
                    desc_field = page.locator(sel).first
                    if desc_field.is_visible(timeout=3000):
                        desc_field.click()
                        page.wait_for_timeout(300)
                        desc_field.press("Control+a")
                        page.wait_for_timeout(200)
                        # Escribir en chunks para textos largos
                        desc_field.fill(description)
                        log("Descripción llenada", "✓")
                        break
                except:
                    continue

        page.wait_for_timeout(500)

        # -- Subir thumbnail personalizado --
        if thumbnail_path and os.path.exists(thumbnail_path):
            log(f"Subiendo thumbnail: {os.path.basename(thumbnail_path)}", "🖼")
            try:
                # Scroll down para ver la sección de thumbnails
                page.evaluate("document.querySelector('#scrollable-content')?.scrollTo(0, 400)")
                page.wait_for_timeout(1000)

                # Método 1: Usar expect_file_chooser (mas confiable)
                thumb_uploaded = False

                # Buscar el botón de upload thumbnail y hacer click mientras esperamos el file chooser
                thumb_btn_selectors = [
                    "#still-picker ytcp-thumbnails-compact-editor-uploader",
                    "#still-picker #upload-button",
                    "ytcp-thumbnails-compact-editor-uploader #upload-button",
                    "#still-picker button",
                    "ytcp-thumbnails-compact-editor-uploader button",
                    "button:has-text('Upload thumbnail')",
                    "button:has-text('Subir miniatura')",
                    "#still-picker ytcp-button",
                ]

                for sel in thumb_btn_selectors:
                    try:
                        elem = page.locator(sel).first
                        if elem.is_visible(timeout=2000):
                            log(f"Thumbnail botón encontrado: {sel}", "[BUSCAR]")
                            # Usar file_chooser para interceptar el diálogo nativo
                            with page.expect_file_chooser(timeout=5000) as fc_info:
                                elem.click()
                            file_chooser = fc_info.value
                            file_chooser.set_files(thumbnail_path)
                            thumb_uploaded = True
                            log("Thumbnail subido ✓", "🖼")
                            break
                    except Exception as e:
                        continue

                # Método 2: Fallback - buscar el input file directamente
                if not thumb_uploaded:
                    log("Intentando método alternativo para thumbnail...", "🔄")
                    # Buscar todos los file inputs y filtrar por los de imagen
                    all_inputs = page.locator("input[type='file']").all()
                    for inp in all_inputs:
                        try:
                            accept = inp.get_attribute("accept") or ""
                            if "image" in accept:
                                inp.set_input_files(thumbnail_path)
                                thumb_uploaded = True
                                log("Thumbnail subido (método alt) ✓", "🖼")
                                break
                        except:
                            continue

                if not thumb_uploaded:
                    log("No se pudo subir thumbnail automaticamente", "⚠")

                page.wait_for_timeout(2000)  # Esperar que YouTube procese la imagen

                # Scroll de vuelta arriba
                page.evaluate("document.querySelector('#scrollable-content')?.scrollTo(0, 0)")
                page.wait_for_timeout(500)

            except Exception as e:
                log(f"Error subiendo thumbnail: {e}", "⚠")
        else:
            if thumbnail_path:
                log(f"Thumbnail no encontrado: {thumbnail_path}", "⚠")

        page.wait_for_timeout(500)

        # -- Marcar "not made for kids" --
        log("Marcando 'No es para niños'...", "👶")
        try:
            not_for_kids_selectors = [
                "#audience tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']",
                "tp-yt-paper-radio-button[name='NOT_MADE_FOR_KIDS']",
                "#radioLabel:has-text('No, it')",
                "#radioLabel:has-text('No, no')",
            ]
            for sel in not_for_kids_selectors:
                try:
                    elem = page.locator(sel).first
                    if elem.is_visible(timeout=3000):
                        elem.click()
                        log("'Not for kids' marcado", "✓")
                        break
                except:
                    continue
        except:
            log("No se pudo marcar 'not for kids', puede ya estar seleccionado", "⚠")

        page.wait_for_timeout(500)

        # -- Navegar wizard: Next × 3 --
        log("Navegando pasos del wizard...", "➡")
        for step in range(3):
            page.wait_for_timeout(1500)
            next_clicked = False

            next_selectors = [
                "#next-button",
                "ytcp-button#next-button",
                "#step-badge-3",  # ir directo a visibility
            ]
            for sel in next_selectors:
                try:
                    elem = page.locator(sel).first
                    if elem.is_visible(timeout=5000):
                        elem.click()
                        next_clicked = True
                        log(f"Paso {step + 1}/3 ✓", "➡")
                        break
                except:
                    continue

            if not next_clicked:
                log(f"No se pudo avanzar paso {step + 1}, puede que ya estemos al final", "⚠")
                break

        page.wait_for_timeout(2000)

        # -- Seleccionar visibilidad --
        log(f"Estableciendo visibilidad: {privacy}", "🔒")

        privacy_map = {
            "public": ["PUBLIC", "Pública", "Public"],
            "unlisted": ["UNLISTED", "No listado", "Unlisted", "Oculto"],
            "private": ["PRIVATE", "Privada", "Private", "Privado"],
        }

        visibility_names = privacy_map.get(privacy, ["PUBLIC"])

        for name in visibility_names:
            try:
                radio = page.locator(f"tp-yt-paper-radio-button[name='{name}']").first
                if radio.is_visible(timeout=2000):
                    radio.click()
                    log(f"Visibilidad '{name}' seleccionada", "✓")
                    break
            except:
                continue

        page.wait_for_timeout(1500)

        # -- Publicar (botón DONE/SAVE) --
        log("Publicando video...", "🚀")

        done_selectors = [
            "#done-button",
            "ytcp-button#done-button",
        ]

        done_clicked = False
        for sel in done_selectors:
            try:
                elem = page.locator(sel).first
                if elem.is_visible(timeout=10000):
                    elem.click()
                    done_clicked = True
                    log("Botón DONE clickeado", "✓")
                    break
            except:
                continue

        if not done_clicked:
            return False, None, "No se pudo clickear el botón DONE/SAVE"

        # -- Esperar confirmación --
        log("Esperando confirmación de YouTube...", "⏳")
        page.wait_for_timeout(5000)

        # Intentar obtener URL del video publicado
        video_url = None
        video_id = None

        try:
            # Buscar el link en el diálogo de confirmación
            link_selectors = [
                "a.style-scope.ytcp-video-info[href*='youtu']",
                "a[href*='youtu.be']",
                "a[href*='youtube.com/watch']",
                ".video-url-fadeable a",
            ]
            for sel in link_selectors:
                try:
                    link_elem = page.locator(sel).first
                    if link_elem.is_visible(timeout=5000):
                        href = link_elem.get_attribute("href")
                        if href and "youtu" in href:
                            video_url = href
                            if "v=" in video_url:
                                video_id = video_url.split("v=")[1].split("&")[0]
                            elif "youtu.be/" in video_url:
                                video_id = video_url.split("youtu.be/")[1].split("?")[0]
                            log(f"URL obtenida: {video_url}", "🔗")
                            break
                except:
                    continue
        except:
            pass

        # Cerrar el diálogo de confirmación si hay botón close
        try:
            close_btn = page.locator("ytcp-button#close-button, #close-button").first
            if close_btn.is_visible(timeout=3000):
                close_btn.click()
                page.wait_for_timeout(1000)
        except:
            pass

        if video_url:
            return True, video_url, None
        else:
            return True, "URL no disponible (revisa YouTube Studio)", None

    except PWTimeout as e:
        return False, None, f"Timeout: {str(e)[:200]}"
    except Exception as e:
        return False, None, f"Error: {str(e)[:200]}"


# -- Menú Interactivo -----------------------------------------------------------
def print_header():
    clear_screen()
    print()
    print("  ═══════════════════════════════════════════════════════════════")
    print("   🎬 UPLOADER PRO v4.0 — YouTube + TikTok")
    print("  ═══════════════════════════════════════════════════════════════")

def print_video_list(videos, show_all=False):
    """Muestra lista de videos con estado"""
    pending = [v for v in videos if not v['uploaded']]
    uploaded = [v for v in videos if v['uploaded']]

    print(f"\n  📁 {len(videos)} videos encontrados")
    print(f"     ⏳ {len(pending)} pendientes  |  ✅ {len(uploaded)} subidos")
    print(f"  {'─' * 60}")

    display = videos if show_all else pending

    if not display:
        print("  (No hay videos para mostrar)")
        return

    for i, v in enumerate(display, 1):
        size_str = format_size(v['size'])
        status = "✅" if v['uploaded'] else ("❌" if v['has_error'] else "⏳")
        source_tag = f"[{v['source']}]" if v['source'] != "LOCAL" else ""
        short_tag = "📱SHORT" if v.get('is_short') else ""

        print(f"  {i:3d}. {status} {v['title'][:50]} {short_tag}")
        print(f"       {size_str} {source_tag}")

        if v['uploaded'] and v['url']:
            print(f"       🔗 {v['url']}")
        elif v['has_error']:
            print(f"       ⚠ Error: {v['error_msg'][:60]}")

    print(f"  {'─' * 60}")


def interactive_menu():
    """Menú interactivo principal"""
    from playwright.sync_api import sync_playwright

    while True:
        videos = find_all_videos()
        pending = [v for v in videos if not v['uploaded']]

        print_header()
        print(f"\n  📁 {len(videos)} videos  |  ⏳ {len(pending)} pendientes  |  ✅ {len(videos) - len(pending)} subidos")
        print(f"  {'─' * 60}")
        print(f"  1. 📋  Ver todos los videos")
        print(f"  2. 📤  Subir UN video específico")
        print(f"  3. 📤  Subir TODOS los pendientes ({len(pending)})")
        print(f"  4. 📤  Subir un rango (ej: 1-5)")
        print(f"  5. 🔑  Verificar login en YouTube")
        print(f"  6. 🔄  Reintentar videos fallidos")
        print(f"  7. 📊  Estado detallado")
        print(f"  {'─' * 60}")
        print(f"  8. 🎵  Subir a TikTok")
        print(f"  9. 🔑  Verificar login TikTok")
        print(f"  {'─' * 60}")
        print(f"  0. ❌  Salir")
        print(f"  {'═' * 60}")

        choice = input("\n  👉 Elige una opción: ").strip()

        if choice == "0":
            print("\n  👋 ¡Hasta luego!")
            break

        elif choice == "1":
            # Ver todos los videos
            print_header()
            print_video_list(videos, show_all=True)
            input("\n  Presiona ENTER para volver al menu...")

        elif choice == "2":
            # Subir un video específico
            print_header()
            print_video_list(videos, show_all=False)

            if not pending:
                print("\n  ✅ No hay videos pendientes!")
                input("\n  Presiona ENTER para volver al menu...")
                continue

            try:
                num = input(f"\n  Número del video a subir (1-{len(pending)}): ").strip()
                if not num:
                    continue
                idx = int(num) - 1
                if idx < 0 or idx >= len(pending):
                    print("  ⚠ Número fuera de rango")
                    input("\n  Presiona ENTER para volver al menu...")
                    continue

                selected = pending[idx]
                print(f"\n  📤 Subiendo: {selected['title']}")
                print(f"     Archivo: {os.path.basename(selected['video'])}")
                print(f"     Tamaño: {format_size(selected['size'])}")

                confirm = input("\n  ¿Confirmar? [S/n]: ").strip().lower()
                if confirm and confirm not in ('s', 'si', 'y', 'yes', ''):
                    continue

                _upload_videos([selected])

            except ValueError:
                print("  ⚠ Entrada inválida")
            input("\n  Presiona ENTER para volver al menu...")

        elif choice == "3":
            # Subir todos los pendientes
            if not pending:
                print("\n  ✅ No hay videos pendientes!")
                input("\n  Presiona ENTER para volver al menu...")
                continue

            print(f"\n  📤 Se subirán {len(pending)} video(s):")
            for i, v in enumerate(pending, 1):
                print(f"     {i}. {v['title'][:50]}")

            confirm = input(f"\n  ¿Subir {len(pending)} video(s)? [S/n]: ").strip().lower()
            if confirm and confirm not in ('s', 'si', 'y', 'yes', ''):
                continue

            _upload_videos(pending)
            input("\n  Presiona ENTER para volver al menu...")

        elif choice == "4":
            # Subir rango
            print_header()
            print_video_list(videos, show_all=False)

            if not pending:
                print("\n  ✅ No hay videos pendientes!")
                input("\n  Presiona ENTER para volver al menu...")
                continue

            try:
                range_str = input(f"\n  Rango a subir (ej: 1-5 o 3,5,7): ").strip()
                if not range_str:
                    continue

                indices = []
                if '-' in range_str:
                    parts = range_str.split('-')
                    start, end = int(parts[0]) - 1, int(parts[1])
                    indices = list(range(start, min(end, len(pending))))
                elif ',' in range_str:
                    indices = [int(x.strip()) - 1 for x in range_str.split(',')]
                else:
                    indices = [int(range_str) - 1]

                selected = [pending[i] for i in indices if 0 <= i < len(pending)]

                if not selected:
                    print("  ⚠ No se seleccionaron videos válidos")
                    input("\n  Presiona ENTER para volver al menu...")
                    continue

                print(f"\n  📤 Se subirán {len(selected)} video(s):")
                for i, v in enumerate(selected, 1):
                    print(f"     {i}. {v['title'][:50]}")

                confirm = input(f"\n  ¿Confirmar? [S/n]: ").strip().lower()
                if confirm and confirm not in ('s', 'si', 'y', 'yes', ''):
                    continue

                _upload_videos(selected)

            except (ValueError, IndexError) as e:
                print(f"  ⚠ Entrada inválida: {e}")
            input("\n  Presiona ENTER para volver al menu...")

        elif choice == "5":
            # Verificar login
            print("\n  🔑 Abriendo Chrome para verificar login en YouTube...")
            print(f"     Perfil: {PW_PROFILE}")
            print("     (Si es la primera vez, necesitas loguearte en YouTube)")
            print()

            with sync_playwright() as p:
                ctx, page = create_browser_context(p)
                try:
                    ok, msg = check_youtube_login(page)
                    if ok:
                        log("✅ ¡Estás logueado en YouTube Studio!", "🎉")

                        # Verificar botón CREATE
                        try:
                            create_btn = page.locator("#create-icon").first
                            if create_btn.is_visible(timeout=5000):
                                log("Botón CREATE visible — ¡Todo listo para subir!", "✅")
                            else:
                                log("Estás logueado pero no se ve el botón CREATE", "⚠")
                        except:
                            pass

                        log("Tu sesión queda guardada para futuros uploads", "💾")
                    else:
                        print()
                        print("  ╔══════════════════════════════════════════════╗")
                        print("  ║  PRIMERA VEZ — Necesitas loguearte          ║")
                        print("  ║                                              ║")
                        print("  ║  1. Loguéate con tu cuenta de Google         ║")
                        print("  ║  2. Ve a YouTube Studio                      ║")
                        print("  ║  3. La sesión se guarda automaticamente      ║")
                        print("  ╚══════════════════════════════════════════════╝")
                        print()

                        log("Navegando a YouTube para login...", "🔗")
                        page.goto("https://accounts.google.com/ServiceLogin?service=youtube", 
                                  wait_until="domcontentloaded", timeout=30000)

                        log("Loguéate en la ventana de Chrome...", "⏳")
                        log("Esperando hasta 3 minutos para que completes el login...", "⏰")

                        # Esperar a que el usuario se loguee
                        logged_in = False
                        for i in range(180):  # 3 minutos
                            time.sleep(1)
                            try:
                                url = page.url
                                if "studio.youtube.com" in url or "youtube.com" in url:
                                    if "accounts.google.com" not in url and "ServiceLogin" not in url:
                                        logged_in = True
                                        break
                            except:
                                pass
                            if i % 15 == 0 and i > 0:
                                log(f"Esperando login... ({180-i}s restantes)", "⏳")

                        if logged_in:
                            log("✅ ¡Login detectado!", "🎉")
                            # Navegar a YouTube Studio para confirmar
                            page.goto("https://studio.youtube.com", 
                                      wait_until="domcontentloaded", timeout=30000)
                            time.sleep(3)
                            log(f"URL: {page.url}", "🔗")
                            log("Tu sesión queda guardada para futuros uploads", "💾")
                        else:
                            log("Timeout esperando login. Inténtalo de nuevo.", "⚠")
                finally:
                    ctx.close()
                    log("Chrome cerrado", "🔒")

            input("\n  Presiona ENTER para volver al menu...")

        elif choice == "6":
            # Reintentar fallidos
            failed = [v for v in videos if v['has_error'] and not v['uploaded']]
            if not failed:
                print("\n  ✅ No hay videos fallidos!")
                input("\n  Presiona ENTER para volver al menu...")
                continue

            print(f"\n  🔄 {len(failed)} video(s) fallido(s):")
            for i, v in enumerate(failed, 1):
                print(f"     {i}. {v['title'][:50]}")
                print(f"        Error: {v['error_msg'][:60]}")

            confirm = input(f"\n  ¿Reintentar {len(failed)} video(s)? [S/n]: ").strip().lower()
            if confirm and confirm not in ('s', 'si', 'y', 'yes', ''):
                continue

            # Resetear estado de error
            for v in failed:
                update_upload_status(v['info_path'], error=None)
                # Force reset
                try:
                    with open(v['info_path'], 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    data['upload'] = {
                        'uploaded': False,
                        'uploaded_at': None,
                        'video_id': None,
                        'video_url': None
                    }
                    with open(v['info_path'], 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                except:
                    pass

            _upload_videos(failed)
            input("\n  Presiona ENTER para volver al menu...")

        elif choice == "7":
            # Estado detallado
            print_header()
            print("\n  📊 ESTADO DETALLADO")
            print(f"  {'═' * 60}")

            print_video_list(videos, show_all=True)

            # Stats
            total_size = sum(v['size'] for v in videos)
            pending_size = sum(v['size'] for v in pending)
            print(f"\n  📊 Espacio total: {format_size(total_size)}")
            print(f"     Pendientes: {format_size(pending_size)}")

            # Directorio principal
            print(f"\n  📂 Videos LOCAL VERSION: {len([v for v in videos if v['source'] == 'LOCAL'])}")
            print(f"  📂 Videos ROOT output:   {len([v for v in videos if v['source'] != 'LOCAL'])}")

            input("\n  Presiona ENTER para volver al menu...")

        elif choice == "8":
            # Subir a TikTok
            tk_pending, tk_uploaded, _ = find_tiktok_pending()

            print_header()
            print(f"\n  🎵 TIKTOK — {len(tk_pending)} pendientes  |  ✅ {len(tk_uploaded)} subidos")
            print(f"  {'─' * 60}")

            if not tk_pending:
                print("  ✅ Todos los videos ya estan subidos a TikTok!")
                input("\n  Presiona ENTER para volver al menu...")
                continue

            for i, v in enumerate(tk_pending, 1):
                short_tag = "📱SHORT" if v.get('is_short') else ""
                print(f"  {i:3d}. ⏳ {v['title'][:50]} {short_tag}")
                print(f"       {format_size(v['size'])}")
            print(f"  {'─' * 60}")

            print(f"\n  a. Subir TODOS los pendientes ({len(tk_pending)})")
            print(f"  #. Subir uno específico (número)")
            print(f"  #,#,#. Múltiples (ej: 12,13,14)")
            print(f"  #-#. Rango (ej: 12-15)")

            tk_choice = input("\n  👉 Opción: ").strip().lower()

            selected = []
            if tk_choice == 'a':
                selected = tk_pending
            elif ',' in tk_choice:
                # Múltiples números separados por coma: 12,13,14,15
                try:
                    indices = [int(x.strip()) - 1 for x in tk_choice.split(',')]
                    selected = [tk_pending[i] for i in indices if 0 <= i < len(tk_pending)]
                except:
                    pass
            elif '-' in tk_choice:
                # Rango: 12-15
                try:
                    parts = tk_choice.split('-')
                    start, end = int(parts[0]) - 1, int(parts[1])
                    indices = list(range(start, min(end, len(tk_pending))))
                    selected = [tk_pending[i] for i in indices if 0 <= i < len(tk_pending)]
                except:
                    pass
            else:
                # Un solo número
                try:
                    idx = int(tk_choice) - 1
                    if 0 <= idx < len(tk_pending):
                        selected = [tk_pending[idx]]
                except:
                    pass

            if selected:
                print(f"\n  📤 Se subirán {len(selected)} video(s) a TikTok:")
                for i, v in enumerate(selected, 1):
                    print(f"     {i}. {v['title'][:50]}")
                confirm = input(f"\n  ¿Confirmar? [S/n]: ").strip().lower()
                if not confirm or confirm in ('s', 'si', 'y', 'yes'):
                    _upload_tiktok_videos(selected)
            else:
                print("  ⚠ No se seleccionaron videos")

            input("\n  Presiona ENTER para volver al menu...")

        elif choice == "9":
            # Verificar login TikTok
            print("\n  🔑 Abriendo Chrome para verificar login en TikTok...")
            print(f"     Perfil: {PW_TIKTOK_PROFILE}")
            print("     (Si es la primera vez, necesitas loguearte en TikTok)")
            print()

            with sync_playwright() as p:
                ctx, page = _create_tiktok_browser(p)
                try:
                    ok, msg = check_tiktok_login(page)
                    if ok:
                        log("✅ ¡Estás logueado en TikTok!", "🎉")
                        log("Tu sesión queda guardada para futuros uploads", "💾")
                    else:
                        print()
                        print("  ╔══════════════════════════════════════════════╗")
                        print("  ║  PRIMERA VEZ — Necesitas loguearte          ║")
                        print("  ║                                              ║")
                        print("  ║  1. Loguéate con tu cuenta de TikTok         ║")
                        print("  ║  2. La sesión se guarda automaticamente      ║")
                        print("  ╚══════════════════════════════════════════════╝")
                        print()

                        log("Navegando a TikTok para login...", "🔗")
                        page.goto("https://www.tiktok.com/login",
                                  wait_until="domcontentloaded", timeout=30000)

                        log("Loguéate en la ventana de Chrome...", "⏳")
                        log("Esperando hasta 3 minutos...", "⏰")

                        logged_in = False
                        for i in range(180):
                            time.sleep(1)
                            try:
                                url = page.url
                                if "tiktok.com" in url and "/login" not in url:
                                    if "accounts" not in url:
                                        logged_in = True
                                        break
                            except:
                                pass
                            if i % 15 == 0 and i > 0:
                                log(f"Esperando login... ({180-i}s restantes)", "⏳")

                        if logged_in:
                            log("✅ ¡Login detectado!", "🎉")
                            log("Tu sesión queda guardada para futuros uploads", "💾")
                        else:
                            log("Timeout esperando login. Inténtalo de nuevo.", "⚠")
                finally:
                    ctx.close()
                    log("Chrome cerrado", "🔒")

            input("\n  Presiona ENTER para volver al menu...")

        else:
            print("  ⚠ Opción no válida")
            time.sleep(1)


def _upload_videos(video_list):
    """Sube una lista de videos usando una única sesión de Playwright"""
    from playwright.sync_api import sync_playwright

    print(f"\n  {'═' * 60}")
    log(f"Iniciando upload de {len(video_list)} video(s)...", "🚀")
    print(f"  {'═' * 60}")

    success_count = 0
    fail_count = 0

    with sync_playwright() as p:
        ctx, page = create_browser_context(p)

        try:
            # Verificar login primero
            ok, msg = check_youtube_login(page)
            if not ok:
                log(f"❌ Login fallido: {msg}", "🚫")
                log("Ejecuta opción 5 (Verificar login) primero", "💡")
                ctx.close()
                return

            log("Login verificado ✓", "✅")

            for i, video in enumerate(video_list, 1):
                print(f"\n  {'─' * 60}")
                log(f"Video {i}/{len(video_list)}: {video['title'][:50]}", "📤")
                log(f"Archivo: {os.path.basename(video['video'])}", "📁")
                log(f"Tamaño: {format_size(video['size'])}", "💾")

                success, url, error = upload_single_video(page, video['video'], video['data'])

                if success:
                    success_count += 1
                    log(f"✅ ¡Subido exitosamente!", "🎉")
                    if url:
                        log(f"URL: {url}", "🔗")
                    update_upload_status(video['info_path'], video_url=url)
                else:
                    fail_count += 1
                    log(f"❌ Error: {error}", "🚫")
                    update_upload_status(video['info_path'], error=error)

                # Esperar entre uploads
                if i < len(video_list):
                    log("Esperando 5s antes del siguiente...", "⏳")
                    time.sleep(5)
                    # Volver a YouTube Studio para el siguiente
                    page.goto("https://studio.youtube.com", wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(3000)

        except Exception as e:
            log(f"Error general: {e}", "❌")
        finally:
            ctx.close()
            log("Chrome cerrado", "🔒")

    # Resumen
    print(f"\n  {'═' * 60}")
    print(f"  📊 RESUMEN")
    print(f"  {'═' * 60}")
    log(f"Total: {len(video_list)} | ✅ Exitosos: {success_count} | ❌ Fallidos: {fail_count}")

    if success_count == len(video_list):
        print("\n  🎉 ¡Todos los videos subidos correctamente!")
    elif success_count > 0:
        print("\n  ⚠ Algunos videos fallaron. Usa opción 6 para reintentar.")
    else:
        print("\n  ❌ Ningún video fue subido. Verifica tu login (opción 5).")
    print(f"  {'═' * 60}")


# -- TikTok Functions -----------------------------------------------------------
def _create_tiktok_browser(playwright, headless=False):
    """Crea un contexto de Playwright con perfil dedicado para TikTok"""
    log("Abriendo Chrome con perfil TikTok...", "🎵")
    log(f"Perfil: {PW_TIKTOK_PROFILE}", "📂")

    ctx = playwright.chromium.launch_persistent_context(
        user_data_dir=PW_TIKTOK_PROFILE,
        channel="chrome",
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1400,900",
        ],
        viewport={"width": 1400, "height": 900},
        timeout=60000,
    )

    if ctx.pages:
        page = ctx.pages[0]
    else:
        page = ctx.new_page()

    return ctx, page


def check_tiktok_login(page):
    """Verifica que estemos logueados en TikTok"""
    log("Navegando a TikTok Studio...", "🎵")
    page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)

    current_url = page.url
    log(f"URL: {current_url}", "🔗")

    if "/login" in current_url:
        return False, "No estas logueado en TikTok."
    elif "tiktokstudio" in current_url or "creator" in current_url:
        return True, "TikTok Studio OK"
    elif "tiktok.com" in current_url and "/login" not in current_url:
        return True, "TikTok OK"
    else:
        return False, f"URL inesperada: {current_url}"


def upload_single_tiktok(page, video_path, info_data):
    """Sube un video a TikTok Studio. Retorna (success, tiktok_url, error_message)"""
    from playwright.sync_api import TimeoutError as PWTimeout

    try:
        # Navegar a la página de upload
        log("Navegando a TikTok Studio upload...", "🎵")
        page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # Verificar que estamos logueados
        if "/login" in page.url:
            return False, None, "No estas logueado en TikTok. Usa opción 9 primero."

        # Buscar el input de archivo
        log("Buscando input de archivo...", "📁")
        file_input = None
        file_input_selectors = [
            "input[type='file'][accept*='video']",
            "input[type='file']",
        ]
        for sel in file_input_selectors:
            try:
                fi = page.locator(sel).first
                if fi.count() > 0:
                    file_input = fi
                    break
            except:
                continue

        if not file_input:
            return False, None, "No se encontro input de archivo en TikTok Studio"

        # Subir el archivo
        log(f"Subiendo: {os.path.basename(video_path)}", "📤")
        file_input.set_input_files(video_path)
        log("Archivo enviado, esperando procesamiento...", "⏳")
        page.wait_for_timeout(5000)

        # Esperar a que se procese el video (puede tardar)
        log("Esperando que TikTok procese el video...", "⏳")
        for wait_round in range(60):  # Hasta 5 minutos
            page.wait_for_timeout(5000)
            # Buscar indicadores de que el video se procesó
            try:
                # Buscar el editor de caption/descripción
                caption_selectors = [
                    "[data-text='true']",
                    ".notranslate[contenteditable='true']",
                    "div[contenteditable='true']",
                    ".caption-editor",
                    "[class*='editor'] [contenteditable]",
                ]
                for sel in caption_selectors:
                    try:
                        editor = page.locator(sel).first
                        if editor.is_visible(timeout=1000):
                            log("Editor de descripción encontrado", "✓")
                            break
                    except:
                        continue
                else:
                    if wait_round % 6 == 0 and wait_round > 0:
                        log(f"Aún procesando... ({wait_round * 5}s)", "⏳")
                    continue
                break  # Editor found
            except:
                continue

        # Llenar descripción con título + hashtags
        video_info = info_data.get('video', {})
        title = video_info.get('title', '')
        tags = video_info.get('tags', [])
        hashtags = ' '.join([f'#{t.replace(" ", "")}' for t in tags[:5]])
        caption = f"{title}\n\n{hashtags}".strip()
        if len(caption) > 2200:
            caption = caption[:2200]

        log(f"Escribiendo caption: {caption[:60]}...", "✍")

        try:
            caption_written = False
            for sel in ["[data-text='true']", ".notranslate[contenteditable='true']",
                        "div[contenteditable='true']", ".caption-editor"]:
                try:
                    editor = page.locator(sel).first
                    if editor.is_visible(timeout=2000):
                        editor.click()
                        page.wait_for_timeout(500)
                        page.keyboard.press("Control+a")
                        page.keyboard.press("Delete")
                        page.wait_for_timeout(300)
                        page.keyboard.type(caption, delay=10)
                        caption_written = True
                        log("Caption escrito", "✓")
                        break
                except:
                    continue

            if not caption_written:
                log("No se pudo escribir caption (continúa manual)", "⚠")

            # Cerrar cualquier dropdown/popup que se haya abierto
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

            # Click fuera del editor para deseleccionar
            try:
                page.mouse.click(700, 200)
                page.wait_for_timeout(500)
            except:
                pass

        except Exception as e:
            log(f"Error escribiendo caption: {e}", "⚠")

        page.wait_for_timeout(2000)

        # Scroll hacia abajo para que el botón Post sea visible
        try:
            page.mouse.wheel(0, 500)
            page.wait_for_timeout(1000)
        except:
            pass

        # === MARCAR CONTENIDO CREADO CON IA ===
        log("Buscando opciones adicionales (More)...", "[BUSCAR]")
        try:
            # Click en "More" o "More options"
            more_selectors = [
                "button:has-text('More')",
                "div:has-text('More'):not(:has(div))",
                "[data-e2e='more-options']",
                "div[class*='more']",
            ]
            for sel in more_selectors:
                try:
                    more_btn = page.locator(sel).first
                    if more_btn.is_visible(timeout=3000):
                        more_btn.click()
                        log("Botón MORE clickeado", "✓")
                        page.wait_for_timeout(1500)
                        break
                except:
                    continue
            
            # === MARCAR CONTENIDO CREADO CON IA EN TIKTOK ===
            log("Marcando AI-generated content...", "🤖")
            page.wait_for_timeout(2000)
            
            # Scroll para ver todas las opciones
            page.mouse.wheel(0, 300)
            page.wait_for_timeout(1000)
            
            ai_checked = False
            
            # Método 1: JavaScript — buscar el switch cerca del texto "AI-generated"
            try:
                result = page.evaluate("""() => {
                    // Buscar todos los elementos que contengan "AI-generated" o "AI generated"
                    const allElements = document.querySelectorAll('*');
                    for (const el of allElements) {
                        if (el.children.length === 0 && el.textContent && 
                            (el.textContent.includes('AI-generated') || el.textContent.includes('AI generated'))) {
                            // Subir en el DOM buscando el switch más cercano
                            let parent = el.parentElement;
                            for (let i = 0; i < 10 && parent; i++) {
                                const sw = parent.querySelector('.Switch__content[aria-checked="false"]');
                                if (sw) {
                                    sw.click();
                                    return 'clicked_near_text';
                                }
                                const input = parent.querySelector('input[role="switch"]');
                                if (input) {
                                    input.click();
                                    return 'clicked_input_near_text';
                                }
                                parent = parent.parentElement;
                            }
                        }
                    }
                    return 'not_found';
                }""")
                if 'clicked' in result:
                    ai_checked = True
                    log(f"✅ AI-generated marcado ({result})", "🤖")
                else:
                    log("Método 1: no encontró switch cerca de texto AI", "⚠")
            except Exception as e:
                log(f"Método 1 falló: {e}", "⚠")
            
            # Método 2: Playwright — click en Switch__content que tenga aria-checked=false
            if not ai_checked:
                try:
                    switches = page.locator('.Switch__content[aria-checked="false"][data-state="unchecked"]').all()
                    log(f"  Switches sin marcar encontrados: {len(switches)}", "🔍")
                    if len(switches) > 0:
                        # El de AI suele ser el último switch
                        switches[-1].click(force=True)
                        page.wait_for_timeout(800)
                        ai_checked = True
                        log("✅ AI-generated marcado (último switch)", "🤖")
                except Exception as e:
                    log(f"Método 2 falló: {e}", "⚠")
            
            # Método 3: JavaScript force click en el input[role=switch] directamente
            if not ai_checked:
                try:
                    result = page.evaluate("""() => {
                        const inputs = document.querySelectorAll('input[role="switch"][class*="Switch__input"]');
                        for (const input of inputs) {
                            const container = input.closest('.Switch__content');
                            if (container && container.getAttribute('aria-checked') === 'false') {
                                // Force click via dispatchEvent
                                container.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                                return 'dispatched';
                            }
                        }
                        return 'none';
                    }""")
                    if result == 'dispatched':
                        ai_checked = True
                        log("✅ AI-generated marcado (dispatchEvent)", "🤖")
                except Exception as e:
                    log(f"Método 3 falló: {e}", "⚠")
            
            if not ai_checked:
                log("No se pudo marcar AI-generated. Hazlo manual.", "⚠")
            
            page.wait_for_timeout(500)
            # ==========================================
        except Exception as e:
            log(f"Error opciones IA: {e}", "⚠")
        
        # ==========================================

        # Buscar y hacer click en el botón de Publicar/Post
        log("Buscando botón de publicar...", "📱")
        post_selectors = [
            "div.Button__content--type-primary:has-text('Post')",
            "div[class*='Button__content--type-primary']:has-text('Post')",
            "button:has(div[class*='Button__content--type-primary'])",
        ]

        posted = False
        for sel in post_selectors:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=2000) and btn.is_enabled(timeout=1000):
                    # Scroll el botón al centro antes de clickear
                    btn.scroll_into_view_if_needed()
                    page.wait_for_timeout(500)
                    btn.click()
                    posted = True
                    log("Botón POST clickeado", "✓")
                    break
            except:
                continue

        if not posted:
            log("No se encontro botón POST automaticamente", "⚠")
            log("Por favor, haz click en 'Post' manualmente en la ventana", "👉")
            log("Esperando 30 segundos...", "⏳")
            page.wait_for_timeout(30000)

        # Esperar popup de confirmación "Post now"
        page.wait_for_timeout(2000)
        try:
            post_now_selectors = [
                "div.Button__content--type-primary:has-text('Post now')",
                "div[class*='Button__content--type-primary']:has-text('Post now')",
                "button:has-text('Post now')",
                "div.Button__content--type-primary:has-text('Post')",
            ]
            for psel in post_now_selectors:
                try:
                    pn_btn = page.locator(psel).first
                    if pn_btn.is_visible(timeout=3000):
                        pn_btn.click()
                        log("Botón 'Post now' confirmación clickeado", "✓")
                        break
                except:
                    continue
        except:
            pass

        # Manejar diálogo "Are you sure you want to exit?" si aparece
        page.wait_for_timeout(3000)
        try:
            # El diálogo tiene "Exit" (rojo) y "Cancel" — clickear Cancel para quedarse
            cancel_selectors = [
                "button:has-text('Cancel')",
                "div:has-text('Cancel')",
                ":text('Cancel')",
            ]
            cancel_found = False
            for csel in cancel_selectors:
                try:
                    cancel_btn = page.locator(csel).first
                    if cancel_btn.is_visible(timeout=1500):
                        cancel_btn.click()
                        log("Diálogo 'Exit' detectado — clickeando Cancel", "✓")
                        cancel_found = True
                        break
                except:
                    continue
                page.wait_for_timeout(2000)
                
                # Ahora buscar el botón Post de nuevo y scrollear
                page.mouse.wheel(0, 800)
                page.wait_for_timeout(1000)
                #for sel in post_selectors:
                #    try:
                #        btn = page.locator(sel).first
                #        if btn.is_visible(timeout=2000) and btn.is_enabled(timeout=1000):
                #            btn.scroll_into_view_if_needed()
                #            page.wait_for_timeout(500)
                #            btn.click()
                #            log("Botón POST clickeado (segundo intento)", "✓")
                #            break
                #    except:
                #        continue
        except:
            pass

        # Esperar confirmación
        log("Esperando confirmación de TikTok...", "⏳")
        page.wait_for_timeout(10000)

        # Verificar si se publicó
        try:
            success_indicators = [
                "text=Your video has been uploaded",
                "text=Your video is being uploaded",
                "text=Video published",
                "text=successfully",
                "text=Uploaded",
                "text=Tu video se ha subido",
                "text=publicado",
            ]
            for indicator in success_indicators:
                try:
                    if page.locator(indicator).first.is_visible(timeout=2000):
                        log("Confirmación de éxito detectada", "✅")
                        return True, "Subido a TikTok", None
                except:
                    continue
        except:
            pass

        # Si no hay confirmación clara, asumir éxito si no hay error
        log("No se confirmó automaticamente — verificar en TikTok Studio", "[BUSCAR]")
        return True, "Subido a TikTok (verificar manualmente)", None

    except PWTimeout as e:
        return False, None, f"Timeout: {str(e)[:200]}"
    except Exception as e:
        return False, None, f"Error: {str(e)[:200]}"


def _upload_tiktok_videos(video_list):
    """Sube una lista de videos a TikTok usando una única sesión de Playwright"""
    from playwright.sync_api import sync_playwright

    print(f"\n  {'═' * 60}")
    log(f"Iniciando upload a TikTok de {len(video_list)} video(s)...", "🎵")
    print(f"  {'═' * 60}")

    success_count = 0
    fail_count = 0

    with sync_playwright() as p:
        ctx, page = _create_tiktok_browser(p)

        try:
            # Verificar login primero
            ok, msg = check_tiktok_login(page)
            if not ok:
                log(f"❌ Login TikTok fallido: {msg}", "🚫")
                log("Ejecuta opción 9 (Verificar login TikTok) primero", "💡")
                ctx.close()
                return

            log("Login TikTok verificado ✓", "✅")

            for i, video in enumerate(video_list, 1):
                print(f"\n  {'─' * 60}")
                log(f"Video {i}/{len(video_list)}: {video['title'][:50]}", "📤")
                log(f"Archivo: {os.path.basename(video['video'])}", "📁")
                log(f"Tamaño: {format_size(video['size'])}", "💾")

                success, url, error = upload_single_tiktok(page, video['video'], video['data'])
                filename = os.path.basename(video['video'])

                if success:
                    success_count += 1
                    log(f"✅ ¡Subido a TikTok!", "🎉")
                    save_tiktok_upload(filename, tiktok_url=url)
                else:
                    fail_count += 1
                    log(f"❌ Error: {error}", "🚫")
                    save_tiktok_upload(filename, error=error)

                # Esperar entre uploads
                if i < len(video_list):
                    log("Esperando 5s antes del siguiente...", "⏳")
                    time.sleep(5)

        except Exception as e:
            log(f"Error general: {e}", "❌")
        finally:
            ctx.close()
            log("Chrome cerrado", "🔒")

    # Resumen
    print(f"\n  {'═' * 60}")
    print(f"  🎵 RESUMEN TIKTOK")
    print(f"  {'═' * 60}")
    log(f"Total: {len(video_list)} | ✅ Exitosos: {success_count} | ❌ Fallidos: {fail_count}")

    if success_count == len(video_list):
        print("\n  🎉 ¡Todos los videos subidos a TikTok!")
    elif success_count > 0:
        print("\n  ⚠ Algunos videos fallaron.")
    else:
        print("\n  ❌ Ningún video fue subido. Verifica tu login (opción 9).")
    print(f"  {'═' * 60}")


# -- Main -----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="YouTube Uploader Pro v3.0 — Creepypasta Factory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  %(prog)s                     # Menú interactivo
  %(prog)s --auto              # Subir todos los pendientes
  %(prog)s --file video.mp4    # Subir un video específico
  %(prog)s --list              # Listar videos disponibles
        """
    )
    parser.add_argument("--file", type=str, default=None,
                        help="Subir solo este video (ruta al archivo .mp4)")
    parser.add_argument("--auto", action="store_true",
                        help="Modo automático: subir todos los videos pendientes")
    parser.add_argument("--list", action="store_true",
                        help="Listar videos disponibles sin subir")
    parser.add_argument("--privacy", type=str, default="public",
                        choices=["public", "private", "unlisted"],
                        help="Privacidad del video (default: public)")
    parser.add_argument("--headless", action="store_true",
                        help="Ejecutar sin mostrar ventana de Chrome")

    args = parser.parse_args()

    # Si no se pasan argumentos, mostrar menu interactivo
    if len(sys.argv) == 1:
        try:
            interactive_menu()
        except KeyboardInterrupt:
            print("\n\n  👋 ¡Cancelado!")
        return

    # -- Modo lista --
    if args.list:
        videos = find_all_videos()
        print_header()
        print_video_list(videos, show_all=True)
        return

    # -- Modo archivo único --
    if args.file:
        video_path = os.path.abspath(args.file)
        if not os.path.exists(video_path):
            log(f"Video no encontrado: {video_path}", "❌")
            sys.exit(1)

        # Buscar metadata
        base = video_path.replace('.mp4', '')
        info_file = base + '_video_info.json'

        if os.path.exists(info_file):
            with open(info_file, 'r', encoding='utf-8') as f:
                info_data = json.load(f)
        else:
            info_data = {
                'video': {
                    'title': os.path.basename(video_path).replace('.mp4', '').replace('_', ' '),
                    'youtube_title': os.path.basename(video_path).replace('.mp4', '').replace('_', ' '),
                    'description': 'Relato de terror narrado con voz natural.',
                    'tags': ["creepypasta", "terror", "relatos de terror"],
                    'privacy': args.privacy
                },
                'upload': {'uploaded': False}
            }

        _upload_videos([{
            'video': video_path,
            'info_path': info_file if os.path.exists(info_file) else None,
            'data': info_data,
            'title': info_data['video'].get('title', 'Sin título'),
            'size': os.path.getsize(video_path),
            'uploaded': False,
            'has_error': False,
        }])
        return

    # -- Modo auto --
    if args.auto:
        videos = find_all_videos()
        pending = [v for v in videos if not v['uploaded']]

        if not pending:
            log("No hay videos pendientes de subir", "✅")
            return

        log(f"Encontrados {len(pending)} video(s) pendiente(s)", "📋")
        for i, v in enumerate(pending, 1):
            print(f"  {i}. {v['title'][:50]}")

        _upload_videos(pending)
        return

    # Si llega aquí, mostrar menu
    interactive_menu()


if __name__ == "__main__":
    main()
