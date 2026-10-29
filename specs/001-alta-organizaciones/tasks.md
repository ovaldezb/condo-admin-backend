---

description: "Task list for feature 001-alta-organizaciones"
---

# Tasks: Alta de organizaciones

**Input**: Design documents from `/specs/001-alta-organizaciones/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: se incluyen porque la constitución (principio IV) exige pruebas unitarias, de
integración y de aislamiento entre tenants, con 80 % de cobertura por módulo. Dentro de cada
historia, las pruebas se escriben primero y deben fallar antes de implementar.

**Organization**: las tareas se agrupan por historia de usuario, en orden de prioridad:
US1 (P1) → US5 (P1) → US2 (P2) → US3 (P2) → US4 (P3). Los números US conservan la numeración de
spec.md. Este repositorio es sólo de backend (constitución 2.0.0, principio I).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Infraestructura compartida: `infra/`
- Backend: `backend/core/` (paquete `condo_core`), `backend/modules/organizaciones/`, `backend/scripts/`
- Disparador de Cognito: `infra/shared/src/cognito_triggers/`
- Pipelines: `.github/workflows/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Crear la estructura de carpetas de plan.md (`infra/bootstrap`, `infra/atlas`, `infra/shared/src/cognito_triggers/tests`, `infra/shared/tests`, `backend/core/src/condo_core`, `backend/core/tests`, `backend/modules/organizaciones/src/organizaciones`, `backend/modules/organizaciones/tests/unit`, `backend/modules/organizaciones/tests/integration`, `backend/scripts`, `.github/workflows`) y un `.gitignore` raíz para Python, Node, `.serverless/`, `coverage/` y `.venv/`
- [ ] T002 Crear el workspace de uv en `backend/pyproject.toml` con miembros `core` y `modules/organizaciones`, `requires-python = "==3.12.*"` y dependencias de desarrollo `pytest`, `pytest-cov`, `moto[cognitoidp,s3]`, `testcontainers[mongodb]`, `ruff`, `mypy` y `pip-audit`
- [ ] T003 [P] Crear `backend/core/pyproject.toml` (paquete `condo-core`, layout `src/`) con dependencias `aws-lambda-powertools`, `pydantic>=2`, `pymongo[aws]` y `boto3`
- [ ] T004 [P] Crear `backend/modules/organizaciones/pyproject.toml` (paquete `organizaciones`, layout `src/`) que dependa de `condo-core` como fuente del workspace, más `email-validator`
- [ ] T005 [P] Crear `infra/shared/pyproject.toml` (paquete `cognito-triggers`, código en `src/cognito_triggers`) que dependa de `condo-core` por ruta `../../backend/core`, con las mismas dependencias de desarrollo de T002 más `pyyaml`
- [ ] T006 [P] Configurar ruff (`line-length = 100`; reglas `E`, `F`, `I`, `B`, `S`, `UP`) y mypy (`strict = true`) en `backend/pyproject.toml` e `infra/shared/pyproject.toml`
- [ ] T007 [P] Crear `package.json` en la raíz del repositorio con `serverless@4` y `serverless-python-requirements` fijados a versiones exactas, para los despliegues

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Infraestructura AWS

- [ ] T008 Escribir `infra/bootstrap/serverless.yml` (servicio `condo-bootstrap`, sin funciones, recursos en `resources:`) con:
  - El proveedor OIDC `token.actions.githubusercontent.com`.
  - Los roles `condo-deploy-dev` y `condo-deploy-prod`, cada uno con confianza limitada a `aud = sts.amazonaws.com` y `sub = repo:${param:githubOrg}/${param:githubRepo}:environment:<dev|prod>`.
  - Permisos de mínimo privilegio (principio V), en una política por rol:
    - `cloudformation:*` sólo sobre `arn:aws:cloudformation:*:*:stack/condo-*/*`, más `cloudformation:ValidateTemplate`.
    - `iam:CreateRole`, `DeleteRole`, `GetRole`, `PassRole`, `TagRole`, `PutRolePolicy`, `DeleteRolePolicy`, `AttachRolePolicy` y `DetachRolePolicy` sólo sobre `arn:aws:iam::*:role/condo-*`, con un permissions boundary obligatorio (`condo-boundary`, definido en este mismo stack) para todo rol que creen, exigido con la condición `iam:PermissionsBoundary`.
    - `condo-boundary` permite sólo lo que necesitan las Lambdas: CloudWatch Logs, `cognito-idp:Admin*` sobre user pools de la cuenta, S3 sobre buckets `condo-*` y las interfaces de red de VPC (`ec2:CreateNetworkInterface` y relacionadas) en prod. Niega `iam:*` y `sts:AssumeRole`.
    - Lambda, API Gateway, Cognito, S3, CloudWatch Logs y EventBridge, limitados a recursos con prefijo `condo-` donde el servicio admite ARN por nombre.
    - S3 (`GetObject`, `PutObject`, `DeleteObject`, `ListBucket`, `GetBucketLocation`) sólo sobre el bucket de despliegue que crea este mismo stack.
    - EC2 (VPC, subredes, NAT, endpoints, security groups) y SES sólo en el rol `condo-deploy-prod`.
    - Sin `iam:CreateUser`, sin `iam:CreateAccessKey` y sin `*:*`.
  - El bucket de despliegue `condo-deployments-${aws:accountId}-${aws:region}`: privado, BlockPublicAccess, SSE-S3, versionado y política que niegue `aws:SecureTransport = false`. Salida `DeploymentBucketName`.
- [ ] T009 [P] Escribir `infra/bootstrap/README.md` con:
  - El procedimiento único por cuenta: un administrador ejecuta `npx serverless deploy` en `infra/bootstrap` con sus credenciales y con `SERVERLESS_LICENSE_KEY` como variable de entorno de su sesión, sin guardarla en archivos.
  - Que el bootstrap mismo usa el bucket por defecto de Serverless: es el único stack que se despliega antes de que exista `condo-deployments-*`.
  - La referencia a la excepción del principio X (constitución 2.0.0).
  - La regla de que cualquier cambio posterior a este stack pasa por revisión en el repositorio.
