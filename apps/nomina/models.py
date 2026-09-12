from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.base.models import TimeStampedModel

class Sindicato(TimeStampedModel):
    """
    Convenios Colectivos de Trabajo (CCT)
    """
    nombre = models.CharField(max_length=200, verbose_name=_("Sindicato / Convenio"))
    codigo_cct = models.CharField(max_length=20, blank=True, verbose_name=_("N° CCT"))
    aporte_solidario_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), verbose_name=_("% Aporte Solidario"))
    cuota_sindical_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), verbose_name=_("% Cuota Sindical"))

    class Meta:
        verbose_name = _("Sindicato")
        verbose_name_plural = _("Sindicatos")

    def __str__(self):
        return f"{self.nombre} (CCT {self.codigo_cct})"


class Empleado(TimeStampedModel):
    """
    Legajo del empleado interno de la PyME / Comitente.
    """
    TIPO_CONTRATO = [
        ('INDETERMINADO', _('Tiempo Indeterminado')),
        ('PLAZO_FIJO', _('Plazo Fijo')),
        ('INDEPENDIENTE', _('Colaborador Independiente (Ley Bases)')),
    ]

    nombre_completo = models.CharField(max_length=255, verbose_name=_("Nombre completo"))
    cuil = models.CharField(max_length=13, unique=True, verbose_name=_("CUIL"))
    fecha_ingreso = models.DateField(verbose_name=_("Fecha de Ingreso"))
    
    # Ley Bases: Período de prueba dinámico
    meses_periodo_prueba = models.IntegerField(
        default=6, 
        verbose_name=_("Meses Periodo Prueba"),
        help_text=_("6 meses general. Por CCT puede ser 8 (empresas 6-100) o 12 (hasta 5 empleados).")
    )
    
    tipo_contrato = models.CharField(
        max_length=20, choices=TIPO_CONTRATO, default='INDETERMINADO', verbose_name=_("Tipo de Contrato")
    )
    sueldo_basico = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_("Sueldo Básico")
    )
    
    sindicato = models.ForeignKey(Sindicato, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("Sindicato / CCT"))
    afiliado_sindicato = models.BooleanField(default=False, verbose_name=_("¿Es afiliado? (Cuota Sindical)"))
    
    # Ley Bases: Fondo de Cese Laboral
    adherido_fondo_cese = models.BooleanField(
        default=False, 
        verbose_name=_("Adherido al Fondo de Cese Laboral"),
        help_text=_("Reemplaza la indemnización Art. 245 por un aporte mensual a una cuenta fiduciaria.")
    )

    activo = models.BooleanField(default=True, verbose_name=_("Empleado Activo"))
    fecha_egreso = models.DateField(null=True, blank=True, verbose_name=_("Fecha de Egreso"))
    
    # Generic relation to documents for contracts
    from django.contrib.contenttypes.fields import GenericRelation
    documentos_adjuntos = GenericRelation(
        "documentos.DocumentoAdjunto",
        content_type_field="content_type",
        object_id_field="object_id",
        related_query_name="empleado"
    )

    class Meta:
        verbose_name = _("Empleado (Legajo)")
        verbose_name_plural = _("Empleados (Legajos)")

    def __str__(self):
        return f"{self.nombre_completo} ({self.cuil})"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.adherido_fondo_cese:
            # Check if there is any document attached (must have been saved first)
            # In Django, we can't check related objects on unsaved instances easily in clean() 
            # without checking self.pk, but we can enforce it logically or via a flag.
            if self.pk and not self.documentos_adjuntos.exists():
                raise ValidationError({
                    'adherido_fondo_cese': _('Riesgo Legal: No se puede adherir al Fondo de Cese Laboral (Ley Bases) sin un contrato firmado adjunto en el legajo.')
                })


class Licencia(TimeStampedModel):
    """
    Registro de Vacaciones, Ausencias y Licencias.
    """
    TIPO_LICENCIA = [
        ('VACACIONES', _('Vacaciones Anuales')),
        ('ENFERMEDAD', _('Licencia por Enfermedad')),
        ('MATERNIDAD', _('Licencia por Maternidad')),
        ('INJUSTIFICADA', _('Ausencia Injustificada')),
        ('JUSTIFICADA', _('Ausencia Justificada (sin goce)')),
    ]

    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name="licencias")
    tipo = models.CharField(max_length=20, choices=TIPO_LICENCIA, verbose_name=_("Tipo de Novedad"))
    fecha_inicio = models.DateField(verbose_name=_("Fecha de Inicio"))
    fecha_fin = models.DateField(verbose_name=_("Fecha de Fin"))
    dias_habiles = models.IntegerField(default=1, verbose_name=_("Días Hábiles a computar"))
    observaciones = models.TextField(blank=True, verbose_name=_("Observaciones / Certificados"))

    class Meta:
        verbose_name = _("Novedad / Licencia")
        verbose_name_plural = _("Novedades y Licencias")

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.empleado.nombre_completo} ({self.dias_habiles} días)"


