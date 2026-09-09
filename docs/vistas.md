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
- Las columnas de costo unitario y total de insumos requeridos.
- Las tarifas estimadas y liquidadas de las etapas de talleristas.

## 3. Interfaces de Trabajo Diario y Componentes Reutilizables
- **Control de Estados (`DocumentoBase`)**: Badges de estado dinámicos (`borrador` gris, `confirmado` azul, `finalizado` verde, `cancelado`/`anulado` rojo).
- **Gestor de Archivos Adjuntos**: Componente reutilizable en plantillas para listar y subir archivos vinculados a cualquier documento (`{% for adjunto in documento.adjuntos.all %}`).
- **Curva de Talles y Variantes**: Tablas interactivas que agrupan los productos por template y desglosan cantidades por talle y color.
- **Frontend interno**: Framework CSS responsivo integrado en `base.html` con formularios validados por **Django Forms**.
