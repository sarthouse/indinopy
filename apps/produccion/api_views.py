from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import transaction
from .serializers import OrdenProduccionHeadlessSerializer
from .services import ProduccionService

class RecepcionHeadlessEOPView(APIView):
    """
    Endpoint para que un ERP externo (ej. SAP/Odoo de la Marca) 
    inyecte una e-OP cruda en Indinopy.
    
    Indinopy actuará como Gateway Criptográfico:
    1. Recibe el JSON y el BOM externo.
    2. Crea la e-OP internamente sin afectar el módulo de inventario local.
    3. Confirma la e-OP (firma el hash y reserva el Escrow).
    """
    
    # En producción esto debe usar un API Key específica o validación HMAC
    permission_classes = [permissions.AllowAny] 

    @transaction.atomic
    def post(self, request):
        serializer = OrdenProduccionHeadlessSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                # 1. Guardar la orden en borrador con su BOM externo
                op = serializer.save()
                
                # 2. Llamar al Service Layer para confirmar y sellar la OP
                # Como op.bom_headless tiene datos, el servicio va a omitir el descuento de stock.
                ProduccionService.confirmar_op(op)
                
                return Response({
                    "mensaje": "e-OP Headless creada y confirmada exitosamente.",
                    "op_numero": op.numero,
                    "op_uuid": op.uuid_identificador,
                    "estado_escrow": op.estado_escrow,
                    "hash_seguridad": op.hash_seguridad
                }, status=status.HTTP_201_CREATED)
                
            except Exception as e:
                # Si falla algo (ej. no hay fondos en la tesorería para el escrow), 
                # la transacción se revierte
                return Response({
                    "error": str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
                
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
