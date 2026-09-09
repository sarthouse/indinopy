🎯 Visión, Diagnóstico & Arquitectura de Software

# Explicación Técnica del Proyecto: Cómo Indinopy Resuelve la Crisis Productiva

> **Tesis Central:** El problema del calzado y la manufactura en el Conurbano no es la falta de capacidad técnica ni de demanda de mano de obra. Es una **falla estructural de arquitectura institucional y financiera**: la banca tradicional solo presta contra inmuebles, el fisco ahoga al que produce con costos fijos, y las marcas financian su capital de trabajo postergando los pagos de los talleres más débiles. **Indinopy** es el sistema de gestión libre (ERP/MES) que formaliza, colateraliza y gobierna la cadena en el territorio.

## 1. ¿Qué Buscamos? (Los 5 Objetivos Estratégicos)

### 💵 1. Transformar el Trabajo en Dinero Líquido
Superar la "trampa de Stiglitz". Un aparador o costurero no tiene una casa para hipotecar. La **e-OP (Orden de Producción Electrónica)** se transforma en un título de crédito fiduciario negociable ante el Banco Provincia y el Fideicomiso FDI, dando liquidez sin pedir garantías patrimoniales.

### ⚡ 2. El Hito Cero: Nadie Enciende un Motor sin Cobrar
Erradicar la práctica de entregar materiales y esperar 60 o 90 días para cobrar la confección. Al firmarse la e-OP y despacharse el cuero, el sistema libera un **anticipo automático del 30% al 40% (o 50% con Sello de Buen Diseño)** para solventar costos operativos inmediatos.

### 🛡️ 3. Blindaje Legal de Insumos (Inembargabilidad)
Bajo el régimen de Maquila y Locación de Obra (Arts. 1251 y 1356 CCCN), se formaliza la disociación patrimonial: el cuero es de la marca y el taller es depositario. Los insumos son **estrictamente inembargables** ante quiebras o litigios particulares de cualquiera de las partes.

### ⏱️ 4. Silencio Administrativo Positivo (48 Horas)
Neutralizar la parálisis burocrática y política. Si la Comisión de Crédito de la Mesa de Enlace (MES) no emite una objeción técnica fundada en 48 horas hábiles, el contrato inteligente gatilla automáticamente la convalidación por omisión y libera los fondos.

### 🔍 5. Transparencia Radical ante el Consumidor
Mediante un código QR inviolable en la lengüeta del calzado, el consumidor final escanea y ve con exactitud matemática el desglose de cada peso: cuánto cobró el taller de barrio, cuánto costaron los insumos nacionales, cuánto retuvo el fisco y cuánto la marca.

### 🛑 6. Suspensión Activa de Oficio (Cero Deuda Fija)
Si un taller deja de recibir órdenes por 15 días corridos, el sistema muta su estado a "Suspensión Activa". Su carga impositiva cae automáticamente a \$0 y no devenga deuda previsional ni intereses retroactivos por parálisis fabril involuntaria.

## 2. Cuadro Comparativo: Sistema Tradicional vs. Protocolo Indinopy

| Dimensión | Sistema Tradicional / Banca Comercial | Protocolo Indinopy ERP/MES + RIGI Conurbano |
|---|---|---|
| **Garantía Exigida** | `Patrimonial` (Inmuebles, rodados, avales de terceros) | `Flujo Productivo` (e-OP colateralizada con insumos en custodia) |
| **Plazo de Cobro Taller** | `60 a 90 días` (Diferido arbitrario por la marca) | `Inmediato` (Hito 0 al 30-40% + Avances contra pares certificados) |
| **Riesgo de Parálisis** | `Burocracia discrecional` (Cajoneo de expedientes) | `Timelock 48h` (Silencio Administrativo Positivo por sistema) |
| **Seguridad Jurídica** | `Embargos cruzados` (Juicios laborales o comerciales traban stock) | `Inembargabilidad CCCN` (Activo de afectación productiva territorial) |
| **Régimen Fiscal** | `Cuota fija destructiva` (Monotributo acumula deuda sin producir) | `Suspensión Activa` (Si no hay máquina en marcha, el impuesto es \$0) |
| **Fijación de Precios** | `Dumping y precarización` (La marca impone precios de miseria) | `Pisos Éticos Paritarios` (Alertas automáticas por debajo de convenio) |

## 3. ¿Cómo lo Resuelve Indinopy Técnicamente? (Módulos de Software)

**Indinopy** no es una empresa de calzado ni una marca comercial: es una **suite ERP/MES de código abierto** desarrollada en Python y Django, diseñada para operar en el territorio fabril. Cada problema del diagnóstico está mapeado a un módulo de ingeniería de software concreto:

