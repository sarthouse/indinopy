# Gestión de Permisos y Roles (Django Auth)

Django trae incluido un sistema de autenticación y autorización sumamente robusto (el framework `django.contrib.auth`). Para un sistema ERP como Indino, donde un "Vendedor" no debe ver los costos de la "Fábrica" y un "Tallerista" solo debe ver lo suyo, este sistema es perfecto.

## 1. Conceptos Básicos: Usuarios, Grupos y Permisos

Django maneja la seguridad mediante tres pilares:
1. **Users (Usuarios)**: Las personas que se loguean (ej. Juan el tallerista, María de tesorería).
2. **Permissions (Permisos)**: Acciones atómicas que se pueden realizar. Por defecto, cada vez que creas un Modelo (ej. `OrdenProduccion`), Django crea automáticamente 4 permisos: `add`, `change`, `delete`, `view`.
3. **Groups (Grupos o Roles)**: Colecciones de permisos. A un Usuario se le asigna un Grupo, y hereda todos sus permisos.

### Estructura de Roles sugerida para Indino (Grupos)
- **Dueño / Gerente**: Permisos totales (Superusuario).
- **Ventas**: Permisos para `view` y `add` Pedidos, `view` Clientes. No puede borrar.
- **Tallerista**: Permisos mínimos. Solo puede acceder a un panel especial para avanzar etapas de sus OPs asignadas.
- **Administración / Tesorería**: Permisos sobre Facturas, Pagos y Liquidaciones.

## 2. Permisos Personalizados (Custom Permissions)

A veces los 4 permisos por defecto no alcanzan. Recordando el caso de la Orden de Producción (OP), donde no queríamos que los talleristas vieran los costos, podemos crear un permiso específico dentro del archivo `models.py`.

```python
# apps/produccion/models.py
from django.db import models

class OrdenProduccion(models.Model):
    # ... tus campos ...

    class Meta:
        permissions = [
            ("view_costos_op", "Puede ver los costos e insumos valorizados de la OP"),
            ("aprobar_op", "Puede pasar una OP de Pendiente a En Proceso"),
        ]
```

## 3. Aplicando Permisos en el Código

Una vez creados, los permisos se deben chequear en dos lugares principales: en las Vistas (Backend) y en los Templates (Frontend).

### A. Protegiendo las Vistas (Backend)
Si usamos Vistas Basadas en Clases (CBV), usamos el `PermissionRequiredMixin`. Si un usuario sin el permiso intenta entrar a la URL, Django le mostrará un error 403 (Acceso Denegado).

```python
# apps/produccion/views.py
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.views.generic import DetailView
from .models import OrdenProduccion

class OrdenProduccionDetailView(PermissionRequiredMixin, DetailView):
    model = OrdenProduccion
    template_name = 'produccion/orden_produccion.html'
    
    # El usuario DEBE tener este permiso para que la vista cargue siquiera
    permission_required = 'produccion.view_ordenproduccion'
```

### B. Protegiendo elementos de la Interfaz (Templates)
A veces queremos que el usuario sí entre a la página (ej. el Tallerista viendo la OP), pero queremos **ocultar** ciertos botones o columnas de costos. Django inyecta automáticamente una variable `perms` en todos los templates.

```html
<!-- templates/produccion/orden_produccion.html -->

<h1>Orden de Producción N° {{ op.numero_op }}</h1>

<!-- Si el usuario pertenece al grupo Administración, verá los costos -->
{% if perms.produccion.view_costos_op %}
    <div class="costos-secretos">
        Costo Total del Material: ${{ op.total_costo_insumos }}
    </div>
{% endif %}

<!-- Restricción de botones de acción -->
{% if perms.produccion.aprobar_op %}
    <button class="btn btn-success">Aprobar OP para Fabricación</button>
{% else %}
    <p class="text-muted">No tienes permisos para aprobar esta orden.</p>
{% endif %}
```

## 4. El Panel de Administración de Django
La gran ventaja es que no tienes que programar la interfaz para asignar estos roles. Django provee un Panel de Administración (`/admin/`) "gratis". Desde allí, el gerente de Indino puede:
1. Crear el grupo "Talleristas Externos".
2. Buscar en una lista de *checkboxes* los permisos, y tildar solo "Ver OP" (dejando destildado "Ver Costos OP").
3. Crear un usuario para "Juan", asignarle el grupo "Talleristas Externos" y guardarlo.

