# Research: Alta de organizaciones

**Feature**: `001-alta-organizaciones` | **Date**: 2026-10-28

Cada decisión resuelve una incógnita del Technical Context o fija una práctica para una
dependencia. Las marcadas con **⚠️ Confirmar** tienen un impacto de costo o de operación que
conviene validar con el responsable del proyecto antes de implementar.

---

## 1. Organización de stacks de Serverless Framework

- **Decision**: tres tipos de stack, todos con Serverless Framework (principio I).
  - `infra/bootstrap`: proveedor OIDC y roles de despliegue, aplicado una vez por cuenta según la
    excepción del principio X. Serverless Framework lo despliega con recursos de CloudFormation en
    la sección `resources:`.
  - `infra/shared`: identidad y API.
  - Un stack por módulo en `backend/modules/<modulo>`.

  El hosting del frontend no está en este repositorio (constitución 2.0.0, principio I).

  Los módulos importan de `shared` el id de la HTTP API y del autorizador mediante
  `${cf:condo-shared-${stage}.HttpApiId}`.

  El stack de arranque crea el bucket de despliegue que usan los demás stacks
  (`provider.deploymentBucket.name`), para que los permisos del rol de despliegue apunten a un
  recurso conocido. También define el permissions boundary `condo-boundary`, obligatorio para todo
  rol que creen los stacks del pipeline.
- **Rationale**: cumple el principio II (cada módulo se despliega por separado) y mantiene cada
  stack lejos del límite de 500 recursos. Una sola HTTP API compartida da un solo dominio y una
  sola configuración de CORS al frontend.
- **URLs del frontend**: las callbacks del app client de Cognito y los orígenes de CORS se declaran
  por ambiente en `params` de `infra/shared/serverless.yml` (`frontendUrls`). En `dev` incluyen
  `http://localhost:4200`. Quedan versionadas en el repositorio, sin cambios manuales en AWS.
- **Alternatives considered**:
  - Un solo `serverless.yml`: acopla los despliegues y crece hacia el límite de recursos.
  - Una API por módulo: varios dominios, CORS y autorizadores duplicados.

## 2. Versión de Serverless Framework

- **Decision**: Serverless Framework v4. La clave de licencia se guarda como **secreto del
  environment de GitHub** (`SERVERLESS_LICENSE_KEY`, uno por environment) y el workflow de
  despliegue la expone como variable de entorno, de donde v4 la lee. Para el despliegue único del
  bootstrap, el administrador usa la misma variable en su sesión, sin guardarla en archivos.
- **Interpretación del principio V**: los secretos cifrados de GitHub cuentan como "gestor de
  secretos" para las credenciales que sólo usa el pipeline. Es la única credencial del sistema
  guardada ahí; la conexión a MongoDB usa IAM y no tiene contraseña (decisión 6).
- **Rationale**: v3 ya no recibe mantenimiento. Guardar la clave en GitHub evita crear a mano un
  recurso de AWS para ella, que prohíbe el principio I, sin necesidad de enmendar la constitución.
- **Alternatives considered**:
  - v3: sin mantenimiento.
  - Forks comunitarios de v3: menor soporte.
- **⚠️ Confirmar**: v4 requiere licencia de pago para organizaciones con ingresos anuales
  superiores a 2 millones de dólares.

## 3. Tipo de API Gateway y autorización

- **Decision**: API Gateway **HTTP API** (v2) con autorizador JWT nativo contra el user pool de
  Cognito, validando el `client_id` de **access tokens**. Cada Lambda vuelve a verificar el grupo
  (`cognito:groups`) en cada ruta.
- **Rationale**: es más barata y con menor latencia que REST API. El autorizador JWT no requiere
  una Lambda. La verificación en la Lambda cumple "autorización en cada endpoint" aunque el
  autorizador se configure mal.
- **Alternatives considered**:
  - REST API con Cognito authorizer: mayor costo, sin ventaja para este caso.
  - ID tokens como bearer: no es la práctica recomendada para APIs.

## 4. Cómo llega el `tenant_id` al token

