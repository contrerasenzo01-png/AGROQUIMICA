/* ============================================================
   MI PERFIL · Agroquímica del Valle
   Componente React con clases de Bootstrap 5.3.
   Los datos los arma perfil.py (mi_perfil) y llegan en el
   <script id="datos-perfil"> del template.

   - La foto se previsualiza al instante (arrastrar o elegir).
   - Guardar se habilita solo cuando hay cambios.
   - Al guardar se actualiza el menú lateral sin recargar.
   ============================================================ */

const { useState, useMemo, useEffect, useRef } = React;

const DATOS = JSON.parse(
    document.getElementById('datos-perfil').textContent
);

const TIPOS_IMAGEN = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_BYTES = DATOS.limites.foto_mb * 1024 * 1024;
const REGEX_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;


/* ------------------------------------------------------------
   UTILIDADES
   ------------------------------------------------------------ */

function tokenCsrf() {
    const campo = document.querySelector('[name=csrfmiddlewaretoken]');
    return campo ? campo.value : '';
}

function limpiar(texto) {
    return texto.split(/\s+/).filter(Boolean).join(' ');
}

/* Actualiza la foto (o la inicial) y el correo del menú lateral,
   sin recargar la página. */
function actualizarMenuLateral(u) {
    const avatar = document.querySelector('.sidebar-user-avatar');

    if (avatar) {
        avatar.textContent = '';

        if (u.foto_url) {
            const img = document.createElement('img');
            img.src = u.foto_url;
            img.alt = '';
            avatar.appendChild(img);
            avatar.classList.add('con-foto');
        } else {
            avatar.textContent = (u.nombre || '?').charAt(0).toUpperCase();
            avatar.classList.remove('con-foto');
        }
    }

    const nombre = document.querySelector('.sidebar-user-name');
    if (nombre) nombre.textContent = u.nombre + ' ' + u.apellido;
}


/* ------------------------------------------------------------
   ÍCONOS
   ------------------------------------------------------------ */

const TRAZOS = {
    subir: ['M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4', 'm17 8-5-5-5 5', 'M12 3v12'],
    candado: ['M5 11h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z', 'M7 11V7a5 5 0 0 1 10 0v4'],
    escudo: ['M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z', 'm9 12 2 2 4-4'],
    check: ['M20 6 9 17l-5-5'],
    alerta: ['m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3', 'M12 9v4', 'M12 17h.01'],
    candadoCerrado: ['M12 15v2', 'M5 11h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z', 'M7 11V7a5 5 0 0 1 10 0v4'],
};

function Icono({ nombre }) {
    return (
        <svg className="pf-svg" viewBox="0 0 24 24" aria-hidden="true">
            {TRAZOS[nombre].map((d, i) => <path key={i} d={d} />)}
        </svg>
    );
}


/* ------------------------------------------------------------
   SELECTOR DE FOTO (arrastrar, elegir y vista previa)
   ------------------------------------------------------------ */

