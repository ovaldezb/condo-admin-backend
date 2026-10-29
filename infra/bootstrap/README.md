# Stack de arranque (`condo-bootstrap`)

Crea lo que GitHub Actions necesita para desplegar todo lo demás:

- El proveedor OIDC de GitHub (`token.actions.githubusercontent.com`).
- Los roles `condo-deploy-dev` y `condo-deploy-prod`. Cada uno sólo lo puede asumir un job de este
  repositorio que use el environment correspondiente de GitHub.
- El permissions boundary `condo-boundary`. Todo rol que creen los stacks del pipeline debe
  llevarlo; los roles de despliegue no pueden crear roles sin él.
- El bucket de despliegue `condo-deployments-<cuenta>-<región>`, que usan los demás stacks.

Se usa **una sola cuenta de AWS con dos regiones**: `dev` en `us-east-1` y `prod` en `us-west-1`
(`params.devRegion` y `params.prodRegion`). IAM es global, así que el proveedor OIDC, el
boundary y los roles se crean sólo en la región de dev; en la de prod el stack crea únicamente el
bucket de despliegue de esa región.

## Por qué se despliega a mano

La constitución (principio X) prohíbe desplegar desde una máquina local, con **una única
excepción**: este stack. GitHub Actions no puede autenticarse en AWS antes de que exista el
proveedor OIDC, así que alguien tiene que crearlo primero.

Reglas de la excepción:

- Se despliega **una sola vez por cuenta y región** (constitución 2.0.1): aquí, una vez en
  `us-east-1` y una vez en `us-west-1`.
- La definición vive en este repositorio (`infra/bootstrap/serverless.yml`).
- **Cualquier cambio posterior pasa por revisión en el repositorio** (PR aprobado) antes de que
  un administrador lo vuelva a aplicar.

## Procedimiento único por cuenta y región

Lo ejecuta un administrador de la cuenta de AWS, con sus propias credenciales temporales (por
ejemplo, IAM Identity Center). No se usan llaves de acceso permanentes.

```bash
cd infra/bootstrap
npm ci --prefix ../..           # instala Serverless Framework v4 (package.json de la raíz)

# Access key de serverless.com: sólo vive en la sesión; no se guarda en archivos.
read -rs SERVERLESS_ACCESS_KEY && export SERVERLESS_ACCESS_KEY

# 1. Región de dev (principal): recursos globales de IAM + bucket de us-east-1.
npx serverless deploy --region us-east-1
# 2. Región de prod: sólo el bucket de us-west-1.
npx serverless deploy --region us-west-1

unset SERVERLESS_ACCESS_KEY
```

Este es el único stack que usa el bucket de despliegue por defecto de Serverless, porque se
despliega antes de que exista `condo-deployments-*`, que él mismo crea.

Si cambia la región de algún ambiente, hay que actualizar `params` (por PR), aplicar el stack en
la región nueva y cambiar la variable `AWS_REGION` del environment de GitHub.

Si el repositorio cambia de organización o de nombre en GitHub, hay que actualizar `githubOrg` y
`githubRepo` en `params` (por PR) y volver a aplicar el stack.

## Después del despliegue

1. Copiar las salidas `DeployDevRoleArn` y `DeployProdRoleArn` del stack de `us-east-1`.
2. En GitHub, en cada environment, definir:

   | Nombre | Tipo | `dev` | `prod` |
   |---|---|---|---|
   | `AWS_DEPLOY_ROLE_ARN` | Variable | ARN de `condo-deploy-dev` | ARN de `condo-deploy-prod` |
   | `AWS_REGION` | Variable | `us-east-1` | `us-west-1` |
   | `SERVERLESS_ACCESS_KEY` | Secreto | access key de serverless.com | access key de serverless.com |

3. En el environment `prod`, configurar revisores obligatorios.
4. Mapear los roles en MongoDB Atlas según [`infra/atlas/README.md`](../atlas/README.md).

## Verificar que no hubo cambios manuales

```bash
# Repetir con --region us-west-1 para el stack de prod.
aws cloudformation detect-stack-drift --stack-name condo-bootstrap --region us-east-1
aws cloudformation describe-stack-resource-drifts --stack-name condo-bootstrap --region us-east-1 \
  --stack-resource-drift-status-filters MODIFIED DELETED
```

Cualquier diferencia indica un cambio hecho fuera del repositorio y debe revertirse.
