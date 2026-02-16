import sys
import logging
import re
from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QDialog,
    QVBoxLayout, QHBoxLayout, QMessageBox, QApplication, QDesktopWidget
)
from PyQt5.QtCore import pyqtSignal, Qt
# Importamos las clases necesarias de otros archivos
from database.dao import UsuariosDAO
import mysql.connector 

class VentanaRegistro(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crear Nueva Cuenta")
        self.setFixedSize(320, 380) # Aumentamos altura para el feedback
        self.setStyleSheet("background-color: #fdfdfd;")
        
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(30, 30, 30, 30)

        # Título
        lbl_titulo = QLabel("Registro de Usuario")
        lbl_titulo.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; margin-bottom: 10px;")
        lbl_titulo.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_titulo)

        # Campos
        self.input_nombre = QLineEdit()
        self.input_nombre.setPlaceholderText("Nombre completo")
        
        self.input_email = QLineEdit()
        self.input_email.setPlaceholderText("Correo electrónico")
        
        self.input_pass = QLineEdit()
        self.input_pass.setPlaceholderText("Contraseña")
        self.input_pass.setEchoMode(QLineEdit.Password)
        # Conectamos el cambio de texto a la validación en tiempo real
        self.input_pass.textChanged.connect(self.validar_password)

        layout.addWidget(self.input_nombre)
        layout.addWidget(self.input_email)
        layout.addWidget(self.input_pass)

        # Etiqueta de Feedback para la contraseña
        self.lbl_feedback = QLabel("")
        self.lbl_feedback.setWordWrap(True)
        self.lbl_feedback.setStyleSheet("font-size: 11px; color: #e74c3c;")
        layout.addWidget(self.lbl_feedback)

        # Botón Registrar
        self.btn_registrar = QPushButton("Crear Cuenta")
        self.btn_registrar.setCursor(Qt.PointingHandCursor)
        self.btn_registrar.setEnabled(False) # Deshabilitado por defecto
        self.btn_registrar.setStyleSheet("""
            QPushButton { background-color: #95a5a6; color: white; font-weight: bold; padding: 8px; border-radius: 4px; }
        """)
        self.btn_registrar.clicked.connect(self.registrar_usuario)
        layout.addWidget(self.btn_registrar)

        self.setLayout(layout)

    def validar_password(self):
        password = self.input_pass.text()
        errores = []

        # Reglas de validación
        if len(password) < 8:
            errores.append("• Mínimo 8 caracteres")
        if not re.search(r"[A-Z]", password):
            errores.append("• Al menos una mayúscula")
        if not re.search(r"\d", password):
            errores.append("• Al menos un número")
        
        if errores:
            self.lbl_feedback.setText("\n".join(errores))
            self.lbl_feedback.setStyleSheet("font-size: 11px; color: #e74c3c;") # Rojo
            self.btn_registrar.setEnabled(False)
            self.btn_registrar.setStyleSheet("""
                QPushButton { background-color: #95a5a6; color: white; font-weight: bold; padding: 8px; border-radius: 4px; }
            """)
        else:
            self.lbl_feedback.setText("✅ Contraseña segura")
            self.lbl_feedback.setStyleSheet("font-size: 11px; color: #27ae60; font-weight: bold;") # Verde
            self.btn_registrar.setEnabled(True)
            self.btn_registrar.setStyleSheet("""
                QPushButton { background-color: #3498db; color: white; font-weight: bold; padding: 8px; border-radius: 4px; }
                QPushButton:hover { background-color: #2980b9; }
            """)

    def registrar_usuario(self):
        nombre = self.input_nombre.text().strip()
        email = self.input_email.text().strip()
        password = self.input_pass.text().strip()

        if not nombre or not email or not password:
            QMessageBox.warning(self, "Faltan datos", "Por favor, completa todos los campos.")
            return

        dao = UsuariosDAO()
        exito, mensaje = dao.registrar(nombre, email, password)
        
        if exito:
            QMessageBox.information(self, "¡Bienvenido!", f"{mensaje}\nAhora puedes iniciar sesión con tu nueva cuenta.")
            self.accept() # Cierra el diálogo
        else:
            QMessageBox.warning(self, "Error", mensaje)