- [ ] T010 Escribir el user pool de Cognito en `infra/shared/serverless.yml` (servicio `condo-shared`):
  - `params` por stage: `frontendUrls` (lista; en `dev` incluye `http://localhost:4200`), `avisoPrivacidadUrl`, `mongodbUri` (URI de Atlas sin credenciales, research.md decisión 6) y, sólo en `prod`, `sesDomain`.
  - `provider.deploymentBucket.name: condo-deployments-${aws:accountId}-${aws:region}`.
  - `UsernameAttributes: [email]`, sin distinguir mayúsculas.
  - Atributo `custom:tenant_id` de tipo String, `Mutable: false`, longitud 32 a 32.
  - `AllowAdminCreateUserOnly: true` y `TemporaryPasswordValidityDays: 7`.
  - `InviteMessageTemplate` en español que incluya `${param:avisoPrivacidadUrl}` (FR-031).
  - `UserPoolTier: ESSENTIALS`.
  - Grupos `SUPER_ADMIN`, `ADMIN` y `ASISTENTE`.
  - App client público sin secreto, con Authorization Code + PKCE, callbacks y logout URLs desde `${param:frontendUrls}` y `WriteAttributes` sin `custom:tenant_id`.
  - Dominio de managed login.
  - En `prod`, un recurso `AWS::SES::EmailIdentity` para `${param:sesDomain}`.
  - Parámetro `sesVerificado` (por defecto `false`). Con `false`, `EmailConfiguration: COGNITO_DEFAULT`. Con `true`, que sólo se activa en `prod` mediante un PR después de verificar el dominio, `EmailConfiguration: DEVELOPER` con `SourceArn` de la identidad. En `dev`, siempre el correo por defecto de Cognito.
- [ ] T011 Agregar a `infra/shared/serverless.yml`:
  - La HTTP API compartida, con CORS para `${param:frontendUrls}`.
  - El autorizador JWT, con el issuer del user pool y el app client como audiencia.
  - Las salidas `HttpApiId`, `AuthorizerId`, `ApiUrl`, `UserPoolId`, `UserPoolArn`, `UserPoolClientId`, `CognitoDomain` y `MongoDbUri` (valor de `${param:mongodbUri}`). En `prod`, también los tokens DKIM de la identidad de SES.
- [ ] T012 Agregar a `infra/shared/serverless.yml` los recursos condicionados a `stage == prod` (research.md, decisión 7): VPC con 2 subredes privadas, NAT Gateway, endpoint de interfaz para Atlas PrivateLink (nombre del servicio como parámetro), security group y salidas de subredes y security group para los módulos.
- [ ] T013 Agregar a `infra/shared/serverless.yml` la función `cognito-triggers` con:
  - Python 3.12, arm64 y rol con nombre fijo `condo-cognito-triggers-${sls:stage}`, con
    `permissionsBoundary: arn:aws:iam::${aws:accountId}:policy/condo-boundary` (exigido por T008).
  - Variable de entorno `MONGODB_URI` con `${param:mongodbUri}`.
  - Conexión como disparador `PreTokenGeneration` con `LambdaVersion: V2_0`.
  - La configuración de VPC de prod.
- [ ] T014 [P] Escribir `infra/atlas/README.md` con la configuración manual de Atlas por ambiente:
  - Clúster (M10 o superior en prod).
  - Usuarios IAM mapeados a `condo-organizaciones-<stage>` y `condo-cognito-triggers-<stage>`.
  - Roles personalizados copiados literalmente de research.md, decisión 6: `organizaciones` = "`readWrite` en `platform.organizaciones`. `find` en `shared.*`. Ningún privilegio sobre bases `t_*`."; `cognito-triggers` = "`find` en `platform.organizaciones`."
  - PrivateLink en prod y lista de acceso abierta en dev.
  - Registro de la URI del clúster en `params.mongodbUri` de `infra/shared/serverless.yml` mediante un PR (sin credenciales; no se usa SSM).

### Paquete común `condo_core`

- [ ] T015 [P] Implementar `backend/core/src/condo_core/mongo.py`:
  - `MongoClient` singleton perezoso por contenedor.
  - URI leída de la variable de entorno `MONGODB_URI`.
  - `authMechanism=MONGODB-AWS` y `tls=True`, salvo que la URI indique otro mecanismo (las pruebas usan un contenedor local sin IAM).
  - Funciones `platform_db()` y `shared_db()`.
- [ ] T016 [P] Implementar `backend/core/src/condo_core/logging.py`:
  - `Logger` de Powertools con `log_event=False`.
  - `bind_request(event, claims, target_tenant_id=None)` que agregue `tenant_id` (el claim, o `"platform"` si es SUPER_ADMIN), `target_tenant_id`, `request_id` (`requestContext.requestId`) y `lambda_request_id`.
  - Nunca registra cuerpos de petición ni de respuesta.
- [ ] T017 [P] Implementar `backend/core/src/condo_core/errors.py`:
  - `DomainError(status, code, title, detail=None, errores=None)` que se convierte en respuesta `application/problem+json` con `type`, `title`, `status`, `code`, `requestId` y `errores[{campo, code, mensaje}]`.
  - `ValidationError` de Pydantic → 400 `VALIDACION`; errores `extra_forbidden` → 400 `CAMPO_NO_PERMITIDO`.
- [ ] T018 [P] Implementar `backend/core/src/condo_core/normalize.py`: `normalize(text)` → minúsculas, NFKD, sin marcas combinantes y espacios colapsados.
- [ ] T019 Implementar `backend/core/src/condo_core/auth.py`:
  - Dataclass `Claims` construida desde `requestContext.authorizer.jwt.claims`. Debe aceptar `cognito:groups` tanto como lista como en el formato de cadena `"[GRUPO]"` que entrega la HTTP API.
  - `require_role(claims, *roles)`.
  - Reglas literales de contracts/cognito-claims.md:
    - Sin claims → 401 `NO_AUTENTICADO`.
    - Más de un grupo o ninguno → 403 `PROHIBIDO`.
    - `SUPER_ADMIN` con `tenant_id` presente → 403 `PROHIBIDO`.
    - `ADMIN`/`ASISTENTE` sin `tenant_id` o que no cumpla `^[0-9a-f]{32}$` → 403 `PROHIBIDO`.
