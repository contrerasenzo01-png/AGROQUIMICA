from django import forms
from .models import Proveedores, Productos

class ProveedorForm(forms.ModelForm):
    productos = forms.ModelMultipleChoiceField(
        queryset=Productos.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="PRODUCTOS SUMINISTRADOS — PRODUCTOS_X_PROVEEDORES"
    )

    class Meta:
        model = Proveedores
        fields = ['nombre_proveedor', 'telefono_proveedor', 'email_proveedor', 'direccion_proveedor', 'estado_proveedor']
        labels = {
            'nombre_proveedor': 'NOMBRE_PROVEEDOR',
            'telefono_proveedor': 'TELEFONO_PROVEEDOR',
            'email_proveedor': 'EMAIL_PROVEEDOR',
            'direccion_proveedor': 'DIRECCION_PROVEEDOR',
            'estado_proveedor': 'ESTADO_PROVEEDOR',
        }
        widgets = {
            'nombre_proveedor': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ej. Agroinsumos Cuyo S.A.'}),
            'telefono_proveedor': forms.TextInput(attrs={'class': 'form-input'}),
            'email_proveedor': forms.EmailInput(attrs={'class': 'form-input'}),
            'direccion_proveedor': forms.TextInput(attrs={'class': 'form-input'}),
            'estado_proveedor': forms.Select(attrs={'class': 'form-input'}),
        }

    def clean_nombre_proveedor(self):
        nombre = self.cleaned_data.get('nombre_proveedor')
        query = Proveedores.objects.filter(nombre_proveedor__iexact=nombre)
        if self.instance.pk:
            query = query.exclude(pk=self.instance.pk)
        if query.exists():
            raise forms.ValidationError("Ya existe un proveedor registrado con este nombre.")
        return nombre