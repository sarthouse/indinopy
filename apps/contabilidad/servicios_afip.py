import logging
from django.conf import settings
from apps.base.models import ConfiguracionEmpresa
from afip import Afip

logger = logging.getLogger(__name__)


class FacturadorAFIP:
    """
    Adapter para integrar la facturación electrónica de AFIP mediante afip.py.
    Extrae la configuración global (CUIT, Certificados, Entorno) del modelo Singleton ConfiguracionEmpresa.
    """

    def __init__(self):
        # 1. Traer la configuración Single-Tenant
        self.config = ConfiguracionEmpresa.get_solo()

        if not self.config.afip_certificado or not self.config.afip_clave_privada:
            logger.warning(
                "Faltan certificados AFIP en la Configuración de Empresa. Las llamadas a AFIP fallarán."
            )

        # 2. Inicializar afip.py
        # afip.py requiere los paths a los archivos crt y key, y si es producción o no.
        # En Django, usamos el atributo `.path` de los FileFields para pasar la ruta absoluta.
        self.afip = Afip(
            {
                "CUIT": int(self.config.cuit.replace("-", "")),
                "cert": self.config.afip_certificado.path
                if self.config.afip_certificado
                else None,
                "key": self.config.afip_clave_privada.path
                if self.config.afip_clave_privada
                else None,
                "production": self.config.afip_entorno == "produccion",
            }
        )

    def emitir_comprobante(self, documento_deuda):
        """
        Recibe una instancia de DocumentoDeuda, prepara el payload JSON,
        solicita el CAE vía WSFE (afip.py) y actualiza el modelo.
        """

        if not documento_deuda.tipo_comprobante_afip:
            raise ValueError(
                f"El documento {documento_deuda.numero} no tiene un Tipo de Comprobante AFIP."
            )

        if not documento_deuda.tipo_comprobante_afip.es_electronico:
            logger.info("El comprobante no requiere autorización electrónica.")
            return True

        if documento_deuda.afip_cae:
            logger.warning(
                f"El documento {documento_deuda.numero} ya posee un CAE activo."
            )
            return True

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
        payload = {
            "CantReg": 1,
            "PtoVta": pto_vta,
            "CbteTipo": tipo_cbte,
            "DocTipo": 80 if len(documento_deuda.contacto.cuit) == 11 else 99,
            "DocNro": int(documento_deuda.contacto.cuit.replace("-", ""))
            if documento_deuda.contacto.cuit
            else 0,
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

        logger.info(f"Autorizando comprobante {next_voucher}...")

        try:
            # Ejecutar el request SOAP envuelto en REST vía afip.py
            res = self.afip.ElectronicBilling.createVoucher(payload)

            res_cae = res["CAE"]
            res_vencimiento = res["CAEFchVto"]  # Formato YYYYMMDD

            # Convertir YYYYMMDD a fecha para Django
            from datetime import datetime

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
            from apps.contabilidad.contabilizacion import ContabilizacionDocumentoService
            try:
                ContabilizacionDocumentoService.contabilizar_factura(documento_deuda)
            except Exception as accounting_error:
                logger.error(f"Error contabilizando comprobante {documento_deuda.numero}: {accounting_error}")

            logger.info(
                f"CAE Autorizado: {res_cae}. Comprobante Número: {documento_deuda.numero}"
            )
            return True

        except Exception as e:
            logger.error(f"AFIP rechazó el comprobante: {str(e)}")
            raise e
