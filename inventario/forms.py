import re

from django import forms
from .models import Proveedores
from .validaciones import (
    validar_nombre, validar_texto, validar_telefono, validar_email,
)

class ProveedorForm(forms.ModelForm):

    class Meta:
        model = Proveedores

        fields = [
            'nombre_proveedor',
            'telefono_proveedor',
            'email_proveedor',
            'direccion_proveedor',
            'estado_proveedor',
        ]

        labels = {
            'nombre_proveedor': 'Nombre del proveedor',
            'telefono_proveedor': 'Teléfono',
            'email_proveedor': 'Correo electrónico',
            'direccion_proveedor': 'Dirección',
            'estado_proveedor': 'Estado',
        }

        widgets = {
            'nombre_proveedor': forms.TextInput(
                attrs={
                    'class': 'form-input',
                    'placeholder': 'Ej. Agroinsumos Cuyo S.A.',
                }
            ),
            'telefono_proveedor': forms.TextInput(
                attrs={'class': 'form-input'}
            ),
            'email_proveedor': forms.EmailInput(
                attrs={'class': 'form-input'}
            ),
            'direccion_proveedor': forms.TextInput(
                attrs={'class': 'form-input'}
            ),
            'estado_proveedor': forms.HiddenInput(),
        }

    def clean_nombre_proveedor(self):
        nombre, error = validar_nombre(
            self.cleaned_data.get('nombre_proveedor'), '', 2, 150
        )

        if error:
            raise forms.ValidationError(error)

        consulta = Proveedores.objects.filter(nombre_proveedor__iexact=nombre)

        # No considerar duplicado al propio proveedor que se edita.
        if self.instance.pk:
            consulta = consulta.exclude(pk=self.instance.pk)

        if consulta.exists():
            raise forms.ValidationError(
                'Ya existe un proveedor registrado con este nombre.'
            )

        return nombre

    def clean_telefono_proveedor(self):
        telefono, error = validar_telefono(
            self.cleaned_data.get('telefono_proveedor'), '', obligatorio=False
        )

        if error:
            raise forms.ValidationError(error)

        return telefono or None

    def clean_email_proveedor(self):
        email, error = validar_email(
            self.cleaned_data.get('email_proveedor'), '', obligatorio=False
        )

        if error:
            raise forms.ValidationError(error)

        return email or None

    def clean_direccion_proveedor(self):
        direccion, error = validar_texto(
            self.cleaned_data.get('direccion_proveedor'), '',
            minimo=5, maximo=255, obligatorio=False
        )

        if error:
            raise forms.ValidationError(error)

        return direccion or None
