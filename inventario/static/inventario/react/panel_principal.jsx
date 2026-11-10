/* ============================================================
   PANEL PRINCIPAL · Agroquímica del Valle
   Componente React con clases de Bootstrap 5.3 y gráficos
   de ApexCharts (se cargan desde _react.html).
   Los datos los arma views.py (_datos_panel) y llegan en el
   <script id="datos-panel"> del template.
   ============================================================ */

const { useState, useMemo, useEffect, useRef } = React;

const DATOS = JSON.parse(
    document.getElementById('datos-panel').textContent
);

/* Foto de la portada (la ruta la pone el template con {% static %}) */
const RAIZ = document.getElementById('panel-raiz');
const FOTO_PORTADA = {
    webp: RAIZ.dataset.fotoWebp || '',
    jpg: RAIZ.dataset.fotoJpg || '',
};


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

function sinMovimientoReducido() {
    return !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}


/* ------------------------------------------------------------
   TEMA (claro / oscuro)
   tema.js avisa con el evento "av:tema" cuando se cambia el modo.
   ------------------------------------------------------------ */

function useTemaOscuro() {
    const [oscuro, setOscuro] = useState(
        () => document.documentElement.classList.contains('modo-oscuro')
    );

    useEffect(() => {
        const alCambiar = () => {
            setOscuro(document.documentElement.classList.contains('modo-oscuro'));
        };

        window.addEventListener('av:tema', alCambiar);
        return () => window.removeEventListener('av:tema', alCambiar);
    }, []);

    return oscuro;
}

/* Colores de los gráficos según el tema (mismos tonos que panel_principal.css y tema.css) */
function coloresGrafico(oscuro) {
    return oscuro
        ? {
            texto: '#e3ece6',
            texto2: '#a4b6ab',
            borde: '#263830',
            fondoTarjeta: '#151f1a',
            peligro: '#f87171',
            minimo: '#324539',
            paleta: ['#2e9d66', '#f5c400', '#8bc34a', '#2dd4bf', '#7db8f5', '#fb923c', '#c4a7f5'],
        }
        : {
            texto: '#1c2a23',
            texto2: '#6b7c73',
            borde: '#e3eae6',
            fondoTarjeta: '#ffffff',
            peligro: '#dc3545',
            minimo: '#cfe3d7',
            paleta: ['#185a38', '#2e9d66', '#f5c400', '#8bc34a', '#0f766e', '#3b82f6', '#a855f7'],
        };
}


/* ------------------------------------------------------------
   ANIMACIÓN DE NÚMEROS (de 0 al valor final)
   ------------------------------------------------------------ */

function useContador(objetivo, duracion = 900) {
    const [valor, setValor] = useState(0);

    useEffect(() => {
        if (!sinMovimientoReducido()) {
            setValor(objetivo);
            return undefined;
        }

        let inicio = null;
        let cuadro;

        const paso = (marca) => {
            if (inicio === null) inicio = marca;

            const avance = Math.min((marca - inicio) / duracion, 1);
            const suave = 1 - Math.pow(1 - avance, 3);   // frena al final

            setValor(Math.round(objetivo * suave));

            if (avance < 1) cuadro = requestAnimationFrame(paso);
        };

        cuadro = requestAnimationFrame(paso);
        return () => cancelAnimationFrame(cuadro);
    }, [objetivo, duracion]);

    return valor;
}


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
   GRÁFICO GENÉRICO DE APEXCHARTS
   Crea el gráfico una vez y, cuando cambian las opciones (por
   ejemplo, al cambiar de tema), las actualiza sin repetir la
   animación de entrada.
   ------------------------------------------------------------ */

