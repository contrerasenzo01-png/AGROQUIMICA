/* ============================================================
   PANEL PRINCIPAL · Agroquímica del Valle
   Componente React. Los datos los arma views.py (_datos_panel)
   y llegan en el <script id="datos-panel"> del template.
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


/* ------------------------------------------------------------
   ENCABEZADO
   ------------------------------------------------------------ */

function Encabezado({ usuario }) {
    return (
        <header className="header">
            <h1>Panel Principal</h1>
            <div className="subtitle">
                {saludoSegunHora()}, {usuario.nombre} · {fechaDeHoy()}
            </div>
        </header>
    );
}


/* ------------------------------------------------------------
   TARJETAS DE MÉTRICAS
   ------------------------------------------------------------ */

function TarjetaMetrica({ metrica }) {
    const contenido = (
        <>
            <div className="metric-title">{metrica.titulo}</div>
            <div className={'metric-value ' + metrica.color}>
                {formatearNumero(metrica.valor)}
            </div>
            <div className="pp-metric-detalle">{metrica.detalle}</div>
        </>
    );

    // Si el usuario puede entrar al módulo, la tarjeta es un enlace.
    if (metrica.url) {
        return (
            <a className="metric-card pp-metric-link" href={metrica.url}>
                {contenido}
            </a>
        );
    }

    return <div className="metric-card">{contenido}</div>;
}

function Metricas({ metricas }) {
    if (!metricas.length) return null;

    return (
        <section className="metrics-grid">
            {metricas.map(m => <TarjetaMetrica key={m.clave} metrica={m} />)}
        </section>
    );
}


/* ------------------------------------------------------------
   GRÁFICO: PRODUCTOS POR SUBTIPO
   ------------------------------------------------------------ */

function GraficoProductos({ datos, url }) {
    const maximo = Math.max(1, ...datos.map(d => d.cantidad));
    const total = datos.reduce((suma, d) => suma + d.cantidad, 0);

    return (
        <div className="card-panel">
            <div className="pp-panel-cab">
                <h2>Productos activos por subtipo</h2>
                <a className="pp-ver-todo" href={url}>Ver productos →</a>
            </div>

            {datos.length === 0 ? (
                <p className="pp-vacio">Todavía no hay productos activos.</p>
            ) : (
                <>
                    <ul className="pp-barras">
                        {datos.map((d, i) => (
                            <li key={d.nombre} className="pp-barra-fila">
                                <span className="pp-barra-nombre" title={d.nombre}>
                                    {d.nombre}
                                </span>

                                <span className="pp-barra-pista">
                                    <span
                                        className={'pp-barra pp-color-' + (i % 5)}
                                        style={{ width: (d.cantidad / maximo) * 100 + '%' }}
                                    />
                                </span>

                                <span className="pp-barra-valor">{d.cantidad}</span>
                            </li>
                        ))}
                    </ul>

                    <p className="pp-nota">
                        {total} producto{total === 1 ? '' : 's'} activo{total === 1 ? '' : 's'} en total
                    </p>
                </>
            )}
        </div>
    );
}


/* ------------------------------------------------------------
   ATENCIÓN: STOCK BAJO Y LOTES POR VENCER
   ------------------------------------------------------------ */

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
        <div className="card-panel">
            <div className="pp-panel-cab">
                <h2>Requieren atención</h2>
            </div>

            <div className="pp-tabs" role="tablist">
                {permisos.productos && (
                    <button
                        type="button"
                        role="tab"
                        aria-selected={pestana === 'stock'}
                        className={'pp-tab' + (pestana === 'stock' ? ' activa' : '')}
                        onClick={() => setPestana('stock')}
                    >
                        Stock bajo
                        <span className="pp-tab-contador">{stockBajo.length}</span>
                    </button>
                )}

                <button
                    type="button"
                    role="tab"
                    aria-selected={pestana === 'vencer'}
                    className={'pp-tab' + (pestana === 'vencer' ? ' activa' : '')}
                    onClick={() => setPestana('vencer')}
                >
                    Por vencer
                    <span className="pp-tab-contador">{porVencer.length}</span>
                </button>
            </div>

            {pestana === 'stock' && (
                <ListaStockBajo items={stockBajo} url={urls.productos} />
            )}

            {pestana === 'vencer' && (
                <>
                    <div className="pp-filtro-dias">
                        <label htmlFor="pp-dias">Mostrar</label>
                        <select
                            id="pp-dias"
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
    );
}

