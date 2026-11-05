import re

from django import forms
from .models import Proveedores


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
                attrs={
                    'class': 'form-input',
                    'placeholder': 'Ej. 3874567890',
                    'inputmode': 'tel',
                    'oninput': "this.value = this.value.replace(/[^0-9+()\\s-]/g, '')",
                }
            ),

            'email_proveedor': forms.EmailInput(
                attrs={
                    'class': 'form-input',
                    'placeholder': 'Ej. contacto@empresa.com',
                }
            ),

            'direccion_proveedor': forms.TextInput(
                attrs={
                    'class': 'form-input',
                    'placeholder': 'Ingrese la dirección',
                }
            ),

            'estado_proveedor': forms.HiddenInput(),
        }

    # =====================================================
    # CONSULTAR DUPLICADOS
    # =====================================================

    def _consulta_duplicados(self, campo, valor):
        consulta = Proveedores.objects.filter(**{
            f'{campo}__iexact': valor
        })

        if self.instance.pk:
            consulta = consulta.exclude(
                pk=self.instance.pk
            )

        return consulta.exists()

    # =====================================================
    # VALIDAR NOMBRE
    # =====================================================

    def clean_nombre_proveedor(self):
        nombre = (
            self.cleaned_data.get('nombre_proveedor') or ''
        ).strip()

        if not nombre:
            raise forms.ValidationError(
                'El nombre del proveedor es obligatorio.'
            )

        if len(nombre) < 2:
            raise forms.ValidationError(
                'El nombre debe tener al menos 2 caracteres.'
            )

        if not any(caracter.isalpha() for caracter in nombre):
            raise forms.ValidationError(
                'El nombre del proveedor no puede contener solamente números.'
            )

        if self._consulta_duplicados(
            'nombre_proveedor', nombre
        ):
            raise forms.ValidationError(
                'Ya existe un proveedor registrado con este nombre.'
            )

        return nombre

    # =====================================================
    # VALIDAR TELÉFONO
    # =====================================================

    def clean_telefono_proveedor(self):
        telefono = (
            self.cleaned_data.get('telefono_proveedor') or ''
        ).strip()

        if not telefono:
            return None

        if not re.fullmatch(r'\+?[0-9\s()-]+', telefono):
            raise forms.ValidationError(
                'Ingrese un teléfono válido. No se permiten letras.'
            )

        cantidad_digitos = sum(
            caracter.isdigit() for caracter in telefono
        )

        if cantidad_digitos < 7:
            raise forms.ValidationError(
                'El teléfono debe tener al menos 7 números.'
            )

        if self._consulta_duplicados(
            'telefono_proveedor', telefono
        ):
            raise forms.ValidationError(
                'Ya existe un proveedor registrado con este teléfono.'
            )

        return telefono

    # =====================================================
    # VALIDAR CORREO ELECTRÓNICO
    # =====================================================

    def clean_email_proveedor(self):
        email = (
            self.cleaned_data.get('email_proveedor') or ''
        ).strip().lower()

        if not email:
            return None

        if self._consulta_duplicados(
            'email_proveedor', email
        ):
            raise forms.ValidationError(
                'Ya existe un proveedor registrado con este correo electrónico.'
            )

        return email

    # =====================================================
    # VALIDAR DIRECCIÓN
    # =====================================================

    def clean_direccion_proveedor(self):
        direccion = (
            self.cleaned_data.get('direccion_proveedor') or ''
        ).strip()

        return direccion or None
