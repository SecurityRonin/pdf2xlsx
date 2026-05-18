# GUI Converter Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a cross-platform PySide6 desktop app that previews a PDF on the left and shows extracted XLSX tables on the right, packaged as MSI/deb/Homebrew following the blazehash release pattern.

**Architecture:** PySide6 QMainWindow with a QSplitter — left panel renders PDF pages via pymupdf pixmaps, right panel shows extracted tables in a QTabWidget of QTableWidgets. PyInstaller bundles the app into a single executable; GitHub Actions matrix builds produce MSI (WiX), .deb (fpm), and macOS .dmg + Homebrew formula.

**Tech Stack:** PySide6 ≥6.7, pymupdf (existing), pytest-qt, PyInstaller, WiX Toolset (Windows CI), fpm (Linux CI), create-dmg (macOS CI), GitHub Actions.

---

## Task 1: Add PySide6 + pytest-qt to project

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add dependencies**

Edit `pyproject.toml` — add `"PySide6>=6.7"` to `dependencies` and `"pytest-qt>=4.4"` to `[dependency-groups] dev`. Also add a new script entry `pdf2xlsx-gui = "pdf2xlsx.gui.app:main"`.

```toml
[project]
dependencies = [
    "pdfplumber>=0.11",
    "pymupdf>=1.24",
    "openpyxl>=3.1",
    "typer>=0.12",
    "rich>=13.0",
    "PySide6>=6.7",
]

[project.scripts]
pdf2xlsx = "pdf2xlsx.cli:app"
pdf2xlsx-gui = "pdf2xlsx.gui.app:main"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "pytest-qt>=4.4",
]
```

**Step 2: Install**

```bash
uv sync --group dev
```

Expected: PySide6 and pytest-qt installed, no errors.

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add PySide6 + pytest-qt dependencies"
```

---

## Task 2: GUI package skeleton + MainWindow (RED)

**Files:**
- Create: `src/pdf2xlsx/gui/__init__.py`
- Create: `src/pdf2xlsx/gui/app.py`
- Create: `src/pdf2xlsx/gui/main_window.py`
- Test: `tests/test_gui.py`

**Step 1: Write the failing tests**

```python
# tests/test_gui.py
import pytest
from pytestqt.qtbot import QtBot


def test_main_window_title(qtbot):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.windowTitle() == "pdf2xlsx"


def test_main_window_has_open_button(qtbot):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.btn_open is not None


def test_main_window_has_convert_button(qtbot):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.btn_convert is not None
    assert not win.btn_convert.isEnabled()  # disabled until PDF loaded


def test_main_window_has_save_button(qtbot):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.btn_save is not None
    assert not win.btn_save.isEnabled()  # disabled until converted


def test_main_window_has_splitter(qtbot):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.splitter is not None


def test_main_window_has_pdf_panel(qtbot):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.pdf_panel is not None


