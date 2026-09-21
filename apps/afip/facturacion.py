from datetime import datetime
import logging
from apps.contabilidad.contabilizacion import ContabilizacionDocumentoService
from .client import AFIPClientFactory

logger = logging.getLogger(__name__)


class FacturadorAFIP:
    """
    Adapter para integrar la facturación electrónica de AFIP mediante afip.py (WSFE / WSFEX).
    """

    def __init__(self):
        self.afip = AFIPClientFactory.get_client()

    @staticmethod
    def validar_compatibilidad_fiscal(emisor, receptor, tipo_comprobante):
        """
        Valida que el tipo de comprobante seleccionado sea legalmente admisible
        según la combinación de condición frente al IVA del emisor y del receptor.
        """
        cond_emisor = getattr(emisor, "condicion_iva", "responsable_inscripto")
        cond_receptor = getattr(receptor, "condicion_iva", "consumidor_final")
        letra = tipo_comprobante.letra.upper()

        # Validación 1: Empresa Monotributista
        if cond_emisor == "monotributista":
            if letra not in ["C", "E"]:
                raise ValueError(
                    f"Inconsistencia fiscal: La empresa emisora está configurada como Monotributista "
                    f"y únicamente puede emitir comprobantes clase 'C' o 'E' (se intentó emitir clase '{letra}')."
                )

        # Validación 2: Empresa Exenta
        elif cond_emisor == "exento":
            if letra not in ["C", "E"]:
                raise ValueError(
                    f"Inconsistencia fiscal: La empresa emisora es Exenta en IVA "
                    f"y únicamente puede emitir comprobantes clase 'C' o 'E' (se intentó emitir clase '{letra}')."
                )

        # Validación 3: Empresa Responsable Inscripto
        elif cond_emisor == "responsable_inscripto":
            if letra == "C":
                raise ValueError(
                    "Inconsistencia fiscal: Una empresa Responsable Inscripto no puede emitir comprobantes clase 'C'."
                )
            if letra in ["A", "M"]:
                if cond_receptor != "responsable_inscripto":
                    raise ValueError(
                        f"Inconsistencia fiscal: Los comprobantes clase '{letra}' solo pueden ser emitidos a "
                        f"receptores Responsables Inscriptos (el contacto '{receptor.nombre}' tiene condición '{receptor.get_condicion_iva_display()}')."
                    )
                cuit = str(getattr(receptor, "cuil", "") or getattr(receptor, "cuit", "")).replace("-", "").strip()
                if len(cuit) != 11:
                    raise ValueError(
                        f"Inconsistencia fiscal: La emisión de comprobantes clase '{letra}' exige CUIT válido de 11 dígitos en el receptor."
                    )
            elif letra == "B":
                if cond_receptor == "responsable_inscripto":
                    raise ValueError(
                        f"Inconsistencia fiscal: No se puede emitir comprobante clase 'B' a un Responsable Inscripto (corresponde clase 'A' o 'M')."
                    )

    def emitir_comprobante(self, documento_deuda):
        """
        Recibe una instancia de DocumentoDeuda, valida compatibilidad fiscal emisor/receptor,
        prepara el payload JSON, solicita el CAE vía WSFE (afip.py) y actualiza el modelo.
        """
        from apps.base.models import ConfiguracionEmpresa

        if not documento_deuda.tipo_comprobante_afip:
            raise ValueError(
                f"El documento {documento_deuda.numero} no tiene un Tipo de Comprobante AFIP."
            )

        if not documento_deuda.diario.es_facturacion_electronica:
            logger.info(
                f"El diario {documento_deuda.diario.codigo} opera bajo modalidad de gestión interna (no electrónico). Se omite conexión con AFIP."
            )
            return True

        if documento_deuda.afip_cae:
            logger.warning(
                f"El documento {documento_deuda.numero} ya posee un CAE activo."
            )
            return True

        # Validar compatibilidad de condiciones frente al IVA
        empresa = ConfiguracionEmpresa.get_solo()
        self.validar_compatibilidad_fiscal(
            emisor=empresa,
            receptor=documento_deuda.contacto,
            tipo_comprobante=documento_deuda.tipo_comprobante_afip,
        )

        # Determinar Punto de Venta
        if not documento_deuda.diario.punto_venta_afip:
            raise ValueError(
                f"El diario '{documento_deuda.diario.nombre}' no tiene Punto de Venta AFIP configurado."
            )

        pto_vta = documento_deuda.diario.punto_venta_afip
        tipo_cbte = int(documento_deuda.tipo_comprobante_afip.codigo)

        # Obtener el número del último comprobante para este punto de venta y tipo
        try:
            last_voucher = self.afip.ElectronicBilling.getLastVoucher(
                pto_vta, tipo_cbte
            )
            next_voucher = last_voucher + 1
        except Exception as e:
            logger.error(f"No se pudo obtener el último comprobante: {e}")
            raise

        # Construcción del payload nativo para afip.py
        cuit_dest = str(documento_deuda.contacto.cuit or "").replace("-", "").strip() if hasattr(documento_deuda.contacto, 'cuit') else ""
        payload = {
            "CantReg": 1,
            "PtoVta": pto_vta,
            "CbteTipo": tipo_cbte,
            "DocTipo": 80 if len(cuit_dest) == 11 else 99,
            "DocNro": int(cuit_dest) if cuit_dest.isdigit() else 0,
            "CbteDesde": next_voucher,
            "CbteHasta": next_voucher,
            "CbteFch": int(documento_deuda.fecha_emision.strftime("%Y%m%d")),
            "ImpTotal": float(documento_deuda.monto_total),
            "ImpTotConc": 0.0,
            "ImpNeto": float(documento_deuda.monto_neto),
            "ImpOpEx": 0.0,
            "ImpTrib": 0.0,
            "ImpIVA": float(documento_deuda.monto_impuestos),
            "FchServDesde": None,
            "FchServHasta": None,
            "FchVtoPago": int(documento_deuda.fecha_vencimiento.strftime("%Y%m%d"))
            if documento_deuda.fecha_vencimiento
            else None,
            "MonId": documento_deuda.moneda.afip_codigo
            if documento_deuda.moneda
            else "PES",
            "MonCotiz": float(documento_deuda.tasa_cambio)
            if documento_deuda.moneda
            else 1.0,
        }

        # Manejo de Comprobantes Asociados (Obligatorio en Notas de Crédito y Débito)
        clasif = getattr(documento_deuda.tipo_comprobante_afip, "clasificacion_interna", "")
        if clasif in ["nota_credito", "nota_debito"] or "nota_credito" in documento_deuda.tipo or "nota_debito" in documento_deuda.tipo:
            if not documento_deuda.comprobante_asociado:
                raise ValueError(
                    f"Inconsistencia fiscal: La {documento_deuda.get_tipo_display()} {documento_deuda.numero} "
                    f"exige un comprobante original asociado (campo 'comprobante_asociado') para autorizarse en AFIP."
                )

            comp_orig = documento_deuda.comprobante_asociado
            if not comp_orig.tipo_comprobante_afip:
                raise ValueError(
                    f"El comprobante asociado {comp_orig.numero} no posee un tipo de comprobante fiscal AFIP válido."
                )

            pto_asoc, nro_asoc = comp_orig.desglosar_punto_venta_y_numero()
            tipo_asoc = int(comp_orig.tipo_comprobante_afip.codigo)
            cuit_emisor_num = int(str(empresa.cuit).replace("-", "").strip() or "0")

            payload["CbtesAsoc"] = [
                {
                    "Tipo": tipo_asoc,
                    "PtoVta": pto_asoc,
                    "Nro": nro_asoc,
                    "Cuit": cuit_emisor_num,
                }
            ]

        # Manejo de Factura de Crédito Electrónica MiPyME (FCE - Ley 27.440)
        if documento_deuda.tipo_comprobante_afip.es_mipyme_fce:
            if not documento_deuda.fecha_vencimiento:
                raise ValueError(
                    f"La Factura de Crédito MiPyME {documento_deuda.numero} exige fecha de vencimiento de pago obligatoria."
                )

            cbu = documento_deuda.cbu_emisor
            if not cbu:
                raise ValueError(
                    f"La Factura de Crédito MiPyME {documento_deuda.numero} exige CBU del emisor (Opcional AFIP 2101)."
                )

            payload["Opcionales"] = [
                {
                    "Id": 2101,  # CBU del emisor
                    "Valor": str(cbu).strip(),
                },
                {
                    "Id": 27,    # Sistema de Circulación (SCA = Sistema de Circulación Abierta, ADC = Agente de Depósito Colectivo)
                    "Valor": documento_deuda.fce_sistema_circulacion or "SCA",
                },
            ]

        # Manejo dinámico de IVA
        if documento_deuda.monto_impuestos > 0:
            iva_dict = {}
            for linea in documento_deuda.lineas.all():
                if (
                    linea.impuesto
                    and linea.impuesto.tipo == "iva"
                    and linea.impuesto.afip_id
                ):
                    afip_id = linea.impuesto.afip_id
                    if afip_id not in iva_dict:
                        iva_dict[afip_id] = {"BaseImp": 0.0, "Importe": 0.0}
                    iva_dict[afip_id]["BaseImp"] += float(linea.subtotal)
                    importe_iva = float(linea.subtotal) * (
                        float(linea.impuesto.alicuota) / 100.0
                    )
                    iva_dict[afip_id]["Importe"] += importe_iva

            if iva_dict:
                payload["Iva"] = [
                    {
                        "Id": k,
                        "BaseImp": round(v["BaseImp"], 2),
                        "Importe": round(v["Importe"], 2),
                    }
                    for k, v in iva_dict.items()
                ]

        # Manejo de Tributos, Percepciones y Retenciones (ImpTrib y array Tributos)
        tributos_qs = documento_deuda.tributos.all()
        if tributos_qs.exists() or documento_deuda.monto_tributos > 0:
            trib_list = []
            imp_trib_total = 0.0
            for trib in tributos_qs:
                imp = float(trib.importe)
                imp_trib_total += imp
                trib_list.append({
                    "Id": trib.afip_tributo_id,
                    "Desc": trib.descripcion,
                    "BaseImp": float(trib.base_imponible),
                    "Alic": float(trib.alicuota),
                    "Importe": imp,
                })

            if trib_list:
                payload["Tributos"] = trib_list
                payload["ImpTrib"] = round(imp_trib_total, 2)
            elif documento_deuda.monto_tributos > 0:
                payload["ImpTrib"] = float(documento_deuda.monto_tributos)

        logger.info(f"Autorizando comprobante {next_voucher}...")

        try:
            # Ejecutar el request SOAP envuelto en REST vía afip.py
            res = self.afip.ElectronicBilling.createVoucher(payload)

            res_cae = res["CAE"]
            res_vencimiento = res["CAEFchVto"]  # Formato YYYYMMDD

            # Convertir YYYYMMDD a fecha para Django
            fecha_vto_cae = datetime.strptime(res_vencimiento, "%Y%m%d").date()

            # Guardar en base de datos
            documento_deuda.afip_cae = res_cae
            documento_deuda.afip_vencimiento_cae = fecha_vto_cae
            documento_deuda.numero = (
                f"{pto_vta:04d}-{next_voucher:08d}"  # Formatear ej. 0001-00000005
            )
            documento_deuda.estado = "publicado"
            documento_deuda.save(
                update_fields=["afip_cae", "afip_vencimiento_cae", "numero", "estado"]
            )

            # Generar Asiento Contable
            try:
                ContabilizacionDocumentoService.contabilizar_factura(documento_deuda)
            except Exception as accounting_error:
                logger.error(
                    f"Error contabilizando comprobante {documento_deuda.numero}: {accounting_error}"
                )

            logger.info(
                f"CAE Autorizado: {res_cae}. Comprobante Número: {documento_deuda.numero}"
            )
            return True

        except Exception as e:
            logger.error(f"AFIP rechazó el comprobante: {str(e)}")
            raise e
