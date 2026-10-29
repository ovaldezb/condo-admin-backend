# Constitución de condo-admin

Sistema SaaS multi-tenant de gestión de condominios.

## Principios fundamentales

### I. Stack obligatorio

- El backend DEBE escribirse en Python 3.12 y ejecutarse en AWS Lambda expuesto por API Gateway.
- El frontend DEBE escribirse en Angular 22.
- MongoDB DEBE ser la única base de datos del sistema.
- AWS Cognito DEBE ser el único mecanismo de autenticación y gestión de usuarios. Está PROHIBIDO
  implementar manejo propio de contraseñas o de sesiones.
- La infraestructura DEBE definirse como código (IaC) con Serverless Framework. Está PROHIBIDO
  crear o modificar recursos de AWS a mano fuera de esa definición.
- Backend y frontend DEBEN vivir en repositorios separados.
- Cualquier cambio de stack REQUIERE una enmienda a esta constitución.

**Motivo**: un stack único y cerrado evita divergencias entre módulos y mantiene acotados el costo
de operación y la superficie de seguridad.

### II. Un punto de acceso por módulo

- Cada módulo de negocio DEBE desplegarse como una sola Lambda con una ruta proxy en API Gateway
  y enrutamiento interno.
- Está PROHIBIDO crear una Lambda por endpoint.
- Cada módulo DEBE ser independiente y desplegable por separado.

**Motivo**: no acercarse al límite de 500 recursos por stack de CloudFormation.

### III. Aislamiento multi-tenant (INNEGOCIABLE)

- Cada organización DEBE tener su propia base de datos.
- El tenant DEBE resolverse siempre a partir de los claims del token de Cognito, NUNCA de
  parámetros enviados por el cliente.
- Ninguna consulta PUEDE cruzar datos entre organizaciones.
- Las bases de datos compartidas DEBEN contener únicamente catálogos y configuración global (por
  ejemplo, los paquetes de servicio contratables). NUNCA contienen datos de condóminos, de
  usuarios ni de operación de una organización.
- Las organizaciones DEBEN tener sólo acceso de lectura a las bases de datos compartidas.
- DEBE existir una base de datos de plataforma, distinta de las bases de organización y de las
  compartidas, que contiene el registro de instituciones enroladas con sus datos comerciales y
  fiscales.
- El sistema define tres roles: SUPER_ADMIN (administra la plataforma), ADMIN (gestiona los datos
  de su propia organización) y ASISTENTE (rol operativo dentro de su propia organización).
- Sólo SUPER_ADMIN PUEDE consultar o modificar la base de datos de plataforma. ADMIN y ASISTENTE
  NUNCA acceden a ella. La única excepción es que el backend PUEDE leer el estatus de la
  institución del propio tenant para aplicar reglas de acceso.
- ADMIN y ASISTENTE sólo PUEDEN operar sobre la base de datos de su propia organización.

**Motivo**: una fuga de datos entre organizaciones es el fallo más grave posible en este sistema;
el aislamiento físico por base de datos lo hace verificable.

### IV. Pruebas y cobertura

- La cobertura mínima DEBE ser del 80 % por módulo, medida de forma individual en el CI de cada
  repositorio (backend y frontend).
- Un módulo por debajo del umbral DEBE bloquear la integración, aunque el promedio global lo
  supere.
- Toda feature DEBE incluir pruebas unitarias y de integración.
- Toda feature que toque datos DEBE incluir una prueba de aislamiento entre tenants.

**Motivo**: medir por módulo impide que un módulo bien probado oculte a otro sin pruebas.

### V. Seguridad

- El sistema DEBE cumplir OWASP Top 10 y OWASP API Security Top 10.
- Toda entrada DEBE validarse.
- La autorización DEBE verificarse en cada endpoint.
- Los roles IAM DEBEN seguir el principio de mínimo privilegio.
- Los secretos DEBEN residir sólo en un gestor de secretos, NUNCA en el código ni en el
  repositorio.
- Los datos DEBEN cifrarse en tránsito y en reposo.
- CI DEBE ejecutar análisis de dependencias y análisis estático de código.

### VI. Datos personales

- El sistema trata datos de condóminos y residentes, entre los que puede haber menores de edad.
- DEBE recolectarse sólo el mínimo de datos necesario.
- Está PROHIBIDO escribir datos personales en logs.
- El sistema DEBE cumplir la LFPDPPP de México.