- **Decision**: atributo personalizado `custom:tenant_id` **no modificable** en Cognito, que el app
  client no puede escribir. Un disparador **Pre Token Generation V2** lo copia como claim
  `tenant_id` al access token.
- **Rationale**: los access tokens de Cognito no incluyen atributos personalizados por defecto. El
  claim queda firmado por Cognito y el cliente no puede alterarlo (principio III).
- **Alternatives considered**:
  - Buscar el tenant por `sub` en una tabla de mapeo: requeriría que los usuarios de tenant leyeran
    la base de plataforma, lo que prohíbe el principio III.
  - Usar ID tokens: ver decisión 3.
- **⚠️ Confirmar**: Pre Token Generation V2 para access tokens requiere el plan de funcionalidades
  **Essentials** de Cognito, más caro por usuario activo mensual que el plan Lite.

## 5. Bloqueo inmediato al deshabilitar (FR-028, SC-003)

- **Decision**: dos barreras.
  1. El mismo disparador Pre Token Generation lee el `estatus` de la organización en
     `platform.organizaciones` y rechaza la emisión de tokens si no está `activa`. Este disparador
     corre tanto en el inicio de sesión como en la renovación con refresh token.
  2. `condo_core.auth.require_active_tenant()` lee ese mismo campo en **cada** petición de un
     usuario de tenant, sin caché, y responde 403 `ORGANIZACION_DESHABILITADA`. Lo usarán los
     módulos de tenant de funcionalidades posteriores; en esta se entrega con sus pruebas.
- **Rationale**: un access token ya emitido sigue siendo válido hasta que vence; sólo la
  verificación por petición garantiza el rechazo desde el siguiente intento. Es una lectura por
  `_id` que proyecta sólo `estatus`, de costo despreciable. El principio III permite al backend
  leer el estatus del propio tenant.
- **Alternatives considered**:
  - `AdminUserGlobalSignOut` a todos los usuarios de la organización: sólo revoca refresh tokens,
    no access tokens vigentes.
  - Caché de estatus de 60 s: incumple SC-003.

## 6. Conexión a MongoDB Atlas y mínimo privilegio

- **Decision**: autenticación **IAM (`MONGODB-AWS`)**. Cada rol de ejecución de Lambda, con nombre
  fijo por módulo y ambiente, se mapea a un usuario de base de datos en Atlas con un rol
  personalizado.

  | Rol de Lambda | Privilegios en Atlas |
  |---|---|
  | `organizaciones` | `readWrite` en `platform.organizaciones`. `find` en `shared.*`. Ningún privilegio sobre bases `t_*`. |
  | `cognito-triggers` | `find` en `platform.organizaciones`. |
  | Futuros módulos de tenant (referencia) | `find` en `platform.organizaciones`, `find` en `shared.*`, `readWrite` en cualquier base. El aislamiento por `t_<tenant_id>` se aplica en `condo_core.tenancy`. |

  La URI del clúster (por ejemplo,
  `mongodb+srv://<cluster>.mongodb.net/?authMechanism=MONGODB-AWS&authSource=$external`) no
  contiene credenciales, así que se declara por ambiente en `params.mongodbUri` de
  `infra/shared/serverless.yml`, versionada en el repositorio. `shared` la publica como salida
  `MongoDbUri` y los módulos la reciben en la variable de entorno `MONGODB_URI`. No se usa SSM, para
  no crear recursos de AWS a mano (principio I).
- **Rationale**: sin contraseñas de base de datos que rotar ni guardar. El código del disparador y
  de `require_active_tenant()` proyecta sólo `estatus`, pero Atlas no restringe permisos por
  campo, así que su rol puede leer la colección completa. Se acepta para no mantener una colección
  de estatus aparte. Atlas tampoco permite comodines en nombres de base, por lo que los módulos de
  tenant tendrán privilegios sobre cualquier base y el aislamiento se garantiza en código y con
  pruebas.
- **Alternatives considered**:
  - Usuario y contraseña en Secrets Manager: funciona, pero agrega rotación y un secreto más.
  - Crear un rol de Atlas por tenant mediante la Admin API de Atlas: mucha complejidad para la
    escala actual.

