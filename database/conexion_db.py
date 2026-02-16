import mysql.connector
from dotenv import load_dotenv
import os
import logging
import sys

# --- FIX CRÍTICO PARA PYINSTALLER ---
# Esto evita el error "No localization support for language 'eng'" cuando falla la conexión.
# Forzamos a PyInstaller a incluir el archivo de mensajes de error explícitamente.
try:
    import mysql.connector.locales.eng.client_error
except ImportError:
    pass

load_dotenv()

def resource_path(relative_path):
    """ Obtiene la ruta absoluta al recurso, funciona para dev y para PyInstaller """
    try:
        # PyInstaller crea una carpeta temporal en _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def conectar_db():
    """Establece y devuelve una conexión simple y segura a la base de datos."""
    try:
        # Leemos la contraseña usando DB_PASS, como está en tu .env
        password = os.getenv("DB_PASS")
        user = os.getenv("DB_USER")
        host = os.getenv("DB_HOST")
        
        if not all([password, user, host]):
            logging.error("Faltan variables de entorno críticas (DB_USER, DB_PASS o DB_HOST).")
            return None

        port_int = int(os.getenv("DB_PORT", "3306"))
        
        conn = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=os.getenv("DB_NAME"),
            port=port_int,
            # --- CONEXIÓN SEGURA PARA LA NUBE ---
            ssl_ca=resource_path('ca.pem'),
            ssl_verify_cert=True,
            use_pure=True  # Forzar conector Pure Python para máxima compatibilidad
        )
        return conn
    except Exception as err:
        logging.error(f"Error fatal al conectar a la base de datos: {err}", exc_info=True)
        return None

def verificar_y_crear_tablas_base():
    """Asegura que las tablas esenciales existan, sin modificar datos."""
    try:
        with conectar_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS colores (
                    id_color INT AUTO_INCREMENT PRIMARY KEY,
                    nombre VARCHAR(50) NOT NULL,
                    codigo VARCHAR(7) NOT NULL UNIQUE
                ) ENGINE=InnoDB;
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id_usuario INT AUTO_INCREMENT PRIMARY KEY,
                    nombre VARCHAR(100) NOT NULL,
                    email VARCHAR(100) NOT NULL UNIQUE,
                    contrasena VARCHAR(255) NOT NULL
                ) ENGINE=InnoDB;
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS eventos (
                    id_evento INT AUTO_INCREMENT PRIMARY KEY,
                    usuario_id INT,
                    titulo VARCHAR(255) NOT NULL,
                    descripcion TEXT,
                    fecha_inicio DATETIME NOT NULL,
                    color_id INT,
                    FOREIGN KEY (usuario_id) REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
                    FOREIGN KEY (color_id) REFERENCES colores(id_color)
                ) ENGINE=InnoDB;
            """)
            conn.commit()
            cursor.close()
            logging.info("Verificación de tablas base completada.")
    except Exception as e:
        logging.error(f"No se pudieron crear las tablas base: {e}", exc_info=True)
