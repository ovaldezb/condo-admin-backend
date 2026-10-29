# Implementation Plan: Alta de organizaciones

**Branch**: `001-alta-organizaciones` | **Date**: 2026-10-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-alta-organizaciones/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

El SUPER_ADMIN da de alta, lista, consulta, modifica, deshabilita y rehabilita organizaciones
(administradoras de condominios) mediante una API. El alta registra la organización en la base de
plataforma, le asigna un `tenant_id` aleatorio de 32 caracteres hexadecimales, que también da nombre
a su base de datos propia `t_<tenant_id>`, y registra a su primer ADMIN en Cognito, que recibe una
invitación por correo. MongoDB crea esa base cuando un módulo de operación guarda su primer dato, en
una funcionalidad posterior. El alta se ejecuta como una saga idempotente con compensación, para
que nunca quede a medias.

Este repositorio contiene **sólo el backend** (constitución 2.0.0, principio I). La interfaz de
usuario vive en el repositorio del frontend y consume la API definida en
[contracts/organizaciones.openapi.yaml](./contracts/organizaciones.openapi.yaml).

Al ser la primera funcionalidad, este plan también entrega la **infraestructura base compartida**:

- Un stack de arranque con el proveedor OIDC de GitHub y los roles de despliegue, definido con
  Serverless Framework y aplicado una sola vez por cuenta (excepción del principio X).
- Un stack compartido con el user pool de Cognito, la HTTP API con autorizador JWT y el disparador
  de Cognito que inyecta el `tenant_id` y bloquea a organizaciones deshabilitadas.
- Pipelines de GitHub Actions con OIDC y ambientes `dev` (automático) y `prod` (aprobación manual).

Cada módulo de negocio tiene su propio `serverless.yml`, separado de los recursos compartidos.

Se entrega un módulo de backend, `organizaciones` (sólo SUPER_ADMIN). El paquete común
`condo_core` incluye ya la resolución del tenant y la verificación de estatus en cada petición, que
usarán los módulos de tenant de funcionalidades posteriores.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**:
- AWS Lambda Powertools for Python (enrutamiento, logs estructurados, validación), Pydantic v2,
  PyMongo y boto3.
- Infraestructura: Serverless Framework v4 y `serverless-python-requirements`.

**Storage**:
- MongoDB Atlas con autenticación IAM (`MONGODB-AWS`), una base por organización
  (`t_<tenant_id>`), base `shared` de sólo lectura para organizaciones y base `platform` exclusiva
  de SUPER_ADMIN.
- Amazon S3 sólo para archivos (logotipos); no es una base de datos.

**Testing**: pytest, pytest-cov (umbral de 80 % por módulo), moto (Cognito y S3) y
testcontainers con MongoDB 8.

**Target Platform**: AWS Lambda (Python 3.12, arm64) detrás de API Gateway HTTP API.

**Project Type**: Servicio backend serverless (API REST) en su propio repositorio.

**Performance Goals**: búsqueda y filtrado en menos de 2 s con 1,000 organizaciones (SC-004); alta
completa en menos de 10 s en el 95 % de los casos (SC-001), dentro del límite de 30 s de API
Gateway.

**Constraints**:
- El tenant se resuelve sólo de los claims del token.
- Verificación del estatus de la organización en cada petición de un usuario de tenant, sin caché
  (SC-003).
- Ningún dato personal en logs.
- Logotipo de hasta 2 MB validado por contenido real (magic bytes).
- Las URLs del frontend (callbacks de Cognito y orígenes de CORS) y la URL del aviso de privacidad
  se reciben como parámetros por ambiente; este repositorio no despliega el frontend.

