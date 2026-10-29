# Feature Specification: Alta de organizaciones

**Feature Branch**: `001-alta-organizaciones`

**Created**: 2026-10-28

**Status**: Draft

**Input**: User description: "Alta de organizaciones. Las organizaciones son los clientes (administradoras de condominios) que contratan la plataforma. Sólo el SUPER_ADMIN puede acceder a esta funcionalidad; ADMIN y ASISTENTE no tienen acceso. El SUPER_ADMIN puede dar de alta, listar, consultar, modificar, deshabilitar y volver a habilitar organizaciones. Deshabilitar es un borrado lógico: los datos se conservan, pero los usuarios de la organización dejan de poder entrar de inmediato. Datos de la organización: generales (obligatorios): nombre comercial, nombre de contacto, correo, teléfono; dirección opcional. Logotipo: opcional, PNG o JPG, máximo 2 MB. Fiscales (obligatorios): RFC (único en la plataforma), razón social, régimen fiscal, código postal fiscal. Módulos habilitados: se eligen de un catálogo global de módulos disponibles. Facturación de la suscripción: día de corte y día límite de pago (1 a 28). Al dar de alta una organización se le asigna un identificador de tenant único, aleatorio e inmutable, que identifica su base de datos propia, y se registra su primer usuario ADMIN (nombre y correo), que recibe una invitación para activar su cuenta. El listado permite buscar por nombre o RFC, filtrar por estatus (activa o deshabilitada) y paginar. Cada alta, modificación, deshabilitación y rehabilitación queda registrada con usuario y fecha. Fuera de alcance: el cobro automático de la suscripción, la suspensión por falta de pago y la gestión de usuarios adicionales de la organización."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Dar de alta una organización con su primer ADMIN (Priority: P1)

El SUPER_ADMIN registra a una nueva administradora de condominios que acaba de contratar la
plataforma. Captura sus datos generales, fiscales, de facturación, el logotipo (si lo tiene) y los
módulos contratados, y registra a la persona que será su primer ADMIN. Al confirmar, la
organización queda activa con su propio espacio de datos aislado y el ADMIN recibe una invitación
para activar su cuenta.

**Why this priority**: sin organizaciones dadas de alta ningún cliente puede usar la plataforma;
es la puerta de entrada de todo el sistema y la base del aislamiento entre clientes.

**Independent Test**: se prueba completa dando de alta una organización y verificando que aparece
como activa, que tiene un identificador de tenant asignado y que el ADMIN puede activar su cuenta
con la invitación recibida y entrar a la plataforma.

**Acceptance Scenarios**:

1. **Given** un SUPER_ADMIN autenticado y un RFC que no existe en la plataforma, **When** captura
   todos los datos obligatorios, elige al menos un módulo, registra al primer ADMIN y confirma,
   **Then** la organización queda registrada como activa, con un identificador de tenant único
   asignado, y el ADMIN recibe una invitación en el correo capturado.
2. **Given** un SUPER_ADMIN capturando una organización, **When** omite un dato obligatorio o
   captura un dato con formato inválido (RFC, correo, teléfono, código postal, días de facturación),
   **Then** el sistema no registra la organización e indica cada campo a corregir.
3. **Given** que ya existe una organización (activa o deshabilitada) con el RFC "ABC010101AB1",
   **When** el SUPER_ADMIN intenta dar de alta otra organización con ese mismo RFC, **Then** el
   sistema rechaza el alta e informa que el RFC ya está registrado.
4. **Given** un SUPER_ADMIN capturando una organización, **When** adjunta un logotipo que no es
   PNG ni JPG, o que pesa más de 2 MB, **Then** el sistema rechaza el archivo e indica el motivo.
5. **Given** que la invitación del ADMIN fue enviada, **When** el ADMIN la sigue y activa su
   cuenta, **Then** puede iniciar sesión como ADMIN y su sesión queda asociada únicamente a su
   organización.

---

### User Story 2 - Deshabilitar y rehabilitar una organización (Priority: P2)

