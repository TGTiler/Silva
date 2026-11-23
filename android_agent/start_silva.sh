#!/usr/bin/env bash
# Wrapper para compatibilidade retroativa. Redireciona para o inicializador da raiz.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/../start_silva.sh" "$@"
