# Loads the TMDL model with Power BI Desktop's own parser (Windows with Desktop installed).
# Usage: powershell -ExecutionPolicy Bypass -File scripts/validate_tmdl.ps1
$bin = "C:\Program Files\Microsoft Power BI Desktop\bin"
$script:loading = @{}
[AppDomain]::CurrentDomain.add_AssemblyResolve({
    param($s, $e)
    $n = ($e.Name -split ',')[0]
    if ($script:loading[$n]) { return $null }
    $script:loading[$n] = $true
    $p = Join-Path $bin "$n.dll"
    if (Test-Path $p) { return [Reflection.Assembly]::LoadFrom($p) }
    return $null
})
$found = @()
foreach ($f in "Microsoft.AnalysisServices.Server.Tabular.dll", "Microsoft.PowerBI.Tabular.dll", "Microsoft.PowerBI.Amo.dll") {
    try {
        $a = [Reflection.Assembly]::LoadFrom((Join-Path $bin $f))
        try { $types = $a.GetTypes() } catch { $types = $_.Exception.Types | Where-Object { $_ } }
        foreach ($t in $types) { if ($t.Name -like "Tmdl*") { $found += $t } }
    } catch { "load error $f : " + $_.Exception.Message }
}
"Tmdl types: " + (($found | ForEach-Object { $_.FullName }) -join ", ")
$ser = $found | Where-Object { $_.Name -eq "TmdlSerializer" } | Select-Object -First 1
if (-not $ser) { "no TmdlSerializer"; exit }
$m = $ser.GetMethods() | Where-Object { $_.Name -eq "DeserializeDatabaseFromFolder" } | Select-Object -First 1
"method: " + $m
try {
    $db = $m.Invoke($null, @("C:\Users\Parsa\Documents\gridpulse-de\powerbi\GridPulse.SemanticModel\definition"))
    "LOADED database: " + $db.Name
    "tables: " + (($db.Model.Tables | ForEach-Object { $_.Name }) -join ", ")
    "measures: " + (($db.Model.Tables | ForEach-Object { $_.Measures.Count } | Measure-Object -Sum).Sum)
    "relationships: " + $db.Model.Relationships.Count
    "expressions: " + (($db.Model.Expressions | ForEach-Object { $_.Name }) -join ", ")
} catch {
    "ERROR: " + $_.Exception.GetBaseException().Message
}
