#!/usr/bin/env python3
"""
🎬 V-CONTENT CREATOR
AI-powered viral video content factory.
Text: Gemini / Moonshot (Kimi) -> Stories + image prompts
Audio: Gemini 2.5 Flash TTS / ElevenLabs -> natural voice
Subs: faster-whisper -> transcription
Images: diffusers + SDXL (local GPU) | Gemini Web (browser)
Video: ffmpeg -> local rendering

GitHub: https://github.com/YOUR_USERNAME/v-content-creator
"""

import os
import sys
import random
import json
import wave
import base64
import subprocess
import urllib.request
import shutil
import re
from datetime import datetime
import glob
import litellm

# Fix Windows console encoding for emoji
import io
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
elif sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── Load environment variables from .env ───────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass  # dotenv not installed, will use system env vars

# ── Configuration ──────────────────────────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# API Keys (loaded from .env file — see .env.example)
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVEN_VOICE_ID = os.getenv("ELEVEN_VOICE_ID", "qEWvRpD5bptlI1hEomR7")  # "Adam" voice

MOONSHOT_API_KEY = os.getenv("MOONSHOT_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ── Autodetect API Keys from .env ──
available_keys = {
    "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
    "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
    "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY"),
    "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
    "GROQ_API_KEY": os.getenv("GROQ_API_KEY"),
    "MOONSHOT_API_KEY": os.getenv("MOONSHOT_API_KEY")
}

# Delete empty ones
available_keys = {k: v for k, v in available_keys.items() if v}

# Validate required keys / Interactive Onboarding
# Skip if user is running in Gemini Web mode (no API keys needed)
_using_gemini_web = "--gemini-web-story" in sys.argv

if not available_keys and not _using_gemini_web:
    print("\n" + "="*60)
    print("👋 ¡BIENVENIDO A V-CONTENT CREATOR!")
    print("="*60)
    print("Parece que es tu primera vez y no tienes ninguna API Key configurada.")
    print("Tienes 2 opciones:\n")
    print(" 🌐 OPCIÓN GRATUITA: Usa --gemini-web-story para generar historias")
    print("    sin API Key via tu cuenta de Gemini con Playwright.\n")
    print(" 🔑 OPCIÓN API: Configura un modelo de LiteLLM (+100 disponibles):")
    print("   • gemini/gemini-2.5-flash")
    print("   • openai/gpt-4o")
    print("   • deepseek/deepseek-chat")
    print("   • anthropic/claude-3-5-sonnet-20240620\n")
    
    user_model = input("👉 ¿Qué modelo quieres usar? (o escribe 'web' para Gemini Web): ").strip()
    
    if user_model.lower() == 'web':
        _using_gemini_web = True
        DEFAULT_TEXT_MODEL = "gemini_web"
    elif not user_model:
        print("❌ Operación cancelada. El script requiere un modelo de texto.")
        sys.exit(1)
    else:
        provider = user_model.split('/')[0].upper() if '/' in user_model else user_model.upper()
        api_key_name = f"{provider}_API_KEY"
        
        user_key = input(f"🔑 Pega tu {api_key_name} (se guardará de forma segura en .env): ").strip()
        if not user_key:
            print("❌ Operación cancelada. Se necesita una API Key para funcionar.")
            sys.exit(1)
            
        # Guardar en .env
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        try:
            with open(env_path, "a") as f:
                f.write(f"\n{api_key_name}={user_key}\n")
            print(f"\n✅ ¡Éxito! Tu {api_key_name} ha sido guardada.")
            
            # Load immediately
            os.environ[api_key_name] = user_key
            available_keys[api_key_name] = user_key
        except Exception as e:
            print(f"⚠️ No se pudo guardar en .env: {e}")
            
        # Forzar el modelo por defecto en base a lo que eligió el usuario
        DEFAULT_TEXT_MODEL = user_model

if _using_gemini_web and not available_keys:
    DEFAULT_TEXT_MODEL = "gemini_web"
elif available_keys:
    # Auto-pick the first available model based on keys
    first_key = list(available_keys.keys())[0]
    if first_key == "OPENAI_API_KEY":
        DEFAULT_TEXT_MODEL = "openai/gpt-4o"
    elif first_key == "DEEPSEEK_API_KEY":
        DEFAULT_TEXT_MODEL = "deepseek/deepseek-chat"
    elif first_key == "ANTHROPIC_API_KEY":
        DEFAULT_TEXT_MODEL = "anthropic/claude-3-5-sonnet-20240620"
    elif first_key == "MOONSHOT_API_KEY":
        DEFAULT_TEXT_MODEL = "kimi"
    elif first_key == "GROQ_API_KEY":
        DEFAULT_TEXT_MODEL = "groq/llama3-70b-8192"
    else:  # GEMINI is fallback
        DEFAULT_TEXT_MODEL = "gemini/gemini-pro"

# Channel Configuration (customize in .env)
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "My Channel")
VIDEO_PREFIX = os.getenv("VIDEO_PREFIX", "video")
DEFAULT_TAGS = os.getenv("DEFAULT_TAGS", "stories,narration,storytime").split(",")

# SFX Configuration
SOUNDS_DIR = os.path.join(PROJECT_DIR, "sounds")
if not os.path.exists(SOUNDS_DIR):
    os.makedirs(SOUNDS_DIR)

# Get available sounds dynamically
def get_available_sounds():
    files = []
    if os.path.exists(SOUNDS_DIR):
        for f in os.listdir(SOUNDS_DIR):
            if f.endswith(('.mp3', '.wav', '.ogg')):
                files.append(os.path.splitext(f)[0])
    return files


# Modelo de texto por defecto dinámico
TEXT_MODEL = DEFAULT_TEXT_MODEL

# Motor TTS por defecto (gemini o eleven)
TTS_ENGINE = "gemini"  # Opciones: "gemini" o "kimi"

# Motor de imágenes por defecto (sdxl o gemini_web)
IMAGE_ENGINE = "sdxl"  # Opciones: "sdxl" (GPU local) o "gemini_web" (Playwright browser)

# ═══════════════════════════════════════════════════════════════════════════════
# SISTEMA DE NICHOS DE CONTENIDO VIRAL
# ═══════════════════════════════════════════════════════════════════════════════

