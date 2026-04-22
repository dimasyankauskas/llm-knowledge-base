#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="${1:-}"

if [[ -z "$SOURCE_DIR" ]]; then
  echo "Usage: $0 <source_dir>" >&2
  echo "Example: $0 \"$HOME/Downloads/garuda-extract\"" >&2
  exit 2
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "Source directory not found: $SOURCE_DIR" >&2
  exit 2
fi

shopt -s nullglob
FILES=("$SOURCE_DIR"/*.md "$SOURCE_DIR"/*.txt "$SOURCE_DIR"/*.pdf)
shopt -u nullglob

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "No .md/.txt/.pdf files found under: $SOURCE_DIR" >&2
  exit 2
fi

cd "$ROOT_DIR"

if ! command -v wiki >/dev/null 2>&1; then
  echo "Missing 'wiki' CLI in PATH." >&2
  echo "Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && pip install -e ." >&2
  exit 2
fi

echo "Ingesting ${#FILES[@]} file(s) from: $SOURCE_DIR"
for f in "${FILES[@]}"; do
  echo "==> wiki extract $(basename "$f")"
  wiki extract "$f"
done

wiki link
wiki consolidate
wiki lint
wiki state
