"""
Indicadores de resumen de cada pantalla (las tarjetas de arriba,
con el mismo diseño que las de Productos).

Cada vista arma su lista con `indicador(...)` y la manda al template
como 'resumen'; el template la dibuja con:

    {% include 'inventario/_resumen.html' %}

Colores disponibles: verde, azul, ambar, rojo.
"""

from django.utils.safestring import mark_safe


# Trazos de los íconos (viewBox 0 0 24 24, sin relleno).
ICONOS = {
    'caja': (
        '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8'
        'a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/>'
        '<path d="m3.3 7 8.7 5 8.7-5M12 22V12"/>'
    ),
    'camion': (
        '<path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/>'
        '<path d="M15 18H9"/>'
        '<path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.62l-3.48-4.35'
        'A1 1 0 0 0 17.52 8H14"/>'
        '<circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/>'
    ),
    'check': '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    'pausa': '<circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/>',
    'documento': (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 2v6h6M8 13h8M8 17h8"/>'
    ),
    'etiqueta': (
        '<path d="M12.59 2.59A2 2 0 0 0 11.17 2H4a2 2 0 0 0-2 2v7.17a2 2 0 0 0 .59 1.41'
        'l8.7 8.71a2.43 2.43 0 0 0 3.42 0l6.58-6.58a2.43 2.43 0 0 0 0-3.42z"/>'
        '<circle cx="7.5" cy="7.5" r="1.5"/>'
    ),
    'capas': (
        '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91'
        'a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/>'
        '<path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/>'
        '<path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>'
    ),
    'usuarios': (
        '<path d="M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="10" cy="7" r="4"/>'
        '<path d="M20 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>'
    ),
    'llave': (
        '<circle cx="7.5" cy="15.5" r="5.5"/>'
        '<path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3"/>'
    ),
    'escudo': (
        '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6'
        'a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5'
        'a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>'
    ),
    'cuadricula': (
        '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>'
        '<rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>'
    ),
    'reloj': '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    'calendario': (
        '<rect x="3" y="4" width="18" height="18" rx="2"/>'
        '<path d="M16 2v4M8 2v4M3 10h18"/>'
    ),
    'alerta': (
        '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/>'
        '<path d="M12 9v4M12 17h.01"/>'
    ),
    'bajada': '<path d="M22 17 13.5 8.5 8.5 13.5 2 7"/><path d="M16 17h6v-6"/>',
    'entrada': '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
    'salida': '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    'deshacer': '<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-15-6.7L3 13"/>',
    'actividad': '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    'candado': (
        '<rect x="3" y="11" width="18" height="11" rx="2"/>'
        '<path d="M7 11V7a5 5 0 0 1 10 0v4"/>'
    ),
}


def indicador(valor, etiqueta, color='verde', icono='caja'):
    return {
        'valor': valor,
        'etiqueta': etiqueta,
        'color': color,
        'icono': mark_safe(ICONOS.get(icono, ICONOS['caja'])),
    }
