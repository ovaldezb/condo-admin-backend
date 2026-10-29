# Configuración de MongoDB Atlas

Atlas no es un servicio de AWS, así que no se define con Serverless Framework (el principio I
aplica a los recursos de AWS). Esta guía describe la configuración que debe existir en cada
ambiente. Cualquier cambio a esta guía pasa por PR.

## 1. Clúster por ambiente

| Ambiente | Clúster | Acceso de red |
|---|---|---|
| `dev` (`us-east-1`, AWS `US_EAST_1`) | Cualquier nivel | Lista de acceso abierta (`0.0.0.0/0`), protegida por autenticación IAM y TLS. `dev` no debe contener datos reales. |
| `prod` (`us-west-1`, AWS `US_WEST_1`) | M10 o superior (requisito de PrivateLink) | Sólo por AWS PrivateLink (research.md, decisión 7). |

El cifrado en reposo y en tránsito viene activado por defecto en Atlas (principio V).

## 2. Usuarios de base de datos con autenticación IAM

No hay contraseñas: cada rol de AWS se registra en Atlas como usuario con
**AWS IAM authentication** (tipo "IAM Role"), usando su ARN. Los roles de Lambda tienen nombre fijo:

| Usuario (ARN del rol) | Rol personalizado de Atlas |
|---|---|
| `arn:aws:iam::<cuenta>:role/condo-organizaciones-<stage>` | `condo-organizaciones` |
| `arn:aws:iam::<cuenta>:role/condo-cognito-triggers-<stage>` | `condo-cognito-triggers` |
| `arn:aws:iam::<cuenta>:role/condo-deploy-<stage>` | `condo-deploy` |

### Roles personalizados

Copiados de research.md, decisión 6:

- **`condo-organizaciones`**: "`readWrite` en `platform.organizaciones`. `find` en `shared.*`.
  Ningún privilegio sobre bases `t_*`."
- **`condo-cognito-triggers`**: "`find` en `platform.organizaciones`."

Además, el pipeline necesita uno para sembrar catálogos e índices (`backend/scripts/seed_catalogos.py`):

- **`condo-deploy`**: `find`, `insert`, `update` en `shared.modulos` y
  `shared.regimenes_fiscales`; `createIndex` y `listIndexes` en `platform.organizaciones`.

Los módulos de tenant de funcionalidades posteriores tendrán su propio rol (research.md, decisión 6).

## 3. PrivateLink (sólo `prod`)

1. En Atlas, crear un **Private Endpoint** de AWS en la región del clúster. Atlas muestra el
   nombre del servicio (`com.amazonaws.vpce.<región>.vpce-svc-...`).
2. Registrar ese nombre en `params.prod.atlasPrivateLinkServiceName` de
   `infra/shared/serverless.yml` mediante un PR. El despliegue crea el endpoint de interfaz en la
   VPC de prod.
3. En Atlas, registrar el id del endpoint creado (salida de CloudFormation o consola de VPC) para
   completar la conexión.
4. Usar la cadena de conexión **de PrivateLink** como URI de prod (paso 4).

> **Pendiente para prod:** con el acceso restringido a PrivateLink, el runner de GitHub Actions no
> puede conectarse a Atlas para sembrar catálogos. Antes del primer despliegue a prod hay que
> decidir cómo ejecutar la siembra desde dentro de la VPC (por ejemplo, una Lambda invocada por el
> pipeline). En `dev` funciona tal como está.

## 4. Registrar la URI en el repositorio

La URI no contiene credenciales, así que se versiona (research.md, decisión 6; no se usa SSM):

```yaml
# infra/shared/serverless.yml → params.<stage>.mongodbUri
mongodbUri: mongodb+srv://<clúster>.mongodb.net/?authMechanism=MONGODB-AWS&authSource=$external
```

El cambio se integra por PR. `condo-shared` la publica como salida `MongoDbUri`, y los módulos la
reciben en la variable de entorno `MONGODB_URI`.