**Scale/Scope**: del orden de 1,000 organizaciones y decenas de SUPER_ADMIN; 1 módulo de backend y
2 stacks de infraestructura compartida (bootstrap y shared).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Cumplimiento en este plan | Estado |
|---|---|---|
| I. Stack obligatorio | Python 3.12 en Lambda + API Gateway, MongoDB como única base, Cognito como único mecanismo de identidad y Serverless Framework para toda la infraestructura de AWS, incluido el stack de arranque. Repositorio exclusivo del backend. S3 se usa sólo como almacenamiento de archivos. | ✅ |
| II. Un punto de acceso por módulo | `organizaciones` es una sola Lambda, con rutas `ANY /organizaciones` y `ANY /organizaciones/{proxy+}` y enrutamiento interno (Powertools), en su propio `serverless.yml` y stack. La segunda ruta es necesaria porque `{proxy+}` no cubre la ruta base. El disparador de Cognito no es un módulo de negocio y vive en el stack compartido como una sola Lambda. | ✅ |
| III. Aislamiento multi-tenant | Base `t_<tenant_id>` por organización. El `tenant_id` sale del claim inyectado por el disparador de Cognito, nunca del cliente. `shared` sólo contiene catálogos (módulos y regímenes fiscales). `platform` sólo la usa SUPER_ADMIN. El disparador de Cognito y `require_active_tenant()` sólo leen el campo `estatus` de la propia organización, que es la excepción permitida. | ✅ |
| IV. Pruebas y cobertura | 80 % por módulo (`core`, `organizaciones`, `cognito-triggers`), medido por separado en el CI de este repositorio. Pruebas unitarias, de integración y de aislamiento entre tenants: `condo_core.tenancy` elige la base sólo por el claim e ignora cualquier tenant enviado por el cliente; el ADMIN de cada organización recibe únicamente su `tenant_id`; deshabilitar una organización no afecta a otra. | ✅ |
| V. Seguridad | Validación con Pydantic (`extra="forbid"`), autorización por grupo en cada ruta, roles IAM por módulo, sin secretos en el repositorio (la única credencial, la clave de licencia de Serverless, es un secreto del environment de GitHub; Atlas usa autenticación IAM sin contraseña; ver research.md, decisiones 2 y 6), ningún recurso de AWS creado a mano (URI de Atlas e identidad de SES definidas en `infra/shared/serverless.yml`), TLS y cifrado en reposo (Atlas, S3, Cognito), CodeQL y pip-audit en CI. | ✅ |
| VI. Datos personales | Se capturan sólo los datos de la especificación; el logger de Powertools no registra eventos ni cuerpos. LFPDPPP: la invitación incluye el enlace al aviso de privacidad (FR-031); acceso y rectificación mediante el detalle y la modificación; la cancelación y la política de conservación quedan para una funcionalidad posterior, obligatoria antes de operar con datos reales en `prod` (research.md, decisión 21). | ✅ |
| VII. Pagos | Fuera de alcance: no hay cobros en esta funcionalidad. | N/A |
| VIII. Observabilidad | Logs JSON con `tenant_id` (o `platform` para SUPER_ADMIN, más `target_tenant_id`) y `request_id` en cada línea. | ✅ |
| IX. Frontend | Rige al repositorio del frontend. Este repositorio le entrega un app client público de Cognito con PKCE, sin secretos, y valida toda autorización en la API. | N/A |
| X. Despliegue | GitHub Actions con OIDC; `dev` al integrar en `main` y `prod` con aprobación del environment `prod`. El stack de arranque (`infra/bootstrap/serverless.yml`) se aplica una sola vez por cuenta, según la excepción del principio X. | ✅ |

**Resultado del gate inicial**: aprobado, sin violaciones.

**Re-evaluación tras la fase 1**: el diseño (data-model, contratos y quickstart) no introduce
desviaciones. Notas:

- El disparador de Cognito y los futuros módulos de tenant leen el estatus directamente de
  `platform.organizaciones`, proyectando sólo el campo `estatus`. Su rol de base de datos tiene
  `find` sobre toda la colección, porque Atlas no restringe permisos por campo; ver research.md,
  decisión 6.
- El módulo `organizaciones` no crea bases de datos, así que su rol no necesita privilegios sobre
  otras bases.

## Project Structure

### Documentation (this feature)

