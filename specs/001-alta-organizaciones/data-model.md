# Data Model: Alta de organizaciones

**Feature**: `001-alta-organizaciones` | **Date**: 2026-10-28

Los nombres de campo están en camelCase, igual que en la API. Las fechas se guardan en UTC como
`Date` de MongoDB.

## Bases de datos

| Base | Contenido | Quién accede |
|---|---|---|
| `platform` | Registro de organizaciones | Módulo `organizaciones` (SUPER_ADMIN). El disparador de Cognito y `require_active_tenant()` sólo leen el campo `estatus` de la organización del token. |
| `shared` | Catálogos globales | Todos los módulos, sólo lectura. Lo escribe únicamente `seed_catalogos.py` desde el pipeline. |
| `t_<tenantId>` | Datos de operación de una organización | Sólo los usuarios de esa organización, a través de `condo_core.tenancy`. Esta funcionalidad no crea la base: MongoDB la crea cuando un módulo de operación guarda su primer dato. |

---

## platform.organizaciones

Representa la entidad **Organización**. Un documento por organización.

| Campo | Tipo | Obligatorio | Reglas |
|---|---|---|---|
| `_id` | string | sí | `tenantId`: 32 caracteres hexadecimales en minúsculas (`^[0-9a-f]{32}$`). Inmutable (FR-011). |
| `estatus` | string | sí | `aprovisionando` \| `activa` \| `deshabilitada`. Ver transiciones. |
| `nombreComercial` | string | sí | 2 a 150 caracteres, sin espacios al inicio ni al final. |
| `contacto.nombre` | string | sí | 2 a 120 caracteres. |
| `contacto.correo` | string | sí | Correo válido, hasta 254 caracteres, guardado en minúsculas. |
| `contacto.telefono` | string | sí | Exactamente 10 dígitos (`^\d{10}$`). |
| `direccion` | object | no | Si se envía, `calle`, `numeroExterior`, `colonia`, `municipio`, `estado` y `codigoPostal` son obligatorios. |
| `direccion.calle` | string | condicional | 1 a 150 caracteres. |
| `direccion.numeroExterior` | string | condicional | 1 a 20 caracteres. |
| `direccion.numeroInterior` | string | no | 1 a 20 caracteres. |
| `direccion.colonia` | string | condicional | 1 a 100 caracteres. |
| `direccion.municipio` | string | condicional | Municipio o alcaldía, 1 a 100 caracteres. |
| `direccion.estado` | string | condicional | Una de las 32 entidades federativas. |
| `direccion.codigoPostal` | string | condicional | `^\d{5}$`. |
| `logo` | object | no | Ausente si no hay logotipo. |
| `logo.key` | string | sí (si `logo`) | Llave en S3: `logos/<tenantId>/<uuid>.<png\|jpg>`. |
| `logo.contentType` | string | sí (si `logo`) | `image/png` \| `image/jpeg`, verificado por magic bytes. |
| `logo.bytes` | int | sí (si `logo`) | 1 a 2,097,152. |
| `fiscal.rfc` | string | sí | Mayúsculas. Moral: `^[A-ZÑ&]{3}\d{6}[A-Z\d]{3}$`; física: `^[A-ZÑ&]{4}\d{6}[A-Z\d]{3}$`. La fecha embebida debe ser válida. Sin RFC genéricos. **Único** (FR-005). |
| `fiscal.razonSocial` | string | sí | 2 a 254 caracteres. |
| `fiscal.regimenFiscal` | string | sí | Clave existente y vigente en `shared.regimenes_fiscales`, que aplique al tipo de persona del RFC. |
| `fiscal.codigoPostal` | string | sí | `^\d{5}$`. |
| `modulosHabilitados` | string[] | sí | Al menos 1, sin repetidos (FR-023). En altas y modificaciones, cada clave nueva debe existir en `shared.modulos` con `disponible: true`. Las claves que la organización ya tenía se conservan aunque el módulo deje de estar disponible. |
| `facturacion.diaCorte` | int | sí | 1 a 28 (FR-008). |
| `facturacion.diaLimitePago` | int | sí | 1 a 28. Si es menor que `diaCorte`, corresponde al mes siguiente. |
| `adminInicial.sub` | string | desde `activa` | `sub` del usuario en Cognito. Ausente mientras el estatus es `aprovisionando`; se guarda al pasar a `activa`, porque el usuario se crea después de insertar el documento. |
| `adminInicial.nombre` | string | sí | 2 a 120 caracteres. |
| `adminInicial.correo` | string | sí | Correo en minúsculas. Único en el user pool. |
| `adminInicial.invitacionEnviadaEn` | date | desde `activa` | Ausente mientras el estatus es `aprovisionando`; se guarda al pasar a `activa` y se actualiza al reenviar la invitación. |
| `busqueda` | string | sí | Derivado: `normalize(nombreComercial + " " + fiscal.razonSocial + " " + fiscal.rfc)`. Nunca se acepta del cliente. |
| `idempotencyKey` | string | sí | Valor del encabezado `Idempotency-Key` del alta (UUID). **Único**. |
| `requestHash` | string | sí | SHA-256 del cuerpo normalizado del alta. |
| `version` | int | sí | Empieza en 1 y se incrementa en cada cambio de datos o de estatus de la organización (FR-025). **No** se incrementa al reenviar la invitación, que sólo actualiza `adminInicial.invitacionEnviadaEn`, para que un reenvío no invalide la edición en curso de otro SUPER_ADMIN. |
| `creadoEn` | date | sí | Fecha de alta; ordena el listado. |
| `actualizadoEn` | date | sí | Fecha del último cambio que incrementó `version`. |
| `deshabilitadoEn` | date | no | Presente sólo mientras está deshabilitada. |

