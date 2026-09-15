<span class="doc-header-badge">📖 Glosario</span>
# Glosario de Conceptos del Proyecto: Indinopy, Protocolo e-OP y Gobernanza FIMCA
### *Guía Taxonómica de Términos Legales, Criptográficos, Técnicos, Financieros y Operativos*

**Sistema de Gestión Indinopy ERP/MES · Mesa de Enlace Sectorial (MES Federal / Nodo Conurbano)**

---

Este glosario documenta y define en profundidad cada uno de los conceptos, siglas, fórmulas, procedimientos e instituciones presentes en la arquitectura de **Indinopy ERP/MES**, el modelo de orden de producción (**`modelo_orden_produccion.html`**), el protocolo de la **Orden de Producción Electrónica (e-OP)** y el marco normativo **FIMCA**.

## Introducción al Ecosistema y Marco Taxonómico

El presente glosario constituye el cuerpo conceptual unificado de **Indinopy ERP/MES** y el marco de gobernanza **FIMCA** (*Formalización e Incentivo a la Manufactura del Calzado Argentino*). Su propósito es tender un puente de lenguaje común entre mundos que históricamente han operado desconectados: la ingeniería de software distribuido, la criptografía aplicada, el derecho civil y laboral argentino, la física de la transformación del cuero y la economía política del trabajo territorial.

La arquitectura del proyecto se sostiene sobre cuatro pilares vertebrales cuyos términos se detallan a lo largo de este documento:

1. **Sustitución de Discrecionalidad por Auditoría Criptográfica e Institucional:** La relación entre marcas comitentes y talleres no depende de expedientes analógicos ni de la discrecionalidad estatal. A través de primitivas criptográficas deterministas (hashing SHA-256 de payloads canónicos, árboles de Merkle para recetas BOM y firmas asimétricas Ed25519 en hardware seguro), el sistema garantiza la inmutabilidad de los compromisos y la trazabilidad de los costos sin vulnerar secretos industriales.
2. **La e-OP como Activo Financiero y Colateral:** La Orden de Producción Electrónica deja de ser una simple planilla de fábrica para constituirse en un título ejecutivo de crédito fiduciario. Su convalidación institucional en la Mesa de Enlace Sectorial (MES) habilita el fondeo inmediato del **Hito Cero** (anticipo del 35% al 40% del capital de trabajo) mediante el Fideicomiso de Desarrollo Industrial (FDI), desintermediando el crédito usurario y protegiendo el poder adquisitivo del tallerista mediante la indexación en Unidades de Cuenta Industrial (UCI).
3. **Auditoría Territorial y Prueba de Trabajo Productivo (PoPW):** Para evitar fraudes informáticos o aprobaciones de escritorio, el protocolo exige la verificación física y presencial en el taller. La figura del Promotor Territorial de Formalización (PTF) —un par del propio oficio— constata los lotes mediante geocercado satelital (PostGIS < 150m) y biometría RENAPER, activando la liquidación inmediata de hitos en cuentas inembargables del Banco Provincia (BAPRO).
4. **Descompresión Fiscal y Blindaje Jurídico:** El régimen desarma el "purgatorio fiscal" que condena a los talleristas a la informalidad. Mediante la figura del Monotributo Productivo con micro-retención automática en clearing (1.5%), la Cláusula de No Retroactividad, la Cuenta de IVA Sectorial Diferida y el Crédito Fiscal Presunto del 25%, el sistema permite a las marcas deducir el 100% de sus costos de mano de obra en Ganancias e IVA sin asfixiar la liquidez del tallerista de base, blindando a su vez las materias primas contra embargos bajo el régimen de Locación de Obra (CCCN 1251) y Custodia (CCCN 1356).

---

### Índice Rápido de Secciones

