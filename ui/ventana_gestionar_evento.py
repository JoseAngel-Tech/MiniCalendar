import logging
from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit, QTextEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QMessageBox, QComboBox, QFileDialog, QCheckBox, QDateTimeEdit
)
from PyQt5.QtCore import pyqtSignal, Qt, QUrl
from PyQt5.QtGui import QDesktopServices
import mysql.connector
from database.dao import EventosDAO, ColoresDAO
from utils.ui_utils import centrar_ventana
from utils.config import COLORES_MAP, HEX_A_NOMBRE
import os
import shutil
import uuid

class VentanaGestionEvento(QWidget):
    evento_gestionado = pyqtSignal()

    def __init__(self, usuario, fecha_o_evento):
        super().__init__()
        self.usuario = usuario
        self.dao_eventos = EventosDAO()
        self.dao_colores = ColoresDAO()

        if isinstance(fecha_o_evento, dict): # Modo EDICIÓN
            self.modo = 'editar'
            self.evento = fecha_o_evento
            self.ruta_archivo_adjunto_actual = self.evento.get('archivo_adjunto')
            fecha_display = self.evento['fecha_inicio'].strftime('%d/%m/%Y')
            self.setWindowTitle(f"Gestionar Evento - {fecha_display}")
        else: # Modo CREAR
            self.modo = 'crear'
            self.evento = None
            self.fecha_sugerida = fecha_o_evento
            self.ruta_archivo_adjunto_actual = None
            titulo_fecha = self.fecha_sugerida.strftime('%d/%m/%Y')
            self.setWindowTitle(f"Crear Evento - {titulo_fecha}")

        self.nueva_ruta_archivo = None  # Para un archivo nuevo seleccionado
        self.accion_adjunto = "mantener"  # Puede ser 'mantener', 'cambiar', 'quitar'
        self.resize(500, 600) # Tamaño más cómodo para editar
        centrar_ventana(self)
        
        self.init_ui()
        self.cargar_datos()

    def init_ui(self):
        # ... (Resto de la inicialización de widgets)
        self.label_fecha_hora = QLabel("Fecha y Hora:")
        self.input_fecha_hora = QDateTimeEdit()
        self.input_fecha_hora.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.input_fecha_hora.setCalendarPopup(True)

        self.label_titulo = QLabel("Título:")
        self.input_titulo = QLineEdit()

        self.label_descripcion = QLabel("Descripción:")
        self.input_descripcion = QTextEdit()
        self.input_descripcion.setFixedHeight(80)
        
        self.label_color = QLabel("Color:")
        self.combo_color = QComboBox()
        # 🚨 CAMBIO: Añadir los NOMBRES de las claves del diccionario
        self.combo_color.addItems(list(COLORES_MAP.keys()))

        # --- Importante y Aviso ---
        self.check_importante = QCheckBox("⭐ Importante")
        self.label_aviso = QLabel("Avisar:")
        self.combo_aviso = QComboBox()
        self.combo_aviso.addItem("Sin aviso", 0)
        self.combo_aviso.addItem("5 min", 5)
        self.combo_aviso.addItem("15 min", 15)
        self.combo_aviso.addItem("30 min", 30)
        self.combo_aviso.addItem("1 hora", 60)
        self.combo_aviso.addItem("1 día", 1440)

        # --- Interfaz para adjuntos ---
        self.label_adjunto_titulo = QLabel("Archivo Adjunto:")
        self.label_adjunto_nombre = QLabel("Ninguno")
        self.label_adjunto_nombre.setStyleSheet("font-style: italic; color: #555;")

        self.boton_ver_adjunto = QPushButton("Ver")
        self.boton_ver_adjunto.setCursor(Qt.PointingHandCursor)
        self.boton_ver_adjunto.clicked.connect(self.ver_adjunto)
        self.boton_ver_adjunto.setVisible(False)

        self.boton_cambiar_adjunto = QPushButton("Añadir/Cambiar...")
        self.boton_cambiar_adjunto.setCursor(Qt.PointingHandCursor)
        self.boton_cambiar_adjunto.clicked.connect(self.seleccionar_nuevo_adjunto)

        self.boton_quitar_adjunto = QPushButton("Quitar")
        self.boton_quitar_adjunto.setCursor(Qt.PointingHandCursor)
        self.boton_quitar_adjunto.clicked.connect(self.marcar_para_quitar_adjunto)
        self.boton_quitar_adjunto.setVisible(False)

        # --- Botones de Acción ---
        self.boton_guardar = QPushButton("Guardar")
        self.boton_guardar.setCursor(Qt.PointingHandCursor)
        self.boton_guardar.setStyleSheet("""
            QPushButton { background-color: #3498db; color: white; font-weight: bold; border-radius: 3px; padding: 5px; }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.boton_guardar.clicked.connect(self.guardar)
        
        self.boton_eliminar = QPushButton("Eliminar Evento")
        self.boton_eliminar.setCursor(Qt.PointingHandCursor)
        self.boton_eliminar.setStyleSheet("""
            QPushButton { background-color: #e74c3c; color: white; border-radius: 3px; padding: 5px; }
            QPushButton:hover { background-color: #c0392b; }
        """)
        self.boton_eliminar.clicked.connect(self.confirmar_eliminar)

        # ... (Resto del layout)
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20) # Márgenes para que respire
        layout.setSpacing(10)
        layout.addWidget(self.label_fecha_hora)
        layout.addWidget(self.input_fecha_hora)
        layout.addWidget(self.label_titulo)
        layout.addWidget(self.input_titulo)
        layout.addWidget(self.label_descripcion)
        layout.addWidget(self.input_descripcion)
        layout.addWidget(self.label_color)
        layout.addWidget(self.combo_color)

        h_imp = QHBoxLayout()
        h_imp.addWidget(self.check_importante)
        h_imp.addWidget(self.label_aviso)
        h_imp.addWidget(self.combo_aviso)
        layout.addLayout(h_imp)
        
        # Layout para adjuntos
        adjunto_layout = QHBoxLayout()
        adjunto_layout.addWidget(self.label_adjunto_titulo)
        adjunto_layout.addWidget(self.label_adjunto_nombre, 1)
        adjunto_layout.addWidget(self.boton_ver_adjunto)
        adjunto_layout.addWidget(self.boton_cambiar_adjunto)
        adjunto_layout.addWidget(self.boton_quitar_adjunto)
        layout.addLayout(adjunto_layout)

        h_layout = QHBoxLayout()
        h_layout.addWidget(self.boton_guardar)
        
        if self.modo == 'editar':
            self.boton_guardar.setText("Guardar Cambios")
            h_layout.addWidget(self.boton_eliminar)
        else:
            self.boton_guardar.setText("Crear Evento")
        
        layout.addLayout(h_layout)
        self.setLayout(layout)


    def cargar_datos(self):
        """Rellena los campos si estamos en modo edición o pone valores por defecto si es creación."""
        if self.modo == 'editar':
            self.input_titulo.setText(self.evento['titulo'])
            self.input_descripcion.setText(self.evento.get('descripcion', ''))
            self.input_fecha_hora.setDateTime(self.evento['fecha_inicio'])
            
            # Cargar estado de importante y aviso
            self.check_importante.setChecked(bool(self.evento.get('es_importante', False)))
            minutos = self.evento.get('minutos_aviso', 0)
            idx_aviso = self.combo_aviso.findData(minutos)
            if idx_aviso != -1:
                self.combo_aviso.setCurrentIndex(idx_aviso)

            # Cargar datos del adjunto
            if self.ruta_archivo_adjunto_actual:
                nombre_archivo = os.path.basename(self.ruta_archivo_adjunto_actual)
                self.label_adjunto_nombre.setText(nombre_archivo)
                self.label_adjunto_nombre.setStyleSheet("font-style: normal;")
                self.boton_ver_adjunto.setVisible(True)
                self.boton_quitar_adjunto.setVisible(True)
            else:
                self.boton_ver_adjunto.setVisible(False)
                self.boton_quitar_adjunto.setVisible(False)
            
            # Seleccionar el color actual en el ComboBox
            color_db_string = self.evento.get('color_db_string', '')
            
            # Extraemos el código HEX (ej: #FF0000)
            color_hex_actual = '#' + color_db_string.split('#')[-1] if '#' in color_db_string else ''
            
            # Usar el mapa inverso para obtener el nombre
            nombre_color_actual = HEX_A_NOMBRE.get(color_hex_actual.upper(), None)
            
            if nombre_color_actual:
                # Buscamos y seleccionamos el color por su NOMBRE
                index = self.combo_color.findText(nombre_color_actual)
                if index != -1:
                    self.combo_color.setCurrentIndex(index)
        else: # Modo CREAR
            self.input_fecha_hora.setDateTime(self.fecha_sugerida)
            self.boton_ver_adjunto.setVisible(False)
            self.boton_quitar_adjunto.setVisible(False)


    def ver_adjunto(self):
        if self.ruta_archivo_adjunto_actual and os.path.exists(self.ruta_archivo_adjunto_actual):
            try:
                # Usar QDesktopServices para abrir el archivo con el programa por defecto del sistema.
                # Esto es multiplataforma (funciona en Windows, macOS, Linux).
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(self.ruta_archivo_adjunto_actual)))
            except Exception as e:
                logging.error(f"Error abriendo archivo adjunto: {e}")
                QMessageBox.warning(self, "Error de Archivo", f"No se pudo abrir el archivo adjunto.\nVerifica que el archivo exista y tengas permisos.\nDetalle: {e}")
        else:
            QMessageBox.warning(self, "Archivo no encontrado", "El archivo adjunto parece haber sido eliminado o movido de su ubicación original.")

    def seleccionar_nuevo_adjunto(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Seleccionar nuevo archivo", "", "Todos los archivos (*.*)")
        if ruta:
            self.nueva_ruta_archivo = ruta
            self.accion_adjunto = "cambiar"
            nombre_archivo = os.path.basename(ruta)
            self.label_adjunto_nombre.setText(f"Nuevo: {nombre_archivo}")
            self.label_adjunto_nombre.setStyleSheet("font-style: normal; color: #27ae60;")
            self.boton_ver_adjunto.setVisible(False)

    def marcar_para_quitar_adjunto(self):
        # Si se estaba por cambiar, cancela el cambio
        if self.accion_adjunto == "cambiar":
            self.accion_adjunto = "mantener"
            self.nueva_ruta_archivo = None
            self.cargar_datos() # Restaura la vista original
        # Si había un archivo, lo marca para quitar
        elif self.ruta_archivo_adjunto_actual:
            self.accion_adjunto = "quitar"
            self.label_adjunto_nombre.setText("Se quitará el adjunto")
            self.label_adjunto_nombre.setStyleSheet("font-style: normal; color: #e74c3c;")
            self.boton_ver_adjunto.setVisible(False)
            self.boton_quitar_adjunto.setVisible(False)

    def guardar(self):
        """Unifica la lógica para crear y modificar un evento."""
        titulo = self.input_titulo.text().strip()
        descripcion = self.input_descripcion.toPlainText().strip()
        
        # 🚨 CAMBIO CLAVE: Obtener el HEX a partir del nombre para la búsqueda SQL
        nombre_color_seleccionado = self.combo_color.currentText()
        color_hex = COLORES_MAP.get(nombre_color_seleccionado, "#FFFFFF")

        fecha_nueva = self.input_fecha_hora.dateTime().toPyDateTime()
        es_importante = self.check_importante.isChecked()
        minutos_aviso = self.combo_aviso.currentData()
        
        if not titulo:
            QMessageBox.warning(self, "Error", "El título es obligatorio")
            return
            
        ruta_db = self.ruta_archivo_adjunto_actual
        archivo_a_borrar_si_exito = None
        archivo_creado_a_borrar_si_error = None

        # Lógica para gestionar el archivo
        if self.accion_adjunto == "cambiar" and self.nueva_ruta_archivo:
            try:
                ruta_carpeta_adjuntos = "adjuntos"
                if not os.path.exists(ruta_carpeta_adjuntos):
                    os.makedirs(ruta_carpeta_adjuntos)
                nombre_original, extension = os.path.splitext(os.path.basename(self.nueva_ruta_archivo))
                nombre_unico = f"{nombre_original}_{uuid.uuid4().hex[:8]}{extension}"
                ruta_destino = os.path.join(ruta_carpeta_adjuntos, nombre_unico)
                shutil.copy(self.nueva_ruta_archivo, ruta_destino)
                ruta_db = ruta_destino
                archivo_creado_a_borrar_si_error = ruta_destino
                
                # Marcar el antiguo para borrar SOLO si la DB actualiza bien
                if self.ruta_archivo_adjunto_actual:
                    archivo_a_borrar_si_exito = self.ruta_archivo_adjunto_actual
            except Exception as e:
                logging.error(f"Error gestionando archivo adjunto (modificar): {e}", exc_info=True)
                QMessageBox.critical(self, "Error de Archivo", f"No se pudo guardar el nuevo archivo adjunto.\nVerifica el espacio en disco o permisos.\nDetalle: {e}")
                return
        elif self.accion_adjunto == "quitar":
            if self.ruta_archivo_adjunto_actual:
                archivo_a_borrar_si_exito = self.ruta_archivo_adjunto_actual
            ruta_db = None

        try:
            # 1. Obtener ID del color
            color_id = self.dao_colores.obtener_id_por_hex(color_hex)
            if not color_id:
                QMessageBox.critical(self, "Error BD", "El color seleccionado no se encontró en la base de datos.")
                return
            
            # 2. Preparar datos
            datos_evento = {
                'usuario_id': self.usuario['id_usuario'],
                'titulo': titulo,
                'descripcion': descripcion,
                'fecha_inicio': fecha_nueva,
                'color_id': color_id,
                'archivo_adjunto': ruta_db,
                'es_importante': es_importante,
                'minutos_aviso': minutos_aviso
            }

            # 3. Guardar usando DAO
            id_ev = self.evento['id_evento'] if self.modo == 'editar' else None
            self.dao_eventos.guardar(datos_evento, self.modo, id_ev)
            
            mensaje_exito = "Evento creado correctamente 🎉" if self.modo == 'crear' else "Evento modificado correctamente ✅"

            # --- ÉXITO: Borrar archivo antiguo físico ---
            if archivo_a_borrar_si_exito and os.path.exists(archivo_a_borrar_si_exito):
                try: os.remove(archivo_a_borrar_si_exito)
                except Exception as e: logging.warning(f"No se pudo borrar archivo antiguo: {e}")
            
            QMessageBox.information(self, "Éxito", mensaje_exito)
            self.evento_gestionado.emit()
            self.close()
            
        except mysql.connector.Error as e:
            # --- ERROR: Limpiar archivo nuevo si se creó ---
            if archivo_creado_a_borrar_si_error and os.path.exists(archivo_creado_a_borrar_si_error):
                try: os.remove(archivo_creado_a_borrar_si_error)
                except: pass
            logging.error(f"Error SQL al modificar evento: {e}", exc_info=True)
            QMessageBox.critical(self, "Error al Guardar", f"No se pudieron guardar los cambios en la base de datos.\nDetalle: {e}")

    # ... (Funciones confirmar_eliminar y eliminar_evento sin cambios)
    def confirmar_eliminar(self):
        respuesta = QMessageBox.question(self, 'Confirmar Eliminación',
            "¿Estás seguro de que quieres eliminar este evento? Esta acción es irreversible.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if respuesta == QMessageBox.Yes:
            self.eliminar_evento()

    def eliminar_evento(self):
        # Primero, eliminar el archivo físico si existe
        if self.ruta_archivo_adjunto_actual and os.path.exists(self.ruta_archivo_adjunto_actual):
            try:
                os.remove(self.ruta_archivo_adjunto_actual)
            except Exception as e:
                # No detenemos la eliminación del evento, solo advertimos
                logging.warning(f"No se pudo borrar archivo físico {self.ruta_archivo_adjunto_actual}: {e}")

        try:
            self.dao_eventos.eliminar(self.evento['id_evento'])
            
            QMessageBox.information(self, "Éxito", "Evento eliminado correctamente 🗑️")
            self.evento_gestionado.emit()
            self.close()
            
        except mysql.connector.Error as e:
            logging.error(f"Error SQL al eliminar evento: {e}", exc_info=True)
            QMessageBox.critical(self, "Error al Eliminar", f"No se pudo eliminar el evento de la base de datos.\nDetalle: {e}")