CONTENT_NICHES = {
    "misterio_real": {
        "nombre": "Misterio Real / True Crime",
        "tono": "Periodístico pero íntimo, como si contaras algo que no deberías saber",
        "narrativa": "Investigación personal, descubrimiento gradual de la verdad",
        "hooks": [
            "Hace 3 años encontré algo que la policía nunca quiso investigar...",
            "Mi vecino desapareció un martes. Nadie hizo preguntas. Yo sí.",
            "El caso estaba cerrado. Pero yo tenía la llave que faltaba.",
            "Nunca confíes en alguien que te dice 'no mires ahí'...",
            "Lo que encontré en el sótano de mi abuelo cambió todo lo que sabía de mi familia.",
        ],
        "titulo_formatos": ["nombre_propio", "lugar_hora", "pregunta", "frase_corta", "fecha"],
        "titulo_ejemplos": ["Caso Valentina", "¿Quién cerró la puerta?", "Marzo 14, sin respuesta", "El archivo que nadie pidió"],
        "cliches_prohibidos": ["asesino serial genérico", "detective brillante", "evidencia obvia"],
        "imagen_estilo": "photojournalistic style, documentary photography, moody available light, film grain, desaturated colors",
        "tags": ["misterio", "true crime", "caso real", "investigación", "suspense"],
    },
    "confesiones": {
        "nombre": "Confesiones Oscuras",
        "tono": "Íntimo, vulnerable, como un secreto que te cuentan al oído",
        "narrativa": "Confesión directa al espectador, culpa, arrepentimiento o liberación",
        "hooks": [
            "Nunca le conté esto a nadie. Pero ya no puedo seguir callando.",
            "Lo que hice esa noche me persigue cada vez que cierro los ojos.",
            "Mi familia cree que soy buena persona. No lo soy.",
            "Hay un secreto que destruiría mi matrimonio si sale a la luz.",
            "Hice algo imperdonable y la persona que más quiero no lo sabe.",
        ],
        "titulo_formatos": ["frase_intima", "pregunta", "nombre_propio"],
        "titulo_ejemplos": ["Lo que nunca dije", "Sofía merece saber", "Mi peor versión", "La mentira de los 12 años"],
        "cliches_prohibidos": ["confesión de asesinato obvia", "giro predecible"],
        "imagen_estilo": "intimate close-up photography, shallow depth of field, warm shadows, confessional mood, soft lighting",
        "tags": ["confesiones", "storytime", "secretos", "historia real", "desahogo"],
    },
    "suspenso_cotidiano": {
        "nombre": "Suspenso Cotidiano",
        "tono": "Comienza normal, escala lentamente hacia lo inquietante",
        "narrativa": "Situación mundana que se vuelve perturbadora. Lo aterrador está en lo familiar.",
        "hooks": [
            "Todo empezó con un mensaje de texto de un número que ya no existe.",
            "Mi Uber tomó una ruta que no aparece en Google Maps.",
            "La cámara de seguridad grabó algo a las 3:17 AM que no puedo explicar.",
            "Mi hijo de 4 años empezó a hablar de 'el señor del techo'.",
            "Llevo 3 semanas recibiendo paquetes que no ordené. Dentro hay fotos mías.",
        ],
        "titulo_formatos": ["objeto_cotidiano", "hora_lugar", "frase_inquietante"],
        "titulo_ejemplos": ["El mensaje de las 3AM", "Ruta alterna", "Paquete sin remitente", "La cámara del pasillo"],
        "cliches_prohibidos": ["fantasmas", "posesiones", "muñecas malditas", "espejos"],
        "imagen_estilo": "everyday settings with unsettling atmosphere, suburban horror, liminal spaces, security camera aesthetic, found footage look",
        "tags": ["suspenso", "miedo", "historia de terror", "creepy", "perturbador"],
    },
    "ciencia_ficcion": {
        "nombre": "Sci-Fi / Black Mirror",
        "tono": "Tecnológico, reflexivo, con un giro que te hace cuestionar la realidad",
        "narrativa": "Near-future plausible, dilema moral con tecnología, consecuencias inesperadas",
        "hooks": [
            "La app prometía mostrarte cómo morirías. Era gratis. Todos la descargaron.",
            "Mi esposa llevaba 6 meses muerta. Ayer me mandó un audio de WhatsApp.",
            "La IA de la empresa me pidió que no apagara el servidor. Me dijo 'por favor'.",
            "Desde que me implantaron el chip, puedo ver los recuerdos de otros.",
            "El gobierno ofreció borrar un recuerdo gratis. Solo uno. Yo elegí mal.",
        ],
        "titulo_formatos": ["nombre_app", "concepto_tech", "pregunta_filosofica"],
        "titulo_ejemplos": ["DeathApp v2.3", "El último ping", "Memoria borrada", "Servidor 7, Piso -3"],
        "cliches_prohibidos": ["robots malvados genéricos", "matriz/simulación obvia", "apocalipsis nuclear"],
        "imagen_estilo": "near-future dystopian, cyberpunk lighting, neon reflections, tech noir, blade runner inspired, clinical sterile environments",
        "tags": ["ciencia ficción", "black mirror", "tecnología", "futuro", "IA"],
    },
    "drama_humano": {
        "nombre": "Drama Humano / Storytime Emocional",
        "tono": "Emotivo, crudo, real — historias que golpean el corazón",
        "narrativa": "Experiencia humana intensa, relaciones, pérdida, redención, sacrificio",
        "hooks": [
            "Mi padre me llamó después de 15 años de silencio. Solo dijo una palabra.",
            "El día que mi mejor amigo me salvó la vida fue el día que arruiné la suya.",
            "Vendí todo lo que tenía para pagar una deuda que no era mía.",
            "Mi madre trabajó 30 años en una fábrica. El día que se jubiló entendí por qué.",
            "Le prometí a mi hermano que volvería. Han pasado 8 años.",
        ],
        "titulo_formatos": ["nombre_propio", "relacion_familiar", "frase_emotiva"],
        "titulo_ejemplos": ["La llamada de papá", "Deuda de sangre", "30 años en silencio", "Promesa rota en Tijuana"],
        "cliches_prohibidos": ["enfermedad terminal predecible", "reencuentro perfecto", "finales felices forzados"],
        "imagen_estilo": "cinematic scene photography, dramatic available light, golden hour or blue hour, raw emotional moments, documentary style, intimate framing, varied compositions",
        "tags": ["storytime", "drama", "historia real", "emocional", "reflexión"],
    },
    "terror_psicologico": {
        "nombre": "Terror Psicológico",
        "tono": "Insidioso, perturbador — el miedo viene de dentro, no de monstruos",
        "narrativa": "La amenaza es invisible, ambigua. ¿Es real o está en la mente del narrador?",
        "hooks": [
            "No puedo dormir porque cada noche despierto en un lugar diferente de mi casa.",
            "Mi psicólogo me dijo que dejara de inventar personas. Pero ella está aquí, sentada frente a mí.",
            "Llevo 3 días sin dormir. No por insomnio. Por lo que pasa cuando cierro los ojos.",
            "Encontré un diario en mi letra con fechas que aún no han pasado.",
            "Mi esposa dice que anoche tuvimos una pelea terrible. Yo no recuerdo nada.",
        ],
        "titulo_formatos": ["sintoma", "objeto_personal", "frase_inquietante"],
        "titulo_ejemplos": ["El diario de mañana", "Sonámbulo", "La otra conversación", "Recuerdo inventado"],
        "cliches_prohibidos": ["jumpscares", "casas embrujadas", "demonios", "muñecas", "payasos", "espejos poseídos"],
        "imagen_estilo": "psychological horror, distorted perspectives, unsettling portraits, David Lynch inspired, abstract dread, clinical photography",
        "tags": ["terror psicológico", "perturbador", "mente", "thriller", "horror"],
    },
    "folklore_latam": {
        "nombre": "Folklore Latinoamericano Reimaginado",
        "tono": "Raíces culturales mezcladas con narrativa moderna y cinematográfica",
        "narrativa": "Leyenda tradicional contada como experiencia personal contemporánea",
        "hooks": [
            "Mi abuela me prohibió salir después de las 6. Cuando entendí por qué, ya era tarde.",
            "En mi pueblo dicen que si silbas de noche, algo te contesta. Yo silbé.",
            "La curandera del barrio me miró y dijo: 'Lo que traes encima no es tuyo'.",
            "Hay una carretera en mi país donde los GPS dejan de funcionar a las 2AM.",
            "Mi tía hizo un trato que mi familia lleva 40 años pagando.",
        ],
        "titulo_formatos": ["lugar_real", "nombre_criatura", "dicho_popular"],
        "titulo_ejemplos": ["La carretera de Azua", "Silbido en Barinas", "Lo que trajo la curandera", "Pacto de los 40 años"],
        "cliches_prohibidos": ["llorona genérica", "chupacabras", "descripciones Wikipedia de criaturas"],
        "imagen_estilo": "latin american magical realism, tropical noir, lush vegetation with shadows, rural mystery, warm humid atmosphere",
        "tags": ["leyendas", "folklore", "latinoamérica", "mitos", "campo"],
    },
    "venganza": {
        "nombre": "Venganza / Justicia Poética",
        "tono": "Calculador, satisfactorio — el malo recibe lo que merece",
        "narrativa": "Alguien fue traicionado/humillado y ejecuta una venganza elaborada",
        "hooks": [
            "Mi jefe me humilló frente a toda la oficina. Tardé 6 meses en devolvérsela.",
            "Me robaron todo. Les tomó 3 minutos. A mí me tomó un año encontrarlos.",
            "La persona que arruinó mi vida acaba de pedirme un favor. Dije que sí.",
            "Mi ex publicó mis secretos. Lo que no sabe es que yo tengo los suyos.",
            "Despidieron a mi madre sin razón. Ahora soy el nuevo jefe de quien la despidió.",
        ],
        "titulo_formatos": ["accion", "tiempo", "frase_fria"],
        "titulo_ejemplos": ["6 meses de paciencia", "El favor", "Recibo pendiente", "La renuncia perfecta"],
        "cliches_prohibidos": ["violencia gratuita", "venganza imposible", "héroe perfecto"],
        "imagen_estilo": "neo-noir cinematography, dramatic chiaroscuro, corporate thriller aesthetic, cold calculated framing, power dynamics",
        "tags": ["venganza", "justicia", "karma", "storytime", "satisfactorio"],
    },
    "supervivencia": {
        "nombre": "Supervivencia / Experiencias Extremas",
        "tono": "Adrenalina pura, urgencia, vida o muerte",
        "narrativa": "Situación extrema real donde la supervivencia depende de decisiones rápidas",
        "hooks": [
            "Tenía 4 horas de oxígeno. El rescate llegaría en 6.",
            "Me perdí en la selva colombiana. Al tercer día dejé de buscar el camino.",
            "El bote se volteó a 3 km de la costa. No sé nadar.",
            "Desperté en un hospital de un país donde no hablo el idioma.",
            "La montaña nos atrapó. Éramos 5. Bajamos 3.",
        ],
        "titulo_formatos": ["lugar_extremo", "tiempo_limite", "numero"],
        "titulo_ejemplos": ["4 horas de aire", "Tercer día en el Darién", "3 kilómetros", "Bajamos 3"],
        "cliches_prohibidos": ["héroe invencible", "rescate perfecto last-minute", "sin consecuencias"],
        "imagen_estilo": "extreme environment photography, survival documentary, harsh natural lighting, wide wilderness shots, visceral close-ups",
        "tags": ["supervivencia", "extremo", "aventura", "vida real", "adrenalina"],
    },
    "misterio_digital": {
        "nombre": "Misterio Digital / Internet Creepy",
        "tono": "Moderno, tecno-paranoia, lo perturbador está en la pantalla",
        "narrativa": "Algo extraño encontrado online, en la deep web, en un archivo, en un livestream",
        "hooks": [
            "Encontré un canal de YouTube con 0 suscriptores. Los videos son de mi casa.",
            "Mi contraseña fue cambiada. El email de recuperación es mío, pero nunca lo creé.",
            "Alguien está editando mi perfil de Google Maps. Los lugares que agrega no existen.",
            "Compré un disco duro usado. Tenía 40,000 fotos. Todas son de la misma persona.",
            "Un usuario anónimo me manda mi ubicación exacta cada día a las 11:11 PM.",
        ],
        "titulo_formatos": ["plataforma_digital", "dato_tecnico", "username"],
        "titulo_ejemplos": ["Canal sin suscriptores", "40,000 fotos", "@nadie_real", "11:11 PM"],
        "cliches_prohibidos": ["dark web genérica", "hacker de película", "virus mágico"],
        "imagen_estilo": "screen capture aesthetic, digital glitch art, dark monitor glow, surveillance footage, cyber horror, lo-fi digital",
        "tags": ["misterio digital", "internet", "creepy", "tecnología", "deep web"],
    },
}

def select_niche(niche_name=None):
    """Selecciona un nicho de contenido. Si no se especifica, elige uno al azar."""
    if niche_name and niche_name in CONTENT_NICHES:
        return niche_name, CONTENT_NICHES[niche_name]
    # Selección aleatoria ponderada (algunos nichos son más virales)
    viral_boost = ["confesiones", "suspenso_cotidiano", "drama_humano", "venganza", "misterio_digital"]
    pool = list(CONTENT_NICHES.keys())
    weights = [2.0 if n in viral_boost else 1.0 for n in pool]
    chosen = random.choices(pool, weights=weights, k=1)[0]
    return chosen, CONTENT_NICHES[chosen]

IS_SHORT = False
VIDEO_QUALITY = os.getenv("VIDEO_QUALITY", "high")

QUALITY_PRESETS = {
    "high": {"crf": "18", "preset": "slow", "maxrate": "8M", "bufsize": "16M"},
    "medium": {"crf": "23", "preset": "medium", "maxrate": "4M", "bufsize": "8M"},
    "low": {"crf": "28", "preset": "fast", "maxrate": "2M", "bufsize": "4M"},
    "minimal": {"crf": "32", "preset": "veryfast", "maxrate": "1M", "bufsize": "2M"},
}

# TTS: Gemini 2.5 Flash TTS
GEMINI_TTS_MODEL = "gemini-2.5-pro-preview-tts"
GEMINI_TTS_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TTS_MODEL}:generateContent"
GEMINI_TTS_VOICE = "Charon"

# SDXL
SDXL_MODELS_DIR = os.path.join(PROJECT_DIR, "stable-diffusion-webui-master", "models", "Stable-diffusion")

_sd_pipe = None
_whisper_mdl = None
_ip_adapter_ok = False


