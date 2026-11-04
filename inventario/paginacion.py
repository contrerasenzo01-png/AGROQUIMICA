"""
Paginación en el servidor · Agroquímica del Valle

Uso en una vista:

    from .paginacion import paginar

    pagina = paginar(request, consulta)
    return render(request, '...', {'registros': pagina, 'pagina': pagina})

Y en el template, debajo de la tabla:

    {% include 'inventario/_paginacion.html' %}

La búsqueda y los filtros se conservan al cambiar de página, porque
los enlaces se arman con {% querystring %} sobre la dirección actual.
La cantidad por página elegida queda guardada en la sesión, una por
pantalla.
"""

from django.core.paginator import Paginator

OPCIONES_POR_PAGINA = (10, 25, 50)


def paginar(request, consulta, por_defecto=10):
    """Devuelve la página pedida, con los datos que usa _paginacion.html."""

    coincidencia = getattr(request, 'resolver_match', None)
    nombre = coincidencia.url_name if coincidencia else request.path
    clave = f'paginacion:{nombre}'

    pedido = request.GET.get('por_pagina', '')

    if pedido.isdigit() and int(pedido) in OPCIONES_POR_PAGINA:
        por_pagina = int(pedido)
        request.session[clave] = por_pagina
    else:
        por_pagina = request.session.get(clave, por_defecto)

        if por_pagina not in OPCIONES_POR_PAGINA:
            por_pagina = por_defecto

    paginador = Paginator(consulta, por_pagina)
    pagina = paginador.get_page(request.GET.get('page'))

    # Números de página con "…": 1 … 4 5 6 … 20
    pagina.rango = list(
        paginador.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)
    )
    pagina.elipsis = paginador.ELLIPSIS
    pagina.por_pagina = por_pagina
    pagina.opciones = OPCIONES_POR_PAGINA

    return pagina