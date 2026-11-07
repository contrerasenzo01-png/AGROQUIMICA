/* ============================================================
   PANTALLAS DE ACCESO · Agroquímica del Valle
   (login, recuperar contraseña, nueva contraseña, cambiar contraseña)

   - Valida cada campo por separado y muestra el error en rojo
     debajo del campo (<div id="{id}Error">).
   - Botón para mostrar u ocultar la contraseña.
   - Aviso de Bloq Mayús.
   - Lista de requisitos de la nueva contraseña que se pone en verde.
   - Evita el doble envío y muestra "cargando" en el botón.

   Las reglas son las mismas que valida el servidor
   (validaciones.py y validar_contrasena en views.py).
   ============================================================ */

window.Acceso = (function () {

    'use strict';

    // ---------------------------------------------------------
    // REGLAS (devuelven el mensaje de error o '' si está bien)
    // ---------------------------------------------------------

    const reglas = {

        usuario: function (v) {
            if (!v) return 'Ingrese su usuario.';
            if (/\s/.test(v)) return 'El usuario no puede tener espacios.';
            if (/\d/.test(v)) return 'El usuario no puede contener números.';
            if (!/^[A-Za-z]+$/.test(v)) return 'El usuario solo puede tener letras, sin tildes, ñ ni símbolos.';
            if (v.length < 3) return 'El usuario debe tener al menos 3 letras.';
            if (v.length > 50) return 'El usuario no puede superar los 50 caracteres.';
            return '';
        },

        // Contraseña al INGRESAR: solo formato, no se revelan las reglas.
        claveLogin: function (v) {
            if (!v) return 'Ingrese su contraseña.';
            if (/\s/.test(v)) return 'La contraseña no puede tener espacios.';
            if (v.length < 8) return 'La contraseña debe tener al menos 8 caracteres.';
            if (v.length > 64) return 'La contraseña no puede superar los 64 caracteres.';
            return '';
        },

        email: function (v) {
            v = v.trim();
            if (!v) return 'Ingrese su correo electrónico.';
            if (/\s/.test(v)) return 'El correo no puede tener espacios.';
            if (v.length > 100) return 'El correo no puede superar los 100 caracteres.';
            if ((v.match(/@/g) || []).length !== 1) return 'El correo debe tener un solo @. Ejemplo: nombre@empresa.com';
            if (v.indexOf('..') !== -1) return 'El correo no puede tener dos puntos seguidos.';
            if (!/^[A-Za-z0-9](?:[A-Za-z0-9._%+-]*[A-Za-z0-9])?@(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}$/.test(v)) {
                return 'Ingrese un correo válido. Ejemplo: nombre@empresa.com';
            }
            return '';
        },

        // Contraseña NUEVA: mismas reglas y textos que
        // validar_contrasena (views.py). Los espacios y el nombre de
        // usuario tienen su propio aviso; el resto de los requisitos
        // (los de la lista) da un mensaje general.
        claveNueva: function (usuario) {
            return function (v) {
                if (!v) return 'Ingrese la nueva contraseña.';
                if (/\s/.test(v)) return 'No se pueden usar espacios.';
                if (usuario && v.toLowerCase().indexOf(usuario.toLowerCase()) !== -1) {
                    return 'No se puede usar el nombre de usuario.';
                }
                if (v.length < 8 || v.length > 64 || !/[A-Z]/.test(v) || !/[a-z]/.test(v) || !/\d/.test(v)) {
                    return 'La contraseña no cumplió con los requerimientos solicitados.';
                }
                return '';
            };
        },

        // Confirmación: tiene que coincidir con el campo indicado.
        coincide: function (idOriginal) {
            return function (v) {
                const original = document.getElementById(idOriginal);
                if (!v) return 'Repita la nueva contraseña.';
                if (original && v !== original.value) return 'Las contraseñas no coinciden.';
                return '';
            };
        },
    };


    // ---------------------------------------------------------
    // MOSTRAR / OCULTAR EL ERROR DE UN CAMPO
    // ---------------------------------------------------------

    function pintar(campo, animar) {
        const mensaje = campo.regla(campo.input.value);

        campo.error.textContent = mensaje;
        campo.input.classList.toggle('is-invalid', !!mensaje);
        campo.input.classList.toggle('is-valid', !mensaje);

        if (mensaje) {
            campo.input.setAttribute('aria-invalid', 'true');

            if (animar) {
                const caja = campo.input.closest('.input-icon') || campo.input;
                caja.classList.remove('shake');
                void caja.offsetWidth;          // reinicia la animación
                caja.classList.add('shake');
            }
        } else {
            campo.input.removeAttribute('aria-invalid');
        }

        return !mensaje;
    }


    // ---------------------------------------------------------
    // FORMULARIO
    // definiciones: { idDelInput: funcionRegla, ... }
    // ---------------------------------------------------------

    function formulario(form, definiciones) {

        if (!form) return;

        const campos = Object.keys(definiciones).map(function (id) {
            const input = document.getElementById(id);
            return {
                input: input,
                error: document.getElementById(id + 'Error'),
                regla: definiciones[id],
                // Si el servidor ya lo marcó, se valida mientras se escribe.
                tocado: input.classList.contains('is-invalid'),
            };
        }).filter(function (c) { return c.input && c.error; });

        campos.forEach(function (campo) {

            // Primera validación: al salir del campo (si escribió algo).
            campo.input.addEventListener('blur', function () {
                if (campo.input.value.length > 0 || campo.tocado) {
                    campo.tocado = true;
                    pintar(campo, false);
                }
            });

            // Después, con cada tecla. También se revisan los demás
            // campos ya tocados (por ejemplo "Repetir contraseña").
            campo.input.addEventListener('input', function () {
                campos.forEach(function (otro) {
                    if (otro.tocado) pintar(otro, false);
                });
            });
        });

        const boton = form.querySelector('[type="submit"]');

        form.addEventListener('submit', function (e) {
            let primero = null;

            campos.forEach(function (campo) {
                campo.tocado = true;
                if (!pintar(campo, true) && !primero) primero = campo.input;
            });

            if (primero) {
                e.preventDefault();
                primero.focus();
                return;
            }

            if (boton) {
                boton.disabled = true;
                boton.classList.add('cargando');
            }
        });

        // Al volver con "atrás", el botón tiene que estar activo.
        window.addEventListener('pageshow', function () {
            if (boton) {
                boton.disabled = false;
                boton.classList.remove('cargando');
            }
        });

        // Foco inicial: el primer campo con error o el primero vacío.
        const conError = form.querySelector('.is-invalid');
        const vacio = campos.find(function (c) { return !c.input.value; });

        if (conError) conError.focus();
        else if (vacio) vacio.input.focus();
    }


    // ---------------------------------------------------------
    // MOSTRAR / OCULTAR CONTRASEÑA (botones .toggle-password)
    // ---------------------------------------------------------

    function iniciarOjos() {
        document.querySelectorAll('.toggle-password[data-target]').forEach(function (btn) {
            const input = document.getElementById(btn.dataset.target);
            if (!input) return;

            btn.addEventListener('click', function () {
                const mostrar = input.type === 'password';
                input.type = mostrar ? 'text' : 'password';
                btn.classList.toggle('visible', mostrar);
                btn.setAttribute('aria-pressed', mostrar ? 'true' : 'false');
                btn.setAttribute('aria-label', mostrar ? 'Ocultar contraseña' : 'Mostrar contraseña');
                input.focus();
            });
        });
    }


    // ---------------------------------------------------------
    // AVISO DE BLOQ MAYÚS (div id="{idDelInput}Caps")
    // ---------------------------------------------------------

    function iniciarBloqMayus() {
        document.querySelectorAll('input[type="password"]').forEach(function (input) {
            const aviso = document.getElementById(input.id + 'Caps');
            if (!aviso) return;

            function revisar(e) {
                if (typeof e.getModifierState === 'function') {
                    aviso.hidden = !e.getModifierState('CapsLock');
                }
            }

            input.addEventListener('keydown', revisar);
            input.addEventListener('keyup', revisar);
            input.addEventListener('blur', function () { aviso.hidden = true; });
        });
    }


    // ---------------------------------------------------------
    // REQUISITOS DE LA NUEVA CONTRASEÑA (ul.reglas-clave)
    // ---------------------------------------------------------

    function iniciarRequisitos() {
        document.querySelectorAll('.reglas-clave[data-for]').forEach(function (lista) {
            const input = document.getElementById(lista.dataset.for);
            if (!input) return;

            const pruebas = {
                largo: function (v) { return v.length >= 8 && v.length <= 64; },
                mayus: function (v) { return /[A-Z]/.test(v); },
                minus: function (v) { return /[a-z]/.test(v); },
                numero: function (v) { return /\d/.test(v); },
            };

            function actualizar() {
                const v = input.value;
                lista.querySelectorAll('li[data-regla]').forEach(function (li) {
                    const prueba = pruebas[li.dataset.regla];
                    li.classList.toggle('ok', !!(prueba && prueba(v)));
                });
            }

            input.addEventListener('input', actualizar);
            actualizar();
        });
    }


    document.addEventListener('DOMContentLoaded', function () {
        iniciarOjos();
        iniciarBloqMayus();
        iniciarRequisitos();
    });

    return { reglas: reglas, formulario: formulario };

})();
