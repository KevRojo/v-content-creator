#!/usr/bin/env python3
"""
🎬 V-Content Creator — GUI (PyQt5)
Interfaz gráfica para vcontent_creator.py
"""

import sys
import os
import io
import threading

# Force 1.5x scale for 4K displays — MUST be set before importing PyQt5
os.environ["QT_SCALE_FACTOR"] = "1.5"

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox,
    QCheckBox, QPushButton, QTextEdit, QGroupBox, QGridLayout,
    QFrame, QSplitter, QProgressBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor, QTextCursor, QIcon

# Fix encoding for Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Estilos ────────────────────────────────────────────────────────────────────
DARK_STYLE = """
QMainWindow {
    background-color: #1a1a2e;
}
QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
    font-family: 'Segoe UI', 'Arial', sans-serif;
    font-size: 16px;
}
QGroupBox {
    border: 1px solid #2d2d50;
    border-radius: 10px;
    margin-top: 16px;
    padding-top: 24px;
    font-weight: bold;
    font-size: 18px;
    color: #a78bfa;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
}
QComboBox {
    background-color: #16213e;
    border: 1px solid #2d2d50;
    border-radius: 6px;
    padding: 8px 14px;
    min-height: 38px;
    font-size: 15px;
    color: #e0e0e0;
}
QComboBox:hover {
    border-color: #a78bfa;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #16213e;
    border: 1px solid #2d2d50;
    selection-background-color: #a78bfa;
    color: #e0e0e0;
}
QLineEdit {
    background-color: #16213e;
    border: 1px solid #2d2d50;
    border-radius: 6px;
    padding: 8px 14px;
    min-height: 38px;
    font-size: 15px;
    color: #e0e0e0;
}
QLineEdit:focus {
    border-color: #a78bfa;
}
QSpinBox, QDoubleSpinBox {
    background-color: #16213e;
    border: 1px solid #2d2d50;
    border-radius: 6px;
    padding: 8px 14px;
    min-height: 38px;
    font-size: 15px;
    color: #e0e0e0;
}
QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #a78bfa;
}
QCheckBox {
    spacing: 8px;
    color: #e0e0e0;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #2d2d50;
    border-radius: 4px;
    background-color: #16213e;
}
QCheckBox::indicator:checked {
    background-color: #a78bfa;
    border-color: #a78bfa;
}
QPushButton {
    background-color: #a78bfa;
    color: #1a1a2e;
    border: none;
    border-radius: 10px;
    padding: 14px 30px;
    font-weight: bold;
    font-size: 17px;
    min-height: 48px;
}
QPushButton:hover {
    background-color: #c4a7ff;
}
QPushButton:pressed {
    background-color: #8b5cf6;
}
QPushButton:disabled {
    background-color: #3d3d5c;
    color: #6b6b8a;
}
QPushButton#stopBtn {
    background-color: #ef4444;
    color: white;
}
QPushButton#stopBtn:hover {
    background-color: #f87171;
}
QTextEdit {
    background-color: #0f0f1a;
    border: 1px solid #2d2d50;
    border-radius: 8px;
    padding: 10px;
    font-family: 'Cascadia Code', 'Consolas', 'Courier New', monospace;
    font-size: 14px;
    color: #c8c8e0;
    selection-background-color: #a78bfa;
}
QLabel {
    color: #b0b0cc;
    font-size: 15px;
}
QLabel#headerLabel {
    font-size: 30px;
    font-weight: bold;
    color: #a78bfa;
}
QLabel#subLabel {
    font-size: 12px;
    color: #6b6b8a;
}
QProgressBar {
    border: 1px solid #2d2d50;
    border-radius: 4px;
    background-color: #16213e;
    text-align: center;
    color: #e0e0e0;
    min-height: 8px;
    max-height: 8px;
}
QProgressBar::chunk {
    background-color: #a78bfa;
    border-radius: 3px;
}
QSplitter::handle {
    background-color: #2d2d50;
    height: 2px;
}
"""


class GenerationWorker(QThread):
    """Ejecuta claude_director.py como SUBPROCESS para aislar la GUI de crashes."""
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)

    def __init__(self, params):
        super().__init__()
        self.params = params
        self.process = None

    def run(self):
        import subprocess

        # Construir el comando
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vcontent_creator.py")
        cmd = [sys.executable, script]

        p = self.params
        cmd += ["--count", str(p['count'])]
        cmd += ["--quality", p['quality']]
        cmd += ["--model", p['model']]
        cmd += ["--voice", p['voice']]

        if p.get('context'):
            cmd += ["--context", p['context']]
        if p.get('duration'):
            cmd += ["--duration", str(p['duration'])]
        if p.get('niche'):
            cmd += ["--niche", p['niche']]
        if p.get('short'):
            cmd += ["--short"]
        if p.get('tts_engine') == "eleven":
            cmd += ["--eleven"]
        if p.get('gemini_images'):
            cmd += ["--gemini-images"]
        if p.get('gemini_web_story'):
            cmd += ["--gemini-web-story"]

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                cwd=os.path.dirname(script)
            )

            # Leer output línea por línea en tiempo real
            for line in self.process.stdout:
                line = line.rstrip('\n\r')
                if line:
                    self.output_signal.emit(line)

            self.process.wait()
            self.finished_signal.emit(self.process.returncode == 0)

        except Exception as e:
            self.output_signal.emit(f"\n❌ ERROR: {e}")
            self.finished_signal.emit(False)

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()


class ViralFactoryGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.setWindowTitle("🎬 V-Content Creator")
        self.setMinimumSize(900, 900)
        self.resize(1050, 1000)
        self.init_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 12, 16, 12)

        # ── Header ─────────────────────────────────────────
        header = QLabel("🎬 V-Content Creator")
        header.setObjectName("headerLabel")
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)

        sub = QLabel("AI-powered viral video content factory · Gemini + SDXL + TTS")
        sub.setObjectName("subLabel")
        sub.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(sub)

        # ── Splitter: Config arriba, Console abajo ─────────
        splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(splitter, 1)

        # === Panel de configuración ===
        config_widget = QWidget()
        config_layout = QVBoxLayout(config_widget)
        config_layout.setContentsMargins(0, 0, 0, 0)

        # ── Grupo: Contenido ───────────────────────────────
        content_group = QGroupBox("📝 Contenido")
        content_grid = QGridLayout(content_group)
        content_grid.setSpacing(8)

        # Nicho
        content_grid.addWidget(QLabel("Nicho:"), 0, 0)
        self.niche_combo = QComboBox()
        self.niche_combo.addItem("🎲 Aleatorio (viral)", "")
        # Importar nichos del módulo
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from vcontent_creator import CONTENT_NICHES
            for key, val in CONTENT_NICHES.items():
                self.niche_combo.addItem(f"{val['nombre']}", key)
        except ImportError:
            for n in ["misterio_real", "confesiones", "suspenso_cotidiano", "ciencia_ficcion",
                       "drama_humano", "terror_psicologico", "folklore_latam", "venganza",
                       "supervivencia", "misterio_digital"]:
                self.niche_combo.addItem(n, n)
        content_grid.addWidget(self.niche_combo, 0, 1, 1, 3)

        # Contexto
        content_grid.addWidget(QLabel("Contexto:"), 1, 0)
        self.context_input = QLineEdit()
        self.context_input.setPlaceholderText("Ej: historia de inmigración, un robo en Santo Domingo...")
        content_grid.addWidget(self.context_input, 1, 1, 1, 3)

        # Count + Duration
        content_grid.addWidget(QLabel("Historias:"), 2, 0)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 10)
        self.count_spin.setValue(1)
        content_grid.addWidget(self.count_spin, 2, 1)

        content_grid.addWidget(QLabel("Duración (min):"), 2, 2)
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(0, 15)
        self.duration_spin.setValue(0)
        self.duration_spin.setSingleStep(0.5)
        self.duration_spin.setSpecialValueText("Auto")
        content_grid.addWidget(self.duration_spin, 2, 3)

        config_layout.addWidget(content_group)

        # ── Grupo: Producción ──────────────────────────────
        prod_group = QGroupBox("⚙️ Producción")
        prod_grid = QGridLayout(prod_group)
        prod_grid.setSpacing(8)

        # Model
        prod_grid.addWidget(QLabel("Modelo texto:"), 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.addItem("✨ Gemini (gemini-3-flash)", "gemini")
        self.model_combo.addItem("🌙 Kimi (moonshot)", "kimi")
        prod_grid.addWidget(self.model_combo, 0, 1)

        # Voice
        prod_grid.addWidget(QLabel("Voz TTS:"), 0, 2)
        self.voice_combo = QComboBox()
        voices = ["Charon", "Fenrir", "Orus", "Kore", "Enceladus", "Umbriel",
                   "Iapetus", "Zephyr", "Puck", "Leda", "Aoede"]
        for v in voices:
            self.voice_combo.addItem(v, v)
        prod_grid.addWidget(self.voice_combo, 0, 3)

        # Quality
        prod_grid.addWidget(QLabel("Calidad:"), 1, 0)
        self.quality_combo = QComboBox()
        self.quality_combo.addItem("🔥 High", "high")
        self.quality_combo.addItem("⚡ Medium", "medium")
        self.quality_combo.addItem("💨 Low", "low")
        self.quality_combo.addItem("🏎️ Minimal", "minimal")
        prod_grid.addWidget(self.quality_combo, 1, 1)

        # Short mode
        self.short_check = QCheckBox("📱 Modo Short (9:16)")
        prod_grid.addWidget(self.short_check, 1, 2)

        # ElevenLabs TTS
        self.eleven_check = QCheckBox("🔊 ElevenLabs TTS")
        prod_grid.addWidget(self.eleven_check, 1, 3)

        # Gemini Images (row 2)
        self.gemini_images_check = QCheckBox("🖼️ Gemini Images")
        prod_grid.addWidget(self.gemini_images_check, 2, 2)

        # Gemini Web Story (row 2)
        self.gemini_web_story_check = QCheckBox("🧠 Gemini Web History")
        prod_grid.addWidget(self.gemini_web_story_check, 2, 3)

        config_layout.addWidget(prod_group)

        # ── Botones ────────────────────────────────────────
        btn_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("🚀  GENERAR")
        self.start_btn.clicked.connect(self.start_generation)
        btn_layout.addWidget(self.start_btn, 3)

        self.stop_btn = QPushButton("⏹  DETENER")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_generation)
        btn_layout.addWidget(self.stop_btn, 1)

        config_layout.addLayout(btn_layout)

        # Progress bar (indeterminate while running)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setVisible(False)
        config_layout.addWidget(self.progress)

        splitter.addWidget(config_widget)

        # === Panel de consola ===
        console_widget = QWidget()
        console_layout = QVBoxLayout(console_widget)
        console_layout.setContentsMargins(0, 4, 0, 0)

        console_header = QHBoxLayout()
        console_label = QLabel("📟 Consola")
        console_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #a78bfa;")
        console_header.addWidget(console_label)
        console_header.addStretch()
        
        self.clear_btn = QPushButton("Limpiar")
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d2d50; color: #b0b0cc; 
                padding: 4px 12px; font-size: 11px; min-height: 24px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #3d3d5c; }
        """)
        self.clear_btn.clicked.connect(lambda: self.console.clear())
        console_header.addWidget(self.clear_btn)
        console_layout.addLayout(console_header)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Cascadia Code", 13))
        console_layout.addWidget(self.console)

        splitter.addWidget(console_widget)
        splitter.setSizes([400, 520])

    def start_generation(self):
        # Recoger parámetros
        params = {
            'niche': self.niche_combo.currentData(),
            'context': self.context_input.text().strip(),
            'count': self.count_spin.value(),
            'duration': self.duration_spin.value() if self.duration_spin.value() > 0 else None,
            'model': self.model_combo.currentData(),
            'voice': self.voice_combo.currentData(),
            'quality': self.quality_combo.currentData(),
            'short': self.short_check.isChecked(),
            'tts_engine': 'eleven' if self.eleven_check.isChecked() else 'gemini',
            'gemini_images': self.gemini_images_check.isChecked(),
            'gemini_web_story': self.gemini_web_story_check.isChecked(),
        }

        self.console.clear()
        self.log("═" * 50)
        self.log("🎬 INICIANDO GENERACIÓN...")
        self.log(f"   Nicho: {params['niche'] or 'Aleatorio'}")
        self.log(f"   Modelo: {params['model']}")
        self.log(f"   Voz: {params['voice']}")
        self.log(f"   Calidad: {params['quality']}")
        if params['context']:
            self.log(f"   Contexto: {params['context']}")
        if params['duration']:
            self.log(f"   Duración: {params['duration']} min")
        self.log("═" * 50 + "\n")

        # UI state
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.setVisible(True)

        # Launch worker
        self.worker = GenerationWorker(params)
        self.worker.output_signal.connect(self.log)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def stop_generation(self):
        if self.worker and self.worker.isRunning():
            self.log("\n⚠️ Deteniendo... (puede tardar un momento)")
            self.worker.terminate()
            self.worker.wait(3000)
            self.on_finished(False)

    def on_finished(self, success):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress.setVisible(False)
        if success:
            self.log("\n✅ ¡GENERACIÓN COMPLETADA!")
        else:
            self.log("\n⚠️ Generación terminada.")

    MAX_CONSOLE_LINES = 2000

    def log(self, text):
        # Filtrar líneas de ruido (progress bars tqdm, warnings de torch)
        if any(c in text for c in '█▉▊▋▌▍▎▏'):
            return  # Progress bars de SDXL/tqdm — no mostrar
        if 'FutureWarning' in text or 'deprecat' in text.lower():
            return  # Warnings de torch/diffusers
        
        self.console.moveCursor(QTextCursor.End)
        self.console.insertPlainText(text + "\n")
        
        # Limitar líneas para evitar leak de memoria
        doc = self.console.document()
        if doc.blockCount() > self.MAX_CONSOLE_LINES:
            cursor = QTextCursor(doc.begin())
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, 
                              doc.blockCount() - self.MAX_CONSOLE_LINES)
            cursor.removeSelectedText()
        
        self.console.moveCursor(QTextCursor.End)
        self.console.ensureCursorVisible()


def main():
    # Asegurar que el directorio de trabajo es el del script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    sys.path.insert(0, script_dir)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)

    window = ViralFactoryGUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