# ═══════════════════════════════════════════════════════════════════════════════
# LITELLM TEXT API
# ═══════════════════════════════════════════════════════════════════════════════

def get_system_prompt():
    available_sfx = get_available_sounds()
    sfx_instruction = ""
    if available_sfx:
        sfx_list = ", ".join(f"'{s}'" for s in available_sfx)
        sfx_instruction = f"""
También eres el Diseñador de Sonido (Foley Artist). Tienes acceso a los siguientes efectos de sonido: {sfx_list}.
Debes decidir en qué momento exacto de la historia debe sonar cada efecto para maximizar la inmersión.

INSTRUCCIÓN VITAL: Tu respuesta DEBE tener TRES secciones marcadas exactamente con estas etiquetas obligatorias:
[STORY]
[IMAGE_PROMPTS]
[SOUND_EFFECTS]
"""
    else:
        sfx_instruction = """
INSTRUCCIÓN VITAL: Tu respuesta DEBE tener DOS secciones marcadas exactamente con estas etiquetas obligatorias:
[STORY]
[IMAGE_PROMPTS]
"""

    return f"""Eres un escritor de relatos creativo y experto en retención visual (Cinematógrafo y Guionista).
Sigues instrucciones de formato al pie de la letra sin inventar comillas extra.
{sfx_instruction}"""

