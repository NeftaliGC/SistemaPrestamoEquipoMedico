"""Dashboard de préstamo de equipo médico (Flask + SQLite + ESP32 por serial).

Ejecutar:  python app.py   →  http://localhost:5000
"""
import os
from datetime import datetime

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

import database as db
from serial_reader import LectorSerial

app = Flask(__name__)
app.secret_key = os.environ.get('CLAVE_SECRETA', 'cambiar-esta-clave-en-produccion')


# ---------------------------------------------------------------------------
# Lector RFID por serial (ESP32 + RC522)
# ---------------------------------------------------------------------------

def al_leer_uid(uid):
    """Se ejecuta con cada lectura (hilo serial o simulador) para registrarla."""
    eq = db.buscar_equipo_por_uid(uid)
    if eq:
        db.registrar_evento_rfid(uid, eq['id'], 'Equipo reconocido')
    else:
        db.registrar_evento_rfid(uid, None, 'UID desconocido')


lector = LectorSerial(callback=al_leer_uid)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hoy():
    return datetime.now().strftime('%Y-%m-%d')


def _equipos_con_estado():
    """Equipos con su préstamo activo (si lo tienen) y si están vencidos."""
    conn = db.get_conn()
    filas = conn.execute('''
        SELECT e.id, e.nombre, e.categoria, e.uid_rfid, e.notas, e.activo,
               pr.id AS prestamo_id, pr.fecha_prestamo, pr.fecha_limite,
               p.nombre AS prestamista, p.rol AS rol_prestamista
        FROM equipos e
        LEFT JOIN prestamos pr ON pr.equipo_id = e.id AND pr.fecha_devolucion IS NULL
        LEFT JOIN personas p ON p.id = pr.persona_id
        WHERE e.activo = 1
        ORDER BY e.nombre
    ''').fetchall()
    conn.close()
    hoy = _hoy()
    equipos = []
    for f in filas:
        d = dict(f)
        d['prestado'] = d['prestamo_id'] is not None
        d['vencido'] = bool(d['prestado'] and d['fecha_limite']
                            and d['fecha_limite'][:10] < hoy)
        equipos.append(d)
    return equipos


# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    conn = db.get_conn()
    personas = [dict(r) for r in conn.execute(
        'SELECT id, nombre, rol FROM personas WHERE activo = 1 ORDER BY nombre').fetchall()]
    conn.close()
    return render_template('dashboard.html',
                           equipos=_equipos_con_estado(),
                           personas=personas)


@app.route('/prestamos')
def prestamos():
    equipo_id = request.args.get('equipo_id', type=int)
    persona_id = request.args.get('persona_id', type=int)

    conn = db.get_conn()
    q = '''SELECT pr.*, e.nombre AS equipo, e.uid_rfid,
                  p.nombre AS persona, p.rol
           FROM prestamos pr
           JOIN equipos e ON e.id = pr.equipo_id
           JOIN personas p ON p.id = pr.persona_id'''
    condiciones, params = [], []
    if equipo_id:
        condiciones.append('pr.equipo_id = ?')
        params.append(equipo_id)
    if persona_id:
        condiciones.append('pr.persona_id = ?')
        params.append(persona_id)
    if condiciones:
        q += ' WHERE ' + ' AND '.join(condiciones)
    q += ' ORDER BY pr.fecha_prestamo DESC'
    filas = [dict(r) for r in conn.execute(q, params).fetchall()]

    equipos = [dict(r) for r in conn.execute(
        'SELECT id, nombre FROM equipos WHERE activo = 1 ORDER BY nombre').fetchall()]
    personas = [dict(r) for r in conn.execute(
        'SELECT id, nombre, rol FROM personas ORDER BY nombre').fetchall()]
    historial = [dict(r) for r in conn.execute('''
        SELECT h.*, e.nombre AS equipo
        FROM historial_estados h JOIN equipos e ON e.id = h.equipo_id
        ORDER BY h.id DESC LIMIT 50''').fetchall()]
    eventos = [dict(r) for r in conn.execute('''
        SELECT ev.*, e.nombre AS equipo
        FROM eventos_rfid ev LEFT JOIN equipos e ON e.id = ev.equipo_id
        ORDER BY ev.id DESC LIMIT 20''').fetchall()]
    conn.close()

    hoy = _hoy()
    for p in filas:
        p['estado'] = 'pendiente' if not p['fecha_devolucion'] else 'devuelto'
        p['vencido'] = bool(p['estado'] == 'pendiente' and p['fecha_limite']
                            and p['fecha_limite'][:10] < hoy)

    return render_template('prestamos.html', prestamos=filas, equipos=equipos,
                           personas=personas, historial=historial, eventos=eventos,
                           filtro_equipo=equipo_id, filtro_persona=persona_id)


