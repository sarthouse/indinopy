import logging
import csv
import os
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from apps.base.models import ConfiguracionEmpresa, Moneda
from apps.inventario.models import UnidadMedida, Categoria, Ubicacion
from apps.contactos.models import Contacto, TipoDocumentoAFIP
from apps.contabilidad.models import Impuesto, TipoComprobanteAFIP, Diario

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Inicializa la base de datos con los datos maestros (Estilo Odoo)"

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING("Iniciando carga de datos maestros ERP...")
        )

        self.crear_tipos_documento()
        self.crear_monedas()
        self.crear_configuracion_empresa()
        self.crear_unidades_medida()
        self.crear_categorias_basicas()
        self.crear_ubicaciones_almacen()
        self.crear_contactos_sistema()
        self.crear_impuestos()
        self.cargar_tipos_comprobantes_afip()
        self.crear_diarios_contables()

        self.stdout.write(
            self.style.SUCCESS("¡Datos maestros inicializados correctamente!")
        )

    def crear_configuracion_empresa(self):
        conf, created = ConfiguracionEmpresa.objects.get_or_create(
            id=1,
            defaults={
                "razon_social": "Indinopy S.A. (Demo)",
                "cuit": "30000000000",
                "condicion_iva": "responsable_inscripto",
                "email": "admin@indinopy.com",
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("✔️ Configuración de Empresa creada."))
        else:
            self.stdout.write("Configuración de Empresa ya existía.")

    def crear_unidades_medida(self):
        unidades = [
            {"nombre": "Unidades", "abreviatura": "u", "tipo": "unidad"},
            {"nombre": "Kilos", "abreviatura": "kg", "tipo": "peso"},
            {"nombre": "Metros", "abreviatura": "m", "tipo": "longitud"},
            {"nombre": "Horas", "abreviatura": "hs", "tipo": "tiempo"},
            {"nombre": "Litros", "abreviatura": "l", "tipo": "volumen"},
        ]
        for u in unidades:
            UnidadMedida.objects.get_or_create(nombre=u["nombre"], defaults=u)
        self.stdout.write(self.style.SUCCESS("✔️ Unidades de Medida creadas."))

    def crear_categorias_basicas(self):
        categorias = [
            "Materia Prima",
            "Producto Terminado",
            "Servicios",
            "Insumos",
            "Scrap",
        ]
        for cat in categorias:
            Categoria.objects.get_or_create(nombre=cat)
        self.stdout.write(self.style.SUCCESS("✔️ Categorías básicas creadas."))

    def crear_ubicaciones_almacen(self):
        # 1. Almacén Físico
        Ubicacion.objects.get_or_create(
            nombre="Almacén Principal", defaults={"tipo": "interna"}
        )

        # 2. Virtual: Producción
        Ubicacion.objects.get_or_create(
            nombre="Producción", defaults={"tipo": "produccion"}
        )

        # 3. Virtual: Scrap
        Ubicacion.objects.get_or_create(
            nombre="Scrap / Mermas", defaults={"tipo": "ajuste"}
        )

        # 4. Custodia RIGI / Maquila -> Depósito de Fábrica
        Ubicacion.objects.get_or_create(
            nombre="Depósito de Fábrica", defaults={"tipo": "interna"}
        )

        # 5. Virtual: Clientes
        Ubicacion.objects.get_or_create(nombre="Clientes", defaults={"tipo": "cliente"})

        # 6. Virtual: Proveedores
        Ubicacion.objects.get_or_create(
            nombre="Proveedores", defaults={"tipo": "proveedor"}
        )
        self.stdout.write(self.style.SUCCESS("✔️ Ubicaciones logísticas creadas."))

    def crear_contactos_sistema(self):
        # AFIP (Autoridad Recaudadora)
        tipo_cuit = TipoDocumentoAFIP.objects.filter(codigo="80").first()
        Contacto.objects.get_or_create(
            codigo="AFIP-01",
            defaults={
                "nombre": "ARCA",
                "tipo_documento": tipo_cuit,
                "cuil": "33-69345023-9",
                "condicion_iva": "exento",
                "tipo": "proveedor",
            },
        )

        # Consumidor Final Genérico (Para Ventas Mostrador / Circuito X)
        tipo_sin_identificar = TipoDocumentoAFIP.objects.filter(codigo="99").first()
        Contacto.objects.get_or_create(
            codigo="CF-01",
            defaults={
                "nombre": "Consumidor Final Genérico",
                "tipo_documento": tipo_sin_identificar,
                "cuil": "",
                "condicion_iva": "consumidor_final",
                "tipo": "cliente",
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                "✔️ Contactos de sistema (AFIP / Consumidor Final) creados."
            )
        )

    def crear_impuestos(self):
        impuestos = [
            {
                "nombre": "IVA 0%",
                "tipo": "iva",
                "alicuota": 0.00,
                "aplicacion": "ambas",
            },
            {
                "nombre": "IVA 2.5%",
                "tipo": "iva",
                "alicuota": 2.50,
                "aplicacion": "ambas",
            },
            {
                "nombre": "IVA 5%",
                "tipo": "iva",
                "alicuota": 5.00,
                "aplicacion": "ambas",
            },
            {
                "nombre": "IVA 10.5%",
                "tipo": "iva",
                "alicuota": 10.50,
                "aplicacion": "ambas",
            },
            {
                "nombre": "IVA 21%",
                "tipo": "iva",
                "alicuota": 21.00,
                "aplicacion": "ambas",
            },
            {
                "nombre": "IVA 27%",
                "tipo": "iva",
                "alicuota": 27.00,
                "aplicacion": "ambas",
            },
        ]
        for imp in impuestos:
            Impuesto.objects.get_or_create(nombre=imp["nombre"], defaults=imp)
        self.stdout.write(self.style.SUCCESS("✔️ Impuestos y alícuotas AFIP creados."))

    def cargar_tipos_comprobantes_afip(self):
        csv_path = os.path.join(
            settings.BASE_DIR, "implementeacion", "tipos_comprobantes_afip.csv"
        )

        if not os.path.exists(csv_path):
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️ No se encontró {csv_path}. Saltando carga de comprobantes."
                )
            )
            return

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                es_electronico = row["es_electronico"].lower() == "true"
                es_mipyme = row["es_mipyme_fce"].lower() == "true"
                es_exportacion = row["es_exportacion"].lower() == "true"

                TipoComprobanteAFIP.objects.get_or_create(
                    codigo=row["codigo"].zfill(3),
                    defaults={
                        "nombre": row["nombre"],
                        "letra": row["letra"],
                        "clasificacion_interna": row["clasificacion_interna"],
                        "es_electronico": es_electronico,
                        "es_mipyme_fce": es_mipyme,
                        "es_exportacion": es_exportacion,
                    },
                )
                count += 1

        self.stdout.write(
            self.style.SUCCESS(f"✔️ {count} Tipos de Comprobantes AFIP cargados.")
        )

    def crear_tipos_documento(self):
        docs = [
            {"codigo": "80", "descripcion": "CUIT"},
            {"codigo": "86", "descripcion": "CUIL"},
            {"codigo": "87", "descripcion": "CDI"},
            {"codigo": "96", "descripcion": "DNI"},
            {"codigo": "99", "descripcion": "Consumidor Final"},
        ]
        for doc in docs:
            TipoDocumentoAFIP.objects.get_or_create(
                codigo=doc["codigo"], defaults={"descripcion": doc["descripcion"]}
            )
        self.stdout.write(self.style.SUCCESS("✔️ Tipos de Documento AFIP creados."))

    def crear_monedas(self):
        monedas = [
            {
                "codigo": "PES",
                "nombre": "Pesos Argentinos",
                "simbolo": "$",
                "afip_codigo": "PES",
            },
            {
                "codigo": "USD",
                "nombre": "Dólares",
                "simbolo": "U$S",
                "afip_codigo": "DOL",
            },
            {"codigo": "EUR", "nombre": "Euros", "simbolo": "€", "afip_codigo": "060"},
        ]
        for mon in monedas:
            Moneda.objects.get_or_create(
                codigo=mon["codigo"],
                defaults={
                    "nombre": mon["nombre"],
                    "simbolo": mon["simbolo"],
                    "afip_codigo": mon["afip_codigo"],
                },
            )
        self.stdout.write(self.style.SUCCESS("✔️ Monedas AFIP creadas."))

    def crear_diarios_contables(self):
        # 1. Diario Blanco (Conectado a AFIP)
        Diario.objects.get_or_create(
            codigo="VEN-A",
            defaults={
                "nombre": "Ventas AFIP (Blanco)",
                "tipo": "ventas",
                "punto_venta_afip": 3,
                "es_facturacion_electronica": True,
                "es_exportacion": False,
            },
        )

        # 2. Diario Negro (Circuito X / No Informado)
        Diario.objects.get_or_create(
            codigo="VEN-X",
            defaults={
                "nombre": "Ventas Internas (Circuito X)",
                "tipo": "ventas",
                "punto_venta_afip": None,
                "es_facturacion_electronica": False,
                "es_exportacion": False,
            },
        )
        self.stdout.write(
            self.style.SUCCESS("✔️ Diarios contables (Blanco / X) creados.")
        )