## 7. Red entre Lambda y Atlas

- **Decision**:
  - `prod`: Lambdas en una VPC con subredes privadas, Atlas **PrivateLink** y NAT Gateway para
    llamar a Cognito y SES.
  - `dev`: Lambdas sin VPC; lista de acceso de Atlas abierta, protegida por autenticación IAM y TLS
    obligatorio.

  La VPC, el endpoint de PrivateLink y el NAT se definen en `infra/shared` sólo cuando
  `stage == prod`.
- **Rationale**: en `prod` el tráfico a la base no sale a internet. En `dev` se evita el costo fijo
  del NAT, y no se cargan datos reales.
- **Alternatives considered**:
  - VPC en ambos ambientes: duplica el costo fijo.
  - Sin VPC en `prod`: la base queda expuesta a internet.
- **⚠️ Confirmar**: el NAT Gateway y PrivateLink tienen costo mensual fijo. También hay que
  confirmar que `dev` nunca tendrá datos reales.

## 8. Formato del `tenant_id` y nombre de la base

- **Decision**: `tenant_id = secrets.token_hex(16)` (32 caracteres hexadecimales en minúsculas,
  generados con el CSPRNG del sistema). Nombre de la base: `t_<tenant_id>` (34 caracteres). El
  `tenant_id` es también el `_id` del documento en `platform.organizaciones` y el identificador
  público en la API.
- **Rationale**: cumple lo pedido por el usuario, no se relaciona con los datos de la organización
  (FR-010) y queda por debajo de los límites de longitud de nombre de base de Atlas. El prefijo
  distingue las bases de tenant de `platform` y `shared`.
- **Alternatives considered**:
  - UUID con guiones: más largo, y los guiones complican los nombres de base.
  - Derivarlo del RFC: filtraría información y rompería FR-010.

## 9. Atomicidad e idempotencia del alta (FR-015, FR-016)

- **Decision**: saga con compensación, guiada por un encabezado obligatorio `Idempotency-Key`.

  Verificaciones previas sin efectos secundarios:
  - Validación del cuerpo de la petición.
  - El RFC no existe en la plataforma.
  - El correo del ADMIN no existe en Cognito (`AdminGetUser`).

  Pasos:
  1. Insertar la organización con estatus `aprovisionando`, junto con el `idempotencyKey` y el
     hash del cuerpo. Los índices únicos protegen el RFC y la llave de idempotencia.
  2. Crear el usuario ADMIN en Cognito (`AdminCreateUser` con `custom:tenant_id` y envío de
     invitación) y agregarlo al grupo `ADMIN`. Si el usuario ya existe con el mismo tenant, se
     continúa.
  3. Cambiar el estatus a `activa` y guardar `adminInicial.sub` y `adminInicial.invitacionEnviadaEn`,
     que no existen hasta completar el paso 2.

  La base `t_<tenant_id>` no se crea en el alta: MongoDB la crea cuando un módulo de operación
  guarda su primer dato.

  Si cualquier paso falla, se compensa en orden inverso (eliminar el usuario de Cognito creado y
  borrar el documento) y se responde 503 `ALTA_FALLIDA`.

  Un **reconciliador** programado cada 15 minutos sobre la misma Lambda compensa las altas que
  lleven más de 15 minutos en `aprovisionando`, por ejemplo si la Lambda terminó por timeout.

  Comportamiento ante reintentos:
  - Misma llave y mismo cuerpo, con la organización ya `activa`: responde 201 con la misma
    organización.
  - Misma llave con un cuerpo distinto: 422 `IDEMPOTENCY_KEY_REUTILIZADA`.
- **Rationale**: MongoDB y Cognito no comparten una transacción. La saga con compensación y el
  reconciliador garantizan que no queden altas a medias, como exige SC-006. Mientras la
  organización está en `aprovisionando`, el disparador de Cognito ya rechaza a su ADMIN, porque
  sólo acepta organizaciones `activa`.
- **Alternatives considered**:
  - Step Functions: agrega un servicio y recursos por un flujo de 3 pasos.
  - Aprovisionamiento asíncrono con estado visible: complica la experiencia y la especificación
    pide un resultado inmediato.

