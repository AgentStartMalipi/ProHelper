# Genera los fixtures de Office con Word/PowerPoint/Excel reales (COM).
# Se corre una vez; los archivos quedan versionados en speak/tests/fixtures.
#   powershell -ExecutionPolicy Bypass -File speak\tests\fixtures\make_office.ps1
$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

# --- Word: encabezado, vinetas, tabla, cuadro de texto, pie de pagina --------
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$doc = $word.Documents.Add()
$doc.Sections(1).Headers(1).Range.Text = "Ecoeffy - Propuesta confidencial"
$doc.Sections(1).Footers(1).Range.Text = "Pagina de pie: contacto ventas@ecoeffy.test"
$sel = $word.Selection
$sel.Style = $doc.Styles.Item(-2)  # Titulo 1
$sel.TypeText("Propuesta de auditoría energética para Acme")
$sel.TypeParagraph()
$sel.Style = $doc.Styles.Item(-1)  # Normal
$sel.TypeText("La auditoría cubre el sistema de vapor de tres plantas. El ahorro esperado es de 8 a 15 por ciento.")
$sel.TypeParagraph()
$sel.Range.ListFormat.ApplyBulletDefault()
$sel.TypeText("Levantamiento de trampas de vapor")
$sel.TypeParagraph()
$sel.TypeText("Medición de consumo por línea")
$sel.TypeParagraph()
$sel.Range.ListFormat.RemoveNumbers()
$sel.TypeText("Tabla de precios:")
$sel.TypeParagraph()
$table = $doc.Tables.Add($sel.Range, 3, 3)
$vals = @(@("Planta", "Precio USD", "Plazo"), @("Bogotá", "12.000", "8 semanas"), @("Medellín", "10.500", "6 semanas"))
for ($r = 1; $r -le 3; $r++) { for ($c = 1; $c -le 3; $c++) { $table.Cell($r, $c).Range.Text = $vals[$r - 1][$c - 1] } }
$sel.EndKey(6) | Out-Null
$sel.TypeParagraph()
$sel.TypeText("Garantía: si el ahorro medido es menor a 5 por ciento, devolvemos el 50 por ciento del valor.")
$box = $doc.Shapes.AddTextbox(1, 100, 500, 300, 60)
$box.TextFrame.TextRange.Text = "Nota destacada: anticipo del 30 por ciento"
$doc.SaveAs([ref](Join-Path $dir "propuesta_acme.docx"), [ref]16)
$doc.Close()
$word.Quit()

# --- PowerPoint: titulo, vinetas, tabla, grupo de formas, notas --------------
$ppt = New-Object -ComObject PowerPoint.Application
$pres = $ppt.Presentations.Add(0)
$s1 = $pres.Slides.Add(1, 1)  # ppLayoutTitle
$s1.Shapes.Item(1).TextFrame.TextRange.Text = "Caso de éxito Cementos X"
$s1.Shapes.Item(2).TextFrame.TextRange.Text = "Ahorro de 11 por ciento en vapor"
$s1.NotesPage.Shapes.Placeholders.Item(2).TextFrame.TextRange.Text = "Nota del orador: el cliente pidió no mencionar el nombre de la planta."
$s2 = $pres.Slides.Add(2, 12)  # ppLayoutBlank
$t = $s2.Shapes.AddTable(2, 2, 50, 50, 400, 100)
$t.Table.Cell(1, 1).Shape.TextFrame.TextRange.Text = "Indicador"
$t.Table.Cell(1, 2).Shape.TextFrame.TextRange.Text = "Resultado"
$t.Table.Cell(2, 1).Shape.TextFrame.TextRange.Text = "Retorno"
$t.Table.Cell(2, 2).Shape.TextFrame.TextRange.Text = "14 meses"
$a = $s2.Shapes.AddShape(1, 50, 250, 150, 50); $a.TextFrame.TextRange.Text = "Caldera"
$b = $s2.Shapes.AddShape(1, 300, 250, 150, 50); $b.TextFrame.TextRange.Text = "Red de vapor"
$s2.Shapes.Range([object[]]@($a.Name, $b.Name)).Group() | Out-Null
for ($i = 3; $i -le 11; $i++) {
    $s = $pres.Slides.Add($i, 12)
    $tb = $s.Shapes.AddTextbox(1, 50, 50, 400, 50)
    $tb.TextFrame.TextRange.Text = "Diapositiva de relleno $i"
}
$pres.SaveAs((Join-Path $dir "caso_cementos.pptx"), 24)
$pres.Close()
$ppt.Quit()

# --- Excel: lista de precios con dos hojas, numeros y formulas ---------------
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false
$xl.DisplayAlerts = $false
$wb = $xl.Workbooks.Add()
$ws = $wb.Worksheets.Item(1)
$ws.Name = "Precios"
$ws.Cells.Item(1, 1) = "Servicio"; $ws.Cells.Item(1, 2) = "Precio USD"; $ws.Cells.Item(1, 3) = "Unidad"
$ws.Cells.Item(2, 1) = "Auditoría de vapor"; $ws.Cells.Item(2, 2) = 12000; $ws.Cells.Item(2, 3) = "planta"
$ws.Cells.Item(3, 1) = "Monitoreo IoT"; $ws.Cells.Item(3, 2) = 450; $ws.Cells.Item(3, 3) = "mes"
$ws.Cells.Item(4, 1) = "Total ejemplo"; $ws.Cells.Item(4, 2).Formula = "=B2+B3"
$ws2 = $wb.Worksheets.Add([Type]::Missing, $ws)
$ws2.Name = "Descuentos"
$ws2.Cells.Item(1, 1) = "Volumen"; $ws2.Cells.Item(1, 2) = "Descuento"
$ws2.Cells.Item(2, 1) = "3 plantas o más"; $ws2.Cells.Item(2, 2) = "7%"
$wb.SaveAs((Join-Path $dir "precios.xlsx"), 51)
$wb.Close()
$xl.Quit()
"ok"
