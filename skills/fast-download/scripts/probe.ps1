param(
  [ValidateSet('all', 'github', 'pip', 'npm', 'hf')]
  [string]$Type = 'all',
  [int]$LimitSec = 6
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Fmt = '%{http_code}|%{size_download}|%{time_starttransfer}|%{time_total}|%{speed_download}'

function Probe-Url {
  param([string]$Url, [int]$LimitSec)
  $raw = & curl.exe -o NUL -s -L --max-time $LimitSec --connect-timeout 5 --range 0-1048575 `
    -A 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) fast-download-probe/1.0' -w $Fmt $Url 2>$null
  if (-not $raw) {
    return [pscustomobject]@{ Code = 'ERR'; MB = 0; TTFB = 0; Sec = 0; MBps = 0 }
  }
  $p = $raw -split '\|'
  $bytes = [double]$p[1]
  $total = [double]$p[3]
  return [pscustomobject]@{
    Code = $p[0]
    MB   = [math]::Round($bytes / 1MB, 2)
    TTFB = [math]::Round([double]$p[2], 2)
    Sec  = [math]::Round($total, 2)
    MBps = if ($total -gt 0) { [math]::Round(($bytes / 1MB) / $total, 2) } else { 0 }
  }
}

$sets = @{
  github = @(
    @{ Name = 'gh-proxy.com'; Url = 'https://gh-proxy.com/https://github.com/neovim/neovim/releases/download/v0.10.2/nvim-win64.zip' }
    @{ Name = 'ghfast.top';   Url = 'https://ghfast.top/https://github.com/neovim/neovim/releases/download/v0.10.2/nvim-win64.zip' }
    @{ Name = 'official';     Url = 'https://github.com/neovim/neovim/releases/download/v0.10.2/nvim-win64.zip' }
  )
  pip = @(
    @{ Name = 'huawei';   Url = 'https://repo.huaweicloud.com/repository/pypi/packages/25/ca/1166b75c21abd1da445b97bf1fa2f14f423c6cfb4fc7c4ef31dccf9f6a94/numpy-2.1.3.tar.gz' }
    @{ Name = 'tencent';  Url = 'https://mirrors.cloud.tencent.com/pypi/packages/25/ca/1166b75c21abd1da445b97bf1fa2f14f423c6cfb4fc7c4ef31dccf9f6a94/numpy-2.1.3.tar.gz' }
    @{ Name = 'aliyun';   Url = 'https://mirrors.aliyun.com/pypi/packages/25/ca/1166b75c21abd1da445b97bf1fa2f14f423c6cfb4fc7c4ef31dccf9f6a94/numpy-2.1.3.tar.gz' }
    @{ Name = 'official'; Url = 'https://files.pythonhosted.org/packages/25/ca/1166b75c21abd1da445b97bf1fa2f14f423c6cfb4fc7c4ef31dccf9f6a94/numpy-2.1.3.tar.gz' }
  )
  npm = @(
    @{ Name = 'npmmirror'; Url = 'https://registry.npmmirror.com/typescript/-/typescript-5.6.3.tgz' }
    @{ Name = 'tencent';   Url = 'https://mirrors.cloud.tencent.com/npm/typescript/-/typescript-5.6.3.tgz' }
    @{ Name = 'official';  Url = 'https://registry.npmjs.org/typescript/-/typescript-5.6.3.tgz' }
  )
  hf = @(
    @{ Name = 'modelscope'; Url = 'https://modelscope.cn/models/AI-ModelScope/all-MiniLM-L6-v2/resolve/master/pytorch_model.bin' }
    @{ Name = 'hf-mirror';  Url = 'https://hf-mirror.com/sentence-transformers/all-MiniLM-L6-v2/resolve/main/pytorch_model.bin' }
    @{ Name = 'official';   Url = 'https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/pytorch_model.bin' }
  )
}

$selected = if ($Type -eq 'all') { @('github', 'pip', 'npm', 'hf') } else { @($Type) }

foreach ($group in $selected) {
  Write-Host ""
  Write-Host "[$group]"
  $rows = @()
  foreach ($t in $sets[$group]) {
    $r = Probe-Url -Url $t.Url -LimitSec $LimitSec
    $rows += [pscustomobject]@{ Name = $t.Name; Code = $r.Code; MB = $r.MB; TTFB = $r.TTFB; MBps = $r.MBps }
  }
  $rows | Sort-Object MBps -Descending | ForEach-Object {
    Write-Host ("  {0,-12} code={1,-4} got={2,5:N2}MB  ttfb={3,5:N2}s  {4,7:N2} MB/s" -f `
        $_.Name, $_.Code, $_.MB, $_.TTFB, $_.MBps)
  }
}

Write-Host ""
Write-Host "Note: 1MB samples are for comparison only. Use a 20MB+ file to judge real bandwidth."