def test_main_window_has_xlsx_panel(qtbot):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.xlsx_panel is not None
```

**Step 2: Run to verify RED**

```bash
uv run pytest tests/test_gui.py -v
```

Expected: FAIL with `ModuleNotFoundError: pdf2xlsx.gui.main_window`

**Step 3: Create the package skeleton**

`src/pdf2xlsx/gui/__init__.py` — empty file.

`src/pdf2xlsx/gui/main_window.py`:

```python
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QToolBar, QStatusBar
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from pdf2xlsx.gui.pdf_panel import PdfPanel
from pdf2xlsx.gui.xlsx_panel import XlsxPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pdf2xlsx")
        self.resize(1280, 800)
        self._pdf_path = None
        self._tables = []
        self._build_toolbar()
        self._build_central()
        self.setStatusBar(QStatusBar())

    def _build_toolbar(self):
        tb = QToolBar("Main")
        self.addToolBar(tb)

        self.btn_open = tb.addAction("Open PDF")
        self.btn_open.triggered.connect(self._on_open)

        tb.addSeparator()

        self.btn_convert = tb.addAction("Convert")
        self.btn_convert.setEnabled(False)
        self.btn_convert.triggered.connect(self._on_convert)

        tb.addSeparator()

        self.btn_save = tb.addAction("Save XLSX")
        self.btn_save.setEnabled(False)
        self.btn_save.triggered.connect(self._on_save)

    def _build_central(self):
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.pdf_panel = PdfPanel()
        self.xlsx_panel = XlsxPanel()
        self.splitter.addWidget(self.pdf_panel)
        self.splitter.addWidget(self.xlsx_panel)
        self.splitter.setSizes([640, 640])
        self.setCentralWidget(self.splitter)

    def _on_open(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF", "", "PDF Files (*.pdf)"
        )
        if path:
            self._pdf_path = path
            self.pdf_panel.load_pdf(path)
            self.btn_convert.setEnabled(True)
            self.btn_save.setEnabled(False)
            self.xlsx_panel.clear()
            self.statusBar().showMessage(f"Loaded: {path}")

    def _on_convert(self):
        from pathlib import Path
        from pdf2xlsx.extractor import extract_tables
        self.statusBar().showMessage("Converting…")
        try:
            self._tables = extract_tables(Path(self._pdf_path))
            self.xlsx_panel.load_tables(self._tables)
            self.btn_save.setEnabled(True)
            self.statusBar().showMessage(
                f"Extracted {len(self._tables)} table(s)"
            )
        except Exception as exc:
            self.statusBar().showMessage(f"Error: {exc}")

    def _on_save(self):
        from PySide6.QtWidgets import QFileDialog
        from pathlib import Path
        from pdf2xlsx.writer import write_xlsx
        path, _ = QFileDialog.getSaveFileName(
            self, "Save XLSX", "", "Excel Files (*.xlsx)"
        )
        if path:
            write_xlsx(self._tables, Path(path))
            self.statusBar().showMessage(f"Saved: {path}")
```

**Step 4: Run to confirm GREEN**

```bash
uv run pytest tests/test_gui.py -v
```

Expected: all 7 pass (PdfPanel + XlsxPanel stubs needed first — see Task 3).

**Step 5: Commit**

```bash
git add src/pdf2xlsx/gui/ tests/test_gui.py
git commit -m "feat(GREEN): MainWindow skeleton with toolbar and panels"
```

---

## Task 3: PdfPanel — PDF page renderer (RED → GREEN)

**Files:**
- Create: `src/pdf2xlsx/gui/pdf_panel.py`
- Test: `tests/test_gui.py` (append)

**Step 1: Add tests for PdfPanel**

Append to `tests/test_gui.py`:

```python
def test_pdf_panel_loads_pdf(qtbot, tmp_path):
    """PdfPanel accepts a real PDF path and renders page 1."""
    import shutil
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    src = "tests/fixtures/term_sheet.pdf"
    dst = str(tmp_path / "test.pdf")
    shutil.copy(src, dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)
    panel.load_pdf(dst)
    # Page label should show page 1
    assert panel.lbl_page.text() == "Page 1 / 1" or panel.lbl_page.text().startswith("Page 1")


def test_pdf_panel_prev_next_buttons(qtbot, tmp_path):
    """Multi-page PDF: next/prev navigate pages."""
    import shutil
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    src = "tests/fixtures/annual_report.pdf"
    dst = str(tmp_path / "multi.pdf")
    shutil.copy(src, dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)
    panel.load_pdf(dst)
    assert panel.current_page == 0
    qtbot.mouseClick(panel.btn_next, Qt.MouseButton.LeftButton)
    assert panel.current_page == 1
    qtbot.mouseClick(panel.btn_prev, Qt.MouseButton.LeftButton)
    assert panel.current_page == 0
```

Also add to top of file:
```python
from PySide6.QtCore import Qt
```

**Step 2: Run RED**

```bash
uv run pytest tests/test_gui.py::test_pdf_panel_loads_pdf -v
```

Expected: FAIL with ImportError

**Step 3: Implement PdfPanel**

`src/pdf2xlsx/gui/pdf_panel.py`:

```python
import fitz  # pymupdf
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QPushButton, QSizePolicy
)
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import Qt


class PdfPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc = None
        self.current_page = 0
        self._zoom = 1.5
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Navigation bar
        nav = QHBoxLayout()
        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.clicked.connect(self._prev_page)
        self.btn_prev.setEnabled(False)
        self.lbl_page = QLabel("No document")
        self.lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_next = QPushButton("Next ▶")
        self.btn_next.clicked.connect(self._next_page)
        self.btn_next.setEnabled(False)
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.lbl_page, 1)
        nav.addWidget(self.btn_next)
        layout.addLayout(nav)

        # Scrollable page image
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.lbl_img = QLabel()
        self.lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_img.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.scroll.setWidget(self.lbl_img)
        layout.addWidget(self.scroll, 1)

    def load_pdf(self, path: str):
        if self._doc:
            self._doc.close()
        self._doc = fitz.open(path)
        self.current_page = 0
        self._render()

    def _render(self):
        if not self._doc:
            return
        page = self._doc[self.current_page]
        mat = fitz.Matrix(self._zoom, self._zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = QImage(
            pix.samples, pix.width, pix.height,
            pix.stride, QImage.Format.Format_RGB888
        )
        self.lbl_img.setPixmap(QPixmap.fromImage(img))
        total = len(self._doc)
        self.lbl_page.setText(f"Page {self.current_page + 1} / {total}")
        self.btn_prev.setEnabled(self.current_page > 0)
        self.btn_next.setEnabled(self.current_page < total - 1)

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._render()

    def _next_page(self):
        if self._doc and self.current_page < len(self._doc) - 1:
            self.current_page += 1
            self._render()
```

**Step 4: Run GREEN**

```bash
uv run pytest tests/test_gui.py -v
```

Expected: all pass.

**Step 5: Commit**

```bash
git add src/pdf2xlsx/gui/pdf_panel.py tests/test_gui.py
git commit -m "feat(GREEN): PdfPanel with pymupdf page rendering + navigation"
```

---

## Task 4: XlsxPanel — extracted table viewer (RED → GREEN)

**Files:**
- Create: `src/pdf2xlsx/gui/xlsx_panel.py`
- Test: `tests/test_gui.py` (append)

**Step 1: Add tests**

Append to `tests/test_gui.py`:

```python
def test_xlsx_panel_loads_tables(qtbot):
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    from pdf2xlsx.models import ExtractedTable
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    tables = [
        ExtractedTable(page=1, index=0, rows=[["A", "B"], ["1", "2"]], source="pdfplumber"),
        ExtractedTable(page=2, index=0, rows=[["X", "Y"], ["3", "4"]], source="pdfplumber"),
    ]
    panel.load_tables(tables)
    assert panel.tab_widget.count() == 2


def test_xlsx_panel_clear(qtbot):
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    from pdf2xlsx.models import ExtractedTable
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    panel.load_tables([
        ExtractedTable(page=1, index=0, rows=[["A"]], source="pdfplumber")
    ])
    panel.clear()
    assert panel.tab_widget.count() == 0


def test_xlsx_panel_cell_data(qtbot):
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    from pdf2xlsx.models import ExtractedTable
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    panel.load_tables([
        ExtractedTable(page=3, index=0, rows=[["Name", "Val"], ["Alice", "100"]], source="pdfplumber")
    ])
    tbl = panel.tab_widget.widget(0)
    assert tbl.item(0, 0).text() == "Name"
    assert tbl.item(1, 1).text() == "100"
```

**Step 2: Run RED**

```bash
uv run pytest tests/test_gui.py::test_xlsx_panel_loads_tables -v
```

Expected: FAIL with ImportError

**Step 3: Implement XlsxPanel**

`src/pdf2xlsx/gui/xlsx_panel.py`:

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont


class XlsxPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

    def load_tables(self, tables):
        self.tab_widget.clear()
        for t in tables:
            tbl = self._make_table(t.rows)
            self.tab_widget.addTab(tbl, t.sheet_name)

    def clear(self):
        self.tab_widget.clear()

    def _make_table(self, rows) -> QTableWidget:
        if not rows:
            return QTableWidget()
        n_rows = len(rows)
        n_cols = max(len(r) for r in rows)
        tbl = QTableWidget(n_rows, n_cols)
        tbl.setAlternatingRowColors(True)

        # Style header row
        header_font = QFont()
        header_font.setBold(True)
        header_bg = QColor("#1f4e79")
        header_fg = QColor("white")

        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                item = QTableWidgetItem(str(cell) if cell else "")
                if r == 0:
                    item.setBackground(header_bg)
                    item.setForeground(header_fg)
                    item.setFont(header_font)
                tbl.setItem(r, c, item)

        tbl.horizontalHeader().hide()
        tbl.verticalHeader().hide()
        tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        tbl.resizeColumnsToContents()
        return tbl
```

**Step 4: Run GREEN**

```bash
uv run pytest tests/test_gui.py -v
```

Expected: all pass.

**Step 5: Commit**

```bash
git add src/pdf2xlsx/gui/xlsx_panel.py tests/test_gui.py
git commit -m "feat(GREEN): XlsxPanel with QTabWidget table previews"
```

---

## Task 5: App entry point + __main__ (RED → GREEN)

**Files:**
- Create: `src/pdf2xlsx/gui/app.py`
- Create: `src/pdf2xlsx/__main__.py`
- Test: `tests/test_gui.py` (append)

**Step 1: Add test**

```python
def test_app_module_importable():
    from pdf2xlsx.gui import app
    assert hasattr(app, "main")
```

**Step 2: Create app.py**

`src/pdf2xlsx/gui/app.py`:

```python
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from pdf2xlsx.gui.main_window import MainWindow


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("pdf2xlsx")
    app.setApplicationVersion("0.1.0")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

`src/pdf2xlsx/__main__.py`:

```python
from pdf2xlsx.gui.app import main
main()
```

**Step 3: Run GREEN**

```bash
uv run pytest tests/test_gui.py -v
```

**Step 4: Commit**

```bash
git add src/pdf2xlsx/gui/app.py src/pdf2xlsx/__main__.py tests/test_gui.py
git commit -m "feat(GREEN): app entry point, pdf2xlsx-gui script"
```

---

## Task 6: Integration — open PDF then convert end-to-end (RED → GREEN)

**Files:**
- Test: `tests/test_gui_integration.py`

**Step 1: Write integration test**

`tests/test_gui_integration.py`:

```python
"""End-to-end GUI integration tests using real fixture PDFs."""
import pytest
import shutil
from pathlib import Path
from PySide6.QtCore import Qt

FIXTURES = Path("tests/fixtures")


@pytest.fixture
def term_sheet_path(tmp_path):
    dst = tmp_path / "term_sheet.pdf"
    shutil.copy(FIXTURES / "term_sheet.pdf", dst)
    return str(dst)


def test_load_pdf_enables_convert(qtbot, term_sheet_path):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert not win.btn_convert.isEnabled()
    win.pdf_panel.load_pdf(term_sheet_path)
    win._pdf_path = term_sheet_path
    win.btn_convert.setEnabled(True)
    assert win.btn_convert.isEnabled()


def test_convert_populates_xlsx_panel(qtbot, term_sheet_path):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    win._pdf_path = term_sheet_path
    win._on_convert()
    assert win.xlsx_panel.tab_widget.count() > 0


def test_convert_enables_save(qtbot, term_sheet_path):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    win._pdf_path = term_sheet_path
    win._on_convert()
    assert win.btn_save.isEnabled()


def test_save_writes_file(qtbot, term_sheet_path, tmp_path):
    from pdf2xlsx.gui.main_window import MainWindow
    from unittest.mock import patch
    win = MainWindow()
    qtbot.addWidget(win)
    win._pdf_path = term_sheet_path
    win._on_convert()
    out_path = str(tmp_path / "out.xlsx")
    with patch(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        return_value=(out_path, "Excel Files (*.xlsx)")
    ):
        win._on_save()
    assert Path(out_path).exists()
    assert Path(out_path).stat().st_size > 0
```

**Step 2: Run RED (should fail only if GUI not built yet)**

```bash
uv run pytest tests/test_gui_integration.py -v
```

**Step 3: Run GREEN (should pass after Tasks 2-5)**

Expected: all pass.

**Step 4: Commit**

```bash
git add tests/test_gui_integration.py
git commit -m "test(GREEN): end-to-end GUI integration with term_sheet fixture"
```

---

## Task 7: PyInstaller spec file

**Files:**
- Create: `pdf2xlsx.spec`
- Create: `packaging/build.py`

**Step 1: Create PyInstaller spec**

`pdf2xlsx.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['src/pdf2xlsx/gui/app.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'pdf2xlsx.extractor',
        'pdf2xlsx.postprocess',
        'pdf2xlsx.writer',
        'pdf2xlsx.models',
        'pdfplumber',
        'pymupdf',
        'openpyxl',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='pdf2xlsx',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI app — no console window
    icon=None,      # add assets/icon.ico when available
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='pdf2xlsx',
)

# macOS: create .app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='pdf2xlsx.app',
        bundle_identifier='com.securityronin.pdf2xlsx',
        info_plist={
            'NSPrincipalClass': 'NSApplication',
            'NSHighResolutionCapable': True,
            'CFBundleVersion': '0.1.0',
            'CFBundleShortVersionString': '0.1.0',
        },
    )