@app.route('/equipos', methods=['GET', 'POST'])
def equipos_pagina():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        categoria = request.form.get('categoria', '').strip() or 'General'
        uid = request.form.get('uid_rfid', '').strip().upper()
        notas = request.form.get('notas', '').strip()
        if not nombre or not uid:
            flash('Nombre y UID RFID son obligatorios.', 'error')
        else:
            conn = db.get_conn()
            try:
                conn.execute(
                    'INSERT INTO equipos (nombre, categoria, uid_rfid, notas) VALUES (?,?,?,?)',
                    (nombre, categoria, uid, notas))
                conn.commit()
                flash('Equipo "%s" registrado con el UID %s.' % (nombre, uid), 'exito')
            except Exception:
                flash('No se pudo guardar: el UID RFID ya está en uso.', 'error')
            finally:
                conn.close()
        return redirect(url_for('equipos_pagina'))

    conn = db.get_conn()
    hoy = _hoy()
    equipos = [dict(r) for r in conn.execute('''
        SELECT e.*,
               pr.id AS prestamo_id, pr.fecha_prestamo, pr.fecha_limite,
               p.nombre AS prestamista
        FROM equipos e
        LEFT JOIN prestamos pr ON pr.equipo_id = e.id AND pr.fecha_devolucion IS NULL
        LEFT JOIN personas p ON p.id = pr.persona_id
        ORDER BY e.activo DESC, e.nombre''').fetchall()]
    conn.close()
    for e in equipos:
        e['prestado'] = e['prestamo_id'] is not None
        e['vencido'] = bool(e['prestado'] and e['fecha_limite']
                            and e['fecha_limite'][:10] < hoy)
    return render_template('equipos.html', equipos=equipos)


@app.route('/equipos/<int:equipo_id>/editar', methods=['POST'])
def equipo_editar(equipo_id):
    nombre = request.form.get('nombre', '').strip()
    categoria = request.form.get('categoria', '').strip() or 'General'
    uid = request.form.get('uid_rfid', '').strip().upper()
    notas = request.form.get('notas', '').strip()
    if not nombre or not uid:
        flash('Nombre y UID RFID son obligatorios.', 'error')
    else:
        conn = db.get_conn()
        try:
            conn.execute(
                'UPDATE equipos SET nombre = ?, categoria = ?, uid_rfid = ?, notas = ? WHERE id = ?',
                (nombre, categoria, uid, notas, equipo_id))
            conn.commit()
            flash('Equipo actualizado.', 'exito')
        except Exception:
            flash('No se pudo actualizar: el UID RFID ya está en uso por otro equipo.', 'error')
        finally:
            conn.close()
    return redirect(url_for('equipos_pagina'))


@app.route('/equipos/<int:equipo_id>/toggle', methods=['POST'])
def equipo_toggle(equipo_id):
    conn = db.get_conn()
    equipo = conn.execute('SELECT nombre, activo FROM equipos WHERE id = ?',
                          (equipo_id,)).fetchone()
    if equipo:
        nuevo = 0 if equipo['activo'] else 1
        if nuevo == 1:
            pend = conn.execute(
                'SELECT COUNT(*) AS n FROM prestamos WHERE equipo_id = ? AND fecha_devolucion IS NULL',
                (equipo_id,)).fetchone()
            if pend['n']:
                flash('No se puede dar de baja: el equipo tiene un préstamo activo.', 'error')
                conn.close()
                return redirect(url_for('equipos_pagina'))
        conn.execute('UPDATE equipos SET activo = ? WHERE id = ?', (nuevo, equipo_id))
        conn.commit()
        flash('Equipo %s.' % ('dado de alta' if nuevo else 'dado de baja'), 'exito')
    conn.close()
    return redirect(url_for('equipos_pagina'))