```text
specs/001-alta-organizaciones/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── organizaciones.openapi.yaml
│   └── cognito-claims.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
package.json                     # Serverless Framework v4 y plugins, versiones fijas

infra/
├── bootstrap/
│   ├── serverless.yml           # Proveedor OIDC de GitHub + roles de despliegue por ambiente (aplicación única)
│   └── README.md                # Procedimiento único de arranque por cuenta (principio X)
├── atlas/
│   └── README.md                # Configuración de MongoDB Atlas por ambiente (fuera de AWS)
└── shared/
    ├── pyproject.toml           # Paquete cognito-triggers
    ├── serverless.yml           # Cognito (pool, grupos, app client, dominio), HTTP API + autorizador JWT,
    │                            # Lambda de disparadores de Cognito, identidad SES (prod) y parámetros por
    │                            # ambiente (URLs del frontend, aviso de privacidad, URI de Atlas)
    ├── tests/                   # Pruebas de la configuración de serverless.yml
    └── src/cognito_triggers/
        ├── handler.py           # PreTokenGeneration V2: inyecta tenant_id y rechaza organizaciones deshabilitadas
        └── tests/

backend/
├── pyproject.toml               # Workspace de uv
├── core/                        # Paquete condo_core, incluido en cada Lambda
│   ├── src/condo_core/
│   │   ├── auth.py              # Lectura de claims, require_role, require_active_tenant
│   │   ├── tenancy.py           # Resolución de tenant y acceso a la base t_<tenant_id> (para módulos futuros)
│   │   ├── mongo.py             # Cliente MongoDB reutilizable con autenticación IAM
│   │   ├── logging.py           # Logger de Powertools con tenant_id y request_id
│   │   ├── errors.py            # Errores de dominio → application/problem+json
│   │   └── normalize.py         # Normalización de texto para búsqueda (minúsculas, sin acentos)
│   └── tests/
├── modules/
│   └── organizaciones/
│       ├── serverless.yml       # 1 Lambda, rutas proxy, bucket de logotipos, evento programado del reconciliador
│       ├── src/organizaciones/
│       │   ├── handler.py       # Entrada: HTTP (resolver de Powertools) o evento programado
│       │   ├── routes.py
│       │   ├── schemas.py       # Modelos Pydantic de entrada y salida
│       │   ├── validators.py    # RFC, régimen fiscal, teléfono, códigos postales, logotipo
│       │   ├── repository.py    # platform.organizaciones
│       │   ├── provisioning.py  # Saga de alta y compensación
│       │   ├── identity.py      # Operaciones de Cognito (crear ADMIN, reenviar invitación)
│       │   └── logos.py         # Validación y guardado en S3, URLs firmadas
│       └── tests/
│           ├── unit/
│           └── integration/
└── scripts/
    ├── seed_catalogos.py        # Upsert idempotente de shared.modulos y shared.regimenes_fiscales, e índices
    └── crear_super_admin.py     # Ejecutado sólo desde un workflow manual con aprobación

.github/workflows/
├── ci.yml                       # PR: pruebas y cobertura por módulo, CodeQL, pip-audit
├── _deploy.yml                  # Workflow reutilizable: shared → módulos → catálogos
├── deploy-dev.yml               # Push a main → _deploy.yml en dev
├── deploy-prod.yml              # Manual, environment prod con revisores obligatorios
└── crear-super-admin.yml        # workflow_dispatch con aprobación por environment
```

**Structure Decision**: servicio backend con dos carpetas raíz:

- `infra/`: infraestructura compartida, con un stack por responsabilidad.
- `backend/`: un `serverless.yml` por módulo más el paquete común `condo_core`.

Los stacks se despliegan en este orden: `shared` → `modules/*`. Los módulos importan de `shared`
el id de la HTTP API y del autorizador. Las URLs del frontend de cada ambiente (callbacks de
Cognito y orígenes de CORS) se declaran en `params` de `infra/shared/serverless.yml`; en `dev`
incluyen `http://localhost:4200`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

Sin violaciones. El stack de arranque se apoya en la excepción explícita del principio X
(constitución 2.0.0).
