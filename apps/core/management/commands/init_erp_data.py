import logging
import csv
import os
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from apps.base.models import ConfiguracionEmpresa, Moneda, Secuencia
from apps.inventario.models import UnidadMedida, Categoria, Ubicacion
from apps.contactos.models import Contacto, TipoDocumentoAFIP
from apps.contabilidad.models import Impuesto, TipoComprobanteAFIP, Diario
from apps.ventas.models import ListaPrecio

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Inicializa la base de datos con los datos maestros del ERP"

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
        self.crear_listas_precios()
        self.crear_secuencias_documentos()

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
            {"nombre": "Unidades", "simbolo": "u", "tipo": "unidad"},
            {"nombre": "Kilos", "simbolo": "kg", "tipo": "peso"},
            {"nombre": "Metros", "simbolo": "m", "tipo": "longitud"},
            {"nombre": "Horas", "simbolo": "hs", "tipo": "tiempo"},
            {"nombre": "Litros", "simbolo": "l", "tipo": "volumen"},
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

        # Consumidor Final Genérico (Para Ventas Mostrador / Operaciones Locales)
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
                "afip_id": 3,
            },
            {
                "nombre": "IVA 2.5%",
                "tipo": "iva",
                "alicuota": 2.50,
                "aplicacion": "ambas",
                "afip_id": 9,
            },
            {
                "nombre": "IVA 5%",
                "tipo": "iva",
                "alicuota": 5.00,
                "aplicacion": "ambas",
                "afip_id": 8,
            },
            {
                "nombre": "IVA 10.5%",
                "tipo": "iva",
                "alicuota": 10.50,
                "aplicacion": "ambas",
                "afip_id": 4,
            },
            {
                "nombre": "IVA 21%",
                "tipo": "iva",
                "alicuota": 21.00,
                "aplicacion": "ambas",
                "afip_id": 5,
            },
            {
                "nombre": "IVA 27%",
                "tipo": "iva",
                "alicuota": 27.00,
                "aplicacion": "ambas",
                "afip_id": 6,
            },
            {
                "nombre": "Percepción IIBB PBA (ARBA)",
                "tipo": "percepcion_iibb",
                "alicuota": 3.00,
                "aplicacion": "ventas",
                "jurisdiccion_sifere": "902",
                "afip_id": 2,
            },
            {
                "nombre": "Percepción IIBB CABA (AGIP)",
                "tipo": "percepcion_iibb",
                "alicuota": 3.00,
                "aplicacion": "ventas",
                "jurisdiccion_sifere": "901",
                "afip_id": 2,
            },
        ]
        for imp in impuestos:
            Impuesto.objects.get_or_create(nombre=imp["nombre"], defaults=imp)
        self.stdout.write(self.style.SUCCESS("✔️ Impuestos y alícuotas AFIP creados con afip_id oficial."))

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
        # 1. Diario de Ventas Electrónicas (Conectado a AFIP/ARCA)
        Diario.objects.get_or_create(
            codigo="VEN-A",
            defaults={
                "nombre": "Ventas Electrónicas (AFIP)",
                "tipo": "ventas",
                "punto_venta_afip": 3,
                "es_facturacion_electronica": True,
                "es_exportacion": False,
            },
        )

        # 2. Diario de Gestión y Control Interno (No Electrónico / RG AFIP 1415)
        Diario.objects.get_or_create(
            codigo="VEN-X",
            defaults={
                "nombre": "Ventas de Gestión Interna",
                "tipo": "ventas",
                "punto_venta_afip": None,
                "es_facturacion_electronica": False,
                "es_exportacion": False,
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                "✔️ Diarios contables (Electrónico / Gestión Interna) creados."
            )
        )

    def crear_listas_precios(self):
        moneda_pes = Moneda.objects.filter(codigo="PES").first()
        moneda_usd = Moneda.objects.filter(codigo="USD").first()

        if not moneda_pes:
            self.stdout.write(
                self.style.WARNING(
                    "⚠️ Moneda PES no encontrada, omitiendo listas de precio."
                )
            )
            return

        # 1. Lista de Precios Minorista / Público General (ARS)
        lista_minorista, created_min = ListaPrecio.objects.get_or_create(
            codigo="MIN-ARS",
            defaults={
                "nombre": "Minorista / Consumidor Final (ARS)",
                "moneda": moneda_pes,
                "descripcion": "Tarifa base para venta al público y mostrador",
                "activa": True,
            },
        )

        # 2. Lista de Precios Mayorista / Distribuidores (ARS)
        ListaPrecio.objects.get_or_create(
            codigo="MAY-ARS",
            defaults={
                "nombre": "Mayorista (ARS)",
                "moneda": moneda_pes,
                "descripcion": "Tarifa para operaciones B2B y compras por volumen en pesos",
                "activa": True,
            },
        )

        # 3. Lista de Precios Mayorista USD (si existe moneda USD)
        if moneda_usd:
            ListaPrecio.objects.get_or_create(
                codigo="MAY-USD",
                defaults={
                    "nombre": "Mayorista / Comercio Exterior (USD)",
                    "moneda": moneda_usd,
                    "descripcion": "Tarifa en moneda extranjera para distribuidores",
                    "activa": True,
                },
            )

        # Asignar lista minorista predeterminada al Consumidor Final Genérico
        contacto_cf = Contacto.objects.filter(codigo="CF-01").first()
        if contacto_cf and not contacto_cf.lista_precio_defecto:
            contacto_cf.lista_precio_defecto = lista_minorista
            contacto_cf.save(update_fields=["lista_precio_defecto"])

        self.stdout.write(
            self.style.SUCCESS("✔️ Listas de Precios de venta maestras creadas.")
        )

    def crear_secuencias_documentos(self):
        secuencias = [
            # --- VENTAS Y COMPRAS ---
            {
                "codigo": "ventas.ov",
                "nombre": "Orden de Venta (B2B / Presupuestos)",
                "prefijo": "OV-%(year)s-",
                "longitud_relleno": 8,
                "reinicio_anual": True,
            },
            {
                "codigo": "compras.oc",
                "nombre": "Orden de Compra a Proveedores",
                "prefijo": "OC-%(year)s-",
                "longitud_relleno": 8,
                "reinicio_anual": True,
            },
            # --- INVENTARIO (LOGÍSTICA Y REMITOS) ---
            {
                "codigo": "inventario.remito_fiscal",
                "nombre": "Remito Fiscal Electrónico (R)",
                "prefijo": "R-%(puntoventa)s-",
                "punto_venta": 1,
                "longitud_relleno": 8,
                "reinicio_anual": False,
            },
            {
                "codigo": "inventario.recepcion",
                "nombre": "Remito de Recepción / Entrada",
                "prefijo": "REC-%(year)s-",
                "longitud_relleno": 8,
                "reinicio_anual": True,
            },
            {
                "codigo": "inventario.entrega",
                "nombre": "Remito de Entrega / Despacho",
                "prefijo": "ENT-%(year)s-",
                "longitud_relleno": 8,
                "reinicio_anual": True,
            },
            {
                "codigo": "inventario.traslado",
                "nombre": "Traslado Interno de Stock",
                "prefijo": "TRA-%(year)s-",
                "longitud_relleno": 8,
                "reinicio_anual": True,
            },
            # --- CONTABILIDAD / COMPROBANTES DE GESTIÓN (X) ---
            {
                "codigo": "contabilidad.factura_x",
                "nombre": "Comprobante de Venta Interno (X)",
                "prefijo": "X-%(puntoventa)s-",
                "punto_venta": 99,
                "longitud_relleno": 8,
                "reinicio_anual": False,
            },
            # --- TESORERÍA (PAGOS Y COBRANZAS) ---
            {
                "codigo": "tesoreria.recibo",
                "nombre": "Recibo de Cobranza (Cliente)",
                "prefijo": "REC-COB-%(year)s-",
                "longitud_relleno": 8,
                "reinicio_anual": True,
            },
            {
                "codigo": "tesoreria.orden_pago",
                "nombre": "Orden de Pago (Proveedor / Tallerista)",
                "prefijo": "OP-TES-%(year)s-",
                "longitud_relleno": 8,
                "reinicio_anual": True,
            },
            {
                "codigo": "tesoreria.transferencia",
                "nombre": "Transferencia entre Cajas / Bancos",
                "prefijo": "TRA-TES-%(year)s-",
                "longitud_relleno": 8,
                "reinicio_anual": True,
            },
            # --- PRODUCCIÓN INDUSTRIAL Y RED FEDERADA ---
            {
                "codigo": "produccion.op",
                "nombre": "Orden de Producción (Planta)",
                "prefijo": "OP-%(year)s-",
                "longitud_relleno": 8,
                "reinicio_anual": True,
            },
            {
                "codigo": "eop.contrato",
                "nombre": "Contrato e-OP Federado FIMCA",
                "prefijo": "EOP-%(year)s-",
                "longitud_relleno": 8,
                "reinicio_anual": True,
            },
            # --- COMUNICACIONES OFICIALES Y CÉDULAS ELECTRÓNICAS ---
            {
                "codigo": "federacion.comunicacion",
                "nombre": "Comunicación Oficial Federada / Cédula Electrónica",
                "prefijo": "NO-%(year)s-",
                "longitud_relleno": 8,
                "reinicio_anual": True,
            },
        ]

        for sec in secuencias:
            Secuencia.objects.get_or_create(
                codigo=sec["codigo"],
                defaults=sec,
            )
        self.stdout.write(
            self.style.SUCCESS(
                "✔️ Secuencias maestras de documentos inicializadas (longitud unificada a 8 dígitos)."
            )
        )