- [ ] T020 Implementar `backend/core/src/condo_core/tenancy.py`: `tenant_db(claims)` devuelve la base `t_<tenant_id>` usando **sólo** `claims.tenant_id`, sin aceptar parámetros de ruta, consulta, encabezados ni cuerpo.
- [ ] T021 [P] Crear `backend/core/tests/conftest.py` con:
  - Contenedor `mongo:8` de testcontainers, con `MONGODB_URI` apuntando a él.
  - Constructores de claims y de eventos de HTTP API v2 para SUPER_ADMIN, ADMIN, ASISTENTE y sin token.
- [ ] T022 [P] Escribir pruebas unitarias en `backend/core/tests/`:
  - `test_auth.py`: todas las reglas de T019.
  - `test_errors.py`.
  - `test_normalize.py`: "Bajío" → "bajio".
  - `test_logging.py`: cada línea tiene `tenant_id` y `request_id`, y ningún cuerpo aparece en los logs.
- [ ] T023 [P] Escribir `backend/core/tests/test_tenancy_aislamiento.py`: la base se elige sólo por el claim `tenant_id`; un tenant distinto en la ruta, la consulta, los encabezados o el cuerpo se ignora; un `tenant_id` inválido → 403 `PROHIBIDO`.

### Disparador de Cognito

- [ ] T024 Implementar `infra/shared/src/cognito_triggers/handler.py` según contracts/cognito-claims.md:
  1. SUPER_ADMIN → evento sin cambios.
  2. Sin `custom:tenant_id` → excepción.
  3. Leer `platform.organizaciones` por `_id` con proyección `{estatus: 1}`. Si no existe o `estatus != "activa"`, lanzar una excepción con el mensaje `ORGANIZACION_DESHABILITADA`.
  4. Agregar `tenant_id` en `claimsAndScopeOverrideDetails.accessTokenGeneration.claimsToAddOrOverride`.

  Registrar sólo `tenant_id` y el resultado, nunca el correo ni otros atributos.
- [ ] T025 [P] Escribir `infra/shared/src/cognito_triggers/tests/test_handler.py` con estos casos:
  - SUPER_ADMIN sin cambios.
  - Organización activa → claim inyectado.
  - Estatus `deshabilitada` → rechazo.
  - Estatus `aprovisionando` → rechazo.
  - Organización inexistente → rechazo.
  - Sin atributo → rechazo.
  - El correo no aparece en los logs.

### Scripts y catálogos

- [ ] T026 [P] Implementar `backend/scripts/seed_catalogos.py`, idempotente con upserts:
  - `shared.modulos` con `_id`, `nombre`, `descripcion`, `disponible` y `orden`. Semilla: `condominios`, `condominos`, `cuotas`, `pagos`, `avisos` y `areas-comunes`, todos `disponible: true`.
  - `shared.regimenes_fiscales` con `_id`, `descripcion`, `personaFisica`, `personaMoral` y `vigente: true`:
    - Moral: 601, 603, 620, 622, 623, 624.
    - Física: 605, 606, 607, 608, 611, 612, 614, 615, 616, 621, 625.
    - Ambas: 610, 626.
    - Con un comentario indicando que deben verificarse contra el catálogo `c_RegimenFiscal` del SAT.
  - Índices de `platform.organizaciones`: `{ "fiscal.rfc": 1 }` único, `{ idempotencyKey: 1 }` único y `{ estatus: 1, creadoEn: -1 }`.
- [ ] T027 [P] Implementar `backend/scripts/crear_super_admin.py`: `AdminCreateUser` con el correo recibido como argumento, sin `custom:tenant_id`, y alta en el grupo `SUPER_ADMIN`. Es idempotente: si el usuario ya existe, sólo asegura el grupo.

### Esqueleto del módulo `organizaciones`

- [ ] T028 Escribir `backend/modules/organizaciones/serverless.yml` (servicio `condo-organizaciones`):
  - Provider: `python3.12`, `arm64`, `httpApi.id: ${cf:condo-shared-${sls:stage}.HttpApiId}` y `deploymentBucket.name: condo-deployments-${aws:accountId}-${aws:region}`.
  - Función `api`:
    - Rol con nombre fijo `condo-organizaciones-${sls:stage}`, con
      `permissionsBoundary: arn:aws:iam::${aws:accountId}:policy/condo-boundary` (exigido por T008),
      `timeout: 29` y `memorySize: 512`.
    - Eventos `httpApi` `ANY /organizaciones` y `ANY /organizaciones/{proxy+}`, con el autorizador de `shared`.
    - Evento `schedule: rate(15 minutes)`.
  - Bucket de logotipos privado: BlockPublicAccess, SSE-S3 y negación de `aws:SecureTransport = false`.
  - IAM de mínimo privilegio:
    - `cognito-idp:AdminCreateUser`, `AdminGetUser`, `AdminAddUserToGroup` y `AdminDeleteUser` sobre `UserPoolArn`.
    - `s3:GetObject`, `PutObject` y `DeleteObject` sobre `logos/*` del bucket.
  - Retención de logs de 30 días en `dev` y 90 en `prod`.
  - VPC de `shared` en `prod`.
  - Plugin `serverless-python-requirements`.
  - Variables de entorno `STAGE`, `USER_POOL_ID`, `LOGOS_BUCKET` y `MONGODB_URI` (`${cf:condo-shared-${sls:stage}.MongoDbUri}`).
- [ ] T029 Implementar `backend/modules/organizaciones/src/organizaciones/handler.py`:
  - `APIGatewayHttpResolver` de Powertools.
  - Si el evento trae `source == "aws.events"`, despacha al reconciliador, que se conecta en T049; si no, al resolver.
  - Middleware global que, **antes** de resolver la ruta, ejecuta `bind_request` y `require_role(claims, "SUPER_ADMIN")` (FR-001, FR-002).
  - Manejador de `DomainError` y de `ValidationError` → problem+json.
