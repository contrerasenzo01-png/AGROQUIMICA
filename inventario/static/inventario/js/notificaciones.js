/* ============================================================
   BANDEJA DE NOTIFICACIONES · Agroquímica del Valle
   - Abre y cierra la bandeja del topbar.
   - Carga las alertas pendientes (stock mínimo y vencimiento).
   - Permite marcarlas como atendidas sin salir de la pantalla.
   - Actualiza el número cada minuto.
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

    var urlDatos = raiz.dataset.url;
    var urlAtender = raiz.dataset.urlAtender;
    var puedeAtender = raiz.dataset.puedeAtender === '1';

    var campoCsrf = raiz.querySelector('[name="csrfmiddlewaretoken"]');
    var csrf = campoCsrf ? campoCsrf.value : '';

    var abierto = false;

    var ICONOS = {
        stock: '<path d="M22 17 13.5 8.5 8.5 13.5 2 7"/><path d="M16 17h6v-6"/>',
        vencimiento: '<rect x="3" y="4" width="18" height="18" rx="2"/>' +
                     '<path d="M16 2v4M8 2v4M3 10h18"/><path d="M12 14v3l2 1"/>'
    };


    /* ---------- Número de pendientes ---------- */

    function actualizarContador(cantidad) {
        contador.textContent = cantidad > 99 ? '99+' : String(cantidad);
        contador.hidden = !cantidad;

        boton.classList.toggle('tiene-alertas', cantidad > 0);

        var texto = cantidad
            ? cantidad + (cantidad === 1 ? ' alerta sin atender' : ' alertas sin atender')
            : 'Sin alertas pendientes';

        boton.title = texto;
        boton.setAttribute('aria-label', 'Notificaciones: ' + texto);
        resumen.textContent = cantidad ? cantidad + ' sin atender' : 'Todo al día';
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

    function crearItem(alerta) {
        var item = crearElemento(
            'li',
            'tb-notif-item tb-notif-' + alerta.tipo + (alerta.vencido ? ' tb-notif-vencido' : '')
        );

        var icono = crearElemento('span', 'tb-notif-icono');
        icono.appendChild(crearSvg(ICONOS[alerta.tipo] || ICONOS.stock));
        item.appendChild(icono);

        // Textos con textContent: nunca se interpreta como HTML.
        var cuerpo = crearElemento('div', 'tb-notif-cuerpo');

        var linea = crearElemento('div', 'tb-notif-linea');
        linea.appendChild(crearElemento('span', 'tb-notif-etiqueta', alerta.etiqueta));
        linea.appendChild(crearElemento('span', 'tb-notif-hace', alerta.hace));
        cuerpo.appendChild(linea);

        cuerpo.appendChild(crearElemento('strong', 'tb-notif-producto', alerta.producto));
        cuerpo.appendChild(crearElemento('p', 'tb-notif-mensaje', alerta.mensaje));
        item.appendChild(cuerpo);

        if (puedeAtender) {
            var atender = crearElemento('button', 'tb-notif-atender');
            atender.type = 'button';
            atender.title = 'Marcar como atendida';
            atender.setAttribute('aria-label', 'Marcar como atendida: ' + alerta.producto);
            atender.appendChild(crearSvg('<path d="m5 12 4 4L19 6"/>'));

            atender.addEventListener('click', function () {
                atenderAlerta(alerta.id, item, atender);
            });

            item.appendChild(atender);
        }

        return item;
    }

    function mostrar(datos) {
        actualizarContador(datos.pendientes);

        if (!datos.alertas.length) {
            mensajeVacio('No hay alertas pendientes. ¡Todo al día!');
            return;
        }

        lista.innerHTML = '';

        datos.alertas.forEach(function (alerta, i) {
            var item = crearItem(alerta);
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
                mensajeVacio('No se pudieron cargar las alertas.');
            });
    }

    function atenderAlerta(id, item, botonAtender) {
        botonAtender.disabled = true;

        fetch(urlAtender.replace('/0/', '/' + id + '/'), {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': csrf,
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
            .then(function (respuesta) { return respuesta.json(); })
            .then(function (datos) {
                if (!datos.ok) { throw new Error(datos.error || 'Error'); }

                actualizarContador(datos.pendientes);

                // La alerta se va con una animación.
                item.classList.add('tb-notif-saliendo');

                setTimeout(function () {
                    item.remove();
                    if (!lista.querySelector('.tb-notif-item')) { cargar(); }
                }, 260);
            })
            .catch(function () {
                botonAtender.disabled = false;
                botonAtender.title = 'No se pudo marcar. Probá de nuevo.';
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
                if (abierto) { mostrar(datos); } else { actualizarContador(datos.pendientes); }
            })
            .catch(function () { /* se reintenta en el próximo minuto */ });
    }, 60000);
})();