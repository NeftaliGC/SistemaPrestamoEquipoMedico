# Sistema de Préstamo de Equipo Médico

Dashboard web para registrar préstamos de equipo médico entre médicos y
enfermeros, con identificación del equipo por **tag RFID** leído por un
**ESP32 + MFRC522** conectado por **puerto serial USB**.

## Requisitos

- Python 3.8+
- Placa ESP32 con lector MFRC522 y tags RFID (MIFARE Classic o compatibles)

## Instalación

```bash
pip install -r requirements.txt
python app.py
```

Abra **http://localhost:5000**. La base de datos `prestamos.db` se crea
automáticamente con datos de ejemplo (7 equipos, 6 personas, 3 préstamos).

## Uso del dashboard

1. **Registrar préstamo**: elija a la persona, selecciónelo el equipo en la
   lista **o** deje «Escanear tag RFID» y acerque el tag; opcionalmente ponga
   una fecha límite.
2. **Registrar devolución**: pulse «Escanear tag para devolver» y acerque el
   tag del equipo, o use el botón «Devolver» de la tabla de préstamos activos.
3. Los equipos **vencidos** (fecha límite pasada) se resaltan en rojo.
4. Pestañas **Equipos** y **Personal**: alta, edición y baja lógica. Cada
   equipo lleva su UID RFID único.

### Simulador RFID

Si el ESP32 aún no está conectado, use el campo «Simular lectura RFID» del
dashboard: escriba un UID (p. ej. `A1B2C3D4`) y pulse «Enviar». El sistema lo
trata como una lectura real.

## Firmware ESP32 (PlatformIO)

El firmware vive en `firmware/esp32_rc522/` como proyecto **PlatformIO**
(`platformio.ini` + `src/main.cpp`; la librería MFRC522 se descarga sola).
Soporta tres variantes de placa — elija la de su placa al subir:

```bash
cd firmware/esp32_rc522
pio run -e esp32s3-supermini -t upload   # ESP32-S3 SuperMini  ← placa de este proyecto
pio run -e esp32-supermini   -t upload   # ESP32 Super Mini clásico (WROOM-32E)
pio run -e esp32c3-supermini -t upload   # ESP32-C3 SuperMini
pio device monitor                        # ver las lecturas a 115200 baud
```

Conexiones al MFRC522:

| MFRC522 | Super Mini clásico | ESP32-C3 | ESP32-S3 |
|---------|--------------------|----------|----------|
| VCC     | 3V3                | 3V3      | 3V3      |
| GND     | GND                | GND      | GND      |
| SCK     | GPIO18             | GPIO4    | GPIO12   |
| MISO    | GPIO19             | GPIO5    | GPIO13   |
| MOSI    | GPIO23             | GPIO6    | GPIO11   |
| SDA     | GPIO5              | GPIO7    | GPIO10   |
| RST     | GPIO4              | GPIO10   | GPIO9    |

- En el **C3**, GPIO18/19 quedan libres porque los ocupa el USB nativo.
- En el **S3**, GPIO19/20 son el USB nativo (no tiene puente serial: el
  firmware envía `Serial` por el propio USB con CDC on boot); se evitan
  también los pines de arranque 0/3/45/46 y 33-37 (PSRAM octal).

| MFRC522 | ESP32      |
|---------|------------|
| VCC     | 3V3        |
| GND     | GND        |
| SCK     | GPIO18     |
| MISO    | GPIO19     |
| MOSI    | GPIO23     |
| SDA     | GPIO5      |
| RST     | GPIO4      |

El firmware envía `RFID:<UID>` por USB serial a **115200 baud** cada vez que
se acerca un tag. El dashboard detecta el puerto automáticamente (CH340,
CP210x, FTDI o ESPRESSIF). Para forzar un puerto: `PUERTO_SERIAL=/dev/ttyUSB0 python app.py`.

## Base de datos (SQLite)

| Tabla              | Contenido                                             |
|--------------------|-------------------------------------------------------|
| `personas`         | Médicos y enfermeros (nombre, rol, cédula, activo)    |
| `equipos`          | Equipos con su `uid_rfid` único                       |
| `prestamos`        | Préstamos con fechas y notas; `fecha_devolucion NULL` = activo |
| `eventos_rfid`     | Log de cada lectura del lector                        |
| `historial_estados`| Auditoría de cambios disponible ↔ prestado            |

## Variables de entorno

| Variable        | Uso                                        |
|-----------------|--------------------------------------------|
| `PUERTO_SERIAL` | Forzar puerto serial del ESP32             |
| `PUERTO`        | Puerto del servidor web (default 5000)     |
| `DB_PATH`       | Ruta alternativa del archivo SQLite        |
| `CLAVE_SECRETA` | Secreto de Flask (cambiar en producción)   |