function SelectorFoto({ vista, inicial, error, onElegir, onQuitar }) {
    const entrada = useRef(null);
    const [arrastrando, setArrastrando] = useState(false);

    const abrir = () => entrada.current && entrada.current.click();

    const alSoltar = (e) => {
        e.preventDefault();
        setArrastrando(false);

        const archivo = e.dataTransfer.files[0];
        if (archivo) onElegir(archivo);
    };

    const alElegir = (e) => {
        const archivo = e.target.files[0];
        if (archivo) onElegir(archivo);
        e.target.value = '';   // permite elegir de nuevo la misma foto
    };

    return (
        <div className="text-center">
            <input
                ref={entrada}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                hidden
                onChange={alElegir}
            />

            <div
                role="button"
                tabIndex={0}
                aria-label={vista ? 'Cambiar la foto de perfil' : 'Elegir una foto de perfil'}
                className={'pf-foto' + (arrastrando ? ' arrastrando' : '') + (vista ? ' con-foto' : '')}
                onClick={abrir}
                onKeyDown={e => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        abrir();
                    }
                }}
                onDragEnter={e => { e.preventDefault(); setArrastrando(true); }}
                onDragOver={e => { e.preventDefault(); setArrastrando(true); }}
                onDragLeave={e => { e.preventDefault(); setArrastrando(false); }}
                onDrop={alSoltar}
            >
                {vista ? (
                    <img key={vista} src={vista} alt="Tu foto de perfil" className="pf-foto-img" />
                ) : (
                    <span className="pf-foto-inicial" aria-hidden="true">{inicial}</span>
                )}

                <span className="pf-foto-capa">
                    <Icono nombre="subir" />
                    <span>{arrastrando ? 'Soltá la foto acá' : (vista ? 'Cambiar foto' : 'Agregar foto')}</span>
                </span>
            </div>

            <p className="small text-body-secondary mt-3 mb-2">
                Arrastrá una foto o tocá el círculo.<br />
                JPG, PNG o WEBP · hasta {DATOS.limites.foto_mb} MB
            </p>

            {vista && (
                <button type="button" className="btn btn-sm btn-outline-danger" onClick={onQuitar}>
                    Quitar foto
                </button>
            )}

            {error && <div className="text-danger small fw-semibold mt-2" role="alert">{error}</div>}
        </div>
    );
}


/* ------------------------------------------------------------
   CAMPO DE FORMULARIO
   ------------------------------------------------------------ */

function Campo({ id, etiqueta, valor, onCambio, error, tipo = 'text', maximo, autocompletar }) {
    return (
        <div>
            <label className="form-label" htmlFor={id}>{etiqueta}</label>
            <input
                id={id}
                type={tipo}
                className={'form-control' + (error ? ' is-invalid' : '')}
                value={valor}
                maxLength={maximo}
                autoComplete={autocompletar}
                onChange={e => onCambio(e.target.value)}
                aria-invalid={error ? 'true' : 'false'}
            />
            {error && <div className="invalid-feedback">{error}</div>}
        </div>
    );
}

function DatoFijo({ etiqueta, children }) {
    return (
        <div className="pf-dato">
            <span>{etiqueta}</span>
            <strong>{children}</strong>
        </div>
    );
}


/* ------------------------------------------------------------
   PERMISOS (solo lectura)
   ------------------------------------------------------------ */

