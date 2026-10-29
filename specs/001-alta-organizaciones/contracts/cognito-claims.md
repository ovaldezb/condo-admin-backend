# Contrato: claims del access token y disparador de Cognito

**Feature**: `001-alta-organizaciones`

Este contrato lo comparten `infra/shared` (disparador), `backend/core` (lectura de claims) y los
consumidores de la API, como el repositorio del frontend.

## Claims del access token

| Claim | Origen | SUPER_ADMIN | ADMIN / ASISTENTE |
|---|---|---|---|
| `sub` | Cognito | sí | sí |
| `username` | Cognito | sí | sí |
| `client_id` | Cognito; lo valida el autorizador JWT | sí | sí |
| `cognito:groups` | Cognito | `["SUPER_ADMIN"]` | `["ADMIN"]` o `["ASISTENTE"]` |
| `tenant_id` | Disparador Pre Token Generation V2, copiado de `custom:tenant_id` | **ausente** | 32 caracteres hexadecimales |

## Reglas de `condo_core.auth`

- Un usuario con más de un grupo, o sin grupos, se rechaza con 403 `PROHIBIDO`.
- `SUPER_ADMIN` con `tenant_id` presente → 403 `PROHIBIDO`, porque indica una mala configuración.
- `ADMIN` o `ASISTENTE` sin `tenant_id`, o con un `tenant_id` que no cumple `^[0-9a-f]{32}$` →
  403 `PROHIBIDO`.
- Ningún valor de tenant que provenga de la ruta, la consulta, los encabezados o el cuerpo se usa
  para elegir la base de datos.

## Disparador `cognito-triggers` (Pre Token Generation V2)

Entrada: evento `TokenGeneration_*` de Cognito, en el inicio de sesión y en la renovación con
refresh token.

1. Si el usuario pertenece a `SUPER_ADMIN`, devuelve el evento sin cambios.
2. Lee `custom:tenant_id` de los atributos del usuario. Si falta, falla y Cognito niega el token.
3. Lee `platform.organizaciones` con `_id = tenant_id`, proyectando sólo `estatus`. Si no existe o
   `estatus != "activa"`, falla con el mensaje `ORGANIZACION_DESHABILITADA` y Cognito niega el
   token.
4. Agrega `tenant_id` a `claimsAndScopeOverrideDetails.accessTokenGeneration.claimsToAddOrOverride`.

El disparador registra `tenant_id` y el resultado, nunca el correo ni otros atributos del usuario.
