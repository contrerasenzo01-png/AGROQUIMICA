(function () {
    'use strict';

    var script = document.currentScript;
    var LIMITE = parseInt(script && script.dataset.limiteMs, 10);

    if (!LIMITE) { return; }   // página sin sesión

    var URL_BLOQUEO = script.dataset.bloqueoUrl;
    var URL_PING = script.dataset.pingUrl;
    var URL_LOGIN = script.dataset.loginUrl;

    var CLAVE_ACTIVIDAD = 'av:ultima';
    var CLAVE_RESTAURAR = 'av:restaurar';
    var PREFIJO = 'av:borrador:';
    var SALTOS = ['password', 'hidden', 'file', 'submit', 'button', 'reset', 'image'];

    var bloqueado = false;
    var ultimoPing = Date.now();
    var ultimoRegistro = 0;
    var temporizadorGuardado = null;

    // ======================================================
    // ACTIVIDAD
    // ======================================================

    function registrar() {
        var ahora = Date.now();

        if (bloqueado || ahora - ultimoRegistro < 1000) { return; }

        ultimoRegistro = ahora;

        try { localStorage.setItem(CLAVE_ACTIVIDAD, String(ahora)); }
        catch (e) { /* sin almacenamiento */ }
    }

    function ultimaActividad() {
        try {
            return parseInt(localStorage.getItem(CLAVE_ACTIVIDAD), 10) || Date.now();
        } catch (e) {
            return Date.now();
        }
    }

    ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart', 'input']
        .forEach(function (nombre) {
            document.addEventListener(nombre, registrar, true);
        });

    // Cargar una página cuenta como actividad (el servidor la registró).
    try { localStorage.setItem(CLAVE_ACTIVIDAD, String(Date.now())); }
    catch (e) { /* sin almacenamiento */ }

    function irAlLogin() { window.location.href = URL_LOGIN; }

    function ping() {
        ultimoPing = Date.now();

        fetch(URL_PING, {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (r) {
            if (r.ok) { return; }

            return r.json().then(function (d) {
                if (d && d.bloqueada) { mostrarBloqueo(); } else { irAlLogin(); }
            });
        }).catch(function () { /* sin conexión: se reintenta */ });
    }

    function revisar() {
        if (bloqueado) { return; }

        var ahora = Date.now();

        if (ahora - ultimaActividad() > LIMITE) {
            mostrarBloqueo();
            return;
        }

        // Mientras haya actividad, se mantiene viva la sesión del servidor.
        if (ultimaActividad() > ultimoPing && ahora - ultimoPing > 60000) {
            ping();
        }
    }

    setInterval(revisar, 15000);

    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) { revisar(); }
    });

    window.addEventListener('focus', revisar);

    // ======================================================
    // CARTEL DE BLOQUEO (la página no se recarga)
    // ======================================================

    function csrf() {
        var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        if (m) { return decodeURIComponent(m[1]); }

        var i = document.querySelector('input[name=csrfmiddlewaretoken]');
        return i ? i.value : '';
    }

    function mostrarBloqueo() {
        if (bloqueado) { return; }

        bloqueado = true;
        guardarTodos();

        var token = csrf();

        // Sin token no se puede validar por ajax: se usa la pantalla de bloqueo.
        if (!token) {
            window.location.href = URL_BLOQUEO + '?next=' +
                encodeURIComponent(location.pathname + location.search);
            return;
        }

        var ov = document.createElement('div');
        ov.className = 'lck-overlay lck-visible';
        ov.innerHTML =
            '<div class="lck-caja" role="dialog" aria-modal="true">' +
                '<h3>Sesión bloqueada por inactividad</h3>' +
                '<p>Ingresá tu usuario y contraseña para continuar. ' +
                'Lo que estabas haciendo sigue en pantalla.</p>' +
                '<div class="lck-error" style="display:none"></div>' +
                '<form autocomplete="on">' +
                    '<div class="lck-campo"><label>Usuario</label>' +
                    '<input type="text" name="usuario" autocomplete="username" required></div>' +
                    '<div class="lck-campo"><label>Contraseña</label>' +
                    '<input type="password" name="password" autocomplete="current-password" required></div>' +
                    '<button type="submit" class="lck-btn">Continuar</button>' +
                '</form>' +
            '</div>';

        document.body.appendChild(ov);

        var form = ov.querySelector('form');
        var error = ov.querySelector('.lck-error');
        var boton = ov.querySelector('.lck-btn');

        form.elements.usuario.focus();

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            boton.disabled = true;
            error.style.display = 'none';

            fetch(URL_BLOQUEO, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': token,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: new URLSearchParams({
                    usuario: form.elements.usuario.value,
                    password: form.elements.password.value
                })
            }).then(function (r) {
                return r.json().then(function (d) { return { r: r, d: d }; });
            }).then(function (res) {
                if (res.d.ok) {
                    ov.remove();
                    bloqueado = false;
                    ultimoPing = Date.now();
                    ultimoRegistro = 0;
                    registrar();
                    return;
                }

                if (res.d.cerrada) { irAlLogin(); return; }

                error.textContent = res.d.error || 'No se pudo validar.';
                error.style.display = 'block';
                form.elements.password.value = '';
                boton.disabled = false;
            }).catch(function () {
                error.textContent = 'Sin conexión con el servidor. Reintentá.';
                error.style.display = 'block';
                boton.disabled = false;
            });
        });
    }

    // ======================================================
    // BORRADORES (solo se restauran si el servidor bloqueó la sesión)
    // ======================================================

    function esPost(form) {
        return (form.getAttribute('method') || 'get').toLowerCase() === 'post';
    }

    function campos(form) {
        var cuenta = {};
        var lista = [];

        Array.prototype.forEach.call(form.elements, function (el) {
            if (!el.name || el.disabled || el.name === 'csrfmiddlewaretoken') { return; }
            if (SALTOS.indexOf((el.type || '').toLowerCase()) >= 0) { return; }

            cuenta[el.name] = (cuenta[el.name] || 0) + 1;
            lista.push({ el: el, k: el.name + '#' + (cuenta[el.name] - 1) });
        });

        return lista;
    }

    function claveForm(form, i) {
        return PREFIJO + location.pathname + '|' + (form.id || 'form' + i);
    }

    function guardarForm(form, i) {
        if (!esPost(form)) { return; }

        var datos = {};
        var hayDatos = false;

        campos(form).forEach(function (c) {
            var esMarca = c.el.type === 'checkbox' || c.el.type === 'radio';
            var v = esMarca ? c.el.checked : c.el.value;

            datos[c.k] = v;

            if (v === true || (typeof v === 'string' && v !== '')) { hayDatos = true; }
        });

        try {
            if (hayDatos) {
                sessionStorage.setItem(claveForm(form, i), JSON.stringify(datos));
            } else {
                sessionStorage.removeItem(claveForm(form, i));
            }
        } catch (e) { /* sin almacenamiento */ }
    }

    function guardarTodos() {
        Array.prototype.forEach.call(document.forms, guardarForm);
    }

    function borrarBorradores(conservarRuta) {
        try {
            Object.keys(sessionStorage).forEach(function (k) {
                if (k.indexOf(PREFIJO) !== 0) { return; }
                if (conservarRuta && k.indexOf(PREFIJO + location.pathname + '|') === 0) { return; }
                sessionStorage.removeItem(k);
            });
        } catch (e) { /* sin almacenamiento */ }
    }

    function restaurar() {
        Array.prototype.forEach.call(document.forms, function (form, i) {
            if (!esPost(form)) { return; }

            var datos;
            try { datos = JSON.parse(sessionStorage.getItem(claveForm(form, i))); }
            catch (e) { return; }

            if (!datos) { return; }

            campos(form).forEach(function (c) {
                if (!(c.k in datos)) { return; }

                var el = c.el;
                var v = datos[c.k];

                if (el.type === 'checkbox' || el.type === 'radio') {
                    if (el.checked !== v) {
                        el.checked = v;
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                } else if (el.value !== v) {
                    el.value = v;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });
        });
    }

    function iniciar() {
        var vieneDeBloqueo = false;

        try {
            vieneDeBloqueo = sessionStorage.getItem(CLAVE_RESTAURAR) === '1';
            sessionStorage.removeItem(CLAVE_RESTAURAR);
        } catch (e) { /* sin almacenamiento */ }

        if (vieneDeBloqueo) {
            restaurar();
            borrarBorradores(true);
        } else {
            // Navegación normal: los borradores viejos no se reutilizan.
            borrarBorradores(false);
        }

        document.addEventListener('input', function (e) {
            if (!e.target.form) { return; }

            clearTimeout(temporizadorGuardado);

            temporizadorGuardado = setTimeout(function () {
                var form = e.target.form;
                guardarForm(form, Array.prototype.indexOf.call(document.forms, form));
            }, 300);
        });

        document.addEventListener('change', function (e) {
            if (!e.target.form) { return; }

            var form = e.target.form;
            guardarForm(form, Array.prototype.indexOf.call(document.forms, form));
        });

        // Al cerrar sesión a propósito no queda nada guardado.
        document.addEventListener('click', function (e) {
            var a = e.target.closest ? e.target.closest('a[href*="cerrar-sesion"]') : null;

            if (a) { borrarBorradores(false); }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', iniciar);
    } else {
        iniciar();
    }
})();