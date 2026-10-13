from django.db import transaction
from apps.contactos.models import Contacto
from apps.ventas.dtos import ClienteDTO


class ContactosService:
    """
    Servicio de sincronización y normalización de contactos y clientes
    utilizado por los distintos canales comerciales.
    """

    @staticmethod
    @transaction.atomic
    def sincronizar_cliente_desde_dto(cliente_dto: ClienteDTO) -> Contacto:
        """
        Resuelve o crea un Contacto a partir de un ClienteDTO canónico.
        Prioridad de resolución:
        1. CUIT / CUIL si viene informado
        2. Email comercial
        3. Creación como nuevo Contacto tipo 'cliente'
        """
        cliente = None
        cuit = (cliente_dto.cuit or "").strip()
        email = (cliente_dto.email or "").strip()

        if cuit:
            cliente = Contacto.objects.filter(cuil=cuit).first()

        if not cliente and email:
            cliente = Contacto.objects.filter(email=email).first()

        defaults = {
            "nombre": cliente_dto.nombre[:200],
            "email": email,
            "telefono": cliente_dto.telefono[:50],
            "direccion": cliente_dto.direccion[:300],
            "ciudad": cliente_dto.ciudad[:100],
            "provincia": cliente_dto.provincia[:100],
            "codigo_postal": cliente_dto.codigo_postal[:20],
            "tipo": "cliente",
            "condicion_iva": cliente_dto.condicion_iva or "consumidor_final",
        }
        if cuit:
            defaults["cuil"] = cuit

        if not cliente:
            codigo = f"CLI-{cuit or email or 'WEB'}"[:20]
            # Asegurar código único
            base_cod = codigo
            counter = 1
            while Contacto.objects.filter(codigo=codigo).exists():
                codigo = f"{base_cod[:16]}-{counter}"
                counter += 1

            defaults["codigo"] = codigo
            cliente = Contacto.objects.create(**defaults)
        else:
            # Actualizar datos de contacto si cambiaron
            update_fields = []
            if not cliente.telefono and cliente_dto.telefono:
                cliente.telefono = cliente_dto.telefono[:50]
                update_fields.append("telefono")
            if not cliente.direccion and cliente_dto.direccion:
                cliente.direccion = cliente_dto.direccion[:300]
                update_fields.append("direccion")
            if not cliente.provincia and cliente_dto.provincia:
                cliente.provincia = cliente_dto.provincia[:100]
                update_fields.append("provincia")
            if cuit and not cliente.cuil:
                cliente.cuil = cuit
                update_fields.append("cuil")
            if update_fields:
                cliente.save(update_fields=update_fields)

        return cliente