### A. Módulo Producción `apps.produccion`
*   **Tupla e-OP Inmutable:** Modela la Orden de Producción como un activo financiero completo: `OP = <UUID, ClaveComitente, ClaveTaller, MerkleBOM, CurvaTalles, VectorCostos, Hitos, RegimenLegal, Multifirma>`.
*   **Receta Técnica y Tolerancias INTI:** Árbol de Merkle determinista que fija las cantidades teóricas de cuero, suela y adhesivo con hasta un 10% de tolerancia técnica de merma auditada por el INTI.
*   **Partes de Producción:** Registro en tiempo real de lotes y pares terminados en cada etapa física (corte, rebajado, aparado, armado) que disparan los pagos en tesorería.

### B. Módulo Tesorería y Escrow Digital `apps.tesoreria`
*   **Máquina de Estados Finita:** Los fondos depositados por el comitente quedan bloqueados en una cuenta de custodia (*Escrow*) del Fideicomiso de Desarrollo Industrial (FDI) y se desbloquean paso a paso:
    <br>`BORRADOR → COLATERALIZADA (2% FDI) → HITO0_UNLOCKED (30-40%) → EN_PROCESO → LIQUIDADA`.
*   **Algoritmo de Timelock:** Temporizador regresivo que monitorea las 48 horas hábiles. Si la Comisión de Crédito de la MES no carga un dictamen formal de rechazo, el sistema emite automáticamente la firma de liberación.
*   **Partición Factorial de Pagos:** Al liquidar una etapa, el sistema fragmenta automáticamente la transferencia en cuentas separadas: mano de obra directa para el taller, aportes sindicales y reserva de garantía FDI (2%).

### C. Módulo Contactos y Bolsa de Trabajo `apps.contactos`
*   **Perfil Tallerista y Capacidad Instalada:** Registra la dotación de operarios, máquinas disponibles y capacidad teórica semanal en pares de calzado.
*   **Prevención de Cuellos de Botella:** Si al asignarle una nueva OP a un tallerista su ocupación supera el 100% para la fecha de entrega, el sistema alerta y sugiere fragmentar el lote en un taller secundario de la Bolsa Distrital.
*   **Auditoría Algorética de Tarifas:** Compara el valor pactado por par con la tabla oficial de precios mínimos paritarios de la MES; si está por debajo del piso de convenio, bloquea la homologación automática.

### D. Módulo Inventario y Partida Doble `apps.inventario`
*   **Disociación de Dominio:** Sistema de inventario por partida doble que diferencia con precisión jurídica entre *Propietario* (Comitente) y *Custodio* (Tallerista).
*   **Remitos de Traslado de Maquila:** Emisión de comprobantes digitales de movimiento de cuero y avíos con código QR y leyenda legal expresa de los Arts. 1251 y 1356 del Código Civil y Comercial de la Nación.

### E. Vista Pública de Trazabilidad Socioproductiva `/t/<uuid>/`
*   **Endpoint Público sin Login:** Interfaz móvil ultra-liviana a la que accede el consumidor final al escanear la etiqueta del calzado.
*   **Gráfico Dinámico de Participación:** Desglosa el 100% del precio de góndola en: mano de obra territorial del Conurbano, cuero y materias primas nacionales, carga fiscal neta y margen comercial.

## 4. Los 5 Dispositivos de Trinchera del RIGI del Conurbano

Más allá de la emisión de la e-OP, el proyecto institucionaliza cinco dispositivos operativos de base territorial diseñados para extirpar la informalidad forzosa, desarmar la extorsión burocrática y garantizar la soberanía tecnológica de la manufactura:

### 4.1. El Puente de Transición y la Cuenta de IVA Sectorial Diferida
**🌉 De la Identidad Prestada a la Sociedad por Acciones Simplificada (SAS)**

**El Diagnóstico del Purgatorio Fiscal:** Ante la imposibilidad de asumir los costos fijos y la complejidad del régimen general, el tallerista o diseñador recurre al préstamo de CUITs de familiares o empleados. Esto destruye su patrimonio personal ante contingencias y priva a la marca de computar costos reales en Ganancias e IVA.

**El Puente SAS de Neutralización Patrimonial:** El sistema crea un circuito de reconversión gratuita y de oficio en la Ventanilla Única Municipal. La SAS escinde de forma inmediata las herramientas y el hogar del trabajador de los pasivos fiscales de la unidad productiva.
*   **Doble Escala Anti-Fraude:** Para los *Prestadores Eventuales Individuales* (aparadores a destajo), el Monotributo Productivo de oficio tiene tope en la Categoría A. Para *Unidades Productivas Consolidadas (SAS)* de hasta 30 operarios, rige el límite de la Ley MiPyME para absorber nóminas formales.
*   **Cuenta de IVA Sectorial Diferida:** El IVA de la e-OP no se devenga mensualmente en abstracto: se retiene y liquida automáticamente por API en el milisegundo en que la Cuenta Custodia del FDI hace el clearing efectivo. Si la marca comitente no paga la orden, el tallerista jamás devenga la obligación fiscal.
*   **Crédito Fiscal Presunto del 25%:** Las SAS pueden computar una deducción presunta de hasta el 25% del valor de la e-OP en Ganancias e IVA en concepto de mano de obra en transición territorial, corrigiendo de raíz la pérdida histórica de crédito fiscal.
*   **Asesoría Contable y Administrativa Gratuita en CIFO:** Para que el tallerista no afronte costos de gestores ni contadores privados ($60.000-$100.000/mes), el CIFO de su distrito asume gratis el patrocinio contable y la carga de oficio, vinculando las e-OP y liquidando el IVA diferido.

