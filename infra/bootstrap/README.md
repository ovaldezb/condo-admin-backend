# Stack de arranque (`condo-bootstrap`)

Crea lo que GitHub Actions necesita para desplegar todo lo demás:

- El proveedor OIDC de GitHub (`token.actions.githubusercontent.com`).
- Los roles `condo-deploy-dev` y `condo-deploy-prod`. Cada uno sólo lo puede asumir un job de este
  repositorio que use el environment correspondiente de GitHub.
- El permissions boundary `condo-boundary`. Todo rol que creen los stacks del pipeline debe
  llevarlo; los roles de despliegue no pueden crear roles sin él.
- El bucket de despliegue `condo-deployments-<cuenta>-<región>`, que usan los demás stacks.

## Por qué se despliega a mano

La constitución (principio X) prohíbe desplegar desde una máquina local, con **una única
excepción**: este stack. GitHub Actions no puede autenticarse en AWS antes de que exista el
proveedor OIDC, así que alguien tiene que crearlo primero.

Reglas de la excepción:

- Se despliega **una sola vez por cuenta de AWS**.
- La definición vive en este repositorio (`infra/bootstrap/serverless.yml`).
- **Cualquier cambio posterior pasa por revisión en el repositorio** (PR aprobado) antes de que
  un administrador lo vuelva a aplicar.

## Procedimiento único por cuenta

Lo ejecuta un administrador de la cuenta de AWS, con sus propias credenciales temporales (por
ejemplo, IAM Identity Center). No se usan llaves de acceso permanentes.

```bash
cd infra/bootstrap
npm ci --prefix ../..           # instala Serverless Framework v4 (package.json de la raíz)

# La clave de licencia sólo vive en la sesión; no se guarda en archivos.
read -rs SERVERLESS_LICENSE_KEY && export SERVERLESS_LICENSE_KEY

npx serverless deploy --region us-east-1
unset SERVERLESS_LICENSE_KEY
```

Este es el único stack que usa el bucket de despliegue por defecto de Serverless, porque se
despliega antes de que exista `condo-deployments-*`, que él mismo crea.

Si el repositorio cambia de organización o de nombre en GitHub, hay que actualizar `githubOrg` y
`githubRepo` en `params` (por PR) y volver a aplicar el stack.

## Después del despliegue

1. Copiar las salidas `DeployDevRoleArn` y `DeployProdRoleArn`.
2. En GitHub, en cada environment (`dev` y `prod`), definir:
   - La variable `AWS_DEPLOY_ROLE_ARN` con el ARN del rol correspondiente.
   - La variable `AWS_REGION` (`us-east-1`).
   - El secreto `SERVERLESS_LICENSE_KEY` (research.md, decisión 2).
3. En el environment `prod`, configurar revisores obligatorios.
4. Mapear los roles en MongoDB Atlas según [`infra/atlas/README.md`](../atlas/README.md).

## Verificar que no hubo cambios manuales

```bash
aws cloudformation detect-stack-drift --stack-name condo-bootstrap
aws cloudformation describe-stack-resource-drifts --stack-name condo-bootstrap \
  --stack-resource-drift-status-filters MODIFIED DELETED
```

Cualquier diferencia indica un cambio hecho fuera del repositorio y debe revertirse.
