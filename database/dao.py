import mysql.connector
import logging
import bcrypt
from datetime import datetime, timedelta
from database.conexion_db import conectar_db

class BaseDAO:
    def get_connection(self):
        conn = conectar_db()
        if not conn:
            raise Exception("No se pudo obtener una conexión a la base de datos.")
        return conn

class UsuariosDAO(BaseDAO):
    def autenticar(self, email, password):
        try:
            with self.get_connection() as conn:
                if not conn: return None
                
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT id_usuario, nombre, contrasena FROM usuarios WHERE email = %s", (email,))
                usuario = cursor.fetchone()
                cursor.close()
                
                if not usuario:
                    return None

                stored_pass = usuario['contrasena']
                login_exitoso = False
                migrar_a_hash = False

                # 1. Validar como Hash (bcrypt)
                if stored_pass.startswith('$2b$'):
                    if bcrypt.checkpw(password.encode('utf-8'), stored_pass.encode('utf-8')):
                        login_exitoso = True
                # 2. Validar como Texto Plano y migrar
                elif stored_pass == password:
                    login_exitoso = True
                    migrar_a_hash = True

                if login_exitoso:
                    if migrar_a_hash:
                        try:
                            nuevo_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                            # Usamos la misma conexión para la transacción de actualización
                            c_up = conn.cursor()
                            c_up.execute("UPDATE usuarios SET contrasena=%s WHERE id_usuario=%s", (nuevo_hash, usuario['id_usuario']))
                            conn.commit()
                            c_up.close()
                            logging.info(f"Seguridad: Contraseña del usuario {email} migrada a bcrypt.")
                        except Exception as e:
                            logging.error(f"Error en la migración de contraseña para {email}: {e}")

                    del usuario['contrasena']
                    return usuario
                return None
        except Exception as e:
            logging.error(f"Error en autenticación: {e}", exc_info=True)
            return None

    def registrar(self, nombre, email, password):
        try:
            with self.get_connection() as conn:
                if not conn:
                    return False, "No se pudo conectar a la base de datos."
                
                cursor = conn.cursor()
                
                # 1. Verificar si el email ya existe
                cursor.execute("SELECT id_usuario FROM usuarios WHERE email = %s", (email,))
                if cursor.fetchone():
                    return False, "Este correo electrónico ya está registrado."

                # Hashing de contraseña antes de guardar
                hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                sql = "INSERT INTO usuarios (nombre, email, contrasena) VALUES (%s, %s, %s)"
                cursor.execute(sql, (nombre, email, hashed))
                
                # 2. Onboarding: Crear eventos de bienvenida
                nuevo_id = cursor.lastrowid
                self._crear_eventos_bienvenida(conn, nuevo_id)
                
                conn.commit()
                cursor.close()
                return True, "Usuario registrado correctamente."
        except mysql.connector.Error as e:
            raise e
        except Exception as e:
            logging.error(f"Error al registrar usuario: {e}", exc_info=True)
            return False, f"Ocurrió un error inesperado: {e}"

    def _crear_eventos_bienvenida(self, conn, usuario_id):
        """Crea eventos iniciales para que el nuevo usuario no vea el calendario vacío."""
        try:
            cursor = conn.cursor()
            # Obtener IDs de colores (fallback a 1 si no existen)
            cursor.execute("SELECT id_color, nombre FROM colores")
            colores = {row[1].lower(): row[0] for row in cursor.fetchall()}
            def get_col(name): return colores.get(name, 1)

            hoy = datetime.now()
            manana = hoy + timedelta(days=1)
            pasado = hoy + timedelta(days=2)

            eventos = [
                ("☕ Café de Bienvenida", "Configurar perfil y explorar la app.", manana.replace(hour=10, minute=0), "naranja"),
                ("🚀 Revisión de Objetivos", "Primera planificación semanal.", manana.replace(hour=12, minute=0), "azul"),
                ("🎉 Lanzamiento", "Celebrar el inicio del uso del calendario.", pasado.replace(hour=16, minute=0), "verde")
            ]

            sql = "INSERT INTO eventos (usuario_id, titulo, descripcion, fecha_inicio, color_id, es_importante, minutos_aviso) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            for titulo, desc, fecha, color_nombre in eventos:
                cursor.execute(sql, (usuario_id, titulo, desc, fecha, get_col(color_nombre), False, 0))
            
            cursor.close()
        except Exception as e:
            logging.error(f"Error creando eventos de bienvenida: {e}", exc_info=True)

    def login_invitado(self):
        """Inicia sesión como invitado. Si es nuevo o no tiene eventos, carga la demo de Feb 2026."""
        try:
            with self.get_connection() as conn:
                if not conn: return None
                cursor = conn.cursor(dictionary=True)
                email_demo = "invitado@demo.com"
                
                # 1. Buscamos si ya existe el usuario invitado
                cursor.execute("SELECT id_usuario, nombre FROM usuarios WHERE email=%s", (email_demo,))
                usuario = cursor.fetchone()

                if not usuario:
                    # 2. Si no existe, lo creamos con una contraseña simple
                    hashed_demo = bcrypt.hashpw("demo".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    cursor.execute("INSERT INTO usuarios (nombre, email, contrasena) VALUES (%s, %s, %s)", 
                                   ("Invitado", email_demo, hashed_demo))
                    conn.commit()
                    usuario = {'id_usuario': cursor.lastrowid, 'nombre': 'Invitado'}
                
                cursor.close()
                
                # 3. Verificar y cargar demo (Lógica centralizada)
                self._verificar_y_cargar_demo(conn, usuario['id_usuario'])
                
                return usuario
        except Exception as e:
            logging.error(f"Error en login de invitado: {e}", exc_info=True)
            return None

    def _verificar_y_cargar_demo(self, conn, id_usuario):
        """Verifica si el usuario tiene eventos. Si no, carga los eventos de la captura (Feb 2026)."""
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM eventos WHERE usuario_id = %s", (id_usuario,))
            count = cursor.fetchone()[0]

            if count == 0:
                # Cargar mapa de colores
                cursor.execute("SELECT id_color, nombre FROM colores")
                colores_db = {row[1].lower(): row[0] for row in cursor.fetchall()}
                
                def get_cid(nombre):
                    key = nombre.lower()
                    if "blanco" in key or "gris" in key: key = "gris"
                    return colores_db.get(key, 1)

                # Eventos Feb 2026
                eventos_demo = [
                    # Viernes 6
                    ("Reunión equipo producción", "Cian", datetime(2026, 2, 6, 9, 30)),
                    ("Preparar presupuesto evento", "Amarillo", datetime(2026, 2, 6, 12, 0)),
                    ("Rodaje spot publicitario", "Gris", datetime(2026, 2, 6, 16, 0)),
                    # Lunes 9
                    ("Inventario material técnico", "Verde", datetime(2026, 2, 9, 9, 0)),
                    ("Planificación personal evento", "Rosa", datetime(2026, 2, 9, 11, 0)),
                    ("Llamada cliente", "Rojo", datetime(2026, 2, 9, 16, 0)),
                    # Martes 10
                    ("Confirmar horarios staff", "Amarillo", datetime(2026, 2, 10, 10, 0)),
                    ("Supervisión técnica", "Amarillo", datetime(2026, 2, 10, 12, 0)),
                    ("Revisión checklist", "Gris", datetime(2026, 2, 10, 15, 0)),
                    # Miércoles 11
                    ("🎂 Cumpleaños Ana", "Cian", datetime(2026, 2, 11, 9, 0)),
                    ("Evento corporativo", "Verde", datetime(2026, 2, 11, 14, 0)),
                    ("Informe final", "Naranja", datetime(2026, 2, 11, 17, 0)),
                    # Jueves 12
                    ("Cita médica", "Rojo", datetime(2026, 2, 12, 10, 0)),
                    ("Viaje Madrid", "Cian", datetime(2026, 2, 12, 16, 0)),
                ]

                sql = "INSERT INTO eventos (usuario_id, titulo, descripcion, fecha_inicio, color_id, es_importante, minutos_aviso) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                for titulo, color, fecha in eventos_demo:
                    cursor.execute(sql, (id_usuario, titulo, "Evento Demo", fecha, get_cid(color), False, 0))
                
                conn.commit()
            
            cursor.close()
        except Exception as e:
            logging.error(f"Error cargando demo: {e}", exc_info=True)

    def obtener_primer_usuario(self):
        try:
            with self.get_connection() as conn:
                if not conn: return None
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT id_usuario, nombre FROM usuarios LIMIT 1")
                usuario = cursor.fetchone()
                cursor.close()
                return usuario
        except Exception as e:
            logging.error(f"Error obteniendo primer usuario: {e}", exc_info=True)
            return None

class ColoresDAO(BaseDAO):
    def obtener_id_por_hex(self, hex_code):
        try:
            with self.get_connection() as conn:
                if not conn: return None
                cursor = conn.cursor()
                cursor.execute("SELECT id_color FROM colores WHERE UPPER(codigo) = %s LIMIT 1", (hex_code.upper(),))
                result = cursor.fetchone()
                cursor.close()
                return result[0] if result else None
        except Exception as e:
            logging.error(f"Error obteniendo id de color: {e}", exc_info=True)
            return None
            
    def sincronizar(self, mapa_colores):
        try:
            with self.get_connection() as conn:
                if not conn: return
                cursor = conn.cursor()
                for nombre, hex_code in mapa_colores.items():
                    cursor.execute("SELECT id_color FROM colores WHERE codigo = %s", (hex_code,))
                    if not cursor.fetchone():
                        cursor.execute("INSERT INTO colores (nombre, codigo) VALUES (%s, %s)", (nombre, hex_code))
                conn.commit()
                cursor.close()
        except Exception as e:
            logging.error(f"Error sincronizando colores: {e}", exc_info=True)

class EventosDAO(BaseDAO):
    def obtener_por_usuario(self, usuario_id):
        try:
            with self.get_connection() as conn:
                if not conn: return None
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT e.id_evento, e.titulo, e.descripcion, e.fecha_inicio, c.codigo AS color_db_string, e.archivo_adjunto, e.es_importante, e.minutos_aviso
                    FROM eventos e
                    JOIN colores c ON e.color_id = c.id_color
                    WHERE e.usuario_id=%s
                    ORDER BY e.fecha_inicio ASC, e.titulo ASC, e.id_evento ASC
                """, (usuario_id,))
                eventos = cursor.fetchall()
                cursor.close()
                return eventos
        except mysql.connector.Error as e:
            logging.error(f"Error SQL cargando eventos: {e}", exc_info=True)
            raise e

    def guardar(self, datos, modo='crear', id_evento=None):
        try:
            with self.get_connection() as conn:
                if not conn: raise Exception("No hay conexión con la base de datos")
                cursor = conn.cursor()
                if modo == 'crear':
                    cursor.execute("""
                        INSERT INTO eventos (usuario_id, titulo, descripcion, fecha_inicio, color_id, archivo_adjunto, es_importante, minutos_aviso)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (datos['usuario_id'], datos['titulo'], datos['descripcion'], datos['fecha_inicio'], datos['color_id'], datos['archivo_adjunto'], datos['es_importante'], datos['minutos_aviso']))
                else:
                    cursor.execute("""
                        UPDATE eventos 
                        SET titulo = %s, descripcion = %s, color_id = %s, archivo_adjunto = %s, fecha_inicio = %s, es_importante = %s, minutos_aviso = %s
                        WHERE id_evento = %s
                    """, (datos['titulo'], datos['descripcion'], datos['color_id'], datos['archivo_adjunto'], datos['fecha_inicio'], datos['es_importante'], datos['minutos_aviso'], id_evento))
                conn.commit()
                cursor.close()
        except Exception as e:
            logging.error(f"Error guardando evento: {e}", exc_info=True)
            raise e

    def eliminar(self, id_evento):
        try:
            with self.get_connection() as conn:
                if not conn: raise Exception("No hay conexión")
                cursor = conn.cursor()
                cursor.execute("DELETE FROM eventos WHERE id_evento = %s", (id_evento,))
                conn.commit()
                cursor.close()
        except Exception as e:
            logging.error(f"Error eliminando evento: {e}", exc_info=True)
            raise e

    def actualizar_fecha_evento_con_ripple(self, id_evento, nueva_fecha, lista_eventos_posteriores, indice_inicio):
        """
        Actualiza la fecha de un evento y aplica un "efecto dominó" a los eventos
        siguientes para evitar colisiones, todo dentro de una transacción.
        """
        try:
            with self.get_connection() as conn:
                if not conn:
                    raise Exception("No hay conexión con la base de datos para la actualización.")
                
                cursor = conn.cursor()
                # 1. Actualizar el evento principal que se movió
                cursor.execute("UPDATE eventos SET fecha_inicio = %s WHERE id_evento = %s", (nueva_fecha, id_evento))
                
                # 2. Efecto Dominó (Ripple): Verificar colisiones y empujar eventos siguientes
                tiempo_actual = nueva_fecha
                for i in range(indice_inicio, len(lista_eventos_posteriores)):
                    ev = lista_eventos_posteriores[i]
                    
                    if ev['fecha_inicio'] <= tiempo_actual:
                        tiempo_actual += timedelta(minutes=1) # Empujar 1 minuto
                        cursor.execute("UPDATE eventos SET fecha_inicio = %s WHERE id_evento = %s", (tiempo_actual, ev['id_evento']))
                    else:
                        break # No hay más colisiones, el efecto dominó termina

                conn.commit()
                cursor.close()
        except Exception as e:
            logging.error(f"Error en ripple update: {e}", exc_info=True)
            raise e

    def verificar_columnas(self):
        try:
            with self.get_connection() as conn:
                if conn:
                    cursor = conn.cursor()
                    try: cursor.execute("ALTER TABLE eventos ADD COLUMN es_importante BOOLEAN DEFAULT FALSE")
                    except: pass
                    try: cursor.execute("ALTER TABLE eventos ADD COLUMN minutos_aviso INT DEFAULT 0")
                    except: pass
                    conn.commit()
                    cursor.close()
        except Exception as e:
            logging.warning(f"No se pudieron verificar/añadir columnas: {e}")