import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QPushButton,
    QLabel, QComboBox, QHeaderView, QMessageBox, QScrollArea, QToolTip,
    QDialog, QCheckBox, QDialogButtonBox, QApplication, QAbstractItemView, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QMimeData, QTimer
from PyQt5.QtGui import QColor, QBrush, QDrag
from datetime import datetime, timedelta
import calendar
import mysql.connector
import urllib.error
from functools import partial

from utils.ui_utils import centrar_ventana
from ui.ventana_gestionar_evento import VentanaGestionEvento
from database.dao import EventosDAO
from logic.services import ClimaService
from utils.config import CONFIGURACION, FESTIVOS_DATA, COLORES_FESTIVOS

MESES_ESPANOL = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# Santoral básico (Mes, Día): "Nombre"
SANTORAL = {
    (1, 1): "Sta. María", (1, 6): "Reyes Magos", (1, 17): "S. Antón",
    (2, 2): "Candelaria", (2, 14): "S. Valentín",
    (3, 19): "S. José", (3, 25): "Anunciación",
    (4, 23): "S. Jorge",
    (5, 1): "S. José Obrero", (5, 15): "S. Isidro",
    (6, 13): "S. Antonio", (6, 24): "S. Juan", (6, 29): "S. Pedro",
    (7, 16): "Virgen Carmen", (7, 25): "Santiago", (7, 26): "Sta. Ana",
    (8, 15): "Asunción", (8, 24): "S. Bartolomé",
    (9, 29): "S. Miguel", (10, 4): "S. Francisco", (10, 12): "Virgen Pilar",
    (11, 1): "Todos Santos", (12, 6): "S. Nicolás", (12, 8): "Inmaculada", (12, 25): "Navidad"
}

VISTAS = ["Día", "Semana", "Mes", "Año"]
MAX_EVENTOS_CELDA = 3

# --- WIDGET DE CELDA PARA VISTA MES (CON DROP) ---
class CeldaDiaWidget(QWidget):
    evento_soltado_en_celda = pyqtSignal(int, object, datetime) # id_movido, id_destino, fecha_celda

    def __init__(self, fecha, parent=None):
        super().__init__(parent)
        self.fecha = fecha
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WA_StyledBackground, True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        # Auto-scroll al arrastrar cerca de los bordes para ver eventos ocultos
        scroll_area = self.findChild(QScrollArea)
        if scroll_area:
            vbar = scroll_area.verticalScrollBar()
            y = event.pos().y()
            h = self.height()
            margin = 25 # Margen de detección (píxeles)
            step = 10   # Velocidad de scroll
            
            if y < margin:
                vbar.setValue(vbar.value() - step)
            elif y > h - margin:
                vbar.setValue(vbar.value() + step)
        
        event.accept()

    def dropEvent(self, event):
        try:
            id_evento_movido = int(event.mimeData().text())
            
            scroll_area = self.findChild(QScrollArea)
            # Si no hay scroll_area (porque no hay eventos), el destino es nulo.
            if not scroll_area:
                self.evento_soltado_en_celda.emit(id_evento_movido, None, self.fecha)
                event.acceptProposedAction()
                return

            content_widget = scroll_area.widget() # El QWidget dentro del QScrollArea
            pos_in_content = content_widget.mapFromGlobal(self.mapToGlobal(event.pos())) # Posición del drop relativa al widget de contenido

            id_evento_destino = None
            # Iteramos sobre los botones en el layout para encontrar la posición de inserción
            layout = content_widget.layout()
            if layout:
                for i in range(layout.count()):
                    item = layout.itemAt(i)
                    if item and item.widget():
                        widget = item.widget()
                        if isinstance(widget, BotonEvento):
                            # Si la posición Y del drop es menor que el centro del botón,
                            # significa que queremos insertar ANTES de este botón.
                            if pos_in_content.y() < widget.y() + widget.height() / 2:
                                id_evento_destino = widget.evento['id_evento']
                                break
            self.evento_soltado_en_celda.emit(id_evento_movido, id_evento_destino, self.fecha)
            event.acceptProposedAction()
        except (ValueError, AttributeError):
            event.ignore()

# --- CLASES PARA DRAG & DROP ---
class BotonEvento(QPushButton):
    def __init__(self, evento, titulo, parent=None):
        super().__init__(titulo, parent)
        self.evento = evento
        self.setCursor(Qt.PointingHandCursor)
        self._drag_start_pos = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_start_pos = e.pos()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and self._drag_start_pos:
            if (e.pos() - self._drag_start_pos).manhattanLength() > QApplication.startDragDistance():
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(str(self.evento['id_evento']))
                drag.setMimeData(mime)
                drag.exec_(Qt.MoveAction)
                self._drag_start_pos = None
                return
        super().mouseMoveEvent(e)

class CalendarioTable(QTableWidget):
    evento_dropped = pyqtSignal(int, int, int) # id_evento, row, col

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setMouseTracking(True)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item:
            id_evento = item.data(Qt.UserRole)
            if id_evento:
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(str(id_evento))
                drag.setMimeData(mime)
                drag.exec_(supportedActions)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        event.accept()

    def mouseMoveEvent(self, event):
        item = self.itemAt(event.pos())
        if item:
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def dropEvent(self, event):
        try:
            id_evento = int(event.mimeData().text())
            index = self.indexAt(event.pos())
            if index.isValid():
                self.evento_dropped.emit(id_evento, index.row(), index.column())
                event.accept()
        except ValueError:
            event.ignore()

