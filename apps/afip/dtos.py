from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class ContribuyentePadronDTO:
    """
    Datos estructurados y normalizados obtenidos de la consulta al Padrón de AFIP (Alcance 10 / 13).
    """
    cuit: str
    nombre_razon_social: str
    tipo_persona: str  # 'FISICA' o 'JURIDICA'
    estado_clave: str  # 'ACTIVO', etc.
    condicion_iva: str  # 'RESPONSABLE_INSCRIPTO', 'RESPONSABLE_MONOTRIBUTO', 'EXENTO', 'CONSUMIDOR_FINAL'
    categoria_monotributo: Optional[str] = None
    es_monotributista: bool = False
    es_responsable_inscripto: bool = False
    es_exento: bool = False
    
    # Domicilio Fiscal
    direccion: str = ""
    localidad: str = ""
    provincia: str = ""
    codigo_postal: str = ""
    
    # Actividades e impuestos
    impuestos_activos: List[int] = field(default_factory=list)
    actividades: List[str] = field(default_factory=list)
    
    # Payload original por si se requiere auditar
    raw_data: dict = field(default_factory=dict)
