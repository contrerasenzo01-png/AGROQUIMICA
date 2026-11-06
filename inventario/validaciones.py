"""
Validaciones de datos del sistema.

Todas las funciones devuelven una tupla (valor_limpio, error):
  - si el dato es válido, error es None;
  - si no, error es un texto listo para mostrar al usuario.

Si "etiqueta" va vacía, el mensaje no lleva prefijo (se usa en los
formularios de Django, donde el error ya aparece debajo del campo).
El navegador aplica las mismas reglas (static/inventario/js/validaciones.js).
"""

import re
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

SIMBOLOS_NOMBRE = " .,-/&()%+'°"
SIMBOLOS_TEXTO = " .,;:-/&()%+'\"°#¿?¡!@_"
SIMBOLOS_PERSONA = " '-."
SIMBOLOS_CODIGO = "-./_"

EMAIL_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._%+-]*[A-Za-z0-9])?@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}$"
)


# ------------------------------------------------------------
# UTILIDADES
# ------------------------------------------------------------

def _m(etiqueta, texto):
    """'Etiqueta: texto' o, sin etiqueta, el texto con mayúscula inicial."""
    if etiqueta:
        return f'{etiqueta}: {texto}'
    return texto[:1].upper() + texto[1:]


def _fmt(numero):
    """1234567.5 -> '1.234.567,50' (formato argentino)."""
    texto = f'{numero:,.2f}'.replace(',', '#').replace('.', ',').replace('#', '.')
    return texto[:-3] if texto.endswith(',00') else texto


def limpiar_espacios(texto):
    """Quita espacios de más (principio, final y repetidos)."""
    return ' '.join(str(texto if texto is not None else '').split())


def _es_simbolo(c):
    return not c.isalnum() and not c.isspace()


def _corrida(valor, condicion):
    """Largo de la repetición más larga de un mismo carácter."""
    mejor = actual = 0
    previo = None

    for c in valor:
        if condicion(c):
            actual = actual + 1 if c == previo else 1
        else:
            actual = 0
        previo = c
        mejor = max(mejor, actual)

    return mejor


def _vacio(valor, etiqueta, obligatorio, vacio_devuelto):
    if obligatorio:
        return vacio_devuelto, _m(etiqueta, 'es obligatorio.')
    return vacio_devuelto, None


# ------------------------------------------------------------
# TEXTOS
# ------------------------------------------------------------

def validar_nombre(texto, etiqueta='', minimo=2, maximo=50, obligatorio=True):
    """Nombres de producto, tipo, subtipo, perfil, proveedor."""

    valor = limpiar_espacios(texto)

    if not valor:
        return _vacio(valor, etiqueta, obligatorio, '')

    if len(valor) < minimo:
        return valor, _m(etiqueta, f'debe tener al menos {minimo} caracteres.')

    if len(valor) > maximo:
        return valor, _m(etiqueta, f'no puede superar los {maximo} caracteres.')

    for c in valor:
        if not (c.isalnum() or c in SIMBOLOS_NOMBRE):
            return valor, _m(
                etiqueta,
                f'no se permite el carácter «{c}». '
                "Usá letras, números y . , - / & ( ) % + '"
            )

    if not valor[0].isalnum():
        return valor, _m(etiqueta, 'tiene que empezar con una letra o un número.')

    if not any(c.isalpha() for c in valor):
        return valor, _m(etiqueta, 'tiene que incluir al menos una letra.')

    if any(_es_simbolo(a) and _es_simbolo(b) for a, b in zip(valor, valor[1:])):
        return valor, _m(etiqueta, 'no puede tener símbolos seguidos.')

    if _corrida(valor, str.isalpha) >= 4:
        return valor, _m(etiqueta, 'tiene letras repetidas. Revisalo.')

    if not (valor[-1].isalnum() or valor[-1] in ').%'):
        return valor, _m(etiqueta, 'no puede terminar con ese símbolo.')

    return valor, None


def validar_persona(texto, etiqueta='', minimo=2, maximo=50, obligatorio=True):
    """Nombre o apellido de una persona."""

    valor = limpiar_espacios(texto)

    if not valor:
        return _vacio(valor, etiqueta, obligatorio, '')

    if len(valor) < minimo:
        return valor, _m(etiqueta, f'debe tener al menos {minimo} caracteres.')

    if len(valor) > maximo:
        return valor, _m(etiqueta, f'no puede superar los {maximo} caracteres.')

    for c in valor:
        if c.isdigit():
            return valor, _m(etiqueta, 'no puede contener números.')
        if not (c.isalpha() or c in SIMBOLOS_PERSONA):
            return valor, _m(etiqueta, f'no se permite el carácter «{c}».')

    if not valor[0].isalpha():
        return valor, _m(etiqueta, 'tiene que empezar con una letra.')

    if sum(c.isalpha() for c in valor) < 2:
        return valor, _m(etiqueta, 'tiene que tener al menos 2 letras.')

    if any(_es_simbolo(a) and _es_simbolo(b) for a, b in zip(valor, valor[1:])):
        return valor, _m(etiqueta, 'no puede tener símbolos seguidos.')

    if _corrida(valor, str.isalpha) >= 4:
        return valor, _m(etiqueta, 'tiene letras repetidas. Revisalo.')

    if not (valor[-1].isalpha() or valor[-1] == '.'):
        return valor, _m(etiqueta, 'no puede terminar con ese símbolo.')

    return valor, None