class VentanaLogin(QWidget):
    # Señal que se emitirá con los datos del usuario tras un login exitoso
    login_exitoso = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MiniCalendar - Iniciar Sesión")
        self.setFixedSize(350, 320) # Aumentamos altura para el nuevo botón
        self.centrar_ventana()

        # Etiquetas y campos
        self.label_usuario = QLabel("Email:")
        self.input_usuario = QLineEdit()
        self.input_usuario.setPlaceholderText("ejemplo@email.com")
        self.label_password = QLabel("Contraseña:")
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)

        # Botón para mostrar/ocultar contraseña (ojo)
        self.toggle_password_button = QPushButton('👁️')
        self.toggle_password_button.setCheckable(True)
        self.toggle_password_button.setFixedSize(28, 28)
        self.toggle_password_button.setStyleSheet("QPushButton { border: none; background-color: transparent; }")
        self.toggle_password_button.setCursor(Qt.PointingHandCursor)
        self.toggle_password_button.clicked.connect(self.toggle_password_visibility)

        # Layout horizontal para el campo de contraseña y el botón
        password_layout = QHBoxLayout()
        password_layout.setContentsMargins(0, 0, 0, 0)
        password_layout.setSpacing(0)
        password_layout.addWidget(self.input_password)
        password_layout.addWidget(self.toggle_password_button)

        # Layout horizontal para el email (para igualar ancho visual con contraseña)
        email_layout = QHBoxLayout()
        email_layout.setContentsMargins(0, 0, 0, 0)
        email_layout.setSpacing(0)
        email_layout.addWidget(self.input_usuario)
        email_layout.addSpacing(28) # Mismo ancho que el botón de ojo para equilibrar

        # Botón de login
        self.boton_login = QPushButton("Iniciar Sesión")
        self.boton_login.setCursor(Qt.PointingHandCursor)
        self.boton_login.setStyleSheet("""
            QPushButton { background-color: #3498db; color: white; font-weight: bold; padding: 5px; border-radius: 4px; min-height: 30px; }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.boton_login.clicked.connect(self.verificar_login)

        # Botón de acceso invitado (Para entrevistadores/demo)
        self.boton_invitado = QPushButton("👤 Acceso Invitado (Demo)")
        self.boton_invitado.setCursor(Qt.PointingHandCursor)
        self.boton_invitado.setStyleSheet("""
            QPushButton { background-color: #27ae60; color: white; font-weight: bold; padding: 5px; border-radius: 4px; min-height: 30px; }
            QPushButton:hover { background-color: #2ecc71; }
        """)
        self.boton_invitado.clicked.connect(self.entrar_invitado)

        # Botón Registrarse (Nuevo)
        self.boton_registro = QPushButton("¿No tienes cuenta? Regístrate")
        self.boton_registro.setCursor(Qt.PointingHandCursor)
        self.boton_registro.setStyleSheet("""
            QPushButton { background-color: transparent; color: #3498db; text-decoration: underline; border: none; }
            QPushButton:hover { color: #2980b9; }
        """)
        self.boton_registro.clicked.connect(self.abrir_registro)

        # Layout
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(4)
        
        layout.addWidget(self.label_usuario)
        layout.addLayout(email_layout)
        layout.addSpacing(15)
        layout.addWidget(self.label_password)
        layout.addLayout(password_layout)
        layout.addSpacing(20)
        layout.addWidget(self.boton_login)
        layout.addSpacing(5)
        layout.addWidget(self.boton_invitado)
        layout.addSpacing(10)
        layout.addWidget(self.boton_registro)
        self.setLayout(layout)

    def toggle_password_visibility(self, checked):
        if checked:
            self.input_password.setEchoMode(QLineEdit.Normal)
            self.toggle_password_button.setText('🙈')
        else:
            self.input_password.setEchoMode(QLineEdit.Password)
            self.toggle_password_button.setText('👁️')

    def centrar_ventana(self):
        """Centra la ventana en la pantalla."""
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def abrir_registro(self):
        dialogo = VentanaRegistro(self)
        dialogo.exec_()

    def verificar_login(self):
        email = self.input_usuario.text().strip()
        password = self.input_password.text().strip()
        
        dao = UsuariosDAO()

        try:
            usuario = dao.autenticar(email, password)
            
            if usuario:
                # En lugar de abrir la ventana aquí, emitimos una señal
                # y dejamos que el script principal (main.py) gestione la transición.
                self.login_exitoso.emit(usuario)
                self.close() # Cerramos la ventana de login
            else:
                QMessageBox.warning(self, "Error", "¡ATENCIÓN! Usuario o contraseña incorrectos.")
                
        except mysql.connector.Error as e:
            logging.error(f"Error SQL en Login: {e}", exc_info=True)
            QMessageBox.critical(self, "Error de Base de Datos", f"Error al intentar iniciar sesión.\nDetalle técnico: {e}")
        except Exception as e:
            logging.critical(f"Error inesperado en Login: {e}", exc_info=True)
            QMessageBox.critical(self, "Error Inesperado", f"Ha ocurrido un error desconocido.\nDetalle: {e}")

    def entrar_invitado(self):
        dao = UsuariosDAO()
        try:
            usuario = dao.login_invitado()
            if usuario:
                # Creamos un mensaje personalizado para quitar el icono azul predeterminado
                msg = QMessageBox(self)
                msg.setWindowTitle("Modo Demo")
                msg.setText("<span style='font-size: 20pt;'>📅</span> Bienvenido, puedes explorar las funcionalidades de MiniCalendar")
                msg.setIcon(QMessageBox.NoIcon) # Esto borra el icono de interrogación/información
                msg.exec_()
                self.login_exitoso.emit(usuario)
                self.close()
            else:
                QMessageBox.warning(self, "Error", "No se pudo iniciar el modo invitado.")
        except Exception as e:
            logging.error(f"Error en acceso invitado: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Fallo al entrar como invitado.\n{e}")
