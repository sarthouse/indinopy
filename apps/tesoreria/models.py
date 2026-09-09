from django.db import models
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal
from apps.base.models import TimeStampedModel, DocumentoBase

class Caja(TimeStampedModel):
    """
    Representa una caja física, cuenta bancaria o pasarela de pago.
    """
    TIPO_CAJA_CHOICES = [
        ("efectivo", "Caja Efectivo"),
        ("banco", "Cuenta Bancaria"),
        ("tarjeta", "Tarjeta / Pasarela Digital"),
    ]
    nombre = models.CharField(max_length=100, verbose_name="Nombre de la Caja / Cuenta")
    tipo = models.CharField(max_length=20, choices=TIPO_CAJA_CHOICES, default="efectivo")
    moneda = models.ForeignKey("base.Moneda", on_delete=models.RESTRICT, verbose_name="Moneda")
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Caja / Cuenta"
        verbose_name_plural = "Cajas y Cuentas"
        ordering = ["tipo", "nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.moneda.codigo})"

    @property
    def saldo_actual(self):
        ingresos = self.movimientos.filter(estado="confirmado").aggregate(total=Sum('monto_ingreso'))['total'] or Decimal('0.00')
        egresos = self.movimientos.filter(estado="confirmado").aggregate(total=Sum('monto_egreso'))['total'] or Decimal('0.00')
        return ingresos - egresos


class ComprobanteTesoreria(DocumentoBase):
    """
    Documento maestro operativo: Recibo (Cobranza) u Orden de Pago.
    """
    TIPO_COMPROBANTE_CHOICES = [
        ("recibo", "Recibo (Cobranza a Cliente)"),
        ("orden_pago", "Orden de Pago (A Proveedor)"),
        ("transferencia", "Transferencia Interna (Entre cajas)"),
    ]
    tipo = models.CharField(max_length=20, choices=TIPO_COMPROBANTE_CHOICES, verbose_name="Tipo de Operación")
    contacto = models.ForeignKey(
        "contactos.Contacto", 
        on_delete=models.RESTRICT, 
        null=True, blank=True,
        verbose_name="Cliente / Proveedor"
    )
    
    class Meta:
        verbose_name = "Comprobante de Tesorería"
        verbose_name_plural = "Comprobantes de Tesorería"

    def __str__(self):
        return f"{self.get_tipo_display()} {self.numero}"

    @property
    def total_ingreso(self):
        return self.valores.aggregate(total=Sum('monto_ingreso'))['total'] or Decimal('0.00')

    @property
    def total_egreso(self):
        return self.valores.aggregate(total=Sum('monto_egreso'))['total'] or Decimal('0.00')


class MovimientoCaja(TimeStampedModel):
    """
    Línea de valor asociada a un comprobante. Representa la entrada o salida real de valores (Efectivo, Cheques, Retenciones).
    """
    TIPO_VALOR_CHOICES = [
        ("efectivo", "Efectivo"),
        ("transferencia", "Transferencia Bancaria"),
        ("cheque", "Cheque"),
        ("retencion", "Certificado de Retención"),
    ]
    comprobante = models.ForeignKey(ComprobanteTesoreria, on_delete=models.CASCADE, related_name="valores")
    caja = models.ForeignKey(Caja, on_delete=models.RESTRICT, related_name="movimientos")
    fecha = models.DateField(default=timezone.now)
    tipo_valor = models.CharField(max_length=20, choices=TIPO_VALOR_CHOICES, default="efectivo")
    
    monto_ingreso = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Ingreso")
    monto_egreso = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Egreso")
    
    # Referencias opcionales
    cheque = models.ForeignKey("Cheque", on_delete=models.SET_NULL, null=True, blank=True)
    impuesto = models.ForeignKey("contabilidad.Impuesto", on_delete=models.RESTRICT, null=True, blank=True, help_text="Si es una retención")
    estado = models.CharField(max_length=20, choices=DocumentoBase.ESTADO_CHOICES, default="borrador")

    class Meta:
        verbose_name = "Movimiento de Caja"
        verbose_name_plural = "Movimientos de Caja"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.caja.nombre} - {self.get_tipo_valor_display()}"
class Cheque(TimeStampedModel):
    """
    Gestión de Cheques (Terceros y Propios) - Típico en ERPs con localización argentina.
    """
    TIPO_CHEQUE_CHOICES = [
        ("tercero", "Cheque de Terceros"),
        ("propio", "Cheque Propio"),
    ]
    
    FORMATO_CHOICES = [
        ("fisico", "Físico (Papel)"),
        ("echeq", "E-Cheq (Electrónico)"),
    ]
    
    CATEGORIA_CHOICES = [
        ("comun", "Común (Al día)"),
        ("diferido", "Pago Diferido (CPD)"),
    ]

    ESTADO_CHOICES = [
        ("en_cartera", "En Cartera"),
        ("entregado", "Entregado a Proveedor"),
        ("depositado", "Depositado en Banco"),
        ("acreditado", "Acreditado / Debitado"),
        ("rechazado", "Rechazado"),
    ]

    tipo = models.CharField(max_length=20, choices=TIPO_CHEQUE_CHOICES, default="tercero", verbose_name="Origen")
    formato = models.CharField(max_length=20, choices=FORMATO_CHOICES, default="fisico", verbose_name="Formato")
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default="diferido", verbose_name="Categoría")
    numero = models.CharField(max_length=50, verbose_name="Número de Cheque")
    banco = models.CharField(max_length=100, verbose_name="Banco Emisor")
    monto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Monto")
    fecha_emision = models.DateField(default=timezone.now, verbose_name="Fecha de Emisión")
    fecha_pago = models.DateField(verbose_name="Fecha de Pago (Vencimiento)")
    
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="en_cartera", verbose_name="Estado")
    
    cuit_emisor = models.CharField(max_length=20, blank=True, verbose_name="CUIT Emisor")
    nombre_emisor = models.CharField(max_length=100, blank=True, verbose_name="Nombre Emisor")

    contacto_origen = models.ForeignKey(
        "contactos.Contacto", 
        on_delete=models.SET_NULL, 
        null=True, blank=True, 
        related_name="cheques_entregados",
        verbose_name="Recibido de (Cliente)"
    )
    contacto_destino = models.ForeignKey(
        "contactos.Contacto", 
        on_delete=models.SET_NULL, 
        null=True, blank=True, 
        related_name="cheques_recibidos",
        verbose_name="Entregado a (Proveedor)"
    )

    class Meta:
        verbose_name = "Cheque"
        verbose_name_plural = "Cheques"
        ordering = ["fecha_pago"]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.banco} #{self.numero} (${self.monto})"
