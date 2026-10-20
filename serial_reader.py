"""Hilo lector del puerto serial conectado al ESP32 con sensor RFID.

El firmware envía una línea por lectura con el formato:  RFID:<uid>
Ejemplo: RFID:A1B2C3D4     (115200 baud, USB serial / adaptador CH340, CP210x o FTDI)

Si el ESP32 no está conectado, el dashboard sigue funcionando y puede
usarse el simulador de lectura incluido.
"""
import os
import threading
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pyserial no instalado: el dashboard funciona sin hardware
    serial = None
    list_ports = None

# VID de adaptadores USB-serie más comunes en placas ESP32
_CH340 = 0x1A86
_CP210X = 0x10C4
_FTDI = 0x0403
_ESPRESSIF = 0x303A
VIDS_CONOCIDOS = {_CH340, _CP210X, _FTDI, _ESPRESSIF}

PUERTOS_COMUNES = ['/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyACM0',
                   '/dev/ttyACM1', 'COM3', 'COM4', 'COM5']


def detectar_puerto():
    """Devuelve el primer puerto serial que parezca un ESP32, o None."""
    if list_ports is None:
        return None
    for p in list_ports.comports():
        if p.vid in VIDS_CONOCIDOS:
            return p.device
    for c in PUERTOS_COMUNES:
        if os.path.exists(c):
            return c
    return None


class LectorSerial:
    def __init__(self, puerto=None, baudios=115200, callback=None):
        self.puerto = puerto or os.environ.get('PUERTO_SERIAL') or detectar_puerto()
        self.baudios = baudios
        self.callback = callback  # se invoca con cada UID leído
        self.conectado = False
        self.mensaje = 'Serial sin iniciar'
        self._uid = None
        self._ts = 0.0
        self._lock = threading.Lock()
        self._detener = False
        self._hilo = None

    def iniciar(self):
        if serial is None:
            self.mensaje = ('pyserial no está instalado (pip install -r requirements.txt). '
                            'El dashboard funciona igual con el simulador de lectura.')
            return
        if not self.puerto:
            self.mensaje = 'No se detectó adaptador serial; buscando ESP32…'
        self._hilo = threading.Thread(target=self._loop, daemon=True)
        self._hilo.start()

    def estado(self):
        with self._lock:
            return {
                'uid': self._uid,
                'ts': self._ts,
                'conectado': self.conectado,
                'puerto': self.puerto,
                'mensaje': self.mensaje,
            }

    def leer_manual(self, uid):
        """Registra una lectura como si hubiera llegado por el ESP32 (simulador)."""
        uid = uid.upper()
        with self._lock:
            self._uid = uid
            self._ts = time.time()
        self._notificar(uid)

    # ------------------------------------------------------------------

    def _notificar(self, uid):
        if self.callback:
            try:
                self.callback(uid)
            except Exception:
                # Nunca dejar que un fallo de registro tumbe el hilo serial
                pass

    def _loop(self):
        while not self._detener:
            if not self.puerto:
                self.puerto = detectar_puerto()
                if not self.puerto:
                    self.mensaje = 'Buscando adaptador serial del ESP32…'
                    time.sleep(2)
                    continue
            try:
                with serial.Serial(self.puerto, self.baudios, timeout=1) as sp:
                    self.conectado = True
                    self.mensaje = 'Conectado al ESP32 en %s a %d baud' % (self.puerto, self.baudios)
                    buffer = b''
                    while not self._detener:
                        data = sp.read(64)
                        if not data:
                            continue
                        buffer += data
                        while b'\n' in buffer:
                            linea, buffer = buffer.split(b'\n', 1)
                            self._procesar(linea.decode('utf-8', 'ignore').strip())
            except Exception as exc:
                self.conectado = False
                self.mensaje = 'Error de serial: %s' % exc
                time.sleep(2)

    def _procesar(self, linea):
        if not linea:
            return
        uid = None
        alto = linea.upper()
        if alto.startswith('RFID:'):
            uid = alto.split(':', 1)[1].strip()
        elif all(c in '0123456789ABCDEF:' for c in alto) and len(alto.replace(':', '')) >= 8:
            # Acepta también un UID crudo tipo "A1:B2:C3:D4"
            uid = alto.replace(':', '')
        if not uid:
            return  # mensajes informativos del firmware, p. ej. "Listo para leer RFID"
        with self._lock:
            self._uid = uid
            self._ts = time.time()
        self._notificar(uid)