### 4.2. Tutelaje Administrativo, Inmunidad de 180 Días y Canal Tuitivo de Denuncias
**🛡️ Blindaje Territorial frente a la Extorsión Burocrática y Comercial**

El tallerista de barrio no confía en un folleto estatal; teme que registrarse sea la puerta de entrada a la coima o la inspección extorsiva. El régimen implementa un blindaje tuitivo de trinchera:
*   **Ventanilla Única Municipal en 48 Horas:** Al registrarse la primera e-OP, el Municipio emite de oficio la Habilitación Simplificada del taller y la Exención de Tasas Locales (Seguridad e Higiene, Abasto) por 10 años.
*   **El Promotor Territorial (PTF) como Tutor:** Un par del propio oficio con 12 meses en el régimen y honorario equivalente a 2 SMVM financiado por el FDI guía al tallerista, labra el *Dictamen de Transición Asistida* y lo tutela en sus primeras 3 e-OP.
*   **Canal de Denuncias Criptográfico y Buzón Lacrado:** Terminales descentralizadas e independientes de la Agencia de Recaudación (ARCA) para denunciar aprietes, coimas o imposición de precios de miseria.
*   **Inmunidad Fiscal Temporaria de 180 Días:** La radicación formal de una denuncia suspende de pleno derecho toda inspección presencial o ejecución fiscal sobre el taller por 180 días hábiles prorrogables.
*   **Orden de Restricción Administrativa ("Perimetral al Inspector"):** Si un funcionario público pide dádivas, el sistema suspende preventivamente su usuario informático y la justicia le prohíbe el ingreso al cuadrante productivo del taller denunciante.
*   **Solidaridad de Distrito:** Si una seccional fiscal acumula más de 3 denuncias firmes en un año, se congelan los fondos de incentivo salarial ("cuenta de jerarquización") de toda esa delegación.

### 4.3. Red de Centros CIFO y Banco Comunitario de Maquinarias
**⚙️ Capital Físico Comunitario y Rescate de Bienes de Capital Fuera de Circuito**

**Red CIFO (Centros de Innovación y Formación de Oficios):** Espacios de formación técnica y seguridad ciudadana preventiva financiados con una asignación específica del **3% de los recursos del FDI local**:
*   **Acceso Popular sin Prerrequisitos:** Queda prohibida la exigencia del título secundario. El único requisito de ingreso es la voluntad de trabajo productivo.
*   **Trípode Institucional:** Conducción paritaria entre el Gremio (maestros de oficio), las Cámaras/Diseñadores (demanda real de trabajo) y el INTI/Municipio (certificación oficial y comodato edilicio).
*   **Beca Productiva y Reparto de Renta:** Los estudiantes perciben una beca mensual y se distribuyen el **50% de la renta neta de los Lotes Escuela** terminados con Sello de Buen Diseño (SBD). Egresan con alta de oficio y Prioridad 1 en la Bolsa de Trabajo.
*   **Área de Asesoría Contable, Fiscal y Administrativa Comunitaria:** Cada CIFO aloja una ventanilla técnica contable gratuita financiada por el FDI que gestiona la constitución de la SAS en 48h, emite facturas electrónicas vía API de ARCA, administra la Cuenta de IVA Diferida, arma el legajo para computar la deducción especial presunta del 35% por costos no documentados y liquida haberes bajo CCT con el subsidio del 27% patronal del fondo fiduciario.

**Banco Comunitario de Maquinarias y Bienes de Capital:** Moviliza activos ociosos en galpones cerrados:
*   **Condonación de Pasivos Preexistentes de ARCA:** Los titulares de maquinaria pesada parada que la cedan en comodato por 36 meses a la Red CIFO o talleres SAS acceden a la extinción total de sus deudas tributarias anteriores.
*   **Puesta a Punto por Alumnos Avanzados e INTI:** Las máquinas son calibradas en las aulas del CIFO como práctica profesional.
*   **Asignación con Opción a Transferencia Definitiva:** Se entregan en comodato productivo a los egresados Prioridad 1 o talleres con 3 e-OP cumplidas, erradicando el scoring patrimonial bancario.
*   **Muletto Técnico en 24 Horas y Seguro de Parálisis:** Ante la rotura imprevista de una máquina crítica, el Banco provee un reemplazo en 24h y el FDI liquida una compensación diaria por lucro cesante a los costureros.

