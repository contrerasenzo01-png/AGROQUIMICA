/* ============================================================
   VALIDACIONES DE FORMULARIOS · Agroquímica del Valle

   Se carga una sola vez (en base.html) y valida TODOS los
   formularios que tengan campos de la tabla REGLAS de abajo,
   según el atributo name del campo. No hay que tocar los inputs.

   - Muestra el error debajo del campo, en vivo.
   - Saca los caracteres no permitidos mientras se escribe.
   - Frena el envío si algo está mal.
   - Funciona con los campos que se agregan después (lotes).

   Para cambiar una regla de un campo puntual:
     data-v="entero" data-v-min="1" data-v-max="50"
   Para excluir un campo:  data-v="none"
   El servidor vuelve a validar todo (inventario/validaciones.py).
   ============================================================ */
(function () {
    'use strict';

    /* ---------- 1. REGLAS POR NOMBRE DE CAMPO ---------- */

    const REGLAS = {
        // Productos
        Nombre_producto:       { tipo: 'nombre',  min: 2, max: 50 },
        Descripcion_producto:  { tipo: 'texto',   max: 200 },
        Precio:                { tipo: 'decimal', min: 0.01, max: 99999999.99, dec: 2 },
        Stock_minimo:          { tipo: 'entero',  min: 0, max: 999999 },
        Cantidad_presentacion: { tipo: 'decimal', min: 0.01, max: 99999.99, dec: 2 },

        // Egreso por venta y baja por vencimiento
        cantidad:              { tipo: 'entero',  min: 1, max: 999999 },
        descripcion:           { tipo: 'texto',   max: 200 },
        observacion:           { tipo: 'texto',   max: 200 },

        // Tipos, subtipos y perfiles
        Nombre_tipo_producto:  { tipo: 'nombre',  min: 2, max: 50 },
        Nombre_subtipo:        { tipo: 'nombre',  min: 2, max: 50 },
        Descripcion_subtipo:   { tipo: 'texto',   max: 200 },
        Nombre_perfil:         { tipo: 'nombre',  min: 3, max: 50 },

        // Proveedores
        nombre_proveedor:      { tipo: 'nombre',  min: 2, max: 150 },
        telefono_proveedor:    { tipo: 'telefono', max: 25 },
        email_proveedor:       { tipo: 'email',   max: 100 },
        direccion_proveedor:   { tipo: 'texto',   min: 5, max: 255 },

        // Usuarios y contraseñas
        Nombre_usuario:        { tipo: 'persona', min: 2, max: 50 },
        Apellido_usuario:      { tipo: 'persona', min: 2, max: 50 },
        DNI:                   { tipo: 'dni' },
        Email_usuario:         { tipo: 'email',   max: 100 },
        Contrasena:            { tipo: 'password', max: 64 },
        nueva_contrasena:      { tipo: 'password', max: 64 },
        confirmar_contrasena:  { tipo: 'confirmar', max: 64 },
        email:                 { tipo: 'email',   max: 100, req: true },   // recuperar contraseña

        // Remitos y lotes
        Numero_remito:         { tipo: 'codigo',  min: 3, max: 20 },
        Fecha_remito:          { tipo: 'fecha',   desde: -3650, hasta: 0,
                                 msgDesde: 'La fecha es demasiado antigua (máximo 10 años).',
                                 msgHasta: 'La fecha del remito no puede ser futura.' },
        lote_numero:           { tipo: 'codigo',  min: 1, max: 50 },
        lote_cajas:            { tipo: 'entero',  min: 1, max: 999999 },
        lote_unidades_caja:    { tipo: 'entero',  min: 1, max: 999999 },
        lote_vencimiento:      { tipo: 'fecha',   desde: 0, hasta: 5475,
                                 msgDesde: 'No se pueden registrar lotes ya vencidos.',
                                 msgHasta: 'El vencimiento no puede superar los 15 años.' },
        Numero_lote:           { tipo: 'codigo',  min: 1, max: 50 },
        Cantidad_cajas:        { tipo: 'entero',  min: 1, max: 999999 },
        Unidades_por_caja:     { tipo: 'entero',  min: 1, max: 999999 },
        Cantidad_actual:       { tipo: 'entero',  min: 0, max: 10000000 },
        Fecha_ingreso:         { tipo: 'fecha',   desde: -3650, hasta: 0,
                                 msgDesde: 'La fecha es demasiado antigua (máximo 10 años).',
                                 msgHasta: 'La fecha de ingreso no puede ser futura.' },
        Fecha_vencimiento:     { tipo: 'fecha',   desde: -3650, hasta: 5475,
                                 msgHasta: 'El vencimiento no puede superar los 15 años.' },

        // Justificaciones
        Motivo_anulacion:      { tipo: 'texto',   min: 10, max: 200, req: true },
    };

    const SELECTOR_MAPEADOS = Object.keys(REGLAS)
        .map(function (n) { return '[name="' + n + '"]'; })
        .join(',') + ',[data-v]:not([data-v="none"])';

    const SIMB_NOMBRE = " .,-/&()%+'°";
    const SIMB_TEXTO = ' .,;:-/&()%+\'"°#¿?¡!@_';
    const SIMB_PERSONA = " '-.";

    const esAlnum = function (c) { return /[\p{L}\p{N}]/u.test(c); };
    const esLetra = function (c) { return /\p{L}/u.test(c); };
    const esSimbolo = function (c) { return !esAlnum(c) && !/\s/.test(c); };
    const limpiar = function (t) { return String(t).split(/\s+/).filter(Boolean).join(' '); };
    const fmt = function (n) { return Number(n).toLocaleString('es-AR', { maximumFractionDigits: 2 }); };


    /* ---------- 2. VALIDADORES (devuelven el mensaje de error o '') ---------- */

    function largo(t, r) {
        const min = r.min || 0;
        const max = r.max || 255;
        if (t.length < min) return 'Debe tener al menos ' + min + ' caracteres.';
        if (t.length > max) return 'No puede superar los ' + max + ' caracteres.';
        return '';
    }

    function vNombre(v, r) {
        const t = limpiar(v);
        const e = largo(t, { min: r.min || 2, max: r.max || 50 });
        if (e) return e;

        const malo = Array.from(t).find(function (c) { return !(esAlnum(c) || SIMB_NOMBRE.includes(c)); });
        if (malo) return 'No se permite el carácter «' + malo + '». Use letras, números y . , - / & ( ) % + \'';
        if (!esAlnum(t[0])) return 'Tiene que empezar con una letra o un número.';
        if (!/\p{L}/u.test(t)) return 'Tiene que incluir al menos una letra.';
        if (/([^\p{L}\p{N}\s])\1/u.test(t) || /[^\p{L}\p{N}\s]{2,}/u.test(t)) return 'No puede tener símbolos seguidos.';
        if (/(\p{L})\1{3,}/u.test(t)) return 'Tiene letras repetidas. Revíselo.';
        if (!/[\p{L}\p{N})%.]$/u.test(t)) return 'No puede terminar con ese símbolo.';
        return '';
    }

    function vPersona(v, r) {
        const t = limpiar(v);
        const e = largo(t, { min: r.min || 2, max: r.max || 50 });
        if (e) return e;

        for (const c of t) {
            if (/\d/.test(c)) return 'No puede contener números.';
            if (!(esLetra(c) || SIMB_PERSONA.includes(c))) return 'No se permite el carácter «' + c + '».';
        }
        if (!esLetra(t[0])) return 'Tiene que empezar con una letra.';
        if ((t.match(/\p{L}/gu) || []).length < 2) return 'Tiene que tener al menos 2 letras.';
        if (/[^\p{L}\s]{2,}/u.test(t)) return 'No puede tener símbolos seguidos.';
        if (/(\p{L})\1{3,}/u.test(t)) return 'Tiene letras repetidas. Revíselo.';
        if (!/[\p{L}.]$/u.test(t)) return 'No puede terminar con ese símbolo.';
        return '';
    }

    function vTexto(v, r) {
        const t = limpiar(v);
        const e = largo(t, { min: r.min || 0, max: r.max || 200 });
        if (e) return e;

        const malo = Array.from(t).find(function (c) { return !(esAlnum(c) || SIMB_TEXTO.includes(c)); });
        if (malo) return 'No se permite el carácter «' + malo + '».';
        if ((t.match(/[\p{L}\p{N}]/gu) || []).length < 2) return 'Tiene que incluir letras o números.';
        if (/([^\p{L}\p{N}\s])\1{2,}/u.test(t)) return 'Repite demasiadas veces el mismo símbolo.';
        if (/(\p{L})\1{4,}/u.test(t)) return 'Tiene letras repetidas. Revíselo.';
        return '';
    }

    function vCodigo(v, r) {
        const t = String(v).trim();
        const e = largo(t, { min: r.min || 1, max: r.max || 50 });
        if (e) return e;

        if (!/^[A-Za-z0-9][A-Za-z0-9\-./_]*$/.test(t)) {
            return 'Solo letras, números y - . / _ (sin espacios). Tiene que empezar con letra o número.';
        }
        if (/[-./_]{2,}/.test(t)) return 'No puede tener símbolos seguidos.';
        if (/[-./_]$/.test(t)) return 'No puede terminar con un símbolo.';
        return '';
    }

    function vEntero(v, r, el) {
        const t = String(v).trim();
        if (!/^\d{1,12}$/.test(t)) return 'Ingrese solo números enteros, sin signos, puntos ni comas.';

        const n = Number(t);
        const min = r.min !== undefined ? r.min : 0;

        // El máximo del campo (por ejemplo, el stock disponible en un egreso) manda si es menor.
        let max = r.max !== undefined ? r.max : 999999;
        const attr = el && el.getAttribute('max');
        if (attr !== null && attr !== '' && !isNaN(Number(attr))) max = Math.min(max, Number(attr));

        if (n < min) return min === 1 ? 'Tiene que ser mayor a cero.' : 'No puede ser menor a ' + fmt(min) + '.';
        if (n > max) return 'No puede superar ' + fmt(max) + '.';
        return '';
    }

    function vDecimal(v, r) {
        const t = String(v).trim().replace(',', '.');
        if (!/^\d{1,12}(\.\d+)?$/.test(t)) return 'Ingrese un número válido (solo dígitos y una coma o punto decimal).';

        const dec = r.dec !== undefined ? r.dec : 2;
        if ((t.split('.')[1] || '').length > dec) return 'Máximo ' + dec + ' decimales.';

        const n = Number(t);
        const min = r.min !== undefined ? r.min : 0.01;
        const max = r.max !== undefined ? r.max : 99999999.99;

        if (n < min) return min > 0 && min <= 0.01 ? 'Tiene que ser mayor a cero.' : 'No puede ser menor a ' + fmt(min) + '.';
        if (n > max) return 'No puede superar ' + fmt(max) + '.';
        return '';
    }

    function vDni(v) {
        const t = String(v).trim();
        if (!/^\d+$/.test(t)) return 'Solo números, sin puntos ni espacios.';
        if (t.length < 7 || t.length > 8) return 'El DNI tiene 7 u 8 dígitos.';
        if (Number(t) < 1000000) return 'El DNI no es válido.';
        return '';
    }

    function vTelefono(v, r) {
        const t = limpiar(v);
        if (t.length > (r.max || 25)) return 'No puede superar los ' + (r.max || 25) + ' caracteres.';
        if (!/^\+?[\d\s()-]+$/.test(t)) return 'Solo números, espacios y los símbolos + - ( ).';
        if ((t.match(/\(/g) || []).length !== (t.match(/\)/g) || []).length) return 'Tiene paréntesis sin cerrar.';

        const d = t.replace(/\D/g, '');
        if (d.length < 6) return 'Tiene que tener al menos 6 dígitos.';
        if (d.length > 15) return 'No puede tener más de 15 dígitos.';
        if (/(\d)\1{7,}/.test(d)) return 'No parece un teléfono válido.';
        return '';
    }

    const RE_EMAIL = /^[A-Za-z0-9](?:[A-Za-z0-9._%+-]*[A-Za-z0-9])?@(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}$/;

    function vEmail(v, r) {
        const t = String(v).trim();
        if (/\s/.test(t)) return 'No puede tener espacios.';
        if (t.length > (r.max || 100)) return 'No puede superar los ' + (r.max || 100) + ' caracteres.';
        if (!t.includes('@')) return 'Falta el @. Ejemplo: nombre@empresa.com';
        if (t.split('@').length > 2) return 'Tiene más de un @.';
        if (t.includes('..')) return 'No puede tener dos puntos seguidos.';

        const partes = t.split('@');
        if (!partes[0]) return 'Falta lo que va antes del @.';
        if (partes[0].length > 64) return 'La parte anterior al @ es demasiado larga.';
        if (!partes[1] || !partes[1].includes('.')) return 'El dominio no es válido. Ejemplo: nombre@empresa.com';
        if (!RE_EMAIL.test(t)) return 'Ingrese un correo válido. Ejemplo: nombre@empresa.com';
        return '';
    }

    function reqsPassword(v, usuario) {
        const lista = [
            { ok: v.length >= 8 && v.length <= 64, txt: 'Entre 8 y 64 caracteres', err: 'Debe tener entre 8 y 64 caracteres.' },
            { ok: /[A-Z]/.test(v), txt: 'Una letra mayúscula', err: 'Debe tener al menos una mayúscula.' },
            { ok: /[a-z]/.test(v), txt: 'Una letra minúscula', err: 'Debe tener al menos una minúscula.' },
            { ok: /\d/.test(v), txt: 'Un número', err: 'Debe tener al menos un número.' },
            { ok: !/\s/.test(v), txt: 'Sin espacios', err: 'No puede tener espacios.' },
        ];

        if (usuario) {
            lista.push({
                ok: !v.toLowerCase().includes(usuario.toLowerCase()),
                txt: 'No contiene el nombre de usuario',
                err: 'No puede contener el nombre de usuario.',
            });
        }
        return lista;
    }

    function vPassword(v, r, el) {
        const falla = reqsPassword(v, usuarioDe(el)).find(function (x) { return !x.ok; });
        return falla ? falla.err : '';
    }

    function vConfirmar(v, r, el) {
        const f = el.form;
        const p = f && f.querySelector('[name="nueva_contrasena"], [name="Contrasena"]');
        return p && v !== p.value ? 'Las contraseñas no coinciden.' : '';
    }

    function vFecha(v, r) {
        const t = String(v).trim();
        if (!/^\d{4}-\d{2}-\d{2}$/.test(t)) return 'Ingrese una fecha válida.';

        const p = t.split('-').map(Number);
        const f = new Date(p[0], p[1] - 1, p[2]);
        if (f.getFullYear() !== p[0] || f.getMonth() !== p[1] - 1 || f.getDate() !== p[2]) return 'La fecha no existe.';

        const hoy = new Date();
        hoy.setHours(0, 0, 0, 0);
        const dias = Math.round((f - hoy) / 86400000);

        if (r.desde !== undefined && dias < r.desde) return r.msgDesde || 'La fecha es demasiado antigua.';
        if (r.hasta !== undefined && dias > r.hasta) return r.msgHasta || 'La fecha es demasiado lejana.';
        return '';
    }

    const VALIDADORES = {
        nombre: vNombre, persona: vPersona, texto: vTexto, codigo: vCodigo,
        entero: vEntero, decimal: vDecimal, dni: vDni, telefono: vTelefono,
        email: vEmail, password: vPassword, confirmar: vConfirmar, fecha: vFecha,
    };

    // Qué caracteres se aceptan mientras se escribe (el resto se saca solo).
    const FILTROS = {
        nombre: function (c) { return esAlnum(c) || SIMB_NOMBRE.includes(c); },
        persona: function (c) { return esLetra(c) || SIMB_PERSONA.includes(c); },
        texto: function (c) { return esAlnum(c) || SIMB_TEXTO.includes(c) || /\s/.test(c); },
        codigo: function (c) { return /[A-Za-z0-9\-./_]/.test(c); },
        telefono: function (c) { return /[\d\s()+-]/.test(c); },
        entero: function (c) { return /\d/.test(c); },
        dni: function (c) { return /\d/.test(c); },
    };


    /* ---------- 3. CAMPOS Y REGLAS ---------- */

    const TIPOS_IGNORADOS = ['hidden', 'checkbox', 'radio', 'file', 'submit', 'button', 'reset', 'image', 'range', 'color'];

    function esCampo(el) {
        if (!el || !el.tagName) return false;
        const t = el.tagName;
        if (t !== 'INPUT' && t !== 'SELECT' && t !== 'TEXTAREA') return false;
        if (t === 'INPUT' && TIPOS_IGNORADOS.includes(el.type)) return false;
        if (el.disabled || el.readOnly) return false;
        if (el.dataset && el.dataset.v === 'none') return false;
        return true;
    }

    function reglaDe(el) {
        const base = REGLAS[el.name];
        if (!el.dataset || !el.dataset.v) return base || null;

        const r = Object.assign({}, base, { tipo: el.dataset.v });
        ['min', 'max', 'dec'].forEach(function (k) {
            const d = el.dataset['v' + k.charAt(0).toUpperCase() + k.slice(1)];
            if (d !== undefined) r[k] = Number(d);
        });
        if (el.dataset.vReq !== undefined) r.req = true;
        return r;
    }

    function esFormValidable(form) {
        return Boolean(form && form.querySelector && form.querySelector(SELECTOR_MAPEADOS));
    }

    function camposDe(form) {
        return Array.from(form.elements).filter(esCampo);
    }

    function usuarioDe(el) {
        const f = el.form;

        if (el.dataset && el.dataset.usuario) {
            const o = document.querySelector(el.dataset.usuario);
            if (o) return String(o.value !== undefined ? o.value : o.textContent).trim();
        }
        if (f && f.dataset.usuarioValor) return f.dataset.usuarioValor.trim();

        const prev = f && f.querySelector('#Usuario_preview');
        if (prev) return prev.value.trim();

        const modal = el.closest('[id^="modal"]');
        const rotulo = modal && modal.querySelector('#restablecerUsuario');
        return rotulo ? rotulo.textContent.trim() : '';
    }


    /* ---------- 4. MENSAJES DE ERROR ---------- */

    function ancla(el) { return el.closest('.input-group, .password-wrapper, .ojo-envoltorio') || el; }

    function nodoError(el) {
        if (!el._vError) {
            const n = document.createElement('div');
            n.className = 'v-error';
            n.setAttribute('role', 'alert');
            n.hidden = true;
            ancla(el).insertAdjacentElement('afterend', n);
            el._vError = n;
        }
        return el._vError;
    }

    function mostrarError(el, msg, aviso) {
        const n = nodoError(el);
        n.textContent = msg;
        n.hidden = false;
        n.classList.toggle('v-aviso', Boolean(aviso));

        if (!aviso) {
            el.classList.add('v-invalid');
            el.setAttribute('aria-invalid', 'true');
        }
    }

    function ocultarError(el) {
        if (el._vError) {
            el._vError.hidden = true;
            el._vError.textContent = '';
            el._vError.classList.remove('v-aviso');
        }
        el.classList.remove('v-invalid');
        el.removeAttribute('aria-invalid');
    }

    function validarCampo(el) {
        if (!esCampo(el)) { ocultarError(el); return true; }

        const regla = reglaDe(el);
        const valor = el.value || '';
        const conEspacios = regla && (regla.tipo === 'password' || regla.tipo === 'confirmar');
        const vacio = conEspacios ? valor === '' : valor.trim() === '';
        let msg = '';

        if (el.validity && el.validity.badInput) {
            msg = 'Ingrese solo números.';
        } else if (vacio) {
            if (el.required || (regla && regla.req)) {
                msg = el.tagName === 'SELECT' ? 'Seleccione una opción.' : 'Complete este campo.';
            }
        } else if (regla && VALIDADORES[regla.tipo]) {
            msg = VALIDADORES[regla.tipo](valor, regla, el);
        }

        // Control extra propio de una pantalla (ej. número de remito
        // repetido): el.vExtra = function (valor) { return 'mensaje' | ''; }
        if (!msg && !vacio && typeof el.vExtra === 'function') {
            msg = el.vExtra(valor, el) || '';
        }

        if (msg) { mostrarError(el, msg, false); return false; }

        ocultarError(el);
        return true;
    }

    function validarForm(form) {
        let primero = null;

        camposDe(form).forEach(function (el) {
            el.classList.add('v-tocado');
            if (!validarCampo(el) && !primero) primero = el;
        });

        return primero;
    }

    function limpiarForm(form) {
        Array.from(form.elements).forEach(function (el) {
            el.classList.remove('v-tocado');
            ocultarError(el);
        });
        setTimeout(function () { refrescarListas(form); }, 0);
    }


    /* ---------- 5. CHECKLIST DE CONTRASEÑA ---------- */

    function crearChecklist(el) {
        if (el._vLista) return;
        const ul = document.createElement('ul');
        ul.className = 'v-checklist';
        nodoError(el).insertAdjacentElement('afterend', ul);
        el._vLista = ul;
        actualizarChecklist(el);
    }

    function actualizarChecklist(el) {
        const ul = el._vLista;
        if (!ul) return;

        const v = el.value || '';
        ul.textContent = '';

        reqsPassword(v, usuarioDe(el)).forEach(function (x) {
            const li = document.createElement('li');
            li.textContent = x.txt;
            if (v !== '') li.className = x.ok ? 'ok' : 'no';
            ul.appendChild(li);
        });
    }

    function refrescarListas(form) {
        if (!form) return;
        form.querySelectorAll('input').forEach(function (p) {
            if (p._vLista) actualizarChecklist(p);
        });
    }

    function revalidarDependientes(el) {
        const regla = reglaDe(el);
        if (!regla || regla.tipo !== 'password' || !el.form) return;

        el.form.querySelectorAll('[name="confirmar_contrasena"]').forEach(function (c) {
            if (c.classList.contains('v-tocado')) validarCampo(c);
        });
    }


    /* ---------- 6. PREPARAR, SANEAR Y NORMALIZAR ---------- */

    const TIPOS_TEXTO = ['text', 'search', 'email', 'tel', 'password', 'url'];

    function asegurar(el) {
        if (el.form && esFormValidable(el.form)) el.form.noValidate = true;

        const regla = reglaDe(el);
        if (!regla) return;

        const admiteLargo = el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && TIPOS_TEXTO.includes(el.type));
        if (admiteLargo && regla.max && (el.maxLength < 0 || el.maxLength > regla.max)) {
            el.maxLength = regla.max;
        }

        if (regla.tipo === 'password') crearChecklist(el);
    }

    // Saca los caracteres no permitidos. Devuelve el aviso si sacó alguno.
    function sanear(el, regla) {
        const filtro = FILTROS[regla.tipo];
        const sirve = el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && ['text', 'search', 'tel'].includes(el.type));
        if (!filtro || !sirve) return '';

        const original = el.value;
        const chars = Array.from(original);
        const limpio = chars.filter(filtro).join('');
        if (limpio === original) return '';

        const malo = chars.find(function (c) { return !filtro(c); });
        let pos = null;

        try {
            const izq = original.slice(0, el.selectionStart);
            pos = Array.from(izq).filter(filtro).join('').length;
        } catch (e) { pos = null; }

        el.value = limpio;
        if (pos !== null) { try { el.setSelectionRange(pos, pos); } catch (e) { /* sin cursor */ } }

        return 'No se permite el carácter «' + (/\s/.test(malo) ? 'espacio' : malo) + '» en este campo.';
    }

    function normalizar(el, regla) {
        let nuevo = el.value;

        if (['nombre', 'persona', 'texto', 'telefono'].includes(regla.tipo)) nuevo = limpiar(nuevo);
        else if (regla.tipo === 'email') nuevo = nuevo.trim().toLowerCase();
        else if (['codigo', 'entero', 'decimal', 'dni', 'fecha'].includes(regla.tipo)) nuevo = nuevo.trim();

        if (nuevo !== el.value) el.value = nuevo;
    }


    /* ---------- 7. EVENTOS (delegados: sirven para campos agregados después) ---------- */

    document.addEventListener('focusin', function (e) {
        if (esCampo(e.target)) asegurar(e.target);
    }, true);

    document.addEventListener('keydown', function (e) {
        const el = e.target;
        if (!esCampo(el) || el.type !== 'number') return;

        const regla = reglaDe(el);
        if (!regla) return;

        const bloqueadas = ['e', 'E', '+', '-'];
        if (regla.tipo === 'entero' || regla.tipo === 'dni') bloqueadas.push('.', ',');
        if (bloqueadas.includes(e.key)) e.preventDefault();
    }, true);

    document.addEventListener('input', function (e) {
        const el = e.target;
        if (!esCampo(el) || e.isComposing) return;

        asegurar(el);

        const regla = reglaDe(el);
        const aviso = regla ? sanear(el, regla) : '';
        const activo = el.classList.contains('v-tocado') || (el._vError && !el._vError.hidden) || aviso;

        if (activo) {
            el.classList.add('v-tocado');
            if (validarCampo(el) && aviso) mostrarError(el, aviso, true);
        }

        refrescarListas(el.form);
        revalidarDependientes(el);
    }, true);

    document.addEventListener('focusout', function (e) {
        const el = e.target;
        if (!esCampo(el)) return;

        const regla = reglaDe(el);
        if (!regla) return;

        normalizar(el, regla);
        el.classList.add('v-tocado');
        validarCampo(el);
        revalidarDependientes(el);
    }, true);

    document.addEventListener('change', function (e) {
        const el = e.target;
        if (!esCampo(el)) return;

        if (reglaDe(el) || el.tagName === 'SELECT' || el.type === 'date') {
            el.classList.add('v-tocado');
            validarCampo(el);
            revalidarDependientes(el);
        }
    }, true);

    document.addEventListener('reset', function (e) {
        if (e.target instanceof HTMLFormElement) limpiarForm(e.target);
    }, true);

    // Frena el envío si hay errores (se ejecuta antes que los scripts de cada pantalla).
    document.addEventListener('submit', function (e) {
        const form = e.target;
        if (!(form instanceof HTMLFormElement) || !esFormValidable(form)) return;

        const primero = validarForm(form);
        if (!primero) return;

        e.preventDefault();
        e.stopPropagation();
        primero.focus();
        primero.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }, true);

    // Al abrir un modal, se borran los errores que quedaron de la vez anterior.
    const modalesVistos = new WeakMap();

    function vigilarModales() {
        new MutationObserver(function (cambios) {
            cambios.forEach(function (c) {
                const el = c.target;
                if (!(el instanceof HTMLElement) || typeof el.className !== 'string' || !/modal/i.test(el.className)) return;

                const ahora = getComputedStyle(el).display !== 'none';
                const antes = modalesVistos.get(el);
                modalesVistos.set(el, ahora);

                if (ahora && antes === false) el.querySelectorAll('form').forEach(limpiarForm);
            });
        }).observe(document.body, { attributes: true, attributeFilter: ['style', 'class'], subtree: true });
    }

    function iniciar() {
        document.querySelectorAll('form').forEach(function (f) {
            if (esFormValidable(f)) f.noValidate = true;
        });
        document.querySelectorAll(SELECTOR_MAPEADOS).forEach(function (el) {
            if (esCampo(el)) asegurar(el);
        });
        vigilarModales();
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
    else iniciar();


    /* ---------- 8. API PÚBLICA (la usa, por ejemplo, perfil.jsx) ---------- */

    window.Validar = {
        campo: validarCampo,
        formulario: validarForm,
        limpiar: limpiarForm,
        persona: function (v) { return vPersona(v, { min: 2, max: 50 }); },
        nombre: function (v) { return vNombre(v, { min: 2, max: 50 }); },
        email: function (v) { return vEmail(v, { max: 100 }); },
    };
})();