## 10. Invitación del ADMIN

- **Decision**: el user pool usa el correo como nombre de usuario. La invitación se envía con
  `AdminCreateUser`, usando una plantilla en español configurada en
  `AdminCreateUserConfig.InviteMessageTemplate`, con vigencia de 7 días
  (`TemporaryPasswordValidityDays`). La plantilla incluye el enlace al aviso de privacidad,
  tomado de `params.avisoPrivacidadUrl` en `infra/shared/serverless.yml` (FR-031). El reenvío usa
  `MessageAction=RESEND`. En `prod`, Cognito envía los correos con SES desde un dominio verificado.
- **Rationale**: es el flujo nativo de Cognito, sin manejo propio de contraseñas (principio I). El
  managed login resuelve el cambio de contraseña temporal en el primer acceso.
- **Alternatives considered**:
  - Correo propio con enlace y token: implica manejar credenciales, lo que prohíbe el principio I.
- **SES en `prod`, en dos fases**: la identidad de dominio se define como
  `AWS::SES::EmailIdentity` en `infra/shared/serverless.yml`, sólo en `prod` (dominio como
  parámetro). El primer despliegue usa `sesVerificado: false`, con el correo por defecto de
  Cognito. Después se publican en el DNS los registros DKIM que devuelve la identidad (si el DNS es
  Route 53, se definen en el mismo stack), y cuando SES marca el dominio como verificado se cambia
  `sesVerificado` a `true` en un PR, lo que activa `EmailConfiguration: DEVELOPER`.
- **⚠️ Confirmar**: hace falta un dominio de correo propio para `prod`. El correo por defecto de
  Cognito, que usa `dev`, está limitado a pocos envíos por día.

## 11. Logotipo

- **Decision**: endpoint aparte `PUT /organizaciones/{tenantId}/logo` con cuerpo JSON
  (`contentType` + contenido en base64, de hasta 2 MB decodificados). La Lambda verifica los magic
  bytes (PNG `89 50 4E 47`, JPEG `FF D8 FF`) y el tamaño, y guarda en un bucket S3 privado del
  módulo `organizaciones` (`logos/<tenant_id>/<uuid>.<ext>`), con cifrado SSE-S3, TLS obligatorio
  y acceso público bloqueado. Las lecturas usan URLs firmadas de 5 minutos.

  Indicación para quien consuma la API: subir el logotipo justo después de crear la organización.
  Si esa subida falla, la organización ya existe y el logotipo puede reintentarse, lo cual es válido
  porque es opcional.
- **Rationale**: valida en un solo lugar y en el servidor (FR-009). 2 MB en base64 (unos 2.7 MB)
  caben en el límite de 6 MB de carga de Lambda.
- **Alternatives considered**:
  - URL firmada para subir directo a S3: el tipo real se validaría hasta un segundo paso, lo que
    agrega estados intermedios.
  - Guardar el logotipo en MongoDB: infla los documentos de plataforma.

## 12. Módulos habilitados

- **Decision**: el catálogo vive en `shared.modulos`. Las claves elegidas se guardan sólo en
  `platform.organizaciones.modulosHabilitados`. Esta funcionalidad no incluye ningún mecanismo para
  que los módulos de tenant consulten si están habilitados.
- **Rationale**: todavía no existe ningún módulo de tenant que lo necesite. Cómo cada módulo
  impide su uso cuando no está habilitado se decide en la funcionalidad de ese módulo (FR-024).
- **Pendiente para funcionalidades posteriores**: el principio III sólo permite a los usuarios de
  tenant leer el estatus en la base de plataforma. Hay tres opciones para que un módulo sepa si
  está habilitado:
  - Incluir los módulos en el token: el cambio tarda hasta que se renueva el token.
  - Guardar una copia en la base del tenant.
  - Enmendar la constitución para permitir también la lectura de `modulosHabilitados`.

## 13. Búsqueda sin distinguir acentos (FR-019)

