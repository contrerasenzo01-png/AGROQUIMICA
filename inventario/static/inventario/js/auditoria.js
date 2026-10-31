console.log('auditoria.js se cargó correctamente');

/* =========================================================
   TEXTOS
========================================================= */

// Nombre legible de cada acción.
const NOMBRES_ACCION = {
    CREACION: 'Creación',
    MODIFICACION: 'Modificación',
    ELIMINACION: 'Eliminación',
    ANULACION: 'Anulación',
    INICIO_SESION: 'Inicio de sesión',
    CIERRE_SESION: 'Cierre de sesión'
};

// Clase de la insignia de cada acción (las mismas de la tabla).
const CLASES_ACCION = {
    CREACION: 'aud-cre',
    MODIFICACION: 'aud-mod',
    ELIMINACION: 'aud-eli',
    ANULACION: 'aud-anu',
    INICIO_SESION: 'aud-ini',
    CIERRE_SESION: 'aud-cie'
};

const MESES = [
    'ene.', 'feb.', 'mar.', 'abr.', 'may.', 'jun.',
    'jul.', 'ago.', 'sep.', 'oct.', 'nov.', 'dic.'
];

// Íconos (trazos simples, se dibujan con el color del texto).
const ICONOS = {
    usuario:
        '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/>' +
        '<circle cx="12" cy="7" r="4"/>',
    perfil:
        '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 ' +
        '20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 ' +
        '1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>' +
        '<path d="m9 12 2 2 4-4"/>',
    seccion:
        '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 ' +
        '1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/>' +
        '<path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/>' +
        '<path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
    id:
        '<line x1="4" x2="20" y1="9" y2="9"/>' +
        '<line x1="4" x2="20" y1="15" y2="15"/>' +
        '<line x1="10" x2="8" y1="3" y2="21"/>' +
        '<line x1="16" x2="14" y1="3" y2="21"/>',
    reloj:
        '<circle cx="12" cy="12" r="10"/>' +
        '<polyline points="12 6 12 12 16 14"/>'
};

// Nombre legible de los campos más comunes.
const ETIQUETAS_CAMPO = {
    // Productos
    Nombre_producto: 'Nombre',
    Marca: 'Marca',
    Descripcion_producto: 'Descripción',
    ID_Tipo_producto: 'Tipo de producto',
    ID_Subtipo: 'Subtipo',
    Precio: 'Precio',
    Cantidad_presentacion: 'Cantidad de presentación',
    Unidad_medida_producto: 'Unidad de medida',
    Unidades_por_presentacion: 'Unidades por presentación',
    Estado_producto: 'Estado',
    Stock_minimo: 'Stock mínimo',
    // Lotes
    ID_Producto: 'Producto',
    ID_Remito: 'Remito',
    Numero_lote: 'Número de lote',
    Cantidad_cajas: 'Cantidad de cajas',
    Unidades_por_caja: 'Unidades por caja',
    Cantidad_ingresada: 'Cantidad ingresada',
    Cantidad_actual: 'Cantidad actual',
    Fecha_ingreso: 'Fecha de ingreso',
    Fecha_vencimiento: 'Fecha de vencimiento',
    // Remitos
    ID_Proveedor: 'Proveedor',
    Numero_remito: 'Número de remito',
    Fecha_remito: 'Fecha del remito',
    Estado_remito: 'Estado',
    Fecha_anulacion: 'Fecha de anulación',
    Motivo_anulacion: 'Motivo de la anulación',
    ID_Usuario_anulacion: 'Anulado por',
    // Proveedores
    nombre_proveedor: 'Nombre',
    telefono_proveedor: 'Teléfono',
    email_proveedor: 'Email',
    direccion_proveedor: 'Dirección',
    estado_proveedor: 'Estado',
    // Usuarios
    ID_Perfil: 'Perfil',
    DNI: 'DNI',
    Apellido_usuario: 'Apellido',
    Nombre_usuario: 'Nombre',
    Usuario: 'Usuario',
    Email_usuario: 'Email',
    Estado_usuario: 'Estado',
    Fecha_ultima_modificacion: 'Última modificación',
    Fecha_Baja: 'Fecha de baja',
    Cambiar_contrasena: 'Debe cambiar la contraseña',
    // Perfiles, permisos, tipos y subtipos
    Nombre_perfil: 'Nombre',
    Estado_perfil: 'Estado',
    Nombre_permiso: 'Nombre',
    Descripcion_permiso: 'Descripción',
    Nombre_tipo_producto: 'Nombre',
    Estado_tipo_producto: 'Estado',
    Nombre_subtipo: 'Nombre',
    Descripcion_subtipo: 'Descripción',
    // Otros
    Nota: 'Nota',
    accion: 'Acción'
};