El SUPER_ADMIN deshabilita a una organización (por ejemplo, porque canceló el servicio). Sus datos
se conservan, pero ningún usuario de esa organización puede seguir entrando ni operando. Más
adelante, si el cliente regresa, el SUPER_ADMIN la rehabilita y sus usuarios recuperan el acceso
con los datos intactos.

**Why this priority**: es el mecanismo para cortar el acceso de un cliente sin perder su
información; sin él, la única opción sería borrar datos.

**Independent Test**: se prueba deshabilitando una organización con un ADMIN activo, verificando
que ese ADMIN ya no puede entrar ni operar, y después rehabilitándola y verificando que recupera
el acceso con los mismos datos.

**Acceptance Scenarios**:

1. **Given** una organización activa con usuarios que tienen sesión abierta, **When** el
   SUPER_ADMIN la deshabilita, **Then** la organización queda con estatus "deshabilitada" y la
   siguiente operación de cualquiera de sus usuarios es rechazada, al igual que cualquier nuevo
   intento de inicio de sesión.
2. **Given** una organización deshabilitada, **When** el SUPER_ADMIN la rehabilita, **Then** su
   estatus vuelve a "activa" y sus usuarios pueden volver a entrar y ver toda la información que
   tenían antes de la deshabilitación.
3. **Given** una organización deshabilitada, **When** el SUPER_ADMIN consulta el listado sin
   filtros, **Then** la organización sigue apareciendo, marcada como deshabilitada.

---

### User Story 3 - Listar, buscar y consultar organizaciones (Priority: P2)

El SUPER_ADMIN necesita localizar rápidamente a un cliente para revisar sus datos. Obtiene un
listado paginado de organizaciones, puede buscar por nombre o RFC y filtrar por estatus, y consulta el detalle
de una organización para consultar toda su información.

**Why this priority**: es necesario para operar la plataforma día a día y es el punto de partida
para modificar, deshabilitar o rehabilitar.

**Independent Test**: se prueba con un conjunto de organizaciones de ejemplo, verificando que la
búsqueda, los filtros y la paginación devuelven exactamente los registros esperados.

**Acceptance Scenarios**:

1. **Given** 45 organizaciones registradas, **When** el SUPER_ADMIN consulta el listado, **Then** obtiene
   la primera página de resultados y puede avanzar a las siguientes hasta ver las 45.
2. **Given** organizaciones con nombres y RFC diversos, **When** el SUPER_ADMIN busca un texto
   parcial del nombre comercial, de la razón social o del RFC, **Then** el listado devuelve sólo las
   organizaciones que coinciden, sin distinguir mayúsculas, minúsculas ni acentos.
3. **Given** organizaciones activas y deshabilitadas, **When** el SUPER_ADMIN filtra por
   "deshabilitada", **Then** el listado devuelve únicamente las deshabilitadas.
4. **Given** una organización existente, **When** el SUPER_ADMIN consulta su detalle, **Then** obtiene sus
   datos generales, fiscales, de facturación, logotipo, módulos habilitados, estatus e identificador
   de tenant.

---

### User Story 4 - Modificar los datos de una organización (Priority: P3)

El SUPER_ADMIN actualiza los datos de un cliente: cambio de contacto, de datos fiscales, de
logotipo, de días de facturación o de los módulos contratados.

**Why this priority**: los datos cambian con el tiempo, pero una organización recién dada de alta
ya es útil sin esta capacidad.

**Independent Test**: se prueba modificando cada grupo de datos de una organización y verificando
que el cambio se refleja en el detalle.

**Acceptance Scenarios**:

1. **Given** una organización existente, **When** el SUPER_ADMIN modifica su teléfono de contacto
   y guarda, **Then** el detalle devuelve el nuevo teléfono.
2. **Given** una organización con los módulos A y B habilitados, **When** el SUPER_ADMIN quita el
   módulo B y guarda, **Then** la organización deja de tener habilitado el módulo B, sin que se
   pierda la información que ya se había generado en él.
3. **Given** una organización existente, **When** el SUPER_ADMIN intenta cambiar el RFC por uno
   que ya pertenece a otra organización, **Then** el sistema rechaza el cambio.
