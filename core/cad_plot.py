"""Печать листа: DXF → DWG + PDF через AutoCAD (COM, «DWG To PDF.pc3», А3, 1:1), запасной предпросмотр ezdxf.

Предпросмотр нужен только для быстрых итераций генератора; в комплект идёт PDF из AutoCAD.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext, layout, pymupdf as dpm
from ezdxf.addons.drawing.config import Configuration, ColorPolicy, BackgroundPolicy

PLOT_PS1 = r"""
param([string]$Dxf, [string]$Dwg, [string]$Pdf)
$ErrorActionPreference = 'Stop'
$acad = $null
try { $acad = [Runtime.InteropServices.Marshal]::GetActiveObject('AutoCAD.Application') } catch { }
$own = $false
if (-not $acad) { $acad = New-Object -ComObject 'AutoCAD.Application'; $own = $true }
for ($k = 0; $k -lt 120; $k++) { try { $null = $acad.Documents.Count; break } catch { Start-Sleep -Seconds 1 } }
try { $acad.Visible = $false } catch { }
function Retry([scriptblock]$Action) {
  for ($k = 0; $k -lt 60; $k++) {
    try { return & $Action } catch [System.Runtime.InteropServices.COMException] {
      if ($_.Exception.HResult -ne -2147418111 -and $_.Exception.HResult -ne -2147417846) { throw }
      Start-Sleep -Milliseconds 1000
    }
  }
  throw 'AutoCAD не отвечает (занят)'
}
$doc = $null
for ($i = 0; $i -lt 30 -and -not $doc; $i++) { try { $doc = $acad.Documents.Open($Dxf, $false) } catch { Start-Sleep -Seconds 2 } }
if (-not $doc) { throw "AutoCAD не открыл $Dxf" }
try {
  Retry { $doc.SetVariable('BACKGROUNDPLOT', [int16]0) }
  Retry { $doc.SetVariable('FILEDIA', [int16]0) }
  if (Test-Path $Dwg) { Remove-Item $Dwg -Force }
  if (Test-Path $Pdf) { Remove-Item $Pdf -Force }
  Retry { $doc.SaveAs($Dwg) }
  $lay = Retry { $doc.ModelSpace.Layout }
  Retry { $doc.ActiveLayout = $lay }
  Retry { $lay.ConfigName = 'DWG To PDF.pc3' }
  Retry { $lay.RefreshPlotDeviceInfo() }
  $media = @(Retry { $lay.GetCanonicalMediaNames() })
  $a3 = $media | Where-Object { $_ -match 'ISO_full_bleed_A3_\(420' } | Select-Object -First 1
  if (-not $a3) { $a3 = $media | Where-Object { $_ -match 'A3.*420' } | Select-Object -First 1 }
  $lay.CanonicalMediaName = $a3
  $lay.PaperUnits = 1
  $lay.PlotRotation = 0
  $lay.PlotType = 1
  $lay.UseStandardScale = $true
  $lay.StandardScale = 16
  $lay.CenterPlot = $true
  $lay.PlotWithLineweights = $true
  try { $lay.StyleSheet = 'monochrome.ctb'; $lay.PlotWithPlotStyles = $true } catch { }
  Retry { $doc.Regen(1) }
  $ok = Retry { $doc.Plot.PlotToFile($Pdf, 'DWG To PDF.pc3') }
  if (-not $ok -or -not (Test-Path $Pdf)) { throw "Печать $Pdf не выполнена" }
  Retry { $doc.Save() }
} finally {
  try { $doc.Close($false) } catch { }
  if ($own) { try { $acad.Quit() } catch { } }
}
"""


def preview_pdf(dxf: Path, pdf: Path) -> Path:
    doc = ezdxf.readfile(str(dxf))
    msp = doc.modelspace()
    cfg = Configuration(color_policy=ColorPolicy.BLACK, background_policy=BackgroundPolicy.WHITE,
                        min_lineweight=0.13)
    backend = dpm.PyMuPdfBackend()
    Frontend(RenderContext(doc), backend, config=cfg).draw_layout(msp)
    page = layout.Page(420, 297, layout.Units.mm, margins=layout.Margins.all(0))
    settings = layout.Settings(scale=1, fit_page=False)
    pdf.write_bytes(backend.get_pdf_bytes(page, settings=settings))
    return pdf


def preview_png(dxf: Path, png: Path, dpi: int = 110) -> Path:
    doc = ezdxf.readfile(str(dxf))
    cfg = Configuration(color_policy=ColorPolicy.BLACK, background_policy=BackgroundPolicy.WHITE)
    backend = dpm.PyMuPdfBackend()
    Frontend(RenderContext(doc), backend, config=cfg).draw_layout(doc.modelspace())
    page = layout.Page(420, 297, layout.Units.mm, margins=layout.Margins.all(0))
    png.write_bytes(backend.get_pixmap_bytes(page, fmt="png", dpi=dpi, settings=layout.Settings(scale=1, fit_page=False)))
    return png


def autocad_plot(dxf: Path, dwg: Path, pdf: Path, timeout: int = 300) -> None:
    script = dxf.parent / "_plot.ps1"
    script.write_text(PLOT_PS1, encoding="utf-8-sig")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                        "-Dxf", str(dxf), "-Dwg", str(dwg), "-Pdf", str(pdf)],
                       capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    script.unlink(missing_ok=True)
    if r.returncode != 0 or not pdf.is_file():
        raise RuntimeError(f"AutoCAD: печать {dxf.name} не выполнена: {r.stderr.strip()[-600:]}")
