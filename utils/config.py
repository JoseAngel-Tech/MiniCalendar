"""
Archivo para constantes y configuraciones globales.
"""

# Diccionario de colores con nombre y código HEX
COLORES_MAP = {
    "Rojo": "#FF0000",
    "Verde": "#00FF00",
    "Amarillo": "#FFFF00",
    "Naranja": "#FFA500",
    "Cian": "#00FFFF",
    "Rosa": "#FFC0CB",
    "Marrón": "#A52A2A",
    "Gris": "#808080",
    "Blanco": "#FFFFFF",
    "Turquesa": "#40E0D0",
    "Lima": "#00FF7F",
    "Violeta": "#EE82EE",
    "Dorado": "#FFD700",
    "Plateado": "#C0C0C0",
    "Bronce": "#CD7F32"
}

# Mapa inverso para buscar el NOMBRE a partir del HEX
HEX_A_NOMBRE = {v: k for k, v in COLORES_MAP.items()}

# --- CONFIGURACIÓN DE VISUALIZACIÓN ---
CONFIGURACION = {
    "MOSTRAR_SANTOS": True,
    "MOSTRAR_FESTIVOS": True,
    "MOSTRAR_CUMPLEANOS": True,
    "MOSTRAR_NOTAS": True,
    "ESTILO_INTENSO": False,
}

# --- FESTIVOS DETALLADOS (España, Andalucía, Sevilla) ---
# Formato: (Mes, Día): {"nombre": "Nombre", "tipo": "nacional"|"autonomico"|"local"}
FESTIVOS_DATA = {
    # Nacionales (Rojo)
    (1, 1): {"nombre": "Año Nuevo", "tipo": "nacional"},
    (1, 6): {"nombre": "Epifanía del Señor", "tipo": "nacional"},
    (4, 18): {"nombre": "Viernes Santo", "tipo": "nacional"}, # Variable, ejemplo 2025
    (5, 1): {"nombre": "Fiesta del Trabajo", "tipo": "nacional"},
    (8, 15): {"nombre": "Asunción de la Virgen", "tipo": "nacional"},
    (10, 12): {"nombre": "Fiesta Nacional de España", "tipo": "nacional"},
    (11, 1): {"nombre": "Todos los Santos", "tipo": "nacional"},
    (12, 6): {"nombre": "Día de la Constitución", "tipo": "nacional"},
    (12, 8): {"nombre": "Inmaculada Concepción", "tipo": "nacional"},
    (12, 25): {"nombre": "Natividad del Señor", "tipo": "nacional"},
    
    # Autonómicos - Andalucía (Naranja)
    (2, 28): {"nombre": "Día de Andalucía", "tipo": "autonomico"},
    (4, 17): {"nombre": "Jueves Santo", "tipo": "autonomico"}, # Variable
    
    # Locales - Sevilla (Azul Suave)
    (5, 30): {"nombre": "San Fernando", "tipo": "local"}, # Patrón de Sevilla
    (6, 19): {"nombre": "Corpus Christi", "tipo": "local"}, # Variable
}

# Colores para los tipos de festivos
COLORES_FESTIVOS = {
    "nacional": "#e74c3c",    # Rojo
    "autonomico": "#e67e22",  # Naranja
    "local": "#3498db"        # Azul suave
}