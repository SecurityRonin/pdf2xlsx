from pathlib import Path
from typing import Optional
import typer
from rich.console import Console

from pdf2xlsx.extractor import extract_tables
from pdf2xlsx.writer import write_xlsx

app = typer.Typer(help="Extract tables from a PDF into an Excel workbook (.xlsx).")
console = Console()


@app.command()
def main(
    input_pdf: Path = typer.Argument(..., help="Path to the input PDF file"),
    output_xlsx: Optional[Path] = typer.Argument(
        None, help="Output .xlsx path (default: same directory as input PDF)"
    ),
) -> None:
    if not input_pdf.exists():
        console.print(f"[red]Error:[/red] File not found: {input_pdf}")
        raise typer.Exit(code=1)

    if output_xlsx is None:
        output_xlsx = input_pdf.with_suffix(".xlsx")

    console.print(f"Extracting tables from [cyan]{input_pdf.name}[/cyan] ...")
    tables = extract_tables(input_pdf)

    if not tables:
        console.print("[yellow]Warning:[/yellow] No tables found in this PDF.")
    else:
        console.print(f"Found [green]{len(tables)}[/green] table(s).")

    write_xlsx(tables, output_xlsx)
    console.print(f"Saved [green]{len(tables)}[/green] table(s) → [cyan]{output_xlsx}[/cyan]")
