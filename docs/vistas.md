# Vistas y Presentación (Django SSR)

Al utilizar **Server Side Rendering (SSR)**, Django generará el HTML que se envía al navegador. Usaremos el sistema de plantillas integrado (Django Templates) o Jinja2.

## 1. Vistas Basadas en Clases (CBV)
Para el panel administrativo, utilizaremos CBV (`ListView`, `DetailView`, `CreateView`, `UpdateView`) que aceleran el desarrollo de los ABM (Altas, Bajas y Modificaciones).

## 2. Doble Vista de la Orden de Producción (ACL)
Tal como lo requiere el negocio, el documento principal (`orden_produccion.html`) tiene dos versiones. Esto se manejará en la Vista (`DetailView` de la OP):

```python
# produccion/views.py
class OrdenProduccionDetailView(DetailView):
    model = OrdenProduccion
    template_name = 'produccion/orden_produccion.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Lógica de Permisos: Si es Administrativo ve costos, si es Tallerista, no.
        if self.request.user.has_perm('produccion.view_costos_op'):
            context['mostrar_costos'] = True
        else:
            context['mostrar_costos'] = False
        return context
```

En el Template (`orden_produccion.html`), el condicional `{% if mostrar_costos %}` ocultará:
- El badge de "ORIGINAL".
- Las columnas de costo unitario y total.
- La liquidación de los talleristas.

## 3. Interfaces de Trabajo Diario
- **Frontend interno**: Utilizaremos un framework CSS (como Bootstrap 5 o Tailwind CSS) integrado en `base.html` para un desarrollo rápido y responsivo del ERP.
- Formularios manejados por **Django Forms**, aprovechando la validación del backend directamente en la interfaz.
