from django.db import transaction
from django.core.exceptions import ValidationError
from apps.contabilidad.models import Asiento, ConfiguracionContable
from apps.contabilidad.services import ContabilidadService
from apps.base.models import ConfiguracionEmpresa

class ContabilizacionDocumentoService:
    @staticmethod
    @transaction.atomic
    def contabilizar_factura(doc):
        if doc.estado != 'publicado':
            raise ValidationError('Solo se pueden contabilizar documentos publicados.')
            
        # Evitar duplicados
        asientos_existentes = Asiento.objects.filter(
            content_type__model='documentodeuda', 
            object_id=doc.id
        )
        if asientos_existentes.exists():
            return asientos_existentes.first()

        # Obtener configuración global
        empresa_config = ConfiguracionEmpresa.get_solo()
        try:
            config_contable = empresa_config.contabilidad
        except:
            raise ValidationError("Falta crear la Configuración Contable base.")

        lineas = []
        contacto_perfil = getattr(doc.contacto, 'perfil_contable', None)

        if doc.tipo in ['factura_cliente', 'nota_debito_cliente']:
            # Deudores por Ventas
            cta_cobrar = contacto_perfil.cuenta_a_cobrar if contacto_perfil and contacto_perfil.cuenta_a_cobrar else config_contable.cuenta_clientes_defecto
            lineas.append({'cuenta_codigo': cta_cobrar.codigo, 'debe': doc.monto_total, 'haber': 0, 'contacto': doc.contacto})
            
            # Ventas (Desglosar por linea para soportar múltiples cuentas de ingreso)
            for linea in doc.lineas.all():
                if linea.subtotal > 0:
                    perfil_prod = getattr(linea.producto, 'perfil_contable', None) if linea.producto else None
                    cta_ingreso = perfil_prod.cuenta_ingreso if perfil_prod and perfil_prod.cuenta_ingreso else config_contable.cuenta_ventas_defecto
                    lineas.append({'cuenta_codigo': cta_ingreso.codigo, 'debe': 0, 'haber': linea.subtotal, 'contacto': doc.contacto})
            
            # IVA Débito (Agrupando impuestos de lineas)
            for linea in doc.lineas.all():
                if linea.impuesto and linea.impuesto.cuenta_imputacion:
                    monto_impuesto = linea.subtotal * (linea.impuesto.alicuota / 100)
                    if monto_impuesto > 0:
                        lineas.append({'cuenta_codigo': linea.impuesto.cuenta_imputacion.codigo, 'debe': 0, 'haber': monto_impuesto, 'contacto': doc.contacto})

        elif doc.tipo in ['factura_proveedor', 'nota_debito_proveedor', 'liquidacion_fason']:
            # Proveedores o Talleristas
            cta_pagar = contacto_perfil.cuenta_a_pagar if contacto_perfil and contacto_perfil.cuenta_a_pagar else config_contable.cuenta_proveedores_defecto
            lineas.append({'cuenta_codigo': cta_pagar.codigo, 'debe': 0, 'haber': doc.monto_total, 'contacto': doc.contacto})
            
            # Compras / Gastos (Desglosar por linea)
            for linea in doc.lineas.all():
                if linea.subtotal > 0:
                    perfil_prod = getattr(linea.producto, 'perfil_contable', None) if linea.producto else None
                    cta_gasto = perfil_prod.cuenta_gasto if perfil_prod and perfil_prod.cuenta_gasto else config_contable.cuenta_gastos_defecto
                    lineas.append({'cuenta_codigo': cta_gasto.codigo, 'debe': linea.subtotal, 'haber': 0, 'contacto': doc.contacto})
            
            # IVA Crédito
            for linea in doc.lineas.all():
                if linea.impuesto and linea.impuesto.cuenta_imputacion:
                    monto_impuesto = linea.subtotal * (linea.impuesto.alicuota / 100)
                    if monto_impuesto > 0:
                        lineas.append({'cuenta_codigo': linea.impuesto.cuenta_imputacion.codigo, 'debe': monto_impuesto, 'haber': 0, 'contacto': doc.contacto})

        if not lineas:
            return None

        # Consolidar lineas por cuenta si es necesario (el servicio ya debería manejarlo o las insertamos crudas)
        
        # Crear y asentar
        asiento = ContabilidadService.crear_asiento(
            diario_codigo=doc.diario.codigo,
            fecha=doc.fecha_emision,
            descripcion=f"Asiento de {doc.get_tipo_display()} {doc.numero}",
            lineas_apuntes=lineas,
            documento_origen=doc
        )
        return ContabilidadService.validar_y_asentar(asiento.id)
