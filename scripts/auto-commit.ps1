param(
  [Alias('m')]
  [string]$Message = '',
  [string]$Type = 'chore',
  [string]$Scope = ''
)

$ErrorActionPreference = 'Stop'

# 参数说明：
# -Message/-m：显式提交信息，优先级最高
# -Type：默认提交类型，用于自动生成提交信息
# -Scope：可选范围，参与默认提交信息拼接
# 默认提交信息策略：{Type}{(Scope)}: 自动提交 YYYY-MM-DD HH:mm
# 无改动时行为：输出提示并以 0 退出

# 切换到仓库根目录（脚本所在目录的上一级）
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# 确认当前目录为 Git 仓库根目录
$gitDir = Join-Path $root '.git'
if (-not (Test-Path $gitDir)) {
  throw '未找到 .git，当前目录不是 Git 仓库根目录'
}

# 检查是否有改动
$status = git status --porcelain
if (-not $status) {
  Write-Host '无改动，跳过提交。'
  exit 0
}

# 暂存所有改动
git add -A
if ($LASTEXITCODE -ne 0) {
  throw 'git add 失败'
}

# 生成提交信息（Angular 规范）
$finalMessage = $Message.Trim()
if (-not $finalMessage) {
  $safeType = $Type.Trim()
  if (-not $safeType) {
    $safeType = 'chore'
  }

  $safeScope = $Scope.Trim()
  $scopePart = ''
  if ($safeScope) {
    $scopePart = "($safeScope)"
  }

  $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm'
  $finalMessage = "$safeType$scopePart: 自动提交 $timestamp"
}

git commit -m $finalMessage
if ($LASTEXITCODE -ne 0) {
  throw 'git commit 失败'
}

Write-Host "提交完成：$finalMessage"