```

**Step 2: Add PyInstaller to dev deps**

In `pyproject.toml` dev group, add `"pyinstaller>=6.0"`.

Run `uv sync --group dev`.

**Step 3: Test build locally**

```bash
uv run pyinstaller pdf2xlsx.spec --clean
```

Expected: `dist/pdf2xlsx/` directory created with executable.

**Step 4: Commit**

```bash
git add pdf2xlsx.spec pyproject.toml
git commit -m "chore: add PyInstaller spec for cross-platform bundling"
```

---

## Task 8: WiX MSI config (Windows)

**Files:**
- Create: `wix/main.wxs`
- Create: `wix/License.rtf`

**Step 1: Create WiX manifest**

`wix/main.wxs`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="*"
           Name="pdf2xlsx"
           Language="1033"
           Version="0.1.0"
           Manufacturer="Security Ronin"
           UpgradeCode="A1B2C3D4-E5F6-7890-ABCD-EF1234567890">

    <Package InstallerVersion="200" Compressed="yes" InstallScope="perMachine"/>

    <MajorUpgrade DowngradeErrorMessage="A newer version is already installed."/>
    <MediaTemplate EmbedCab="yes"/>

    <Feature Id="ProductFeature" Title="pdf2xlsx" Level="1">
      <ComponentGroupRef Id="ProductComponents"/>
    </Feature>

    <Directory Id="TARGETDIR" Name="SourceDir">
      <Directory Id="ProgramFiles64Folder">
        <Directory Id="INSTALLDIR" Name="pdf2xlsx">
          <Directory Id="BinDir" Name="bin"/>
        </Directory>
      </Directory>
    </Directory>

    <ComponentGroup Id="ProductComponents" Directory="BinDir">
      <Component Id="MainExecutable" Guid="*">
        <File Id="pdf2xlsxEXE"
              Source="dist\pdf2xlsx\pdf2xlsx.exe"
              KeyPath="yes"/>
      </Component>
    </ComponentGroup>

    <UIRef Id="WixUI_Minimal"/>
    <WixVariable Id="WixUILicenseRtf" Value="wix\License.rtf"/>
  </Product>
</Wix>
```