- **Decision**: campo derivado `busqueda` con nombre comercial, razón social y RFC normalizados
  (minúsculas, sin acentos, NFKD). La búsqueda usa una expresión regular de subcadena con el texto
  del usuario normalizado y **escapado** (`re.escape`). La paginación es por número de página, con
  20 resultados por defecto y un máximo de 100, ordenada por `creadoEn` descendente con índice
  `{estatus: 1, creadoEn: -1}`.
- **Rationale**: con unas 1,000 organizaciones, un barrido con expresión regular sobre un campo
  corto responde en milisegundos. Escapar la entrada evita inyección de expresiones regulares y
  ataques ReDoS.
- **Alternatives considered**:
  - Atlas Search: más infraestructura de la que esta escala necesita.
  - Collation con strength 1: no resuelve la búsqueda por subcadena.

## 14. Edición simultánea (FR-025)

- **Decision**: campo entero `version` en el documento. `GET` devuelve `ETag: "<version>"`. Las
  operaciones de escritura exigen `If-Match`: sin él se responde 428; si no coincide, 412
  `VERSION_DESACTUALIZADA`. La actualización filtra por `{_id, version}`.
- **Rationale**: es control de concurrencia optimista con semántica HTTP estándar.
- **Alternatives considered**:
  - Bloqueos pesimistas: complican la experiencia y requieren limpieza.

## 15. Validaciones fiscales

- **Decision**:
  - RFC en mayúsculas.
    - Persona moral: `^[A-ZÑ&]{3}\d{6}[A-Z\d]{3}$`.
    - Persona física: `^[A-ZÑ&]{4}\d{6}[A-Z\d]{3}$`.
    - Fecha embebida válida.
    - Se rechazan los RFC genéricos `XAXX010101000` y `XEXX010101000`.
  - El régimen fiscal debe existir en `shared.regimenes_fiscales`, estar vigente y aplicar al tipo
    de persona deducido de la longitud del RFC.
  - Código postal fiscal: 5 dígitos.
- **Rationale**: atrapa la mayoría de los errores de captura sin depender de servicios externos del
  SAT.
- **Alternatives considered**:
  - Validar el dígito verificador del RFC: viable más adelante, pero no lo pide la especificación.
  - Consultar la lista del SAT en línea: dependencia externa frágil.

## 16. Logs estructurados (principio VIII)

- **Decision**: el `Logger` de Powertools agrega en cada línea:
  - `tenant_id`: el del token, o `platform` si es SUPER_ADMIN.
  - `target_tenant_id`: la organización sobre la que actúa un SUPER_ADMIN.
  - `request_id`: el id de petición de API Gateway.
  - `lambda_request_id`.

  `log_event=False`. Nunca se registran cuerpos de petición ni de respuesta. Los errores registran
  códigos de dominio, no valores.

  Retención en CloudWatch: 30 días en `dev` y 90 días en `prod`.
- **Rationale**: permite diagnosticar por organización sin exponer datos personales (principio VI).

## 17. Pruebas

- **Decision**:
  - Backend: pytest por módulo, con `--cov-fail-under=80` ejecutado por separado para `core`,
    `organizaciones` y `cognito-triggers`. moto para Cognito y S3. testcontainers con
    `mongo:8`.
  - Pruebas de aislamiento entre tenants:
    - `condo_core.tenancy` elige la base sólo por el claim `tenant_id` e ignora cualquier tenant
      enviado en la ruta, la consulta, los encabezados o el cuerpo.
    - Al dar de alta las organizaciones A y B, el ADMIN de A queda con `custom:tenant_id = A` y
      su token sólo lleva A.
    - Deshabilitar A no cambia el estatus ni el acceso de B.
  - Prueba de autorización en `organizaciones`: todos los endpoints responden 403 a ADMIN y
    ASISTENTE, y 401 sin token.
- **Rationale**: cumple el principio IV y la puerta de calidad de cobertura por módulo.
- **Alternatives considered**:
  - mongomock: no reproduce de forma fiel los índices únicos.

## 18. Lo que el backend entrega al frontend para autenticarse

