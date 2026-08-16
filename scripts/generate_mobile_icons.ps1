param(
    [string]$SourcePath = ""
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$mobileRoot = Join-Path $workspaceRoot "mobile"
if (-not $SourcePath) {
    $SourcePath = Join-Path $mobileRoot "assets\icon\app_icon.png"
}

$resolvedMobileRoot = [System.IO.Path]::GetFullPath($mobileRoot)
$resolvedSource = [System.IO.Path]::GetFullPath($SourcePath)
if (-not (Test-Path -LiteralPath $resolvedSource -PathType Leaf)) {
    throw "App icon source does not exist: $resolvedSource"
}

$targets = @{
    "android\app\src\main\res\mipmap-mdpi\ic_launcher.png" = 48
    "android\app\src\main\res\mipmap-hdpi\ic_launcher.png" = 72
    "android\app\src\main\res\mipmap-xhdpi\ic_launcher.png" = 96
    "android\app\src\main\res\mipmap-xxhdpi\ic_launcher.png" = 144
    "android\app\src\main\res\mipmap-xxxhdpi\ic_launcher.png" = 192
    "ios\Runner\Assets.xcassets\AppIcon.appiconset\Icon-App-20x20@1x.png" = 20
    "ios\Runner\Assets.xcassets\AppIcon.appiconset\Icon-App-20x20@2x.png" = 40
    "ios\Runner\Assets.xcassets\AppIcon.appiconset\Icon-App-20x20@3x.png" = 60
    "ios\Runner\Assets.xcassets\AppIcon.appiconset\Icon-App-29x29@1x.png" = 29
    "ios\Runner\Assets.xcassets\AppIcon.appiconset\Icon-App-29x29@2x.png" = 58
    "ios\Runner\Assets.xcassets\AppIcon.appiconset\Icon-App-29x29@3x.png" = 87
    "ios\Runner\Assets.xcassets\AppIcon.appiconset\Icon-App-40x40@1x.png" = 40
    "ios\Runner\Assets.xcassets\AppIcon.appiconset\Icon-App-40x40@2x.png" = 80
    "ios\Runner\Assets.xcassets\AppIcon.appiconset\Icon-App-40x40@3x.png" = 120
    "ios\Runner\Assets.xcassets\AppIcon.appiconset\Icon-App-60x60@2x.png" = 120
    "ios\Runner\Assets.xcassets\AppIcon.appiconset\Icon-App-60x60@3x.png" = 180
    "ios\Runner\Assets.xcassets\AppIcon.appiconset\Icon-App-76x76@1x.png" = 76
    "ios\Runner\Assets.xcassets\AppIcon.appiconset\Icon-App-76x76@2x.png" = 152
    "ios\Runner\Assets.xcassets\AppIcon.appiconset\Icon-App-83.5x83.5@2x.png" = 167
    "ios\Runner\Assets.xcassets\AppIcon.appiconset\Icon-App-1024x1024@1x.png" = 1024
}

$source = [System.Drawing.Image]::FromFile($resolvedSource)
try {
    if ($source.Width -ne $source.Height) {
        throw "App icon source must be square; received $($source.Width)x$($source.Height)."
    }

    foreach ($relativePath in $targets.Keys) {
        $target = [System.IO.Path]::GetFullPath((Join-Path $mobileRoot $relativePath))
        if (-not $target.StartsWith($resolvedMobileRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to write an icon outside the mobile workspace: $target"
        }

        $size = $targets[$relativePath]
        $bitmap = New-Object System.Drawing.Bitmap(
            $size,
            $size,
            [System.Drawing.Imaging.PixelFormat]::Format24bppRgb
        )
        try {
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            try {
                $graphics.Clear([System.Drawing.ColorTranslator]::FromHtml("#08086B"))
                $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
                $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
                $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
                $graphics.DrawImage($source, 0, 0, $size, $size)
            }
            finally {
                $graphics.Dispose()
            }
            $bitmap.Save($target, [System.Drawing.Imaging.ImageFormat]::Png)
        }
        finally {
            $bitmap.Dispose()
        }
    }
}
finally {
    $source.Dispose()
}

Write-Output "Generated $($targets.Count) Android and iOS launcher icons from $resolvedSource"
