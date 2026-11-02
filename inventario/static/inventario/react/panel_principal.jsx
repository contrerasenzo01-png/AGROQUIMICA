/* ============================================================
   PANEL PRINCIPAL · Agroquímica del Valle
   Componente React con clases de Bootstrap 5.3.
   Los datos los arma views.py (_datos_panel) y llegan en el
   <script id="datos-panel"> del template.
   ============================================================ */

const { useState, useMemo } = React;

const DATOS = JSON.parse(
    document.getElementById('datos-panel').textContent
);


/* ------------------------------------------------------------
   UTILIDADES
   ------------------------------------------------------------ */

function formatearNumero(valor) {
    return Number(valor || 0).toLocaleString('es-AR');
}

function saludoSegunHora() {
    const hora = new Date().getHours();

    if (hora < 12) return 'Buenos días';
    if (hora < 20) return 'Buenas tardes';
    return 'Buenas noches';
}

function fechaDeHoy() {
    const texto = new Date().toLocaleDateString('es-AR', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric',
    });

    return texto.charAt(0).toUpperCase() + texto.slice(1);
}

function textoDias(dias) {
    if (dias < 0) return 'Vencido';
    if (dias === 0) return 'Vence hoy';
    if (dias === 1) return 'Vence mañana';
    return 'Vence en ' + dias + ' días';
}

/* Etiqueta suave de Bootstrap: fondo claro, texto y borde del mismo color */
function claseEtiqueta(color) {
    return `badge rounded-pill bg-${color}-subtle text-${color}-emphasis border border-${color}-subtle`;
}

/* Color de Bootstrap para cada tarjeta y cada tipo de movimiento */
const COLOR_METRICA = { green: 'success', blue: 'info', red: 'danger', orange: 'warning' };
const COLOR_MOVIMIENTO = { entrada: 'success', salida: 'danger', vencimiento: 'warning', anulacion: 'secondary' };


/* ------------------------------------------------------------
   ÍCONOS (línea, del mismo estilo que el menú)
   ------------------------------------------------------------ */

const TRAZOS = {
    usuarios: ['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2', 'M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z', 'M22 21v-2a4 4 0 0 0-3-3.87', 'M16 3.13a4 4 0 0 1 0 7.75'],
    productos: ['m21 16-9 5-9-5V8l9-5 9 5v8Z', 'm3.3 7.8 8.7 5 8.7-5', 'M12 22V12.8'],
    stock_bajo: ['M22 17 13.5 8.5 8.5 13.5 2 7', 'M16 17h6v-6'],
    por_vencer: ['M8 2v4', 'M16 2v4', 'M3 10h18', 'M21 12V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h7', 'M18 15v3l2 1'],
    alertas: ['M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9', 'M13.73 21a2 2 0 0 1-3.46 0'],
};

function Icono({ nombre }) {
    return (
        <svg className="pp-svg" viewBox="0 0 24 24" aria-hidden="true">
            {(TRAZOS[nombre] || TRAZOS.productos).map((d, i) => <path key={i} d={d} />)}
        </svg>
    );
}


/* ------------------------------------------------------------
   ENCABEZADO
   ------------------------------------------------------------ */

function Encabezado({ usuario }) {
    return (
        <header className="mb-4">
            <h1 className="mb-1">Panel Principal</h1>
            <p className="text-body-secondary small mb-0">
                {saludoSegunHora()}, {usuario.nombre} · {fechaDeHoy()}
            </p>
        </header>
    );
}


/* ------------------------------------------------------------
   TARJETAS DE MÉTRICAS (grilla de Bootstrap)
   ------------------------------------------------------------ */