# --- HILO PARA OBTENER EL CLIMA (SEVILLA) ---
class HiloClima(QThread):
    datos_clima = pyqtSignal(str, str, dict) # temp_actual, icono_actual, pronostico_diario

    def run(self):
        try:
            # Delegamos la llamada a la API al servicio
            data = ClimaService.obtener_pronostico_sevilla()
                
            # 1. Clima Actual
            temp_actual = "N/A"
            icono_actual = "❓"
            if "current_weather" in data:
                temp_actual = data["current_weather"]["temperature"]
                code = data["current_weather"]["weathercode"]
                icono_actual = self.obtener_icono(code)
            
            # 2. Pronóstico Diario (Próximos 7 días)
            pronostico = {}
            if "daily" in data:
                fechas = data["daily"]["time"]
                codigos = data["daily"]["weathercode"]
                temps = data["daily"]["temperature_2m_max"]
                temps_min = data["daily"]["temperature_2m_min"]
                
                for i in range(len(fechas)):
                    fecha = fechas[i] # Formato YYYY-MM-DD
                    icono = self.obtener_icono(codigos[i])
                    temp = temps[i]
                    temp_min = temps_min[i]
                    pronostico[fecha] = (icono, temp, temp_min)
                
            self.datos_clima.emit(str(temp_actual), icono_actual, pronostico)
        except urllib.error.URLError as e:
            logging.warning(f"Fallo de red al obtener clima: {e}")
            self.datos_clima.emit("Error", "🚫", {})
        except Exception as e:
            logging.error(f"Error procesando datos del clima: {e}", exc_info=True)
            self.datos_clima.emit("Error", "🚫", {})

    def obtener_icono(self, code):
        if code == 0: return "☀️"
        elif code in [1, 2, 3]: return "⛅"
        elif code in [45, 48]: return "🌫️"
        elif code in [51, 53, 55, 61, 63, 65, 80, 81, 82]: return "🌧️"
        elif code in [71, 73, 75, 77, 85, 86]: return "❄️"
        elif code in [95, 96, 99]: return "⛈️"
        return "❓"

# --- HILO PARA IMPORTAR GOOGLE CALENDAR ---
class HiloGoogle(QThread):
    resultado = pyqtSignal(bool, str)

    def __init__(self, usuario_id):
        super().__init__()
        self.usuario_id = usuario_id

    def run(self):
        try:
            from logic.google_calendar import sincronizar_eventos
            exito, mensaje = sincronizar_eventos(self.usuario_id)
            self.resultado.emit(exito, mensaje)
        except Exception as e:
            logging.error(f"Excepción en HiloGoogle: {e}", exc_info=True)
            self.resultado.emit(False, f"Error inesperado durante la sincronización: {str(e)}")

