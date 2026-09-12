from decimal import Decimal
from django.db import transaction
from .models import ConceptoLiquidacion, LiquidacionNomina, DetalleLiquidacion

class NominaService:
    @staticmethod
    def _get_or_create_concepto(codigo, defaults):
        concepto, _ = ConceptoLiquidacion.objects.get_or_create(
            codigo=codigo, defaults=defaults
        )
        return concepto

    @staticmethod
    @transaction.atomic
    def generar_conceptos_base():
        """
        Crea los conceptos estándar de liquidación laboral argentina (2024-2026).
        """
        conceptos = [
            # Haberes
            ('SUELDO', 'Sueldo Básico', 'REMUNERATIVO', None, True),
            ('PLUS_VAC', 'Plus Vacacional', 'REMUNERATIVO', None, True),
            ('PRESENTISMO', 'Adicional Presentismo', 'REMUNERATIVO', Decimal('8.33'), True),
            ('ANTIGUEDAD', 'Adicional Antigüedad', 'REMUNERATIVO', Decimal('1.00'), True),
            
            # Retenciones (A cargo del empleado) - Suman 17%
            ('JUBILACION', 'Jubilación (SIPA)', 'RETENCION', Decimal('11.00'), False),
            ('OBRA_SOC', 'Obra Social', 'RETENCION', Decimal('3.00'), False),
            ('LEY_19032', 'INSSJP (Ley 19.032)', 'RETENCION', Decimal('3.00'), False),
            ('SINDICATO', 'Cuota Sindical', 'RETENCION', Decimal('2.00'), False), # Depende del CCT
            
            # Cargas Patronales (Costo empresa PyME)
            ('PAT_JUB', 'Contribución SIPA/FNE (PyME)', 'CONTRIBUCION', Decimal('18.00'), False),
            ('PAT_OBRAS', 'Contribución Obra Social', 'CONTRIBUCION', Decimal('6.00'), False),
            
            # Reformas Ley Bases
            ('FONDO_CESE', 'Aporte Fondo Cese Laboral', 'CONTRIBUCION', Decimal('8.00'), False),
        ]

        for cod, desc, tipo, pct, aporta in conceptos:
            NominaService._get_or_create_concepto(
                codigo=cod,
                defaults={
                    'descripcion': desc,
                    'tipo': tipo,
                    'porcentaje': pct,
                    'base_jubilacion': aporta,
                    'base_obra_social': aporta,
                }
            )

    @staticmethod
    @transaction.atomic
    def liquidar_mes(empleado, mes, anio, dias_trabajados=30, dias_vacaciones=0, dias_licencia=0):
        """
        Motor de liquidación mensual básico.
        """
        sueldo_basico = empleado.sueldo_basico
        
        liquidacion = LiquidacionNomina.objects.create(
            empleado=empleado,
            periodo_mes=mes,
            periodo_anio=anio,
            dias_trabajados=dias_trabajados,
            dias_vacaciones=dias_vacaciones,
            dias_licencia=dias_licencia,
        )

        total_rem = Decimal('0.00')
        total_no_rem = Decimal('0.00')
        total_ret = Decimal('0.00')
        total_patronal = Decimal('0.00')

        # 1. SUELDO NORMAL
        if dias_trabajados > 0:
            conc_sueldo = ConceptoLiquidacion.objects.get(codigo='SUELDO')
            monto_sueldo = round((sueldo_basico / 30) * dias_trabajados, 2)
            DetalleLiquidacion.objects.create(
                liquidacion=liquidacion, concepto=conc_sueldo, cantidad=dias_trabajados,
                monto_unitario=round(sueldo_basico/30, 2), subtotal=monto_sueldo
            )
            total_rem += monto_sueldo

        # 2. VACACIONES (Divisor 25 en vez de 30 = Plus Vacacional)
        if dias_vacaciones > 0:
            conc_vac = ConceptoLiquidacion.objects.get(codigo='PLUS_VAC')
            monto_vacaciones = round((sueldo_basico / 25) * dias_vacaciones, 2)
            DetalleLiquidacion.objects.create(
                liquidacion=liquidacion, concepto=conc_vac, cantidad=dias_vacaciones,
                monto_unitario=round(sueldo_basico/25, 2), subtotal=monto_vacaciones
            )
            total_rem += monto_vacaciones

        # 3. PRESENTISMO
        if dias_trabajados + dias_vacaciones + dias_licencia >= 30:
            conc_pres = ConceptoLiquidacion.objects.get(codigo='PRESENTISMO')
            monto_pres = round(total_rem * (conc_pres.porcentaje / 100), 2)
            DetalleLiquidacion.objects.create(
                liquidacion=liquidacion, concepto=conc_pres, cantidad=conc_pres.porcentaje,
                monto_unitario=total_rem, subtotal=monto_pres
            )
            total_rem += monto_pres

        # 4. RETENCIONES (17% clásico)
        retenciones_codigos = ['JUBILACION', 'OBRA_SOC', 'LEY_19032']
        if empleado.afiliado_sindicato:
            retenciones_codigos.append('SINDICATO')

        for cod in retenciones_codigos:
            conc_ret = ConceptoLiquidacion.objects.get(codigo=cod)
            pct = conc_ret.porcentaje
            if cod == 'SINDICATO' and empleado.sindicato:
                pct = empleado.sindicato.cuota_sindical_pct

            monto_ret = round(total_rem * (pct / 100), 2)
            DetalleLiquidacion.objects.create(
                liquidacion=liquidacion, concepto=conc_ret, cantidad=pct,
                monto_unitario=total_rem, subtotal=monto_ret
            )
            total_ret += monto_ret

        # 5. CARGAS PATRONALES (PyME 18% + 6%)
        for cod in ['PAT_JUB', 'PAT_OBRAS']:
            conc_pat = ConceptoLiquidacion.objects.get(codigo=cod)
            monto_pat = round(total_rem * (conc_pat.porcentaje / 100), 2)
            DetalleLiquidacion.objects.create(
                liquidacion=liquidacion, concepto=conc_pat, cantidad=conc_pat.porcentaje,
                monto_unitario=total_rem, subtotal=monto_pat
            )
            total_patronal += monto_pat

        # 6. LEY BASES: FONDO DE CESE LABORAL
        if empleado.adherido_fondo_cese:
            conc_cese = ConceptoLiquidacion.objects.get(codigo='FONDO_CESE')
            monto_cese = round(total_rem * (conc_cese.porcentaje / 100), 2)
            DetalleLiquidacion.objects.create(
                liquidacion=liquidacion, concepto=conc_cese, cantidad=conc_cese.porcentaje,
                monto_unitario=total_rem, subtotal=monto_cese
            )
            total_patronal += monto_cese

        # 7. ART (Riesgos de Trabajo)
        from apps.base.models import ConfiguracionEmpresa
        config_empresa = ConfiguracionEmpresa.objects.first()
        if config_empresa and (config_empresa.art_porcentaje > 0 or config_empresa.art_fijo_por_empleado > 0):
            conc_art = NominaService._get_or_create_concepto(
                'PAT_ART', 
                {'descripcion': f'ART ({config_empresa.art_nombre or "Aseguradora"})', 'tipo': 'CONTRIBUCION'}
            )
            monto_art_var = round(total_rem * (config_empresa.art_porcentaje / 100), 2)
            monto_art_fijo = config_empresa.art_fijo_por_empleado
            monto_art_total = monto_art_var + monto_art_fijo
            
            DetalleLiquidacion.objects.create(
                liquidacion=liquidacion, concepto=conc_art, cantidad=1,
                monto_unitario=monto_art_total, subtotal=monto_art_total
            )
            total_patronal += monto_art_total

        # 8. GUARDAR TOTALES
        liquidacion.total_remunerativo = total_rem
        liquidacion.total_no_remunerativo = total_no_rem
        liquidacion.total_retenciones = total_ret
        liquidacion.sueldo_neto_pagar = total_rem + total_no_rem - total_ret
        liquidacion.total_cargas_patronales = total_patronal
        liquidacion.save()

        return liquidacion

    @staticmethod
    @transaction.atomic
    def solicitar_aprobacion_tesoreria(liquidacion):
        """Paso 1 (SoD): RRHH termina el cálculo y lo envía a Tesorería."""
        if liquidacion.estado != 'BORRADOR':
            raise ValueError("Solo se pueden solicitar aprobación desde BORRADOR.")
        
        liquidacion.estado = 'REVISION_TESORERIA'
        liquidacion.save(update_fields=['estado'])
        return liquidacion

    @staticmethod
    @transaction.atomic
    def aprobar_liquidacion_tesoreria(liquidacion, aprobador_user):
        """
        Paso 2 (SoD): Tesorería valida y firma.
        Aprueba la liquidación, genera el Asiento Contable (Partida Doble) y 
        crea la Orden de Pago en Tesorería.
        """
        from django.utils import timezone
        if liquidacion.estado != 'REVISION_TESORERIA':
            raise ValueError("La liquidación debe ser enviada a Tesorería por RRHH primero.")

        liquidacion.aprobador_tesoreria = aprobador_user

        from apps.contabilidad.services import ContabilidadService
        from apps.contabilidad.models import Diario, Cuenta
        from apps.tesoreria.models import ComprobanteTesoreria, Caja
        from apps.contactos.models import Contacto
        
        # 1. CONTABILIDAD: Crear Asiento por Partida Doble
        diario_sueldos, _ = Diario.objects.get_or_create(codigo='SUELDOS', defaults={'nombre': 'Diario de Sueldos', 'tipo': 'varios'})
        
        # (Cuentas contables hardcodeadas para el ejemplo, deberían venir del Plan de Cuentas)
        cuenta_gasto, _ = Cuenta.objects.get_or_create(codigo='4.1.01', defaults={'nombre': 'Sueldos y Jornales', 'tipo': 'resultado_negativo', 'naturaleza': 'deudora'})
        cuenta_gasto_pat, _ = Cuenta.objects.get_or_create(codigo='4.1.02', defaults={'nombre': 'Cargas Sociales Patronales', 'tipo': 'resultado_negativo', 'naturaleza': 'deudora'})
        cuenta_pasivo, _ = Cuenta.objects.get_or_create(codigo='2.1.01', defaults={'nombre': 'Sueldos a Pagar', 'tipo': 'pasivo', 'naturaleza': 'acreedora'})
        cuenta_cargas, _ = Cuenta.objects.get_or_create(codigo='2.1.02', defaults={'nombre': 'Cargas Sociales a Pagar', 'tipo': 'pasivo', 'naturaleza': 'acreedora'})
        
        # Regla de Oro: Debe = Haber
        lineas_asiento = [
            {'cuenta_codigo': cuenta_gasto.codigo, 'debe': liquidacion.sueldo_bruto, 'haber': 0},
            {'cuenta_codigo': cuenta_gasto_pat.codigo, 'debe': liquidacion.total_cargas_patronales, 'haber': 0},
            {'cuenta_codigo': cuenta_pasivo.codigo, 'debe': 0, 'haber': liquidacion.sueldo_neto_pagar},
            {'cuenta_codigo': cuenta_cargas.codigo, 'debe': 0, 'haber': liquidacion.total_retenciones + liquidacion.total_cargas_patronales},
        ]
        
        fecha_asiento = liquidacion.creado_en.date() if liquidacion.creado_en else timezone.now().date()
        
        asiento = ContabilidadService.crear_asiento(
            diario_codigo=diario_sueldos.codigo,
            fecha=fecha_asiento,
            descripcion=f"Devengamiento Liq. {liquidacion.get_tipo_liquidacion_display()} {liquidacion.periodo_mes}/{liquidacion.periodo_anio} - {liquidacion.empleado.cuil}",
            lineas_apuntes=lineas_asiento,
            documento_origen=liquidacion
        )
        
        # Validar matemáticamente y Asentar (Bloquear)
        ContabilidadService.validar_y_asentar(asiento.id)

        # 2. TESORERÍA: Crear la Orden de Pago (Borrador) para que Finanzas la cancele luego.
        # Asumimos que existe un contacto asociado al Empleado (creamos uno temporal si no existe)
        contacto_empleado, _ = Contacto.objects.get_or_create(
            cuit=liquidacion.empleado.cuil, 
            defaults={'nombre': liquidacion.empleado.nombre_completo, 'tipo': 'empleado'}
        )
        
        import uuid
        op_tesoreria = ComprobanteTesoreria.objects.create(
            numero=f"OP-SUELDO-{liquidacion.id}",
            tipo='orden_pago',
            contacto=contacto_empleado,
            fecha=fecha_asiento,
            uuid_identificador=uuid.uuid4()
        )
        
        # 3. Marcar Liquidación como APROBADA
        liquidacion.estado = 'APROBADA'
        liquidacion.save(update_fields=['estado', 'aprobador_tesoreria'])
        
        return liquidacion, asiento, op_tesoreria

    @staticmethod
    @transaction.atomic
    def liquidar_sac(empleado, anio, semestre):
        """
        Liquida el Sueldo Anual Complementario (Aguinaldo).
        semestre: 1 (Junio) o 2 (Diciembre)
        """
        mes_inicio = 1 if semestre == 1 else 7
        mes_fin = 6 if semestre == 1 else 12
        
        # Buscar la mejor remuneración del semestre
        liquidaciones_semestre = LiquidacionNomina.objects.filter(
            empleado=empleado,
            periodo_anio=anio,
            periodo_mes__gte=mes_inicio,
            periodo_mes__lte=mes_fin,
            tipo_liquidacion='M'
        )
        
        mejor_remuneracion = Decimal('0.00')
        dias_trabajados_semestre = 0
        
        for liq in liquidaciones_semestre:
            if liq.total_remunerativo > mejor_remuneracion:
                mejor_remuneracion = liq.total_remunerativo
            dias_trabajados_semestre += liq.dias_trabajados + liq.dias_vacaciones + liq.dias_licencia
            
        # Limitar a 180 días máximo por semestre
        dias_trabajados_semestre = min(dias_trabajados_semestre, 180)
        
        # Cálculo proporcional
        monto_sac = round((mejor_remuneracion / 2) * (Decimal(dias_trabajados_semestre) / Decimal(180)), 2)
        
        # Crear Cabecera
        liquidacion = LiquidacionNomina.objects.create(
            empleado=empleado,
            periodo_mes=mes_fin,
            periodo_anio=anio,
            tipo_liquidacion='S',
            dias_trabajados=0,
            dias_base_tope=0 # El SAC no prorratea tope mensual general
        )
        
        conc_sac = NominaService._get_or_create_concepto('SAC', {'descripcion': 'S.A.C. Proporcional', 'tipo': 'REMUNERATIVO'})
        DetalleLiquidacion.objects.create(
            liquidacion=liquidacion, concepto=conc_sac, cantidad=1,
            monto_unitario=monto_sac, subtotal=monto_sac
        )
        
        # Retenciones sobre el SAC (17% clásico)
        total_ret = Decimal('0.00')
        for cod in ['JUBILACION', 'OBRA_SOC', 'LEY_19032']:
            conc_ret = ConceptoLiquidacion.objects.get(codigo=cod)
            monto_ret = round(monto_sac * (conc_ret.porcentaje / 100), 2)
            DetalleLiquidacion.objects.create(
                liquidacion=liquidacion, concepto=conc_ret, cantidad=conc_ret.porcentaje,
                monto_unitario=monto_sac, subtotal=monto_ret
            )
            total_ret += monto_ret
            
        liquidacion.total_remunerativo = monto_sac
        liquidacion.total_retenciones = total_ret
        liquidacion.sueldo_neto_pagar = monto_sac - total_ret
        liquidacion.save()
        return liquidacion

    @staticmethod
    @transaction.atomic
    def liquidar_final(empleado, fecha_egreso, motivo='RENUNCIA'):
        """
        Liquidación Extraordinaria por egreso.
        motivos: RENUNCIA, DESPIDO_SIN_CAUSA, MUTUO_ACUERDO
        """
        import calendar
        
        mes = fecha_egreso.month
        anio = fecha_egreso.year
        dias_mes_calendario = calendar.monthrange(anio, mes)[1]
        dias_trabajados = fecha_egreso.day
        
        sueldo_basico = empleado.sueldo_basico
        mejor_sueldo = sueldo_basico # Simplificación. En la realidad se busca la mejor del último año.
        
        liquidacion = LiquidacionNomina.objects.create(
            empleado=empleado, periodo_mes=mes, periodo_anio=anio,
            tipo_liquidacion='E', dias_trabajados=dias_trabajados
        )
        
        total_rem = Decimal('0.00')
        total_norem = Decimal('0.00')
        
        # 1. Días trabajados del mes (Remunerativo)
        conc_dias = NominaService._get_or_create_concepto('DIAS_MES', {'descripcion': 'Días Trabajados Mes Egreso', 'tipo': 'REMUNERATIVO'})
        monto_dias = round((sueldo_basico / 30) * dias_trabajados, 2)
        DetalleLiquidacion.objects.create(liquidacion=liquidacion, concepto=conc_dias, cantidad=dias_trabajados, monto_unitario=round(sueldo_basico/30, 2), subtotal=monto_dias)
        total_rem += monto_dias
        
        # 2. SAC Proporcional (Remunerativo)
        dias_semestre = (fecha_egreso - fecha_egreso.replace(month=1 if mes <=6 else 7, day=1)).days + 1
        conc_sac = NominaService._get_or_create_concepto('SAC_PROP', {'descripcion': 'SAC Proporcional', 'tipo': 'REMUNERATIVO'})
        monto_sac = round((mejor_sueldo / 2) * (Decimal(dias_semestre) / Decimal(180)), 2)
        DetalleLiquidacion.objects.create(liquidacion=liquidacion, concepto=conc_sac, cantidad=1, monto_unitario=monto_sac, subtotal=monto_sac)
        total_rem += monto_sac
        
        # 3. Vacaciones No Gozadas + SAC s/ Vac. (No Remunerativos)
        # Asumimos 14 días base por antigüedad menor a 5 años como ejemplo.
        dias_vac_prop = round((14 / 365) * ((fecha_egreso.date() - empleado.fecha_ingreso).days % 365), 2)
        conc_vac_ng = NominaService._get_or_create_concepto('VAC_NO_GOZ', {'descripcion': 'Vacaciones No Gozadas', 'tipo': 'NO_REMUNERATIVO'})
        monto_vac_ng = round((sueldo_basico / 25) * Decimal(dias_vac_prop), 2)
        DetalleLiquidacion.objects.create(liquidacion=liquidacion, concepto=conc_vac_ng, cantidad=Decimal(dias_vac_prop), monto_unitario=round(sueldo_basico/25, 2), subtotal=monto_vac_ng)
        total_norem += monto_vac_ng
        
        conc_sac_vac = NominaService._get_or_create_concepto('SAC_VAC_NG', {'descripcion': 'SAC s/ Vac. No Gozadas', 'tipo': 'NO_REMUNERATIVO'})
        monto_sac_vac = round(monto_vac_ng / 12, 2)
        DetalleLiquidacion.objects.create(liquidacion=liquidacion, concepto=conc_sac_vac, cantidad=1, monto_unitario=monto_vac_ng, subtotal=monto_sac_vac)
        total_norem += monto_sac_vac
        
        # 4. Indemnizaciones (Solo si es despido y NO adhirió al Fondo de Cese de la Ley Bases)
        if motivo == 'DESPIDO_SIN_CAUSA' and not empleado.adherido_fondo_cese:
            antiguedad_anios = (fecha_egreso.date() - empleado.fecha_ingreso).days / 365
            anios_computables = int(antiguedad_anios) + (1 if (antiguedad_anios % 1) > 0.25 else 0)
            
            # Art. 245
            conc_245 = NominaService._get_or_create_concepto('IND_245', {'descripcion': 'Indemnización Antigüedad (Art 245)', 'tipo': 'NO_REMUNERATIVO'})
            monto_245 = mejor_sueldo * max(anios_computables, 1)
            DetalleLiquidacion.objects.create(liquidacion=liquidacion, concepto=conc_245, cantidad=max(anios_computables, 1), monto_unitario=mejor_sueldo, subtotal=monto_245)
            total_norem += monto_245
            
            # Integración Mes de Despido (si no despide el último día)
            if dias_trabajados < dias_mes_calendario:
                dias_integracion = dias_mes_calendario - dias_trabajados
                conc_integ = NominaService._get_or_create_concepto('INTEGRACION', {'descripcion': 'Integración Mes Despido', 'tipo': 'NO_REMUNERATIVO'})
                monto_integ = round((sueldo_basico / 30) * dias_integracion, 2)
                DetalleLiquidacion.objects.create(liquidacion=liquidacion, concepto=conc_integ, cantidad=dias_integracion, monto_unitario=round(sueldo_basico/30,2), subtotal=monto_integ)
                total_norem += monto_integ
                
        # Aplicar Retenciones SOLO sobre total_rem (17%)
        total_ret = Decimal('0.00')
        for cod in ['JUBILACION', 'OBRA_SOC', 'LEY_19032']:
            conc_ret = ConceptoLiquidacion.objects.get(codigo=cod)
            monto_ret = round(total_rem * (conc_ret.porcentaje / 100), 2)
            DetalleLiquidacion.objects.create(liquidacion=liquidacion, concepto=conc_ret, cantidad=conc_ret.porcentaje, monto_unitario=total_rem, subtotal=monto_ret)
            total_ret += monto_ret

        liquidacion.total_remunerativo = total_rem
        liquidacion.total_no_remunerativo = total_norem
        liquidacion.total_retenciones = total_ret
        liquidacion.sueldo_neto_pagar = total_rem + total_norem - total_ret
        liquidacion.save()
        
        # Marcar empleado como inactivo
        empleado.activo = False
        empleado.fecha_egreso = fecha_egreso.date()
        empleado.save(update_fields=['activo', 'fecha_egreso'])
        
        return liquidacion