function Permisos({ permisos, urlDetalle }) {
    return (
        <div className="card pf-aparecer" style={{ '--pf-i': 4 }}>
            <div className="card-header bg-transparent d-flex flex-wrap justify-content-between align-items-center gap-2 py-3">
                <div className="d-flex align-items-center gap-2">
                    <span className="pf-icono-titulo"><Icono nombre="escudo" /></span>
                    <h2 className="mb-0">Mis permisos</h2>
                </div>
                <a className="link-success fw-semibold small text-decoration-none" href={urlDetalle}>
                    Ver detalle →
                </a>
            </div>

            <div className="card-body">
                <p className="small text-body-secondary mb-3">
                    {permisos.es_admin
                        ? 'Tu perfil tiene acceso a todas las funciones del sistema.'
                        : `Tu perfil tiene ${permisos.total} de ${permisos.total_catalogo} permisos. Los define un administrador.`}
                </p>

                {permisos.modulos.length === 0 ? (
                    <div className="alert alert-light small text-center py-2 mb-0">
                        Tu perfil todavía no tiene permisos asignados.
                    </div>
                ) : (
                    <div className="pf-modulos">
                        {permisos.modulos.map(m => (
                            <details key={m.nombre} className="pf-modulo">
                                <summary>
                                    <span className="fw-semibold">{m.nombre}</span>
                                    <span className="badge rounded-pill bg-success-subtle text-success-emphasis border border-success-subtle">
                                        {m.permisos.length}
                                    </span>
                                </summary>

                                <ul className="pf-permisos">
                                    {m.permisos.map(p => (
                                        <li key={p.nombre} title={p.descripcion}>{p.nombre}</li>
                                    ))}
                                </ul>
                            </details>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}


/* ------------------------------------------------------------
   PANTALLA COMPLETA
   ------------------------------------------------------------ */

function Perfil() {
    const [actual, setActual] = useState(DATOS.usuario);   // lo que está guardado
    const [form, setForm] = useState({
        nombre: DATOS.usuario.nombre,
        apellido: DATOS.usuario.apellido,
        email: DATOS.usuario.email,
    });
    const [foto, setFoto] = useState(null);                // { archivo, url } elegida y sin guardar
    const [quitar, setQuitar] = useState(false);           // quitar la foto guardada
    const [errores, setErrores] = useState({});
    const [guardando, setGuardando] = useState(false);
    const [aviso, setAviso] = useState(null);              // { tipo, texto }

    /* La URL temporal de la vista previa se libera al cambiar de foto. */
    useEffect(() => () => {
        if (foto) URL.revokeObjectURL(foto.url);
    }, [foto]);

    /* El aviso de "guardado" se cierra solo. */
    useEffect(() => {
        if (!aviso || aviso.tipo !== 'success') return undefined;

        const espera = setTimeout(() => setAviso(null), 4500);
        return () => clearTimeout(espera);
    }, [aviso]);

    const vista = foto ? foto.url : (quitar ? '' : actual.foto_url);

    const hayCambios = useMemo(() => (
        limpiar(form.nombre) !== actual.nombre ||
        limpiar(form.apellido) !== actual.apellido ||
        form.email.trim() !== actual.email ||
        foto !== null ||
        quitar
    ), [form, actual, foto, quitar]);

    const cambiar = (campo) => (valor) => {
        setForm(f => ({ ...f, [campo]: valor }));
        setErrores(e => ({ ...e, [campo]: undefined }));
    };

    const elegirFoto = (archivo) => {
        if (!TIPOS_IMAGEN.includes(archivo.type)) {
            setErrores(e => ({ ...e, foto: 'La foto debe ser JPG, PNG o WEBP.' }));
            return;
        }
        if (archivo.size > MAX_BYTES) {
            setErrores(e => ({ ...e, foto: `La foto no puede superar los ${DATOS.limites.foto_mb} MB.` }));
            return;
        }

        setErrores(e => ({ ...e, foto: undefined }));
        setFoto({ archivo, url: URL.createObjectURL(archivo) });
        setQuitar(false);
    };

    const quitarFoto = () => {
        setFoto(null);
        setQuitar(Boolean(actual.foto_url));
        setErrores(e => ({ ...e, foto: undefined }));
    };

    const descartar = () => {
        setForm({ nombre: actual.nombre, apellido: actual.apellido, email: actual.email });
        setFoto(null);
        setQuitar(false);
        setErrores({});
    };

    /* Validación rápida en el navegador (el servidor vuelve a validar). */
    const validar = () => {
        const nuevos = {};
        const V = window.Validar;

        if (!limpiar(form.nombre)) nuevos.nombre = 'Ingresá tu nombre.';
        else if (V && V.persona(form.nombre)) nuevos.nombre = V.persona(form.nombre);

        if (!limpiar(form.apellido)) nuevos.apellido = 'Ingresá tu apellido.';
        else if (V && V.persona(form.apellido)) nuevos.apellido = V.persona(form.apellido);

        if (!form.email.trim()) nuevos.email = 'Ingresá tu correo electrónico.';
        else if (V && V.email(form.email)) nuevos.email = V.email(form.email);
        else if (!REGEX_EMAIL.test(form.email.trim())) nuevos.email = 'Ingresá un correo electrónico válido.';

        return nuevos;
    };

    const guardar = async (evento) => {
        evento.preventDefault();
        if (!hayCambios || guardando) return;

        const nuevos = validar();
        setErrores(nuevos);

        if (Object.values(nuevos).some(Boolean)) return;

        const datos = new FormData();
        datos.append('Nombre_usuario', limpiar(form.nombre));
        datos.append('Apellido_usuario', limpiar(form.apellido));
        datos.append('Email_usuario', form.email.trim());

        if (foto) datos.append('Foto', foto.archivo);
        if (quitar) datos.append('quitar_foto', '1');

        setGuardando(true);
        setAviso(null);

        try {
            const respuesta = await fetch(DATOS.urls.guardar, {
                method: 'POST',
                body: datos,
                credentials: 'same-origin',
                headers: {
                    'X-CSRFToken': tokenCsrf(),
                    'X-Requested-With': 'XMLHttpRequest',
                },
            });

            let resultado = null;
            try { resultado = await respuesta.json(); } catch (e) { resultado = null; }

            if (!respuesta.ok || !resultado || !resultado.ok) {
                setErrores((resultado && resultado.errores) || {});
                setAviso({
                    tipo: 'danger',
                    texto: (resultado && resultado.error) || 'No se pudo guardar. Probá de nuevo en un momento.',
                });
                return;
            }

            const guardado = resultado.usuario;

            setActual(guardado);
            setForm({ nombre: guardado.nombre, apellido: guardado.apellido, email: guardado.email });
            setFoto(null);
            setQuitar(false);
            setErrores({});
            setAviso({ tipo: resultado.sin_cambios ? 'info' : 'success', texto: resultado.mensaje });

            actualizarMenuLateral(guardado);
        } catch (e) {
            setAviso({ tipo: 'danger', texto: 'No hay conexión con el servidor. Revisá tu internet y probá de nuevo.' });
        } finally {
            setGuardando(false);
        }
    };

    const inicial = (form.nombre.trim().charAt(0) || actual.nombre.charAt(0) || '?').toUpperCase();

    return (
        <div className="container-fluid px-0">

            <header className="mb-4 pf-aparecer">
                <h1 className="mb-1">Mi perfil</h1>
                <p className="text-body-secondary small mb-0">
                    Actualizá tu foto y tus datos personales.
                </p>
            </header>

            {aviso && (
                <div className={`alert alert-${aviso.tipo} d-flex align-items-center justify-content-between gap-3 pf-aparecer`} role="status">
                    <span>{aviso.texto}</span>
                    <button type="button" className="btn-close" aria-label="Cerrar" onClick={() => setAviso(null)}></button>
                </div>
            )}

            <form onSubmit={guardar} noValidate>
                <div className="row g-4">

                    {/* ---------- FOTO Y RESUMEN ---------- */}
                    <div className="col-12 col-lg-4 pf-aparecer" style={{ '--pf-i': 1 }}>
                        <div className="card h-100">
                            <div className="card-body d-flex flex-column align-items-center text-center py-4">

                                <SelectorFoto
                                    vista={vista}
                                    inicial={inicial}
                                    error={errores.foto}
                                    onElegir={elegirFoto}
                                    onQuitar={quitarFoto}
                                />

                                <hr className="w-100 my-4" />

                                <h2 className="mb-1">{actual.nombre} {actual.apellido}</h2>
                                <p className="text-body-secondary small mb-2">{actual.email}</p>
                                <span className="badge rounded-pill bg-success-subtle text-success-emphasis border border-success-subtle">
                                    {actual.perfil}
                                </span>
                            </div>
                        </div>
                    </div>

                    {/* ---------- DATOS ---------- */}
                    <div className="col-12 col-lg-8 d-flex flex-column gap-4">

                        <div className="card pf-aparecer" style={{ '--pf-i': 2 }}>
                            <div className="card-header bg-transparent py-3">
                                <h2 className="mb-0">Datos personales</h2>
                            </div>

                            <div className="card-body">
                                <div className="row g-3">
                                    <div className="col-12 col-md-6">
                                        <Campo
                                            id="pf-nombre" etiqueta="Nombre"
                                            valor={form.nombre} onCambio={cambiar('nombre')}
                                            error={errores.nombre} maximo={DATOS.limites.nombre}
                                            autocompletar="given-name"
                                        />
                                    </div>

                                    <div className="col-12 col-md-6">
                                        <Campo
                                            id="pf-apellido" etiqueta="Apellido"
                                            valor={form.apellido} onCambio={cambiar('apellido')}
                                            error={errores.apellido} maximo={DATOS.limites.nombre}
                                            autocompletar="family-name"
                                        />
                                    </div>

                                    <div className="col-12">
                                        <Campo
                                            id="pf-email" etiqueta="Correo electrónico" tipo="email"
                                            valor={form.email} onCambio={cambiar('email')}
                                            error={errores.email} maximo={DATOS.limites.email}
                                            autocompletar="email"
                                        />
                                        <div className="form-text">
                                            A este correo te llegan las alertas y el enlace para recuperar tu contraseña.
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div className="card-footer bg-transparent d-flex flex-wrap justify-content-end align-items-center gap-2 py-3">
                                {hayCambios && !guardando && (
                                    <span className="small text-body-secondary me-auto pf-pendiente">
                                        Tenés cambios sin guardar
                                    </span>
                                )}

                                <button
                                    type="button"
                                    className="btn btn-outline-success"
                                    onClick={descartar}
                                    disabled={!hayCambios || guardando}
                                >
                                    Descartar
                                </button>

                                <button type="submit" className="btn btn-success" disabled={!hayCambios || guardando}>
                                    {guardando ? (
                                        <>
                                            <span className="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>
                                            Guardando…
                                        </>
                                    ) : (
                                        <>
                                            <Icono nombre="check" /> Guardar cambios
                                        </>
                                    )}
                                </button>
                            </div>
                        </div>

                        {/* ---------- DATOS QUE NO SE EDITAN ---------- */}
                        <div className="card pf-aparecer" style={{ '--pf-i': 3 }}>
                            <div className="card-header bg-transparent d-flex align-items-center gap-2 py-3">
                                <span className="pf-icono-titulo"><Icono nombre="candadoCerrado" /></span>
                                <div>
                                    <h2 className="mb-0">Datos de tu cuenta</h2>
                                    <div className="small text-body-secondary">
                                        Los administra un administrador del sistema.
                                    </div>
                                </div>
                            </div>

                            <div className="card-body">
                                <div className="pf-datos">
                                    <DatoFijo etiqueta="DNI">{actual.dni}</DatoFijo>
                                    <DatoFijo etiqueta="Nombre de usuario">{actual.usuario}</DatoFijo>
                                    <DatoFijo etiqueta="Perfil">{actual.perfil}</DatoFijo>
                                    <DatoFijo etiqueta="Estado">
                                        <span className="badge rounded-pill bg-success-subtle text-success-emphasis border border-success-subtle">
                                            {actual.estado}
                                        </span>
                                    </DatoFijo>
                                </div>

                                <hr />

                                <div className="d-flex flex-wrap justify-content-between align-items-center gap-3">
                                    <div>
                                        <div className="fw-semibold">Contraseña</div>
                                        <div className="small text-body-secondary">
                                            Cambiala cada tanto para mantener tu cuenta segura.
                                        </div>
                                    </div>

                                    <a className="btn btn-outline-success" href={DATOS.urls.contrasena}>
                                        <Icono nombre="candado" /> Cambiar contraseña
                                    </a>
                                </div>
                            </div>
                        </div>

                    </div>
                </div>
            </form>

            <div className="mt-4">
                <Permisos permisos={DATOS.permisos} urlDetalle={DATOS.urls.mis_permisos} />
            </div>

        </div>
    );
}


ReactDOM.createRoot(document.getElementById('perfil-raiz')).render(<Perfil />);