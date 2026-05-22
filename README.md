<p align="center">
  <img src="assets/pdf2xlsx-banner.png" alt="pdf2xlsx" width="520" />
</p>

[![CI](https://github.com/SecurityRonin/pdf2xlsx/actions/workflows/ci.yml/badge.svg)](https://github.com/SecurityRonin/pdf2xlsx/actions/workflows/ci.yml)
[![Release](https://github.com/SecurityRonin/pdf2xlsx/actions/workflows/release.yml/badge.svg)](https://github.com/SecurityRonin/pdf2xlsx/releases)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Sponsor](https://img.shields.io/badge/sponsor-h4x0r-ea4aaa?logo=github-sponsors)](https://github.com/sponsors/h4x0r)

Extract tables from PDFs into Excel workbooks — with a split-panel GUI that lets you preview the source PDF on the left and the extracted spreadsheet on the right.

```bash
brew tap SecurityRonin/tap && brew install pdf2xlsx
```

---

## Install

**macOS**
```bash
brew tap SecurityRonin/tap && brew install pdf2xlsx
```

**Debian / Ubuntu / Kali**
```bash
curl -1sLf 'https://dl.cloudsmith.io/public/securityronin/pdf2xlsx/setup.deb.sh' | sudo bash
sudo apt install pdf2xlsx
```

**Windows**

Download the `.msi` from the [latest release](https://github.com/SecurityRonin/pdf2xlsx/releases/latest).

**pip**
```bash
pip install pdf2xlsx
```

---

## Usage

### GUI

```bash
pdf2xlsx-gui
```

Opens a split-panel window:

- **Left** — PDF preview with page thumbnails, a page-jump spinbox, and Prev / Next navigation. Drag a PDF file onto this panel to open it.
- **Right** — Extracted tables appear tab by tab as conversion progresses. Tabs link back to their source page — clicking a tab jumps the PDF viewer to that page, and vice versa.

Click **Open PDF** (or drag a file in) to load and auto-convert. Click **Save XLSX** when done.

### CLI

```bash
# Convert all tables in a PDF to a workbook
pdf2xlsx convert report.pdf report.xlsx

# Choose extraction engine explicitly
pdf2xlsx convert report.pdf report.xlsx --engine pdfplumber
pdf2xlsx convert report.pdf report.xlsx --engine pymupdf
```

---

## How It Works

pdf2xlsx uses two extraction engines and picks the best result:

| Engine | Strength |
|--------|----------|
| **pdfplumber** | Lattice tables with visible borders |
| **pymupdf** | Stream tables and sparse layouts |

Raw extraction output is cleaned up by a postprocessing pipeline that handles common PDF-to-table artefacts:

- **Currency prefix attachment** — lone `$` / `£` / `€` cells are merged with the numeric cell that follows
- **Header alignment** — headers that land in the wrong column after currency extraction are shifted to match their data
- **Sparse column consolidation** — rows for the same logical column that end up in different physical columns are merged
- **Paragraph filtering** — prose that pdfplumber captures below a table is discarded
- **Empty row/column removal**

---

## Output

Each detected table becomes a separate sheet in the workbook, named `p{page}-t{index}`. The GUI shows all sheets as tabs.

---

## Platform Builds

Binary releases are built via GitHub Actions on native runners — no cross-compilation:

| Platform | Runner |
|----------|--------|
| macOS arm64 | `macos-14` |
| macOS x86_64 | `macos-15` |
| Linux amd64 | `ubuntu-24.04` |
| Linux arm64 | `ubuntu-24.04-arm` |
| Windows x86_64 | `windows-latest` |

---

[Privacy Policy](https://securityronin.github.io/pdf2xlsx/privacy/) · [Terms of Service](https://securityronin.github.io/pdf2xlsx/terms/) · © 2026 Security Ronin Ltd
