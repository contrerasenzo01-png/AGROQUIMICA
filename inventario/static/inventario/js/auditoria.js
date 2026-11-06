
console.log('auditoria.js se cargó correctamente');

/* =========================================================
   TEXTOS
========================================================= */

// Nombre legible de cada acción.
const NOMBRES_ACCION = {
    CREACION: 'Creación',
    MODIFICACION: 'Modificación',
    ELIMINACION: 'Eliminación',
    ANULACION: 'Anulación de venta',
    ANULACION_REMITO: 'Anulación de remito',
    INICIO_SESION: 'Inicio de sesión',
    CIERRE_SESION: 'Cierre de sesión',
    BLOQUEO_INACTIVIDAD: 'Bloqueo por inactividad',
    EGRESO_STOCK: 'Egreso de stock',
    EGRESO_VENCIMIENTO: 'Egreso por vencimiento',
    INGRESO_LOTE: 'Ingreso de lote',
    DESCARGA_PDF: 'Descarga de PDF',
    ASIGNACION_PERFIL: 'Asignación de perfil',
    ASIGNACION_PERMISOS: 'Asignación de permisos',
    ATENCION_ALERTA: 'Atención de alerta',
    BAJA: 'Baja',
    ACTIVACION: 'Activación',
    RESET_CONTRASENA: 'Restablecimiento de contraseña',
    ENVIO_RECUPERACION: 'Envío de enlace de recuperación',
    RECUPERA_CONTRASENA: 'Recuperación de contraseña'
};

// Clase de la insignia de cada acción.
const CLASES_ACCION = {
    CREACION: 'aud-cre',
    MODIFICACION: 'aud-mod',
    ELIMINACION: 'aud-eli',
    ANULACION: 'aud-anu',
    ANULACION_REMITO: 'aud-anu-remito',
    INICIO_SESION: 'aud-ini',
    CIERRE_SESION: 'aud-cie',
    BLOQUEO_INACTIVIDAD: 'aud-blq',
    EGRESO_STOCK: 'aud-egr',
    EGRESO_VENCIMIENTO: 'aud-egr-ven',
    INGRESO_LOTE: 'aud-ing',
    DESCARGA_PDF: 'aud-pdf',
    ASIGNACION_PERFIL: 'aud-asp',
    ASIGNACION_PERMISOS: 'aud-asm',
    ATENCION_ALERTA: 'aud-ate',
    BAJA: 'aud-baj',
    ACTIVACION: 'aud-act',
    RESET_CONTRASENA: 'aud-res',
    ENVIO_RECUPERACION: 'aud-env',
    RECUPERA_CONTRASENA: 'aud-rec'
};

const MESES = [
    'ene.', 'feb.', 'mar.', 'abr.', 'may.', 'jun.',
    'jul.', 'ago.', 'sep.', 'oct.', 'nov.', 'dic.'
];

// Íconos.

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


// Nombre legible de los campos.
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

    // Auditoría de stock, PDF y permisos
    Lote: 'Número de lote',
    Cantidad: 'Cantidad',
    Lote_antes: 'Cantidad del lote antes',
    Lote_despues: 'Cantidad del lote después',
    Stock_antes: 'Stock antes',
    Stock_despues: 'Stock después',
    Observaciones: 'Observaciones',
    Documento: 'Documento',
    Archivo: 'Archivo',
    Tipo_movimiento: 'Tipo de movimiento',
    Perfil: 'Perfil',
    Permisos: 'Permisos',
    Agregados: 'Permisos agregados',
    Quitados: 'Permisos quitados',
    Cantidad_lotes: 'Cantidad de lotes',
    Lotes_revertidos: 'Cantidad de lotes revertidos',

    // Alertas
    Atendida: 'Atendida',
    Fecha_hora_atencion: 'Fecha de atención',

    // Recuperación de contraseña
    Correo: 'Correo',

    // Otros
    Nota: 'Nota',
    accion: 'Acción'
};

// Campos de la anulación de un remito.
const CAMPOS_ANULACION = [
    'Fecha_anulacion',
    'Motivo_anulacion',
    'ID_Usuario_anulacion'
];

// Campos que no deben repetirse en la tabla de cambios.
const REPETIDOS_EN_ANULACION = [
    'Fecha_anulacion',
    'ID_Usuario_anulacion'
];

