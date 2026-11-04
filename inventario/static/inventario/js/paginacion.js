/* ============================================================
   PAGINACIÓN · Agroquímica del Valle

   1) Paginación en el navegador (catálogos chicos):
        const pag = Paginador({
            contenedor: document.querySelector('tbody'),
            items: '.mi-fila',
            nav: document.getElementById('miPaginacion'),
            clave: 'proveedores',
        });

      Los filtros de cada pantalla marcan las filas con
      data-coincide="1" o "0" y después llaman a pag.refrescar(true).
      La paginación se aplica solo sobre las que coinciden, así la
      búsqueda encuentra en todas las páginas.

   2) Paginación en el servidor: el selector "por página" de
      _paginacion.html recarga la página con ?por_pagina=N.
   ============================================================ */

(function () {
    'use strict';

    const FLECHA_ANTERIOR = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>';
    const FLECHA_SIGUIENTE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>';


    /* La cantidad por página elegida se recuerda por pantalla. */
    function leerTamano(clave, opciones, porDefecto) {
        try {
            const valor = parseInt(localStorage.getItem('pg:' + clave), 10);
            return opciones.includes(valor) ? valor : porDefecto;
        } catch (e) {
            return porDefecto;
        }
    }

    function guardarTamano(clave, valor) {
        try { localStorage.setItem('pg:' + clave, valor); } catch (e) { /* sin almacenamiento */ }
    }


    /* Números de página con "…": 1 … 4 5 6 … 20 */
    function rango(actual, total) {
        const lista = [];

        for (let n = 1; n <= total; n++) {
            if (n === 1 || n === total || Math.abs(n - actual) <= 1) {
                lista.push(n);
            } else if (lista[lista.length - 1] !== '…') {
                lista.push('…');
            }
        }

        return lista;
    }


    window.Paginador = function (cfg) {
        const opciones = cfg.opciones || [10, 25, 50];
        const nav = cfg.nav;
        let porPagina = leerTamano(cfg.clave, opciones, cfg.porPagina || opciones[0]);
        let actual = 1;

        const mostrar = cfg.mostrar || function (el, visible) {
            el.style.display = visible ? '' : 'none';
        };

        function todos() {
            return Array.from(cfg.contenedor.querySelectorAll(cfg.items));
        }

        function coincidentes() {
            return todos().filter(function (el) { return el.dataset.coincide !== '0'; });
        }

        function crearBoton(contenido, destino, deshabilitado, etiqueta, clase) {
            const boton = document.createElement('button');
            boton.type = 'button';
            boton.className = 'pg-btn' + (clase ? ' ' + clase : '') + (deshabilitado ? ' pg-off' : '');
            boton.setAttribute('aria-label', etiqueta);
            boton.disabled = deshabilitado;

            if (contenido.charAt(0) === '<') {
                boton.innerHTML = contenido;
            } else {
                boton.textContent = contenido;
            }

            boton.addEventListener('click', function () {
                actual = destino;
                mostrarPagina(true, true);
            });

            return boton;
        }

        function dibujar(total, desde, hasta, paginas) {
            nav.innerHTML = '';
            nav.hidden = total === 0;

            if (!total) { return; }

            const info = document.createElement('p');
            info.className = 'pg-info';
            info.append('Mostrando ');
            const rangoTexto = document.createElement('strong');
            rangoTexto.textContent = desde + '–' + hasta;
            info.append(rangoTexto, ' de ');
            const totalTexto = document.createElement('strong');
            totalTexto.textContent = total;
            info.append(totalTexto);
            nav.appendChild(info);

            if (paginas > 1) {
                const caja = document.createElement('div');
                caja.className = 'pg-botones';

                caja.appendChild(crearBoton(FLECHA_ANTERIOR, actual - 1, actual === 1, 'Página anterior', 'pg-flecha'));

                rango(actual, paginas).forEach(function (n) {
                    if (n === '…') {
                        const puntos = document.createElement('span');
                        puntos.className = 'pg-puntos';
                        puntos.textContent = '…';
                        caja.appendChild(puntos);
                    } else if (n === actual) {
                        const marca = document.createElement('span');
                        marca.className = 'pg-btn pg-actual';
                        marca.setAttribute('aria-current', 'page');
                        marca.textContent = n;
                        caja.appendChild(marca);
                    } else {
                        caja.appendChild(crearBoton(String(n), n, false, 'Página ' + n));
                    }
                });

                caja.appendChild(crearBoton(FLECHA_SIGUIENTE, actual + 1, actual === paginas, 'Página siguiente', 'pg-flecha'));

                nav.appendChild(caja);
            }

            const etiqueta = document.createElement('label');
            etiqueta.className = 'pg-tamano';

            const texto = document.createElement('span');
            texto.textContent = 'Por página';

            const selector = document.createElement('select');
            selector.setAttribute('aria-label', 'Registros por página');

            opciones.forEach(function (opcion) {
                const elemento = new Option(opcion, opcion);
                elemento.selected = opcion === porPagina;
                selector.add(elemento);
            });

            selector.addEventListener('change', function () {
                porPagina = parseInt(selector.value, 10);
                guardarTamano(cfg.clave, porPagina);
                actual = 1;
                mostrarPagina(true, false);
            });

            etiqueta.append(texto, selector);
            nav.appendChild(etiqueta);
        }

        function mostrarPagina(animar, subir) {
            const lista = coincidentes();
            const total = lista.length;
            const paginas = Math.max(1, Math.ceil(total / porPagina));

            actual = Math.min(Math.max(1, actual), paginas);

            const inicio = (actual - 1) * porPagina;
            const enPagina = lista.slice(inicio, inicio + porPagina);
            const visibles = new Set(enPagina);

            todos().forEach(function (el) { mostrar(el, visibles.has(el)); });

            dibujar(total, total ? inicio + 1 : 0, inicio + enPagina.length, paginas);

            if (cfg.alCambiar) {
                cfg.alCambiar(enPagina);
            } else if (animar) {
                enPagina.forEach(function (el, i) {
                    el.classList.remove('pg-entra');
                    void el.offsetWidth;   // reinicia la animación
                    el.style.setProperty('--pg-i', Math.min(i, 15));
                    el.classList.add('pg-entra');
                });
            }

            // Al cambiar de página desde abajo, se vuelve al principio de la lista.
            if (subir) {
                const destino = cfg.subirA || cfg.contenedor;
                const arriba = destino.getBoundingClientRect().top;

                if (arriba < 80) {
                    window.scrollTo({ top: window.scrollY + arriba - 90, behavior: 'smooth' });
                }
            }
        }

        mostrarPagina(false, false);

        return {
            refrescar: function (volverAlInicio) {
                if (volverAlInicio) { actual = 1; }
                mostrarPagina(true, false);
            }
        };
    };


    /* Selector "por página" de las pantallas paginadas en el servidor */
    document.addEventListener('change', function (evento) {
        const selector = evento.target.closest && evento.target.closest('[data-pg-servidor]');

        if (!selector) { return; }

        const url = new URL(window.location.href);
        url.searchParams.set('por_pagina', selector.value);
        url.searchParams.delete('page');
        window.location.href = url.toString();
    });


    /* Filas de las pantallas paginadas en el servidor: entrada escalonada */
    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-pg-animar]').forEach(function (contenedor) {
            Array.from(contenedor.children).forEach(function (fila, i) {
                fila.style.setProperty('--pg-i', Math.min(i, 15));
                fila.classList.add('pg-entra');
            });
        });
    });
})();