#!/usr/bin/env bash
# Build the submission report PDF from the Markdown template.
#
# Prerequisites:
#   - pandoc
#   - typst  (used as pandoc --pdf-engine)
#
# Usage (from repo root):
#   ./scripts/build_report_pdf.sh yohei1126
#   ./scripts/build_report_pdf.sh yohei1126 path/to/draft.md
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1
Install tip: brew install pandoc typst"
}

usage() {
  cat <<'EOF'
Usage:
  ./scripts/build_report_pdf.sh <omnicampus_account> [input.md]

Output:
  report/説明資料_PAI最終課題_<omnicampus_account>.pdf
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

ACCOUNT="${1:-}"
[[ -n "$ACCOUNT" ]] || die "omnicampus account name is required
$(usage)"

# Reject path separators / whitespace that would break the official filename rule.
if [[ "$ACCOUNT" == *"/"* || "$ACCOUNT" == *"\\"* || "$ACCOUNT" =~ [[:space:]] ]]; then
  die "omnicampus account must not contain spaces or path separators: '$ACCOUNT'"
fi

DEFAULT_MD="$ROOT/report/説明資料_PAI最終課題_yohei1126.md"
INPUT_MD="${2:-$DEFAULT_MD}"
[[ -f "$INPUT_MD" ]] || die "input markdown not found: $INPUT_MD"

OUT_PDF="$ROOT/report/説明資料_PAI最終課題_${ACCOUNT}.pdf"
PDF_ENGINE="${REPORT_PDF_ENGINE:-typst}"

echo "==> Prerequisite checks"
need_cmd pandoc
need_cmd "$PDF_ENGINE"

echo "==> Building PDF"
echo "    input : $INPUT_MD"
echo "    output: $OUT_PDF"
echo "    engine: $PDF_ENGINE"

# pandoc→typst emits #divider() for thematic breaks (---), which breaks on typst 0.14+.
# Strip standalone --- lines (not table separators) via a temp copy.
TMP_MD="$(mktemp "${TMPDIR:-/tmp}/report_XXXXXX.md")"
trap 'rm -f "$TMP_MD"' EXIT
# shellcheck disable=SC2016
awk '
  /^[[:space:]]*---[[:space:]]*$/ { next }
  { print }
' "$INPUT_MD" >"$TMP_MD"

pandoc "$TMP_MD" \
  -o "$OUT_PDF" \
  --from markdown \
  --pdf-engine="$PDF_ENGINE"

[[ -f "$OUT_PDF" ]] || die "pandoc finished but output PDF is missing: $OUT_PDF"

echo "==> Done: $OUT_PDF"
echo "    Reminder: strip personal info (name / affiliation / email) before submission."
