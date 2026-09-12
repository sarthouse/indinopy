import requests
from django.conf import settings
from apps.base.models import ConfiguracionEmpresa

class FederacionCreditoService:
    """
    Servicio cliente para consumir las APIs del Nodo Central (MES).
    """
    
    @staticmethod
    def consultar_cupo_mes():
        """
        Consulta en tiempo real (Pull) el estado del crédito y la mora
        al servidor de la MES.
        """
        empresa = ConfiguracionEmpresa.objects.first()
        if not empresa:
            raise ValueError("No hay una ConfiguracionEmpresa definida en este nodo.")
        
        mi_cuit = empresa.cuit
        
        # En producción, esta URL vendría de settings. NODO_MES_URL
        mes_url = getattr(settings, 'NODO_MES_URL', 'http://localhost:8000')
        endpoint = f"{mes_url}/mes/api/v1/fdi/estado-credito/"
        
        try:
            # Petición HTTP al nodo MES. Se inyecta el CUIT propio en los headers
            respuesta = requests.get(
                endpoint,
                headers={"X-CUIT": mi_cuit},
                timeout=5
            )
            
            if respuesta.status_code == 200:
                return respuesta.json()
            elif respuesta.status_code == 404:
                raise ValueError("La MES informa que tu empresa no tiene una línea de crédito asignada.")
            else:
                raise ValueError(f"Error de red comunicándose con la MES: {respuesta.status_code}")
                
        except requests.RequestException as e:
            raise ValueError(f"El Nodo MES no está disponible: {str(e)}")
