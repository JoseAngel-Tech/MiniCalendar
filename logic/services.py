import urllib.request
import urllib.error
import json
import logging

class ClimaService:
    @staticmethod
    def obtener_pronostico_sevilla():
        try:
            url = "https://api.open-meteo.com/v1/forecast?latitude=37.38&longitude=-5.98&current_weather=true&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=auto"
            with urllib.request.urlopen(url, timeout=5) as response:
                return json.loads(response.read().decode())
        except Exception as e:
            logging.error(f"Error servicio clima: {e}")
            raise e