// Campos de la anulación de un remito. La fecha y el usuario ya figuran
// arriba (momento y responsable de la acción), así que no se repiten.
const CAMPOS_ANULACION = [
    'Fecha_anulacion', 'Motivo_anulacion', 'ID_Usuario_anulacion'
];
const REPETIDOS_EN_ANULACION = ['Fecha_anulacion', 'ID_Usuario_anulacion'];

function estaVacio(valor) {
    return valor === null || valor === undefined || valor === '';
}

// Texto que se muestra cuando un valor está vacío.
const SIN_VALOR = 'Sin valor';

// Los campos con ID no se muestran, salvo los que el servidor ya
// reemplazó por el nombre del registro relacionado.
function campoVisible(campo) {
    return !String(campo).startsWith('ID_') ||
           ETIQUETAS_CAMPO[campo] !== undefined;
}

// Nombre de un campo: el conocido, o el original con formato.
function etiquetaCampo(campo) {
    if (ETIQUETAS_CAMPO[campo]) {
        return ETIQUETAS_CAMPO[campo];
    }

    const texto = String(campo).replace(/_/g, ' ');
    return texto.charAt(0).toUpperCase() + texto.slice(1);
}

// Texto para mostrar un valor.
function formatearValor(valor, campo) {
    if (valor === null || valor === undefined || valor === '') {
        return SIN_VALOR;
    }

    if (typeof valor === 'boolean') {
        if (campo && campo.toLowerCase().startsWith('estado')) {
            return valor ? 'Activo' : 'Inactivo';
        }

        return valor ? 'Sí' : 'No';
    }

    if (typeof valor === 'string') {
        // Fecha: 2026-10-30
        const fecha = valor.match(/^(\d{4})-(\d{2})-(\d{2})$/);

        if (fecha) {
            return `${fecha[3]}/${fecha[2]}/${fecha[1]}`;
        }

        // Fecha y hora con zona horaria: se muestra en la hora local.
        if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}.*(Z|[+-]\d{2}:\d{2})$/.test(valor)) {
            const momento = new Date(valor);

            if (!isNaN(momento.getTime())) {
                const dos = n => String(n).padStart(2, '0');

                return `${dos(momento.getDate())}/` +
                       `${dos(momento.getMonth() + 1)}/` +
                       `${momento.getFullYear()} ` +
                       `${dos(momento.getHours())}:${dos(momento.getMinutes())}`;
            }
        }

        // Fecha y hora sin zona: 2026-10-30T14:05:00...
        const fechaHora = valor.match(
            /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/
        );

        if (fechaHora) {
            return `${fechaHora[3]}/${fechaHora[2]}/${fechaHora[1]} ` +
                   `${fechaHora[4]}:${fechaHora[5]}`;
        }
    }

    return String(valor);
}

// "USUARIOS" -> "Usuarios"
function nombreSeccion(texto) {
    if (!texto) {
        return 'Sin dato';
    }

    const t = String(texto).toLowerCase();
    return t.charAt(0).toUpperCase() + t.slice(1);
}

// "31/10/2026" -> "31 oct. 2026"
function fechaCorta(texto) {
    const partes = String(texto || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);

    if (!partes) {
        return texto || 'Sin dato';
    }

    return `${partes[1]} ${MESES[Number(partes[2]) - 1]} ${partes[3]}`;
}

/* =========================================================
   ESTILOS (se agregan una sola vez)
========================================================= */

