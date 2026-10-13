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

            # Percepciones Cobradas en Venta (Pasivo fiscal a ingresar al Fisco al Haber)
            for trib in doc.tributos.all():
                if trib.importe > 0:
                    cta_trib = trib.impuesto.cuenta_imputacion if trib.impuesto and trib.impuesto.cuenta_imputacion else None
                    if cta_trib:
                        lineas.append({'cuenta_codigo': cta_trib.codigo, 'debe': 0, 'haber': trib.importe, 'contacto': doc.contacto})

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
            
            # IVA Crédito Fiscal:
            # Art. 23.2 Ley e-OP: Los anticipos y tramos de avance de una e-OP NO perfeccionan el hecho imponible del IVA.
            # Solo devengan IVA si NO es un anticipo en custodia o si corresponde a la liquidación final con entrega de lote conforme.
            es_anticipo_eop = getattr(doc, "es_anticipo_eop", False)
            if not es_anticipo_eop:
                for linea in doc.lineas.all():
                    if linea.impuesto and linea.impuesto.cuenta_imputacion:
                        monto_impuesto = linea.subtotal * (linea.impuesto.alicuota / 100)
                        if monto_impuesto > 0:
                            lineas.append({'cuenta_codigo': linea.impuesto.cuenta_imputacion.codigo, 'debe': monto_impuesto, 'haber': 0, 'contacto': doc.contacto})

            # Percepciones Sufridas en Compra (Crédito fiscal / Activo impositivo al Debe)
            for trib in doc.tributos.all():
                if trib.importe > 0:
                    cta_trib = trib.impuesto.cuenta_imputacion if trib.impuesto and trib.impuesto.cuenta_imputacion else None
                    if cta_trib:
                        lineas.append({'cuenta_codigo': cta_trib.codigo, 'debe': trib.importe, 'haber': 0, 'contacto': doc.contacto})

        elif doc.tipo == 'nota_credito_cliente':
            # Anulación de venta: Deudores por Ventas al HABER, Ingreso al DEBE, IVA Débito al DEBE
            cta_cobrar = contacto_perfil.cuenta_a_cobrar if contacto_perfil and contacto_perfil.cuenta_a_cobrar else config_contable.cuenta_clientes_defecto
            lineas.append({'cuenta_codigo': cta_cobrar.codigo, 'debe': 0, 'haber': doc.monto_total, 'contacto': doc.contacto})

            for linea in doc.lineas.all():
                if linea.subtotal > 0:
                    perfil_prod = getattr(linea.producto, 'perfil_contable', None) if linea.producto else None
                    cta_ingreso = perfil_prod.cuenta_ingreso if perfil_prod and perfil_prod.cuenta_ingreso else config_contable.cuenta_ventas_defecto
                    lineas.append({'cuenta_codigo': cta_ingreso.codigo, 'debe': linea.subtotal, 'haber': 0, 'contacto': doc.contacto})

            for linea in doc.lineas.all():
                if linea.impuesto and linea.impuesto.cuenta_imputacion:
                    monto_impuesto = linea.subtotal * (linea.impuesto.alicuota / 100)
                    if monto_impuesto > 0:
                        lineas.append({'cuenta_codigo': linea.impuesto.cuenta_imputacion.codigo, 'debe': monto_impuesto, 'haber': 0, 'contacto': doc.contacto})

            # Reversión de Percepciones Cobradas en Venta (Pasivo fiscal al Debe)
            for trib in doc.tributos.all():
                if trib.importe > 0:
                    cta_trib = trib.impuesto.cuenta_imputacion if trib.impuesto and trib.impuesto.cuenta_imputacion else None
                    if cta_trib:
                        lineas.append({'cuenta_codigo': cta_trib.codigo, 'debe': trib.importe, 'haber': 0, 'contacto': doc.contacto})

        elif doc.tipo == 'nota_credito_proveedor':
            # Anulación de compra: Proveedores al DEBE, Gasto al HABER, IVA Crédito al HABER
            cta_pagar = contacto_perfil.cuenta_a_pagar if contacto_perfil and contacto_perfil.cuenta_a_pagar else config_contable.cuenta_proveedores_defecto
            lineas.append({'cuenta_codigo': cta_pagar.codigo, 'debe': doc.monto_total, 'haber': 0, 'contacto': doc.contacto})

            for linea in doc.lineas.all():
                if linea.subtotal > 0:
                    perfil_prod = getattr(linea.producto, 'perfil_contable', None) if linea.producto else None
                    cta_gasto = perfil_prod.cuenta_gasto if perfil_prod and perfil_prod.cuenta_gasto else config_contable.cuenta_gastos_defecto
                    lineas.append({'cuenta_codigo': cta_gasto.codigo, 'debe': 0, 'haber': linea.subtotal, 'contacto': doc.contacto})

            for linea in doc.lineas.all():
                if linea.impuesto and linea.impuesto.cuenta_imputacion:
                    monto_impuesto = linea.subtotal * (linea.impuesto.alicuota / 100)
                    if monto_impuesto > 0:
                        lineas.append({'cuenta_codigo': linea.impuesto.cuenta_imputacion.codigo, 'debe': 0, 'haber': monto_impuesto, 'contacto': doc.contacto})

            # Reversión de Percepciones Sufridas en Compra (Activo fiscal al Haber)
            for trib in doc.tributos.all():
                if trib.importe > 0:
                    cta_trib = trib.impuesto.cuenta_imputacion if trib.impuesto and trib.impuesto.cuenta_imputacion else None
                    if cta_trib:
                        lineas.append({'cuenta_codigo': cta_trib.codigo, 'debe': 0, 'haber': trib.importe, 'contacto': doc.contacto})

        if not lineas:
            return None

        # Crear y asentar
        asiento = ContabilidadService.crear_asiento(
            diario_codigo=doc.diario.codigo,
            fecha=doc.fecha_emision,
            descripcion=f"Asiento de {doc.get_tipo_display()} {doc.numero}",
            lineas_apuntes=lineas,
            documento_origen=doc
        )
        return ContabilidadService.validar_y_asentar(asiento.id)

    @staticmethod
    @transaction.atomic
    def contabilizar_credito_fiscal_presunto_eop(contrato_eop, fecha=None):
        """
        Cómputo del Crédito Fiscal Presunto del 10% (Art. 23.1 Ley e-OP).
        Registra en el libro IVA Compras de la marca comitente un Crédito Fiscal Presunto
        del 10% sobre el c_MOD de contratos e-OP cumplidos con monotributistas productivos.
        """
        from decimal import Decimal
        from django.utils import timezone
        from apps.eop.services import UCIService

        cotizacion_uci = UCIService.obtener_cotizacion_actual()
        if not cotizacion_uci or cotizacion_uci <= 0:
            cotizacion_uci = Decimal("1.00")

        # Base imponible: c_MOD expresado en ARS
        mod_ars = round(Decimal(str(contrato_eop.costo_mod)) * cotizacion_uci, 2)
        if mod_ars <= Decimal("0.00"):
            return None

        credito_presunto_ars = round(mod_ars * Decimal("0.10"), 2)

        empresa_config = ConfiguracionEmpresa.get_solo()
        config_contable = empresa_config.contabilidad

        # Cuenta IVA Crédito Fiscal (Activo)
        cta_credito_iva = config_contable.cuenta_gastos_defecto  # Fallback si no hay cuenta IVA presunto específica
        # Buscamos cuenta de IVA crédito o usamos cuentas configuradas
        cta_bonificacion = config_contable.cuenta_ventas_defecto  # Menor costo / bonificación fiscal

        contacto_taller = contrato_eop.ptf_asignado
        fecha_asiento = fecha or timezone.now().date()

        lineas = [
            {
                "cuenta_codigo": cta_credito_iva.codigo,
                "debe": credito_presunto_ars,
                "haber": Decimal("0.00"),
                "contacto": contacto_taller,
            },
            {
                "cuenta_codigo": cta_bonificacion.codigo,
                "debe": Decimal("0.00"),
                "haber": credito_presunto_ars,
                "contacto": contacto_taller,
            },
        ]

        diario_codigo = "LIB_COMPRAS" if hasattr(contrato_eop, "diario") else "GEN"

        # Buscar diario existente o usar el primero
        from apps.contabilidad.models import Diario
        diario = Diario.objects.filter(tipo="compras").first() or Diario.objects.first()
        if not diario:
            return None

        asiento = ContabilidadService.crear_asiento(
            diario_codigo=diario.codigo,
            fecha=fecha_asiento,
            descripcion=f"Crédito Fiscal Presunto 10% Art. 23.1 Ley e-OP - Contrato {contrato_eop.numero or contrato_eop.uuid_identificador}",
            lineas_apuntes=lineas,
            documento_origen=contrato_eop,
        )
        return ContabilidadService.validar_y_asentar(asiento.id)