def validar_texto(texto, etiqueta='', minimo=0, maximo=200, obligatorio=False):
    """Descripciones, direcciones, observaciones y justificaciones."""

    valor = limpiar_espacios(texto)

    if not valor:
        return _vacio(valor, etiqueta, obligatorio, '')

    if len(valor) < minimo:
        return valor, _m(etiqueta, f'debe tener al menos {minimo} caracteres.')

    if len(valor) > maximo:
        return valor, _m(etiqueta, f'no puede superar los {maximo} caracteres.')

    for c in valor:
        if not (c.isalnum() or c in SIMBOLOS_TEXTO):
            return valor, _m(etiqueta, f'no se permite el carácter «{c}».')

    if sum(c.isalnum() for c in valor) < 2:
        return valor, _m(etiqueta, 'tiene que incluir letras o números.')

    if _corrida(valor, _es_simbolo) >= 3:
        return valor, _m(etiqueta, 'repite demasiadas veces el mismo símbolo.')

    if _corrida(valor, str.isalpha) >= 5:
        return valor, _m(etiqueta, 'tiene letras repetidas. Revisalo.')

    return valor, None


def validar_codigo(texto, etiqueta='', minimo=1, maximo=50, obligatorio=True):
    """Número de remito o de lote."""

    valor = str(texto if texto is not None else '').strip()

    if not valor:
        return _vacio(valor, etiqueta, obligatorio, '')

    if len(valor) < minimo:
        return valor, _m(etiqueta, f'debe tener al menos {minimo} caracteres.')

    if len(valor) > maximo:
        return valor, _m(etiqueta, f'no puede superar los {maximo} caracteres.')

    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9\-./_]*', valor):
        return valor, _m(
            etiqueta,
            'solo puede tener letras, números y - . / _ (sin espacios), '
            'y tiene que empezar con una letra o un número.'
        )

    if any(a in SIMBOLOS_CODIGO and b in SIMBOLOS_CODIGO
           for a, b in zip(valor, valor[1:])):
        return valor, _m(etiqueta, 'no puede tener símbolos seguidos.')

    if valor[-1] in SIMBOLOS_CODIGO:
        return valor, _m(etiqueta, 'no puede terminar con un símbolo.')

    return valor, None


# ------------------------------------------------------------
# NÚMEROS
# ------------------------------------------------------------

def validar_entero(texto, etiqueta='', minimo=0, maximo=999999, obligatorio=True):
    """Devuelve (int o None, error)."""

    valor = str(texto if texto is not None else '').strip()

    if not valor:
        return _vacio(valor, etiqueta, obligatorio, None)

    if not re.fullmatch(r'\d{1,12}', valor):
        return None, _m(
            etiqueta, 'tiene que ser un número entero, sin signos, puntos ni comas.'
        )

    numero = int(valor)

    if numero < minimo:
        if minimo == 1:
            return None, _m(etiqueta, 'tiene que ser mayor a cero.')
        return None, _m(etiqueta, f'no puede ser menor a {_fmt(minimo)}.')

    if numero > maximo:
        return None, _m(etiqueta, f'no puede superar {_fmt(maximo)}.')

    return numero, None


def validar_decimal(texto, etiqueta='', minimo=Decimal('0.01'),
                    maximo=Decimal('99999999.99'), decimales=2, obligatorio=True):
    """Devuelve (Decimal o None, error)."""

    valor = str(texto if texto is not None else '').strip().replace(',', '.')

    if not valor:
        return _vacio(valor, etiqueta, obligatorio, None)

    if not re.fullmatch(r'\d{1,12}(\.\d+)?', valor):
        return None, _m(etiqueta, 'tiene que ser un número válido.')

    if len(valor.partition('.')[2]) > decimales:
        return None, _m(etiqueta, f'puede tener como máximo {decimales} decimales.')

    numero = Decimal(valor)

    if numero < minimo:
        if Decimal('0') < minimo <= Decimal('0.01'):
            return None, _m(etiqueta, 'tiene que ser mayor a cero.')
        return None, _m(etiqueta, f'no puede ser menor a {_fmt(minimo)}.')

    if numero > maximo:
        return None, _m(etiqueta, f'no puede superar {_fmt(maximo)}.')

    return numero, None


