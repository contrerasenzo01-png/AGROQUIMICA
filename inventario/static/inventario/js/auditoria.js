
console.log('auditoria.js se cargó correctamente');

function abrirDetalleAuditoria(boton) {
    console.log('Se hizo clic en Ver detalle');

    const modal = document.getElementById('modalAuditoria');
    const contenido = document.getElementById('contenidoDetalleAuditoria');

    // Verificar que existan los elementos del modal.
    if (!modal || !contenido) {
        console.error('No se encontró el modal o su contenido.');
        return;
    }

    // Mostrar el modal.
    modal.classList.add('activo');
    modal.setAttribute('aria-hidden', 'false');

    // Mostrar mensaje mientras se cargan los datos.
    contenido.textContent = 'Cargando detalle...';

    const url = boton.dataset.url;

    if (!url) {
        contenido.textContent = 'No se encontró la URL del detalle.';
        console.error('El botón no tiene el atributo data-url.');
        return;
    }

    fetch(url)
        .then(respuesta => {
            if (!respuesta.ok) {
                throw new Error(
                    `Error ${respuesta.status}: no se pudo obtener el detalle.`
                );
            }

            return respuesta.json();
        })
        .then(datos => {
            contenido.replaceChildren();

            // Información general del registro.
            const tabla = document.createElement('table');
            tabla.className = 'al-table';

            const informacion = [
                ['Fecha', datos.fecha],
                ['Hora', datos.hora],
                ['Usuario', datos.usuario],
                ['Perfil', datos.perfil],
                ['Sección', datos.entidad],
                ['ID del registro', datos.registro],
                ['Acción', datos.accion]
            ];

            const cuerpo = tabla.createTBody();

            informacion.forEach(([campo, valor]) => {
                const fila = cuerpo.insertRow();
                const encabezado = document.createElement('th');
                const celda = fila.insertCell();

                encabezado.textContent = campo;
                celda.textContent = valor ?? '—';

                fila.prepend(encabezado);
            });

            contenido.appendChild(tabla);

            // Título de los cambios.
            const titulo = document.createElement('h3');
            titulo.textContent = 'Cambios realizados';
            contenido.appendChild(titulo);

            // Si no existen cambios registrados.
            if (!datos.cambios || datos.cambios.length === 0) {
                const mensaje = document.createElement('p');
                mensaje.textContent =
                    'No hay cambios de campos registrados.';

                contenido.appendChild(mensaje);
                return;
            }

            // Tabla de cambios.
            const tablaCambios = document.createElement('table');
            tablaCambios.className = 'al-table';

            const cabecera = tablaCambios.createTHead().insertRow();

            ['Campo', 'Valor anterior', 'Valor nuevo'].forEach(texto => {
                const th = document.createElement('th');
                th.textContent = texto;
                cabecera.appendChild(th);
            });

            const cuerpoCambios = tablaCambios.createTBody();

            datos.cambios.forEach(cambio => {
                const fila = cuerpoCambios.insertRow();

                [
                    cambio.campo,
                    cambio.antes,
                    cambio.despues
                ].forEach(valor => {
                    const celda = fila.insertCell();
                    celda.textContent = valor ?? '—';
                });
            });

            contenido.appendChild(tablaCambios);
        })
        .catch(error => {
            console.error('Error al cargar el detalle:', error);

            contenido.replaceChildren();

            const mensaje = document.createElement('p');
            mensaje.textContent = error.message;

            contenido.appendChild(mensaje);
        });
}

function cerrarDetalleAuditoria() {
    const modal = document.getElementById('modalAuditoria');

    if (!modal) {
        console.error('No se encontró el modal de auditoría.');
        return;
    }

    modal.classList.remove('activo');
    modal.setAttribute('aria-hidden', 'true');
}

// Cerrar el modal al presionar Escape.
document.addEventListener('keydown', evento => {
    if (evento.key === 'Escape') {
        cerrarDetalleAuditoria();
    }
});

// Cerrar el modal al hacer clic fuera de su contenido.
document.addEventListener('click', evento => {
    const modal = document.getElementById('modalAuditoria');

    if (modal && evento.target === modal) {
        cerrarDetalleAuditoria();
    }
});