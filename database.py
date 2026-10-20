"""Base de datos SQLite: conexión, esquema y datos iniciales de ejemplo."""
import os
import sqlite3
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('DB_PATH', os.path.join(BASE_DIR, 'prestamos.db'))
SCHEMA_PATH = os.path.join(BASE_DIR, 'schema.sql')
FMT = '%Y-%m-%d %H:%M:%S'


def ahora():
    return datetime.now().strftime(FMT)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    """Crea las tablas (si no existen) y si la BD está vacía carga datos de ejemplo."""
    conn = get_conn()
    with open(SCHEMA_PATH, encoding='utf-8') as fh:
        conn.executescript(fh.read())
    conn.commit()
    if conn.execute('SELECT COUNT(*) AS n FROM personas').fetchone()['n'] == 0:
        _sembrar_ejemplo(conn)
    conn.close()


# ---------------------------------------------------------------------------
# Datos de ejemplo
# ---------------------------------------------------------------------------

def _sembrar_ejemplo(conn):
    ahora_dt = datetime.now()

    equipos = [
        ('Oxímetro de pulso', 'Diagnóstico', 'A1B2C3D4', 'Ubicación: enfermería'),
        ('Tensiómetro digital', 'Diagnóstico', 'B2C3D4E5', 'Incluye manguito adulto'),
        ('Bomba de infusión', 'Infusión', 'C3D4E5F6', 'Revisar nivel de batería'),
        ('Nebulizador', 'Respiratorio', 'D4E5F6A7', ''),
        ('Aspirador de secreciones', 'Respiratorio', 'E5F6A7B8', 'Manguera esterilizable'),
        ('Glucómetro', 'Diagnóstico', 'F6A7B8C9', 'Incluye tiras reactivas'),
        ('Electrocardiógrafo portátil', 'Diagnóstico', '1A2B3C4D', 'Equipo costoso, requiere justificación'),
    ]
    personas = [
        ('Dra. María López', 'medico', 'MED-1001'),
        ('Dr. Carlos Ramírez', 'medico', 'MED-1002'),
        ('Dr. Javier Ortiz', 'medico', 'MED-1003'),
        ('Enf. Ana García', 'enfermero', 'ENF-2001'),
        ('Enf. Luis Herrera', 'enfermero', 'ENF-2002'),
        ('Enf. Sofía Márquez', 'enfermero', 'ENF-2003'),
    ]
    conn.executemany(
        'INSERT INTO equipos (nombre, categoria, uid_rfid, notas) VALUES (?,?,?,?)',
        equipos)
    conn.executemany(
        'INSERT INTO personas (nombre, rol, cedula) VALUES (?,?,?)',
        personas)

    eq = {r['nombre']: r['id'] for r in conn.execute('SELECT id, nombre FROM equipos')}
    pe = {r['nombre']: r['id'] for r in conn.execute('SELECT id, nombre FROM personas')}

    def ts(dt):
        return dt.strftime(FMT)

    def historial(equipo, anterior, nuevo, motivo, cuando):
        conn.execute(
            'INSERT INTO historial_estados (equipo_id, estado_anterior, estado_nuevo, motivo, cambio_en) VALUES (?,?,?,?,?)',
            (eq[equipo], anterior, nuevo, motivo, ts(cuando)))

    # 1) Préstamo activo sin vencer: bomba de infusión → Enf. Ana García
    p1 = ahora_dt - timedelta(days=1)
    conn.execute(
        'INSERT INTO prestamos (equipo_id, persona_id, fecha_prestamo, fecha_limite, notas_prestamo) VALUES (?,?,?,?,?)',
        (eq['Bomba de infusión'], pe['Enf. Ana García'], ts(p1), ts(p1 + timedelta(days=3)), 'Cama 12'))
    historial('Bomba de infusión', 'disponible', 'prestado', 'Prestado a Enf. Ana García', p1)

    # 2) Préstamo VENCIDO: aspirador → Dra. María López (límite ayer)
    p2 = ahora_dt - timedelta(days=4)
    conn.execute(
        'INSERT INTO prestamos (equipo_id, persona_id, fecha_prestamo, fecha_limite, notas_prestamo) VALUES (?,?,?,?,?)',
        (eq['Aspirador de secreciones'], pe['Dra. María López'], ts(p2),
         ts(ahora_dt - timedelta(days=1)), 'Urgencias, cama 3'))
    historial('Aspirador de secreciones', 'disponible', 'prestado', 'Prestado a Dra. María López', p2)

    # 3) Préstamo ya devuelto: nebulizador → Dr. Carlos Ramírez
    p3 = ahora_dt - timedelta(days=6)
    d3 = ahora_dt - timedelta(days=2)
    conn.execute(
        'INSERT INTO prestamos (equipo_id, persona_id, fecha_prestamo, fecha_limite, fecha_devolucion, notas_prestamo, notas_devolucion) VALUES (?,?,?,?,?,?,?)',
        (eq['Nebulizador'], pe['Dr. Carlos Ramírez'], ts(p3), ts(p3 + timedelta(days=5)), ts(d3),
         'Consulta externa', 'Equipo limpio y funcional'))
    historial('Nebulizador', 'disponible', 'prestado', 'Prestado a Dr. Carlos Ramírez', p3)
    historial('Nebulizador', 'prestado', 'disponible', 'Devuelto por Dr. Carlos Ramírez', d3)

    conn.commit()


