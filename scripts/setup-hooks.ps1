param()

$ErrorActionPreference = 'Stop'

# 切换到仓库根目录
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# 启用项目内 hooks 目录
git config core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) {
  throw '设置 core.hooksPath 失败'
}

Write-Host '已启用 .githooks（提交信息将按 Angular 规范校验）。'