`wix/License.rtf` — minimal RTF file with MIT license text (one line):

```
{\rtf1\ansi MIT License — Copyright (c) 2024 Security Ronin}
```

**Step 2: Commit**

```bash
git add wix/
git commit -m "chore: add WiX MSI config for Windows installer"
```

---

## Task 9: Debian packaging script

**Files:**
- Create: `packaging/build-deb.sh`

**Step 1: Create fpm-based deb build script**

`packaging/build-deb.sh`:

```bash
#!/usr/bin/env bash
# Requires: fpm (gem install fpm), PyInstaller dist already built
set -euo pipefail

VERSION="${VERSION:-0.1.0}"
ARCH="${ARCH:-amd64}"
DIST_DIR="dist/pdf2xlsx"
STAGE_DIR="$(mktemp -d)"

# Install binary
mkdir -p "${STAGE_DIR}/usr/bin"
cp "${DIST_DIR}/pdf2xlsx" "${STAGE_DIR}/usr/bin/pdf2xlsx"
chmod 755 "${STAGE_DIR}/usr/bin/pdf2xlsx"

# Build .deb
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

rm -rf "${STAGE_DIR}"
echo "Built: pdf2xlsx_${VERSION}_${ARCH}.deb"
```

**Step 2: Commit**

```bash
chmod +x packaging/build-deb.sh
git add packaging/build-deb.sh
git commit -m "chore: add fpm .deb build script"
```

