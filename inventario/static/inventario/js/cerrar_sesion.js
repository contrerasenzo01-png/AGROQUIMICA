/* ============================================================
   CONFIRMAR CIERRE DE SESIÓN
   Al presionar "Cerrar sesión" (a.logout-link) se abre un modal.
   - "Sí, cerrar sesión": sigue el enlace y cierra la sesión.
   - "No, continuar trabajando" / Esc / clic afuera: no hace nada.
   ============================================================ */

(function () {
    'use strict';

    var overlay = null;
    var enlace = null;          // enlace "Cerrar sesión" presionado
    var confirmado = false;     // deja pasar el clic una vez confirmado
    var foco = null;            // elemento con foco antes de abrir

    function construir() {
        if (overlay) { return; }

        overlay = document.createElement('div');
        overlay.className = 'cs-overlay';
        overlay.innerHTML =
            '<div class="cs-caja" role="alertdialog" aria-modal="true" ' +
                 'aria-labelledby="csTitulo" aria-describedby="csMensaje">' +
                '<div class="cs-icono" aria-hidden="true">' +
                    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                        '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>' +
                        '<path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>' +
                    '</svg>' +
                '</div>' +
                '<h3 class="cs-titulo" id="csTitulo">¿Desea cerrar la sesión?</h3>' +
                '<p class="cs-mensaje" id="csMensaje">' +
                    'Está a punto de salir del sistema. Para volver a ingresar ' +
                    'deberá introducir nuevamente su <strong>usuario y contraseña</strong>.' +
                '</p>' +
                '<div class="cs-acciones">' +
                    '<button type="button" class="cs-btn cs-quedarse">No, continuar trabajando</button>' +
                    '<button type="button" class="cs-btn cs-salir">' +
                        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
                            '<path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>' +
                        '</svg>' +
                        '<span>Sí, cerrar sesión</span>' +
                    '</button>' +
                '</div>' +
            '</div>';

        document.body.appendChild(overlay);

        overlay.querySelector('.cs-quedarse').addEventListener('click', cerrar);
        overlay.querySelector('.cs-salir').addEventListener('click', salir);

        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) { cerrar(); }
        });

        overlay.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                e.preventDefault();
                cerrar();
                return;
            }

            // Mantiene el foco dentro del modal con Tab.
            if (e.key === 'Tab') {
                var botones = overlay.querySelectorAll('button');
                var primero = botones[0];
                var ultimo = botones[botones.length - 1];

                if (e.shiftKey && document.activeElement === primero) {
                    e.preventDefault();
                    ultimo.focus();
                } else if (!e.shiftKey && document.activeElement === ultimo) {
                    e.preventDefault();
                    primero.focus();
                }
            }
        });
    }

    function abrir(a) {
        construir();
        enlace = a;
        foco = document.activeElement;

        var btnSalir = overlay.querySelector('.cs-salir');
        btnSalir.disabled = false;
        btnSalir.classList.remove('cs-cargando');

        overlay.classList.add('cs-visible');
        overlay.querySelector('.cs-quedarse').focus();
    }

    function cerrar() {
        if (!overlay) { return; }
        overlay.classList.remove('cs-visible');
        enlace = null;
        if (foco && foco.focus) { foco.focus(); }
    }

    function salir() {
        if (!enlace) { return; }

        var btnSalir = overlay.querySelector('.cs-salir');
        btnSalir.disabled = true;
        btnSalir.classList.add('cs-cargando');
        btnSalir.querySelector('span').textContent = 'Cerrando sesión…';

        // Se vuelve a hacer clic en el enlace real, así también se
        // ejecuta lo que otros scripts hacen al cerrar sesión
        // (por ejemplo, borrar los borradores guardados).
        confirmado = true;
        try {
            enlace.click();
        } finally {
            confirmado = false;
        }
    }

    // Se escucha en captura para frenar el clic antes que nadie.
    document.addEventListener('click', function (e) {
        if (confirmado) { return; }

        var a = e.target.closest ? e.target.closest('a.logout-link') : null;
        if (!a) { return; }

        e.preventDefault();
        e.stopImmediatePropagation();
        abrir(a);
    }, true);

    // Al volver con "atrás" el modal tiene que estar cerrado.
    window.addEventListener('pageshow', function () {
        if (overlay) { overlay.classList.remove('cs-visible'); }
    });
})();