function ListaStockBajo({ items, url }) {
    if (!items.length) {
        return <p className="pp-vacio pp-vacio-ok">Ningún producto está por debajo de su stock mínimo.</p>;
    }

    return (
        <div className="stock-list">
            {items.map(p => (
                <a key={p.id} className="stock-item pp-item-link" href={url}>
                    <span className="stock-name">{p.producto}</span>
                    <span className="stock-qty">
                        {p.stock === 0 ? 'Sin stock' : formatearNumero(p.stock)} / mín. {formatearNumero(p.minimo)} un.
                    </span>
                </a>
            ))}
        </div>
    );
}

function ListaPorVencer({ items, url }) {
    if (!items.length) {
        return <p className="pp-vacio pp-vacio-ok">No hay lotes que venzan en ese período.</p>;
    }

    const Elemento = url ? 'a' : 'div';

    return (
        <div className="stock-list">
            {items.map(l => (
                <Elemento
                    key={l.id}
                    className={'stock-item pp-vence' + (l.dias < 0 ? ' pp-vencido' : '') + (url ? ' pp-item-link' : '')}
                    href={url || undefined}
                >
                    <span>
                        <span className="stock-name">{l.producto}</span>
                        <span className="pp-sub">
                            Lote {l.lote} · {formatearNumero(l.cantidad)} un. · {l.vence}
                        </span>
                    </span>
                    <span className="stock-qty">{textoDias(l.dias)}</span>
                </Elemento>
            ))}
        </div>
    );
}


/* ------------------------------------------------------------
   ÚLTIMOS MOVIMIENTOS
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
        <section className="card-panel">
            <div className="pp-panel-cab">
                <h2>Últimos movimientos de stock</h2>

                <div className="pp-chips">
                    {FILTROS_MOVIMIENTO.map(f => (
                        <button
                            key={f.clave}
                            type="button"
                            className={'pp-chip' + (filtro === f.clave ? ' activa' : '')}
                            onClick={() => setFiltro(f.clave)}
                        >
                            {f.texto}
                        </button>
                    ))}

                    <a className="pp-ver-todo" href={url}>Ver todos →</a>
                </div>
            </div>

            {visibles.length === 0 ? (
                <p className="pp-vacio">No hay movimientos para mostrar.</p>
            ) : (
                <div className="table-container">
                    <table className="custom-table">
                        <thead>
                            <tr>
                                <th>N.º</th>
                                <th>Fecha</th>
                                <th>Producto</th>
                                <th>Tipo</th>
                                <th>Cantidad</th>
                                <th>Observaciones</th>
                                <th></th>
                            </tr>
                        </thead>

                        <tbody>
                            {visibles.map(m => (
                                <tr key={m.id}>
                                    <td className="id-mov">MOV-{String(m.id).padStart(4, '0')}</td>

                                    <td>
                                        {m.fecha}
                                        <span className="pp-sub">{m.hora} · {m.usuario}</span>
                                    </td>

                                    <td>
                                        {m.producto}
                                        {m.lote && <span className="pp-sub">Lote {m.lote}</span>}
                                    </td>

                                    <td>
                                        <span className={'badge-tag ' + m.clase}>{m.tipo}</span>
                                    </td>

                                    <td className={m.cantidad > 0 ? 'qty-positive' : 'qty-negative'}>
                                        {m.cantidad > 0 ? '+' : ''}{formatearNumero(m.cantidad)}
                                    </td>

                                    <td className="obs-text">{m.observaciones || '—'}</td>

                                    <td className="pp-celda-accion">
                                        {m.comprobante && (
                                            <a
                                                className="pp-btn-pdf"
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
        <>
            <Encabezado usuario={usuario} />

            <Metricas metricas={DATOS.metricas} />

            {(permisos.productos || muestraAtencion) && (
                <section className="panels-grid">
                    {permisos.productos && (
                        <GraficoProductos datos={DATOS.grafico} url={urls.productos} />
                    )}

                    {muestraAtencion && (
                        <PanelAtencion
                            stockBajo={DATOS.stock_bajo}
                            porVencer={DATOS.por_vencer}
                            permisos={permisos}
                            urls={urls}
                        />
                    )}
                </section>
            )}

            {permisos.movimientos && (
                <TablaMovimientos movimientos={DATOS.movimientos} url={urls.movimientos} />
            )}
        </>
    );
}


ReactDOM.createRoot(document.getElementById('panel-raiz')).render(<Panel />);