function TarjetaMetrica({ metrica }) {
    const color = COLOR_METRICA[metrica.color] || 'success';
    const Elemento = metrica.url ? 'a' : 'div';

    return (
        <div className="col-12 col-sm-6 col-xl">
            <Elemento
                href={metrica.url || undefined}
                className={'card h-100 pp-metrica' + (metrica.url ? ' pp-metrica-link' : '')}
            >
                <div className="card-body d-flex align-items-start gap-3">
                    <span className={`pp-metrica-icono bg-${color}-subtle text-${color}-emphasis`}>
                        <Icono nombre={metrica.clave} />
                    </span>

                    <div className="overflow-hidden">
                        <div className="small fw-semibold text-body-secondary text-truncate">
                            {metrica.titulo}
                        </div>
                        <div className="fs-3 fw-bold lh-sm pp-metrica-valor">
                            {formatearNumero(metrica.valor)}
                        </div>
                        <div className="small text-body-secondary">{metrica.detalle}</div>
                    </div>
                </div>
            </Elemento>
        </div>
    );
}

function Metricas({ metricas }) {
    if (!metricas.length) return null;

    return (
        <section className="row g-3 mb-4">
            {metricas.map(m => <TarjetaMetrica key={m.clave} metrica={m} />)}
        </section>
    );
}


/* ------------------------------------------------------------
   ENCABEZADO DE TARJETA
   ------------------------------------------------------------ */

function CabeceraTarjeta({ titulo, children }) {
    return (
        <div className="card-header bg-transparent d-flex flex-wrap justify-content-between align-items-center gap-2 py-3">
            <h2 className="mb-0">{titulo}</h2>
            {children}
        </div>
    );
}

function EnlaceVerTodo({ url, texto }) {
    return (
        <a className="link-success fw-semibold small text-decoration-none" href={url}>
            {texto} →
        </a>
    );
}

function Vacio({ texto, ok }) {
    return (
        <div className={`alert ${ok ? 'alert-success' : 'alert-light'} small text-center py-2 mb-0`}>
            {texto}
        </div>
    );
}


/* ------------------------------------------------------------
   GRÁFICO: PRODUCTOS POR SUBTIPO (barras de progreso)
   ------------------------------------------------------------ */

function GraficoProductos({ datos, url }) {
    const maximo = Math.max(1, ...datos.map(d => d.cantidad));
    const total = datos.reduce((suma, d) => suma + d.cantidad, 0);

    return (
        <div className="card h-100">
            <CabeceraTarjeta titulo="Productos activos por subtipo">
                <EnlaceVerTodo url={url} texto="Ver productos" />
            </CabeceraTarjeta>

            <div className="card-body">
                {datos.length === 0 ? (
                    <Vacio texto="Todavía no hay productos activos." />
                ) : (
                    <>
                        {datos.map((d, i) => (
                            <div key={d.nombre} className="mb-3">
                                <div className="d-flex justify-content-between small mb-1">
                                    <span className="fw-semibold text-truncate me-2">{d.nombre}</span>
                                    <span className="fw-bold">{d.cantidad}</span>
                                </div>

                                <div
                                    className="progress pp-progreso"
                                    role="progressbar"
                                    aria-label={d.nombre}
                                    aria-valuenow={d.cantidad}
                                    aria-valuemin="0"
                                    aria-valuemax={maximo}
                                >
                                    <div
                                        className={'progress-bar pp-barra-' + (i % 5)}
                                        style={{ width: (d.cantidad / maximo) * 100 + '%' }}
                                    />
                                </div>
                            </div>
                        ))}

                        <p className="small text-body-secondary mb-0">
                            {total} producto{total === 1 ? '' : 's'} activo{total === 1 ? '' : 's'} en total
                        </p>
                    </>
                )}
            </div>
        </div>
    );
}


/* ------------------------------------------------------------
   ATENCIÓN: STOCK BAJO Y LOTES POR VENCER
   ------------------------------------------------------------ */

function BotonSegmento({ activo, onClick, children }) {
    return (
        <button
            type="button"
            role="tab"
            aria-selected={activo}
            className={'btn ' + (activo ? 'btn-success' : 'btn-outline-success')}
            onClick={onClick}
        >
            {children}
        </button>
    );
}