function ApexGrafico({ opciones }) {
    const contenedor = useRef(null);
    const grafico = useRef(null);
    const disponible = typeof ApexCharts !== 'undefined';

    useEffect(() => {
        if (!disponible || !contenedor.current) return undefined;

        grafico.current = new ApexCharts(contenedor.current, opciones);
        grafico.current.render();

        return () => {
            if (grafico.current) grafico.current.destroy();
            grafico.current = null;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        if (grafico.current) {
            grafico.current.updateOptions(opciones, false, false);
        }
    }, [opciones]);

    if (!disponible) {
        return <Vacio texto="No se pudo cargar la librería de gráficos." />;
    }

    return <div ref={contenedor} className="pp-grafico" />;
}

/* Animaciones comunes a todos los gráficos */
function animacionesGrafico(velocidad) {
    return {
        enabled: sinMovimientoReducido(),
        easing: 'easeinout',
        speed: velocidad,
        animateGradually: { enabled: true, delay: 120 },
        dynamicAnimation: { enabled: true, speed: 350 },
    };
}

const FUENTE_GRAFICO = 'Inter, sans-serif';


/* ------------------------------------------------------------
   OPCIONES: TORTA DE PRODUCTOS MÁS / MENOS VENDIDOS
   Cada pestaña tiene su propia paleta de colores vivos.
   ------------------------------------------------------------ */

const PALETAS_VENTAS = {
    mas: ['#6366f1', '#06b6d4', '#22c55e', '#f59e0b', '#ec4899'],
    menos: ['#f43f5e', '#8b5cf6', '#14b8a6', '#f97316', '#3b82f6'],
};

function opcionesTortaVentas(datos, oscuro, paleta) {
    const c = coloresGrafico(oscuro);

    return {
        chart: {
            type: 'pie',
            height: 320,
            background: 'transparent',
            fontFamily: FUENTE_GRAFICO,
            foreColor: c.texto2,
            toolbar: { show: false },
            animations: animacionesGrafico(900),
            dropShadow: { enabled: true, top: 2, left: 0, blur: 6, opacity: oscuro ? 0.35 : 0.12 },
        },
        series: datos.map(d => d.cantidad),
        labels: datos.map(d => d.nombre),
        colors: paleta,
        fill: {
            type: 'gradient',
            gradient: { shade: 'light', type: 'diagonal1', shadeIntensity: 0.25, opacityFrom: 1, opacityTo: 0.9 },
        },
        stroke: { width: 3, colors: [c.fondoTarjeta] },
        plotOptions: {
            pie: { expandOnClick: true, dataLabels: { offset: -12 } },
        },
        dataLabels: {
            enabled: true,
            style: { fontSize: '12px', fontWeight: 700, colors: ['#ffffff'] },
            dropShadow: { enabled: true, blur: 2, opacity: 0.4 },
            formatter: v => Math.round(v) + '%',
        },
        legend: {
            position: 'bottom',
            fontSize: '12px',
            fontWeight: 600,
            labels: { colors: c.texto },
            markers: { size: 7, offsetX: -3 },
            itemMargin: { horizontal: 8, vertical: 4 },
        },
        states: {
            hover: { filter: { type: 'lighten', value: 0.06 } },
        },
        tooltip: {
            theme: oscuro ? 'dark' : 'light',
            y: { formatter: v => formatearNumero(v) + (v === 1 ? ' unidad vendida' : ' unidades vendidas') },
        },
        responsive: [{
            breakpoint: 576,
            options: { chart: { height: 300 } },
        }],
    };
}


/* ------------------------------------------------------------
   OPCIONES: BARRAS DE STOCK BAJO (stock actual vs. mínimo)
   ------------------------------------------------------------ */

function opcionesStockBajo(items, oscuro, alHacerClic) {
    const c = coloresGrafico(oscuro);

    return {
        chart: {
            type: 'bar',
            height: 90 + items.length * 52,
            background: 'transparent',
            fontFamily: FUENTE_GRAFICO,
            foreColor: c.texto2,
            toolbar: { show: false },
            animations: animacionesGrafico(900),
            events: alHacerClic ? { dataPointSelection: alHacerClic } : {},
        },
        series: [
            { name: 'Stock actual', data: items.map(p => p.stock) },
            { name: 'Mínimo', data: items.map(p => p.minimo) },
        ],
        colors: [c.peligro, c.minimo],
        plotOptions: {
            bar: {
                horizontal: true,
                borderRadius: 4,
                barHeight: '66%',
            },
        },
        dataLabels: { enabled: false },
        stroke: { show: false },
        xaxis: {
            categories: items.map(p => p.producto),
            labels: { formatter: v => formatearNumero(v) },
            axisBorder: { show: false },
            axisTicks: { show: false },
        },
        yaxis: {
            labels: { maxWidth: 140, style: { fontWeight: 600 } },
        },
        grid: {
            borderColor: c.borde,
            strokeDashArray: 3,
            xaxis: { lines: { show: true } },
            yaxis: { lines: { show: false } },
        },
        legend: {
            position: 'top',
            horizontalAlign: 'left',
            fontSize: '12px',
            markers: { size: 6, offsetX: -2 },
        },
        states: {
            hover: { filter: { type: 'lighten', value: 0.08 } },
        },
        tooltip: {
            theme: oscuro ? 'dark' : 'light',
            shared: true,
            intersect: false,
            y: { formatter: v => formatearNumero(v) + ' un.' },
        },
    };
}


/* ------------------------------------------------------------
   ENCABEZADO CON PORTADA
   La foto de los productos ocupa la derecha y se funde con el
   fondo de la página con un degradé (máscara en el CSS), así
   queda bien tanto en modo claro como en modo oscuro.
   ------------------------------------------------------------ */

function Encabezado({ usuario, permisos, urls }) {
    const [fotoLista, setFotoLista] = useState(false);
    const hayFoto = Boolean(FOTO_PORTADA.webp || FOTO_PORTADA.jpg);

    return (
        <header className="pp-hero mb-4">

            {hayFoto && (
                <picture className={'pp-hero-foto' + (fotoLista ? ' lista' : '')} aria-hidden="true">
                    {FOTO_PORTADA.webp && <source srcSet={FOTO_PORTADA.webp} type="image/webp" />}
                    <img
                        src={FOTO_PORTADA.jpg || FOTO_PORTADA.webp}
                        alt=""
                        onLoad={() => setFotoLista(true)}
                    />
                </picture>
            )}

            {/* Brillos de color que se mueven lento detrás del texto */}
            <span className="pp-hero-brillo pp-hero-brillo-1" aria-hidden="true"></span>
            <span className="pp-hero-brillo pp-hero-brillo-2" aria-hidden="true"></span>

            <div className="pp-hero-texto">
                <h1 className="pp-hero-titulo pp-aparecer" style={{ '--pp-i': 1 }}>
                    {saludoSegunHora()}, <span>{usuario.nombre}</span>
                </h1>

                <p className="pp-hero-sub pp-aparecer" style={{ '--pp-i': 2 }}>
                    Este es el resumen de hoy en Agroquímica del Valle.
                    <span className={claseEtiqueta('success') + ' ms-2 align-middle'}>{usuario.perfil}</span>
                </p>

                {(permisos.productos || permisos.movimientos) && (
                    <div className="d-flex flex-wrap gap-2 pp-aparecer" style={{ '--pp-i': 3 }}>
                        {permisos.productos && (
                            <a className="btn btn-success btn-sm pp-hero-btn" href={urls.productos}>
                                <Icono nombre="productos" /> Ver productos
                            </a>
                        )}
                        {permisos.movimientos && (
                            <a className="btn btn-outline-success btn-sm pp-hero-btn" href={urls.movimientos}>
                                Movimientos de stock →
                            </a>
                        )}
                    </div>
                )}
            </div>
        </header>
    );
}


/* ------------------------------------------------------------
   TARJETAS DE MÉTRICAS (grilla de Bootstrap)
   ------------------------------------------------------------ */

function TarjetaMetrica({ metrica, indice }) {
    const color = COLOR_METRICA[metrica.color] || 'success';
    const Elemento = metrica.url ? 'a' : 'div';
    const valorAnimado = useContador(Number(metrica.valor) || 0);

    return (
        <div className="col-12 col-sm-6 col-xl pp-aparecer" style={{ '--pp-i': indice }}>
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
                            {formatearNumero(valorAnimado)}
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
            {metricas.map((m, i) => <TarjetaMetrica key={m.clave} metrica={m} indice={i} />)}
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
   GRÁFICO: TOP 5 PRODUCTOS MÁS / MENOS VENDIDOS (torta)
   Dos pestañas con el mismo estilo que "Requieren atención".
   ------------------------------------------------------------ */

function TortaVentas({ datos, paleta }) {
    const oscuro = useTemaOscuro();
    const opciones = useMemo(() => opcionesTortaVentas(datos, oscuro, paleta), [datos, oscuro, paleta]);

    return <ApexGrafico opciones={opciones} />;
}

function GraficoVentas({ datos, url }) {
    const [pestana, setPestana] = useState('mas');
    const lista = pestana === 'mas' ? datos.mas : datos.menos;
    const total = lista.reduce((suma, d) => suma + d.cantidad, 0);

    return (
        <div className="card h-100">
            <CabeceraTarjeta titulo="Productos por ventas">
                <EnlaceVerTodo url={url} texto="Ver productos" />
            </CabeceraTarjeta>

            <div className="card-body d-flex flex-column">
                <div className="btn-group btn-group-sm w-100 mb-3" role="tablist">
                    <BotonSegmento activo={pestana === 'mas'} onClick={() => setPestana('mas')}>
                        Top 5 más vendidos
                    </BotonSegmento>
                    <BotonSegmento activo={pestana === 'menos'} onClick={() => setPestana('menos')}>
                        Top 5 menos vendidos
                    </BotonSegmento>
                </div>

                <div className="flex-grow-1 d-flex flex-column justify-content-center">
                    {lista.length === 0 ? (
                        <Vacio texto="Todavía no hay ventas registradas." />
                    ) : (
                        <>
                            {/* key: al cambiar de pestaña se vuelve a crear el gráfico con su animación */}
                            <TortaVentas key={pestana} datos={lista} paleta={PALETAS_VENTAS[pestana]} />

                            <p className="small text-body-secondary text-center mt-2 mb-0">
                                {formatearNumero(total)} unidades vendidas entre estos {lista.length} productos
                                {pestana === 'menos' && datos.sin_ventas > 0 && (
                                    <> · {datos.sin_ventas} producto{datos.sin_ventas === 1 ? '' : 's'} activo{datos.sin_ventas === 1 ? '' : 's'} sin ventas</>
                                )}
                            </p>
                        </>
                    )}
                </div>
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
                    <StockBajo items={stockBajo} url={urls.productos} />
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

/* Stock bajo: gráfico de barras o lista, a elección */
function StockBajo({ items, url }) {
    const [vista, setVista] = useState('grafico');
    const oscuro = useTemaOscuro();

    const opciones = useMemo(
        () => opcionesStockBajo(items, oscuro, url ? () => { window.location.href = url; } : null),
        [items, oscuro, url]
    );

    if (!items.length) {
        return <Vacio ok texto="Ningún producto está por debajo de su stock mínimo." />;
    }

    return (
        <>
            <div className="btn-group btn-group-sm mb-2" role="group" aria-label="Forma de ver el stock bajo">
                <button
                    type="button"
                    className={'btn ' + (vista === 'grafico' ? 'btn-success' : 'btn-outline-success')}
                    onClick={() => setVista('grafico')}
                >
                    Gráfico
                </button>
                <button
                    type="button"
                    className={'btn ' + (vista === 'lista' ? 'btn-success' : 'btn-outline-success')}
                    onClick={() => setVista('lista')}
                >
                    Lista
                </button>
            </div>

            {vista === 'grafico'
                ? <ApexGrafico opciones={opciones} />
                : <ListaStockBajo items={items} url={url} />}
        </>
    );
}

function ListaStockBajo({ items, url }) {
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
        <section className="card pp-aparecer" style={{ '--pp-i': 6 }}>
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
                            {visibles.map((m, i) => (
                                <tr key={m.id} style={{ '--pp-i': Math.min(i, 10) }}>
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
            <Encabezado usuario={usuario} permisos={permisos} urls={urls} />

            <Metricas metricas={DATOS.metricas} />

            {(permisos.productos || muestraAtencion) && (
                <section className="row g-3 mb-4">
                    {permisos.productos && (
                        <div
                            className={'pp-aparecer col-12' + (muestraAtencion ? ' col-xl-6' : '')}
                            style={{ '--pp-i': 4 }}
                        >
                            <GraficoVentas datos={DATOS.grafico} url={urls.productos} />
                        </div>
                    )}

                    {muestraAtencion && (
                        <div
                            className={'pp-aparecer col-12' + (permisos.productos ? ' col-xl-6' : '')}
                            style={{ '--pp-i': 5 }}
                        >
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