class VentanaPrincipal(QWidget):
    logout_signal = pyqtSignal()

    def __init__(self, usuario_info):
        super().__init__()
        self.usuario = usuario_info
        self.dao = EventosDAO() # Instancia del DAO
        self.setWindowTitle(f"MiniCalendar - Bienvenido, {self.usuario['nombre']}")
        
        # Ajustar tamaño inicial seguro (evita que la ventana sea más grande que la pantalla)
        screen = QApplication.primaryScreen().availableGeometry()
        w = min(1280, screen.width() - 50)
        h = min(800, screen.height() - 50)
        self.resize(w, h)
        
        centrar_ventana(self)
        self.verificar_columnas_db() # Asegurar que existen las columnas nuevas

        # Inicialización
        self.fecha_actual = datetime.now()
        self.vista_actual = "Mes"
        self.eventos = self.cargar_eventos()
        self.pronostico_clima = {} # Diccionario para guardar el clima futuro
        self.celdas_map = {} # Mapeo de (fila, col) -> fecha para Drag&Drop
        self.eventos_notificados = set() # Para no repetir alertas

        # Navegación
        self.label_fecha = QLabel("")
        self.label_fecha.setAlignment(Qt.AlignCenter)
        self.label_fecha.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        self.boton_prev = QPushButton("←")
        self.boton_next = QPushButton("→")
        self.boton_prev.clicked.connect(lambda: self.cambiar_periodo(-1))
        self.boton_prev.setCursor(Qt.PointingHandCursor)
        self.boton_next.clicked.connect(lambda: self.cambiar_periodo(1))
        self.boton_next.setCursor(Qt.PointingHandCursor)
        nav_layout = QHBoxLayout()
        nav_layout.addWidget(self.boton_prev)
        nav_layout.addWidget(self.label_fecha)
        nav_layout.addWidget(self.boton_next)
        
        # Etiqueta del Clima (Sevilla)
        self.label_clima = QLabel("Cargando clima...")
        self.label_clima.setStyleSheet("color: #555; font-size: 12px; margin-left: 15px; padding: 3px; border: 1px solid #ddd; border-radius: 5px; background-color: #f9f9f9;")
        nav_layout.addWidget(self.label_clima)

        # Selector de vista
        self.combo_vista = QComboBox()
        self.combo_vista.addItems(VISTAS)
        self.combo_vista.setCursor(Qt.PointingHandCursor)
        self.combo_vista.setCurrentText(self.vista_actual)
        self.combo_vista.currentTextChanged.connect(self.cambiar_vista)
        vista_layout = QHBoxLayout()
        vista_layout.addWidget(QLabel("Vista:"))
        vista_layout.addWidget(self.combo_vista)
        vista_layout.addStretch()

        # Botón Sincronizar (Nuevo)
        self.boton_sync = QPushButton("↻ Sincronizar")
        self.boton_sync.setToolTip("Recargar eventos desde la base de datos")
        self.boton_sync.clicked.connect(self.sincronizar_manual)
        self.boton_sync.setCursor(Qt.PointingHandCursor)
        self.boton_sync.setStyleSheet("""
            QPushButton { padding: 5px; background-color: #1abc9c; color: white; font-weight: bold; border-radius: 3px; }
            QPushButton:hover { background-color: #16a085; }
        """)
        vista_layout.addWidget(self.boton_sync)

        # Etiqueta de estado de sincronización
        self.label_status = QLabel("")
        self.label_status.setStyleSheet("color: #7f8c8d; font-size: 11px; margin-right: 10px;")
        vista_layout.addWidget(self.label_status)
        
        # Botón Eventos Importantes
        self.boton_importantes = QPushButton("⭐ Importantes")
        self.boton_importantes.clicked.connect(self.abrir_lista_importantes)
        self.boton_importantes.setCursor(Qt.PointingHandCursor)
        self.boton_importantes.setStyleSheet("""
            QPushButton { padding: 5px; background-color: #f1c40f; color: black; font-weight: bold; border-radius: 3px; }
            QPushButton:hover { background-color: #f7dc6f; }
        """)
        vista_layout.addWidget(self.boton_importantes)

        # Botón Importar Google
        self.boton_google = QPushButton("📅 Importar G-Cal")
        self.boton_google.clicked.connect(self.iniciar_importacion_google)
        self.boton_google.setCursor(Qt.PointingHandCursor)
        self.boton_google.setStyleSheet("""
            QPushButton { padding: 5px; background-color: #DB4437; color: white; font-weight: bold; border-radius: 3px; }
            QPushButton:hover { background-color: #e74c3c; }
        """)
        vista_layout.addWidget(self.boton_google)

        # Botón Cerrar Sesión
        self.boton_logout = QPushButton("🔒 Salir")
        self.boton_logout.clicked.connect(self.cerrar_sesion)
        self.boton_logout.setCursor(Qt.PointingHandCursor)
        self.boton_logout.setStyleSheet("""
            QPushButton { padding: 5px; background-color: #7f8c8d; color: white; font-weight: bold; border-radius: 3px; }
            QPushButton:hover { background-color: #95a5a6; }
        """)
        vista_layout.addWidget(self.boton_logout)

        # Tabla principal
        self.tabla = CalendarioTable()
        self.tabla.cellClicked.connect(self.celda_click)
        self.tabla.evento_dropped.connect(self.procesar_drop)
        
        # --- CORRECCIÓN DE LAYOUT ---
        # Configuramos los headers para que estiren (Stretch) todas las secciones por igual.
        # Esto soluciona el problema de filas pequeñas a la izquierda y una grande a la derecha.
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        # Desactivamos el ajuste al contenido para que respete el tamaño de la ventana
        self.tabla.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        self.tabla.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        
        # Estilo para que los encabezados destaquen (Color Azul y texto blanco)
        self.tabla.horizontalHeader().setStyleSheet("""
            QHeaderView::section {
                background-color: #3498db;
                color: white;
                font-weight: bold;
                font-size: 11pt;
                border: 1px solid #2980b9;
                padding: 2px;
            }
        """)

        # Layout principal
        layout = QVBoxLayout()
        layout.addLayout(nav_layout)
        layout.addLayout(vista_layout)
        layout.addWidget(self.tabla, stretch=1)
        self.setLayout(layout)

        self.mostrar_vista()
        self.solicitar_clima()

        # Timer para verificar recordatorios cada 30 segundos
        self.timer_alertas = QTimer(self)
        self.timer_alertas.timeout.connect(self.verificar_recordatorios)
        self.timer_alertas.start(30000) 

    def cerrar_sesion(self):
        self.logout_signal.emit()
        self.close()

    # =================== Sincronización Manual ===================
    def sincronizar_manual(self):
        """Fuerza la recarga de eventos desde la BD con feedback visual."""
        texto_original = self.boton_sync.text()
        self.boton_sync.setText("⏳ Cargando...")
        self.boton_sync.setEnabled(False)
        # Forzamos a la UI a actualizarse antes de iniciar la carga
        QApplication.processEvents()

        try:
            self.refrescar_eventos()
            hora_actual = datetime.now().strftime("%H:%M:%S")
            self.label_status.setText(f"Última sinc: {hora_actual}")
        except Exception as e:
            logging.error(f"Error en sincronización manual: {e}")
        finally:
            self.boton_sync.setText(texto_original)
            self.boton_sync.setEnabled(True)

    # =================== Google Calendar ===================
    def iniciar_importacion_google(self):
        self.boton_google.setEnabled(False)
        self.boton_google.setText("Sincronizando...")
        
        self.hilo_google = HiloGoogle(self.usuario['id_usuario'])
        self.hilo_google.resultado.connect(self.fin_importacion_google)
        self.hilo_google.start()

    def fin_importacion_google(self, exito, mensaje):
        self.boton_google.setEnabled(True)
        self.boton_google.setText("📅 Importar G-Cal")
        if exito:
            QMessageBox.information(self, "Google Calendar", mensaje)
            self.refrescar_eventos()
        else:
            QMessageBox.warning(self, "Error Google", mensaje)

    def solicitar_clima(self):
        """Inicia el hilo de carga del clima, evitando ejecuciones duplicadas."""
        # Si ya hay un hilo de clima corriendo, no hacemos nada para no saturar.
        if hasattr(self, 'hilo_clima') and self.hilo_clima.isRunning():
            return

        self.hilo_clima = HiloClima()
        self.hilo_clima.datos_clima.connect(self.actualizar_clima)
        self.hilo_clima.start()

    # =================== Lógica de Importantes y Alertas ===================
    def verificar_columnas_db(self):
        """Añade columnas para importantes si no existen."""
        self.dao.verificar_columnas()

    def verificar_recordatorios(self):
        ahora = datetime.now()
        for ev in self.eventos:
            # Si tiene aviso configurado y no ha sido notificado en esta sesión
            if ev.get('minutos_aviso', 0) > 0 and ev['id_evento'] not in self.eventos_notificados:
                fecha_evento = ev['fecha_inicio']
                fecha_aviso = fecha_evento - timedelta(minutes=ev['minutos_aviso'])
                
                # Si ya pasó la hora del aviso pero aún no ha pasado el evento (o acaba de pasar)
                if fecha_aviso <= ahora <= fecha_evento:
                    self.mostrar_alerta(ev)
                    self.eventos_notificados.add(ev['id_evento'])

    def mostrar_alerta(self, evento):
        QMessageBox.information(self, "🔔 Recordatorio de Evento", 
                                f"¡Atención!\n\nEl evento importante '{evento['titulo']}'\nes el {evento['fecha_inicio'].strftime('%d/%m a las %H:%M')}")

    def abrir_lista_importantes(self):
        dialogo = QDialog(self)
        dialogo.setWindowTitle("Eventos Importantes ⭐")
        dialogo.resize(400, 500)
        layout = QVBoxLayout()
        
        lista = QListWidget()
        importantes = [e for e in self.eventos if e.get('es_importante')]
        importantes.sort(key=lambda x: x['fecha_inicio'])
        
        for ev in importantes:
            item = QListWidgetItem(f"{ev['fecha_inicio'].strftime('%d/%m %H:%M')} - {ev['titulo']}")
            item.setForeground(QBrush(QColor("#d35400"))) # Color oscuro para resaltar
            lista.addItem(item)
            
        layout.addWidget(QLabel("Próximos eventos importantes:"))
        layout.addWidget(lista)
        dialogo.setLayout(layout)
        dialogo.exec_()

    # =================== Gestión de vistas ===================
    def cambiar_vista(self, nueva_vista):
        self.vista_actual = nueva_vista
        self.mostrar_vista()
        self.solicitar_clima()

    def cambiar_periodo(self, delta):
        if self.vista_actual == "Día":
            self.fecha_actual += timedelta(days=delta)
        elif self.vista_actual == "Semana":
            self.fecha_actual += timedelta(weeks=delta)
        elif self.vista_actual == "Mes":
            mes = self.fecha_actual.month + delta
            anio = self.fecha_actual.year
            if mes > 12:
                mes = 1
                anio += 1
            elif mes < 1:
                mes = 12
                anio -= 1
            self.fecha_actual = self.fecha_actual.replace(year=anio, month=mes)
        elif self.vista_actual == "Año":
            self.fecha_actual = self.fecha_actual.replace(year=self.fecha_actual.year + delta)
        self.mostrar_vista()
        self.solicitar_clima()
        
    def actualizar_clima(self, temp, icono, pronostico):
        """Slot que recibe los datos del hilo y actualiza la interfaz"""
        if temp == "Error":
            self.label_clima.setText("Sin conexión 🚫")
        else:
            self.label_clima.setText(f"Sevilla: {icono} {temp}°C")
            
        self.pronostico_clima = pronostico
        # Refrescamos la vista para que aparezcan los iconos en los días
        self.mostrar_vista()

    def mostrar_vista(self):
        # Reinforzamos el modo Stretch cada vez que se actualiza la vista
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        # Aseguramos que las cabeceras sean visibles (la vista Año las oculta)
        self.tabla.horizontalHeader().setVisible(True)
        self.tabla.verticalHeader().setVisible(False)

        if self.vista_actual == "Día":
            self.mostrar_vista_dia()
        elif self.vista_actual == "Semana":
            self.mostrar_vista_semana()
        elif self.vista_actual == "Mes":
            self.mostrar_vista_mes()
        elif self.vista_actual == "Año":
            self.mostrar_vista_anio()

    # ================= VISTAS =================
    def mostrar_vista_dia(self):
        self.label_fecha.setText(self.fecha_actual.strftime("%d/%m/%Y"))
        self.tabla.clear()
        self.tabla.setShowGrid(True)
        self.celdas_map = {} # Limpiar mapa
        self.tabla.setRowCount(20)
        self.tabla.setColumnCount(1)
        
        nombre_dia = DIAS_SEMANA[self.fecha_actual.weekday()]
        info_extra = ""
        
        # Añadir clima
        fecha_str = self.fecha_actual.strftime("%Y-%m-%d")
        if fecha_str in self.pronostico_clima:
            icono_clima, temp_max, temp_min = self.pronostico_clima[fecha_str]
            info_extra = f"  |  {icono_clima} Max: {temp_max}°C Min: {temp_min}°C"
            
        self.tabla.setHorizontalHeaderLabels([f"{nombre_dia} {info_extra}"])
        
        eventos_dia = [e for e in self.eventos if e['fecha_inicio'].date() == self.fecha_actual.date()]
        for i in range(20):
            item = QTableWidgetItem("")
            if i < len(eventos_dia):
                evento = eventos_dia[i]
                
                titulo_mostrar = evento['titulo']
                if evento.get('archivo_adjunto'):
                    titulo_mostrar = "📎 " + titulo_mostrar
                item.setText(titulo_mostrar)

                color_hex = '#' + evento['color_db_string'].split('#')[-1]
                item.setBackground(QBrush(QColor(color_hex)))
                # Datos para Drag & Drop
                item.setData(Qt.UserRole, evento['id_evento'])
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
            self.tabla.setItem(i, 0, item)
            self.celdas_map[(i, 0)] = self.fecha_actual

    def mostrar_vista_semana(self):
        inicio_semana = self.fecha_actual - timedelta(days=self.fecha_actual.weekday())
        self.label_fecha.setText(f"Semana del {inicio_semana.strftime('%d/%m/%Y')}")
        self.tabla.clear()
        self.tabla.setShowGrid(True)
        self.celdas_map = {} # Limpiar mapa
        self.tabla.setRowCount(20)
        self.tabla.setColumnCount(7)
        
        headers = []
        dias_cortos = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        for col in range(7):
            dia = inicio_semana + timedelta(days=col)
            info = ""
            
            # Añadir clima
            fecha_str = dia.strftime("%Y-%m-%d")
            if fecha_str in self.pronostico_clima:
                icono_clima, temp_max, temp_min = self.pronostico_clima[fecha_str]
                info = f"\n{icono_clima} {temp_max}°/{temp_min}°"
                
            headers.append(f"{dias_cortos[col]}{info}")
            
        self.tabla.setHorizontalHeaderLabels(headers)
        
        # Definición de colores para fin de semana (Igual que en Mes)
        if CONFIGURACION["ESTILO_INTENSO"]:
            color_sabado = "#FF69B4" # HotPink
            color_domingo = "#C71585" # MediumVioletRed
        else:
            color_sabado = "#FFB6C1" # Rosa pastel
            color_domingo = "#F06292" # Rosa oscuro suave

        for col in range(7):
            dia = inicio_semana + timedelta(days=col)
            eventos_dia = [e for e in self.eventos if e['fecha_inicio'].date() == dia.date()]
            
            # Determinar color de fondo de la columna
            bg_color = QColor("white")
            if col == 5: # Sábado
                bg_color = QColor(color_sabado)
            elif col == 6: # Domingo
                bg_color = QColor(color_domingo)

            for fila in range(20):
                item = QTableWidgetItem("")
                item.setBackground(QBrush(bg_color)) # Aplicar fondo base (blanco o rosa finde)
                
                if fila < len(eventos_dia):
                    evento = eventos_dia[fila]
                    
                    titulo_mostrar = evento['titulo']
                    if evento.get('archivo_adjunto'):
                        titulo_mostrar = "📎 " + titulo_mostrar
                    item.setText(titulo_mostrar)

                    color_hex = '#' + evento['color_db_string'].split('#')[-1]
                    item.setBackground(QBrush(QColor(color_hex)))
                    # Datos para Drag & Drop
                    item.setData(Qt.UserRole, evento['id_evento'])
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
                    
                    # Tooltip para eventos en vista semana
                    if CONFIGURACION["MOSTRAR_NOTAS"] and evento.get('descripcion'):
                        item.setToolTip(f"{evento['titulo']}\n---\n{evento['descripcion']}")
                        
                self.tabla.setItem(fila, col, item)
                self.celdas_map[(fila, col)] = dia

    def mostrar_vista_mes(self):
        mes = self.fecha_actual.month
        anio = self.fecha_actual.year
        self.label_fecha.setText(f"{MESES_ESPANOL[mes]} {anio}")
        self.tabla.clear()
        self.tabla.setShowGrid(False) # Ocultamos la cuadrícula para que los días vacíos sean invisibles
        self.celdas_map = {} # Limpiar mapa
        
        # Fijamos 6 filas y 7 columnas para que Stretch funcione perfectamente
        self.tabla.setRowCount(6)
        self.tabla.setColumnCount(7)
        self.tabla.setHorizontalHeaderLabels(["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"])
        
        cal = calendar.Calendar(firstweekday=0)
        dias = list(cal.itermonthdays(anio, mes))
        
        fila, col = 0, 0
        for dia in dias:
            if dia != 0:
                eventos_dia = [e for e in self.eventos if e['fecha_inicio'].day == dia and e['fecha_inicio'].month == mes and e['fecha_inicio'].year == anio]
                
                # --- LÓGICA DE ESTILO (HEATMAP & FINDE & HOY) ---
                es_hoy = (dia == datetime.now().day and mes == datetime.now().month and anio == datetime.now().year)
                fecha_obj = datetime(anio, mes, dia)
                self.celdas_map[(fila, col)] = fecha_obj # <-- AÑADIDO: Mapear celda a fecha para Drag&Drop
                dia_semana = fecha_obj.weekday() # 0=Lun, 5=Sab, 6=Dom
                num_eventos = len(eventos_dia)

                # Color de fondo base (Fin de semana vs Laborable)
                bg_color = "white"
                
                # Definición de paletas (Suave vs Intenso)
                if CONFIGURACION["ESTILO_INTENSO"]:
                    color_sabado = "#FF69B4" # HotPink
                    color_domingo = "#C71585" # MediumVioletRed
                    color_hoy = "#5DADE2" # Azul intenso
                else:
                    color_sabado = "#FFB6C1" # Rosa pastel
                    color_domingo = "#F06292" # Rosa oscuro suave
                    color_hoy = "#AED6F1" # Azul celeste suave

                if dia_semana == 5: # Sábado
                    bg_color = color_sabado
                elif dia_semana == 6: # Domingo
                    bg_color = color_domingo

                # Borde para "HOY"
                borde_estilo = "1px solid #bfbfbf" # Gris estándar para simular rejilla
                if es_hoy:
                    borde_estilo = "2px solid #3498db" # Marco azul
                    bg_color = color_hoy

                # Widget contenedor de la celda
                celda_widget = CeldaDiaWidget(fecha_obj)
                celda_widget.setObjectName("celda_dia")
                celda_widget.evento_soltado_en_celda.connect(self.procesar_drop_mes)
                celda_widget.setStyleSheet(f"#celda_dia {{ background-color: {bg_color}; border: {borde_estilo}; }}")
                celda_layout = QVBoxLayout()
                celda_layout.setContentsMargins(2, 2, 2, 2)
                celda_layout.setSpacing(1)

                # --- CABECERA DE LA CELDA (NÚMERO + SANTO) ---
                # Detectar Festivo
                datos_festivo = FESTIVOS_DATA.get((mes, dia))
                color_numero = "#555" # Gris oscuro por defecto
                tooltip_texto = ""

                if datos_festivo and CONFIGURACION["MOSTRAR_FESTIVOS"]:
                    tipo = datos_festivo["tipo"]
                    color_numero = COLORES_FESTIVOS.get(tipo, "#555")
                    tooltip_texto = f"{datos_festivo['nombre']} ({tipo.capitalize()})"

                # Texto del número (con clima si existe)
                texto_dia = str(dia)
                fecha_str = f"{anio}-{mes:02d}-{dia:02d}"
                if fecha_str in self.pronostico_clima:
                    icono_clima, temp_max, temp_min = self.pronostico_clima[fecha_str]
                    texto_dia += f"  {icono_clima} {temp_max}°/{temp_min}°"

                # Texto del número
                dia_label = QLabel(texto_dia)
                dia_label.setStyleSheet(f"font-weight: bold; color: {color_numero}; font-size: 12px; border: none; background: transparent;")
                dia_label.setAlignment(Qt.AlignLeft)
                if tooltip_texto:
                    dia_label.setToolTip(tooltip_texto)
                
                celda_layout.addWidget(dia_label)

                # Santo (Texto pequeño debajo)
                info_santo = self.obtener_info_dia(fecha_obj)
                if info_santo:
                    santo_label = QLabel(info_santo)
                    santo_label.setStyleSheet("color: #7f8c8d; font-size: 9px; font-style: italic; border: none; background: transparent;")
                    santo_label.setAlignment(Qt.AlignLeft)
                    celda_layout.addWidget(santo_label)

                # Área de scroll para los eventos (por si hay muchos)
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(0) # Sin bordes
                scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff) # Evita que aparezca el scroll horizontal si el texto es largo
                scroll.setStyleSheet("background: transparent;")
                
                contenido_scroll = QWidget()
                contenido_layout = QVBoxLayout()
                contenido_layout.setContentsMargins(0,0,0,0)
                contenido_layout.setSpacing(1)

                for ev in eventos_dia:
                    titulo_mostrar = ev['titulo']
                    # Icono de adjunto
                    if ev.get('archivo_adjunto'):
                        titulo_mostrar = "📎 " + titulo_mostrar
                    # Icono de cumpleaños
                    if CONFIGURACION["MOSTRAR_CUMPLEANOS"] and ("cumple" in titulo_mostrar.lower()):
                        titulo_mostrar = "🎂 " + titulo_mostrar

                    # Usamos BotonEvento para permitir arrastrar
                    btn = BotonEvento(ev, titulo_mostrar)
                    
                    # Mostrar notas (descripción) en tooltip si está activado
                    if CONFIGURACION["MOSTRAR_NOTAS"] and ev.get('descripcion'):
                        btn.setToolTip(f"{ev['titulo']}\n---\n{ev['descripcion']}")

                    # Estilo del evento
                    color_bg = '#' + ev['color_db_string'].split('#')[-1]
                    btn.setStyleSheet(f"""
                        QPushButton {{ background-color: {color_bg}; color: black; text-align: left; font-size: 9pt; border-radius: 2px; padding: 2px; }}
                        QPushButton:hover {{ border: 1px solid #333; }}
                    """)
                    btn.setFixedHeight(18)
                    btn.clicked.connect(partial(self.abrir_gestion_evento, ev))
                    contenido_layout.addWidget(btn)

                contenido_layout.addStretch()
                contenido_scroll.setLayout(contenido_layout)
                scroll.setWidget(contenido_scroll)
                celda_layout.addWidget(scroll)

                # Botón pequeño de "+"
                nuevo_btn = QPushButton("+")
                nuevo_btn.setFixedSize(20, 20)
                nuevo_btn.setCursor(Qt.PointingHandCursor)
                nuevo_btn.setStyleSheet("""
                    QPushButton { background-color: #2ecc71; color: white; font-weight: bold; border-radius: 10px; border: none; }
                    QPushButton:hover { background-color: #27ae60; }
                """)
                nuevo_btn.clicked.connect(partial(self.abrir_crear_evento, datetime(anio, mes, dia)))
                
                # Alineamos el botón + a la derecha
                h_layout_btn = QHBoxLayout()
                h_layout_btn.addStretch()
                h_layout_btn.addWidget(nuevo_btn)
                h_layout_btn.setContentsMargins(0,0,2,2)
                celda_layout.addLayout(h_layout_btn)

                celda_widget.setLayout(celda_layout)
                self.tabla.setCellWidget(fila, col, celda_widget)

            col += 1
            if col > 6:
                col = 0
                fila += 1
        
        # NOTA: Se ha eliminado el bucle manual de "Ajuste uniforme"
        # QHeaderView.Stretch se encarga de todo.

    def mostrar_vista_anio(self):
        anio = self.fecha_actual.year
        self.label_fecha.setText(str(anio))
        self.tabla.clear()
        self.tabla.setShowGrid(False)
        self.celdas_map = {}
        self.tabla.setRowCount(3)
        self.tabla.setColumnCount(4)
        
        # Ocultamos las cabeceras para un look más limpio tipo "Grid"
        self.tabla.horizontalHeader().setVisible(False)
        self.tabla.verticalHeader().setVisible(False)

        # Iconos estacionales según descripción
        ICONOS_ESTACION = {
            1: "❄️", 2: "💨", # Enero (Nieve), Febrero (Viento ráfaga)
            3: "🌱", 4: "🌧️", 5: "🌸", # Primavera (Brote, Lluvia abril, Flor)
            6: "🍦", 7: "🏖️", 8: "☀️", # Verano (Junio=Helado, Julio=Playa, Agosto=Sol)
            9: "🌾", 10: "🍂", 11: "🍁", # Otoño (Campo, Hojas cayendo)
            12: "🌧️" # Diciembre (Lluvia/Invierno)
        }

        for m in range(1, 13):
            fila = (m - 1) // 4
            col = (m - 1) % 4
            
            icono = ICONOS_ESTACION.get(m, "")
            
            # Contamos los eventos de este mes
            count = sum(1 for e in self.eventos if e['fecha_inicio'].month == m and e['fecha_inicio'].year == anio)
            
            # Creamos el botón tarjeta
            btn_mes = QPushButton()
            
            # Layout interno para usar HTML en etiquetas (permite colorear solo los iconos)
            layout_btn = QVBoxLayout(btn_mes)
            layout_btn.setContentsMargins(2, 2, 2, 2)
            layout_btn.setSpacing(0)
            layout_btn.setAlignment(Qt.AlignCenter)

            # Título con HTML
            nombre_mes = MESES_ESPANOL[m]
            html_titulo = f"{icono} {nombre_mes} {icono}"
            
            if m == 1: # Enero: Iconos azules
                html_titulo = f"<span style='color:#3498db;'>{icono}</span> {nombre_mes} <span style='color:#3498db;'>{icono}</span>"
            elif m == 8: # Agosto: Iconos amarillos
                html_titulo = f"<span style='color:#f1c40f;'>{icono}</span> {nombre_mes} <span style='color:#f1c40f;'>{icono}</span>"
            
            lbl_titulo = QLabel(html_titulo)
            lbl_titulo.setAlignment(Qt.AlignCenter)
            lbl_titulo.setAttribute(Qt.WA_TransparentForMouseEvents) # Para que el click pase al botón
            lbl_titulo.setStyleSheet("font-size: 14px; font-weight: bold; border: none; background: transparent; color: #555;")
            
            texto_info = f"{count} Eventos" if count > 0 else "Sin actividad"
            lbl_info = QLabel(texto_info)
            lbl_info.setAlignment(Qt.AlignCenter)
            lbl_info.setAttribute(Qt.WA_TransparentForMouseEvents)
            lbl_info.setStyleSheet("font-size: 11px; color: #777; border: none; background: transparent;")
            
            layout_btn.addWidget(lbl_titulo)
            layout_btn.addWidget(lbl_info)
            
            # Mapa de calor para el AÑO (Color del mes según intensidad)
            bg_mes = "#f8f9fa" # Base
            border_mes = "#e0e0e0"
            if count > 0: bg_mes = "#ebf5fb"; border_mes = "#aed6f1" # Bajo
            if count > 5: bg_mes = "#d6eaf8"; border_mes = "#85c1e9" # Medio
            if count > 15: bg_mes = "#a9cce3"; border_mes = "#5499c7" # Alto
            if count > 30: bg_mes = "#7fb3d5"; border_mes = "#2980b9" # Muy Alto

            # Personalización específica por mes
            if m == 1: # Enero: Fondo celeste (mismo tono que 'Hoy')
                bg_mes = "#AED6F1"

            # Estilo Base
            estilo = """
                QPushButton {
                    border-radius: 15px;
                    font-size: 14px;
                    font-weight: bold;
                }
            """
            
            # Aplicamos colores calculados
            estilo += f"QPushButton {{ background-color: {bg_mes}; border: 2px solid {border_mes}; }}"
            estilo += "QPushButton:hover { background-color: #ffffff; border-color: #3498db; cursor: pointer; }"

            btn_mes.setCursor(Qt.PointingHandCursor)
            btn_mes.setStyleSheet(estilo)
            btn_mes.clicked.connect(lambda checked, mes=m: self.ir_a_mes(mes))
            
            self.tabla.setCellWidget(fila, col, btn_mes)

    def ir_a_mes(self, mes):
        """Cambia la vista al mes seleccionado"""
        self.fecha_actual = self.fecha_actual.replace(month=mes, day=1)
        self.combo_vista.setCurrentText("Mes")

    # =================== Lógica Drag & Drop ===================
    def procesar_drop(self, id_evento, row, col):
        """Calcula la nueva fecha/hora basada en dónde se soltó el evento"""
        evento = next((e for e in self.eventos if e['id_evento'] == id_evento), None)
        if not evento: return

        # Esta función ahora solo gestiona las vistas Día y Semana
        if self.vista_actual in ["Semana", "Día"]:
            # Determinar el día objetivo
            target_date = None
            if self.vista_actual == "Semana":
                inicio_semana = self.fecha_actual - timedelta(days=self.fecha_actual.weekday())
                target_date = inicio_semana + timedelta(days=col)
            else:
                target_date = self.fecha_actual

            # Obtenemos eventos del día objetivo EXCLUYENDO el movido
            evs_dia = [e for e in self.eventos if e['fecha_inicio'].date() == target_date.date() and e['id_evento'] != id_evento]
            # Ordenación robusta para evitar saltos: Hora -> Título -> ID
            evs_dia.sort(key=lambda x: (x['fecha_inicio'], x['titulo'], x['id_evento']))
            
            nueva_fecha_inicio = None

            # 'row' indica la posición visual deseada
            if row >= len(evs_dia):
                # Mover al final
                if evs_dia:
                    nueva_fecha_inicio = evs_dia[-1]['fecha_inicio'] + timedelta(minutes=30)
                else:
                    nueva_fecha_inicio = target_date.replace(hour=9, minute=0, second=0)
            elif row == 0:
                # Mover al principio
                if evs_dia:
                    nueva_fecha_inicio = evs_dia[0]['fecha_inicio'] - timedelta(minutes=30)
                    if nueva_fecha_inicio.date() < target_date.date(): # Evitar cambio de día
                        nueva_fecha_inicio = datetime.combine(target_date.date(), datetime.min.time())
                else:
                    nueva_fecha_inicio = target_date.replace(hour=9, minute=0, second=0)
            else:
                # Insertar entre dos eventos
                prev_t = evs_dia[row-1]['fecha_inicio']
                next_t = evs_dia[row]['fecha_inicio']
                diff_seconds = (next_t - prev_t).total_seconds() / 2
                nueva_fecha_inicio = prev_t + timedelta(seconds=max(60, diff_seconds)) # Mínimo 1 min de diferencia
            
            # Asegurar que la fecha base es la correcta (por si el cálculo de horas cambió el día)
            nueva_fecha_inicio = nueva_fecha_inicio.replace(year=target_date.year, month=target_date.month, day=target_date.day)

            if nueva_fecha_inicio:
                # Actualizamos y aplicamos efecto dominó si es necesario
                self.actualizar_evento_con_ripple(id_evento, nueva_fecha_inicio, evs_dia, row)

    def procesar_drop_mes(self, id_evento_movido, id_evento_destino, fecha_destino_obj):
        """Gestiona el drop en la vista Mes para reordenar o mover eventos."""
        evento_movido = next((e for e in self.eventos if e['id_evento'] == id_evento_movido), None)
        if not evento_movido: return

        # Eventos del día destino (excluyendo el movido) para calcular posiciones
        eventos_destino = [e for e in self.eventos if e['fecha_inicio'].date() == fecha_destino_obj.date() and e['id_evento'] != id_evento_movido]
        # Ordenación robusta para evitar saltos: Hora -> Título -> ID
        eventos_destino.sort(key=lambda x: (x['fecha_inicio'], x['titulo'], x['id_evento']))

        # Determinar índice de inserción
        insert_index = len(eventos_destino) # Por defecto al final
        if id_evento_destino is not None:
            for i, ev in enumerate(eventos_destino):
                if ev['id_evento'] == id_evento_destino:
                    insert_index = i
                    break
        
        nueva_fecha = None

        # Calcular nueva fecha basada en el índice
        if insert_index == 0:
            if eventos_destino:
                # Insertar antes del primero (intentamos 10 min antes)
                nueva_fecha = eventos_destino[0]['fecha_inicio'] - timedelta(minutes=10)
                if nueva_fecha.date() < fecha_destino_obj.date():
                    nueva_fecha = datetime.combine(fecha_destino_obj.date(), datetime.min.time())
            else:
                # Si no hay eventos, mantenemos la hora original o ponemos 09:00
                t = evento_movido['fecha_inicio'].time()
                if t == datetime.min.time(): t = datetime.strptime("09:00", "%H:%M").time()
                nueva_fecha = datetime.combine(fecha_destino_obj.date(), t)
        
        elif insert_index == len(eventos_destino):
            # Insertar al final
            nueva_fecha = eventos_destino[-1]['fecha_inicio'] + timedelta(minutes=30)
            if nueva_fecha.date() > fecha_destino_obj.date():
                nueva_fecha = datetime.combine(fecha_destino_obj.date(), datetime.max.time()) - timedelta(seconds=1)
        
        else:
            # Insertar entre dos eventos
            prev_ev = eventos_destino[insert_index - 1]
            next_ev = eventos_destino[insert_index]
            diff = (next_ev['fecha_inicio'] - prev_ev['fecha_inicio']).total_seconds()
            add_seconds = max(60, diff / 2) # Mínimo 1 minuto
            nueva_fecha = prev_ev['fecha_inicio'] + timedelta(seconds=add_seconds)

        if nueva_fecha:
            self.actualizar_evento_con_ripple(id_evento_movido, nueva_fecha, eventos_destino, insert_index)

    def actualizar_evento_con_ripple(self, id_evento, nueva_fecha, lista_eventos_posteriores, indice_inicio):
        """Actualiza un evento y empuja los siguientes si hay colisión de horas."""
        # Delegamos la lógica de negocio compleja (actualización en cascada) al DAO.
        # Esto mantiene la ventana principal más limpia y la lógica de datos centralizada.
        try:
            self.dao.actualizar_fecha_evento_con_ripple(
                id_evento,
                nueva_fecha,
                lista_eventos_posteriores,
                indice_inicio
            )
            self.refrescar_eventos()
        except Exception as e:
            logging.error(f"Error al mover evento con efecto dominó: {e}", exc_info=True)
            QMessageBox.warning(self, "Error al Mover", f"No se pudo guardar el cambio de fecha.\nError: {e}")
            self.refrescar_eventos() # Recargamos para deshacer el cambio visual

    # =================== Click ===================
    def celda_click(self, row, col):
        if self.vista_actual in ["Día","Semana"]:
            if self.vista_actual=="Día":
                fecha = self.fecha_actual
                fila_celda=row
            else:
                inicio_semana=self.fecha_actual - timedelta(days=self.fecha_actual.weekday())
                fecha = inicio_semana + timedelta(days=col)
                fila_celda=row
            
            eventos_dia=[e for e in self.eventos if e['fecha_inicio'].date()==fecha.date()]
            if fila_celda<len(eventos_dia):
                self.abrir_gestion_evento(eventos_dia[fila_celda])
            else:
                self.abrir_crear_evento(fecha)
        elif self.vista_actual=="Mes":
            pass
        elif self.vista_actual=="Año":
            pass

    # =================== Crear/Gestionar eventos ===================
    def abrir_crear_evento(self, fecha):
        # Lógica inteligente para sugerir hora:
        # Si ya hay eventos ese día, sugerimos 1 hora después del último.
        eventos_dia = [e for e in self.eventos if e['fecha_inicio'].date() == fecha.date()]
        
        fecha_sugerida = fecha
        if eventos_dia:
            eventos_dia.sort(key=lambda x: x['fecha_inicio'])
            ultimo_evento = eventos_dia[-1]
            fecha_sugerida = ultimo_evento['fecha_inicio'] + timedelta(hours=1)
            # Si nos pasamos de día, lo dejamos al final del día
            if fecha_sugerida.date() > fecha.date():
                fecha_sugerida = datetime.combine(fecha.date(), datetime.max.time())
        elif fecha.hour == 0 and fecha.minute == 0:
            # Si es un día vacío y la fecha viene sin hora (00:00), sugerimos las 09:00
            fecha_sugerida = fecha.replace(hour=9, minute=0)

        self.ventana_editor = VentanaGestionEvento(self.usuario, fecha_sugerida)
        self.ventana_editor.evento_gestionado.connect(self.refrescar_eventos)
        self.ventana_editor.show()

    def abrir_gestion_evento(self, evento):
        self.ventana_editor = VentanaGestionEvento(self.usuario, evento)
        self.ventana_editor.evento_gestionado.connect(self.refrescar_eventos)
        self.ventana_editor.show()

    def refrescar_eventos(self):
        self.eventos = self.cargar_eventos()
        self.mostrar_vista()
        # Cada vez que se gestiona un evento, intentamos actualizar el clima
        self.solicitar_clima()
        
    def obtener_info_dia(self, fecha, completo=False):
        """Devuelve el Santo si está activado en config."""
        if not CONFIGURACION["MOSTRAR_SANTOS"]:
            return ""
            
        # Santoral
        return SANTORAL.get((fecha.month, fecha.day), "")


    # =================== Cargar eventos ===================
    def cargar_eventos(self):
        eventos = self.dao.obtener_por_usuario(self.usuario['id_usuario'])
        if eventos is None:
            QMessageBox.critical(self, "Sin Conexión", "Se ha perdido la conexión con el servidor.\nNo se pueden cargar los eventos. Revisa tu internet.")
            return []
        
        # Conversión de fechas si vienen como string (depende del conector)
        for e in eventos:
            if isinstance(e['fecha_inicio'], str):
                e['fecha_inicio'] = datetime.strptime(e['fecha_inicio'], "%Y-%m-%d %H:%M:%S")
        return eventos