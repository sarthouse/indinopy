import logging
from typing import Optional
from apps.afip.padron import PadronAFIPService
from apps.afip.dtos import ContribuyentePadronDTO
from .models import Contacto, TipoDocumentoAFIP

logger = logging.getLogger(__name__)


class ContactosAFIPService:
    """
    Servicio de integración entre el modelo Contacto y los servicios de Padrón de AFIP.
    Permite autocompletar o actualizar los datos fiscales y domiciliarios de un contacto a partir de su CUIT/CUIL.
    """

    MAPEO_CONDICION_IVA = {
        "RESPONSABLE_INSCRIPTO": "responsable_inscripto",
        "RESPONSABLE_MONOTRIBUTO": "monotributista",
        "EXENTO": "exento",
        "CONSUMIDOR_FINAL": "consumidor_final",
    }

    @classmethod
    def consultar_y_enriquecer(cls, cuit: str) -> Optional[ContribuyentePadronDTO]:
        """
        Consulta el padrón de AFIP y retorna el DTO normalizado.
        """
        return PadronAFIPService.consultar_cuit(cuit)

    @classmethod
    def sincronizar_contacto_con_afip(cls, contacto: Contacto, cuit: Optional[str] = None) -> bool:
        """
        Actualiza los campos de un Contacto con los datos oficiales de AFIP.
        """
        cuit_a_consultar = cuit or contacto.cuil
        if not cuit_a_consultar:
            return False

        dto = cls.consultar_y_enriquecer(cuit_a_consultar)
        if not dto:
            return False

        # 1. Razón Social o Nombre
        if not contacto.nombre or contacto.nombre.startswith("CLI-"):
            contacto.nombre = dto.nombre_razon_social

        # 2. CUIL / CUIT y Tipo Documento
        contacto.cuil = dto.cuit
        tipo_cuit = TipoDocumentoAFIP.objects.filter(codigo="80").first()
        if tipo_cuit:
            contacto.tipo_documento = tipo_cuit

        # 3. Condición frente al IVA
        cond_iva_erp = cls.MAPEO_CONDICION_IVA.get(dto.condicion_iva, "consumidor_final")
        contacto.condicion_iva = cond_iva_erp

        # 4. Domicilio oficial si no tiene uno
        if not contacto.direccion and dto.direccion:
            contacto.direccion = dto.direccion
        if not contacto.ciudad and dto.localidad:
            contacto.ciudad = dto.localidad
        if not contacto.provincia and dto.provincia:
            contacto.provincia = dto.provincia
        if not contacto.codigo_postal and dto.codigo_postal:
            contacto.codigo_postal = dto.codigo_postal

        contacto.save()
        logger.info(f"Contacto {contacto.id} ({contacto.nombre}) enriquecido exitosamente con AFIP.")
        return True
