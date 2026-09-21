from decimal import Decimal
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class LineaOrdenDTO:
    sku: str
    cantidad: Decimal
    precio_unitario: Decimal
    descuento: Decimal = Decimal("0.00")
    nombre_producto: str = ""
    id_linea_externo: Optional[str] = None


@dataclass
class RecargoDTO:
    nombre: str
    monto: Decimal
    impuesto: Decimal = Decimal("0.00")


@dataclass
class CuponDTO:
    codigo: str
    monto_descuento: Decimal


@dataclass
class ClienteDTO:
    nombre: str
    email: str
    cuit: Optional[str] = None
    telefono: str = ""
    direccion: str = ""
    ciudad: str = ""
    provincia: str = ""
    codigo_postal: str = ""
    condicion_iva: str = "consumidor_final"


@dataclass
class OrdenVentaDTO:
    """
    DTO Canónico universal e independiente de cualquier canal externo.
    Representa una orden proveniente de cualquier ecommerce (WooCommerce, Shopify, Tiendanube),
    marketplace (MercadoLibre), POS o sistema B2B.
    """
    referencia_externa: str
    numero_externo: str
    estado_canal_externo: str
    cliente: ClienteDTO
    lineas: List[LineaOrdenDTO] = field(default_factory=list)
    recargos: List[RecargoDTO] = field(default_factory=list)
    cupones: List[CuponDTO] = field(default_factory=list)
    
    monto_total: Decimal = Decimal("0.00")
    total_descuentos: Decimal = Decimal("0.00")
    total_envio: Decimal = Decimal("0.00")
    total_impuestos: Decimal = Decimal("0.00")
    
    metodo_envio_titulo: str = ""
    metodo_envio_id: str = ""
    metodo_pago: str = ""
    transaccion_id: str = ""
    
    datos_adicionales_meta: Dict[str, Any] = field(default_factory=dict)