- [ ] T030 Crear `backend/modules/organizaciones/tests/conftest.py` (depende de T026) con:
  - Contenedor `mongo:8`.
  - User pool de moto con los grupos y `custom:tenant_id`.
  - Bucket S3 de moto.
  - Fábrica de eventos de HTTP API v2 con claims por rol.
  - Catálogos e índices sembrados con `backend/scripts/seed_catalogos.py`.

### CI/CD

- [ ] T031 Escribir `.github/workflows/ci.yml`, que corre en `pull_request`:
  - Job `backend` con matriz de tres entradas, cada una con `uv sync`, `ruff check`, `mypy` y `pytest --cov=<paquete> --cov-fail-under=80`:
    - `core`: en `backend/`, `pytest core`.
    - `organizaciones`: en `backend/`, `pytest modules/organizaciones`.
    - `cognito-triggers`: en `infra/shared/`, `pytest src/cognito_triggers tests` (incluye la prueba de configuración T041).
  - Job `security`: CodeQL (`python`) y `pip-audit`.
- [ ] T032 Escribir el workflow reutilizable `.github/workflows/_deploy.yml` (`workflow_call`, input `environment`):
  - `permissions: id-token: write` y `aws-actions/configure-aws-credentials` con `vars.AWS_DEPLOY_ROLE_ARN` y `vars.AWS_REGION`.
  - Variable de entorno `SERVERLESS_LICENSE_KEY: ${{ secrets.SERVERLESS_LICENSE_KEY }}` del environment.
  - Pasos en orden:
    1. `npx serverless deploy --stage <env>` en `infra/shared`.
    2. `npx serverless deploy --stage <env>` en `backend/modules/organizaciones`.
    3. `seed_catalogos.py`.
  - `concurrency` por environment.
  - **No** despliega `infra/bootstrap` (principio X).
- [ ] T033 Escribir `.github/workflows/deploy-dev.yml` (push a `main` → `_deploy.yml` con `environment: dev`) y `.github/workflows/deploy-prod.yml` (`workflow_dispatch` con input `tag` → `_deploy.yml` con `environment: prod`; la aprobación la exigen los revisores del environment `prod` en GitHub).
- [ ] T034 [P] Escribir `.github/workflows/crear-super-admin.yml`: `workflow_dispatch` con inputs `environment` (`dev`|`prod`) y `email`; usa el environment elegido (aprobación) y OIDC, y ejecuta `backend/scripts/crear_super_admin.py`.

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Dar de alta una organización con su primer ADMIN (Priority: P1) 🎯 MVP

**Goal**: el SUPER_ADMIN registra una organización con todos sus datos y su primer ADMIN. La
organización queda activa con un `tenantId` único y el ADMIN recibe la invitación con el enlace al
aviso de privacidad.

**Independent Test**: dar de alta una organización y verificar que queda activa con un `tenantId`
de 32 caracteres hexadecimales, y que el ADMIN puede activar su cuenta con la invitación e iniciar
sesión con un token que lleva ese `tenant_id`.

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T035 [P] [US1] Escribir `backend/modules/organizaciones/tests/unit/test_validators.py` con estos casos:
  - RFC moral válido de 12 caracteres y físico válido de 13.
  - RFC en minúsculas normalizado a mayúsculas.
  - Fecha embebida inválida (por ejemplo `ABC991332XX1`).
  - Genéricos `XAXX010101000` y `XEXX010101000` rechazados.
  - Régimen inexistente, no vigente o de otro tipo de persona.
  - Teléfono distinto de 10 dígitos.
  - Código postal distinto de 5 dígitos.
  - `diaCorte`/`diaLimitePago` fuera de 1 a 28.
  - `estado` que no sea una de las 32 entidades.
  - Magic bytes PNG `89 50 4E 47` y JPEG `FF D8 FF` aceptados; PDF renombrado rechazado.
  - Más de 2,097,152 bytes rechazado.
- [ ] T036 [P] [US1] Escribir `backend/modules/organizaciones/tests/integration/test_alta_saga.py` con estos casos:
  - Alta correcta → 201, `estatus: "activa"`, `tenantId` que cumple `^[0-9a-f]{32}$`, `ETag: "1"` y `Location`.
  - El documento activo tiene `adminInicial.sub` e `adminInicial.invitacionEnviadaEn`.
  - El ADMIN existe en Cognito con `custom:tenant_id` igual al `tenantId` y en el grupo `ADMIN`.
  - No se creó ninguna base `t_<tenantId>`.
  - RFC repetido, incluso de una organización deshabilitada → 409 `RFC_DUPLICADO`.
  - Correo del ADMIN ya existente → 409 `CORREO_EN_USO`.
  - Falla inyectada en cada paso de la saga → 503 `ALTA_FALLIDA` y no queda ni documento ni usuario (FR-015).
  - Misma `Idempotency-Key` con el mismo cuerpo → 201 con el mismo `tenantId` y una sola organización (FR-016).
  - Misma llave con otro cuerpo → 422 `IDEMPOTENCY_KEY_REUTILIZADA`.
  - Sin llave → 428 `IDEMPOTENCY_KEY_REQUERIDA`.
  - Campo desconocido → 400 `CAMPO_NO_PERMITIDO`.
  - `modulosHabilitados: []` → 400.
  - Módulo con `disponible: false` → 400.