def validar_dni(texto, etiqueta='DNI', obligatorio=True):
    valor = str(texto if texto is not None else '').strip()

    if not valor:
        return _vacio(valor, etiqueta, obligatorio, None)

    if not valor.isdigit():
        return None, _m(etiqueta, 'tiene que tener solo números, sin puntos ni espacios.')

    if len(valor) not in (7, 8):
        return None, _m(etiqueta, 'tiene que tener 7 u 8 dígitos.')

    if int(valor) < 1_000_000:
        return None, _m(etiqueta, 'no es válido.')

    return int(valor), None


def validar_telefono(texto, etiqueta='Teléfono', obligatorio=False):
    valor = limpiar_espacios(texto)

    if not valor:
        return _vacio(valor, etiqueta, obligatorio, '')

    if len(valor) > 25:
        return valor, _m(etiqueta, 'no puede superar los 25 caracteres.')

    if not re.fullmatch(r'\+?[\d\s()\-]+', valor):
        return valor, _m(
            etiqueta, 'solo puede tener números, espacios y los símbolos + - ( ).'
        )

    if valor.count('(') != valor.count(')'):
        return valor, _m(etiqueta, 'tiene paréntesis sin cerrar.')

    digitos = re.sub(r'\D', '', valor)

    if len(digitos) < 6:
        return valor, _m(etiqueta, 'tiene que tener al menos 6 dígitos.')

    if len(digitos) > 15:
        return valor, _m(etiqueta, 'no puede tener más de 15 dígitos.')

    if re.search(r'(\d)\1{7,}', digitos):
        return valor, _m(etiqueta, 'no parece un teléfono válido.')

    return valor, None


def validar_email(texto, etiqueta='Correo electrónico', obligatorio=True, maximo=100):
    valor = str(texto if texto is not None else '').strip().lower()

    if not valor:
        return _vacio(valor, etiqueta, obligatorio, '')

    if re.search(r'\s', valor):
        return valor, _m(etiqueta, 'no puede tener espacios.')

    if len(valor) > maximo:
        return valor, _m(etiqueta, f'no puede superar los {maximo} caracteres.')

    error = _m(etiqueta, 'tiene que ser válido. Ejemplo: nombre@empresa.com')

    if valor.count('@') != 1 or '..' in valor:
        return valor, error

    local = valor.partition('@')[0]

    if not local or len(local) > 64 or not EMAIL_RE.match(valor):
        return valor, error

    try:
        validate_email(valor)
    except ValidationError:
        return valor, error

    return valor, None


# ------------------------------------------------------------
# FECHAS
# ------------------------------------------------------------

def validar_fecha(texto, etiqueta='', desde=None, hasta=None, obligatorio=True,
                  msg_desde=None, msg_hasta=None):
    """Devuelve (date o None, error). desde/hasta son fechas límite."""

    valor = str(texto if texto is not None else '').strip()

    if not valor:
        return _vacio(valor, etiqueta, obligatorio, None)

    try:
        fecha = date.fromisoformat(valor)
    except ValueError:
        return None, _m(etiqueta, 'no es una fecha válida.')

    if desde is not None and fecha < desde:
        return None, msg_desde or _m(
            etiqueta, f'no puede ser anterior al {desde:%d/%m/%Y}.'
        )

    if hasta is not None and fecha > hasta:
        return None, msg_hasta or _m(
            etiqueta, f'no puede ser posterior al {hasta:%d/%m/%Y}.'
        )

    return fecha, None

# ------------------------------------------------------------
# LOGIN
# Solo se revisa el FORMATO de lo que se escribe. Las reglas de
# seguridad (mayúscula, número, etc.) se aplican al crear o cambiar
# la contraseña (validar_contrasena en views.py), no al ingresar.
# El navegador aplica las mismas reglas (script de login.html).
# ------------------------------------------------------------

def validar_usuario_login(texto):
    """Usuario del login: solo letras a-z, sin espacios. Devuelve (valor, error)."""

    valor = str(texto if texto is not None else '')

    if not valor:
        return '', 'Ingresá tu usuario.'

    if re.search(r'\s', valor):
        return valor, 'El usuario no puede tener espacios.'

    if re.search(r'\d', valor):
        return valor, 'El usuario no puede contener números.'

    if not re.fullmatch(r'[A-Za-z]+', valor):
        return valor, 'El usuario solo puede tener letras, sin tildes, ñ ni símbolos.'

    if len(valor) < 3:
        return valor, 'El usuario debe tener al menos 3 letras.'

    if len(valor) > 50:
        return valor, 'El usuario no puede superar los 50 caracteres.'

    return valor, None


def validar_contrasena_login(texto):
    """Contraseña del login: obligatoria, sin espacios, entre 8 y 64 caracteres."""

    valor = str(texto if texto is not None else '')

    if not valor:
        return '', 'Ingresá tu contraseña.'

    if re.search(r'\s', valor):
        return valor, 'La contraseña no puede tener espacios.'

    if len(valor) < 8:
        return valor, 'La contraseña debe tener al menos 8 caracteres.'

    if len(valor) > 64:
        return valor, 'La contraseña no puede superar los 64 caracteres.'

    return valor, None
