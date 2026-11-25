#!/usr/bin/env bash
# Ensambla el HLD: concatena las secciones (00–08) y los ADR (001–007) en docs/hld/HLD.md y,
# si pandoc está instalado, genera docs/hld/HLD.pdf.
#
# Uso (desde cualquier carpeta):
#   bash docs/hld/build_hld.sh            # HLD.md + HLD.pdf (si hay pandoc)
#   bash docs/hld/build_hld.sh --md-only  # solo HLD.md
#
# Si una sección o ADR todavía no existe (p. ej. las de Juan Pablo), se inserta un aviso
# "PENDIENTE" en su lugar para que el documento siga armándose. Al final se listan los pendientes.
# Alternativa sin LaTeX: abrir HLD.md en VS Code con la extensión "Markdown PDF" y exportar.
set -euo pipefail

HLD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCS_DIR="$(dirname "$HLD_DIR")"
OUT_MD="$HLD_DIR/HLD.md"
OUT_PDF="$HLD_DIR/HLD.pdf"

SECTIONS=(
  "00_portada.md"
  "01_contexto.md"
  "02_requisitos.md"
  "03_arquitectura.md"
  "04_seguridad.md"
  "05_disponibilidad.md"
  "06_observabilidad.md"
  "07_riesgos.md"
  "08_decisiones.md"
)
ADRS=("ADR-001" "ADR-002" "ADR-003" "ADR-004" "ADR-005" "ADR-006" "ADR-007")

missing=()

# Título que se muestra si la sección todavía no existe (bash 3.2 de macOS: sin arreglos asociativos).
section_title() {
  case "$1" in
    04_seguridad.md) echo "4. Seguridad e identidad" ;;
    05_disponibilidad.md) echo "5. Disponibilidad, respaldo y recuperación" ;;
    06_observabilidad.md) echo "6. Observabilidad y operación" ;;
    *) echo "${1%.md}" ;;
  esac
}

append_file() {
  # $1 = archivo; agrega una línea en blanco al final para separar secciones.
  cat "$1" >>"$OUT_MD"
  printf '\n\n' >>"$OUT_MD"
}

: >"$OUT_MD"

for section in "${SECTIONS[@]}"; do
  path="$HLD_DIR/sections/$section"
  if [[ -f "$path" ]]; then
    append_file "$path"
  else
    missing+=("sections/$section")
    printf '# %s\n\n> **PENDIENTE:** esta sección aún no se ha entregado.\n\n' "$(section_title "$section")" >>"$OUT_MD"
  fi
done

printf '# Anexo: registros de decisiones de arquitectura (ADR)\n\n' >>"$OUT_MD"
for adr in "${ADRS[@]}"; do
  shopt -s nullglob
  matches=("$DOCS_DIR/adr/$adr"-*.md)
  shopt -u nullglob
  if ((${#matches[@]})); then
    # Dentro del anexo, cada ADR baja un nivel de título (# → ##) para que el índice quede ordenado.
    sed -E 's/^(#{1,5}) /#\1 /' "${matches[0]}" >>"$OUT_MD"
    printf '\n\n' >>"$OUT_MD"
  else
    missing+=("adr/$adr-*.md")
    printf '## %s\n\n> **PENDIENTE:** este ADR aún no se ha entregado.\n\n' "$adr" >>"$OUT_MD"
  fi
done

# Las secciones enlazan los ADR como [ADR-00X](../../adr/ADR-00X-....md) (navegables en GitHub);
# dentro de HLD.md el ADR ya está en el anexo, así que el enlace se reemplaza por el texto "ADR-00X".
sed -i.bak -E 's#\[(ADR-[0-9]{3})\]\((\.\./)+adr/[^)]*\)#\1#g' "$OUT_MD" && rm -f "$OUT_MD.bak"

echo "HLD.md generado: $OUT_MD"

pending_markers=$(grep -c "PENDIENTE" "$OUT_MD" || true)
if ((${#missing[@]})); then
  echo "Faltan ${#missing[@]} archivo(s):"
  printf '  - %s\n' "${missing[@]}"
fi
echo "Marcadores PENDIENTE en el documento: $pending_markers"

if [[ "${1:-}" == "--md-only" ]]; then
  exit 0
fi

if ! command -v pandoc >/dev/null 2>&1; then
  echo "pandoc no está instalado: solo se generó HLD.md."
  echo "Instálalo (macOS: brew install pandoc basictex) o exporta HLD.md con la extensión 'Markdown PDF' de VS Code."
  exit 0
fi

# --resource-path permite resolver las imágenes ../diagrams/png/*.png relativas a docs/hld/.
pandoc "$OUT_MD" -o "$OUT_PDF" \
  --from markdown \
  --toc --toc-depth=2 \
  --resource-path="$HLD_DIR" \
  --pdf-engine=xelatex \
  -V geometry:margin=2.2cm \
  -V mainfont="Helvetica" \
  -V lang=es
echo "HLD.pdf generado: $OUT_PDF"
