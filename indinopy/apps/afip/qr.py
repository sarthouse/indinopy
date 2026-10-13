import base64
import json
import urllib.parse
from io import BytesIO


class AFIPQRGenerator:
    """
    Genera el código QR oficial de AFIP según Resolución General 4291/2018.
    Construye la URL https://www.afip.gob.ar/fe/qr/?p=BASE64(JSON) y la convierte
    en una imagen PNG codificada en base64 Data URI lista para incrustar en HTML.
    """

    AFIP_QR_URL = "https://www.afip.gob.ar/fe/qr/?p="

    @classmethod
    def construir_url_afip(
        cls,
        fecha: str,
        cuit_emisor: int,
        punto_venta: int,
        tipo_comprobante: int,
        numero_comprobante: int,
        importe_total: float,
        moneda: str,
        cotizacion: float,
        tipo_doc_receptor: int,
        nro_doc_receptor: int,
        tipo_codigo_autorizacion: str,
        codigo_autorizacion: int,
    ) -> str:
        """
        Construye la URL con el payload JSON en Base64 según especificación RG 4291.
        """
        payload = {
            "ver": 1,
            "fecha": fecha,
            "cuit": int(cuit_emisor),
            "ptoVta": int(punto_venta),
            "tipoCmp": int(tipo_comprobante),
            "nroCmp": int(numero_comprobante),
            "importe": float(importe_total),
            "moneda": str(moneda),
            "ctz": float(cotizacion),
            "tipoDocRec": int(tipo_doc_receptor),
            "nroDocRec": int(nro_doc_receptor),
            "tipoCodAut": str(tipo_codigo_autorizacion),
            "codAut": int(codigo_autorizacion),
        }
        json_str = json.dumps(payload, separators=(",", ":"))
        encoded = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
        return f"{cls.AFIP_QR_URL}{encoded}"

    @classmethod
    def generar_qr_data_uri(cls, url: str) -> str:
        """
        Genera el QR como Data URI en formato base64: 'data:image/png;base64,...'
        Utiliza qrcode si está disponible; de lo contrario genera un placeholder SVG/PNG.
        """
        try:
            import qrcode

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=6,
                border=1,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buffer = BytesIO()
            img.save(buffer, format="PNG")
            b64_img = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return f"data:image/png;base64,{b64_img}"
        except Exception:
            # Fallback a un SVG minimalista codificado en data URI si qrcode no está instalado
            svg_dummy = (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 120 120">'
                f'<rect width="120" height="120" fill="#f0f0f0" stroke="#000" stroke-width="2"/>'
                f'<text x="60" y="55" font-size="11" text-anchor="middle" font-family="sans-serif">QR AFIP</text>'
                f'<text x="60" y="75" font-size="9" text-anchor="middle" font-family="sans-serif">RG 4291</text>'
                f'</svg>'
            )
            b64_svg = base64.b64encode(svg_dummy.encode("utf-8")).decode("utf-8")
            return f"data:image/svg+xml;base64,{b64_svg}"