---

## Task 10: Homebrew formula template

**Files:**
- Create: `packaging/homebrew-formula.rb`

**Step 1: Create formula**

`packaging/homebrew-formula.rb`:

```ruby
class Pdf2xlsx < Formula
  desc "PDF to XLSX table extractor with GUI and CLI"
  homepage "https://github.com/h4x0r/pdf2xlsx"
  version "0.1.0"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/h4x0r/pdf2xlsx/releases/download/v#{version}/pdf2xlsx-#{version}-aarch64-apple-darwin.tar.gz"
      sha256 "PLACEHOLDER_ARM64"
    else
      url "https://github.com/h4x0r/pdf2xlsx/releases/download/v#{version}/pdf2xlsx-#{version}-x86_64-apple-darwin.tar.gz"
      sha256 "PLACEHOLDER_X86_64"
    end
  end

  on_linux do
    url "https://github.com/h4x0r/pdf2xlsx/releases/download/v#{version}/pdf2xlsx-#{version}-x86_64-unknown-linux-musl.tar.gz"
    sha256 "PLACEHOLDER_LINUX"
  end

  def install
    bin.install "pdf2xlsx"
    bin.install "pdf2xlsx-gui" if File.exist?("pdf2xlsx-gui")
  end

  test do
    system "#{bin}/pdf2xlsx", "--help"
  end
end
```

**Step 2: Commit**

```bash
git add packaging/homebrew-formula.rb
git commit -m "chore: add Homebrew formula template"
```

---

## Task 11: GitHub Actions release workflow

**Files:**
- Create: `.github/workflows/release.yml`

**Step 1: Create release workflow**