@app.route('/personas', methods=['GET', 'POST'])
def personas_pagina():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        rol = request.form.get('rol', '').strip()
        cedula = request.form.get('cedula', '').strip() or None
        if not nombre or rol not in ('medico', 'enfermero'):
            flash('Nombre y rol válido (médico o enfermero) son obligatorios.', 'error')
        else:
            conn = db.get_conn()
            try:
                conn.execute(
                    'INSERT INTO personas (nombre, rol, cedula) VALUES (?,?,?)',
                    (nombre, rol, cedula))
                conn.commit()
                flash('%s registrado.' % nombre, 'exito')
            except Exception:
                flash('No se pudo guardar: la cédula ya está en uso.', 'error')
            finally:
                conn.close()
        return redirect(url_for('personas_pagina'))

    conn = db.get_conn()
    personas = [dict(r) for r in conn.execute('''
        SELECT p.*,
               (SELECT COUNT(*) FROM prestamos pr WHERE pr.persona_id = p.id) AS total_prestamos,
               (SELECT COUNT(*) FROM prestamos pr
                WHERE pr.persona_id = p.id AND pr.fecha_devolucion IS NULL) AS pendientes
        FROM personas p
        ORDER BY p.activo DESC, p.nombre''').fetchall()]
    conn.close()
    return render_template('personas.html', personas=personas)


@app.route('/personas/<int:persona_id>/editar', methods=['POST'])
def persona_editar(persona_id):
    nombre = request.form.get('nombre', '').strip()
    rol = request.form.get('rol', '').strip()
    cedula = request.form.get('cedula', '').strip() or None
    if not nombre or rol not in ('medico', 'enfermero'):
        flash('Nombre y rol válido son obligatorios.', 'error')
    else:
        conn = db.get_conn()
        try:
            conn.execute('UPDATE personas SET nombre = ?, rol = ?, cedula = ? WHERE id = ?',
                         (nombre, rol, cedula, persona_id))
            conn.commit()
            flash('Persona actualizada.', 'exito')
        except Exception:
            flash('No se pudo actualizar: la cédula ya está en uso.', 'error')
        finally:
            conn.close()
    return redirect(url_for('personas_pagina'))


@app.route('/personas/<int:persona_id>/toggle', methods=['POST'])
def persona_toggle(persona_id):
    conn = db.get_conn()
    persona = conn.execute('SELECT nombre, activo FROM personas WHERE id = ?',
                           (persona_id,)).fetchone()
    if persona:
        nuevo = 0 if persona['activo'] else 1
        if nuevo == 1:
            pend = conn.execute(
                'SELECT COUNT(*) AS n FROM prestamos WHERE persona_id = ? AND fecha_devolucion IS NULL',
                (persona_id,)).fetchone()
            if pend['n']:
                flash('No se puede dar de baja: la persona tiene préstamos activos.', 'error')
                conn.close()
                return redirect(url_for('personas_pagina'))
        conn.execute('UPDATE personas SET activo = ? WHERE id = ?', (nuevo, persona_id))
        conn.commit()
        flash('%s %s.' % (persona['nombre'], 'activado' if nuevo else 'desactivado'), 'exito')
    conn.close()
    return redirect(url_for('personas_pagina'))


# ---------------------------------------------------------------------------
# API JSON (usada por el dashboard vía JavaScript)
# ---------------------------------------------------------------------------

