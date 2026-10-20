/* Dashboard del sistema de préstamo: polling del lector serial y acciones RFID. */

const $ = (id) => document.getElementById(id);

let ultimoTs = 0;      // timestamp de la última lectura ya procesada
let modoEscaneo = null; // 'prestar' | 'devolver' | null

/* ------------------------------------------------------------------ */
/* Utilidades                                                          */
/* ------------------------------------------------------------------ */

let toastTimer = null;
function toast(mensaje, tipo = 'info') {
  const el = $('toast');
  if (!el) return;
  el.textContent = mensaje;
  el.className = 'toast ' + tipo;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 4500);
}

async function enviar(url, payload) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const d = await resp.json().catch(() => ({ ok: false, mensaje: 'Respuesta inválida del servidor.' }));
  toast(d.mensaje || (d.ok ? 'Listo.' : 'Error.'), d.ok ? 'ok' : 'error');
  if (d.ok) setTimeout(() => location.reload(), 800);
  return d;
}

/* ------------------------------------------------------------------ */
/* Lectura serial (polling cada 1.2 s)                                 */
/* ------------------------------------------------------------------ */

async function consultarUid() {
  try {
    const resp = await fetch('/api/ultimo_uid?since=' + ultimoTs);
    const d = await resp.json();

    const badge = $('serial-status');
    if (badge) {
      badge.textContent = d.conectado
        ? 'ESP32 conectado (' + (d.puerto || 'serial') + ')'
        : 'ESP32 no detectado — modo simulación';
      badge.className = 'serial-badge ' + (d.conectado ? 'conectado' : 'desconectado');
    }
    const msg = $('serial-msg');
    if (msg) msg.textContent = d.mensaje || '';

    if (!d.ts) return;
    if (!ultimoTs) {
      // Primera carga: solo mostrar la última lectura, no repetir acciones.
      ultimoTs = d.ts;
      mostrarUid(d.uid);
      return;
    }
    if (d.nuevo && d.uid) {
      ultimoTs = d.ts;
      await manejarUid(d.uid);
    }
  } catch (e) {
    const badge = $('serial-status');
    if (badge) {
      badge.textContent = 'Servidor no disponible';
      badge.className = 'serial-badge desconectado';
    }
  }
}

function mostrarUid(uid) {
  const el = $('ultimo-uid');
  if (el && uid) el.textContent = uid;
}

function resaltarTarjeta(uid) {
  document.querySelectorAll('.equipo-card').forEach((c) => c.classList.remove('escaneado'));
  const card = document.querySelector('.equipo-card[data-uid="' + CSS.escape(uid) + '"]');
  if (card) {
    card.classList.add('escaneado');
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

async function manejarUid(uid) {
  mostrarUid(uid);
  resaltarTarjeta(uid);

  if (modoEscaneo === 'prestar') {
    modoEscaneo = null;
    const personaId = $('prestar-persona').value;
    if (!personaId) {
      toast('Elija primero la persona en el formulario de préstamo.', 'error');
      return;
    }
    await enviar('/api/prestar', {
      uid,
      persona_id: personaId,
      fecha_limite: $('prestar-fecha').value,
      notas: $('prestar-notas').value,
    });
    return;
  }

  if (modoEscaneo === 'devolver') {
    modoEscaneo = null;
    await enviar('/api/devolver_uid', { uid });
    return;
  }

  // Sin modo activo: solo informar el estado del equipo leído.
  try {
    const resp = await fetch('/api/equipo_por_uid?uid=' + encodeURIComponent(uid));
    const d = await resp.json();
    if (d.ok) {
      toast(d.equipo.nombre + ': ' + (d.equipo.prestado ? 'PRESTADO' : 'Disponible'),
            d.equipo.prestado ? 'error' : 'ok');
    } else {
      toast(d.mensaje, 'error');
    }
  } catch (e) { /* sin conexión */ }
}

/* ------------------------------------------------------------------ */
/* Formularios del dashboard                                           */
/* ------------------------------------------------------------------ */

const formPrestar = $('form-prestar');
if (formPrestar) {
  $('prestar-equipo').addEventListener('change', (ev) => {
    if (ev.target.value === 'escanear') {
      modoEscaneo = 'prestar';
      toast('Modo escaneo: acerque el tag del equipo a leer.', 'info');
    } else if (modoEscaneo === 'prestar') {
      modoEscaneo = null;
    }
  });

  formPrestar.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const personaId = $('prestar-persona').value;
    if (!personaId) {
      toast('Seleccione la persona que recibirá el equipo.', 'error');
      return;
    }
    const valor = $('prestar-equipo').value;
    if (valor === 'escanear') {
      modoEscaneo = 'prestar';
      toast('Modo escaneo activo: acerque el tag del equipo.', 'info');
      return;
    }
    await enviar('/api/prestar', {
      equipo_id: valor,
      persona_id: personaId,
      fecha_limite: $('prestar-fecha').value,
      notas: $('prestar-notas').value,
    });
  });
}

const btnDevolverEscanear = $('btn-devolver-escanear');
if (btnDevolverEscanear) {
  btnDevolverEscanear.addEventListener('click', () => {
    modoEscaneo = 'devolver';
    toast('Modo escaneo de devolución: acerque el tag del equipo.', 'info');
  });
}

document.querySelectorAll('.btn-devolver').forEach((btn) => {
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    await enviar('/api/devolver', { prestamo_id: btn.dataset.id });
  });
});

const btnSimular = $('btn-simular');
if (btnSimular) {
  btnSimular.addEventListener('click', async () => {
    const uid = $('uid-manual').value.trim().toUpperCase();
    if (!uid) {
      toast('Escriba un UID para simular (p. ej. A1B2C3D4).', 'error');
      return;
    }
    try {
      await fetch('/api/simular_uid', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uid }),
      });
    } catch (e) { /* sin conexión */ }
  });
  $('uid-manual').addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') { ev.preventDefault(); btnSimular.click(); }
  });
}

/* ------------------------------------------------------------------ */
/* Arranque                                                            */
/* ------------------------------------------------------------------ */

setInterval(consultarUid, 1200);
consultarUid();