4. **Given** una organización existente, **When** el SUPER_ADMIN consulta los datos editables,
   **Then** el identificador de tenant no puede modificarse.

---

### User Story 5 - Restricción de acceso a SUPER_ADMIN (Priority: P1)

Ningún usuario que no sea SUPER_ADMIN puede ver ni operar sobre el registro de organizaciones.

**Why this priority**: el registro de organizaciones contiene datos comerciales y fiscales de
todos los clientes; que un cliente vea los de otro sería una fuga de datos grave.

**Independent Test**: se prueba intentando cada operación (alta, listado, detalle, modificación,
deshabilitación, rehabilitación) con usuarios ADMIN y ASISTENTE, y sin sesión, y verificando que
todas son rechazadas.

**Acceptance Scenarios**:

1. **Given** un usuario ADMIN o ASISTENTE autenticado, **When** intenta cualquier operación de
   esta funcionalidad, **Then** el sistema la rechaza sin revelar información de ninguna
   organización.
2. **Given** una petición sin sesión válida, **When** intenta cualquier operación de esta
   funcionalidad, **Then** el sistema la rechaza.

---

### Edge Cases

- El correo del primer ADMIN ya pertenece a un usuario existente en la plataforma: el alta se
  rechaza e indica que el correo ya está en uso.
- Falla cualquier paso del alta (registro de la organización o registro del ADMIN): no debe quedar una organización a medias; el alta se completa por entero o
  no se registra nada, y el SUPER_ADMIN puede reintentarla.
- La misma solicitud de alta llega dos veces (doble envío o reintento de red): sólo se
  registra una organización.
- El ADMIN no activa su cuenta antes de que venza la invitación: el SUPER_ADMIN puede reenviar la
  invitación desde el detalle de la organización.
- Dos SUPER_ADMIN modifican la misma organización al mismo tiempo: la segunda modificación se
  rechaza indicando que los datos cambiaron, en lugar de sobrescribir en silencio.
- Se intenta deshabilitar una organización ya deshabilitada, o rehabilitar una activa: el sistema
  informa que ya está en ese estatus y no hace ningún cambio.
- Se intenta quitar todos los módulos a una organización: el sistema lo rechaza; debe conservar al
  menos uno.
- Un módulo del catálogo deja de ofrecerse: las organizaciones que ya lo tenían lo conservan, pero
  no puede elegirse en altas nuevas.
- El día límite de pago es menor que el día de corte (por ejemplo, corte el 25 y pago el 5): se
  acepta y se interpreta como el día de pago del mes siguiente al corte.
- La búsqueda no encuentra coincidencias: el listado se devuelve vacío.

## Requirements *(mandatory)*

### Functional Requirements

**Acceso**

- **FR-001**: El sistema DEBE permitir el acceso a esta funcionalidad únicamente a usuarios con rol
  SUPER_ADMIN y rechazar cualquier operación de usuarios ADMIN, ASISTENTE o sin sesión válida.
- **FR-002**: El rechazo por falta de permisos NO DEBE revelar si una organización existe ni
  ninguno de sus datos.

**Alta**

- **FR-003**: El SUPER_ADMIN DEBE poder dar de alta una organización capturando:
  - Datos generales obligatorios: nombre comercial, nombre de contacto, correo y teléfono.
  - Dirección (opcional): calle, número, colonia, municipio o alcaldía, estado y código postal.
  - Logotipo (opcional).
  - Datos fiscales obligatorios: RFC, razón social, régimen fiscal y código postal fiscal.
  - Al menos un módulo habilitado, elegido del catálogo de módulos disponibles.
  - Día de corte y día límite de pago de la suscripción.
  - Nombre y correo del primer usuario ADMIN.
- **FR-004**: El sistema DEBE validar que el RFC tenga un formato válido de persona moral
  (12 caracteres) o de persona física (13 caracteres).
- **FR-005**: El sistema DEBE rechazar el alta o la modificación si el RFC ya pertenece a otra
  organización de la plataforma, sin importar su estatus.