function PanelAtencion({ stockBajo, porVencer, permisos, urls }) {
    const [pestana, setPestana] = useState(
        permisos.productos ? 'stock' : 'vencer'
    );
    const [dias, setDias] = useState(30);

    const lotesFiltrados = useMemo(
        () => porVencer.filter(l => l.dias <= dias),
        [porVencer, dias]
    );

    return (
        <div className="card h-100">
            <CabeceraTarjeta titulo="Requieren atención" />

            <div className="card-body">
                <div className="btn-group btn-group-sm w-100 mb-3" role="tablist">
                    {permisos.productos && (
                        <BotonSegmento activo={pestana === 'stock'} onClick={() => setPestana('stock')}>
                            Stock bajo
                            <span className="badge rounded-pill pp-contador ms-2">{stockBajo.length}</span>
                        </BotonSegmento>
                    )}

                    <BotonSegmento activo={pestana === 'vencer'} onClick={() => setPestana('vencer')}>
                        Por vencer
                        <span className="badge rounded-pill pp-contador ms-2">{porVencer.length}</span>
                    </BotonSegmento>
                </div>

                {pestana === 'stock' && (
                    <ListaStockBajo items={stockBajo} url={urls.productos} />
                )}

                {pestana === 'vencer' && (
                    <>
                        <div className="d-flex align-items-center gap-2 mb-3">
                            <label htmlFor="pp-dias" className="small text-body-secondary mb-0">
                                Mostrar
                            </label>
                            <select
                                id="pp-dias"
                                className="form-select form-select-sm w-auto"
                                value={dias}
                                onChange={e => setDias(Number(e.target.value))}
                            >
                                <option value={7}>Próximos 7 días</option>
                                <option value={15}>Próximos 15 días</option>
                                <option value={30}>Próximos 30 días</option>
                            </select>
                        </div>

                        <ListaPorVencer
                            items={lotesFiltrados}
                            url={permisos.lotes ? urls.lotes : ''}
                        />
                    </>
                )}
            </div>
        </div>
    );
}

function ListaStockBajo({ items, url }) {
    if (!items.length) {
        return <Vacio ok texto="Ningún producto está por debajo de su stock mínimo." />;
    }

    return (
        <div className="list-group pp-lista">
            {items.map(p => (
                <a
                    key={p.id}
                    href={url}
                    className="list-group-item list-group-item-action d-flex justify-content-between align-items-center gap-2"
                >
                    <span className="fw-semibold small">{p.producto}</span>
                    <span className={claseEtiqueta('danger')}>
                        {p.stock === 0 ? 'Sin stock' : formatearNumero(p.stock)} / mín. {formatearNumero(p.minimo)} un.
                    </span>
                </a>
            ))}
        </div>
    );
}

function ListaPorVencer({ items, url }) {
    if (!items.length) {
        return <Vacio ok texto="No hay lotes que venzan en ese período." />;
    }

    const Elemento = url ? 'a' : 'div';

    return (
        <div className="list-group pp-lista">
            {items.map(l => (
                <Elemento
                    key={l.id}
                    href={url || undefined}
                    className={
                        'list-group-item d-flex justify-content-between align-items-center gap-2' +
                        (url ? ' list-group-item-action' : '')
                    }
                >
                    <span>
                        <span className="fw-semibold small d-block">{l.producto}</span>
                        <span className="small text-body-secondary">
                            Lote {l.lote} · {formatearNumero(l.cantidad)} un. · {l.vence}
                        </span>
                    </span>
                    <span className={claseEtiqueta(l.dias < 0 ? 'danger' : 'warning')}>
                        {textoDias(l.dias)}
                    </span>
                </Elemento>
            ))}
        </div>
    );
}


/* ------------------------------------------------------------
   ÚLTIMOS MOVIMIENTOS (tabla de Bootstrap)
   ------------------------------------------------------------ */

const FILTROS_MOVIMIENTO = [
    { clave: 'todos', texto: 'Todos' },
    { clave: 'entrada', texto: 'Entradas' },
    { clave: 'salidas', texto: 'Salidas' },
];

