from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.contrib import messages
from .models import Proveedores, ProductosXProveedores, Productos 
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
    
    productos_list = Productos.objects.select_related('ID_Tipo_producto').all()

    # --- NUEVA LÓGICA: Verificar si hubo un error de duplicado al crear/editar ---
    error_duplicado_id = request.session.pop('error_duplicado_id', None)
    proveedor_conflicto = None
    if error_duplicado_id:
        proveedor_conflicto = Proveedores.objects.filter(pk=error_duplicado_id).first()

    return render(request, 'inventario/proveedores.html', {
        'proveedores': proveedores_list,
        'activos_count': activos_count,
        'total_count': total_count,
        'form': form,
        'productos_list': productos_list, 
        'busqueda': busqueda,
        'proveedor_conflicto': proveedor_conflicto # <-- Se envía a la plantilla
    })

def crear_proveedor(request):
    if request.method == 'POST':
        form = ProveedorForm(request.POST)
        
        nombre = request.POST.get('nombre_proveedor', '').strip()
        email = request.POST.get('email_proveedor', '').strip()

        # Buscar si algún proveedor ya tiene ese nombre o email
        query = Q()
        if nombre: query |= Q(nombre_proveedor__iexact=nombre)
        if email: query |= Q(email_proveedor__iexact=email)
        
        conflicto = Proveedores.objects.filter(query).first() if (nombre or email) else None

        if conflicto:
            # Si existe un conflicto, guardamos su ID en la sesión y redirigimos
            request.session['error_duplicado_id'] = conflicto.pk
            return redirect('gestion_proveedores')

        if form.is_valid():
            proveedor = form.save()
            productos_seleccionados = form.cleaned_data.get('productos')
            if productos_seleccionados:
                for prod in productos_seleccionados:
                    ProductosXProveedores.objects.create(ID_Producto=prod, ID_Proveedor=proveedor)
            
            messages.success(request, 'Proveedor registrado con éxito.')
            return redirect('gestion_proveedores')
            
    return redirect('gestion_proveedores')

def editar_proveedor(request, pk):
    proveedor = get_object_or_404(Proveedores, pk=pk)
    
    if request.method == 'POST':
        nombre = request.POST.get('nombre_proveedor', '').strip()
        email = request.POST.get('email_proveedor', '').strip()

        # Buscar si OTRO proveedor distinto ya tiene ese nombre o email
        query = Q()
        if nombre: query |= Q(nombre_proveedor__iexact=nombre)
        if email: query |= Q(email_proveedor__iexact=email)
        
        conflicto = Proveedores.objects.filter(query).exclude(pk=pk).first() if (nombre or email) else None

        if conflicto:
            # Si existe un conflicto con otro proveedor, guardamos su ID y redirigimos
            request.session['error_duplicado_id'] = conflicto.pk
            return redirect('gestion_proveedores')

        proveedor.nombre_proveedor = nombre
        proveedor.telefono_proveedor = request.POST.get('telefono_proveedor')
        proveedor.email_proveedor = email
        proveedor.direccion_proveedor = request.POST.get('direccion_proveedor')
        
        estado_val = request.POST.get('estado_proveedor')
        proveedor.estado_proveedor = True if estado_val in ['True', 'true', '1', True] else False
        
        proveedor.save(update_fields=['nombre_proveedor', 'telefono_proveedor', 'email_proveedor', 'direccion_proveedor', 'estado_proveedor'])
        messages.success(request, 'Proveedor actualizado correctamente.')

    return redirect('gestion_proveedores')

def cambiar_estado_proveedor(request, pk):
    if request.method == 'POST':
        proveedor = get_object_or_404(Proveedores, pk=pk)
        
        # Alternar estado del proveedor
        proveedor.estado_proveedor = not proveedor.estado_proveedor
        proveedor.save(update_fields=['estado_proveedor'])
        
        if proveedor.estado_proveedor:
            messages.success(request, f'El proveedor {proveedor.nombre_proveedor} ha sido activado.')
        else:
            messages.warning(request, f'El proveedor {proveedor.nombre_proveedor} ha sido dado de baja.')

    return redirect('gestion_proveedores')