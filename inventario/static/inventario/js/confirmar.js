(function () {
    'use strict';

    var MENSAJE_DENEGADO = 'No tenés permiso para realizar esta acción.';

    var confirmarNativo = window.confirm.bind(window);
    var yaConfirmado = false;
    var overlay = null;
    var btnAceptar = null;
    var btnCancelar = null;
    var alAceptar = null;
    var patrones = leerPatrones();

    // ---------- Rutas que este usuario no puede usar ----------

    function leerPatrones() {
        var nodo = document.getElementById('rutas-denegadas');
        if (!nodo) { return []; }

        try {
            return JSON.parse(nodo.textContent).map(function (p) {
                var rx = p.replace(/[.+?^${}()|[\]\\]/g, '\\$&')
                          .replace(/\*/g, '[^/]+');
                return new RegExp('^' + rx + '$');
            });
        } catch (e) {
            return [];
        }
    }

    function urlDe(el) {
        if (!el) { return ''; }
        if (el.tagName === 'FORM') { return el.action; }
        if (el.form) { return el.formAction || el.form.action; }

        var a = el.closest ? el.closest('a[href]') : null;
        if (a) { return a.href; }

        var f = el.closest ? el.closest('form') : null;
        return f ? f.action : '';
    }

    function denegada(el) {
        var u = urlDe(el);
        if (!u || !patrones.length) { return false; }

        var ruta;
        try { ruta = new URL(u, location.href).pathname; }
        catch (e) { return false; }

        return patrones.some(function (r) { return r.test(ruta); });
    }

    // ---------- Modal ----------

    function construir() {
        if (overlay) { return; }

        overlay = document.createElement('div');
        overlay.className = 'cfm-overlay';
        overlay.innerHTML =
            '<div class="cfm-caja" role="dialog" aria-modal="true" aria-labelledby="cfmTitulo">' +
                '<div class="cfm-cabecera">' +
                    '<div class="cfm-icono"></div>' +
                    '<h3 class="cfm-titulo" id="cfmTitulo"></h3>' +
                '</div>' +
                '<p class="cfm-mensaje"></p>' +
                '<div class="cfm-acciones">' +
                    '<button type="button" class="cfm-btn cfm-cancelar">Cancelar</button>' +
                    '<button type="button" class="cfm-btn cfm-aceptar">Aceptar</button>' +
                '</div>' +
            '</div>';

        document.body.appendChild(overlay);

        btnAceptar = overlay.querySelector('.cfm-aceptar');
        btnCancelar = overlay.querySelector('.cfm-cancelar');

        btnAceptar.addEventListener('click', function () {
            var accion = alAceptar;
            cerrar();
            if (accion) { accion(); }
        });

        btnCancelar.addEventListener('click', cerrar);

        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) { cerrar(); }
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && overlay.classList.contains('cfm-visible')) {
                cerrar();
            }
        });
    }

    function cerrar() {
        if (overlay) { overlay.classList.remove('cfm-visible'); }
        alAceptar = null;
    }

    function abrir(opciones) {
        construir();

        overlay.querySelector('.cfm-caja').className =
            'cfm-caja' + (opciones.peligro ? ' cfm-peligro' : '');
        overlay.querySelector('.cfm-icono').textContent = opciones.icono;
        overlay.querySelector('.cfm-titulo').textContent = opciones.titulo;
        overlay.querySelector('.cfm-mensaje').textContent = opciones.mensaje;

        btnCancelar.style.display = opciones.soloAceptar ? 'none' : '';
        btnAceptar.textContent = opciones.textoAceptar || 'Aceptar';

        alAceptar = opciones.callback || null;
        overlay.classList.add('cfm-visible');
        (opciones.soloAceptar ? btnAceptar : btnCancelar).focus();
    }

    function avisar(mensaje) {
        abrir({
            titulo: 'Acción no permitida',
            mensaje: mensaje,
            icono: '!',
            peligro: true,
            soloAceptar: true,
            textoAceptar: 'Entendido'
        });
    }

    // ---------- Reemplazo de window.confirm ----------

    window.confirm = function (mensaje) {
        if (yaConfirmado) { return true; }

        var ev = window.event;

        if (!ev || !(ev.currentTarget || ev.target)) {
            return confirmarNativo(mensaje);
        }

        var destino = ev.currentTarget || ev.target;

        // Sin permiso: se avisa directamente, sin pedir confirmación.
        if (denegada(destino)) {
            avisar(MENSAJE_DENEGADO);
            return false;
        }

        var esEnvio = ev.type === 'submit';
        var submitter = ev.submitter || undefined;
        var peligro = /elimin|borrar|anul|baja/i.test(String(mensaje));

        abrir({
            titulo: 'Confirmar acción',
            mensaje: String(mensaje),
            icono: peligro ? '!' : '?',
            peligro: peligro,
            callback: function () {
                yaConfirmado = true;
                try {
                    if (esEnvio) {
                        destino.requestSubmit(submitter);
                    } else {
                        destino.click();
                    }
                } finally {
                    yaConfirmado = false;
                }
            }
        });

        return false;
    };

    // ---------- Bloqueo de envíos y enlaces sin permiso ----------

    document.addEventListener('submit', function (e) {
        if (denegada(e.target)) {
            e.preventDefault();
            e.stopImmediatePropagation();
            avisar(MENSAJE_DENEGADO);
        }
    }, true);

    document.addEventListener('click', function (e) {
        var a = e.target.closest ? e.target.closest('a[href]') : null;

        if (a && denegada(a)) {
            e.preventDefault();
            e.stopImmediatePropagation();
            avisar(MENSAJE_DENEGADO);
        }
    }, true);

    // Los enlaces (ej. comprobantes) sin permiso se ocultan.
    function ocultarEnlaces() {
        Array.prototype.forEach.call(
            document.querySelectorAll('a[href]'),
            function (a) { if (denegada(a)) { a.style.display = 'none'; } }
        );
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', ocultarEnlaces);
    } else {
        ocultarEnlaces();
    }
})();