def generate_text_litellm(prompt, model=TEXT_MODEL, max_tokens=4000, temperature=0.95):
    """
    Llama a cualquier modelo soportado por LiteLLM (OpenAI, Gemini, DeepSeek, Claude, etc).
    Las API keys se cargan automáticamente desde el entorno.
    """
    print(f"  🧠 Llamando a LLM ({model}) via LiteLLM...")
    try:
        response = litellm.completion(
            model=model,
            messages=[
                {"role": "system", "content": get_system_prompt()},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=120
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Error en LiteLLM ({model}): {e}")
        return None

def parse_timestamp_to_seconds(timestamp_str):
    """Convierte '0:25' o '1:30' a segundos (25, 90)"""
    try:
        parts = timestamp_str.strip().split(':')
        if len(parts) == 2:
            minutes = int(parts[0])
            seconds = int(parts[1])
            return minutes * 60 + seconds
        elif len(parts) == 1:
            return int(parts[0])
    except:
        pass
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# GENERACIÓN DE HISTORIAS (Igual que el original, pero con Moonshot)
# ═══════════════════════════════════════════════════════════════════════════════

def generate_story_batch(count=1, context=None, target_words=None, niche_name=None):
    """
    Genera historias usando Moonshot API (Kimi) con sistema de nichos virales.
    """
    # Seleccionar nicho de contenido
    niche_id, niche = select_niche(niche_name)
    print(f"  🎯 Nicho seleccionado: {niche['nombre']}")
    
    # Elegir un hook ejemplo del nicho para inspiración
    hook_examples = random.sample(niche['hooks'], min(3, len(niche['hooks'])))
    hooks_text = "\n".join([f"  - \"{h}\"" for h in hook_examples])
    
    # Títulos ejemplo del nicho
    title_examples = ", ".join([f'"{t}"' for t in niche['titulo_ejemplos']])
    
    # Clichés prohibidos del nicho
    cliches = ", ".join(niche['cliches_prohibidos'])
    
    context_block = f"\nDIRECCIÓN CREATIVA DEL USUARIO (integrar con el nicho):\n{context}\n" if context else ""
    
    if target_words:
        word_rule = f"""- EXTENSIÓN OBLIGATORIA: ~{target_words} palabras (± 30 palabras)
  ⚠️ ESTO ES CRÍTICO: si escribes menos de {int(target_words * 0.85)} palabras, la historia será RECHAZADA.
  Cuenta las palabras mentalmente. Un párrafo promedio tiene ~50 palabras. Para {target_words} palabras necesitas ~{target_words // 50} párrafos sustanciales."""
    elif IS_SHORT:
        word_rule = "- Entre 80 y 110 palabras (MUY CORTO — video de máximo 60 segundos)"
    else:
        word_rule = "- Entre 300 y 450 palabras (relato completo con desarrollo, NO escribas menos de 300)"

    prompt = f"""Eres un escritor de contenido viral para YouTube/TikTok. Tu especialidad: {niche['nombre']}.

GENERA {count} historia(s) con potencial VIRAL aplicando estas técnicas narrativas.
{context_block}
═══ IDENTIDAD DEL NICHO ═══
- TONO: {niche['tono']}
- ESTILO NARRATIVO: {niche['narrativa']}

═══ TÉCNICAS VIRALES (OBLIGATORIAS) ═══
1. HOOK (Primera frase): DEBE detener el scroll — crea curiosidad inmediata, tensión o shock
   Inspírate en estos hooks de este nicho:
{hooks_text}
2. ESCALADA: Cada párrafo debe aumentar la tensión/emoción. NUNCA mesetas aburridas.
3. DETALLES SENSORIALES: Olores, texturas, sonidos específicos — NO describas, HAZ SENTIR.
4. DIÁLOGO PUNZANTE: Incluye al menos 1-2 líneas de diálogo que impacten.
5. TWIST/CIERRE: Final que deje al espectador procesando. Puede ser: revelación, ironía, ambigüedad, golpe emocional.

═══ REGLAS DE LA HISTORIA ═══
{word_rule}
- Primera persona ("yo", "mi") — el espectador debe sentir que SE LO CUENTAS A ÉL
- PROHIBIDO estos clichés de este nicho: {cliches}
- PROHIBIDO: prosa florecida, metáforas excesivas, descripciones innecesarias
- SÍ: frases cortas para momentos de tensión, párrafos que respiran
- En español natural (ni demasiado formal ni slang excesivo)

═══ REGLAS DEL TÍTULO (CRÍTICO PARA CTR) ═══
- El título VENDE la historia — debe generar curiosidad irresistible
- Usa SOLO caracteres latinos (A-Z, acentos españoles, números)
- PROHIBIDO caracteres chinos, japoneses, coreanos, árabes u otros scripts no-latinos
- Máximo 8 palabras — corto, punchy, memorable
- Buenos ejemplos para este nicho: {title_examples}
- PROHIBIDO: "El/La [sustantivo] de/del [cosa]", "Protocolo de...", "Herencia de..."
- FORMATOS QUE FUNCIONAN: preguntas provocadoras, nombres propios, lugares+hora, números específicos, frases dichas por personajes

═══ REGLAS DE IMÁGENES (PARA SDXL — TÚ DIRIGES LA GENERACIÓN VISUAL) ═══
- Elige entre 4 y 8 imágenes según la longitud de la historia
- Cada imagen DEBE tener un TIMESTAMP en formato MM:SS
- RITMO: ~135 palabras por minuto de narración
- DISTRIBUCIÓN: hook visual (0:00), desarrollo, clímax, cierre
- Mínimo 6 segundos entre imágenes
- Prompts en INGLÉS, 40-70 palabras, ESPECÍFICOS a escenas de ESTA historia
- TÚ decides el estilo visual que mejor encaja con la historia
- VARIEDAD: NO repitas la misma composición ni perspectiva en todas las imágenes
- Cada prompt debe describir la ESCENA específica, no solo un estilo genérico

═══ FORMATO DE SALIDA (EXACTO — NO copies las instrucciones, solo rellena) ═══

===HISTORIA 1===
IMAGES: [número]

[Tu título aquí]

[Historia completa — recuerda la extensión obligatoria]

===IMAGENES 1===
IMG1 0:00: [prompt detallado de la escena del hook, estilo visual, composición]
IMG2 0:12: [prompt detallado de la escena de desarrollo, distinta composición]
IMG3 0:25: [prompt detallado de la escena del clímax]
IMG4 0:40: [prompt detallado de la escena de cierre/twist]

===SFX 1===
0:12: rain
0:25: heartbeat
0:40: door_knocking

EMPIEZA DIRECTAMENTE con ===HISTORIA 1===, sin texto previo ni explicaciones."""

    # Seleccionar API según TEXT_MODEL
    chat_url_for_images = None
    if TEXT_MODEL == "gemini_web":
        try:
            # gemini_image_gen.py is in the same directory
            from gemini_image_gen import generate_story_web
            
            response, chat_url_for_images = generate_story_web(prompt)
        except Exception as e:
            print(f"⚠️ Error generando historia en Gemini Web: {e}")
            response = None
    else:
        # Usar LiteLLM para manejar a cualquier proveedor
        response = generate_text_litellm(prompt, model=TEXT_MODEL, max_tokens=5000, temperature=0.95)
    
    if not response:
        return []

    stories = []
    historia_blocks = re.split(r'(?:#+\s*)?===\s*HISTORIA\s*\d+\s*===', response)
    historia_blocks = [b.strip() for b in historia_blocks if b.strip()]

    for block in historia_blocks:
        if len(stories) >= count:
            break
        # Separar historia, imágenes y SFX
        parts = re.split(r'(?:#+\s*)?===\s*(?:IM[AÁ]GENES|SFX)\s*\d+\s*===', block, flags=re.IGNORECASE)
        story_part = parts[0].strip()
        images_part = parts[1].strip() if len(parts) > 1 else ""
        sfx_part = parts[2].strip() if len(parts) > 2 else ""

        lines = [l.strip() for l in story_part.split('\n') if l.strip()]
        if len(lines) < 2:
            continue

        declared_count = None
        clean_lines = []
        for line in lines:
            m_img = re.match(r'IMAGES?:\s*\d+', line, re.IGNORECASE)
            m_img2 = re.match(r'IMG\s*COUNT', line, re.IGNORECASE)
            m_num_only = re.match(r'^\d+$', line)
            m_underscore = re.match(r'^[A-Z_]+\d*$', line)
            # Siempre filtrar lineas IMAGES: (no solo la primera)
            if m_img:
                if declared_count is None:
                    declared_count = int(re.search(r'\d+', line).group())
                continue
            if (m_img2 or m_num_only or m_underscore) and declared_count is None:
                continue
            clean_lines.append(line)
        lines = clean_lines

        if len(lines) < 2:
            continue
        
        # Buscar el título: primera línea válida que no sea metadata
        title = None
        for line in lines:
            line_clean = line.replace('[', '').replace(']', '').replace('*', '').replace('#', '').strip()
            # AGRESIVAMENTE limpiar caracteres no-latinos (fix bug caracteres chinos)
            line_clean = re.sub(r'[^\x20-\x7E\u00C0-\u024F\u1E00-\u1EFF]', '', line_clean)
            # Limpiar artefactos de instrucciones que el LLM copia del prompt
            for artifact in ['SOLO caracteres latinos', 'Tu titulo aqui', 'Tu título aquí',
                            'solo caracteres', 'caracteres latinos', '— SOLO', '- SOLO']:
                line_clean = line_clean.replace(artifact, '').strip()
            # Eliminar guiones decorativos al final
            line_clean = re.sub(r'\s*[—–-]+\s*$', '', line_clean).strip()
            if len(line_clean) >= 3 and not re.match(r'^\d+$', line_clean):
                title = line_clean
                break
        
        if not title:
            title = "Historia Sin Titulo"
        story = '\n'.join(lines[1:]).strip()
        if len(story) < 80 or len(title) > 100:
            continue

        # Extraer prompts de imágenes con timestamps
        img_data = []
        img_pattern = r'IMG\d+\s+(\d+:\d+)\s*:\s*(.+?)(?=\nIMG\d+|\n===|\Z)'
        for m in re.finditer(img_pattern, images_part, re.MULTILINE | re.DOTALL):
            timestamp = m.group(1).strip()
            prompt_text = ' '.join(m.group(2).strip().split())
            if len(prompt_text) > 15:
                img_data.append({
                    'prompt': prompt_text,
                    'timestamp': timestamp,
                    'seconds': parse_timestamp_to_seconds(timestamp)
                })
        
        # Fallback: sin timestamps
        if not img_data:
            for m in re.finditer(r'IMG\d+:\s*\[?(.+?)\]?\s*$', images_part, re.MULTILINE):
                p = m.group(1).strip()
                if len(p) > 15:
                    img_data.append({'prompt': p, 'timestamp': None, 'seconds': None})

        # Extraer SFX cues
        sfx_cues = []
        if sfx_part:
            sfx_pattern = r'(\d+:\d+)\s*:\s*([a-zA-Z0-9_]+)'
            for m in re.finditer(sfx_pattern, sfx_part):
                ts = m.group(1).strip()
                sfx_name = m.group(2).strip()
                # Verificar si el archivo existe (tolerancia con extensiones)
                for ext in ['.mp3', '.wav']:
                    if os.path.exists(os.path.join(SOUNDS_DIR, f"{sfx_name}{ext}")):
                        sfx_cues.append({
                            'timestamp': ts,
                            'seconds': parse_timestamp_to_seconds(ts),
                            'file': f"{sfx_name}{ext}"
                        })
                        break
                else:
                    print(f"    ⚠️ SFX '{sfx_name}' no encontrado en sounds/ (ignorado)")

        if sfx_cues:
            print(f"  🎵 SFX detectados: {len(sfx_cues)}")
            for cue in sfx_cues:
                print(f"     🔊 {cue['timestamp']} → {cue['file']}")
        elif sfx_part:
            print(f"  ⚠️ La IA pidió SFX pero ningún archivo coincide en sounds/")

        if declared_count:
            print(f"  🖼️  Kimi eligió {declared_count} imágenes, se encontraron {len(img_data)} prompts")
            for idx, img in enumerate(img_data[:5], 1):
                ts = img['timestamp'] or 'auto'
                print(f"     IMG{idx}: {ts}")

        stories.append({
            'title': title,
            'story': story,
            'place_type': 'generic',
            'niche_id': niche_id,
            'niche': niche,
            'image_prompts': img_data,
            'sfx_cues': sfx_cues,
            'has_timestamps': any(img['timestamp'] for img in img_data),
            'chat_url_for_images': chat_url_for_images
        })

    return stories


# ═══════════════════════════════════════════════════════════════════════════════
# RESTO DEL SISTEMA (Audio, SDXL, Video - Igual que el original)
# ═══════════════════════════════════════════════════════════════════════════════

def get_best_sdxl_model():
    if not os.path.exists(SDXL_MODELS_DIR):
        return None
    preferred = [
        "realvisxlV50_v50Bakedvae.safetensors",
        "realvisxlV50_v50LightningBakedvae.safetensors",
        "realvisxlV40.safetensors",
        "juggernautXL_versionXI.safetensors",
        "sd_xl_base_1.0.safetensors",
    ]
    available = os.listdir(SDXL_MODELS_DIR)
    for model in preferred:
        if model in available:
            return os.path.join(SDXL_MODELS_DIR, model)
    for f in available:
        if f.endswith('.safetensors') and 'xl' in f.lower():
            return os.path.join(SDXL_MODELS_DIR, f)
    return None

SDXL_MODEL_PATH = get_best_sdxl_model()
SDXL_CONFIG = {"scheduler": "DPM++ SDE Karras", "num_inference_steps": 35, "guidance_scale": 7.5}

def find_tool(name):
    path = shutil.which(name) or shutil.which(name + ".exe")
    if path:
        return path
    if sys.platform == "win32":
        candidates = [
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Packages",
                        f"PythonSoftwareFoundation.Python.{sys.version_info.major}.{sys.version_info.minor}_qbz5n2kfra8p0",
                        "LocalCache", "local-packages", f"Python{sys.version_info.major}{sys.version_info.minor}", "Scripts", name + ".exe"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
    return name

FFMPEG_BIN = find_tool("ffmpeg")
FFPROBE_BIN = find_tool("ffprobe")

TTS_WORDS_PER_CHUNK = 350

# ═══════════════════════════════════════════════════════════════════════════════
# SONIDOS DE FONDO (SFX)
# ═══════════════════════════════════════════════════════════════════════════════

SFX_MAP = {
    # Lluvia
    "lluvia": "sounds/rain.mp3",
    "rain": "sounds/rain.mp3",
    "llov": "sounds/rain.mp3",
    "trueno": "sounds/rain.mp3",
    "tormenta": "sounds/rain.mp3",
    "storm": "sounds/rain.mp3",
    "thunder": "sounds/rain.mp3",
    "mojado": "sounds/rain.mp3",
    "wet": "sounds/rain.mp3",
    "charco": "sounds/rain.mp3",
    "puddle": "sounds/rain.mp3",
    
    # Pasos
    "pasos": "sounds/steps.mp3",
    "steps": "sounds/steps.mp3",
    "footsteps": "sounds/steps.mp3",
    "camin": "sounds/steps.mp3",
    "walk": "sounds/steps.mp3",
    "correr": "sounds/steps.mp3",
    "run": "sounds/steps.mp3",
    "corr": "sounds/steps.mp3",
    "apresur": "sounds/steps.mp3",
    "hurry": "sounds/steps.mp3",
    "escap": "sounds/steps.mp3",
    "escape": "sounds/steps.mp3",
    "persegu": "sounds/steps.mp3",
    "chase": "sounds/steps.mp3",
    "sendero": "sounds/steps.mp3",
    "trail": "sounds/steps.mp3",
    "bosque": "sounds/steps.mp3",
    "forest": "sounds/steps.mp3",
    
    # Puerta
    "puerta": "sounds/open_door.mp3",
    "door": "sounds/open_door.mp3",
    "toc": "sounds/open_door.mp3",
    "knock": "sounds/open_door.mp3",
    "golp": "sounds/open_door.mp3",
    "abri": "sounds/open_door.mp3",
    "open": "sounds/open_door.mp3",
    "cerr": "sounds/open_door.mp3",
    "close": "sounds/open_door.mp3",
    "entr": "sounds/open_door.mp3",
    "enter": "sounds/open_door.mp3",
    "salir": "sounds/open_door.mp3",
    "exit": "sounds/open_door.mp3",
    "habitaci": "sounds/open_door.mp3",
    "room": "sounds/open_door.mp3",
    "cuarto": "sounds/open_door.mp3",
    "casa": "sounds/open_door.mp3",
    "house": "sounds/open_door.mp3",
}

def analyze_text_for_sfx(text):
    """Devuelve una lista de SFX sugeridos basados en el texto"""
    found_sfx = []
    text_lower = text.lower()
    for word, filepath in SFX_MAP.items():
        if word in text_lower:
            found_sfx.append(filepath)
    return list(set(found_sfx))  # Evitar duplicados

def mix_background_sfx(audio_path, sfx_files, output_path, sfx_volume=0.15):
    """
    Mezcla sonidos de fondo con el audio principal.
    Los SFX se hacen loop para cubrir toda la duración del audio.
    """
    if not sfx_files:
        # Sin SFX, solo copiar el archivo original
        shutil.copy(audio_path, output_path)
        return True
    
    # Verificar que los archivos existen
    valid_sfx = [sfx for sfx in sfx_files if os.path.exists(sfx)]
    if not valid_sfx:
        print(f"  ⚠️ No se encontraron archivos SFX válidos")
        shutil.copy(audio_path, output_path)
        return True
    
    print(f"  🔊 Mezclando {len(valid_sfx)} sonido(s) de fondo...")
    
    # Obtener duración del audio principal
    try:
        result = subprocess.run([FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration",
                                "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
                               capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=10)
        duration = float(result.stdout.strip())
    except:
        print(f"  ⚠️ No se pudo obtener duración, copiando audio sin SFX")
        shutil.copy(audio_path, output_path)
        return True
    
    # Preparar filtros para mezclar múltiples SFX
    # Cada SFX se hace loop y se mezcla con el volumen reducido
    filter_parts = []
    inputs = []
    
    # Audio principal (índice 0)
    inputs.extend(["-i", audio_path])
    
    # Archivos SFX (índices 1+)
    for i, sfx in enumerate(valid_sfx):
        inputs.extend(["-i", sfx])
        # Loop del SFX para cubrir toda la duración, con fade in/out
        filter_parts.append(
            f"[{i+1}:a]aloop=loop=-1:size=2e+09,afade=t=in:ss=0:d=2,afade=t=out:st={duration-2}:d=2,"
            f"volume={sfx_volume},atrim=0:{duration}[sfx{i}]"
        )
    
    # Construir el filtro de mezcla
    if len(valid_sfx) == 1:
        # Un solo SFX: preparar + mezclar
        filter_complex = filter_parts[0] + ";[0:a][sfx0]amix=inputs=2:duration=first:dropout_transition=3[aout]"
    else:
        # Múltiples SFX: mezclar SFX entre sí, luego con audio principal
        sfx_mix = "".join([f"[sfx{i}]" for i in range(len(valid_sfx))])
        filter_complex = ";".join(filter_parts) + ";" + (
            f"{sfx_mix}amix=inputs={len(valid_sfx)}:duration=longest[combined_sfx];"
            f"[0:a][combined_sfx]amix=inputs=2:duration=first:dropout_transition=3[aout]"
        )
    
    # Ejecutar ffmpeg
    cmd = [FFMPEG_BIN, "-y"] + inputs + ["-filter_complex", filter_complex, "-map", "[aout]", 
           "-c:a", "libmp3lame", "-q:a", "2", output_path]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', 
                               errors='ignore', timeout=120)
        if result.returncode == 0 and os.path.exists(output_path):
            print(f"  ✅ Audio con SFX mezclado")
            return True
        else:
            print(f"  ⚠️ Error mezclando SFX: {result.stderr[:200]}")
            shutil.copy(audio_path, output_path)
            return True
    except Exception as e:
        print(f"  ⚠️ Error en mezcla: {e}")
        shutil.copy(audio_path, output_path)
        return True

def _split_text_chunks(text, max_words=TTS_WORDS_PER_CHUNK):
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current, count = [], "", 0
    for s in sentences:
        s_words = len(s.split())
        if count + s_words <= max_words:
            current = (current + " " + s).strip() if current else s
            count += s_words
        else:
            if current:
                chunks.append(current)
            current = s
            count = s_words
    if current:
        chunks.append(current)
    return chunks

def _tts_chunk_to_pcm(text):
    url = f"{GEMINI_TTS_URL}?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": GEMINI_TTS_VOICE}}}
        }
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode())
    for part in data.get('candidates', [{}])[0].get('content', {}).get('parts', []):
        inline = part.get('inlineData', {})
        if inline.get('data'):
            return base64.b64decode(inline['data'])
    return None

