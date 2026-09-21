from django.db import transaction
from django.db.models import Sum
from decimal import Decimal
from django.core.exceptions import ValidationError
from .models import Asiento, Apunte, Cuenta, Diario

class ContabilidadService:
    """
    Servicio estricto para gestionar la Partida Doble.
    Ningún asiento puede pasar a estado 'asentado' si no cuadra perfectamente.
    """

    @staticmethod
    @transaction.atomic
    def crear_asiento(diario_codigo, fecha, descripcion, lineas_apuntes, documento_origen=None):
        """
        Crea un asiento y sus apuntes en estado borrador.
        lineas_apuntes: lista de diccionarios [{'cuenta_codigo': '1.1.01', 'debe': 100, 'haber': 0, 'contacto': obj}, ...]
        """
        diario = Diario.objects.get(codigo=diario_codigo)
        
        # Generar numero de asiento (Simplificado para el ERP)
        ultimo_asiento = Asiento.objects.filter(diario=diario, fecha__year=fecha.year).count()
        numero = f"AST-{diario.codigo}-{fecha.year}-{(ultimo_asiento + 1):06d}"

        asiento = Asiento.objects.create(
            numero=numero,
            fecha=fecha,
            descripcion=descripcion,
            diario=diario,
            estado='borrador'
        )

        if documento_origen:
            asiento.documento_origen = documento_origen
            asiento.save(update_fields=['content_type', 'object_id'])

        for linea in lineas_apuntes:
            cuenta = Cuenta.objects.get(codigo=linea['cuenta_codigo'])
            if not cuenta.imputable:
                raise ValidationError(f"La cuenta {cuenta.codigo} no es imputable. Es una cuenta agrupadora.")
            
            Apunte.objects.create(
                asiento=asiento,
                cuenta=cuenta,
                debe=Decimal(str(linea.get('debe', 0.00))),
                haber=Decimal(str(linea.get('haber', 0.00))),
                contacto=linea.get('contacto'),
                descripcion_linea=linea.get('descripcion_linea', '')
            )

        return asiento

    @staticmethod
    @transaction.atomic
    def validar_y_asentar(asiento_id):
        """
        Pasa un asiento de 'borrador' a 'asentado'.
        Aplica la regla fundamental de la Partida Doble: Suma del Debe == Suma del Haber.
        """
        asiento = Asiento.objects.select_for_update().get(id=asiento_id)
        
        if asiento.estado == 'asentado':
            return asiento # Ya estaba asentado
            
        if asiento.estado == 'anulado':
            raise ValidationError("No se puede asentar un asiento anulado.")

        totales = asiento.apuntes.aggregate(
            total_debe=Sum('debe'),
            total_haber=Sum('haber')
        )
        
        total_debe = totales['total_debe'] or Decimal('0.00')
        total_haber = totales['total_haber'] or Decimal('0.00')

        if total_debe != total_haber:
            raise ValidationError(
                f"Asiento Descuadrado (Partida Doble fallida). Debe: {total_debe} | Haber: {total_haber}. Diferencia: {total_debe - total_haber}"
            )
            
        if total_debe == Decimal('0.00'):
            raise ValidationError("El asiento no tiene montos registrados.")
            
        if asiento.diario.es_facturacion_electronica and asiento.documento_origen:
            doc = asiento.documento_origen
            if hasattr(doc, 'afip_cae') and not doc.afip_cae:
                raise ValidationError("No se puede asentar este asiento porque el diario es electrónico y el documento origen no tiene CAE autorizado.")

        asiento.estado = 'asentado'
        asiento.save(update_fields=['estado'])
        
        return asiento

    @staticmethod
    @transaction.atomic
    def crear_nota_credito_desde_comprobante(factura_original, motivo="Anulación de factura", lineas_seleccionadas=None):
        """
        Crea una Nota de Crédito en borrador vinculada a la factura o comprobante original.
        - Copia las líneas seleccionadas (o todas si lineas_seleccionadas es None).
        - Asigna el tipo correspondiente (nota_credito_cliente o nota_credito_proveedor).
        - Vincula comprobante_asociado para cumplir con el nodo CbtesAsoc de AFIP.
        """
        from .models import DocumentoDeuda, LineaDocumentoDeuda, TipoComprobanteAFIP

        if factura_original.estado not in ["publicado", "pagado", "pagado_parcial"]:
            raise ValidationError("Solo se pueden emitir Notas de Crédito sobre comprobantes confirmados o publicados.")

        # Determinar tipo inverso y código de comprobante AFIP
        es_cliente = "cliente" in factura_original.tipo or factura_original.tipo == "factura_cliente"
        tipo_nc = "nota_credito_cliente" if es_cliente else "nota_credito_proveedor"

        # Buscar el tipo de comprobante AFIP de Nota de Crédito correspondiente a la misma letra
        tipo_afip_nc = None
        if factura_original.tipo_comprobante_afip:
            letra_orig = factura_original.tipo_comprobante_afip.letra
            tipo_afip_nc = TipoComprobanteAFIP.objects.filter(
                clasificacion_interna="nota_credito",
                letra=letra_orig,
            ).first()

        nc = DocumentoDeuda.objects.create(
            diario=factura_original.diario,
            tipo=tipo_nc,
            tipo_comprobante_afip=tipo_afip_nc,
            comprobante_asociado=factura_original,
            contacto=factura_original.contacto,
            fecha_emision=factura_original.fecha_emision,
            fecha_vencimiento=factura_original.fecha_vencimiento,
            condicion_pago=factura_original.condicion_pago,
            moneda=factura_original.moneda,
            tasa_cambio=factura_original.tasa_cambio,
            estado="borrador",
        )

        lineas_a_copiar = factura_original.lineas.all()
        if lineas_seleccionadas is not None:
            lineas_a_copiar = lineas_a_copiar.filter(id__in=lineas_seleccionadas)

        monto_neto = Decimal("0.00")
        monto_impuestos = Decimal("0.00")

        for linea_orig in lineas_a_copiar:
            subtotal = linea_orig.cantidad * linea_orig.precio_unitario
            monto_neto += subtotal
            if linea_orig.impuesto and linea_orig.impuesto.alicuota > 0:
                monto_impuestos += (subtotal * linea_orig.impuesto.alicuota) / Decimal("100.00")

            LineaDocumentoDeuda.objects.create(
                documento=nc,
                producto=linea_orig.producto,
                descripcion=f"NC: {linea_orig.descripcion}",
                cantidad=linea_orig.cantidad,
                precio_unitario=linea_orig.precio_unitario,
                impuesto=linea_orig.impuesto,
                subtotal=subtotal,
            )

        nc.monto_neto = monto_neto
        nc.monto_impuestos = monto_impuestos
        nc.monto_total = monto_neto + monto_impuestos
        nc.save(update_fields=["monto_neto", "monto_impuestos", "monto_total"])

        return nc

    @staticmethod
    @transaction.atomic
    def crear_nota_debito_desde_comprobante(
        factura_original,
        motivo="Intereses por mora / Recargo",
        monto_neto=Decimal("0.00"),
        alicuota_iva=Decimal("21.00"),
        descripcion_concepto="",
        tributos_adicionales=None,
    ):
        """
        Crea una Nota de Débito en borrador vinculada a la factura original:
        - Asigna el tipo correspondiente (nota_debito_cliente o nota_debito_proveedor).
        - Vincula comprobante_asociado para cumplir con el nodo obligatorio CbtesAsoc de AFIP.
        - Asigna automáticamente el código oficial de AFIP (TipoComprobanteAFIP) según la letra original (A, B o C).
        - Genera la línea de concepto correspondiente a los intereses o recargos y calcula el débito fiscal.
        - Si se especifican tributos_adicionales (ej. percepciones de IIBB sobre los intereses debitados),
          se crean los registros de TributoDocumentoDeuda y se acumulan al monto total.
        """
        from .models import DocumentoDeuda, LineaDocumentoDeuda, TipoComprobanteAFIP, Impuesto, TributoDocumentoDeuda

        if factura_original.estado not in ["publicado", "pagado", "pagado_parcial"]:
            raise ValidationError("Solo se pueden emitir Notas de Débito sobre comprobantes confirmados o publicados.")

        monto_neto = Decimal(str(monto_neto))
        alicuota_iva = Decimal(str(alicuota_iva))
        if monto_neto <= Decimal("0.00"):
            raise ValidationError("El monto neto de la Nota de Débito debe ser mayor a 0.")

        es_cliente = "cliente" in factura_original.tipo or factura_original.tipo == "factura_cliente"
        tipo_nd = "nota_debito_cliente" if es_cliente else "nota_debito_proveedor"

        # Buscar el tipo de comprobante AFIP de Nota de Débito correspondiente a la misma letra
        tipo_afip_nd = None
        if factura_original.tipo_comprobante_afip:
            letra_orig = factura_original.tipo_comprobante_afip.letra
            tipo_afip_nd = TipoComprobanteAFIP.objects.filter(
                clasificacion_interna="nota_debito",
                letra=letra_orig,
            ).first()

        nd = DocumentoDeuda.objects.create(
            diario=factura_original.diario,
            tipo=tipo_nd,
            tipo_comprobante_afip=tipo_afip_nd,
            comprobante_asociado=factura_original,
            contacto=factura_original.contacto,
            fecha_emision=factura_original.fecha_emision,
            fecha_vencimiento=factura_original.fecha_vencimiento,
            condicion_pago=factura_original.condicion_pago,
            moneda=factura_original.moneda,
            tasa_cambio=factura_original.tasa_cambio,
            estado="borrador",
        )

        # Buscar impuesto correspondiente
        impuesto = None
        if alicuota_iva > Decimal("0.00"):
            impuesto = Impuesto.objects.filter(tipo="iva", alicuota=alicuota_iva).first()

        monto_impuestos = (monto_neto * (alicuota_iva / Decimal("100.00"))).quantize(Decimal("0.01")) if alicuota_iva > 0 else Decimal("0.00")

        desc = descripcion_concepto or f"ND: {motivo} s/ {factura_original.numero}"
        LineaDocumentoDeuda.objects.create(
            documento=nd,
            descripcion=desc,
            cantidad=Decimal("1.00"),
            precio_unitario=monto_neto,
            impuesto=impuesto,
            subtotal=monto_neto,
        )

        # Procesar tributos y percepciones adicionales si fueron provistos
        monto_tributos = Decimal("0.00")
        if tributos_adicionales:
            for trib_data in tributos_adicionales:
                imp_trib = Decimal(str(trib_data.get("importe", 0.00)))
                monto_tributos += imp_trib
                TributoDocumentoDeuda.objects.create(
                    documento=nd,
                    afip_tributo_id=trib_data.get("afip_tributo_id", 2),
                    descripcion=trib_data.get("descripcion", "Percepción adicional"),
                    base_imponible=Decimal(str(trib_data.get("base_imponible", monto_neto))),
                    alicuota=Decimal(str(trib_data.get("alicuota", 0.00))),
                    importe=imp_trib,
                    impuesto=trib_data.get("impuesto"),
                )

        nd.monto_neto = monto_neto
        nd.monto_impuestos = monto_impuestos
        nd.monto_tributos = monto_tributos
        nd.monto_total = monto_neto + monto_impuestos + monto_tributos
        nd.save(update_fields=["monto_neto", "monto_impuestos", "monto_tributos", "monto_total"])

        return nd