class ConceptoLiquidacion(TimeStampedModel):
    """
    Conceptos que arman el recibo de sueldo y las cargas sociales.
    """
    TIPO_CONCEPTO = [
        ('REMUNERATIVO', _('Remunerativo (Haberes)')),
        ('NO_REMUNERATIVO', _('No Remunerativo (Asignaciones / Viáticos)')),
        ('RETENCION', _('Retención (Descuentos de Ley)')),
        ('CONTRIBUCION', _('Contribución Patronal (Costo Empresa)')),
    ]

    codigo = models.CharField(max_length=10, unique=True, verbose_name=_("Código Interno"))
    codigo_afip = models.CharField(
        max_length=10, blank=True, null=True, 
        verbose_name=_("Código AFIP (LSD)"),
        help_text=_("Código oficial del diccionario de la AFIP para el Libro de Sueldos Digital.")
    )
    descripcion = models.CharField(max_length=255, verbose_name=_("Descripción"))
    tipo = models.CharField(max_length=20, choices=TIPO_CONCEPTO, verbose_name=_("Tipo de Concepto"))
    
    # Formulaciones fijas (puede sobreescribirse dinámicamente)
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name=_("Porcentaje Fijo (%)"))
    monto_fijo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name=_("Monto Fijo ($)"))
    
    # Banderas impositivas
    base_jubilacion = models.BooleanField(default=True, verbose_name=_("Aporta a Seguridad Social (SIPA, Ley 19032)"))
    base_obra_social = models.BooleanField(default=True, verbose_name=_("Aporta a Obra Social"))
    base_ganancias = models.BooleanField(default=True, verbose_name=_("Gravado Ganancias 4ta Cat."))
    base_sac = models.BooleanField(default=True, verbose_name=_("Se computa para Aguinaldo (SAC)"))
    
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Concepto de Liquidación")
        verbose_name_plural = _("Conceptos de Liquidación")

    def __str__(self):
        return f"{self.codigo} - {self.descripcion}"


class LiquidacionNomina(TimeStampedModel):
    """
    Cabecera del recibo de sueldo por empleado por periodo.
    Prepara los datos para el Registro 1 y Registro 2 del LSD (Libro Sueldos Digital).
    """
    TIPO_LIQUIDACION = [
        ('M', _('Mensual')),
        ('1Q', _('1ra Quincena')),
        ('2Q', _('2da Quincena')),
        ('S', _('SAC / Aguinaldo')),
        ('V', _('Vacaciones')),
        ('E', _('Extraordinaria / Liquidación Final')),
    ]

    ESTADO_LIQUIDACION = [
        ('BORRADOR', _('Borrador (Calculado por RRHH)')),
        ('REVISION_TESORERIA', _('Pendiente Firma Tesorería (SoD)')),
        ('APROBADA', _('Aprobada (Contabilizada y a Pagar)')),
        ('PAGADA', _('Pagada / Cerrada')),
        ('ANULADA', _('Anulada')),
    ]

    empleado = models.ForeignKey(Empleado, on_delete=models.RESTRICT, related_name="liquidaciones")
    aprobador_tesoreria = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name="liquidaciones_aprobadas", verbose_name=_("Firma Dual (Tesorería)"))
    periodo_mes = models.IntegerField(verbose_name=_("Mes (1-12)"))
    periodo_anio = models.IntegerField(verbose_name=_("Año"))
    
    tipo_liquidacion = models.CharField(
        max_length=2, choices=TIPO_LIQUIDACION, default='M', verbose_name=_("Tipo Liquidación AFIP")
    )
    estado = models.CharField(
        max_length=15, choices=ESTADO_LIQUIDACION, default='BORRADOR', verbose_name=_("Estado del Recibo")
    )
    numero_liquidacion = models.IntegerField(
        default=1, verbose_name=_("Número de liquidación"),
        help_text=_("Número secuencial dentro del mes (1 a 5)")
    )
    fecha_pago = models.DateField(null=True, blank=True, verbose_name=_("Fecha de Pago"))
    
    dias_trabajados = models.IntegerField(default=30, verbose_name=_("Días Trabajados"))
    dias_vacaciones = models.IntegerField(default=0, verbose_name=_("Días Vacaciones / Plus"))
    dias_licencia = models.IntegerField(default=0, verbose_name=_("Días Licencia"))
    
    # LSD Reg 2: Días para tope imponible
    dias_base_tope = models.IntegerField(
        default=30, verbose_name=_("Días base tope (LSD)"),
        help_text=_("Proporción para topes de aportes (usualmente 30, o 0 si no corresponde)")
    )
    
    # Totales del recibo
    total_remunerativo = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_no_remunerativo = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_retenciones = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    # Netos y costos patronales
    sueldo_neto_pagar = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_("Sueldo Neto de Bolsillo"))
    total_cargas_patronales = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_("Cargas Patronales (F931)"))
    
    # Integración
    comprobante_pago = models.ForeignKey(
        'tesoreria.ComprobanteTesoreria', 
        on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_("Orden de Pago vinculada")
    )

    class Meta:
        verbose_name = _("Liquidación de Nómina")
        verbose_name_plural = _("Liquidaciones de Nómina")
        unique_together = ('empleado', 'periodo_mes', 'periodo_anio')

    def __str__(self):
        return f"Liquidación {self.periodo_mes}/{self.periodo_anio} - {self.empleado.nombre_completo}"

    @property
    def sueldo_bruto(self):
        return self.total_remunerativo + self.total_no_remunerativo

    @property
    def costo_total_empresa(self):
        """El costo real laboral para el ERP (Bruto + Patronales)"""
        return self.sueldo_bruto + self.total_cargas_patronales


class DetalleLiquidacion(TimeStampedModel):
    """
    Renglones impresos en el recibo de sueldo y cargas patronales.
    """
    liquidacion = models.ForeignKey(LiquidacionNomina, on_delete=models.CASCADE, related_name="detalles")
    concepto = models.ForeignKey(ConceptoLiquidacion, on_delete=models.RESTRICT)
    
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'), verbose_name=_("Cantidad / Unidades"))
    monto_unitario = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Monto Base / Unitario"))
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Subtotal Renglón"))

    class Meta:
        verbose_name = _("Detalle de Liquidación")
        verbose_name_plural = _("Detalles de Liquidación")
        ordering = ['concepto__tipo', 'concepto__codigo']

    def __str__(self):
        return f"{self.concepto.descripcion}: ${self.subtotal}"