- [ ] T037 [P] [US1] Escribir `backend/modules/organizaciones/tests/integration/test_aislamiento_altas.py` (parte de US1): altas de las organizaciones A y B; el ADMIN de A tiene `custom:tenant_id = A`, el de B tiene `B`, y el disparador (T024) emite para cada uno un token sólo con su propio `tenant_id`.
- [ ] T038 [P] [US1] Escribir `backend/modules/organizaciones/tests/integration/test_logo.py` con estos casos:
  - PNG y JPEG válidos → 200, llave `logos/<tenantId>/<uuid>.<png|jpg>` y `ETag` incrementado.
  - PDF con `contentType: image/png` → 415 `LOGO_TIPO_NO_SOPORTADO`.
  - Más de 2 MB decodificados → 413 `LOGO_DEMASIADO_GRANDE`.
  - Sin `If-Match` → 428 `IF_MATCH_REQUERIDO`.
  - `If-Match` viejo → 412 `VERSION_DESACTUALIZADA`.
  - Reemplazar el logotipo borra el objeto anterior.
- [ ] T039 [P] [US1] Escribir `backend/modules/organizaciones/tests/integration/test_catalogos.py` (sólo módulos con `disponible: true` y regímenes vigentes) y `backend/modules/organizaciones/tests/integration/test_reenviar_invitacion.py`, con estos casos:
  - Invitación pendiente → 204, `invitacionEnviadaEn` actualizado y `version` **sin cambio** (data-model.md).
  - ADMIN ya confirmado → 409 `INVITACION_YA_ACEPTADA`.
  - Organización deshabilitada → 409 `ORGANIZACION_DESHABILITADA`.
- [ ] T040 [P] [US1] Escribir `backend/modules/organizaciones/tests/integration/test_reconciliador.py`: un documento en `aprovisionando` con más de 15 minutos y su usuario de Cognito se eliminan; uno con menos de 15 minutos y las organizaciones `activa` no se tocan.
- [ ] T041 [P] [US1] Escribir `infra/shared/tests/test_serverless_config.py`: cargar `infra/shared/serverless.yml`, con un loader de YAML que ignore las etiquetas `!Ref`/`!GetAtt`/`!Sub`, y verificar que `InviteMessageTemplate` contiene `${param:avisoPrivacidadUrl}` (FR-031), que `custom:tenant_id` es `Mutable: false`, que el app client no tiene secreto, y que el rol de `cognito-triggers` en `infra/shared/serverless.yml` y el de `api` en `backend/modules/organizaciones/serverless.yml` declaran `permissionsBoundary` con `condo-boundary`.

### Implementation for User Story 1

- [ ] T042 [P] [US1] Implementar `backend/modules/organizaciones/src/organizaciones/validators.py` con las reglas literales de data-model.md:
  - RFC moral `^[A-ZÑ&]{3}\d{6}[A-Z\d]{3}$` y físico `^[A-ZÑ&]{4}\d{6}[A-Z\d]{3}$`, con "La fecha embebida debe ser válida" y "Sin RFC genéricos".
  - Régimen "existente y vigente en `shared.regimenes_fiscales`, que aplique al tipo de persona del RFC".
  - Teléfono `^\d{10}$` y códigos postales `^\d{5}$`.
  - Lista de las 32 entidades federativas.
  - `detect_image_type(data)` por magic bytes.
- [ ] T043 [P] [US1] Implementar en `backend/modules/organizaciones/src/organizaciones/schemas.py` los modelos Pydantic con `extra="forbid"` y alias camelCase:
  - `Contacto`: `nombre` de 2 a 120 caracteres, `correo` en minúsculas de hasta 254, `telefono` de 10 dígitos.
  - `Direccion`: `calle` 1 a 150, `numeroExterior` 1 a 20, `numeroInterior` opcional 1 a 20, `colonia` 1 a 100, `municipio` 1 a 100, `estado` y `codigoPostal`.
  - `Fiscal`: `razonSocial` 2 a 254 y `rfc` normalizado a mayúsculas.
  - `Facturacion`: días de 1 a 28.
  - `AdminInicialAlta`: `nombre` 2 a 120 y `correo`.
  - `OrganizacionAlta`: `nombreComercial` 2 a 150 sin espacios al inicio ni al final, y `modulosHabilitados` con mínimo 1 elemento y sin repetidos.
  - `Organizacion`, la respuesta del contrato, con `logo.url` y `adminInicial.invitacion` (`pendiente`|`aceptada`|`vencida`).
- [ ] T044 [US1] Implementar `backend/modules/organizaciones/src/organizaciones/repository.py`:
  - `insert_aprovisionando(doc)`: **sin** `adminInicial.sub` ni `adminInicial.invitacionEnviadaEn` (data-model.md: "Ausente mientras el estatus es `aprovisionando`"). Arma `busqueda` con `normalize(nombreComercial + " " + fiscal.razonSocial + " " + fiscal.rfc)`. Convierte un `DuplicateKeyError` sobre `fiscal.rfc` en 409 `RFC_DUPLICADO`; sobre `idempotencyKey`, deja que el llamador consulte la organización existente.
  - `find_by_idempotency_key` y `get_visible(tenant_id)` (excluye `aprovisionando` → 404 `NO_ENCONTRADA`).
  - `set_activa(tenant_id, sub, invitacion_enviada_en)`: fija `estatus: "activa"`, `adminInicial.sub` y `adminInicial.invitacionEnviadaEn`.
  - `delete` y `find_stale_aprovisionando(older_than)`.
  - `update_with_version(tenant_id, expected_version, set_fields, unset_fields=())`: filtra por `{_id, version}`, incrementa `version`, fija `actualizadoEn`, y responde 412 `VERSION_DESACTUALIZADA` si no coincide la versión o 404 si no existe.
  - `touch_invitacion(tenant_id, fecha)`: actualiza sólo `adminInicial.invitacionEnviadaEn`, **sin** cambiar `version` ni `actualizadoEn`.
- [ ] T045 [P] [US1] Implementar `backend/modules/organizaciones/src/organizaciones/identity.py`:
  - `admin_exists(email)`.
  - `create_admin(email, nombre, tenant_id)`: `AdminCreateUser` con `email`, `email_verified=true`, `name`, `custom:tenant_id` y `DesiredDeliveryMediums=[EMAIL]`, y luego `AdminAddUserToGroup` con `ADMIN`. Si el usuario ya existe con el mismo `custom:tenant_id`, se reutiliza; si no, responde 409 `CORREO_EN_USO`. Devuelve `sub`.
  - `delete_admin(email)`.
  - `resend_invitation(email)`, con `MessageAction=RESEND`.
  - `invitation_state(email, enviada_en)`: `CONFIRMED` → `aceptada`; `FORCE_CHANGE_PASSWORD` con más de 7 días → `vencida`; si no, `pendiente`.
