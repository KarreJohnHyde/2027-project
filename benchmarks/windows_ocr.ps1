<#
.SYNOPSIS
  Reads images with the OCR engine built into Windows 10/11 (Windows.Media.Ocr) and prints
  one JSON object per image: {"path", "lines": [...], "seconds"}. Used only by
  benchmarks/ocr_benchmark.py to compare engines; nothing is sent off the machine.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File benchmarks/windows_ocr.ps1 a.png b.png
#>
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Paths)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object { $_.Name -eq "AsTask" -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } |
    Select-Object -First 1

function Await($operation, [Type]$resultType) {
    $task = $asTask.MakeGenericMethod($resultType).Invoke($null, @($operation))
    $task.Wait(-1) | Out-Null
    return $task.Result
}

[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) { throw "No Windows OCR language is installed for this user profile." }
foreach ($path in $Paths) {
    $started = [Diagnostics.Stopwatch]::StartNew()
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path $path).Path)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $stream.Dispose()
    $lines = @($result.Lines | ForEach-Object { $_.Text })
    # Word boxes let the caller group words into rows the same way for every engine.
    $words = @($result.Lines | ForEach-Object { $_.Words } | ForEach-Object {
        $box = $_.BoundingRect
        @{ text = $_.Text; box = @($box.X, $box.Y, ($box.X + $box.Width), ($box.Y + $box.Height)) }
    })
    [pscustomobject]@{ path = $path; lines = $lines; words = $words; seconds = $started.Elapsed.TotalSeconds; language = $engine.RecognizerLanguage.LanguageTag } |
        ConvertTo-Json -Compress -Depth 4
}