- **FR-006**: El sistema DEBE validar que el régimen fiscal pertenezca al catálogo vigente de
  regímenes fiscales del SAT.
- **FR-007**: El sistema DEBE validar el formato del correo, que el teléfono tenga 10 dígitos y que
  los códigos postales tengan 5 dígitos.
- **FR-008**: El sistema DEBE validar que el día de corte y el día límite de pago sean números
  enteros entre 1 y 28.
- **FR-009**: El sistema DEBE aceptar como logotipo únicamente archivos PNG o JPG de hasta 2 MB,
  verificando el tipo real del archivo y no sólo su extensión.
- **FR-010**: Al completar el alta, el sistema DEBE asignar a la organización un identificador de
  tenant único en la plataforma, generado aleatoriamente y sin relación con los datos de la
  organización.
- **FR-011**: El identificador de tenant DEBE ser inmutable durante toda la vida de la
  organización.
- **FR-012**: Cada organización DEBE tener un espacio de datos propio y aislado, identificado por
  su identificador de tenant. Ese espacio empieza a recibir datos cuando los módulos de operación,
  que llegan en funcionalidades posteriores, guardan su primer dato.
- **FR-013**: Al completar el alta, el sistema DEBE registrar al primer usuario ADMIN de la
  organización y enviarle una invitación al correo capturado para que active su cuenta.
- **FR-014**: El sistema DEBE rechazar el alta si el correo del primer ADMIN ya pertenece a un
  usuario existente de la plataforma.
- **FR-015**: El alta DEBE ser atómica: si cualquiera de sus pasos falla, no debe quedar ninguna
  organización ni usuario registrados a medias.
- **FR-016**: El alta DEBE ser idempotente ante reintentos de la misma solicitud: un reintento no
  debe crear una segunda organización.
- **FR-017**: Toda organización recién dada de alta DEBE quedar con estatus "activa".

**Consulta y listado**

- **FR-018**: El SUPER_ADMIN DEBE poder ver un listado paginado de organizaciones con, al menos,
  nombre comercial, RFC, estatus y fecha de alta.
- **FR-019**: El listado DEBE permitir buscar por texto parcial en nombre comercial, razón social o
  RFC, sin distinguir mayúsculas, minúsculas ni acentos.
- **FR-020**: El listado DEBE permitir filtrar por estatus (activa, deshabilitada o todas). Por
  defecto devuelve todas.
- **FR-021**: El SUPER_ADMIN DEBE poder consultar el detalle completo de una organización,
  incluidos su identificador de tenant y sus módulos habilitados.

**Modificación**

- **FR-022**: El SUPER_ADMIN DEBE poder modificar todos los datos capturados en el alta, excepto el
  identificador de tenant y el primer usuario ADMIN, aplicando las mismas validaciones del alta.
- **FR-023**: El sistema DEBE impedir que se guarde una organización sin al menos un módulo
  habilitado.
- **FR-024**: Al quitar un módulo a una organización, el módulo DEBE quedar deshabilitado para
  ella y la información ya generada en él DEBE conservarse. Cómo cada módulo impide su uso cuando
  no está habilitado se define en la funcionalidad de ese módulo.
- **FR-025**: El sistema DEBE detectar modificaciones simultáneas sobre la misma organización y
  evitar que una sobrescriba a otra sin aviso.
- **FR-026**: El SUPER_ADMIN DEBE poder reenviar la invitación al primer ADMIN mientras éste no
  haya activado su cuenta.

**Deshabilitación y rehabilitación**

- **FR-027**: El SUPER_ADMIN DEBE poder deshabilitar una organización activa. Deshabilitar NO DEBE
  borrar ningún dato de la organización.
- **FR-028**: A partir de la deshabilitación, el sistema DEBE rechazar todo nuevo inicio de sesión
  y toda operación de los usuarios de esa organización, incluidas las de usuarios que ya tenían una
  sesión abierta.
- **FR-029**: El SUPER_ADMIN DEBE poder rehabilitar una organización deshabilitada; sus usuarios
  DEBEN recuperar el acceso a todos sus datos tal como estaban.

