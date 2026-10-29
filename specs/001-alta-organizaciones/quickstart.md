# Quickstart: validar el alta de organizaciones

**Feature**: `001-alta-organizaciones`

Esta guía comprueba de punta a punta que la funcionalidad funciona. El detalle de la API está en
[contracts/](./contracts/) y el del modelo en [data-model.md](./data-model.md).

## 1. Prerrequisitos únicos por cuenta de AWS

Se hacen una sola vez y no forman parte del ciclo normal.

1. **Bootstrap de OIDC**: un administrador de la cuenta despliega `infra/bootstrap/serverless.yml`
   una sola vez, siguiendo `infra/bootstrap/README.md`. Es la excepción del principio X.
2. **GitHub**: crear los environments `dev` y `prod`. En `prod`, configurar revisores
   obligatorios. En cada environment, definir las variables `AWS_DEPLOY_ROLE_ARN` y `AWS_REGION` y
   el secreto `SERVERLESS_LICENSE_KEY`.
3. **MongoDB Atlas**, en cada ambiente:
   - Un clúster (M10 o superior en `prod`, para PrivateLink).
   - Usuarios de base de datos con autenticación IAM, mapeados a los roles de Lambda con nombre
     fijo y con los roles personalizados de research.md, decisión 6.
4. **URI de Atlas**: registrarla en `params.mongodbUri` de `infra/shared/serverless.yml` mediante
   un PR. No contiene credenciales.
5. **SES** (sólo `prod`), en dos fases:
   1. El primer despliegue crea la identidad con `sesVerificado: false`; Cognito usa su correo por
      defecto.
   2. Publicar en el DNS los registros DKIM de las salidas del stack (salvo que el DNS esté en
      Route 53). Cuando SES marque el dominio como verificado, cambiar `sesVerificado` a `true` en
      un PR.

## 2. Validación local (sin desplegar)

Requiere Docker, Python 3.12 y `uv`.

```bash
# Backend: cada módulo por separado, con su umbral de cobertura
cd backend
uv sync
uv run pytest core --cov=condo_core --cov-fail-under=80
uv run pytest modules/organizaciones --cov=organizaciones --cov-fail-under=80

# Disparador de Cognito (proyecto propio)
cd ../infra/shared
uv sync
uv run pytest src/cognito_triggers tests --cov=cognito_triggers --cov-fail-under=80
```

**Resultado esperado**: todo en verde. Las pruebas de integración levantan MongoDB 8 con
testcontainers y simulan Cognito y S3 con moto.

Pruebas que **deben existir** y pasar:

| Prueba | Cubre |
|---|---|
| `organizaciones/tests/integration/test_autorizacion.py` | 403 a ADMIN y ASISTENTE y 401 sin token en **todos** los endpoints (FR-001, FR-002). |
| `organizaciones/tests/integration/test_alta_saga.py` | Alta completa; falla inyectada en cada paso de la saga y verificación de que no queda nada (FR-015); reintento con la misma `Idempotency-Key` (FR-016). |
| `organizaciones/tests/unit/test_validators.py` | RFC moral, físico, genérico y con fecha inválida; régimen contra tipo de persona; teléfono; códigos postales; magic bytes del logotipo. |
| `organizaciones/tests/integration/test_concurrencia.py` | 412 con un `If-Match` desactualizado (FR-025). |
| `organizaciones/tests/integration/test_busqueda.py` | Búsqueda sin acentos ni mayúsculas, filtro por estatus, paginación y entrada con metacaracteres de expresión regular. |
| `core/tests/test_tenancy_aislamiento.py` | La base se elige sólo por el claim `tenant_id`; se ignora cualquier tenant en la ruta, la consulta, los encabezados o el cuerpo (principio IV). |
| `core/tests/test_require_active_tenant.py` | 403 `ORGANIZACION_DESHABILITADA` en la primera petición después de deshabilitar, sin caché (FR-028). |
| `organizaciones/tests/integration/test_aislamiento_altas.py` | Altas de A y B: cada ADMIN queda con su propio `custom:tenant_id`; deshabilitar A no afecta el estatus ni el acceso de B. |
| `infra/shared/src/cognito_triggers/tests/` | Inyección de `tenant_id`; rechazo de organizaciones deshabilitadas o en `aprovisionando`; SUPER_ADMIN sin cambios. |