function TablaMovimientos({ movimientos, url }) {
    const [filtro, setFiltro] = useState('todos');

    const visibles = movimientos.filter(m => {
        if (filtro === 'entrada') return m.clase === 'entrada';
        if (filtro === 'salidas') return m.clase !== 'entrada';
        return true;
    });

    return (
        <section className="card">
            <CabeceraTarjeta titulo="Últimos movimientos de stock">
                <div className="d-flex flex-wrap align-items-center gap-3">
                    <div className="btn-group btn-group-sm" role="group" aria-label="Filtrar movimientos">
                        {FILTROS_MOVIMIENTO.map(f => (
                            <button
                                key={f.clave}
                                type="button"
                                className={'btn ' + (filtro === f.clave ? 'btn-success' : 'btn-outline-success')}
                                onClick={() => setFiltro(f.clave)}
                            >
                                {f.texto}
                            </button>
                        ))}
                    </div>

                    <EnlaceVerTodo url={url} texto="Ver todos" />
                </div>
            </CabeceraTarjeta>

            {visibles.length === 0 ? (
                <div className="card-body">
                    <Vacio texto="No hay movimientos para mostrar." />
                </div>
            ) : (
                <div className="table-responsive">
                    <table className="table table-hover align-middle mb-0 pp-tabla">
                        <thead>
                            <tr>
                                <th>N.º</th>
                                <th>Fecha</th>
                                <th>Producto</th>
                                <th>Tipo</th>
                                <th className="text-end">Cantidad</th>
                                <th>Observaciones</th>
                                <th></th>
                            </tr>
                        </thead>

                        <tbody>
                            {visibles.map(m => (
                                <tr key={m.id}>
                                    <td className="fw-bold text-nowrap">
                                        MOV-{String(m.id).padStart(4, '0')}
                                    </td>

                                    <td className="text-nowrap">
                                        {m.fecha}
                                        <div className="small text-body-secondary">{m.hora} · {m.usuario}</div>
                                    </td>

                                    <td>
                                        {m.producto}
                                        {m.lote && <div className="small text-body-secondary">Lote {m.lote}</div>}
                                    </td>

                                    <td>
                                        <span className={claseEtiqueta(COLOR_MOVIMIENTO[m.clase] || 'secondary')}>
                                            {m.tipo}
                                        </span>
                                    </td>

                                    <td className={'text-end fw-bold ' + (m.cantidad > 0 ? 'text-success' : 'text-danger')}>
                                        {m.cantidad > 0 ? '+' : ''}{formatearNumero(m.cantidad)}
                                    </td>

                                    <td className="text-body-secondary">{m.observaciones || '—'}</td>

                                    <td className="text-end">
                                        {m.comprobante && (
                                            <a
                                                className="btn btn-sm btn-outline-success"
                                                href={m.comprobante}
                                                target="_blank"
                                                rel="noopener"
                                                title="Ver comprobante PDF"
                                                aria-label="Ver comprobante PDF"
                                            >
                                                PDF
                                            </a>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </section>
    );
}


/* ------------------------------------------------------------
   PANEL COMPLETO
   ------------------------------------------------------------ */

function Panel() {
    const { usuario, permisos, urls } = DATOS;

    const muestraAtencion = permisos.productos || permisos.lotes;

    return (
        <div className="container-fluid px-0">
            <Encabezado usuario={usuario} />

            <Metricas metricas={DATOS.metricas} />

            {(permisos.productos || muestraAtencion) && (
                <section className="row g-3 mb-4">
                    {permisos.productos && (
                        <div className={'col-12' + (muestraAtencion ? ' col-xl-6' : '')}>
                            <GraficoProductos datos={DATOS.grafico} url={urls.productos} />
                        </div>
                    )}

                    {muestraAtencion && (
                        <div className={'col-12' + (permisos.productos ? ' col-xl-6' : '')}>
                            <PanelAtencion
                                stockBajo={DATOS.stock_bajo}
                                porVencer={DATOS.por_vencer}
                                permisos={permisos}
                                urls={urls}
                            />
                        </div>
                    )}
                </section>
            )}

            {permisos.movimientos && (
                <TablaMovimientos movimientos={DATOS.movimientos} url={urls.movimientos} />
            )}
        </div>
    );
}


ReactDOM.createRoot(document.getElementById('panel-raiz')).render(<Panel />);