def _crossfade_pcm(pcm_a, pcm_b, fade_ms=80):
    import struct
    fade_samples = int(24000 * fade_ms / 1000)
    min_bytes = fade_samples * 2
    if len(pcm_a) < min_bytes or len(pcm_b) < min_bytes:
        return pcm_a + pcm_b
    tail = struct.unpack(f'<{fade_samples}h', pcm_a[-min_bytes:])
    head = struct.unpack(f'<{fade_samples}h', pcm_b[:min_bytes])
    mixed = []
    for i in range(fade_samples):
        t = i / fade_samples
        s = int(tail[i] * (1.0 - t) + head[i] * t)
        mixed.append(max(-32768, min(32767, s)))
    return pcm_a[:-min_bytes] + struct.pack(f'<{fade_samples}h', *mixed) + pcm_b[min_bytes:]

def generate_audio(story_text, output_path):
    """Genera audio usando el motor TTS seleccionado, con fallback a Edge TTS."""
    text = story_text.replace('[', '').replace(']', '').replace('*', '').replace('"', '')
    
    success = False
    if TTS_ENGINE == "eleven" and ELEVENLABS_API_KEY:
        success = _generate_audio_elevenlabs(text, output_path)
    elif GEMINI_API_KEY:
        success = _generate_audio_gemini(text, output_path)
        
    if not success:
        print("  ⚠️ Usando Edge TTS como fallback...")
        success = _generate_audio_edge_tts(text, output_path)
        
    return success

def _generate_audio_edge_tts(text, output_path):
    """Genera audio con Edge TTS (gratuito, no requiere API key)."""
    # Voces en español recomendadas: es-ES-AlvaroNeural o es-MX-JorgeNeural
    voice = "es-ES-AlvaroNeural" if "españa" in CHANNEL_NAME.lower() else "es-MX-JorgeNeural"
    
    try:
        import edge_tts
        import asyncio
        
        async def _main():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)
            
        asyncio.run(_main())
        print("  ✅ Edge TTS: Audio generado con éxito")
        return True
    except ImportError:
        print("  ❌ ERROR: edge-tts no está instalado. Ejecuta: pip install edge-tts")
        return False
    except Exception as e:
        print(f"  ❌ Edge TTS error: {e}")
        return False

def _generate_audio_elevenlabs(text, output_path):
    """Genera audio con ElevenLabs REST API (streaming)."""
    print(f"  🎙️ ElevenLabs TTS (voice: {ELEVEN_VOICE_ID[:8]}...)")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE_ID}"
    payload = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.3,
            "use_speaker_boost": True,
	    "language":"es"
        }
    }
    headers = {
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY,
        "Accept": "audio/mpeg"
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=300) as resp:
            audio_data = resp.read()
            if len(audio_data) > 1000:
                with open(output_path, 'wb') as f:
                    f.write(audio_data)
                print(f"  ✅ ElevenLabs: {len(audio_data)//1024}KB de audio")
                return True
            else:
                print(f"  ⚠️ ElevenLabs: respuesta muy pequeña ({len(audio_data)} bytes)")
                return False
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='ignore')
        print(f"  ❌ ElevenLabs HTTP {e.code}: {error_body[:200]}")
        return False
    except Exception as e:
        print(f"  ❌ ElevenLabs error: {e}")
        return False

def _generate_audio_gemini(text, output_path):
    """Genera audio con Gemini TTS (chunks + crossfade)."""
    chunks = _split_text_chunks(text)
    print(f"  🎙️ {len(chunks)} chunk(s)...")
    all_pcm = b""
    for idx, chunk in enumerate(chunks, 1):
        try:
            print(f"  🔊 Chunk {idx}/{len(chunks)}...")
            pcm = _tts_chunk_to_pcm(chunk)
            if pcm:
                all_pcm = _crossfade_pcm(all_pcm, pcm) if all_pcm else pcm
        except Exception as e:
            print(f"  ⚠️ Error chunk {idx}: {e}")
    if not all_pcm:
        return False
    wav_path = output_path.replace('.mp3', '_raw.wav')
    with wave.open(wav_path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(all_pcm)
    result = subprocess.run([FFMPEG_BIN, "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-q:a", "2", output_path],
                           capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=60)
    os.remove(wav_path)
    return result.returncode == 0 and os.path.exists(output_path)

def generate_subtitles(audio_path, srt_path):
    global _whisper_mdl
    try:
        from faster_whisper import WhisperModel
        if _whisper_mdl is None:
            print("  📝 Cargando Whisper...")
            _whisper_mdl = WhisperModel("base", device="cuda", compute_type="float16")
        print("  📝 Transcribiendo...")
        segments, _ = _whisper_mdl.transcribe(audio_path, language="es", beam_size=5)
        def fmt_time(seconds):
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            ms = int((seconds % 1) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, seg in enumerate(segments, 1):
                f.write(f"{i}\n{fmt_time(seg.start)} --> {fmt_time(seg.end)}\n{seg.text.strip()}\n\n")
        return True
    except Exception as e:
        print(f"  ⚠️ Whisper error: {e}")
        return False

def load_sd_pipeline():
    global _sd_pipe, _ip_adapter_ok
    if _sd_pipe is not None:
        return _sd_pipe
    try:
        import torch
        from diffusers import StableDiffusionXLPipeline, DPMSolverMultistepScheduler
        torch.backends.cudnn.enabled = False
        torch.backends.cudnn.benchmark = False
        print("  📦 Cargando SDXL...")
        _sd_pipe = StableDiffusionXLPipeline.from_single_file(
            SDXL_MODEL_PATH, torch_dtype=torch.float16, use_safetensors=True, variant="fp16"
        ).to("cuda")
        _sd_pipe.scheduler = DPMSolverMultistepScheduler.from_config(
            _sd_pipe.scheduler.config, algorithm_type="sde-dpmsolver++", use_karras_sigmas=True
        )
        print(f"  ✅ SDXL listo")
        _ip_adapter_ok = False
    except Exception as e:
        print(f"  ❌ Error SDXL: {e}")
        _sd_pipe = None
    return _sd_pipe

def load_ip_adapter_if_needed():
    global _sd_pipe, _ip_adapter_ok
    if _sd_pipe is None or _ip_adapter_ok:
        return
    try:
        print("  🎨 Cargando IP-Adapter...")
        _sd_pipe.load_ip_adapter("h94/IP-Adapter", subfolder="sdxl_models", weight_name="ip-adapter_sdxl.bin")
        _ip_adapter_ok = True
        print("  ✅ IP-Adapter activo")
    except Exception as e:
        print(f"  ⚠️ IP-Adapter no disponible: {e}")
        _ip_adapter_ok = False

def unload_sd_pipeline():
    global _sd_pipe
    if _sd_pipe is not None:
        import torch
        del _sd_pipe
        _sd_pipe = None
        torch.cuda.empty_cache()
        print("  🧹 SDXL descargado")

def generate_image_sd(prompt, output_path, reference_image=None):
    pipe = load_sd_pipeline()
    if pipe is None:
        return False
    if reference_image is not None and not _ip_adapter_ok:
        load_ip_adapter_if_needed()
    try:
        import torch
        from PIL import Image as PILImage
        negative = "blurry, out of focus, low quality, jpeg artifacts, text, watermark, signature, logo, cropped, worst quality, cartoon, anime, sketch"
        gen_width, gen_height = (1024, 1024) if not IS_SHORT else (768, 1344)
        with torch.inference_mode():
            if _ip_adapter_ok and reference_image is not None:
                print(f"     ↳ IP-Adapter activo")
                pipe.set_ip_adapter_scale(0.5)
                image = pipe(prompt=prompt, negative_prompt=negative, ip_adapter_image=reference_image,
                            width=gen_width, height=gen_height, num_inference_steps=SDXL_CONFIG["num_inference_steps"],
                            guidance_scale=SDXL_CONFIG["guidance_scale"]).images[0]
            else:
                print(f"     ↳ Primera imagen")
                image = pipe(prompt=prompt, negative_prompt=negative, width=gen_width, height=gen_height,
                            num_inference_steps=SDXL_CONFIG["num_inference_steps"],
                            guidance_scale=SDXL_CONFIG["guidance_scale"]).images[0]
            # Resize
            if IS_SHORT:
                target_width, target_height = 1080, 1920
            else:
                target_width, target_height = 1920, 1080
            img_ratio = image.width / image.height
            target_ratio = target_width / target_height
            if img_ratio > target_ratio:
                new_height = target_height
                new_width = int(new_height * img_ratio)
            else:
                new_width = target_width
                new_height = int(new_width / img_ratio)
            image = image.resize((new_width, new_height), PILImage.Resampling.LANCZOS)
            left = (image.width - target_width) // 2
            top = (image.height - target_height) // 2
            image = image.crop((left, top, left + target_width, top + target_height))
        image.save(output_path, quality=95)
        return os.path.getsize(output_path) > 10000
    except Exception as e:
        import traceback
        print(f"  ⚠️ Error imagen: {e}")
        traceback.print_exc()
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# AUDIO MIXING (SFX)
# ═══════════════════════════════════════════════════════════════════════════════

def mix_audio_sfx(main_audio_path, sfx_cues):
    """
    Mezcla el audio principal (voz) con los efectos de sonido (SFX) generados por el LLM.
    Devuelve la ruta del nuevo archivo (o el original si ocurre un error).
    """
    if not sfx_cues:
        return main_audio_path
        
    print(f"  🎵 Añadiendo {len(sfx_cues)} efectos de sonido (SFX) cinemáticos...")
    output_path = main_audio_path.replace(".mp3", "_mixed.mp3").replace(".wav", "_mixed.wav")
    
    cmd = [FFMPEG_BIN, "-y", "-i", main_audio_path]
    
    # 1. Añadir inputs
    for cue in sfx_cues:
        sfx_path = os.path.join(SOUNDS_DIR, cue['file'])
        cmd.extend(["-i", sfx_path])
        
    # 2. Construir Filter Complex
    filter_complex = ""
    mix_inputs = "[0:a]"
    
    for i, cue in enumerate(sfx_cues):
        idx = i + 1
        delay_ms = int(cue['seconds'] * 1000)
        # Bajar el volumen de los SFX para no ahogar la voz y retrasarlos al segundo exacto
        filter_complex += f"[{idx}:a]volume=0.2,adelay={delay_ms}|{delay_ms}[sfx{idx}]; "
        mix_inputs += f"[sfx{idx}]"
        
    filter_complex += f"{mix_inputs}amix=inputs={len(sfx_cues)+1}:duration=first:dropout_transition=0:normalize=0[aout]"
    
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-c:a", "libmp3lame", "-q:a", "2",
        output_path
    ])
    
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        print(f"  ✅ Audio mezclado con SFX: {os.path.basename(output_path)}")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"    ⚠️ Error mezclando SFX (FFmpeg): {e.stderr.decode('utf-8', errors='ignore')[:200]}")
        return main_audio_path
    except Exception as e:
        print(f"    ⚠️ Error mezclando SFX: {e}")
        return main_audio_path


