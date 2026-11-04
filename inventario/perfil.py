"""
MI PERFIL · Agroquímica del Valle

Pantalla para que cada usuario (con cualquier perfil) edite sus propios
datos: nombre, apellido, correo y foto.

Solo lectura: DNI, nombre de usuario, perfil, estado y permisos.

La pantalla la dibuja React (static/inventario/react/perfil.jsx) y guarda
con fetch contra guardar_mi_perfil, que responde JSON.

Cada cambio queda en la Auditoría como MODIFICACION de "Usuarios".
"""

import uuid
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.validators import validate_email
from django.db import DatabaseError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from PIL import Image, ImageOps, UnidentifiedImageError

from .auditoria import registrar_auditoria, snapshot
from .models import Usuarios
from .permissions import PERFILES_ADMIN, catalogo_plano, permisos_asignados
from .views import IMAGEN_MAX_MB, IMAGEN_TIPOS, usuario_autenticado


# ============================================================
# FOTO DE PERFIL
# Cuadrada de 480 px y en WEBP: pesa poco y entra perfecta en
# los círculos del menú lateral y de la lista de usuarios.
# ============================================================

FOTO_LADO = 480


def _procesar_foto(archivo):
    """Devuelve (ContentFile, None) si la foto es válida, o (None, error)."""

    if archivo.size > IMAGEN_MAX_MB * 1024 * 1024:
        return None, f'La foto no puede superar los {IMAGEN_MAX_MB} MB.'

    if (archivo.content_type or '').lower() not in IMAGEN_TIPOS:
        return None, 'La foto debe ser JPG, PNG o WEBP.'

    try:
        # verify() detecta archivos dañados o que no son imágenes.
        Image.open(archivo).verify()
        archivo.seek(0)

        imagen = ImageOps.exif_transpose(Image.open(archivo))

        if imagen.mode not in ('RGB', 'RGBA'):
            imagen = imagen.convert(
                'RGBA' if 'A' in imagen.getbands() else 'RGB'
            )

        # Recorte cuadrado centrado (un poco hacia arriba, donde suele
        # estar la cara) y reducción al tamaño final.
        imagen = ImageOps.fit(
            imagen,
            (FOTO_LADO, FOTO_LADO),
            method=Image.LANCZOS,
            centering=(0.5, 0.4),
        )

        buffer = BytesIO()
        imagen.save(buffer, format='WEBP', quality=85)

    except (UnidentifiedImageError, OSError, ValueError):
        return None, 'El archivo elegido no es una imagen válida.'

    return ContentFile(buffer.getvalue(), name=f'{uuid.uuid4().hex}.webp'), None


# ============================================================
# DATOS PARA LA PANTALLA
# ============================================================

def _datos_usuario(usuario):
    """Lo que React muestra y lo que se devuelve al guardar."""

    return {
        'nombre': usuario.Nombre_usuario,
        'apellido': usuario.Apellido_usuario,
        'email': usuario.Email_usuario,
        'dni': usuario.DNI,
        'usuario': usuario.Usuario,
        'perfil': usuario.ID_Perfil.Nombre_perfil,
        'estado': 'Activo' if usuario.Estado_usuario else 'Inactivo',
        'foto_url': usuario.Foto_usuario.url if usuario.Foto_usuario else '',
        # Misma inicial que muestra el menú lateral cuando no hay foto.
        'inicial': (usuario.Email_usuario[:1] or '?').upper(),
    }


def _permisos_del_usuario(usuario):
    """Permisos agrupados por módulo (los mismos de "Mis permisos")."""

    es_admin = usuario.ID_Perfil.Nombre_perfil in PERFILES_ADMIN
    asignados = permisos_asignados(usuario)

    grupos = {}

    for nombre, descripcion, grupo in catalogo_plano():
        if es_admin or nombre.strip().lower() in asignados:
            grupos.setdefault(grupo, []).append({
                'nombre': nombre,
                'descripcion': descripcion,
            })

    modulos = [{'nombre': g, 'permisos': p} for g, p in grupos.items()]

    return {
        'es_admin': es_admin,
        'total': sum(len(m['permisos']) for m in modulos),
        'total_catalogo': len(catalogo_plano()),
        'modulos': modulos,
    }


def mi_perfil(request):
    """Pantalla "Mi perfil". La puede abrir cualquier usuario con sesión."""

    usuario = usuario_autenticado(request)

    if not usuario:
        return redirect('login')

    datos = {
        'usuario': _datos_usuario(usuario),
        'permisos': _permisos_del_usuario(usuario),
        'urls': {
            'guardar': reverse('guardar_mi_perfil'),
            'contrasena': reverse('cambiar_contrasena'),
            'mis_permisos': reverse('mis_permisos'),
            'panel': reverse('panel_principal'),
        },
        'limites': {'nombre': 50, 'email': 100, 'foto_mb': IMAGEN_MAX_MB},
    }

    return render(
        request,
        'inventario/perfil.html',
        {
            'usuario': usuario,
            'activo': 'mi_perfil',
            'datos_perfil': datos,
        }
    )


