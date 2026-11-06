---
name: fast-download
description: 在国内网络下载 Git 仓库、GitHub Release 资产、pip/npm 包、HuggingFace 模型时选择实测最快的源，并做分级哈希校验。Use when git clone 超时中断、下载 releases/download 资产、pip install 慢、npm install 慢、hf download 卡住，或官方源报 early EOF、connection timed out。
---

# 快速下载源

官方源在国内多数不可达。按决策表选源，失败后走降级链。

## 决策表

| 场景 | 首选 | 备选 |
|---|---|---|
| GitHub clone / Release / raw | `gh-proxy.com` 前缀 | `ghfast.top` 前缀 |
| pip | 华为云 | 腾讯云 → 阿里云 |
| npm | npmmirror | 腾讯云 |
| HuggingFace | ModelScope | hf-mirror |

速度数据、失效源清单、全局配置见 `REFERENCE.md`。

## 执行

### Git

```
git clone https://gh-proxy.com/https://github.com/OWNER/REPO.git
curl.exe -L -O "https://gh-proxy.com/https://github.com/OWNER/REPO/releases/download/TAG/FILE"
```

前缀只作用于本次命令，`git push` 走原地址。子模块要单独加前缀。优先 `--depth 1 --single-branch`。

### pip / npm

```
pip install -i https://repo.huaweicloud.com/repository/pypi/simple --trusted-host repo.huaweicloud.com PACKAGE
npm install --registry https://registry.npmmirror.com PACKAGE
```

### HuggingFace

```
$env:HF_ENDPOINT = "https://hf-mirror.com"
hf download REPO_ID --local-dir DEST
```

ModelScope 更快，但同名仓库不是字节级镜像，替换前先比对文件。

## 降级链

```
首选 → 备选 → 官方直连
```

只在上一级失败时降级，逐级记录失败原因。

## 分级校验

| 级别 | 对象 | 做法 |
|---|---|---|
| 强制 | GitHub Release | `assets[].digest` 对比 `Get-FileHash` |
| 强制 | 模型权重 | `hf download` 内置校验；ModelScope 替代品逐文件比对 |
| 交给工具 | pip / npm / git | `--require-hashes`、lockfile `integrity`、commit SHA |

```powershell
$rel = curl.exe -s "https://api.github.com/repos/OWNER/REPO/releases/latest" | ConvertFrom-Json
$rel.assets | Select-Object name, size, digest
Get-FileHash .\FILE -Algorithm SHA256
```

## 注意

- 小文件测不出真实带宽，判断速度用 20MB 以上的样本。
- 复测：`pwsh -NoProfile -File "D:\Code\.config\opencode\skills\fast-download\scripts\probe.ps1" -Type all`
