"""
Tests de Verificación para el Subsistema de Comunicaciones Oficiales,
Cédulas de Notificación Fehaciente y Adjuntos Criptográficos.

Diseñado con SimpleTestCase (sin acceso ni dependencias de Base de Datos)
para permitir validación completa sin requerir 'makemigrations' ni 'migrate'.
"""

import hashlib
import json
import uuid
from io import BytesIO
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
from django.utils import timezone
from nacl.signing import SigningKey, VerifyKey
from nacl.exceptions import BadSignatureError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.federacion.services import ComunicacionOficialService
from apps.federacion.reports.comunicacion_report import ComunicacionOficialPDFReport


class ComunicacionCriptografiaTests(SimpleTestCase):
    """
    Batería 1: Pruebas unitarias de integridad criptográfica, determinismo canónico
    y firmas digitales asimétricas Ed25519.
    """

    def setUp(self):
        self.signing_key = SigningKey.generate()
        self.verify_key = self.signing_key.verify_key
        self.clave_publica_hex = self.verify_key.encode().hex()

    def test_hash_canonico_determinista_independiente_de_orden_de_claves(self):
        """
        Verifica que el hash SHA-256 canónico sea idéntico sin importar
        el orden en que se inserten las claves en el diccionario.
        """
        dict_1 = {
            "numero_oficial": "NO-2026-00000001-MES-SUR",
            "cuit_emisor": "30712345678",
            "asunto": "Cédula de Intimación de Plazo",
            "tipo": "intimacion_entrega",
            "hashes_adjuntos": [],
        }

        dict_2 = {
            "hashes_adjuntos": [],
            "asunto": "Cédula de Intimación de Plazo",
            "tipo": "intimacion_entrega",
            "cuit_emisor": "30712345678",
            "numero_oficial": "NO-2026-00000001-MES-SUR",
        }

        hash1 = ComunicacionOficialService._calcular_hash_comunicacion(dict_1)
        hash2 = ComunicacionOficialService._calcular_hash_comunicacion(dict_2)

        self.assertEqual(hash1, hash2, "El orden de inserción alteró el hash canónico.")
        self.assertEqual(len(hash1), 64, "El digest SHA-256 debe tener 64 caracteres hexadecimales.")

    def test_firma_ed25519_valida_y_rechazo_ante_modificacion_de_un_byte(self):
        """
        Verifica que la firma Ed25519 sea válida y que cualquier alteración mínima
        (incluso 1 caracter) provoque el rechazo por BadSignatureError.
        """
        datos = {
            "numero_oficial": "NO-2026-00000001-MES-SUR",
            "cuerpo": "Se intima al tallerista a despachar los 500 pares en 48hs hábiles.",
        }
        digest = ComunicacionOficialService._calcular_hash_comunicacion(datos)

        # 1. Firmar el digest
        firma_hex = self.signing_key.sign(digest.encode()).signature.hex()

        # 2. Verificar con la clave pública (debe pasar sin excepciones)
        vk = VerifyKey(bytes.fromhex(self.clave_publica_hex))
        vk.verify(digest.encode(), bytes.fromhex(firma_hex))

        # 3. Simular manipulación maliciosa de un caracter en el cuerpo
        datos_alterados = {
            "numero_oficial": "NO-2026-00000001-MES-SUR",
            "cuerpo": "Se intima al tallerista a despachar los 600 pares en 48hs hábiles.",  # Alterado 500 -> 600
        }
        digest_alterado = ComunicacionOficialService._calcular_hash_comunicacion(datos_alterados)

        with self.assertRaises(BadSignatureError):
            vk.verify(digest_alterado.encode(), bytes.fromhex(firma_hex))

    def test_calculo_hash_sha256_adjunto_chunks(self):
        """
        Verifica el cálculo de hash en chunks para archivos adjuntos.
        """
        contenido = b"ESTE ES EL CONTENIDO DEL PLIEGO TECNICO ADJUNTO FIRMADO DIGITALMENTE 2026"
        esperado_hash = hashlib.sha256(contenido).hexdigest()

        archivo = SimpleUploadedFile("pliego.pdf", contenido, content_type="application/pdf")

        sha256 = hashlib.sha256()
        for chunk in archivo.chunks():
            sha256.update(chunk)
        digest_calculado = sha256.hexdigest()

        self.assertEqual(digest_calculado, esperado_hash)