- [ ] T046 [US1] Implementar `backend/modules/organizaciones/src/organizaciones/provisioning.py` según research.md, decisión 9:
  - Verificaciones previas: validación, RFC libre y `admin_exists`.
  - `tenant_id = secrets.token_hex(16)` y `requestHash` = SHA-256 del JSON canónico del cuerpo.
  - Pasos: 1) `insert_aprovisionando`; 2) `create_admin`; 3) `set_activa(tenant_id, sub, ahora)`.
  - Compensación en orden inverso y 503 `ALTA_FALLIDA` ante cualquier falla.
  - Reintento con la misma llave: mismo hash y organización `activa` → la devuelve; hash distinto → 422 `IDEMPOTENCY_KEY_REUTILIZADA`.
  - `reconcile_stale()`: compensa los documentos en `aprovisionando` con más de 15 minutos.
- [ ] T047 [P] [US1] Implementar `backend/modules/organizaciones/src/organizaciones/logos.py`:
  - Decodificar base64 y rechazar más de 2,097,152 bytes (413 `LOGO_DEMASIADO_GRANDE`).
  - Detectar el tipo real con `detect_image_type`; si no es PNG ni JPEG → 415 `LOGO_TIPO_NO_SOPORTADO`. Se guarda el tipo real, no el `contentType` declarado.
  - `put_logo(tenant_id, data)` en `logos/<tenantId>/<uuid>.<png|jpg>` y borrado del objeto anterior.
  - `delete_logo(key)`, que borra el objeto de S3.
  - `presigned_url(key)` con vigencia de 300 s.
- [ ] T048 [US1] Implementar en `backend/modules/organizaciones/src/organizaciones/routes.py` las rutas, según contracts/organizaciones.openapi.yaml:
  - `POST /organizaciones`: exige `Idempotency-Key`; responde 201 con `Location` y `ETag`.
  - `GET /organizaciones/catalogos`.
  - `PUT /organizaciones/<tenantId>/logo`: exige `If-Match` (si falta → 428 `IF_MATCH_REQUERIDO`) y usa `update_with_version`.
  - `POST /organizaciones/<tenantId>/admin-inicial/reenviar-invitacion`: **sin** `If-Match`; usa `resend_invitation` y `touch_invitacion`; responde 204, o 409 `INVITACION_YA_ACEPTADA` | `ORGANIZACION_DESHABILITADA`.

  Validar `tenantId` con `^[0-9a-f]{32}$` y registrar `target_tenant_id` en los logs.
- [ ] T049 [US1] Conectar `provisioning.reconcile_stale()` al despacho de eventos programados en `backend/modules/organizaciones/src/organizaciones/handler.py`.

**Checkpoint**: User Story 1 funcional y verificable por sí sola (quickstart.md, secciones 4.1 y 4.2)

---

## Phase 4: User Story 5 - Restricción de acceso a SUPER_ADMIN (Priority: P1)

**Goal**: ningún usuario que no sea SUPER_ADMIN puede ver ni operar el registro de organizaciones.

**Independent Test**: intentar cada operación con ADMIN, ASISTENTE y sin sesión; todas se
rechazan sin revelar información.

### Tests for User Story 5 ⚠️

- [ ] T050 [P] [US5] Escribir `backend/modules/organizaciones/tests/integration/test_autorizacion.py`:
  - Recorrer dinámicamente **todas** las rutas registradas en el resolver, para que las rutas futuras queden cubiertas.
  - Con tokens ADMIN y ASISTENTE → 403 `PROHIBIDO`, sin datos de ninguna organización en el cuerpo.
  - Sin claims → 401 `NO_AUTENTICADO`.
  - SUPER_ADMIN con `tenant_id` → 403.
  - Para un no SUPER_ADMIN, un `tenantId` existente y uno inexistente producen respuestas idénticas (FR-002).
  - Una ruta desconocida responde 403, no 404.

### Implementation for User Story 5

- [ ] T051 [US5] Asegurar en `backend/modules/organizaciones/src/organizaciones/handler.py` que la verificación `require_role(claims, "SUPER_ADMIN")` corra antes de resolver la ruta, de leer el cuerpo y de cualquier consulta, también para rutas inexistentes. Así un no SUPER_ADMIN recibe 403 y nunca 404.

**Checkpoint**: User Stories 1 y 5 funcionan por sí solas

---

## Phase 5: User Story 2 - Deshabilitar y rehabilitar una organización (Priority: P2)

**Goal**: el SUPER_ADMIN deshabilita una organización sin borrar datos, y sus usuarios pierden el
acceso de inmediato; al rehabilitarla lo recuperan.

**Independent Test**: deshabilitar una organización con un ADMIN activo y verificar que no puede
iniciar sesión ni renovar su token; rehabilitarla y verificar que vuelve a entrar.

### Tests for User Story 2 ⚠️

- [ ] T052 [P] [US2] Escribir `backend/modules/organizaciones/tests/integration/test_estatus.py` con estos casos:
  - Deshabilitar una activa → 200, `estatus: "deshabilitada"`, `deshabilitadoEn` presente y `version` + 1.
  - Deshabilitarla de nuevo → 409 `ESTATUS_SIN_CAMBIO` sin modificar el documento.
  - Habilitar → `activa` y sin `deshabilitadoEn`.
  - Habilitar una activa → 409 `ESTATUS_SIN_CAMBIO`.
  - Sin `If-Match` → 428; `If-Match` viejo → 412.
  - Los datos de la organización quedan intactos (FR-027).
- [ ] T053 [P] [US2] Escribir `backend/core/tests/test_require_active_tenant.py`:
  - Organización `activa` → pasa.
  - Cambiar a `deshabilitada` → la **primera** llamada siguiente responde 403 `ORGANIZACION_DESHABILITADA`, sin caché (FR-028, SC-003).
  - Organización inexistente o en `aprovisionando` → 403.
