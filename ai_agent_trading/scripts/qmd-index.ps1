# One-time (or occasional) QMD index for this repo.
# Prerequisites: Node.js 22+; run `npm install` at repo root first (installs @tobilu/qmd).
# Run from anywhere:  pwsh -File scripts/qmd-index.ps1
# If collection "arb" already exists:  node .\node_modules\@tobilu\qmd\dist\cli\qmd.js collection remove arb

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

# Same DB path as Cursor MCP (.cursor/mcp.json env INDEX_PATH)
$QmdDir = Join-Path $Root ".qmd"
New-Item -ItemType Directory -Force -Path $QmdDir | Out-Null
$env:INDEX_PATH = Join-Path $QmdDir "index.sqlite"

$QmdCli = Join-Path $Root "node_modules\@tobilu\qmd\dist\cli\qmd.js"
if (-not (Test-Path -LiteralPath $QmdCli)) {
    Write-Error "Missing $QmdCli — run 'npm install' at repo root (see .cursor/skills/.../qmd-cursor-mcp.md)."
}

Write-Host "Repo root: $Root"
Write-Host "Adding collection 'arb' (py, yaml, yml, md only)..."

& node @($QmdCli, "collection", "add", ".", "--name", "arb", "--mask", "**/*.{py,yaml,yml,md}")

Write-Host "Adding collection context..."
& node @($QmdCli, "context", "add", "qmd://arb", "Upbit-Binance arbitrage: src/, configs/, tests/, skills. Python v2 multi_main.")

Write-Host "Embedding (chunk-strategy auto for code; first run downloads models)..."
& node @($QmdCli, "embed", "--chunk-strategy", "auto")

Write-Host "Done. In Cursor: Settings > MCP > enable project servers, or reload window."
Write-Host "Check: node $QmdCli status"