### VII. Pagos

- Los cobros DEBEN procesarse exclusivamente con Openpay.
- El sistema NUNCA almacena ni registra datos de tarjeta; DEBE usarse la tokenización del
  proveedor.
- Los webhooks de pago DEBEN verificarse y procesarse de forma idempotente.
- Toda operación de cobro DEBE quedar en un registro auditable.

**Motivo**: no tocar datos de tarjeta reduce el alcance de cumplimiento, y la idempotencia evita
cobros o acreditaciones duplicadas ante reintentos del proveedor.

### VIII. Observabilidad

- Cada módulo DEBE emitir logs estructurados que incluyan el identificador de tenant y el
  identificador de petición.
- Los logs NO DEBEN contener datos sensibles.

**Motivo**: con una base de datos por organización, el identificador de tenant en cada log es lo
que permite diagnosticar un problema de una organización concreta.

### IX. Frontend

Este principio rige al repositorio del frontend.

- La autenticación DEBE hacerse sólo a través de Cognito.
- El frontend NO DEBE contener secretos ni lógica de autorización propia; toda regla de acceso
  DEBE validarse en el backend.
- El frontend DEBE organizarse en módulos que correspondan a los módulos del backend.

### X. Despliegue

- Todo despliegue a AWS DEBE ejecutarse sólo desde GitHub Actions. Está PROHIBIDO desplegar desde
  una máquina local.
- DEBEN existir dos ambientes: `dev` y `prod`.
- `dev` DEBE desplegarse automáticamente al integrar un cambio en la rama principal.
- `prod` sólo PUEDE desplegarse con aprobación manual.
- GitHub Actions DEBE autenticarse en AWS mediante OIDC. Está PROHIBIDO usar llaves de acceso
  permanentes.
- Excepción: el stack de arranque que crea el proveedor OIDC de GitHub, los roles de despliegue y
  el bucket de despliegue, definido con Serverless Framework y versionado en el repositorio, PUEDE
  desplegarlo un administrador de la cuenta una única vez por cuenta y región de AWS fuera de
  GitHub Actions. Cualquier modificación posterior de ese stack DEBE pasar por revisión en el
  repositorio.

**Motivo**: un único camino de despliegue, trazable y sin credenciales de larga duración, evita
cambios no revisados en AWS y reduce el riesgo de que una llave filtrada comprometa la cuenta. La
excepción existe porque GitHub Actions no puede autenticarse en AWS antes de que exista el
proveedor OIDC.

## Restricciones tecnológicas y de cumplimiento

| Ámbito | Restricción |
|---|---|
| Backend | Python 3.12 en AWS Lambda detrás de API Gateway |
| Infraestructura | Definida como código (IaC) con Serverless Framework |
| Frontend | Angular 22 |
| Base de datos | MongoDB; una base por organización, bases compartidas de sólo lectura y una base de plataforma exclusiva de SUPER_ADMIN |
| Identidad | AWS Cognito; roles SUPER_ADMIN, ADMIN y ASISTENTE |
| Pagos | Openpay, con tokenización del proveedor |
| Seguridad | OWASP Top 10 y OWASP API Security Top 10 |
| Privacidad | LFPDPPP de México |
| Repositorio | Repositorios separados para backend y frontend |
| Despliegue | Sólo desde GitHub Actions con OIDC; ambientes `dev` (automático) y `prod` (aprobación manual) |

## Flujo de desarrollo y puertas de calidad

Un cambio sólo PUEDE integrarse si CI confirma todo lo siguiente:

- Cobertura de al menos el 80 % en cada módulo afectado del repositorio.
- Pruebas unitarias y de integración en verde.
- Prueba de aislamiento entre tenants en verde, cuando la feature toca datos.
- Análisis de dependencias y análisis estático de código sin hallazgos bloqueantes.

## Gobernanza

- Esta constitución prevalece sobre cualquier otra práctica del proyecto.
- Toda enmienda DEBE documentarse con su versión y su fecha.
- Cada plan DEBE verificar su cumplimiento con esta constitución antes de implementarse.
- El versionado sigue versionado semántico: MAJOR cuando se elimina o redefine un principio de
  forma incompatible, MINOR cuando se añade un principio o una sección o se amplía materialmente
  una guía, y PATCH para aclaraciones y correcciones de redacción.

**Versión**: 2.0.1 | **Ratificada**: 2026-10-06 | **Última enmienda**: 2026-10-28
