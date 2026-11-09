/* ============================================================
   MOSTRAR / OCULTAR CONTRASEÑA (botón del ojo)
   Agrega el ojo a todos los campos de contraseña que no lo
   tengan: formularios de Usuarios, cartel de bloqueo por
   inactividad, etc. También a los que se crean después (modales).

   No toca:
   - los campos de las pantallas de acceso (ya traen su ojo: .has-toggle)
   - Mi perfil (React dibuja su propio ojo en cada campo)
   - los campos marcados con data-sin-ojo
   ============================================================ */
(function () {
    'use strict';

    var OJO_ABIERTO =
        '<svg class="ojo-abierto" viewBox="0 0 24 24" aria-hidden="true">' +
            '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>' +
            '<circle cx="12" cy="12" r="3"/>' +
        '</svg>';

    var OJO_CERRADO =
        '<svg class="ojo-cerrado" viewBox="0 0 24 24" aria-hidden="true">' +
            '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>' +
            '<path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>' +
            '<path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"/>' +
            '<line x1="1" y1="1" x2="23" y2="23"/>' +
        '</svg>';

    function excluido(input) {
        return input.dataset.ojo === '1' ||
               input.hasAttribute('data-sin-ojo') ||
               input.classList.contains('has-toggle') ||
               input.closest('#perfil-raiz, .input-icon');
    }

    function agregarOjo(input) {
        if (excluido(input)) return;
        input.dataset.ojo = '1';

        // Envoltorio para ubicar el botón dentro del campo
        var envoltorio = document.createElement('div');
        envoltorio.className = 'ojo-envoltorio';
        input.parentNode.insertBefore(envoltorio, input);
        envoltorio.appendChild(input);
        input.classList.add('ojo-campo');

        var boton = document.createElement('button');
        boton.type = 'button';
        boton.className = 'ojo-boton';
        boton.setAttribute('aria-label', 'Mostrar contraseña');
        boton.setAttribute('aria-pressed', 'false');
        boton.title = 'Mostrar contraseña';
        boton.innerHTML = OJO_ABIERTO + OJO_CERRADO;
        envoltorio.appendChild(boton);

        boton.addEventListener('click', function () {
            var mostrar = input.type === 'password';
            input.type = mostrar ? 'text' : 'password';
            boton.classList.toggle('visible', mostrar);
            boton.setAttribute('aria-pressed', mostrar ? 'true' : 'false');
            var texto = mostrar ? 'Ocultar contraseña' : 'Mostrar contraseña';
            boton.setAttribute('aria-label', texto);
            boton.title = texto;
            input.focus();
        });

        // Al reiniciar el formulario vuelve a quedar oculta
        if (input.form) {
            input.form.addEventListener('reset', function () {
                input.type = 'password';
                boton.classList.remove('visible');
                boton.setAttribute('aria-pressed', 'false');
            });
        }
    }

    function revisar(raiz) {
        if (!raiz || !raiz.querySelectorAll) return;
        if (raiz.matches && raiz.matches('input[type="password"]')) agregarOjo(raiz);
        raiz.querySelectorAll('input[type="password"]').forEach(agregarOjo);
    }

    function iniciar() {
        revisar(document.body);

        // Campos que aparecen después (por ejemplo, el cartel de bloqueo)
        new MutationObserver(function (cambios) {
            cambios.forEach(function (c) {
                c.addedNodes.forEach(function (nodo) {
                    if (nodo.nodeType === 1) revisar(nodo);
                });
            });
        }).observe(document.body, { childList: true, subtree: true });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', iniciar);
    } else {
        iniciar();
    }
})();