### 4.4. IA Algorética y Conducción Tecnológica Soberana
**🤖 La Técnica Subordinada al Hombre (Doctrina Magnifica Humanitas)**

Recogiendo los principios de la **Encíclica Magnifica Humanitas** y el magisterio social de S.S. Francisco, la Inteligencia Artificial se incorpora al protocolo no como un mecanismo de reemplazo o descarte humano, sino como una herramienta de **Planificación Algorética para la Justicia Distributiva**:
*   **Monitoreo de Precios Justos y Auditoría Predictiva:** El algoritmo analiza las e-OP cargadas y cruza en tiempo real los costos de insumos indexados con los pisos paritarios de rama. Si una marca pretende pagar mano de obra por debajo de convenio, el sistema emite una alerta automática al Sindicato y frena la homologación express.
*   **Asistente en Lenguaje Natural para el PTF:** Aplicación móvil con IA que dialoga por voz con el tallerista informal en el lenguaje llano de su taller, guiándolo paso a paso para formalizarse y calcular sus costos reales sin lidiar con jerga contable.
*   **Detección de Talleres Espejo (Anti-Colusión):** Auditoría continua de metadatos de georreferenciación satelital, direcciones IP y tiempos de producción para detectar patrones donde una gran fábrica se fragmenta artificialmente en prestadores individuales ficticios para eludir el convenio colectivo.
*   **Supremacía de la Conducción Humana:** Queda prohibido por ley que una IA dicte sanciones, exclusiones o bajas automáticas. La IA es puramente consultiva; la soberanía reside de forma indelegable en los representantes humanos de la MES.
*   **Soberanía Tecnológica y Código Abierto:** Plataforma desarrollada con Universidades Públicas del Conurbano y pymes de software bajo licencias de código abierto (Open Source), alojada en servidores y centros de cómputo nacionales.

### 4.5. Arancel Cero para Bienes de Capital y Régimen de Tecnología Conveniente
**🏭 Actualización Tecnológica sin Destruir la Industria Metalúrgica Local**

El Artículo 22 de la Ley de Salvataje Nacional consagra el **arancel cero, IVA aduanero 0% y tasas portuarias 0%** para la importación de maquinaria industrial moderna, pero subordinado al principio de **Tecnología Conveniente** tutelado por el INTI:
*   **Principio de No Competencia:** El beneficio aplica exclusivamente a bienes de capital que no posean sustituto nacional de fabricación local.
*   **Los 3 Criterios Objetivos de Exclusión (INTI):** La importación con arancel cero solo procede si la oferta nacional incumple al menos una de estas condiciones:
    <br>1. *Plazo de Entrega:* El fabricante local no entrega en $\le 90$ días corridos.
    <br>2. *Garantía Técnica:* El proveedor local no ofrece cobertura mínima de 12 meses.
    <br>3. *Precio:* El bien nacional supera en más del 30% el valor CIF del bien importado puesto en planta.
*   **Silencio Administrativo Positivo Aduanero en 15 Días:** El perito del INTI tiene un plazo improrrogable de 15 días hábiles para dictaminar. Vencido el plazo sin pronunciamiento, el certificado aduanero de liberación se emite de forma automática.
*   **Encadenamiento Forzoso con Pymes Metalúrgicas Locales:** Las marcas extranjeras deben licenciar el servicio técnico, transferir planos de despiece y proveer repuestos a talleres electromecánicos y centros CIFO del territorio, dinamizando el empleo calificado local.
*   **Inmovilización Patrimonial de 5 Años:** La maquinaria importada no puede ser revendida ni transferida por un lustro, asegurando su afectación exclusiva a la producción real de los talleres del régimen.

## 5. Síntesis de Impacto Territorial

El RIGI del gran capital ofrece estabilidad fiscal a 30 años a multinacionales extractivas que exportan riqueza en bruto sin agregar valor. El **RIGI del Conurbano** y el software **Indinopy** construyen exactamente lo opuesto:
*   Rescatan la **capacidad manufacturera instalada** en los barrios industriales de San Martín, La Matanza, Lanús y Tres de Febrero.
*   Permiten que las pymes de diseño produzcan en el país con costos transparentes y entregas a tiempo.
*   Devuelven la **dignidad salarial al tallerista**, erradicando el trabajo precarizado mediante crédito al trabajo vivo y no a la especulación.

---
Documento de Especificación Estratégica · Sistema de Gestión **Indinopy ERP/MES** para la Mesa de Enlace Sectorial (MES).
