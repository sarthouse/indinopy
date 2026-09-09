from django.contrib import admin
from .models import Moneda

@admin.register(Moneda)
class MonedaAdmin(admin.ModelAdmin):
    list_display = ["codigo", "nombre", "simbolo", "activa"]
    list_filter = ["activa"]
    search_fields = ["codigo", "nombre"]