**Datos personales**

- **FR-030**: Los datos personales de contacto y del ADMIN (nombres, correos, teléfonos) NO DEBEN
  aparecer en los registros técnicos de operación del sistema.
- **FR-031**: La invitación al primer ADMIN DEBE incluir el enlace al aviso de privacidad de la
  plataforma.

### Key Entities *(include if feature involves data)*

- **Organización**: cliente de la plataforma (una administradora de condominios). Atributos:
  identificador de tenant, nombre comercial, contacto (nombre, correo, teléfono), dirección
  opcional, logotipo opcional, datos fiscales, módulos habilitados, día de corte, día límite de
  pago, estatus (activa o deshabilitada) y fechas de alta y última modificación. Vive en el
  registro de la plataforma, accesible sólo para SUPER_ADMIN.
- **Datos fiscales**: RFC (único en la plataforma), razón social, régimen fiscal y código postal
  fiscal de la organización.
- **Módulo**: funcionalidad de la plataforma que una organización puede tener habilitada. Proviene
  de un catálogo global compartido por todas las organizaciones; una organización tiene uno o
  varios módulos habilitados.
- **Usuario ADMIN inicial**: primer usuario de la organización, con nombre y correo; administra los
  datos de su propia organización. Pertenece a una sola organización.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El sistema completa el alta de una organización, con su primer ADMIN, en menos de
  10 segundos en el 95 % de los casos.
- **SC-002**: El primer ADMIN recibe la invitación en menos de 5 minutos después del alta en el
  99 % de los casos.
- **SC-003**: Tras deshabilitar una organización, el 100 % de las operaciones e inicios de sesión de
  sus usuarios son rechazados a partir de su siguiente intento.
- **SC-004**: Con 1,000 organizaciones registradas, la búsqueda y el filtrado devuelven resultados
  en menos de 2 segundos.
- **SC-005**: El 0 % de los intentos de usuarios ADMIN, ASISTENTE o sin sesión logra ver u operar
  datos del registro de organizaciones.
- **SC-006**: Ningún alta fallida deja organizaciones ni usuarios registrados a medias.

## Assumptions

- Ya existe al menos un usuario SUPER_ADMIN en la plataforma; su creación queda fuera de esta
  funcionalidad.
- El catálogo global de módulos ya existe y está precargado; su administración (alta, cambio o
  retiro de módulos) queda fuera de esta funcionalidad.
- El catálogo de regímenes fiscales del SAT está disponible para validación.
- El día de corte y el día límite de pago sólo se registran en esta funcionalidad; ningún proceso
  de cobro o suspensión los utiliza todavía.
- Los datos de una organización deshabilitada se conservan indefinidamente. La política de
  conservación y cancelación de datos personales que exige la LFPDPPP se definirá en una
  funcionalidad posterior y DEBE estar implementada antes de operar con datos reales en `prod`.
- El texto del aviso de privacidad y su URL los proporciona el área legal del negocio; esta
  funcionalidad sólo incluye el enlace en la invitación.
- La invitación al ADMIN vence a los 7 días y puede reenviarse.
- Esta funcionalidad cubre sólo el backend. La interfaz de usuario se especifica y construye en el
  repositorio del frontend (constitución, principio I). En esta funcionalidad, el ADMIN sólo puede
  activar su cuenta e iniciar sesión.
- El primer ADMIN no puede cambiarse ni eliminarse desde esta funcionalidad; la gestión de
  usuarios de la organización corresponde a una funcionalidad posterior.
- El teléfono es un número nacional de México de 10 dígitos.
- El listado devuelve 20 organizaciones por página por defecto, ordenadas de la más reciente a la
  más antigua.
- Fuera de alcance: interfaz de usuario, cobro automático de la suscripción, suspensión por falta
  de pago, gestión de usuarios adicionales de la organización, administración del catálogo de
  módulos e historial o auditoría de cambios. El historial aparecía en la descripción original y el usuario lo descartó
  el 2026-10-28.
