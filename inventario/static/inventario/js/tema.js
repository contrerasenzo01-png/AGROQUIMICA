(function () {
    'use strict';

    var CLAVE = 'av:tema';
    var html = document.documentElement;
    var boton = document.getElementById('btnTema');

    var LUNA =
        '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" ' +
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';

    var SOL =
        '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" ' +
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<circle cx="12" cy="12" r="4"/>' +
        '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';

    function oscuro() { return html.classList.contains('modo-oscuro'); }

    /* Las pantallas con Bootstrap usan data-bs-theme para su modo oscuro:
       se mantiene igual al tema del sistema. */
    function sincronizarBootstrap() {
        html.setAttribute('data-bs-theme', oscuro() ? 'dark' : 'light');
    }

    function pintar() {
        if (!boton) { return; }

        var texto = oscuro() ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro';

        boton.innerHTML = oscuro() ? SOL : LUNA;
        boton.title = texto;
        boton.setAttribute('aria-label', texto);
    }

    if (boton) {
        boton.addEventListener('click', function () {
            html.classList.toggle('modo-oscuro');

            try { localStorage.setItem(CLAVE, oscuro() ? 'oscuro' : 'claro'); }
            catch (e) { /* sin almacenamiento */ }

            sincronizarBootstrap();
            pintar();
        });
    }

    sincronizarBootstrap();
    pintar();
})();