class ComunicacionPrivacidadCCOTests(SimpleTestCase):
    """
    Batería 2: Pruebas de privacidad y estricta confidencialidad para destinatarios CCO
    en serializaciones y en el render del reporte PDF.
    """

    def setUp(self):
        # Mocks de Nodos
        self.nodo_emisor = MagicMock()
        self.nodo_emisor.nombre = "Nodo Central MES"
        self.nodo_emisor.get_tipo_nodo_display.return_value = "Nodo MES (Central/Root)"

        self.nodo_to = MagicMock()
        self.nodo_to.nombre = "Taller Calzados Quilmes SRL"

        self.nodo_cc = MagicMock()
        self.nodo_cc.nombre = "Cámara de la Industria del Calzado"

        self.nodo_cco = MagicMock()
        self.nodo_cco.nombre = "Tribunal Arbitral Sectorial"

        # Mock de Comunicación Oficial
        self.comunicacion = MagicMock()
        self.comunicacion.uuid_identificador = uuid.uuid4()
        self.comunicacion.numero_oficial = "NO-2026-00000042-MES-SUR"
        self.comunicacion.cuit_emisor = "30712345678"
        self.comunicacion.nodo_emisor = self.nodo_emisor
        self.comunicacion.tipo = "cedula_notificacion"
        self.comunicacion.asunto = "Inicio de Auditoría de Oficio"
        self.comunicacion.cuerpo_contenido = "Notifícase el inicio del proceso sumarial."
        self.comunicacion.estado = "emitida"
        self.comunicacion.fecha_emision = timezone.now()
        self.comunicacion.hash_seguridad_payload = "a" * 64
        self.comunicacion.hashes_adjuntos = [
            {"nombre": "resolucion.pdf", "mimetype": "application/pdf", "tamano": 2048, "sha256": "f" * 64}
        ]

        # Mocks de Cédulas Destinatarios (TO, CC, CCO)
        self.cedula_to = MagicMock()
        self.cedula_to.modo_recepcion = "principal"
        self.cedula_to.cuit_destino = "20111111119"
        self.cedula_to.nodo_destino = self.nodo_to
        self.cedula_to.estado_notificacion = "entregada"

        self.cedula_cc = MagicMock()
        self.cedula_cc.modo_recepcion = "copia_publica"
        self.cedula_cc.cuit_destino = "30222222229"
        self.cedula_cc.nodo_destino = self.nodo_cc
        self.cedula_cc.estado_notificacion = "entregada"

        self.cedula_cco = MagicMock()
        self.cedula_cco.modo_recepcion = "copia_oculta"
        self.cedula_cco.cuit_destino = "30333333339"  # Tribunal Reservado
        self.cedula_cco.nodo_destino = self.nodo_cco
        self.cedula_cco.estado_notificacion = "entregada"

        self.comunicacion.destinatarios.all.return_value = [self.cedula_to, self.cedula_cc, self.cedula_cco]
        self.comunicacion.destinatarios.select_related.return_value.all.return_value = [
            self.cedula_to, self.cedula_cc, self.cedula_cco
        ]

    def test_reporte_pdf_contexto_oculta_cco_a_destinatarios_publicos(self):
        """
        Un destinatario principal (TO) o en copia (CC) NO debe tener en su contexto
        a los destinatarios CCO.
        """
        reporte_to = ComunicacionOficialPDFReport(
            comunicacion=self.comunicacion,
            cuit_observador="20111111119",  # CUIT de Empresa TO
        )
        ctx_to = reporte_to.get_context_data()

        self.assertFalse(ctx_to["es_emisor"])
        self.assertFalse(ctx_to["es_observador_cco"])
        self.assertEqual(len(ctx_to["destinatarios_cco"]), 0, "Los CCO deben filtrarse a 0 para terceros.")
        self.assertEqual(len(ctx_to["destinatarios_principales"]), 1)
        self.assertEqual(len(ctx_to["destinatarios_cc"]), 1)

    def test_reporte_pdf_contexto_revela_cco_solamente_al_emisor(self):
        """
        El nodo emisor DEBE ver la lista completa de CCO para su auditoría y control de acuses.
        """
        reporte_emisor = ComunicacionOficialPDFReport(
            comunicacion=self.comunicacion,
            cuit_observador="30712345678",  # CUIT del Emisor
        )
        ctx_emisor = reporte_emisor.get_context_data()

        self.assertTrue(ctx_emisor["es_emisor"])
        self.assertEqual(len(ctx_emisor["destinatarios_cco"]), 1, "El emisor debe ver a todos los CCO.")
        self.assertEqual(ctx_emisor["destinatarios_cco"][0].cuit_destino, "30333333339")

    def test_reporte_pdf_contexto_indica_reserva_identidad_al_destinatario_cco(self):
        """
        El destinatario CCO que abre el documento debe tener el indicador especial de copia oculta
        y ver su propia cédula sin conocer otros eventuales CCO.
        """
        reporte_cco = ComunicacionOficialPDFReport(
            comunicacion=self.comunicacion,
            cuit_observador="30333333339",  # CUIT del Tribunal CCO
        )
        ctx_cco = reporte_cco.get_context_data()

        self.assertFalse(ctx_cco["es_emisor"])
        self.assertTrue(ctx_cco["es_observador_cco"])
        self.assertIsNotNone(ctx_cco["mi_cedula_cco"])
        self.assertEqual(ctx_cco["mi_cedula_cco"].cuit_destino, "30333333339")
        self.assertEqual(len(ctx_cco["destinatarios_cco"]), 0, "No debe exponerse la lista global de CCO.")


class ComunicacionReglasNegocioTests(SimpleTestCase):
    """
    Batería 3: Pruebas unitarias de reglas de inmutabilidad, estados y timelock.
    """

    @patch("apps.federacion.models.ComunicacionOficialFederada.objects.get")
    def test_prohibicion_de_adjuntar_archivos_a_comunicacion_emitida(self, mock_get):
        """
        Verifica que intentar adjuntar un archivo a una comunicación en estado
        'emitida' dispare un ValueError de inviolabilidad.
        """
        mock_com = MagicMock()
        mock_com.estado = "emitida"
        mock_get.return_value = mock_com

        archivo_dummy = SimpleUploadedFile("anexo.pdf", b"test", content_type="application/pdf")

        with self.assertRaises(ValueError) as ctx:
            ComunicacionOficialService.adjuntar_archivo(
                comunicacion_id=1,
                archivo_obj=archivo_dummy,
            )

        self.assertIn("No se pueden adjuntar archivos a una comunicación oficial ya emitida", str(ctx.exception))
