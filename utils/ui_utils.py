from PyQt5.QtWidgets import QApplication

def centrar_ventana(window):
    """Centra una ventana en la pantalla principal de forma moderna."""
    qr = window.frameGeometry()
    screen = QApplication.primaryScreen().availableGeometry()
    qr.moveCenter(screen.center())
    window.move(qr.topLeft())