`.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  build:
    name: Build ${{ matrix.target }}
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        include:
          - target: aarch64-apple-darwin
            os: macos-14          # Apple Silicon runner
            artifact: pdf2xlsx-aarch64-apple-darwin.tar.gz

          - target: x86_64-apple-darwin
            os: macos-15
            artifact: pdf2xlsx-x86_64-apple-darwin.tar.gz

          - target: x86_64-unknown-linux-musl
            os: ubuntu-24.04
            artifact: pdf2xlsx-x86_64-unknown-linux-musl.tar.gz

          - target: x86_64-pc-windows-msvc
            os: windows-latest
            artifact: pdf2xlsx-x86_64-windows.msi

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install dependencies
        run: uv sync --group dev

      - name: Install Qt platform deps (Linux)
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update -qq
          sudo apt-get install -y --no-install-recommends \
            libgl1 libglib2.0-0 libdbus-1-3 libegl1 \
            libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
            libxcb-randr0 libxcb-render-util0 libxcb-shape0 \
            libxcb-xinerama0 libxcb-xkb1 libxkbcommon-x11-0

      - name: Build with PyInstaller
        run: uv run pyinstaller pdf2xlsx.spec --clean

      - name: Package (Unix)
        if: runner.os != 'Windows'
        run: |
          VERSION="${{ github.ref_name }}"
          tar czf "${{ matrix.artifact }}" -C dist pdf2xlsx

      - name: Build MSI (Windows)
        if: runner.os == 'Windows'
        shell: pwsh
        run: |
          choco install wixtoolset -y
          & 'C:\Program Files (x86)\WiX Toolset v3.11\bin\candle.exe' wix\main.wxs -out wix\main.wixobj
          & 'C:\Program Files (x86)\WiX Toolset v3.11\bin\light.exe' wix\main.wixobj -ext WixUIExtension -out "${{ matrix.artifact }}"

      - uses: actions/upload-artifact@v4
        with:
          name: ${{ matrix.artifact }}
          path: ${{ matrix.artifact }}

  release:
    name: Create GitHub Release
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/download-artifact@v4
        with:
          path: artifacts/
          merge-multiple: true

      - name: Generate checksums
        run: |
          cd artifacts
          sha256sum * > SHA256SUMS.txt

      - name: Publish release
        uses: softprops/action-gh-release@v2
        with:
          files: |
            artifacts/*
          generate_release_notes: true

      - name: Dispatch Homebrew tap update
        uses: peter-evans/repository-dispatch@v3
        with:
          token: ${{ secrets.TAP_GITHUB_TOKEN }}
          repository: h4x0r/homebrew-pdf2xlsx
          event-type: new-release
          client-payload: |
            {
              "version": "${{ github.ref_name }}",
              "arm64_sha": "$(sha256sum artifacts/pdf2xlsx-aarch64-apple-darwin.tar.gz | cut -d' ' -f1)",
              "x86_64_sha": "$(sha256sum artifacts/pdf2xlsx-x86_64-apple-darwin.tar.gz | cut -d' ' -f1)"
            }

  deb:
    name: Build .deb
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install dependencies + Qt deps
        run: |
          uv sync --group dev
          sudo apt-get update -qq
          sudo apt-get install -y --no-install-recommends libgl1 libglib2.0-0 ruby ruby-dev
          sudo gem install fpm

      - name: Build binary
        run: uv run pyinstaller pdf2xlsx.spec --clean

      - name: Build .deb
        run: |
          VERSION="${{ github.ref_name }}" bash packaging/build-deb.sh

      - uses: actions/upload-artifact@v4
        with:
          name: pdf2xlsx-deb
          path: "*.deb"

  release-deb:
    name: Attach .deb to release
    needs: [release, deb]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: pdf2xlsx-deb

      - name: Upload .deb to release
        uses: softprops/action-gh-release@v2
        with:
          files: "*.deb"
```

**Step 2: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "chore: GitHub Actions release workflow — macOS/Linux/Windows + .deb"
```

---

## Task 12: CI workflow for tests

**Files:**
- Create: `.github/workflows/ci.yml`

**Step 1: Create CI workflow**

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    name: Tests (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install deps
        run: uv sync --group dev

      - name: Install Qt platform deps (Linux)
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update -qq
          sudo apt-get install -y --no-install-recommends \
            libgl1 libglib2.0-0 libdbus-1-3 libegl1 \
            libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
            libxcb-randr0 libxcb-render-util0 libxcb-shape0 \
            libxcb-xinerama0 libxcb-xkb1 libxkbcommon-x11-0 \
            xvfb

      - name: Run tests (Linux — headless)
        if: runner.os == 'Linux'
        run: xvfb-run uv run pytest tests/ -v --tb=short

      - name: Run tests
        if: runner.os != 'Linux'
        run: uv run pytest tests/ -v --tb=short
```

**Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "chore: CI workflow — test on macOS, Linux, Windows"
```

---

## Execution Order Summary

1. Task 1 → add deps, install
2. Task 2 → MainWindow (blocked by PdfPanel/XlsxPanel stubs — create empty classes first)
3. Task 3 → PdfPanel
4. Task 4 → XlsxPanel
5. Task 5 → App entry
6. Task 6 → Integration test
7. Task 7 → PyInstaller spec
8. Task 8 → WiX MSI
9. Task 9 → .deb script
10. Task 10 → Homebrew formula
11. Task 11 → Release workflow
12. Task 12 → CI workflow

**Note on Task 2 stubs:** Before running Task 2 tests, create minimal stub files:

`src/pdf2xlsx/gui/pdf_panel.py` (stub):
```python
from PySide6.QtWidgets import QWidget
class PdfPanel(QWidget):
    def load_pdf(self, path): pass
```

`src/pdf2xlsx/gui/xlsx_panel.py` (stub):
```python
from PySide6.QtWidgets import QWidget
class XlsxPanel(QWidget):
    def load_tables(self, tables): pass
    def clear(self): pass
```