## 3. Despliegue a `dev`

No se despliega desde una máquina local (principio X). Se abre un PR, CI pasa, y al integrarlo en
`main` corre `deploy-dev.yml`:

`shared` → `organizaciones` → `seed_catalogos.py`

El primer SUPER_ADMIN se crea ejecutando el workflow **crear-super-admin** en GitHub Actions,
desde la pestaña Actions, con el correo como entrada.

## 4. Escenarios de aceptación en `dev`

Se ejecutan contra la API (`ApiUrl` en las salidas del stack `condo-shared-dev`, en `$API`) con un
access token de SUPER_ADMIN en `$TOKEN`. Para obtenerlo, se inicia sesión en el managed login de
`dev` (la callback `http://localhost:4200` está permitida en ese ambiente) y se canjea el código en
el endpoint `/oauth2/token` de Cognito con PKCE.

### 4.1 Alta (historia 1)

```bash
curl -sS -X POST "$API/organizaciones" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d @alta-ejemplo.json
```

El archivo `alta-ejemplo.json` sigue el esquema `OrganizacionAlta` de
[organizaciones.openapi.yaml](./contracts/organizaciones.openapi.yaml), con un RFC y un correo de
prueba nuevos.

**Resultado esperado**:
- `201`, con un `tenantId` de 32 caracteres hexadecimales, `estatus: "activa"` y un `ETag: "1"`.
- El correo del ADMIN recibe la invitación en menos de 5 minutos (SC-002), con el enlace al aviso
  de privacidad (FR-031).
- Al repetir el mismo comando con la misma `Idempotency-Key`, se recibe `201` con el mismo
  `tenantId` y no aparece una segunda organización.
- Al repetirlo con otra llave y el mismo RFC, se recibe `409 RFC_DUPLICADO`.

### 4.2 Primer acceso del ADMIN (historia 1, escenario 5)

1. Seguir la invitación, cambiar la contraseña temporal en el managed login y obtener su token
   igual que el del SUPER_ADMIN.
2. Decodificar el access token: contiene `cognito:groups: ["ADMIN"]` y el `tenant_id` de su
   organización.
3. Con ese token, `GET /organizaciones` responde `403`.

### 4.3 Deshabilitar y rehabilitar (historia 2)

1. Con el ADMIN dentro de la plataforma, el SUPER_ADMIN ejecuta
   `POST /organizaciones/{tenantId}/deshabilitar` con `If-Match`.
2. Un nuevo inicio de sesión del ADMIN es rechazado, y también la renovación de su token. Todavía
   no hay endpoints de tenant donde probar el rechazo de una sesión abierta; ese caso lo cubre
   `core/tests/test_require_active_tenant.py` (SC-003).
3. `POST /organizaciones/{tenantId}/habilitar` → el ADMIN vuelve a iniciar sesión.

### 4.4 Listado y búsqueda (historia 3)

- `GET /organizaciones?q=condominios%20del%20bajio` encuentra "Condominios del Bajío".
- `GET /organizaciones?estatus=deshabilitada` sólo devuelve deshabilitadas.

### 4.5 Modificación (historia 4)

- `PATCH` con el `ETag` vigente cambia el teléfono → `200` con `ETag: "n+1"` y el nuevo
  teléfono en el detalle.
- El mismo `PATCH` con el `ETag` anterior → `412 VERSION_DESACTUALIZADA`.
- Quitar un módulo → el detalle ya no lo muestra en `modulosHabilitados`.
- `PUT /logo` con un PDF renombrado a `.png` → `415 LOGO_TIPO_NO_SOPORTADO`; con un PNG de 3 MB →
  `413 LOGO_DEMASIADO_GRANDE`.

## 5. Verificaciones de cumplimiento

- **Logs**: en CloudWatch, cada línea de las Lambdas incluye `tenant_id` y `request_id`, y una
  búsqueda del correo de prueba del ADMIN no devuelve resultados (principio VI).
- **Altas fallidas**: no quedan documentos en `aprovisionando` con más de 15 minutos, ni usuarios
  de Cognito con un `custom:tenant_id` que no exista en `platform.organizaciones`.
- **Despliegue a `prod`**: ejecutar `deploy-prod.yml` sobre un tag. El job espera la aprobación de
  un revisor del environment `prod` antes de tocar AWS.