- [ ] T054 [P] [US2] Ampliar `backend/modules/organizaciones/tests/integration/test_aislamiento_altas.py`: deshabilitar A deja a B `activa`, y el disparador sigue emitiendo tokens para el ADMIN de B y rechaza los de A.

### Implementation for User Story 2

- [ ] T055 [US2] Implementar `require_active_tenant(claims)` en `backend/core/src/condo_core/auth.py`: lee `platform.organizaciones` por `_id = claims.tenant_id` con proyección `{estatus: 1}`, sin caché, y responde 403 `ORGANIZACION_DESHABILITADA` si no está `activa`.
- [ ] T056 [US2] Agregar a `backend/modules/organizaciones/src/organizaciones/repository.py` la función `set_estatus(tenant_id, expected_version, nuevo)`. Al deshabilitar fija `deshabilitadoEn`; al habilitar lo elimina; si el estatus no cambia, responde 409 `ESTATUS_SIN_CAMBIO`. Agregar en `backend/modules/organizaciones/src/organizaciones/routes.py` las rutas `POST /organizaciones/<tenantId>/deshabilitar` y `POST /organizaciones/<tenantId>/habilitar`, con `If-Match`.

**Checkpoint**: User Stories 1, 5 y 2 funcionan por sí solas

---

## Phase 6: User Story 3 - Listar, buscar y consultar organizaciones (Priority: P2)

**Goal**: el SUPER_ADMIN localiza clientes con búsqueda, filtro por estatus y paginación, y
consulta el detalle completo.

**Independent Test**: con un conjunto de organizaciones de ejemplo, la búsqueda, el filtro y la
paginación devuelven exactamente los registros esperados.

### Tests for User Story 3 ⚠️

- [ ] T057 [P] [US3] Escribir `backend/modules/organizaciones/tests/integration/test_busqueda.py` con estos casos:
  - 45 organizaciones paginadas de 20 en 20 hasta ver las 45.
  - `size` por defecto 20 y máximo 100 (más de 100 → 400).
  - Orden por `creadoEn` descendente.
  - `q` parcial sobre nombre comercial, razón social o RFC, sin distinguir mayúsculas ni acentos: "condominios del bajio" encuentra "Condominios del Bajío".
  - `estatus=deshabilitada` sólo devuelve deshabilitadas; por defecto se devuelven todas.
  - Las organizaciones en `aprovisionando` nunca aparecen.
  - `q` con metacaracteres (`.*(`, `[`) no falla ni amplía los resultados.
  - Sin coincidencias → `items: []` y `total: 0`.
- [ ] T058 [P] [US3] Escribir `backend/modules/organizaciones/tests/integration/test_detalle.py`:
  - Detalle completo con `ETag`.
  - `logo.url` firmado cuando hay logotipo.
  - `adminInicial.invitacion` en `pendiente`, `aceptada` y `vencida`.
  - `tenantId` inexistente o en `aprovisionando` → 404 `NO_ENCONTRADA`.

### Implementation for User Story 3

- [ ] T059 [US3] Agregar a `backend/modules/organizaciones/src/organizaciones/repository.py` la función `list(q, estatus, page, size)`: filtra `estatus ∈ {activa, deshabilitada}` (o el valor elegido) y, si hay `q`, usa `busqueda` con la expresión regular `re.escape(normalize(q))`. Ordena por `creadoEn` descendente y devuelve `items` y `total`.
- [ ] T060 [US3] Agregar en `backend/modules/organizaciones/src/organizaciones/routes.py`:
  - `GET /organizaciones`: parámetros `q` de hasta 100 caracteres, `estatus` con valor por defecto `todas`, `page` ≥ 1 y `size` de 1 a 100 con valor por defecto 20.
  - `GET /organizaciones/<tenantId>`: con `ETag`, `logo.url` (`logos.presigned_url`) y `adminInicial.invitacion` (`identity.invitation_state`).

**Checkpoint**: User Stories 1, 5, 2 y 3 funcionan por sí solas

---

## Phase 7: User Story 4 - Modificar los datos de una organización (Priority: P3)

**Goal**: el SUPER_ADMIN actualiza contacto, dirección, datos fiscales, logotipo, facturación y
módulos, sin sobrescribir cambios ajenos.

**Independent Test**: modificar cada grupo de datos y verificar que el cambio se refleja en el
detalle; una edición con versión vieja se rechaza.

### Tests for User Story 4 ⚠️

- [ ] T061 [P] [US4] Escribir `backend/modules/organizaciones/tests/integration/test_modificacion.py` con estos casos:
  - `PATCH` de `contacto.telefono` con el `ETag` vigente → 200 y `ETag` "n+1".
  - El mismo `PATCH` con el `ETag` anterior → 412 `VERSION_DESACTUALIZADA`.
  - Sin `If-Match` → 428.
  - Cuerpo vacío → 400.
  - RFC de otra organización → 409 `RFC_DUPLICADO`.
  - `tenantId`, `estatus` o `adminInicial` en el cuerpo → 400 `CAMPO_NO_PERMITIDO`.
  - `modulosHabilitados: []` → 400 (FR-023).
  - Quitar un módulo conserva los demás (FR-024).
  - Agregar un módulo con `disponible: false` → 400, pero conservar uno que ya tenía y dejó de estar disponible está permitido.
  - `direccion: null` elimina la dirección.
  - `busqueda` se recalcula al cambiar el nombre comercial, la razón social o el RFC.
  - `DELETE /organizaciones/<tenantId>/logo` quita el logotipo y borra el objeto de S3.

### Implementation for User Story 4