def create_video(images_dir, audio_file, output_file, subs_file=None, image_timestamps=None):
    """
    Crea video usando timestamps específicos para cada imagen si están disponibles.
    Si los timestamps exceden la duración del audio, se escalan proporcionalmente.
    image_timestamps: lista de dicts con 'seconds' o None para distribución uniforme
    """
    try:
        result = subprocess.run([FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration",
                                "-of", "default=noprint_wrappers=1:nokey=1", audio_file],
                               capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=10)
        duration = float(result.stdout.strip())
    except:
        duration = 120
    
    images = sorted([f for f in os.listdir(images_dir) if f.endswith(('.jpg', '.png'))])
    if not images:
        return False
    
    # Preparar duraciones por imagen
    if image_timestamps and len(image_timestamps) == len(images):
        # Extraer todos los tiempos de inicio válidos
        start_times = []
        for ts in image_timestamps:
            sec = ts.get('seconds')
            if sec is not None and sec >= 0:
                start_times.append(sec)
            else:
                start_times.append(0)
        
        max_ts = max(start_times) if start_times else 0
        
        # Si los timestamps exceden el audio o quedan muy cortos, escalar
        if max_ts > 0 and (max_ts > duration * 0.9 or max_ts < duration * 0.5):
            # Escalar proporcionalmente para que el último timestamp llegue al ~85% del audio
            target_duration = duration * 0.85
            scale_factor = target_duration / max_ts if max_ts > 0 else 1
            
            print(f"  ⏱️ Ajustando timestamps: IA estimó {max_ts:.0f}s, audio es {duration:.0f}s (factor: {scale_factor:.2f})")
            
            scaled_times = []
            for sec in start_times:
                scaled_times.append(sec * scale_factor)
            start_times = scaled_times
        else:
            print(f"  ⏱️ Usando timestamps de la IA para {len(images)} imágenes:")
        
        # Calcular duraciones basadas en tiempos de inicio
        durations = []
        for i, start_sec in enumerate(start_times):
            # El final es el inicio de la siguiente imagen o el final del audio
            if i < len(start_times) - 1:
                next_start = start_times[i + 1]
            else:
                next_start = duration
            
            dur = next_start - start_sec
            
            # Asegurar mínimo y máximo razonables
            dur = max(4, min(dur, duration - start_sec))  # Mínimo 4s, no pasar del audio
            
            # Si la duración es muy corta, extender hasta donde se pueda
            if dur < 5 and i == len(start_times) - 1:  # Última imagen
                dur = duration - start_sec  # Llegar hasta el final
            
            durations.append(dur)
            
            # Mostrar timestamp
            ts_display = f"{int(start_sec)//60}:{int(start_sec)%60:02d}"
            print(f"     IMG{i+1}: {ts_display} → {dur:.1f}s")
        
        # Verificar que cubrimos todo el audio (rebalancear si es necesario)
        total_dur = sum(durations)
        if total_dur < duration - 2:  # Si queda más de 2 segundos sin cubrir
            # Extender la última imagen
            extra = duration - total_dur
            durations[-1] += extra
            print(f"     (extendida última imagen +{extra:.1f}s para cubrir audio)")
    else:
        # Distribución uniforme (comportamiento anterior)
        print(f"  ⏱️ Distribución uniforme: {len(images)} imágenes")
        duration_per_image = duration / len(images)
        durations = [duration_per_image] * len(images)
    
    fps = 30
    
    if IS_SHORT:
        res_w, res_h = 1080, 1920
    else:
        res_w, res_h = 1920, 1080
    res = f"{res_w}x{res_h}"
    
    quality = VIDEO_QUALITY.lower() if VIDEO_QUALITY.lower() in QUALITY_PRESETS else "high"
    q = QUALITY_PRESETS[quality]
    print(f"  🎬 Codificando (calidad: {quality.upper()})")
    
    # Generar un clip por imagen con zoompan individual (respeta timestamps)
    clip_files = []
    for i, img in enumerate(images):
        d_frames_i = max(1, int(durations[i] * fps))
        zoom_speed_i = round(0.5 / d_frames_i, 6)
        
        clip_file = os.path.join(images_dir, f"clip_{i:03d}.mp4")
        img_path = os.path.join(images_dir, img)
        
        vf_i = (f"scale={res_w}:{res_h}:force_original_aspect_ratio=decrease,"
                f"pad={res_w}:{res_h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p,"
                f"zoompan=z='min(zoom+{zoom_speed_i},1.5)':d={d_frames_i}:s={res}")
        
        clip_cmd = [FFMPEG_BIN, "-y", "-loop", "1", "-i", img_path,
                    "-vf", vf_i, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-r", str(fps), "-t", str(durations[i]),
                    "-crf", "1", "-preset", "ultrafast",
                    "-an", clip_file]
        try:
            clip_result = subprocess.run(clip_cmd, capture_output=True, text=True,
                                         encoding='utf-8', errors='ignore', timeout=120)
            if clip_result.returncode == 0 and os.path.exists(clip_file):
                clip_files.append(clip_file)
            else:
                print(f"  ⚠️ Error generando clip {i+1}: {clip_result.stderr[:200] if clip_result.stderr else 'unknown'}")
        except Exception as e:
            print(f"  ⚠️ Error clip {i+1}: {e}")
    
    if not clip_files:
        print("  ❌ No se generaron clips")
        return False
    
    # Escribir lista de clips para concatenar
    concat_file = os.path.join(images_dir, "clips.txt")
    with open(concat_file, 'w', encoding='utf-8') as f:
        for cf in clip_files:
            f.write(f"file '{cf}'\n")
    
    # Preparar subtítulos
    subs_cwd = None
    subs_vf = ""
    if subs_file and os.path.exists(subs_file):
        subs_cwd = os.path.dirname(subs_file)
        subs_name = os.path.basename(subs_file)
        style = ("FontName=Arial,FontSize=14,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                "Outline=2,Bold=1,Alignment=2,MarginV=50") if IS_SHORT else ("FontName=Arial,FontSize=16,"
                "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=3,Bold=1,Alignment=2,MarginV=40")
        subs_vf = f"subtitles='{subs_name}':force_style='{style}'"
    
    # Concatenar clips + audio (+ subs si hay)
    concat_cmd = [FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
                  "-i", audio_file]
    if subs_vf:
        # Re-encode necesario para quemar subtítulos — usar calidad final
        concat_cmd += ["-vf", subs_vf]
        concat_cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
                       "-crf", q["crf"], "-preset", q["preset"],
                       "-maxrate", q["maxrate"], "-bufsize", q["bufsize"]]
    else:
        # Sin subs: copiar video sin re-encode (calidad perfecta)
        concat_cmd += ["-c:v", "copy"]
    concat_cmd += ["-c:a", "aac", "-b:a", "192k", "-t", str(duration),
                   "-shortest", output_file]
    try:
        result = subprocess.run(concat_cmd, capture_output=True, text=True,
                               encoding='utf-8', errors='ignore', timeout=600, cwd=subs_cwd)
        success = result.returncode == 0 and os.path.exists(output_file)
    except Exception as e:
        print(f"  ⚠️ FFmpeg concat error: {e}")
        success = False
    
    # Limpiar clips temporales
    for cf in clip_files:
        try:
            os.remove(cf)
        except:
            pass
    try:
        os.remove(concat_file)
    except:
        pass
    
    return success

