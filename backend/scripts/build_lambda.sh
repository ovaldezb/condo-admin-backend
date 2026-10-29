#!/usr/bin/env bash
# Empaqueta una Lambda de Python 3.12 para arm64: el proyecto y sus dependencias en un zip.
#
# Usa uv en lugar de serverless-python-requirements porque los módulos dependen de condo_core,
# un paquete local fuera de la carpeta de cada servicio, y porque uv instala directamente los
# wheels de arm64 sin Docker ni emulación.
#
# Uso: build_lambda.sh <proyecto-uv> <zip-de-salida> [paquete-del-workspace]
#   build_lambda.sh backend backend/modules/organizaciones/.build/lambda.zip organizaciones
#   build_lambda.sh infra/shared infra/shared/.build/lambda.zip
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Uso: $0 <proyecto-uv> <zip-de-salida> [paquete-del-workspace]" >&2
  exit 2
fi

project_dir=$(cd "$1" && pwd)
mkdir -p "$(dirname "$2")"
out_zip="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
package=${3:-}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

export_args=(--frozen --no-dev --no-editable --no-hashes --format requirements.txt
             --output-file "$work/requirements.txt")
if [[ -n $package ]]; then
  export_args+=(--package "$package")
fi

cd "$project_dir"
uv export --quiet "${export_args[@]}"
# --no-cache: los paquetes locales (condo_core y el módulo) conservan la versión 0.1.0, así que
# una compilación en caché empaquetaría código viejo.
uv pip install --quiet --no-deps --no-cache \
  --target "$work/package" \
  --python-version 3.12 \
  --python-platform aarch64-manylinux2014 \
  --requirement "$work/requirements.txt"

find "$work/package" -type d -name __pycache__ -prune -exec rm -rf {} +
rm -f "$out_zip"
(cd "$work/package" && zip -qr9 "$out_zip" .)
echo "Lambda empaquetada: $out_zip ($(du -h "$out_zip" | cut -f1))"
