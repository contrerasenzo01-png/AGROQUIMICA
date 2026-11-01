from django import template

from ..permissions import menu_para, puede, puede_accion

register = template.Library()


@register.simple_tag
def menu_lateral(usuario):
    return menu_para(usuario)


@register.filter
def puede_ver(usuario, modulo):
    """{% if usuario|puede_ver:"productos" %}"""
    return puede(usuario, modulo)


@register.filter
def puede_gestionar(usuario, modulo):
    """{% if usuario|puede_gestionar:"productos" %}"""
    return puede(usuario, modulo, gestionar=True)


@register.filter
def puede_hacer(usuario, accion):
    """{% if usuario|puede_hacer:"anular_remitos" %}"""
    return puede_accion(usuario, accion)