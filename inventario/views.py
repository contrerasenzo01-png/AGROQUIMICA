from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from .models import Proveedores, ProductosXProveedores
from .forms import ProveedorForm

def gestion_proveedores(request):
    busqueda = request.GET.get('q', '')
    proveedores_list = Proveedores.objects.all()

    if busqueda:
        proveedores_list = proveedores_list.filter(
            Q(nombre_proveedor__icontains=busqueda) |
            Q(email_proveedor__icontains=busqueda) |
            Q(direccion_proveedor__icontains=busqueda)
        )

    activos_count = Proveedores.objects.filter(estado_proveedor=True).count()
    total_count = Proveedores.objects.count()
    form = ProveedorForm()

    return render(request, 'inventario/proveedores.html', {
        'proveedores': proveedores_list,
        'activos_count': activos_count,
        'total_count': total_count,
        'form': form,
        'busqueda': busqueda
    })

def crear_proveedor(request):
    if request.method == 'POST':
        form = ProveedorForm(request.POST)
        if form.is_valid():
            proveedor = form.save()
            productos_seleccionados = form.cleaned_data.get('productos')
            if productos_seleccionados:
                for prod in productos_seleccionados:
                    # Se usa ID_Proveedor e ID_Producto según tu modelo
                    ProductosXProveedores.objects.create(ID_Producto=prod, ID_Proveedor=proveedor)
    return redirect('gestion_proveedores')

def editar_proveedor(request, pk):
    proveedor = get_object_or_404(Proveedores, pk=pk)
    if request.method == 'POST':
        form = ProveedorForm(request.POST, instance=proveedor)
        if form.is_valid():
            form.save()
            # Se usa ID_Proveedor para buscar y eliminar las relaciones previas
            ProductosXProveedores.objects.filter(ID_Proveedor=proveedor).delete()
            productos_seleccionados = form.cleaned_data.get('productos')
            if productos_seleccionados:
                for prod in productos_seleccionados:
                    ProductosXProveedores.objects.create(ID_Producto=prod, ID_Proveedor=proveedor)
    return redirect('gestion_proveedores')

def cambiar_estado_proveedor(request, pk):
    if request.method == 'POST':
        proveedor = get_object_or_404(Proveedores, pk=pk)
        proveedor.estado_proveedor = not proveedor.estado_proveedor
        proveedor.save()
    return redirect('gestion_proveedores')