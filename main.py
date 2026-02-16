import sys
import logging
import os
import traceback
import threading
from PyQt5.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt
from ui.login import VentanaLogin
from ui.ventana_principal import VentanaPrincipal
from database.dao import ColoresDAO, UsuariosDAO
from utils.config import COLORES_MAP
from database.conexion_db import conectar_db, verificar_y_crear_tablas_base

# Configuración Global de Logging
logging.basicConfig(
    filename='minicalendar.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def resource_path(relative_path):
    """ Obtiene la ruta absoluta al recurso, funciona para dev y para PyInstaller """
    try:
        # PyInstaller crea una carpeta temporal en _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def crear_splash_pixmap():
    """Genera un QPixmap para el Splash Screen programáticamente."""
    pixmap = QPixmap(450, 250)
    pixmap.fill(QColor("#2c3e50")) # Fondo oscuro elegante

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    
    # Dibujar borde
    painter.setPen(QColor("#3498db"))
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(0, 0, 449, 249)

    # Dibujar Título
    painter.setPen(QColor("white"))
    font_title = QFont("Segoe UI", 28, QFont.Bold)
    painter.setFont(font_title)
    painter.drawText(pixmap.rect().adjusted(0, -30, 0, 0), Qt.AlignCenter, "MiniCalendar")
    
    # Dibujar Subtítulo
    font_sub = QFont("Segoe UI", 12)
    painter.setFont(font_sub)
    painter.setPen(QColor("#bdc3c7"))
    painter.drawText(pixmap.rect().adjusted(0, 40, 0, 0), Qt.AlignCenter, "Tu organizador personal")

    painter.end()
    return pixmap

def verificar_conexion_db():
    """Intenta conectar a la BD y devuelve True/False."""
    conn = conectar_db()
    if conn and conn.is_connected():
        conn.close()
        return True
    return False

def sincronizar_colores_db():
    """
    Verifica que todos los colores definidos en config.py existan en la base de datos.
    Si alguno falta (como Dorado, Plateado, Bronce), lo inserta automáticamente.
    """
    dao = ColoresDAO()
    dao.sincronizar(COLORES_MAP)

def inicializacion_db_segundo_plano():
    """
    Ejecuta las tareas de inicialización de la BD que pueden ser lentas.
    Se envuelve en un try/except para capturar cualquier error en el hilo.
    """
    try:
        logging.info("Iniciando verificación de tablas y sincronización de colores...")
        verificar_y_crear_tablas_base()
        sincronizar_colores_db()
        logging.info("Inicialización de BD completada con éxito.")
    except Exception as e:
        logging.error(f"Error durante la inicialización de la BD en segundo plano: {e}", exc_info=True)


class AppController:
    """
    Clase que gestiona el flujo de ventanas para evitar variables globales.
    """
    def __init__(self):
        self.ventana_principal = None
        self.login_window = None

    def iniciar(self):
        self.mostrar_login()

    def mostrar_login(self):
        self.login_window = VentanaLogin()
        self.login_window.login_exitoso.connect(self.mostrar_principal)
        self.login_window.show()

    def mostrar_principal(self, usuario_info):
        # Aseguramos que la ventana de login se cierre correctamente antes de abrir la principal
        if self.login_window:
            self.login_window.close()

        # Guardamos la referencia de la ventana principal para que no se destruya
        self.ventana_principal = VentanaPrincipal(usuario_info)

        self.ventana_principal.logout_signal.connect(self.mostrar_login)
        self.ventana_principal.showMaximized()

        # Si el usuario es 'Invitado', personalizamos el título y mostramos el mensaje
        if usuario_info.get('nombre') == 'Invitado':
            self.ventana_principal.setWindowTitle("MiniCalendar - Modo Invitado")

if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        
        # --- SPLASH SCREEN ---
        splash_pix = crear_splash_pixmap()
        splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
        splash.show()
        splash.showMessage("Conectando con la nube...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
        app.processEvents() # Forzar renderizado inmediato
        
        # 1. VERIFICACIÓN DE CONEXIÓN
        if not verificar_conexion_db():
            splash.hide() # Ocultamos el splash para mostrar el error
            QMessageBox.critical(None, "Error Crítico de Base de Datos",
                                 "No se pudo conectar a la base de datos MySQL.\n\n"
                                 "Revisa tus credenciales en .env y el estado del servidor.\n"
                                 "Consulta 'minicalendar.log' para más detalles.")
            sys.exit(1) # Salir de forma segura si no hay conexión
        
        splash.showMessage("Sincronizando datos...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
        app.processEvents()

        # 2. CREACIÓN DE TABLAS Y SINCRONIZACIÓN (con timeout de 5 segundos)
        # Se ejecuta en un hilo para no bloquear la apertura de la UI.
        db_init_thread = threading.Thread(target=inicializacion_db_segundo_plano, daemon=True)
        db_init_thread.start()
        
        splash.showMessage("Iniciando interfaz...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
        app.processEvents()
        
        # Esperamos un máximo de 5 segundos a que termine
        db_init_thread.join(timeout=5.0)
        
        if db_init_thread.is_alive():
            logging.warning("La inicialización de la base de datos ha superado los 5 segundos. La aplicación continuará de todos modos.")
            # El hilo seguirá en segundo plano. Si termina, bien. Si no, no bloquea.

        # 3. Iniciamos el controlador de la aplicación inmediatamente
        controlador = AppController()
        controlador.iniciar()
        
        # El splash se cerrará suavemente cuando aparezca la ventana de login
        splash.finish(controlador.login_window)

        sys.exit(app.exec_())
    except Exception as e:
        logging.critical(f"ERROR FATAL INESPERADO: {e}", exc_info=True)
        traceback.print_exc()
        QMessageBox.critical(None, "Error Fatal", f"La aplicación ha encontrado un error irrecuperable y debe cerrarse.\n\nDetalle: {e}")