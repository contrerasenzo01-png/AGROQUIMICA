/* ============================================================
   BANDEJA DE NOTIFICACIONES · Agroquímica del Valle
   - Abre y cierra la bandeja del header.
   - Carga las notificaciones del perfil del usuario (tabla NOTIFICACION):
     stock mínimo, vencimiento y egreso inusual.
   - Permite marcarlas como leídas (una o todas) sin salir de la pantalla.
   - Actualiza el número de no leídas cada minuto.
   ============================================================ */

(function () {
    'use strict';

    var raiz = document.getElementById('topbarNotif');
    if (!raiz) { return; }

    var boton = document.getElementById('btnNotif');
    var panel = document.getElementById('panelNotif');
    var lista = document.getElementById('notifLista');
    var contador = document.getElementById('notifContador');
    var resumen = document.getElementById('notifResumen');
    var botonTodas = document.getElementById('notifLeerTodas');

    var urlDatos = raiz.dataset.url;
    var urlLeer = raiz.dataset.urlLeer;
    var urlLeerTodas = raiz.dataset.urlLeerTodas;

    var campoCsrf = raiz.querySelector('[name="csrfmiddlewaretoken"]');
    var csrf = campoCsrf ? campoCsrf.value : '';

    var abierto = false;

    var ICONOS = {
        stock: '<path d="M22 17 13.5 8.5 8.5 13.5 2 7"/><path d="M16 17h6v-6"/>',
        vencimiento: '<rect x="3" y="4" width="18" height="18" rx="2"/>' +
                     '<path d="M16 2v4M8 2v4M3 10h18"/><path d="M12 14v3l2 1"/>',
        inusual: '<path d="M12 9v4"/><path d="M12 17h.01"/>' +
                 '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/>'
    };


    /* ---------- Número de no leídas ---------- */

    function actualizarContador(cantidad) {
        contador.textContent = cantidad > 99 ? '99+' : String(cantidad);
        contador.hidden = !cantidad;

        boton.classList.toggle('tiene-alertas', cantidad > 0);

        var texto = cantidad
            ? cantidad + (cantidad === 1 ? ' notificación sin leer' : ' notificaciones sin leer')
            : 'Sin notificaciones nuevas';

        boton.title = texto;
        boton.setAttribute('aria-label', 'Notificaciones: ' + texto);
        resumen.textContent = cantidad ? cantidad + ' sin leer' : 'Todo al día';

        if (botonTodas) { botonTodas.hidden = !cantidad; }
    }


    /* ---------- Lista ---------- */

    function crearSvg(contenido) {
        var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('aria-hidden', 'true');
        svg.innerHTML = contenido;
        return svg;
    }

    function crearElemento(etiqueta, clase, texto) {
        var el = document.createElement(etiqueta);
        if (clase) { el.className = clase; }
        if (texto) { el.textContent = texto; }
        return el;
    }

    function mensajeVacio(texto) {
        lista.innerHTML = '';
        lista.appendChild(crearElemento('li', 'tb-notif-vacio', texto));
    }

    function crearItem(n) {
        var item = crearElemento(
            'li',
            'tb-notif-item tb-notif-' + n.tipo +
            (n.leida ? ' tb-notif-leida' : ' tb-notif-noleida')
        );

        var icono = crearElemento('span', 'tb-notif-icono');
        icono.appendChild(crearSvg(ICONOS[n.tipo] || ICONOS.stock));
        item.appendChild(icono);

        // Textos con textContent: nunca se interpreta como HTML.
        var cuerpo = crearElemento('div', 'tb-notif-cuerpo');

        var linea = crearElemento('div', 'tb-notif-linea');
        linea.appendChild(crearElemento('span', 'tb-notif-etiqueta', n.etiqueta));
        linea.appendChild(crearElemento('span', 'tb-notif-hace', n.hace));
        cuerpo.appendChild(linea);

        cuerpo.appendChild(crearElemento('p', 'tb-notif-mensaje', n.mensaje));
        item.appendChild(cuerpo);

        if (!n.leida) {
            var leer = crearElemento('button', 'tb-notif-atender');
            leer.type = 'button';
            leer.title = 'Marcar como leída';
            leer.setAttribute('aria-label', 'Marcar como leída');
            leer.appendChild(crearSvg('<path d="m5 12 4 4L19 6"/>'));

            leer.addEventListener('click', function () {
                marcarLeida(n.id, item, leer);
            });

            item.appendChild(leer);
        }

        return item;
    }

    function mostrar(datos) {
        actualizarContador(datos.no_leidas);

        if (!datos.notificaciones.length) {
            mensajeVacio('No tenés notificaciones. ¡Todo al día!');
            return;
        }

        lista.innerHTML = '';

        datos.notificaciones.forEach(function (n, i) {
            var item = crearItem(n);
            item.style.animationDelay = (i * 40) + 'ms';
            lista.appendChild(item);
        });
    }


    /* ---------- Servidor ---------- */

    function pedirDatos() {
        return fetch(urlDatos, {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (respuesta) {
            if (!respuesta.ok) { throw new Error('HTTP ' + respuesta.status); }
            return respuesta.json();
        });
    }

    function cargar() {
        pedirDatos()
            .then(mostrar)
            .catch(function () {
                mensajeVacio('No se pudieron cargar las notificaciones.');
            });
    }

    function enviar(url) {
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': csrf,
                'X-Requested-With': 'XMLHttpRequest'
            }
        }).then(function (respuesta) { return respuesta.json(); })
          .then(function (datos) {
              if (!datos.ok) { throw new Error(datos.error || 'Error'); }
              return datos;
          });
    }

    function marcarLeida(id, item, botonLeer) {
        botonLeer.disabled = true;

        enviar(urlLeer.replace('/0/', '/' + id + '/'))
            .then(function (datos) {
                actualizarContador(datos.no_leidas);
                item.classList.remove('tb-notif-noleida');
                item.classList.add('tb-notif-leida');
                botonLeer.remove();
            })
            .catch(function () {
                botonLeer.disabled = false;
                botonLeer.title = 'No se pudo marcar. Intente nuevamente.';
            });
    }

    if (botonTodas) {
        botonTodas.addEventListener('click', function () {
            botonTodas.disabled = true;

            enviar(urlLeerTodas)
                .then(function () { cargar(); })
                .catch(function () { /* se reintenta con el próximo clic */ })
                .then(function () { botonTodas.disabled = false; });
        });
    }


    /* ---------- Abrir y cerrar ---------- */

    function abrir() {
        abierto = true;
        panel.hidden = false;

        // Un cuadro después, para que la animación de entrada se vea.
        requestAnimationFrame(function () {
            panel.classList.add('abierto');
        });

        boton.setAttribute('aria-expanded', 'true');
        cargar();
    }

    function cerrar() {
        abierto = false;
        panel.classList.remove('abierto');
        boton.setAttribute('aria-expanded', 'false');

        setTimeout(function () {
            if (!abierto) { panel.hidden = true; }
        }, 200);
    }

    boton.addEventListener('click', function (evento) {
        evento.stopPropagation();
        if (abierto) { cerrar(); } else { abrir(); }
    });

    // Clic afuera o tecla Escape: se cierra.
    document.addEventListener('click', function (evento) {
        if (abierto && !raiz.contains(evento.target)) { cerrar(); }
    });

    document.addEventListener('keydown', function (evento) {
        if (abierto && evento.key === 'Escape') {
            cerrar();
            boton.focus();
        }
    });


    /* ---------- Actualización automática (cada minuto) ---------- */

    setInterval(function () {
        if (document.hidden) { return; }

        pedirDatos()
            .then(function (datos) {
                if (abierto) { mostrar(datos); } else { actualizarContador(datos.no_leidas); }
            })
            .catch(function () { /* se reintenta en el próximo minuto */ });
    }, 60000);
})();
