#!/usr/bin/env bash
# Build a .deb package from a PyInstaller dist directory.
# Requires: fpm (gem install fpm)
set -euo pipefail

VERSION="${VERSION:-0.1.0}"
ARCH="${ARCH:-amd64}"
DIST_DIR="${DIST_DIR:-dist/pdf2xlsx}"
STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT

mkdir -p "${STAGE_DIR}/usr/bin"
mkdir -p "${STAGE_DIR}/usr/share/applications"
mkdir -p "${STAGE_DIR}/usr/share/doc/pdf2xlsx"

cp "${DIST_DIR}/pdf2xlsx" "${STAGE_DIR}/usr/bin/pdf2xlsx"
chmod 755 "${STAGE_DIR}/usr/bin/pdf2xlsx"

cat > "${STAGE_DIR}/usr/share/applications/pdf2xlsx.desktop" <<EOF
[Desktop Entry]
Name=pdf2xlsx
Comment=Extract tables from PDFs into Excel workbooks
Exec=/usr/bin/pdf2xlsx
Type=Application
Categories=Office;Utility;
EOF

fpm \
  --input-type dir \
  --output-type deb \
  --name pdf2xlsx \
  --version "${VERSION}" \
  --architecture "${ARCH}" \
  --maintainer "SecurityRonin <security-ronin@users.noreply.github.com>" \
  --description "PDF to XLSX table extractor — GUI and CLI" \
  --url "https://github.com/h4x0r/pdf2xlsx" \
  --license MIT \
  --category utils \
  --deb-priority optional \
  --chdir "${STAGE_DIR}" \
  .

echo "Built: pdf2xlsx_${VERSION}_${ARCH}.deb"
