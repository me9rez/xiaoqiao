#!/usr/bin/env pwsh
#requires -Version 7.0
<#
.SYNOPSIS
    构建桌面版：独立 Python 运行时 + 前端资源 + tinyjs 打包。

.DESCRIPTION
    1. 用 uv 下载 python-build-standalone，摊平到 desktop/resources/python
    2. 构建 wheel 并装进这个运行时（不污染系统 Python）
    3. 构建 web 前端并执行 tinyjs build，产出 desktop/dist

    运行时目录很大（~130 MB），已加入 .gitignore。

.PARAMETER PythonVersion
    运行时版本，默认 3.14（与 pyproject 的 requires-python 一致）。

.PARAMETER SkipRuntime
    复用已有的 desktop/resources/python，只重建前端与应用。

.EXAMPLE
    .\scripts\build-desktop.ps1
    .\scripts\build-desktop.ps1 -SkipRuntime
#>
[CmdletBinding()]
param(
    [string]$PythonVersion = "3.14",
    [switch]$SkipRuntime
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$desktopDir = Join-Path $repoRoot "desktop"
$pythonDir = Join-Path $repoRoot "python"
$runtimeDir = Join-Path $desktopDir "resources\python"

function Assert-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "需要 $Name，但在 PATH 中未找到"
    }
}

function Invoke-Step($Message, [scriptblock]$Action) {
    Write-Host "==> $Message" -ForegroundColor Cyan
    & $Action
}

Assert-Command "uv"
Assert-Command "pnpm"
Assert-Command "tinyjs"

if (-not $SkipRuntime) {
    Invoke-Step "下载独立 Python $PythonVersion" {
        $staging = Join-Path $env:TEMP "xiaoqiao-runtime"
        Remove-Item -Recurse -Force $staging -ErrorAction SilentlyContinue
        uv python install -i $staging $PythonVersion --no-registry

        # uv 装到 cpython-<version>-windows-... 子目录，摊平成固定路径
        $dist = Get-ChildItem $staging -Directory |
            Where-Object { $_.Name -like "cpython-*.*-windows*" } |
            Select-Object -First 1
        if (-not $dist) { throw "在 $staging 找不到 CPython 目录" }

        Remove-Item -Recurse -Force $runtimeDir -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Force $runtimeDir | Out-Null
        Copy-Item (Join-Path $dist.FullName "*") $runtimeDir -Recurse -Force
        Remove-Item -Recurse -Force $staging -ErrorAction SilentlyContinue
    }

    Invoke-Step "安装 小巧 到运行时" {
        # uv 给独立解释器打上 PEP 668 标记；这个运行时归应用所有，去掉它。
        $marker = Join-Path $runtimeDir "Lib\EXTERNALLY-MANAGED"
        if (Test-Path $marker) { Remove-Item $marker -Force }

        Push-Location $pythonDir
        try {
            uv build | Out-Host
            $wheel = Get-ChildItem "dist\xiaoqiao-*.whl" |
                Sort-Object LastWriteTime |
                Select-Object -Last 1
            if (-not $wheel) { throw "wheel 构建失败" }
            uv pip install --python (Join-Path $runtimeDir "python.exe") $wheel.FullName | Out-Host
        }
        finally {
            Pop-Location
        }

        & (Join-Path $runtimeDir "python.exe") -c "import xiaoqiao.main; print('runtime ok')"
    }
}
elseif (-not (Test-Path (Join-Path $runtimeDir "python.exe"))) {
    throw "没有现成的运行时，去掉 -SkipRuntime 重跑"
}

Invoke-Step "构建前端 + 打包桌面应用" {
    Push-Location $desktopDir
    try {
        tinyjs build | Out-Host
    }
    finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "完成：$desktopDir\dist\" -ForegroundColor Green
