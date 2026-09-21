"""
Adaptador de compatibilidad regresiva para FacturadorAFIP.
La implementación canónica fue desacoplada hacia `apps.afip.facturacion`.
"""

from apps.afip.facturacion import FacturadorAFIP

__all__ = ["FacturadorAFIP"]