function inyectarEstilosAuditoria() {
    if (document.getElementById('estilos-detalle-auditoria')) {
        return;
    }

    const estilos = document.createElement('style');
    estilos.id = 'estilos-detalle-auditoria';

    estilos.textContent = `
        /* ---------- Colores de cada acción (tabla y detalle) ---------- */
        .al-badge.aud-ini { background: #dbeafe; color: #1d4ed8; }
        .al-badge.aud-cre { background: #dcfce7; color: #166534; }
        .al-badge.aud-mod { background: #ffedd5; color: #c2410c; }
        .al-badge.aud-eli { background: #fee2e2; color: #b91c1c; }
        .al-badge.aud-cie { background: #ede9fe; color: #6d28d9; }
        .al-badge.aud-anu { background: #f1e7dc; color: #7a4a21; }

        /* ---------- Ventana más compacta ---------- */
        .aud-modal .aud-modal-contenido {
            width: min(500px, 92vw);
            max-width: 500px;
            max-height: 88vh;
            overflow-y: auto;
            padding: 22px 26px;
            border-radius: 16px;
        }

        .aud-modal .aud-modal-header {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 12px;
            padding-bottom: 14px;
            margin-bottom: 16px;
            border-bottom: 1px solid #e3eae6;
        }

        .aud-modal .aud-modal-header h2 {
            margin: 0;
            font-size: 19px;
            color: #14352a;
        }

        .aud-modal-sub {
            margin: 2px 0 0;
            font-size: 12px;
            color: #6b7c73;
        }

        .aud-modal .aud-modal-cerrar {
            flex: none;
            width: 32px;
            height: 32px;
            display: grid;
            place-items: center;
            padding: 0;
            border: none;
            border-radius: 8px;
            background: #eef3f0;
            color: #3d4f45;
            font-size: 20px;
            line-height: 1;
            cursor: pointer;
        }

        .aud-modal .aud-modal-cerrar:hover { background: #e1ebe5; }

        .aud-modal .aud-modal-footer { margin-top: 18px; }

        /* ---------- Contenido del detalle ---------- */
        #contenidoDetalleAuditoria .aud-det {
            display: flex;
            flex-direction: column;
            gap: 18px;
        }

        #contenidoDetalleAuditoria .aud-det-cab {
            display: flex;
            flex-direction: column;
            gap: 8px;
            align-items: flex-start;
            margin: 0;
            padding: 0 0 16px;
            border-bottom: 1px solid #e3eae6;
        }

        #contenidoDetalleAuditoria .aud-det-fecha {
            display: flex;
            align-items: center;
            gap: 6px;
            margin: 0;
            font-size: 13px;
            color: #6b7c73;
        }

        #contenidoDetalleAuditoria .aud-det-fecha svg {
            width: 14px;
            height: 14px;
        }

        #contenidoDetalleAuditoria svg {
            stroke: currentColor;
            fill: none;
            stroke-width: 2;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        #contenidoDetalleAuditoria .aud-det-bloque {
            margin: 0;
            padding: 0;
        }

        #contenidoDetalleAuditoria .aud-det-bloque h4 {
            margin: 0 0 12px;
            padding: 0;
            font-size: 14px;
            font-weight: 700;
            color: #14352a;
        }

        #contenidoDetalleAuditoria .aud-det-lista {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 14px 12px;
        }

        @media (max-width: 460px) {
            #contenidoDetalleAuditoria .aud-det-lista {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }

        #contenidoDetalleAuditoria .aud-det-fila {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        #contenidoDetalleAuditoria .aud-det-icono {
            flex: none;
            width: 30px;
            height: 30px;
            display: grid;
            place-items: center;
            border-radius: 8px;
            background: #e7efe9;
            color: #2f5d46;
        }

        #contenidoDetalleAuditoria .aud-det-icono svg {
            width: 15px;
            height: 15px;
        }

        #contenidoDetalleAuditoria .aud-det-fila small {
            display: block;
            margin: 0;
            font-size: 11px;
            line-height: 1.2;
            color: #6b7c73;
        }

        #contenidoDetalleAuditoria .aud-det-fila strong {
            display: block;
            margin: 0;
            font-size: 13px;
            line-height: 1.3;
            color: #14352a;
            word-break: break-word;
        }

        #contenidoDetalleAuditoria .aud-det-nota {
            margin: 0;
            padding: 8px 12px;
            background: #fffbeb;
            border: 1px solid #fde68a;
            border-radius: 8px;
            font-size: 12px;
            line-height: 1.5;
            color: #92400e;
        }

        #contenidoDetalleAuditoria .aud-det-nota strong {
            display: block;
            margin-bottom: 2px;
        }

        #contenidoDetalleAuditoria .aud-det-scroll {
            max-height: 240px;
            overflow: auto;
            border: 1px solid #e3eae6;
            border-radius: 8px;
        }

        #contenidoDetalleAuditoria .aud-det-tabla {
            width: 100%;
            margin: 0;
            border-collapse: collapse;
            font-size: 13px;
        }

        #contenidoDetalleAuditoria .aud-det-tabla th {
            position: sticky;
            top: 0;
            padding: 10px 14px;
            background: #f3f7f5;
            border-bottom: 1px solid #e3eae6;
            text-align: left;
            font-size: 11px;
            font-weight: 600;
            letter-spacing: .04em;
            text-transform: uppercase;
            color: #6b7c73;
        }

        #contenidoDetalleAuditoria .aud-det-tabla td {
            padding: 10px 14px;
            border-bottom: 1px solid #eef3f0;
            vertical-align: top;
            word-break: break-word;
            color: #1c2a23;
        }

        #contenidoDetalleAuditoria .aud-det-tabla tr:last-child td {
            border-bottom: none;
        }

        #contenidoDetalleAuditoria .aud-det-tabla td:first-child {
            width: 36%;
            font-weight: 600;
            color: #3d4f45;
        }

        #contenidoDetalleAuditoria .aud-det-antes {
            color: #6b7c73;
            text-decoration: line-through;
        }

        #contenidoDetalleAuditoria .aud-det-despues {
            font-weight: 600;
            color: #14532d;
        }

        #contenidoDetalleAuditoria .aud-det-sinvalor {
            color: #9aa8a0;
            font-style: italic;
            text-decoration: none;
        }
    `;

    document.head.appendChild(estilos);
}

