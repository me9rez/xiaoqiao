#!/usr/bin/env pwsh
#requires -Version 7.0
<#
.SYNOPSIS
    构建包含 web 前端资源的 xiaoqiao wheel 包。

.DESCRIPTION
    - 构建 web 前端（pnpm install + pnpm build）
    - 构建 Python wheel/sdist（uv build）
    - 验证 wheel 中是否包含 web_dist/index.html
    - 使用 -Publish 开关可发布到 PyPI

.EXAMPLE
    .\scripts\build-package.ps1
    .\scripts\build-package.ps1 -Publish
#>
[CmdletBinding()]
param(
    [switch]$Publish
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$webDir = Join-Path $repoRoot "web"
$pythonDir = Join-Path $repoRoot "python"

function Assert-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "需要 $Name，但在 PATH 中未找到"
    }
}

function Invoke-Step($Message, [scriptblock]$Action) {
    Write-Host "==> $Message" -ForegroundColor Cyan
    & $Action
}

# --- prerequisites ---
Assert-Command "pnpm"
Assert-Command "uv"

# --- build web frontend ---
Invoke-Step "安装 web 依赖" {
    Push-Location $webDir
    try {
        pnpm install
    } finally {
        Pop-Location
    }
}

Invoke-Step "构建 web 前端" {
    Push-Location $webDir
    try {
        pnpm build
    } finally {
        Pop-Location
    }
}

$webDist = Join-Path $webDir "dist"
if (-not (Test-Path (Join-Path $webDist "index.html"))) {
    throw "未找到 web/dist/index.html，前端构建失败"
}

# --- stage web assets into python package ---
$bundleDir = Join-Path $pythonDir "src" "xiaoqiao" "web_dist"
if (Test-Path $bundleDir) {
    Invoke-Step "清理已打包的 web 资源" {
        Remove-Item -Recurse -Force $bundleDir
    }
}
Invoke-Step "将 web 资源复制到 Python 包" {
    Copy-Item -Path $webDist -Destination $bundleDir -Recurse -Force
}

try {
    # --- clean old python dist ---
    $pythonDist = Join-Path $pythonDir "dist"
    if (Test-Path $pythonDist) {
        Invoke-Step "清理旧的 python/dist" {
            Remove-Item -Recurse -Force $pythonDist
        }
    }

    # --- build python wheel ---
    Invoke-Step "构建 Python wheel" {
        Push-Location $pythonDir
        try {
            uv build
        } finally {
            Pop-Location
        }
    }

    # --- verify wheel contents ---
    $wheel = Get-ChildItem -Path $pythonDist -Filter "xiaoqiao-*.whl" | Select-Object -First 1
    if (-not $wheel) {
        throw "在 $pythonDist 中未找到 wheel"
    }

    Invoke-Step "校验 wheel 内容" {
        $entries = uv run --project $pythonDir python -m zipfile -l $wheel.FullName | Select-String "xiaoqiao/web_dist/index.html"
        if (-not $entries) {
            throw "在 $($wheel.FullName) 中未找到打包的 web 资源"
        }
        Write-Host "已找到打包资源: $($entries.Line.Trim())" -ForegroundColor Green
    }

    Write-Host "`n构建完成: $($wheel.FullName)" -ForegroundColor Green

    # --- publish ---
    if ($Publish) {
        Invoke-Step "发布到 PyPI" {
            Push-Location $pythonDir
            try {
                uv publish dist/*
            } finally {
                Pop-Location
            }
        }
    }
} finally {
    Invoke-Step "清理临时 web 资源" {
        if (Test-Path $bundleDir) {
            Remove-Item -Recurse -Force $bundleDir
        }
    }
}
