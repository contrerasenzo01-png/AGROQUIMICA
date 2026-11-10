/* =========================================================
   BORRADOR DE MODALES

   Si un modal con formulario se cierra sin querer (clic fuera del
   modal o tecla Escape), lo que se había escrito se guarda y vuelve
   a aparecer al abrirlo de nuevo para el mismo registro.

   - Cerrar con la X o con "Cancelar" descarta lo escrito (como antes).
   - Si se abre el modal para OTRO registro (otro producto, otro
     usuario...), se carga limpio con los datos de ese registro.
   - Los archivos (fotos) no se pueden restaurar: el navegador no lo
     permite por seguridad.

   Las pantallas no necesitan cambios: el script detecta solo los
   modales. Si una pantalla arma filas dinámicas al abrir (remitos),
   puede preguntar BorradorModal.pendiente(id) para no limpiarlas.
========================================================= */

(function () {
    'use strict';

    // Fondos de modal que usan las distintas pantallas.
    var SELECTOR_MODAL = [
        '.modal', '.rm-modal', '.pf-modal', '.pr-modal', '.pv-modal',
        '.lt-modal', '.ts-modal', '.us-modal'
    ].join(',');

    // Campos ocultos que identifican el registro que se está editando.
    var CAMPO_IDENTIDAD = /(^id|_id$|^ID_|^accion$)/i;

    var borradores = {};   // id del modal -> { identidad, campos }

    function esModalConFormulario(el) {
        return el && el.id && el.matches && el.matches(SELECTOR_MODAL) &&
               el.querySelector('form');
    }

    function visible(modal) {
        var estilo = window.getComputedStyle(modal);
        return estilo.display !== 'none' && estilo.visibility !== 'hidden';
    }

    function camposDe(modal) {
        return Array.prototype.filter.call(
            modal.querySelectorAll('input, select, textarea'),
            function (c) {
                var tipo = (c.type || '').toLowerCase();
                return (c.name || c.id) &&
                       c.name !== 'csrfmiddlewaretoken' &&
                       ['file', 'submit', 'button', 'reset', 'image'].indexOf(tipo) === -1;
            }
        );
    }

    function clave(campo, contador) {
        var base = campo.name || ('#' + campo.id);
        contador[base] = (contador[base] || 0) + 1;
        return base + '|' + contador[base];
    }

    function identidad(modal) {
        var partes = [];

        modal.querySelectorAll('form').forEach(function (f) {
            partes.push(f.getAttribute('action') || '');
        });

        camposDe(modal).forEach(function (c) {
            if (c.type === 'hidden' && CAMPO_IDENTIDAD.test(c.name || c.id)) {
                partes.push((c.name || c.id) + '=' + c.value);
            }
        });

        return partes.join('&');
    }

    function guardar(modal) {
        var contador = {};
        var campos = {};

        camposDe(modal).forEach(function (c) {
            var k = clave(c, contador);
            campos[k] = (c.type === 'checkbox' || c.type === 'radio')
                ? { marcado: c.checked }
                : { valor: c.value };
        });

        borradores[modal.id] = { identidad: identidad(modal), campos: campos };
    }

    function restaurar(modal) {
        var borrador = borradores[modal.id];
        delete borradores[modal.id];

        // Se abrió para otro registro: se respeta lo que cargó la pantalla.
        if (!borrador || borrador.identidad !== identidad(modal)) {
            return;
        }

        var contador = {};

        // En orden: así un select dependiente (tipo -> subtipo) se
        // rellena después de que su "padre" cargó las opciones.
        camposDe(modal).forEach(function (c) {
            var dato = borrador.campos[clave(c, contador)];
            if (!dato) { return; }

            if (c.type === 'hidden' && CAMPO_IDENTIDAD.test(c.name || c.id)) {
                return;
            }

            if ('marcado' in dato) {
                if (c.checked === dato.marcado) { return; }
                c.checked = dato.marcado;
            } else {
                if (c.value === dato.valor) { return; }
                c.value = dato.valor;
            }

            c.dispatchEvent(new Event('input', { bubbles: true }));
            c.dispatchEvent(new Event('change', { bubbles: true }));
        });
    }

    /* ---------- Cierres accidentales ----------
       En fase de captura: se guarda ANTES de que la pantalla cierre
       (y en algunas, limpie) el formulario. */

    // Si el modal sigue abierto y se toca algo adentro, un borrador
    // anterior ya no sirve (se descarta; la X o "Cancelar" lo limpian).
    function descartarSiEsInterno(e) {
        var modal = e.target.closest && e.target.closest(SELECTOR_MODAL);
        if (modal && modal !== e.target && modal.id) {
            delete borradores[modal.id];
        }
    }

    document.addEventListener('mousedown', function (e) {
        descartarSiEsInterno(e);

        // Bootstrap decide el clic de fondo con mousedown + click.
        if (esModalConFormulario(e.target) && visible(e.target)) {
            guardar(e.target);
        }
    }, true);

    document.addEventListener('click', function (e) {
        if (esModalConFormulario(e.target) && visible(e.target)) {
            guardar(e.target);
        }
    }, true);

    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape') {
            descartarSiEsInterno(e);
            return;
        }

        document.querySelectorAll(SELECTOR_MODAL).forEach(function (modal) {
            if (esModalConFormulario(modal) && visible(modal)) {
                guardar(modal);
            }
        });
    }, true);

    /* ---------- Reapertura ----------
       Se observa cuándo cada modal pasa a estar visible. El callback
       corre después de que la función de "abrir" de la pantalla cargó
       sus datos, así que el borrador se aplica encima. */

    function observar(modal) {
        var estabaVisible = visible(modal);

        new MutationObserver(function () {
            var ahora = visible(modal);

            if (ahora && !estabaVisible && borradores[modal.id]) {
                restaurar(modal);
            }

            estabaVisible = ahora;
        }).observe(modal, { attributes: true, attributeFilter: ['style', 'class'] });
    }

    function iniciar() {
        document.querySelectorAll(SELECTOR_MODAL).forEach(function (modal) {
            if (esModalConFormulario(modal)) {
                observar(modal);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', iniciar);
    } else {
        iniciar();
    }

    window.BorradorModal = {
        // ¿Hay algo guardado para este modal? (sin consumirlo)
        pendiente: function (idModal) {
            return Boolean(borradores[idModal]);
        },
        descartar: function (idModal) {
            delete borradores[idModal];
        }
    };
})();