inyectarEstilosAuditoria();

// Agrega el subtítulo debajo del título de la ventana.
function prepararCabeceraModal() {
    const titulo = document.getElementById('tituloModalAuditoria');

    if (!titulo || !titulo.parentNode) {
        return;
    }

    if (titulo.parentNode.querySelector('.aud-modal-sub')) {
        return;
    }

    const envoltorio = document.createElement('div');
    titulo.parentNode.insertBefore(envoltorio, titulo);
    envoltorio.appendChild(titulo);

    const subtitulo = document.createElement('p');
    subtitulo.className = 'aud-modal-sub';
    subtitulo.textContent = 'Información del registro de actividad';
    envoltorio.appendChild(subtitulo);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', prepararCabeceraModal);
} else {
    prepararCabeceraModal();
}

/* =========================================================
   ARMADO DEL DETALLE
========================================================= */

function crear(etiqueta, clase, texto) {
    const nodo = document.createElement(etiqueta);

    if (clase) {
        nodo.className = clase;
    }

    if (texto !== undefined) {
        nodo.textContent = texto;
    }

    return nodo;
}

// Ícono propio de la página (trazos fijos, no vienen del servidor).
function crearIcono(clase, nombre) {
    const nodo = crear('span', clase);

    nodo.innerHTML =
        '<svg viewBox="0 0 24 24" aria-hidden="true">' +
        ICONOS[nombre] +
        '</svg>';

    return nodo;
}

function crearTabla(encabezados, filas, clasesCelda) {
    const envoltorio = crear('div', 'aud-det-scroll');
    const tabla = crear('table', 'aud-det-tabla');

    const cabecera = tabla.createTHead().insertRow();

    encabezados.forEach(texto => {
        const th = document.createElement('th');
        th.textContent = texto;
        cabecera.appendChild(th);
    });

    const cuerpo = tabla.createTBody();

    filas.forEach(valores => {
        const fila = cuerpo.insertRow();

        valores.forEach((valor, posicion) => {
            const celda = fila.insertCell();
            const clase = clasesCelda && clasesCelda[posicion];

            if (valor === SIN_VALOR) {
                celda.appendChild(crear('span', 'aud-det-sinvalor', valor));
            } else if (clase) {
                celda.appendChild(crear('span', clase, valor));
            } else {
                celda.textContent = valor;
            }
        });
    });

    envoltorio.appendChild(tabla);
    return envoltorio;
}

function crearFila(icono, etiqueta, valor) {
    const fila = crear('div', 'aud-det-fila');
    const texto = crear('div');

    texto.appendChild(crear('small', '', etiqueta));
    texto.appendChild(crear('strong', '', valor ?? 'Sin dato'));

    fila.appendChild(crearIcono('aud-det-icono', icono));
    fila.appendChild(texto);

    return fila;
}