def select_best_thumbnail(img_dir):
    images = sorted([f for f in os.listdir(img_dir) if f.endswith(('.jpg', '.png'))])
    if not images:
        return None
    return os.path.join(img_dir, images[len(images) // 2])

def generate_video_info(story_data, video_file, story_dir, img_count, voice_used):
    """Genera metadata optimizada para YouTube con SEO por nicho"""
    video_filename = os.path.basename(video_file)
    body = story_data['story']
    title = story_data['title']
    niche = story_data.get('niche', {})
    niche_id = story_data.get('niche_id', 'general')
    niche_tags = niche.get('tags', [])
    
    # Hook: primera frase de la historia como gancho para la descripción
    first_sentence = body.split('.')[0].strip() + '.' if '.' in body else body[:100]
    preview = body[:500].rsplit('.', 1)[0] + '.' if len(body) > 500 else body
    
    # Títulos variantes para A/B testing
    title_variants = [
        f"{title} | {CHANNEL_NAME}",
        f"{title} — Historia Real Narrada",
        f"{title} | Storytime en Español",
    ]
    if IS_SHORT:
        title_variants = [f"{title} #Shorts" for t in title_variants]
    
    # Descripción optimizada para YouTube SEO
    niche_nombre = niche.get('nombre', 'Relato')
    description = (
        f"🎧 {first_sentence}\n\n"
        f"{preview}\n\n"
        f"{'─'*40}\n"
        f"🎭 {CHANNEL_NAME} — {niche_nombre}\n"
        f"Historias originales narradas con voz natural (IA).\n"
        f"📌 Suscríbete y activa la 🔔 para nuevos relatos.\n\n"
        f"#storytime #relatos #{niche_id} #historias #narración\n"
        f"#{CHANNEL_NAME.replace(' ', '')} #español"
    )
    if IS_SHORT:
        description += "\n\n#Shorts #YouTubeShorts"
    
    # Tags: combinar base + nicho
    all_tags = list(set(
        DEFAULT_TAGS + niche_tags +
        ["storytime español", "historia narrada", niche_id.replace('_', ' ')] +
        (["shorts", "youtube shorts"] if IS_SHORT else [])
    ))
    
    img_dir = os.path.join(story_dir, "images")
    thumbnail_source = select_best_thumbnail(img_dir) if os.path.exists(img_dir) else None
    
    info = {
        "version": "2.0",
        "created_at": datetime.now().isoformat(),
        "video": {
            "filename": video_filename, "path": video_file, "title": title,
            "channel": CHANNEL_NAME,
            "youtube_title": title_variants[0],
            "youtube_title_variants": title_variants,
            "description": description,
            "tags": all_tags, "category": "Entertainment",
            "privacy": "public", "language": "es", "is_short": IS_SHORT
        },
        "content": {
            "niche_id": niche_id,
            "niche_name": niche.get('nombre', 'General'),
            "title": title, "content": body,
            "word_count": len(body.split()),
            "hook": first_sentence,
            "story_file": os.path.join(story_dir, "historia.txt")
        },
        "production": {
            "text_model": "Moonshot (Kimi)", "tts_model": GEMINI_TTS_MODEL, "tts_voice": voice_used,
            "image_model": "Gemini Web (Nano Banana)" if IMAGE_ENGINE == "gemini_web" else "SDXL Local", "image_count": img_count,
            "thumbnail_source": thumbnail_source, "temp_dir": story_dir
        },
        "upload": {"uploaded": False, "uploaded_at": None, "video_id": None, "video_url": None}
    }
    info_file = video_file.replace('.mp4', '_video_info.json')
    with open(info_file, 'w', encoding='utf-8') as f:
        json.dump(info, f, indent=2, ensure_ascii=False)
    return info_file


def create_creepypasta(num_stories=1, context=None, duration_min=None, niche_name=None):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = os.path.join(PROJECT_DIR, "temp", f"batch_{timestamp}")
    output_dir = os.path.join(PROJECT_DIR, "output")
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print(f"🎬 VIRAL CONTENT FACTORY — {CHANNEL_NAME}")
    # Dynamic labels based on actual configuration
    if TEXT_MODEL == "gemini_web":
        model_label = "Gemini Web (Playwright)"
    else:
        model_label = TEXT_MODEL
    print(f"   📝 Texto: {model_label}")
    
    if TTS_ENGINE == "eleven":
        tts_label = f"ElevenLabs — {ELEVEN_VOICE_ID[:8]}..."
    elif TTS_ENGINE == "edge":
        tts_label = "Edge TTS (Gratis)"
    else:
        tts_label = f"Gemini TTS — {GEMINI_TTS_VOICE}"
    print(f"   🎙️ Voz: {tts_label}")
    
    img_label = "Gemini Web (Nano Banana)" if IMAGE_ENGINE == "gemini_web" else "SDXL Local"
    print(f"   🎨 Imágenes: {img_label}")
    if niche_name:
        print(f"   🎯 Nicho: {niche_name}")
    else:
        print(f"   🎯 Nicho: AUTO (selección aleatoria viral)")
    print("=" * 60)

    # ── First-run Gemini Web login check ──
    if TEXT_MODEL == "gemini_web" or IMAGE_ENGINE == "gemini_web":
        pw_profile = os.path.join(os.path.expanduser("~"), ".playwright-youtube")
        # Check if profile has never been created or has no cookies
        needs_login = not os.path.isdir(pw_profile) or not os.listdir(pw_profile)
        
        if needs_login:
            print("\n" + "═"*60)
            print("🌐 PRIMERA VEZ — Necesitas loguearte en Gemini Web")
            print("═"*60)
            print("  Se abrirá Chrome para que te loguees con tu")
            print("  cuenta de Google (la que tiene Gemini Premium).")
            print("  La sesión se guarda automáticamente para futuras ejecuciones.\n")
            
            resp = input("  ¿Abrir Chrome para loguearte ahora? (S/n): ").strip().lower()
            if resp in ("", "s", "si", "sí", "y", "yes"):
                try:
                    from gemini_image_gen import verify_login_interactive
                    verify_login_interactive()
                    print("\n  ✅ Login completado. Continuando con la generación...\n")
                except ImportError:
                    print("  ❌ No se encontró gemini_image_gen.py")
                    return False
                except Exception as e:
                    print(f"  ⚠️ Error durante login: {e}")
                    cont = input("  ¿Intentar continuar de todos modos? (s/N): ").strip().lower()
                    if cont not in ("s", "si", "sí", "y", "yes"):
                        return False
            else:
                print("  ⚠️ Sin login, Gemini Web no funcionará.")
                return False

    global SDXL_MODEL_PATH
    if IMAGE_ENGINE != "gemini_web":
        SDXL_MODEL_PATH = get_best_sdxl_model()
        if not SDXL_MODEL_PATH or not os.path.exists(SDXL_MODEL_PATH):
            print(f"❌ No se encontró modelo SDXL")
            return False

    if duration_min:
        target_words = int(duration_min * 135)
    elif IS_SHORT:
        target_words = 90
    else:
        target_words = None

    if target_words:
        print(f"\n📖 Generando {num_stories} historia(s) (~{target_words} palabras)...")
    else:
        print(f"\n📖 Generando {num_stories} historia(s)...")

    stories = generate_story_batch(num_stories, context=context, target_words=target_words, niche_name=niche_name)
    if not stories:
        print("❌ No se pudieron generar historias")
        return False
    print(f"✅ {len(stories)} historia(s) generada(s) por Kimi")

    generated_videos = []
    for i, story_data in enumerate(stories, 1):
        print(f"\n{'='*60}")
        print(f"🎬 PROCESANDO HISTORIA {i}/{len(stories)}")
        print(f"{'='*60}")
        print(f"📌 Título: {story_data['title'][:60]}")
        print(f"📝 Palabras: {len(story_data['story'].split())}")
        print(f"🖼️  Imágenes: {len(story_data['image_prompts'])}")

        story_dir = os.path.join(work_dir, f"story_{i:02d}")
        os.makedirs(story_dir, exist_ok=True)

        with open(os.path.join(story_dir, "historia.txt"), 'w', encoding='utf-8') as f:
            f.write(f"Título: {story_data['title']}\n\n{story_data['story']}")

        # Audio
        print(f"\n🎙️ Generando voz ({GEMINI_TTS_VOICE})...")
        audio_file = os.path.join(story_dir, "audio.mp3")
        if not generate_audio(story_data['story'], audio_file):
            print("⚠️ Saltando historia (error audio)")
            continue
        print("✅ Voz generada")
        
        # Audio Mix (SFX)
        if story_data.get('sfx_cues'):
            mixed_audio = mix_audio_sfx(audio_file, story_data['sfx_cues'])
            if mixed_audio != audio_file:
                audio_file = mixed_audio # Usar el audio mezclado para el video
                print("✅ Efectos de sonido (SFX) integrados")
        
        # SFX desactivado temporalmente (se reemplazará con ElevenLabs)
        # print("  🔍 Analizando texto para sonidos de fondo...")
        # detected_sfx = analyze_text_for_sfx(story_data['story'])
        # if detected_sfx:
        #     print(f"  🎵 Sonidos detectados: {len(detected_sfx)}")
        #     for sfx in detected_sfx:
        #         print(f"     • {os.path.basename(sfx)}")
        #     audio_with_sfx = os.path.join(story_dir, "audio_with_sfx.mp3")
        #     if mix_background_sfx(audio_file, detected_sfx, audio_with_sfx):
        #         audio_file = audio_with_sfx
        # else:
        #     print("  ℹ️ No se detectaron sonidos de fondo")

        # Subs
        srt_file = os.path.join(story_dir, "subs.srt")
        if generate_subtitles(audio_file, srt_file):
            print("✅ Subtítulos generados")
        else:
            srt_file = None
            print("⚠️ Sin subtítulos")

        # Imágenes
        img_prompts_data = story_data['image_prompts']
        has_timestamps = story_data.get('has_timestamps', False)
        engine_label = "Gemini Web" if IMAGE_ENGINE == "gemini_web" else "SDXL"
        print(f"\n🖼️ Generando {len(img_prompts_data)} imágenes ({engine_label}) {'(con timestamps IA)' if has_timestamps else '(distribución uniforme)'}...")
        img_dir = os.path.join(story_dir, "images")
        os.makedirs(img_dir, exist_ok=True)

        img_count = 0
        reference_image = None
        generated_timestamps = []  # Para pasar a create_video

        if IMAGE_ENGINE == "gemini_web":
            # ── Gemini Web: generar imágenes via Playwright ──
            try:
                # Importar desde BROWSER VERSION
                browser_dir = os.path.join(PROJECT_DIR, "BROWSER VERSION")
                if browser_dir not in sys.path:
                    sys.path.insert(0, browser_dir)
                from gemini_image_gen import generate_images_batch

                # Preparar lista de prompts para batch
                batch_prompts = []
                for j, img_data in enumerate(img_prompts_data):
                    img_file = os.path.join(img_dir, f"img_{j:02d}.png")
                    if isinstance(img_data, dict):
                        img_prompt = img_data['prompt']
                        img_timestamp = img_data.get('timestamp')
                        img_seconds = img_data.get('seconds')
                    else:
                        img_prompt = img_data
                        img_timestamp = None
                        img_seconds = None

                    batch_prompts.append({
                        'prompt': img_prompt,
                        'output_path': img_file,
                    })
                    generated_timestamps.append({
                        'timestamp': img_timestamp,
                        'seconds': img_seconds,
                    })

                # Extraer chat_url si la historia se generó en la web de Gemini
                chat_url_from_story = story_data.get('chat_url_for_images')
                
                # Generar todas las imágenes en batch (una sesión de browser)
                img_count = generate_images_batch(batch_prompts, is_short=IS_SHORT, initial_chat_url=chat_url_from_story)

                # Resize de las imágenes generadas para que coincidan con el video
                from PIL import Image as PILImage
                for j in range(len(img_prompts_data)):
                    img_file = os.path.join(img_dir, f"img_{j:02d}.png")
                    if os.path.exists(img_file) and os.path.getsize(img_file) > 5000:
                        try:
                            image = PILImage.open(img_file)
                            if IS_SHORT:
                                target_w, target_h = 1080, 1920
                            else:
                                target_w, target_h = 1920, 1080
                            img_ratio = image.width / image.height
                            target_ratio = target_w / target_h
                            if img_ratio > target_ratio:
                                new_h = target_h
                                new_w = int(new_h * img_ratio)
                            else:
                                new_w = target_w
                                new_h = int(new_w / img_ratio)
                            image = image.resize((new_w, new_h), PILImage.Resampling.LANCZOS)
                            left = (image.width - target_w) // 2
                            top = (image.height - target_h) // 2
                            image = image.crop((left, top, left + target_w, top + target_h))
                            image.save(img_file, quality=95)
                        except Exception as e:
                            print(f"  ⚠️ Error resize img {j+1}: {e}")

            except ImportError:
                print("❌ No se encontró gemini_image_gen.py")
                print("   Asegúrate de que existe: gemini_image_gen.py")
                continue
            except Exception as e:
                print(f"❌ Error con Gemini Web imágenes: {e}")
                continue

        else:
            # ── SDXL Local: generación original ──
            for j, img_data in enumerate(img_prompts_data):
                img_file = os.path.join(img_dir, f"img_{j:02d}.png")
                label = "🎨" if reference_image is None else "🔗"

                # Extraer el prompt (ahora es un dict)
                if isinstance(img_data, dict):
                    img_prompt = img_data['prompt']
                    img_timestamp = img_data.get('timestamp')
                    img_seconds = img_data.get('seconds')
                else:
                    img_prompt = img_data
                    img_timestamp = None
                    img_seconds = None

                ts_display = f" [{img_timestamp}]" if img_timestamp else ""
                print(f"  {label} Img {j+1}/{len(img_prompts_data)}{ts_display}: {img_prompt[:60]}...")

                if generate_image_sd(img_prompt, img_file, reference_image=reference_image):
                    img_count += 1
                    from PIL import Image as PILImage
                    reference_image = PILImage.open(img_file)
                    generated_timestamps.append({
                        'timestamp': img_timestamp,
                        'seconds': img_seconds
                    })
                    print(f"  ✅ Img {j+1} lista")
                else:
                    print(f"  ⚠️ Falló img {j+1}")
                    generated_timestamps.append({
                        'timestamp': img_timestamp,
                        'seconds': img_seconds
                    })

        if img_count == 0:
            print("❌ Sin imágenes, abortando")
            if IMAGE_ENGINE != "gemini_web":
                unload_sd_pipeline()
            continue
        print(f"✅ {img_count}/{len(img_prompts_data)} imágenes generadas")

        # Video
        print("\n🎬 Renderizando video...")
        safe_title = re.sub(r'[\\/*?:"<>|]', '', story_data['title'])
        safe_title = re.sub(r'\s+', '_', safe_title.strip())[:50]
        prefix = "short" if IS_SHORT else VIDEO_PREFIX
        video_filename = f"{prefix}_{timestamp}_{i:02d}_{safe_title}.mp4"
        video_file = os.path.join(output_dir, video_filename)

        if create_video(img_dir, audio_file, video_file, subs_file=srt_file, 
                        image_timestamps=generated_timestamps if has_timestamps else None):
            size_mb = os.path.getsize(video_file) / (1024 * 1024)
            print(f"✅ VIDEO LISTO: {video_file}")
            print(f"📊 Tamaño: {size_mb:.1f} MB")
            print("📝 Generando metadata...")
            info_file = generate_video_info(story_data, video_file, story_dir, img_count, GEMINI_TTS_VOICE)
            print(f"✅ Metadata: {os.path.basename(info_file)}")
            generated_videos.append({'video': video_file, 'info': info_file, 'title': story_data['title']})
        else:
            print("❌ Error creando video")

        if IMAGE_ENGINE != "gemini_web":
            print("🧹 Liberando memoria GPU...")
            unload_sd_pipeline()
            import time
            time.sleep(2)

    if IMAGE_ENGINE != "gemini_web":
        unload_sd_pipeline()
    print(f"\n{'='*60}")
    print("🏭 PROCESO COMPLETADO - KIMI DIRECTOR")
    print(f"📁 Videos generados: {len(generated_videos)}")
    for v in generated_videos:
        print(f"   • {os.path.basename(v['video'])}")
    print(f"{'='*60}")
    return True


def main():
    global IS_SHORT, VIDEO_QUALITY, GEMINI_TTS_VOICE, TEXT_MODEL, TTS_ENGINE, IMAGE_ENGINE
    
    import argparse
    
    # Listar nichos disponibles para el help
    niche_list = ", ".join(CONTENT_NICHES.keys())
    
    parser = argparse.ArgumentParser(description="🎬 Viral Content Factory — Fábrica de Contenido Viral")
    parser.add_argument("--count", type=int, default=1, help="Número de historias")
    parser.add_argument("--context", type=str, default=None, help="Contexto/idea para la historia")
    parser.add_argument("--duration", type=float, default=None, help="Duración en minutos")
    parser.add_argument("--voice", type=str, default=None, help="Voz TTS (Charon, Fenrir, Kore, Orus)")
    parser.add_argument("--quality", type=str, default="high", choices=["high", "medium", "low", "minimal"])
    parser.add_argument("--short", action="store_true", help="Modo Short (9:16 vertical, ≤60s)")
    parser.add_argument("--model", type=str, default=DEFAULT_TEXT_MODEL,
                        help="Modelo de texto LiteLLM (ej: gemini/gemini-2.5-flash, openai/gpt-4o, deepseek/deepseek-chat)")
    parser.add_argument("--niche", type=str, default=None,
                        help=f"Nicho de contenido. Opciones: {niche_list}. Si no se especifica, se elige uno al azar.")
    parser.add_argument("--list-niches", action="store_true", help="Muestra los nichos disponibles y sale")
    parser.add_argument("--eleven", action="store_true", help="Usar ElevenLabs TTS en vez de Gemini TTS")
    parser.add_argument("--eleven-voice", type=str, default=None,
                        help="Voice ID de ElevenLabs (default: Adam)")
    parser.add_argument("--gemini-images", action="store_true",
                        help="Usar Gemini Web (Playwright) para generar imágenes en vez de SDXL local")
    parser.add_argument("--gemini-web-story", action="store_true",
                        help="Usar Gemini Web (Playwright) para generar LA HISTORIA en vez de API de texto")
    args = parser.parse_args()

    # Mostrar nichos y salir
    if args.list_niches:
        print("\n🎯 NICHOS DE CONTENIDO VIRAL DISPONIBLES:\n")
        for key, niche in CONTENT_NICHES.items():
            print(f"  📌 {key}")
            print(f"     {niche['nombre']}")
            print(f"     Tono: {niche['tono']}")
            print(f"     Ejemplo hook: \"{niche['hooks'][0]}\"")
            print()
        return

    if args.voice:
        GEMINI_TTS_VOICE = args.voice
    
    if args.short:
        IS_SHORT = True
        print("📱 Modo SHORT activado (9:16 vertical, ≤60s)")

    if args.quality:
        VIDEO_QUALITY = args.quality
    
    TEXT_MODEL = args.model
    
    if args.eleven:
        TTS_ENGINE = "eleven"
    if args.eleven_voice:
        ELEVEN_VOICE_ID = args.eleven_voice
    
    if args.gemini_images:
        IMAGE_ENGINE = "gemini_web"
        print("🌐 Modo GEMINI WEB activado para imágenes (Playwright browser)")
    
    if args.gemini_web_story:
        TEXT_MODEL = "gemini_web"
        print("🌐 Modo GEMINI WEB activado para historia (Playwright browser)")
    
    # Validar nicho si se especificó
    if args.niche and args.niche not in CONTENT_NICHES:
        print(f"❌ Nicho '{args.niche}' no existe. Usa --list-niches para ver opciones.")
        sys.exit(1)
    
    if TEXT_MODEL == "gemini_web":
        model_label = "Gemini Web (Playwright)"
    else:
        model_label = f"LiteLLM ({TEXT_MODEL})"
    tts_label = "ElevenLabs" if TTS_ENGINE == "eleven" else f"Gemini TTS ({GEMINI_TTS_VOICE})"
    img_engine_label = "Gemini Web (Playwright)" if IMAGE_ENGINE == "gemini_web" else "SDXL Local"
    print(f"\n🎬 VIRAL CONTENT FACTORY v2.0")
    print(f"{'─'*40}")
    print(f"📺 Canal: {CHANNEL_NAME}")
    print(f"🎬 Calidad: {VIDEO_QUALITY.upper()}")
    print(f"📝 Historias: {args.count}")
    print(f"🎙️ TTS: {tts_label}")
    print(f"🧠 Texto: {model_label}")
    print(f"🎨 Imágenes: {img_engine_label}")
    print(f"🎯 Nicho: {args.niche or 'AUTO (aleatorio viral)'}")
    if args.duration:
        print(f"⏱️ Duración: {args.duration} min (~{int(args.duration*135)} palabras)")
    if args.context:
        print(f"💡 Contexto: {args.context}")
    print(f"{'─'*40}")

    try:
        create_creepypasta(num_stories=args.count, context=args.context, 
                          duration_min=args.duration, niche_name=args.niche)
    except KeyboardInterrupt:
        print("\n\n⚠️ Proceso interrumpido")
        sys.exit(1)


if __name__ == "__main__":
    main()