**Índices**:
- `{ "fiscal.rfc": 1 }`, único.
- `{ idempotencyKey: 1 }`, único.
- `{ estatus: 1, creadoEn: -1 }`.

**Campos que no se pueden modificar** (FR-022): `_id`, `adminInicial.*`, `busqueda`,
`idempotencyKey`, `requestHash`, `version`, `creadoEn`, `estatus`. El estatus sólo cambia mediante
las acciones de deshabilitar y habilitar.

### Transiciones de estatus

```text
               alta OK                  deshabilitar
 (nuevo) ──► aprovisionando ──► activa ◄──────────────► deshabilitada
                   │                       habilitar
                   │ falla / reconciliador
                   ▼
              (se elimina por compensación; no queda registro)
```

- `aprovisionando` es interno: no aparece en el listado ni en el filtro por estatus, y el detalle
  responde 404. El disparador de Cognito sólo emite tokens a organizaciones `activa`, así que el
  ADMIN no puede entrar mientras el alta no termina.
- Deshabilitar una organización ya deshabilitada, o habilitar una activa, responde 409
  `ESTATUS_SIN_CAMBIO` y no modifica nada.

---

## shared.modulos

Entidad **Módulo**. Catálogo global sembrado por `seed_catalogos.py`.

| Campo | Tipo | Reglas |
|---|---|---|
| `_id` | string | Clave estable en kebab-case, por ejemplo `condominios`. |
| `nombre` | string | Nombre visible. |
| `descripcion` | string | |
| `disponible` | bool | `false` = ya no se ofrece en altas nuevas, pero las organizaciones que lo tienen lo conservan. |
| `orden` | int | Orden de presentación. |

**Semilla inicial (tentativa, a confirmar)**: `condominios`, `condominos`, `cuotas`, `pagos`,
`avisos`, `areas-comunes`.

---

## shared.regimenes_fiscales

Catálogo del SAT (`c_RegimenFiscal`), sembrado por `seed_catalogos.py`.

| Campo | Tipo | Reglas |
|---|---|---|
| `_id` | string | Clave de 3 dígitos, por ejemplo `601`. |
| `descripcion` | string | |
| `personaFisica` | bool | |
| `personaMoral` | bool | |
| `vigente` | bool | |

**Semilla**: claves de `c_RegimenFiscal` vigentes (601, 603, 605, 606, 607, 608, 610, 611, 612,
614, 615, 616, 620, 621, 622, 623, 624, 625 y 626), con su aplicabilidad a persona física o moral.
Antes de sembrar hay que verificarlas contra el catálogo publicado por el SAT.

---

## Cognito (user pool por ambiente)

No es parte de MongoDB, pero forma parte del modelo de identidad.

| Elemento | Valor |
|---|---|
| Nombre de usuario | Correo (`UsernameAttributes: email`), sin distinguir mayúsculas. |
| Grupos | `SUPER_ADMIN`, `ADMIN`, `ASISTENTE`. |
| `custom:tenant_id` | String de 32 caracteres, **no modificable**, que el app client no puede escribir. Ausente en SUPER_ADMIN. |
| Vigencia de la contraseña temporal | 7 días. |
| Claims del access token | Ver [contracts/cognito-claims.md](./contracts/cognito-claims.md). |
