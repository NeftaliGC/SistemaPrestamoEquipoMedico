-- Esquema de la base de datos del sistema de préstamo de equipo médico
PRAGMA foreign_keys = ON;

-- Personal habilitado para recibir préstamos (médicos y enfermeros)
CREATE TABLE IF NOT EXISTS personas (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    rol    TEXT NOT NULL CHECK (rol IN ('medico', 'enfermero')),
    cedula TEXT UNIQUE,
    activo INTEGER NOT NULL DEFAULT 1
);

-- Equipos médicos; cada uno tiene un tag RFID asociado (UID)
CREATE TABLE IF NOT EXISTS equipos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre    TEXT NOT NULL,
    categoria TEXT NOT NULL DEFAULT 'General',
    uid_rfid  TEXT NOT NULL UNIQUE,
    notas     TEXT,
    activo    INTEGER NOT NULL DEFAULT 1
);

-- Préstamos: un registro por cada salida de equipo.
-- fecha_devolucion NULL significa préstamo activo (pendiente).
CREATE TABLE IF NOT EXISTS prestamos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    equipo_id         INTEGER NOT NULL REFERENCES equipos(id),
    persona_id        INTEGER NOT NULL REFERENCES personas(id),
    fecha_prestamo    TEXT NOT NULL,
    fecha_limite      TEXT,
    fecha_devolucion  TEXT,
    notas_prestamo    TEXT,
    notas_devolucion  TEXT
);

CREATE INDEX IF NOT EXISTS idx_prestamos_activos
    ON prestamos(equipo_id, fecha_devolucion);

-- Log de cada lectura del lector RFID (incluye lecturas de prueba)
CREATE TABLE IF NOT EXISTS eventos_rfid (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uid         TEXT NOT NULL,
    equipo_id   INTEGER REFERENCES equipos(id),
    resultado   TEXT NOT NULL,
    recibido_en TEXT NOT NULL
);

-- Auditoría de cambios de estado de cada equipo
CREATE TABLE IF NOT EXISTS historial_estados (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    equipo_id     INTEGER NOT NULL REFERENCES equipos(id),
    estado_anterior TEXT NOT NULL,
    estado_nuevo  TEXT NOT NULL,
    motivo        TEXT,
    cambio_en     TEXT NOT NULL
);