function estaVacio(valor) {
    return valor === null || valor === undefined || valor === '';
}

const SIN_VALOR = 'Sin valor';

// Los campos con ID no se muestran, salvo los conocidos.
function campoVisible(campo) {
    return !String(campo).startsWith('ID_') ||
           ETIQUETAS_CAMPO[campo] !== undefined;
}

// Nombre de un campo.
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
        const fecha = valor.match(/^(\d{4})-(\d{2})-(\d{2})$/);

        if (fecha) {
            return `${fecha[3]}/${fecha[2]}/${fecha[1]}`;
        }

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

// Ícono propio de la página.
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

// ¿El nombre del registro ya se ve en el detalle? (usuario que hizo la
// acción, o algún valor de la tabla de datos o de cambios). Si es así,
// la tarjeta "Registro" no se muestra para no repetirlo.
function nombreYaVisible(datos) {
    const normalizar = t => String(t ?? '').trim().toLowerCase();

    const visibles = new Set([normalizar(datos.usuario)]);

    (datos.datos || []).forEach(d => visibles.add(normalizar(d.valor)));
    (datos.cambios || []).forEach(c => {
        visibles.add(normalizar(c.antes));
        visibles.add(normalizar(c.despues));
    });

    const nombre = normalizar(datos.nombre_registro);
    if (visibles.has(nombre)) {
        return true;
    }

    // Nombres compuestos ("Apellido, Nombre", "Producto · Lote X",
    // "Remito X"): están repetidos si cada parte ya aparece.
    const partes = nombre
        .split(/\s*·\s*|,\s*/)
        .map(p => p.replace(/^(lote|remito)\s+/, ''))
        .filter(Boolean);

    return partes.length > 1 && partes.every(p => visibles.has(p));
}

function armarDetalle(contenido, datos) {
    contenido.replaceChildren();

    const detalle = crear('div', 'aud-det');

    // Insignia de la acción.
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

    // Nombre del registro afectado (producto, proveedor, usuario...).
    // Solo si no aparece ya en otro lado del detalle.
    if (datos.nombre_registro && !nombreYaVisible(datos)) {
        const registro = crearFila('id', 'Registro', datos.nombre_registro);
        registro.classList.add('aud-det-fila-registro');
        lista.appendChild(registro);
    }

    bloque.appendChild(lista);
    detalle.appendChild(bloque);

    // Inicio y cierre de sesión.
    if (datos.modo === 'ninguno') {
        contenido.appendChild(detalle);
        return;
    }

    // Altas y eliminaciones.
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

    // Modificaciones, anulaciones, atención de alertas y egresos.
    const esAnulacion =
        datos.accion === 'ANULACION' ||
        datos.accion === 'ANULACION_REMITO';

    const esAtencion = datos.accion === 'ATENCION_ALERTA';
    const esEgresoVencimiento = datos.accion === 'EGRESO_VENCIMIENTO';

    let tituloSeccion = 'Cambios realizados';

    if (datos.accion === 'ANULACION') {
        tituloSeccion = 'Datos de la anulación de venta';
    } else if (datos.accion === 'ANULACION_REMITO') {
        tituloSeccion = 'Datos de la anulación del remito';
    } else if (esAtencion) {
        tituloSeccion = 'Datos de la atención';
    } else if (esEgresoVencimiento) {
        tituloSeccion = 'Datos del egreso por vencimiento';
    }

    const seccion = crear('section', 'aud-det-bloque');
    seccion.appendChild(crear('h4', '', tituloSeccion));

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
    } else if (esAnulacion || esEgresoVencimiento) {
        // En una anulación o egreso se muestran los datos finales.
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

    if (!modal || !contenido) {
        console.error('No se encontró el modal o su contenido.');
        return;
    }

    modal.classList.add('activo');
    modal.setAttribute('aria-hidden', 'false');

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

// Cerrar al presionar Escape.
document.addEventListener('keydown', evento => {
    if (evento.key === 'Escape') {
        cerrarDetalleAuditoria();
    }
});

// Cerrar al hacer clic fuera del contenido.
document.addEventListener('click', evento => {
    const modal = document.getElementById('modalAuditoria');

    if (modal && evento.target === modal) {
        cerrarDetalleAuditoria();
    }
});