- **Decision**: un app client **público** de Cognito, sin secreto, con Authorization Code + PKCE
  contra el managed login, y callbacks tomadas de `params.frontendUrls`. El stack `shared` publica
  como salidas `UserPoolId`, `UserPoolClientId`, `CognitoDomain` y `ApiUrl`, que el repositorio del
  frontend usa para configurarse. Cómo el frontend implementa el inicio de sesión se decide allá
  (principio IX).
- **Rationale**: es el flujo estándar para SPAs y no requiere secretos en el cliente. El managed
  login resuelve el cambio de contraseña temporal de la invitación.
- **Alternatives considered**:
  - App client con secreto: un SPA no puede guardarlo de forma segura.

## 19. CI/CD

- **Decision**:
  - `ci.yml` en cada PR: lint, mypy, pruebas con cobertura por módulo (matriz), CodeQL (Python) y
    `pip-audit`.
  - `_deploy.yml`, workflow reutilizable: `shared` → módulos → `seed_catalogos.py`, con
    `SERVERLESS_LICENSE_KEY` tomado de los secretos del environment.
  - `deploy-dev.yml` en push a `main` → `_deploy.yml` con environment `dev`.
  - `deploy-prod.yml` con `workflow_dispatch` sobre un tag → `_deploy.yml` con environment `prod`,
    que tiene revisores obligatorios.
  - El stack `infra/bootstrap` **no** forma parte de estos workflows: lo aplica un administrador
    una sola vez por cuenta (principio X).
  - `crear-super-admin.yml` con `workflow_dispatch` y aprobación del environment.
  - Autenticación con `aws-actions/configure-aws-credentials` usando OIDC. El ARN del rol es una
    variable de cada environment de GitHub.
  - La relación de confianza de cada rol se limita a
    `repo:<org>/<repo>:environment:<dev|prod>`.
- **Rationale**: cumple el principio X y las puertas de calidad. Restringir la confianza por
  environment impide que una rama cualquiera despliegue a `prod`.
- **⚠️ Confirmar**: se recomienda una cuenta de AWS por ambiente. El plan funciona igual con una
  sola cuenta y dos roles.

## 20. Región de AWS

- **Decision**: `us-east-1` por defecto, como parámetro de cada stack.
- **Rationale**: es donde están disponibles todos los servicios usados (Cognito Essentials, SES,
  PrivateLink con Atlas). La LFPDPPP no exige que los datos residan en México.
- **⚠️ Confirmar**: si se prefiere `mx-central-1`, hay que verificar la disponibilidad de Cognito
  Essentials, SES y Atlas en esa región.

## 21. Cumplimiento de la LFPDPPP (principio VI)

- **Decision**: esta funcionalidad trata datos personales de dos personas por organización: el
  contacto (nombre, correo y teléfono) y el primer ADMIN (nombre y correo). Las obligaciones se
  reparten así:

  | Obligación | En esta funcionalidad | Cómo |
  |---|---|---|
  | Minimización | Sí | Sólo se capturan los campos de la especificación; dirección opcional. |
  | Aviso de privacidad | Parcial | La invitación al ADMIN incluye el enlace al aviso (FR-031). El aviso al contacto se entrega en el proceso comercial de contratación, fuera del sistema. |
  | Medidas de seguridad | Sí | Cifrado en tránsito y en reposo, acceso exclusivo de SUPER_ADMIN, mínimo privilegio y ningún dato personal en logs (FR-030). |
  | Rectificación | Sí | El SUPER_ADMIN corrige los datos con la modificación (US4). |
  | Acceso | Sí | El SUPER_ADMIN consulta los datos con el detalle (US3) para atender una solicitud. |
  | Cancelación, oposición y conservación | No | Requiere una política de conservación y borrado que se define en una funcionalidad posterior, obligatoria antes de operar con datos reales en `prod`. |

- **Rationale**: cubre en esta funcionalidad lo que depende del sistema y deja explícito lo que
  falta, sin bloquear el alta.
- **⚠️ Confirmar**: este reparto es técnico, no una opinión legal. El área legal debe validar las
  obligaciones aplicables de la ley vigente, el texto del aviso de privacidad y la política de
  conservación.