| Eje Temático | Secciones y Contenido Principal |
| :--- | :--- |
| **Institución y Reglas** | [1. Metadatos del Sistema](#sec-1) (Indinopy, e-OP, MES, FDI, Timelock, Silencio Positivo, Modalidad Operativa Fabril, Addenda)<br/>[2. Criptografía y Trazabilidad](#sec-2) (UUID, Merkle BOM, Ed25519, Multisig, QR, PoPW, Geo-Fencing, mTLS, CRL, IA Algorética, Zero-Retention)<br/>[3. Actores y Velo Societario](#sec-3) (Marca, UBO, Tallerista, PTF, Score Solidario, Bolsa de Trabajo, Maestros Artesanos, Talleres Espejo, Ventanilla Única) |
| **Física Productiva** | [4. Técnica del Calzado y BOM](#sec-4) (BOM, Curva de Talles, Horma INTI, SBD, Mermas, Cuero Flor, Cordura, Puntera IRAM, Adhesivos)<br/>[5. Tracking Físico y Partes](#sec-5) (Parte de Producción, Liquidación Desacoplada, Etapas 1 a 4 de Corte a Empaque) |
| **Finanzas y Marco Legal** | [6. Arquitectura Escrow y UCI](#sec-6) (Escrow, Hito Cero, Hitos de Avance, Hito Final, UCI, Micro-canon MES, Fondo de Riesgo, UCP, AML/KYC/ROS)<br/>[7. Desglose Factorial de Costos](#sec-7) (Costo Industrial Fabril, Mano de Obra Territorial, Margen Comercial, P.V.P.)<br/>[8. Tutela Sindical y Arbitraje](#sec-8) (Veto Ex-Post, Alerta de Escrow, Fianza Líquida, Tribunal Arbitral, Slashing, Hard Ban, Canal de Denuncias)<br/>[9. Régimen Fiscal y Previsional](#sec-9) (Locación de Obra vs Compraventa, Inembargabilidad CCCN 1251/1356, Monotributo Productivo 1.5%, Suspensión Activa, Ganancias, Aportes Patronales, No Retroactividad, IVA Diferido, Crédito Presunto 25%, Puente SAS, Tarifa Plana, Control Interno RG 1415) |
| **Infraestructura y Cumplimiento** | [10. Resiliencia de Software y Operaciones](#sec-10) (Dead-Letter Queue, Idempotencia, Topología Offline-First)<br/>[11. Tabla Rápida de Siglas y Acrónimos](#sec-11) (Guía alfabética de acrónimos técnicos, legales y tributarios) |

---

## <a id="sec-1"></a>1. Identificación del Sistema y Metadatos Institucionales

### **Indinopy ERP/MES**
Plataforma de software libre (bajo licencia abierta) diseñada específicamente para la planificación de recursos empresariales (**ERP - Enterprise Resource Planning**) y la ejecución de manufactura en planta (**MES - Manufacturing Execution System**) en cadenas de valor de calzado, confección y marroquinería. **No es una empresa fabricante ni una marca comercial**, sino la infraestructura técnica digital que procesa las órdenes, audita los stocks por partida doble y gestiona la interacción con la Mesa de Enlace Sectorial.

### **Orden de Producción Electrónica (e-OP)**
Primitiva digital que transforma la orden de fabricación tradicional en un **título de afectación productiva, colateral crediticio fiduciario e instrumento de pago en custodia (*Escrow*)**. No es un simple comprobante interno; al ser convalidada por la MES, adquiere fuerza ejecutiva crediticia ante el Fondo Fiduciario (FDI) y valor probatorio de gasto computable ante las autoridades fiscales.

### **Mesa de Enlace Sectorial (MES Federal y Local)**
Órgano colegiado de gobernanza policéntrica paritaria integrado por 7 sillas representativas de la cadena: (1) Cámaras de Marcas Comitentes; (2) Cámaras de Fabricantes Integrados; (3) Talleres Consolidados (SAS/Cooperativas); (4) Talleres Individuales (Monotributo Productivo); (5) Estado Municipal/Provincial (Árbitro de Crédito); (6) Sindicato de Rama (UTICRA/SETIA); y (7) Organismo Tecnológico Neutral (INTI). Articula a nivel macro (**MES Federal**) y en el territorio operativo (**MES Municipal / Nodos Regionales**).

### **Fideicomiso de Desarrollo Industrial (FDI)**
Fondo fiduciario de segundo piso administrado con la participación del **Banco de la Provincia de Buenos Aires (BAPRO)** y cajas de crédito cooperativo. Desintermedia el crédito bancario comercial operando con un ratio de apalancamiento prudencial ($K=3$), financiando el capital de trabajo de los talleres contra el colateral de las e-OPs activas.

### **Contrato Timelock (Bloqueo Temporal de 48 Horas)**
Algoritmo de control temporal programado en el sistema informático. Establece una ventana máxima e improrrogable de **48 horas hábiles** desde la carga de una e-OP para que la Comisión de Crédito de la MES emita un dictamen fundado de objeción técnica. Si la comisión no se pronuncia en ese lapso, el sistema desbloquea automáticamente el anticipo.

### **Silencio Administrativo Positivo**
Principio rector de ingeniería procesal: ante la inacción u omisión burocrática del cuerpo colegiado dentro del plazo perentorio de 48 horas, **el sistema informático da por aprobada la orden de pleno derecho por vía de silencio positivo**. Impide que disputas partidarias o desidia administrativa congelen el trabajo del tallerista.

### **Modalidad Operativa Fabril (OP de Gestión Interna vs. e-OP Federada)**
Arquitectura de ejecución manufacturera estructurada para diferenciar la coordinación técnica de planta del circuito de financiamiento fiduciario:
* **OP de Gestión Interna (Modo Fabril / Taller Propio):** Documento técnico-operativo de planta (hoja de ruta de ingeniería, curva de talles, receta de consumo BOM y ruteo de etapas físicas de corte, rebajado, aparado y armado). Al constituir una directiva operativa interna de coordinación fabril y no una operación de compraventa o enajenación comercial entre terceros, no configura hecho imponible tributario ni requiere validación electrónica ante AFIP/ARCA (sin CAE). Su alcance es estrictamente de gestión industrial y se rige por el Código Civil y Comercial de la Nación (CCCN).
* **e-OP Federada (Protocolo Institucional FIMCA):** Orden que eleva la especificación técnica de planta a título de afectación productiva y colateral financiero ante el Fideicomiso FDI. Activa la custodia en Escrow bancario, el adelanto de capital de trabajo (Hito Cero), el Timelock de 48 horas con silencio positivo, la auditoría técnica territorial (PTF) y el régimen promocional de crédito fiscal presunto (25%) e IVA diferido.

### **Addenda e-OP (Enmienda Contractual por Fuerza Mayor)**
Mecanismo de modificación formal inmutable de una e-OP en ejecución. Ante contingencias fortuitas (siniestros, rotura crítica de maquinaria o mermas extraordinarias no imputables), las partes y la MES suscriben criptográficamente una adenda que recalcula proporcionalmente las metas de entrega, readecua los desembolsos de los hitos pendientes y reintegra el saldo no devengado de la custodia fiduciaria al FDI.

---

## <a id="sec-2"></a>2. Primitivas Criptográficas y de Trazabilidad Inmutable

### **UUID (Universally Unique Identifier)**
Identificador universal único pseudoaleatorio de 128 bits (ej. `e8b7c934-8fa4-4e1a-ad35-c02cd6ac65d1`). Garantiza la unicidad matemática global de cada e-OP emitida en el sistema, vinculando en una sola clave todas las transacciones físicas, remitos, movimientos de inventario y transferencias bancarias asociadas.

### **Merkle Root BOM ($\mathcal{M}_{BOM}$)**
Raíz criptográfica de un **Árbol de Merkle** generado a partir de las hojas que contienen cada insumo, consumo unitario y tolerancia de merma de la receta técnica. Permite verificar matemáticamente que la lista de materiales no fue adulterada a posteriori sin necesidad de exponer en público la totalidad de la fórmula industrial protegida de la marca.

### **Claves Criptográficas Ed25519**
Esquema de firma digital de curvas elípticas de última generación (EdDSA). Ofrece alta velocidad de cálculo y resistencia contra ataques de canal lateral, utilizado para firmar digitalmente las autorizaciones de la marca comitente, del tallerista y del árbitro institucional de la MES.

### **Esquema Multifirma 2 de 3 (Multisig 2-of-3)**
Mecanismo de seguridad transaccional donde los fondos bloqueados en Escrow solo pueden liberarse si confluyen al menos dos firmas criptográficas autorizadas: (a) Marca Comitente; (b) Tallerista Ejecutor; (c) Árbitro de la MES. Evita que cualquiera de las partes bloquee unilateralmente el dinero de manera abusiva.

### **Sello QR de Trazabilidad Socioproductiva**
Código bidimensional impreso en la etiqueta de packaging de cada par de calzado. Al ser escaneado por el consumidor final en góndola o comercio electrónico, redirige a una URL pública (`https://indino.ar/t/{UUID}`) que desglosa de manera transparente la descomposición factorial de costos: mano de obra territorial, materias primas nacionales, carga impositiva neta y margen comercial.

### **PoPW (Proof of Productive Work / Prueba de Trabajo Productivo)**
Mecanismo de consenso fáctico que sustituye a las pruebas computacionales sintéticas. La liberación de recursos en custodia financiera no depende de cálculos de hashing abstractos, sino de la constatación física presencial de un lote manufacturado en planta por parte del PTF, sellada con geolocalización PostGIS, validación biométrica RENAPER y firma Ed25519 en hardware seguro.

### **Geo-Fencing Anti-Colusión (PostGIS `ST_Distance`)**
Algoritmo de salvaguarda espacial ejecutado en la capa transaccional (`services.py`). Al momento de certificar un hito en la app móvil, el sistema evalúa la distancia ortodrómica entre las coordenadas GPS emitidas por el dispositivo del auditor y el polígono catastral habilitado del taller. Si la distancia supera los 150 metros, se bloquea la firma Ed25519 y se dispara un *Alerta de Colusión* en la MES para evitar aprobaciones fraudulentas remotas.

### **mTLS (Mutual TLS) y PKI Federada**
Protocolo de seguridad perimetral de red en el que tanto el cliente como el servidor se autentican mutuamente mediante certificados digitales x509. En la red Indinopy, los nodos de marcas y talleres solo pueden intercambiar payloads canónicos con el nodo MES si sus certificados fueron emitidos por la Autoridad Certificante raíz (`indinopy.ar`).

### **Lista de Revocación de Certificados (CRL)**
Registro criptográfico inmutable y distribuido administrado por la MES que contiene los identificadores de claves públicas Ed25519 dadas de baja por pérdida de terminales móviles, robo o remoción de apoderados y promotores. Toda transacción firmada con una clave registrada en la CRL es rechazada automáticamente por el API Gateway.

### **IA Algorética (Planificación Algorética para la Justicia Distributiva)**
Concepto doctrinario fundacional de FIMCA (Addenda II, Sección VIII.K), inspirado en la encíclica *Magnifica Humanitas* y el principio de subordinación de la tecnología a la dignidad humana. Plantea el despliegue de modelos de inteligencia artificial de código abierto bajo control comunitario para: (a) auditar predictivamente precios de mano de obra y alertar ante intentos de remuneración por debajo del convenio colectivo; (b) optimizar equitativamente la asignación de pedidos en la Bolsa de Trabajo; y (c) asistir a los PTFs mediante interfaces en lenguaje natural. Se establece como dogma legal que **ningún sistema automatizado puede decretar sanciones, exclusiones de marcas ni quitas de beneficios sin intervención y ratificación humana colegiada**.

### **Zero-Retention Biométrico (Ley 25.326 de Protección de Datos)**
Directriz de privacidad y seguridad implementada en la integración de enrolamiento con RENAPER. Los vectores biométricos (huella dactilar o reconocimiento facial) no se almacenan bajo ninguna circunstancia en almacenamiento persistente ni bases de datos de Indinopy. El sistema procesa la validación de forma efímera en memoria RAM, estampa el resultado en el log de auditoría y destruye el vector biométrico de inmediato.

---

## <a id="sec-3"></a>3. Actores de Gobernanza y Velo Societario

### **Marca Comitente**
Empresa que encarga la producción, aporta el diseño, provee las materias primas bajo régimen de custodia, comercializa el producto terminado e integra el fondeo de la mano de obra en la bóveda de Escrow del FDI.

### **Beneficiario Final Real (UBO - Ultimate Beneficial Owner)**
Persona física titular, socio gerente o director real de la marca comitente, identificado fehacientemente mediante su DNI y constatación biométrica ante RENAPER. 
* **Doctrina contra Quiebras Fraudulentas:** Si la marca quiebra una razón social ("Calzados Fantasma S.R.L.") dejando pasivos salariales, la penalización (*Slashing*) y la pérdida de score no quedan en la persona jurídica vaciada, sino que **se heredan en el DNI del titular real**, exigiéndole 100% de fianza líquida si intenta operar con una nueva sociedad.

### **Tallerista Ejecutor / Unidad Productiva Territorial**
Microempresa, taller familiar o consorcio barrial (cortadores, aparadores, armadores) que aporta la capacidad de trabajo físico y la maquinaria de taller. Opera adherido a la Bolsa de Trabajo bajo la figura de Monotributo Productivo o Sociedad por Acciones Simplificada (SAS).

### **Promotor Territorial de Formalización (PTF)**
Trabajador de base del oficio con antigüedad mínima comprobable de 12 meses y aval de 5 talleres vecinos, designado por la MES local y rentado con honorario de 2 Salarios Mínimos, Vitales y Móviles financiados por el FDI. Opera como un **Puente Humano y Tutor Técnico**; actúa como agente fiduciario de proximidad: inspecciona talleres, constata avances de lote, asiste digitalmente a los talleres en la plataforma y da fe ante la MES para la liberación de los hitos del Escrow digital.

### **Score Solidario de la Bolsa de Trabajo**
Algoritmo de reputación cooperativa que reemplaza al *scoring* bancario tradicional. Califica a marcas y talleres sobre una escala de 0 a 100 puntos en base a variables reales: índice de cumplimiento de plazos, calidad de entrega, bajo nivel de desperdicio de cuero y cumplimiento de pisos salariales.

### **Bolsa de Trabajo Sectorial (Registro Nacional de Capacidades)**
Mercado organizado comunitario gobernado por la MES (Addenda II, Sección VIII.B). Funciona como un directorio verificado en tiempo real donde la oferta de los talleres adheridos (especialidades, capacidad productiva semanal auditada, radio logístico e historial de cumplimiento) se cruza con la demanda de las marcas comitentes sin intermediarios ni cobro de comisiones privadas. La formalización es la llave de acceso directa a nuevas oportunidades de negocio.

### **Maestros Artesanos y Sub-Bolsa de Formación**
Categoría de reconocimiento honorífico y operativo dentro de la Bolsa de Trabajo para talleristas con más de diez años en el oficio y antecedentes intachables. Autoriza la tutoría de pasantías productivas remuneradas para jóvenes de 16 a 24 años mediante fondos del FDI, protegiendo del descarte y la extinción técnicas históricas de moldería, aparado fino y marroquinería artesanal.

### **Talleres Espejo (Fragmentación Artificial y Fraude de Escala)**
Práctica ilícita consistente en subdividir artificialmente un taller consolidado en múltiples prestadores individuales falsos o monotributistas precarios para eludir las escalas del régimen general o la registración formal de trabajadores. La plataforma detecta este patrón mediante auditorías automáticas de metadatos espaciales, direcciones IP compartidas y similitud de facturación, derivando de oficio las actuaciones al Sindicato y a la MES para su reconversión forzosa al Puente SAS.

### **Ventanilla Única Municipal de Formalización y Habilitación de Oficio**
Dependencia operativa de articulación entre el gobierno local y la MES. Al tramitarse una e-OP que otorga el alta en el Monotributo Productivo, el municipio emite en un plazo perentorio de 48 horas la habilitación comercial provisoria de oficio del taller barrial y hace efectiva la exención decenal de tasas de seguridad e higiene pactada en el régimen.

---

## <a id="sec-4"></a>4. Técnica del Calzado, BOM y Mermas

### **BOM (Bill of Materials / Lista de Materiales)**
Receta técnica formal y exhaustiva que detalla todos los insumos necesarios para fabricar una unidad de producto (un par de calzado): superficie de cuero, metros de cordura, pares de suelas, kilogramos de adhesivo, pares de punteras y avíos.

### **Curva de Talles**
Matriz de distribución cuantitativa de pares que compone un lote de producción, desglosada por número de calzado (en Argentina, habitualmente del talle 38 al 45 para calzado masculino de trabajo). Responde a la distribución de tallas antropométrica del mercado consumidor.

### **Horma Normalizada (ej. INTI-CALZ-H34)**
Matriz física de madera o polietileno de alta densidad que reproduce la anatomía del pie humano y determina el volumen interno, ancho, calce y silueta estética del calzado. El código `INTI-CALZ` indica que la horma fue auditada por los centros tecnológicos estatales para garantizar estándares ortopédicos y ergonómicos de trabajo.

### **Sello Buen Diseño (SBD)**
Distinción oficial otorgada por la Secretaría de Industria de la Nación a productos que destacan por su innovación, agregación de valor local y calidad de materiales. En el protocolo e-OP, contar con certificación SBD autoriza al taller y a la marca a solicitar un **anticipo preferencial de arranque (Hito Cero) de hasta el 40% o 50%**.

### **Merma Técnica Aprobada por el INTI**
Porcentaje de desperdicio admisible e inevitable que se produce durante el proceso de corte de materiales heterogéneos (como el cuero vacuno, cuyas formas irregulares y cicatrices impiden un aprovechamiento del 100%). La homologación de mermas por el INTI (ej. 8% en cuero flor, 5% en forro textil) impide que la marca comitente acuse arbitrariamente al tallerista de robo de material ante el descarte natural de la chapa de cuero.

### **Cuero Vacuno Box Flor Hidrofugado**
Cuero curtido al cromo de espesor 1.8 a 2.0 mm obtenido de la capa exterior del animal (la "flor"), tratado con aceites hidrófugos durante el proceso de recurtido para repeler la penetración del agua sin perder transpirabilidad.

### **Cordura Rip-Stop 1000D**
Tejido técnico de poliamida de alta tenacidad con hilado de 1000 deniers y trama antidesgarro en cuadrícula (*Rip-Stop*). Utilizado en laterales y cañas del calzado táctico para alivianar peso manteniendo resistencia a la abrasión.

### **Puntera Normalizada IRAM 3610**
Casquillo protector anatómico colocado en la puntera del borcego, ensayado bajo la Norma IRAM 3610 para resistir una energía de impacto de 200 Joules y una carga de compresión de 15 kN sin aplastamiento de los dedos del operario.

### **Adhesivo Poliuretánico sin Tolueno + Halogenante**
Pegamento de base poliéster-poliuretano libre de toluol (solvente aromático altamente nocivo para las vías respiratorias del zapatero). Requiere la aplicación previa de un líquido halogenante sobre la suela de caucho para modificar químicamente la polaridad superficial y garantizar una adherencia indeleble tras reactivación térmica.

---

## <a id="sec-5"></a>5. Tracking Físico y Partes de Producción

### **Parte de Producción Físico (`OPParteProduccion` - PART-N°)**
Comprobante operativo digital y en papel mediante el cual el tallerista declara la culminación de un tramo del trabajo, especificando: pares conformes de primera calidad, pares de segunda y porcentaje de scrap resultante. Es el disparador probatorio que gatilla la auditoría del PTF.

### **Liquidación Desacoplada por Etapa**
Principio arquitectónico del sistema donde cada etapa productiva es tratada como un nodo financiero independiente. Si el taller de corte completó su trabajo, **su pago se liquida de inmediato**; no queda congelado si el taller de aparado posterior sufre demoras operativas.

### **Etapa 1: Corte y Rebajado**
Operación donde se trazan y cortan las piezas de cuero y forro según la moldería, procediendo luego al rebajado (desbaste perimetral del espesor del cuero con cuchilla circular) para que las uniones cosidas no queden toscas ni lastimen el pie.

### **Etapa 2: Aparado y Costura**
Proceso artesanal y de máquina mediante el cual las piezas planas de cuero y cordura son ensambladas, cementadas y cosidas con pespuntes simples, dobles y atraques reforzados, conformando la estructura tridimensional superior del calzado (la "capellada").

### **Etapa 3: Armado, Centrado y Montaje**
Operación pesada en la cual la capellada aparada se monta sobre la horma plástica, se coloca el contrafuerte y la puntera de acero, se estira el cuero mediante pinzas de montar, y se une la suela de caucho con cemento reactivado en prensa neumática vulcanizadora.

### **Etapa 4: Acabado, Emplantillado, Lustre y Empaque**
Etapa final de deshormado, colocación de plantillas de confort en goma EVA, limpieza de hilachas y restos de adhesivo, lustre protector del cuero, colocación de cordones y estibado en cajas individuales de cartón con etiqueta QR.

---

## <a id="sec-6"></a>6. Arquitectura Financiera, Escrow Digital y Moneda

### **Escrow Digital Atomizado**
Dispositivo fiduciario programable en el sistema informático. Los fondos correspondientes a la retribución de la mano de obra son depositados por la marca comitente en una subcuenta fiduciaria cerrada del FDI en el momento en que se emite la orden. La marca **pierde la libre disponibilidad del dinero**, el cual se va liberando automáticamente hacia la cuenta del tallerista conforme se verifican los hitos pactados.

### **Hito Cero (Anticipo de Arranque Territorial)**
Primer desembolso financiero liberado a favor del tallerista (habitualmente entre el **35% y el 40%**, o hasta el **50% con Sello Buen Diseño**). Se acredita inmediatamente tras la convalidación de la orden por la MES (o al cumplirse las 48 horas de silencio positivo). Su fin es fondear el capital de trabajo inicial: compra de hilos, agujas, solventes, energía eléctrica y adelantos salariales para el sustento diario de los costureros.

### **Hitos de Avance (Hito 1 y 2)**
Desembolsos intermedios que se liberan de forma escalonada contra la constatación física de entrega de etapas parciales (ej. 20% al finalizar el corte de los 500 pares, 25% al entregar el aparado cosido).

### **Hito Final (Saldo de Cierre de Lote)**
Último tramo del pago (habitualmente el **15% al 20%**) retenido en Escrow hasta la recepción definitiva del lote terminado en depósito y el control de calidad final. Permanece protegido durante una ventana de 48 horas para la eventual interposición de la tutela sindical ex-post.

### **UCI (Unidad de Cuenta Industrial)**
Unidad de indexación fiduciaria del sistema (1 UCI $\approx$ valor canasta base de mano de obra manufacturera). Todo contrato de e-OP pacta su valor en UCIs, las cuales se liquidan en pesos al momento efectivo de cobro según la variación del **Índice de Precios Internos al Por Mayor (IPIM Manufacturero INDEC)**:
$$\mathcal{P}_{\text{ARS}}(t) = \mathcal{P}_{\text{UCI}} \times \left( \frac{\text{IPIM}(t)}{\text{IPIM}_0} \right)$$
Protege al tallerista del descalce inflacionario entre el día que presupuestó el lote y el día que lo terminó de coser.

### **Micro-canon de Red MES (Take-rate del 1.0%)**
Alícuota fija descontada automáticamente del clearing de cada e-OP liquidada exitosamente. Se divide en: sostenimiento de los honorarios mensuales de los Promotores Territoriales (PTF), equipamiento de centros tecnológicos CIFO y mantenimiento de los servidores del sistema Indinopy. Garantiza el autofinanciamiento del régimen sin depender de subsidios del Estado.

### **Fondo de Riesgo y Contingencias del FDI (0.5%)**
Fondo fiduciario de reserva colectiva alimentado con una alícuota de medio punto sobre las órdenes. Se utiliza para absorber pérdidas fortuitas por rotura de maquinaria pesada, incendios o siniestros en talleres vulnerables, evitando que una contingencia individual hunda a la microempresa o paralice la cadena.

### **UCP (Unidades de Crédito Productivo — Score Solidario de Marcas)**
Activo digital de reputación empresarial co-administrado por la MES Federal y la Secretaría de Comercio de la Nación (Addenda II, Sección VIII.J). Las marcas comitentes homologadas acumulan UCPs en su perfil público al: (a) pagar tarifas justas de mano de obra en término; (b) integrar pedidos con talleres vulnerables; (c) colaborar en la exportación de calzado nacional; o (d) adoptar el Sello QR de transparencia radical de costos en góndola. Un saldo elevado de UCP otorga prioridad automatizada en cupos de importación temporaria con arancel cero y descuentos de hasta el 20% en la Tarifa Plana Industrial.

### **Compliance Fiduciario: AML, KYC y Reporte de Operación Sospechosa (ROS)**
Entramado de cumplimiento regulatorio financiero exigido por los convenios con el Banco de la Provincia de Buenos Aires (BAPRO) y la UIF:
* **KYC (Know Your Customer):** Validación de identidad de titulares y beneficiarios finales (UBO) cruzada en tiempo real con RENAPER y ARCA.
* **AML (Anti-Money Laundering):** Monitoreo algorítmico continuo de volúmenes transaccionales. Si un tallerista excede los topes objetivos de facturación de su categoría fiscal sin justificación técnica, el sistema retiene preventivamente la liquidación del clearing y genera un **ROS interno** para análisis por parte del oficial de cumplimiento del fideicomiso.

---

## <a id="sec-7"></a>7. Matriz Factorial de Costos Ítem por Ítem

### **Costo Industrial Fabril**
Costo técnico directo consolidado de fabricación en planta, compuesto por la suma matemática de:
$$\text{Costo Industrial} = \text{Insumos BOM} + \text{Mano de Obra Neta} + \text{Cargas Previsionales} + \text{Canon MES} + \text{Impuestos Directos}$$

### **Mano de Obra Directa Territorial**
Suma de los valores percibidos por los diferentes talleres y operarios especializados que intervinieron en la transformación física del calzado (corte, rebajado, aparado, armado y empaque). Representa el valor agregado del trabajo vivo en el distrito.

### **Margen Comercial y Distribución de la Marca**
Diferencia bruta entre el Costo Industrial Fabril y el Precio de Venta al Público (sin IVA). Retribuye los costos de desarrollo de moldería, diseño, marketing comercial, logística federal, estructura administrativa y rentabilidad del comitente.

### **P.V.P. Sugerido (Precio de Venta al Público con IVA)**
Precio final proyectado para la venta del calzado en el mostrador del comercio minorista o plataforma de e-commerce, incluyendo el Impuesto al Valor Agregado del 21% aplicable al consumidor final.

---

## <a id="sec-8"></a>8. Tutela Laboral, Veto Ex-Post y Arbitraje

### **Veto Ex-Post Sindical**
Potestad de policía de trabajo ejercida por el sindicato con personería gremial (UTICRA o SETIA). A diferencia del modelo burocrático tradicional, el gremio **no frena el inicio de la orden con sellos preventivos**, sino que audita la realidad física en el taller durante la confección o al momento de la entrega.

### **Alerta de Escrow**
Gatillo informático activado por el sindicato si detecta precios de mano de obra por debajo del piso de convenio colectivo o condiciones insalubres de explotación. Produce el **bloqueo preventivo automático del Hito Final (15%) en el FDI por un plazo máximo de 48 horas hábiles**, sin suspender el trabajo de las máquinas ni privar al tallerista del cobro de lo ya realizado.

### **Fianza Líquida de Continuidad Operativa**
Mecanismo de resguardo que impide que la mercadería quede secuestrada y la marca pierda la temporada comercial. La empresa comitente puede depositar en garantía el **100% del monto salarial en litigio en la cuenta del FDI**; una vez acreditada la fianza, retira los bultos para su venta mientras el diferendo continúa sustanciándose por la vía arbitral.

### **Tribunal Arbitral Territorial**
Tribunal arbitral perentorio constituido en la MES local, integrado por: (a) El perito técnico neutral del INTI (que ejerce la presidencia); (b) Dos vocales sorteados de la Bolsa de Trabajo (un tallerista y una marca ajenos al litigio). Dicta laudo inapelable en un plazo duro de **72 horas hábiles**, ordenando la readecuación retroactiva de tarifas o desestimando la queja.

### **Mecanismo de Slashing (Penalización Algorítmica)**
Castigo informático automático ante faltas graves o reincidencia en prácticas predatorias:
* **Para Marcas Defectoras:** Quita inmediata de Unidades de Crédito Productivo (UCP), pérdida del beneficio de arancel cero y, a la tercera condena firme, **exclusión total del FIMCA**.
* **Para Talleres Defectores:** Retención del 30% en liquidaciones de e-OPs futuras para resarcir cuero dañado y degradación de la insignia en la Bolsa de Trabajo.

### **Hard Ban Criptográfico de Nodo**
Sanción informática máxima e irreversible ejecutada por el Smart Contract del nodo raíz de la MES. Ante un default de pago no subsanado superior a 60 días con el FDI, o ante la reiteración de tres fallos condenatorios por abusos laborales, el CUIT y la clave pública Ed25519 de la marca infractora son inyectados en la lista de bloqueo inmutable de la red. Esto impide técnica y criptográficamente que cualquier nodo federado procese o firme nuevas e-OPs con dicha razón social o con el DNI de sus beneficiarios finales (UBO).

### **Canal de Denuncias y Reserva de Identidad Tuitiva**
Dispositivo bimodal de protección institucional (Addenda II, Sección VIII.F) integrado por un canal digital con cifrado asimétrico y buzones físicos lacrados en municipios y sindicatos. Permite a los talleristas denunciar extorsiones, coimas o imposición de precios abusivos. Su activación dispara de inmediato: (a) reserva estricta de identidad; (b) inmunidad fiscal temporaria de 180 días contra inspecciones presenciales de ARCA; y (c) orden de perimetral administrativa que inhabilita al inspector denunciado para actuar en la zona.

---

## <a id="sec-9"></a>9. Régimen Impositivo, Fiscal y Previsional

### **Locación de Obra vs. Compraventa**
Diferenciación legal de fondo regulada por el Código Civil y Comercial de la Nación (Art. 1251):
* En la **compraventa**, el taller compraría cuero y vendería zapatos, quedando atrapado en el débito de IVA y presunciones de Ganancias de un comerciante.
* En la **locación de obra con insumos provistos**, el tallerista vende únicamente un *servicio de transformación de trabajo humano*. No adquiere la propiedad del cuero ni vende el calzado terminado, tributando solo sobre su honorario de confección.

### **Cláusula de Inembargabilidad Territorial de Insumos**
Blindaje legal explícito conforme a los artículos 1251 y 1356 del CCCN. Las materias primas y semielaborados en taller constituyen **activos intangibles de afectación productiva territorial**. No forman parte del patrimonio ejecutable del tallerista ni pueden ser embargados por deudas comerciales o bancarias de la marca comitente.

### **Monotributo Productivo con Micro-retención en Clearing (1.5%)**
Régimen tributario simplificado adaptado a la economía popular manufacturera:
* Se elimina la cuota fija mensual mensualizada que acumulaba deudas en épocas de parálisis o caída de ventas.
* El impuesto se recauda mediante una **micro-retención del 1.5% aplicada automáticamente en la cuenta bancaria de clearing** en el instante exacto en que el tallerista cobra cada hito.

### **Suspensión Activa de Oficio**
Garantía que ampara al Monotributista Productivo: si el taller pasa meses sin emitir partes ni registrar e-OPs activas, el sistema de ARCA/MES **suspende de oficio el devengamiento de cargas, multas, intereses o bajas de oficio**. El taller puede reactivarse en cualquier momento sin pagar deudas acumuladas.

### **Deducción al 100% en Impuesto a las Ganancias**
Impacto decisivo para la marca comitente: la e-OP certificada por la MES opera como comprobante fiscal habilitante que le permite a la PyME comitente formal **deducir el 100% del gasto de confección pagado a los talleres tercerizados**. Termina con la perversión de tributar Ganancias sobre "utilidades ficticias" causadas por la falta de facturación formal de los talleres clandestinos.

### **Subvención del 100% de Contribuciones Patronales (FDI Previsional)**
Mecanismo de choque para la formalización del empleo asalariado en talleres de base: el FDI financia el **100% de los aportes patronales (27% del salario bruto) de los primeros dos trabajadores regularizados por taller durante un período de 24 meses**, eliminando el costo previsional de arranque para la incorporación de mano de obra joven o no registrada.

### **Pacto Fiscal Productivo y Exención de Tasas Locales**
Acuerdo institucional suscripto entre la Nación, la Provincia de Buenos Aires (ARBA) y los Municipios del Conurbano: los talleres y fábricas adheridos gozan de **exención total por 10 años de la Tasa de Seguridad e Higiene municipal y alícuota cero en Ingresos Brutos** sobre la porción de mano de obra de confección, compensado a los municipios con transferencias directas de infraestructura industrial.

### **Cláusula de No Retroactividad Fiscal**
Garantía legal y doctrinaria indispensable para desarmar el temor histórico del tallerista informal a formalizarse (Addenda II, Sección VIII.A). La ley FIMCA establece taxativamente que el alta en el Monotributo Productivo no habilita a los organismos de recaudación (ARCA, ARBA ni municipios) a iniciar inspecciones retroactivas, determinar deudas de oficio o ejecutar fiscalmente actividades económicas informales previas a la fecha de ingreso al régimen.

### **Cuenta de IVA Sectorial y Crédito Fiscal Presunto (25%)**
Mecanismo de descompresión financiera para unidades productivas (Addenda II, Sección VIII.L):
* **Diferimiento por Clearing:** El IVA sobre la mano de obra no sigue el régimen general de devengamiento mensual inflexible; se retiene y liquida únicamente al momento del cobro efectivo de cada hito bancario. Si el comitente no paga la orden, el tallerista no acumula deuda tributaria.
* **Crédito Fiscal Presunto:** Se habilita a las unidades SAS adheridas a computar un crédito presunto del veinticinco por ciento (25%) sobre el valor de la e-OP, garantizando la perfecta deducibilidad de costos en Ganancias e IVA para las marcas comitentes y absorbiendo la informalidad de insumos de base.

### **Puente SAS para Responsables Inscriptos Humanos**
Programa de migración asistida que desactiva el "purgatorio fiscal" (Addenda II, Sección VIII.L). Permite a los talleres consolidados y diseñadores individuales atrapados en el régimen de Responsable Inscripto constituir de forma gratuita y en 48 horas una Sociedad por Acciones Simplificada (SAS) en la Ventanilla Única Municipal. Esto escinde el patrimonio personal del productor ante eventuales embargos, suspende ejecuciones fiscales previas por 180 días de paraguas productivo y permite facturar hasta los topes MiPyME en lugar de las categorías asfixiantes del Monotributo.

### **Tarifa Plana Industrial Manufacturera (Desacople Energético)**
Dispositivo de soberanía tarifaria (Addenda II, Sección VIII.L) que desacopla el costo de la energía eléctrica consumida por los talleres adheridos de las cotizaciones internacionales o precios dolarizados. Se fija una tarifa plana calculada en pesos según costos reales de generación local más margen auditado. La diferencia con el mercado spot es compensada a las distribuidoras por el FDI mediante la asignación específica de Derechos de Exportación sobre hidrocarburos y minería.

### **Comprobante de Gestión y Control Interno (Clase "X" / Sin CAE - RG AFIP 1415)**
Documento administrativo no fiscal habilitado en el modelo de cuentas a pagar/cobrar (`DocumentoDeuda`) en estricto apego al régimen de emisión de comprobantes de la autoridad fiscal (Resolución General AFIP N° 1415/2003, Art. 8 inc. a, "Documento no válido como factura"):
* **Devengado Operativo de Fábrica:** Permite a la empresa asentar el avance físico de obra, liquidaciones provisorias de taller a destajo, remitos internos de circulación de insumos y provisiones de costos de planta antes de la emisión o recepción del comprobante electrónico definitivo con CAE.
* **Agnosticismo y Realidad Económica:** Garantiza el reflejo fidedigno de los flujos físicos y financieros de la fábrica sin anticipar ni distorsionar bases imponibles fiscales, reservando los comprobantes con validación electrónica (Facturas A, B, C, MiPyME) para los actos comerciales perfeccionados.

> [!NOTE]
> **Aviso de Neutralidad Tecnológica y Cumplimiento Legal:**
> Indinopy es una plataforma de software de ejecución de manufactura (MES) y planificación de recursos (ERP). La habilitación de comprobantes de control interno y órdenes de producción responde estrictamente a necesidades de coordinación técnica fabril y cómputo de costos operativos. Toda orden de producción y comprobante de gestión interna está sujeto a la legislación mercantil y tributaria vigente. La determinación de la materia gravada, la emisión de facturas electrónicas con CAE y la liquidación impositiva recaen de manera exclusiva e indelegable en los contribuyentes y usuarios emisores bajo el Régimen Penal Tributario (Ley 27.430).

---

## <a id="sec-10"></a>10. Resiliencia de Software, Integración y Operaciones Técnicas

### **Dead-Letter Queue (DLQ) e Idempotencia de Webhooks**
Mecanismos de robustez y tolerancia a fallas en la arquitectura asincrónica distribuida (Celery / Redis / PostgreSQL):
* **Idempotencia Transaccional:** Toda llamada API entrante proveniente de pasarelas bancarias o webhooks de comercio electrónico (WooCommerce) viaja sellada con un UUID y cabecera `X-Idempotency-Key`. Ante reintentos por caída de red, el sistema retorna `200 OK` pero omite duplicar asientos contables o disparar nuevamente las APIs de clearing.
* **Dead-Letter Queue (DLQ):** Si un webhook saliente dirigido a un taller con servidor local intermitente falla tras 24 horas de reintentos exponenciales, el mensaje se traslada a una cola de mensajes muertos (DLQ) en Redis para diagnóstico, evitando la pérdida de transacciones y alertando a la infraestructura MES.

### **Topología Offline-First con Sincronización por Polling**
Esquema de comunicación asincrónica saliente (*outbound polling*) diseñado para talleres físicos con conectividad intermitente o detrás de firewalls y NATs sin IP pública fija. Los clientes móviles o servidores locales firman y encolan las aprobaciones de hitos en almacenamiento seguro local con estampado de tiempo criptográfico. Al restablecerse la conexión, transmiten el payload canónico. Si ocurrieran colisiones (ej. cancelación simultánea por la marca), el nodo MES aplica arbitraje por vector temporal de firmas digitales.

---

## <a id="sec-11"></a>11. Tabla Rápida de Siglas y Acrónimos

| Sigla | Significado Completo | Ámbito de Aplicación |
| :--- | :--- | :--- |
| **AML** | *Anti-Money Laundering* (Prevención de Lavado de Activos) | Filtros de volumen fiduciario y alertas UIF |
| **ARCA** | Agencia de Recaudación y Control Aduanero (ex-AFIP) | Administración tributaria y aduanera nacional |
| **BAPRO** | Banco de la Provincia de Buenos Aires | Entidad fiduciaria y agente de clearing bancario |
| **BOM** | *Bill of Materials* (Lista / Receta de Materiales) | Especificación técnica de ingeniería fabril |
| **CCCN** | Código Civil y Comercial de la Nación (Ley 26.994) | Marco legal contractual (Arts. 1251 y 1356) |
| **CCT** | Convenio Colectivo de Trabajo de Rama | Normativa salarial paritaria de base (UTICRA/SETIA) |
| **CIFO** | Centro de Integración y Formación de Oficios | Banco comunitario de maquinaria pesada y capacitación |
| **CRL** | *Certificate Revocation List* | Padrón criptográfico de claves y dispositivos revocados |
| **DLQ** | *Dead-Letter Queue* | Cola de contingencia para webhooks y mensajes fallidos |
| **Ed25519** | Edwards-curve Digital Signature Algorithm | Criptografía asimétrica de firma digital rápida |
| **e-OP** | Orden de Producción Electrónica | Primitiva digital y título de crédito fiduciario |
| **ERP** | *Enterprise Resource Planning* | Módulo de compras, tesorería y contabilidad |
| **FDI** | Fideicomiso de Desarrollo Industrial | Bóveda fiduciaria de segundo piso y liquidez |
| **FIMCA** | Formalización e Incentivo a la Manufactura del Calzado Argentino | Proyecto de Ley y marco general del ecosistema Indinopy |
| **INTI** | Instituto Nacional de Tecnología Industrial | Organismo técnico neutral, certificador de mermas y normas |
| **IPIM** | Índice de Precios Internos al Por Mayor (INDEC) | Referencia de indexación de la Unidad de Cuenta Industrial |
| **KYC** | *Know Your Customer* | Verificación biométrica y tributaria de identidad |
| **MES** | Mesa de Enlace Sectorial (Federal / Local) | Órgano paritario de gobierno de la cadena (7 sillas) |
| **MES** | *Manufacturing Execution System* (en Indinopy) | Sistema de tracking de planta y partes de producción |
| **mTLS** | *Mutual Transport Layer Security* | Canal criptográfico de autenticación mutua entre nodos |
| **PKI** | *Public Key Infrastructure* | Infraestructura de claves públicas gobernada por la MES |
| **PoPW** | *Proof of Productive Work* | Consenso fáctico y auditoría territorial descentralizada |
| **PTF** | Promotor Territorial de Formalización | Representante territorial par y veedor del Escrow |
| **RENAPER** | Registro Nacional de las Personas | Validación biométrica de identidad en tiempo real |
| **ROS** | Reporte de Operación Sospechosa | Alerta antilavado remitida al oficial de cumplimiento |
| **SAS** | Sociedad por Acciones Simplificada | Figura societaria ágil para talleres de hasta 30 operarios |
| **SBD** | Sello Buen Diseño | Distinción oficial que premia la calidad e innovación local |
| **SLA** | *Service Level Agreement* | Acuerdos de nivel de servicio y plazos duros del sistema |
| **UBO** | *Ultimate Beneficial Owner* (Beneficiario Final) | DNI de la persona física detrás de la persona jurídica |
| **UCI** | Unidad de Cuenta Industrial | Moneda de indexación fiduciaria de la mano de obra |
| **UCP** | Unidades de Crédito Productivo | Score solidario y puntaje aduanero/energético de marcas |
| **UIF** | Unidad de Información Financiera | Organismo nacional de control contra lavado de activos |
| **UTICRA** | Unión Trabajadores de la Industria del Calzado | Gremio de rama con tutela territorial (Silla 6 MES) |
| **UUID** | *Universally Unique Identifier* | Identificador universal único de la e-OP |

