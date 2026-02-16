import os.path
import datetime
import logging
from database.conexion_db import conectar_db

# Intentamos importar las librerías de Google
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    LIBRERIAS_GOOGLE_OK = True
except ImportError:
    LIBRERIAS_GOOGLE_OK = False

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def sincronizar_eventos(usuario_id):
    """
    Conecta con Google Calendar y descarga los próximos 10 eventos.
    """
    # 1. Verificar librerías
    if not LIBRERIAS_GOOGLE_OK:
        return (False, "Error de configuración: Faltan las librerías de Google.\nPor favor, contacta con soporte técnico.")

    creds = None
    # 2. Cargar credenciales existentes (token.json)
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # 3. Si no hay credenciales válidas, iniciar login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                if os.path.exists('token.json'): os.remove('token.json')
                return (False, "La sesión de Google ha caducado.\nPor favor, intenta importar de nuevo para reconectar.")
        else:
            if not os.path.exists('credentials.json'):
                return (False, "No se encontró el archivo de configuración 'credentials.json'.\nAsegúrate de tenerlo en la carpeta del programa.")
            
            try:
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as e:
                logging.warning(f"Fallo autenticación Google: {e}")
                return (False, f"No se pudo iniciar sesión en Google.\nRevisa tu conexión o cancelaste el proceso.\nDetalle: {e}")
        
        # Guardar credenciales para la próxima
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    conn = None
    try:
        # 4. Conectar a la API
        service = build('calendar', 'v3', credentials=creds)

        # Obtener próximos 10 eventos
        now = datetime.datetime.utcnow().isoformat() + 'Z' 
        events_result = service.events().list(calendarId='primary', timeMin=now,
                                              maxResults=10, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])

        if not events:
            return (True, "No se encontraron eventos próximos en Google.")

        # 5. Guardar en Base de Datos Local
        conn = conectar_db()
        if not conn: return (False, "No se pudo conectar a la base de datos local para guardar los eventos.")
        
        cursor = conn.cursor()
        count = 0
        
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'Sin título')
            
            # Formato fecha: 2023-01-01T10:00:00Z -> 2023-01-01 10:00:00
            fecha_mysql = start.replace('T', ' ').split('+')[0].split('Z')[0]
            
            # Evitar duplicados (mismo título y fecha)
            cursor.execute("SELECT id_evento FROM eventos WHERE usuario_id=%s AND titulo=%s AND fecha_inicio LIKE %s", 
                           (usuario_id, summary, fecha_mysql + '%'))
            
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO eventos (usuario_id, titulo, descripcion, fecha_inicio, color_id)
                    VALUES (%s, %s, %s, %s, 1)
                """, (usuario_id, summary, "Importado de G-Cal", fecha_mysql))
                count += 1
        
        conn.commit()
        cursor.close()
        
        return (True, f"Sincronización completada: {count} eventos nuevos.")

    except Exception as e:
        logging.error(f"Error crítico en API Google Calendar: {e}", exc_info=True)
        return (False, f"Error de comunicación con Google Calendar.\nRevisa tu conexión a internet.\nDetalle: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()