- [ ] T062 [US4] Agregar a `backend/modules/organizaciones/src/organizaciones/schemas.py` el modelo `OrganizacionCambios`: `extra="forbid"`, al menos 1 propiedad, `direccion` acepta `null`, mismas restricciones que el alta y sin `adminInicial`.
- [ ] T063 [US4] Implementar en `backend/modules/organizaciones/src/organizaciones/routes.py`:
  - `PATCH /organizaciones/<tenantId>` con `If-Match`:
    - Merge parcial.
    - Recalcular `busqueda`.
    - Validar que los módulos nuevos estén disponibles, conservando los que ya tenía.
    - Validar el régimen contra el tipo de persona del RFC resultante.
    - Usar `update_with_version`.
  - `DELETE /organizaciones/<tenantId>/logo` con `If-Match`, usando `logos.delete_logo`.

**Checkpoint**: todas las historias funcionan por sí solas

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T064 [P] Escribir `backend/modules/organizaciones/tests/integration/test_logs_sin_pii.py`: ejecutar alta, modificación, deshabilitación y reenvío capturando los logs, y verificar que no aparecen correos, teléfonos ni nombres de contacto o del ADMIN (principio VI, FR-030).
- [ ] T065 [P] Escribir `backend/modules/organizaciones/tests/integration/test_rendimiento.py` (marcado `slow`), con dos verificaciones:
  - Sembrar 1,000 organizaciones y comprobar que la búsqueda con filtro responde en menos de 2 s (SC-004).
  - Medir 20 altas consecutivas y comprobar que el percentil 95 es menor a 10 s (SC-001).
- [ ] T066 [P] Escribir `backend/README.md` con los comandos locales de prueba de quickstart.md, sección 2, la estructura de módulos y la referencia a `infra/bootstrap/README.md` e `infra/atlas/README.md`.
- [ ] T067 Verificar que la cobertura de `core`, `organizaciones` y `cognito-triggers` sea de al menos 80 % cada uno, y completar las pruebas que falten en sus carpetas de `tests/`.
- [ ] T068 Desplegar a `dev` integrando en `main` y ejecutar las secciones 4 y 5 de `specs/001-alta-organizaciones/quickstart.md`, registrando el resultado de cada escenario.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias.
- **Foundational (Phase 2)**: depende de Setup; bloquea todas las historias.
  - Infraestructura: T008 → T010 → T011 → T012 → T013. T008 lo aplica un administrador antes del primer despliegue (T032).
  - Las tareas de `condo_core` (T015 a T020) van antes de T024 y T029.
  - T028 depende de T011.
  - T030 depende de T026.
  - T032 depende de T011, T028 y T026.
- **Historias (Phase 3 a 7)**: dependen de Foundational.
- **Polish (Phase 8)**: depende de las historias que se vayan a entregar.

### User Story Dependencies

- **US1 (P1)**: sólo depende de Foundational.
- **US5 (P1)**: depende de Foundational. Su prueba (T050) recorre las rutas existentes; conviene ejecutarla de nuevo al terminar cada historia posterior.
- **US2 (P2)**: depende de Foundational y de `repository.update_with_version` (T044).
- **US3 (P2)**: depende de Foundational, de `repository.py` (T044), de `identity.invitation_state` (T045) y de `logos.presigned_url` (T047).
- **US4 (P3)**: depende de los esquemas (T043), el repositorio (T044) y los logotipos (T047) de US1.

### Within Each User Story

- Pruebas primero, y deben fallar.
- Validadores y esquemas → repositorio e identidad → saga o servicio → rutas.
- Terminar cada historia antes de pasar a la siguiente prioridad.

### Parallel Opportunities

- Setup: T003 a T007 en paralelo.
- Foundational: T009, T014, T015 a T018, T021 a T023, T025 a T027 y T034 en paralelo, respetando las dependencias de arriba.
- US1: las pruebas T035 a T041 en paralelo; T042, T043, T045 y T047 en paralelo.
- US2: T052 a T054 en paralelo.
- US3: T057 y T058 en paralelo.
- Polish: T064 a T066 en paralelo.

---

## Parallel Example: User Story 1

```bash
# Pruebas de US1 en paralelo:
Task: "Pruebas de validadores en backend/modules/organizaciones/tests/unit/test_validators.py"
Task: "Prueba de la saga de alta en backend/modules/organizaciones/tests/integration/test_alta_saga.py"
Task: "Prueba de aislamiento de altas en backend/modules/organizaciones/tests/integration/test_aislamiento_altas.py"
Task: "Prueba de configuración de Cognito en infra/shared/tests/test_serverless_config.py"

# Piezas independientes de US1 en paralelo:
Task: "Validadores en backend/modules/organizaciones/src/organizaciones/validators.py"
Task: "Esquemas en backend/modules/organizaciones/src/organizaciones/schemas.py"
Task: "Identidad en backend/modules/organizaciones/src/organizaciones/identity.py"
Task: "Logotipos en backend/modules/organizaciones/src/organizaciones/logos.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 + User Story 5)

1. Completar Phase 1 (Setup).
2. Completar Phase 2 (Foundational): incluye el bootstrap único de OIDC (T008, T009) y la configuración de Atlas (T014), que requieren un administrador.
3. Completar Phase 3 (US1) y Phase 4 (US5). Ambas son P1, y la restricción de acceso no debe salir a `dev` sin probarse.
4. **STOP and VALIDATE**: quickstart.md, secciones 4.1 y 4.2.
5. Integrar en `main` → despliegue automático a `dev`.

### Incremental Delivery

1. Setup + Foundational → base lista.
2. US1 + US5 → validar → `dev` (MVP).
3. US2 → validar el bloqueo → `dev`.
4. US3 → validar búsqueda y detalle → `dev`.
5. US4 → validar la edición concurrente → `dev`.
6. Polish → desplegar a `prod` con `deploy-prod.yml` y aprobación, sólo después de implementar la
   política de conservación de datos que exige la LFPDPPP (research.md, decisión 21).

---

## Notes

- [P] = archivos distintos y sin dependencias pendientes.
- [USn] relaciona cada tarea con su historia en spec.md.
- Verificar que las pruebas fallen antes de implementar.
- Ningún despliegue a AWS desde una máquina local, salvo el bootstrap único del principio X.
- Hacer commit por tarea o por grupo lógico.