# ============================================================
# GUARDAR
# ============================================================

def _limpiar(texto):
    """Sin espacios de más: '  Ana   María ' -> 'Ana María'."""
    return ' '.join((texto or '').split())


def _snapshot_perfil(usuario):
    """Datos del usuario para la auditoría.

    La foto se guarda como texto ('Con foto' / 'Sin foto'): no tiene
    sentido guardar el nombre del archivo en el registro de cambios.
    """

    datos = snapshot(usuario)
    datos['Foto_usuario'] = 'Con foto' if usuario.Foto_usuario else 'Sin foto'
    return datos


def _error_json(texto, status=400, errores=None):
    cuerpo = {'ok': False, 'error': texto}

    if errores:
        cuerpo['errores'] = errores

    return JsonResponse(cuerpo, status=status)


@require_POST
def guardar_mi_perfil(request):
    """Guarda nombre, apellido, correo y foto del usuario con sesión.

    Solo se toman esos cuatro datos del formulario: DNI, usuario, perfil
    y estado no se pueden cambiar desde acá aunque alguien los envíe.
    """

    usuario = usuario_autenticado(request)

    if not usuario:
        return _error_json('Tu sesión venció. Volvé a ingresar.', status=401)

    nombre = _limpiar(request.POST.get('Nombre_usuario'))
    apellido = _limpiar(request.POST.get('Apellido_usuario'))
    email = (request.POST.get('Email_usuario') or '').strip()
    quitar_foto = request.POST.get('quitar_foto') == '1'
    archivo = request.FILES.get('Foto')

    # ---------------- VALIDACIONES ----------------
    errores = {}

    if not nombre:
        errores['nombre'] = 'Ingresá tu nombre.'
    elif len(nombre) > 50:
        errores['nombre'] = 'El nombre no puede superar los 50 caracteres.'

    if not apellido:
        errores['apellido'] = 'Ingresá tu apellido.'
    elif len(apellido) > 50:
        errores['apellido'] = 'El apellido no puede superar los 50 caracteres.'

    if not email:
        errores['email'] = 'Ingresá tu correo electrónico.'
    elif len(email) > 100:
        errores['email'] = 'El correo no puede superar los 100 caracteres.'
    else:
        try:
            validate_email(email)
        except ValidationError:
            errores['email'] = 'Ingresá un correo electrónico válido.'
        else:
            if Usuarios.objects.filter(
                Email_usuario__iexact=email
            ).exclude(pk=usuario.pk).exists():
                errores['email'] = 'Ya existe otro usuario con ese correo.'

    foto_nueva = None

    if archivo:
        foto_nueva, error_foto = _procesar_foto(archivo)

        if error_foto:
            errores['foto'] = error_foto

    if errores:
        return _error_json('Revisá los datos marcados.', errores=errores)

    # ---------------- GUARDAR ----------------
    try:
        with transaction.atomic():

            antes = _snapshot_perfil(usuario)
            foto_vieja = usuario.Foto_usuario.name

            usuario.Nombre_usuario = nombre
            usuario.Apellido_usuario = apellido
            usuario.Email_usuario = email

            foto_cambio = None

            if foto_nueva:
                usuario.Foto_usuario.save(
                    foto_nueva.name, foto_nueva, save=False
                )
                foto_cambio = 'Foto actualizada'

            elif quitar_foto and foto_vieja:
                usuario.Foto_usuario = None
                foto_cambio = 'Sin foto'

            despues = _snapshot_perfil(usuario)

            if foto_cambio:
                despues['Foto_usuario'] = foto_cambio

            if antes == despues:
                return JsonResponse({
                    'ok': True,
                    'sin_cambios': True,
                    'mensaje': 'No hay cambios para guardar.',
                    'usuario': _datos_usuario(usuario),
                })

            usuario.save()

            if foto_cambio and foto_vieja:
                # El archivo viejo se borra recién cuando se confirma.
                transaction.on_commit(
                    lambda: default_storage.delete(foto_vieja)
                )

            registrar_auditoria(
                usuario, 'Usuarios', usuario, 'MODIFICACION', antes, despues
            )

    except DatabaseError:
        return _error_json(
            'Ocurrió un error en la base de datos. No se guardaron los cambios.',
            status=500
        )

    return JsonResponse({
        'ok': True,
        'mensaje': 'Tu perfil se actualizó correctamente.',
        'usuario': _datos_usuario(usuario),
    })