function armarDetalle(contenido, datos) {
    contenido.replaceChildren();

    const detalle = crear('div', 'aud-det');

    // Insignia de la acción, con la fecha y la hora debajo.
    const cabecera = crear('div', 'aud-det-cab');

    cabecera.appendChild(
        crear(
            'span',
            'al-badge ' + (CLASES_ACCION[datos.accion] || ''),
            NOMBRES_ACCION[datos.accion] || datos.accion
        )
    );

    const momento = crear('p', 'aud-det-fecha');
    momento.appendChild(crearIcono('', 'reloj'));
    momento.appendChild(
        document.createTextNode(
            `${fechaCorta(datos.fecha)} · ${datos.hora} hs`
        )
    );
    cabecera.appendChild(momento);

    detalle.appendChild(cabecera);

    // Datos básicos.
    const bloque = crear('section', 'aud-det-bloque');
    bloque.appendChild(crear('h4', '', 'Datos generales'));

    const lista = crear('div', 'aud-det-lista');
    lista.appendChild(crearFila('usuario', 'Usuario', datos.usuario));
    lista.appendChild(crearFila('perfil', 'Perfil', datos.perfil));
    lista.appendChild(
        crearFila('seccion', 'Sección', nombreSeccion(datos.entidad))
    );

    bloque.appendChild(lista);
    detalle.appendChild(bloque);

    // Inicio y cierre de sesión: no hay datos que mostrar.
    if (datos.modo === 'ninguno') {
        contenido.appendChild(detalle);
        return;
    }

    // Altas y eliminaciones: los datos del registro.
    if (datos.modo === 'datos') {
        const campos = datos.datos || [];
        const nota = campos.find(d => d.campo === 'Nota');
        const filas = campos.filter(
            d => d.campo !== 'Nota' &&
                 campoVisible(d.campo) &&
                 !(CAMPOS_ANULACION.includes(d.campo) && estaVacio(d.valor))
        );

        if (nota) {
            const aviso = crear('div', 'aud-det-nota');
            aviso.appendChild(crear('strong', '', 'Nota'));
            aviso.appendChild(document.createTextNode(String(nota.valor)));
            detalle.appendChild(aviso);
        }

        const seccion = crear('section', 'aud-det-bloque');

        seccion.appendChild(
            crear(
                'h4',
                '',
                datos.accion === 'ELIMINACION'
                    ? 'Datos eliminados'
                    : 'Datos registrados'
            )
        );

        if (filas.length === 0) {
            seccion.appendChild(
                crear('p', 'aud-det-vacio', 'No hay datos registrados.')
            );
        } else {
            seccion.appendChild(
                crearTabla(
                    ['Campo', 'Detalle'],
                    filas.map(d => [
                        etiquetaCampo(d.campo),
                        formatearValor(d.valor, d.campo)
                    ])
                )
            );
        }

        detalle.appendChild(seccion);
        contenido.appendChild(detalle);
        return;
    }

    // Modificaciones y anulaciones.
    const esAnulacion = datos.accion === 'ANULACION';

    const seccion = crear('section', 'aud-det-bloque');

    seccion.appendChild(
        crear(
            'h4',
            '',
            esAnulacion ? 'Datos de la anulación' : 'Cambios realizados'
        )
    );

    const cambiosVisibles = (datos.cambios || []).filter(
        c => campoVisible(c.campo) &&
             !(esAnulacion && REPETIDOS_EN_ANULACION.includes(c.campo))
    );

    if (cambiosVisibles.length === 0) {
        seccion.appendChild(
            crear(
                'p',
                'aud-det-vacio',
                'No hay cambios de campos registrados.'
            )
        );
    } else if (esAnulacion) {
        // En una anulación solo importa lo que quedó registrado.
        seccion.appendChild(
            crearTabla(
                ['Campo', 'Detalle'],
                cambiosVisibles.map(c => [
                    etiquetaCampo(c.campo),
                    formatearValor(c.despues, c.campo)
                ]),
                [null, 'aud-det-despues']
            )
        );
    } else {
        seccion.appendChild(
            crearTabla(
                ['Campo', 'Anterior', 'Actual'],
                cambiosVisibles.map(c => [
                    etiquetaCampo(c.campo),
                    formatearValor(c.antes, c.campo),
                    formatearValor(c.despues, c.campo)
                ]),
                [null, 'aud-det-antes', 'aud-det-despues']
            )
        );
    }

    detalle.appendChild(seccion);
    contenido.appendChild(detalle);
}

/* =========================================================
   MODAL
========================================================= */

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
        .then(datos => armarDetalle(contenido, datos))
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