# ---------------------------------------------------------------------------
# Consultas y operaciones usadas por la app
# ---------------------------------------------------------------------------

def buscar_equipo_por_uid(uid):
    conn = get_conn()
    fila = conn.execute(
        'SELECT * FROM equipos WHERE UPPER(uid_rfid) = ?', (uid.upper(),)).fetchone()
    conn.close()
    return fila


def obtener_prestamo_pendiente(equipo_id):
    conn = get_conn()
    fila = conn.execute(
        'SELECT * FROM prestamos WHERE equipo_id = ? AND fecha_devolucion IS NULL '
        'ORDER BY fecha_prestamo DESC LIMIT 1', (equipo_id,)).fetchone()
    conn.close()
    return fila


def registrar_evento_rfid(uid, equipo_id=None, resultado='lectura'):
    conn = get_conn()
    conn.execute(
        'INSERT INTO eventos_rfid (uid, equipo_id, resultado, recibido_en) VALUES (?,?,?,?)',
        (uid, equipo_id, resultado, ahora()))
    conn.commit()
    conn.close()


def registrar_prestamo(equipo_id, persona_id, fecha_limite=None, notas=''):
    """Devuelve (prestamo_id, None) o (None, mensaje_de_error)."""
    conn = get_conn()
    try:
        pend = conn.execute(
            'SELECT id FROM prestamos WHERE equipo_id = ? AND fecha_devolucion IS NULL LIMIT 1',
            (equipo_id,)).fetchone()
        if pend:
            return None, 'Ese equipo ya tiene un préstamo activo.'
        eq = conn.execute('SELECT nombre FROM equipos WHERE id = ? AND activo = 1',
                          (equipo_id,)).fetchone()
        if not eq:
            return None, 'Equipo no encontrado o inactivo.'
        pe = conn.execute('SELECT nombre FROM personas WHERE id = ? AND activo = 1',
                          (persona_id,)).fetchone()
        if not pe:
            return None, 'Persona no encontrada o inactiva.'
        cur = conn.execute(
            'INSERT INTO prestamos (equipo_id, persona_id, fecha_prestamo, fecha_limite, notas_prestamo) '
            'VALUES (?,?,?,?,?)',
            (equipo_id, persona_id, ahora(), fecha_limite or None, notas or None))
        conn.execute(
            'INSERT INTO historial_estados (equipo_id, estado_anterior, estado_nuevo, motivo, cambio_en) '
            'VALUES (?,?,?,?,?)',
            (equipo_id, 'disponible', 'prestado', 'Prestado a ' + pe['nombre'], ahora()))
        conn.commit()
        return cur.lastrowid, None
    finally:
        conn.close()


def registrar_devolucion(prestamo_id, notas=None):
    """Devuelve (info_dict, None) o (None, mensaje_de_error)."""
    conn = get_conn()
    try:
        fila = conn.execute(
            'SELECT pr.*, e.nombre AS equipo, p.nombre AS persona '
            'FROM prestamos pr '
            'JOIN equipos e ON e.id = pr.equipo_id '
            'JOIN personas p ON p.id = pr.persona_id '
            'WHERE pr.id = ?', (prestamo_id,)).fetchone()
        if not fila:
            return None, 'Préstamo no encontrado.'
        if fila['fecha_devolucion']:
            return None, 'Ese préstamo ya fue devuelto.'
        conn.execute(
            'UPDATE prestamos SET fecha_devolucion = ?, notas_devolucion = ? WHERE id = ?',
            (ahora(), notas or None, prestamo_id))
        conn.execute(
            'INSERT INTO historial_estados (equipo_id, estado_anterior, estado_nuevo, motivo, cambio_en) '
            'VALUES (?,?,?,?,?)',
            (fila['equipo_id'], 'prestado', 'disponible',
             'Devuelto por ' + fila['persona'], ahora()))
        conn.commit()
        return dict(fila), None
    finally:
        conn.close()