@app.route('/api/ultimo_uid')
def api_ultimo_uid():
    st = lector.estado()
    since = request.args.get('since', 0, type=float)
    st['nuevo'] = bool(st['ts'] and st['ts'] > since)
    return jsonify(st)


@app.route('/api/simular_uid', methods=['POST'])
def api_simular_uid():
    data = request.get_json(silent=True) or {}
    uid = (data.get('uid') or '').strip().upper()
    if not uid:
        return jsonify({'ok': False, 'mensaje': 'UID vacío.'}), 400
    lector.leer_manual(uid)
    return jsonify({'ok': True})


@app.route('/api/equipo_por_uid')
def api_equipo_por_uid():
    uid = request.args.get('uid', '').strip().upper()
    eq = db.buscar_equipo_por_uid(uid)
    if not eq:
        return jsonify({'ok': False, 'mensaje': 'El UID %s no está registrado como equipo.' % uid}), 404
    d = dict(eq)
    d['prestado'] = db.obtener_prestamo_pendiente(d['id']) is not None
    return jsonify({'ok': True, 'equipo': d})


@app.route('/api/prestar', methods=['POST'])
def api_prestar():
    data = request.get_json(silent=True) or {}
    try:
        persona_id = int(data.get('persona_id'))
    except (TypeError, ValueError):
        persona_id = None

    equipo_id = data.get('equipo_id')
    uid = (data.get('uid') or '').strip().upper()
    if not equipo_id and uid:
        eq = db.buscar_equipo_por_uid(uid)
        if not eq:
            db.registrar_evento_rfid(uid, None, 'UID desconocido en préstamo')
            return jsonify({'ok': False,
                            'mensaje': 'El UID %s no está registrado como equipo.' % uid}), 404
        equipo_id = eq['id']
    if not persona_id or not equipo_id:
        return jsonify({'ok': False, 'mensaje': 'Faltan datos: se requiere persona y equipo (o UID).'}), 400

    fecha_limite = (data.get('fecha_limite') or '').strip() or None
    notas = (data.get('notas') or '').strip()
    prestamo_id, err = db.registrar_prestamo(equipo_id, persona_id, fecha_limite, notas)
    if err:
        return jsonify({'ok': False, 'mensaje': err}), 409
    return jsonify({'ok': True, 'mensaje': 'Préstamo registrado.', 'prestamo_id': prestamo_id})


@app.route('/api/devolver', methods=['POST'])
def api_devolver():
    data = request.get_json(silent=True) or {}
    try:
        prestamo_id = int(data.get('prestamo_id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'mensaje': 'Préstamo inválido.'}), 400
    info, err = db.registrar_devolucion(prestamo_id, (data.get('notas') or '').strip())
    if err:
        return jsonify({'ok': False, 'mensaje': err}), 409
    return jsonify({'ok': True,
                    'mensaje': 'Devolución registrada: %s (%s).' % (info['equipo'], info['persona'])})


@app.route('/api/devolver_uid', methods=['POST'])
def api_devolver_uid():
    data = request.get_json(silent=True) or {}
    uid = (data.get('uid') or '').strip().upper()
    eq = db.buscar_equipo_por_uid(uid)
    if not eq:
        return jsonify({'ok': False, 'mensaje': 'El UID %s no está registrado.' % uid}), 404
    pend = db.obtener_prestamo_pendiente(eq['id'])
    if not pend:
        return jsonify({'ok': False,
                        'mensaje': '"%s" no tiene préstamo activo.' % eq['nombre']}), 409
    info, err = db.registrar_devolucion(pend['id'], (data.get('notas') or '').strip())
    if err:
        return jsonify({'ok': False, 'mensaje': err}), 409
    return jsonify({'ok': True,
                    'mensaje': 'Devolución registrada: %s de %s.' % (info['equipo'], info['persona'])})


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------

db.init_db()
lector.iniciar()

if __name__ == '__main__':
    puerto = int(os.environ.get('PUERTO', 5000))
    print('Dashboard en http://localhost:%d' % puerto)
    app.run(host='0.0.0.0', port=puerto, debug=False, threaded=True)
