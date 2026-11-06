# 测速数据与配置附录

## 测试环境

| 项 | 值 |
|---|---|
| 时间 | 2026-11-02 |
| 系统 | Windows |
| 出口 | 中国电信 IPv6（Cloudflare 显示 loc=CN / colo=SJC） |
| 代理 | 无（WARP 对测试请求未生效，`warp=off`） |
| 工具 | curl 8.13（单线程）、git 2.51、Python 3.12 |
| 方法 | 每源 2~3 轮，60s 截断，按实际字节折算平均速度 |

## GitHub clone（`--depth 1`，facebook/react，40MB）

| 源 | 平均 MB/s | 峰值 MB/s | 结果 |
|---|---:|---:|---|
| gh-proxy.com | 3.48 | 4.22 | 成功 |
| ghfast.top | 2.66 | 2.92 | 成功 |
| github.com 官方 | — | — | 失败：`early EOF` / 连接重置 |
| ghproxy.net | — | — | 失败：120 秒无响应 |
| hub.gitmirror.com / kkgithub.com / github.moeyy.xyz | — | — | 不可达 |
| gitclone.com | — | — | 超时 |

## GitHub Release（Git for Windows，65.6MB）

| 源 | 平均 MB/s | 峰值 MB/s |
|---|---:|---:|
| gh-proxy.com | 22.92 | 24.56 |
| ghfast.top | 2.20 | 2.23 |
| ghproxy.net | 0.30 | 0.53 |
| github.com 官方 | — | 连接超时 |

## GitHub Release 小文件对照（nvim，12.2MB）

| 源 | 平均 MB/s | 峰值 MB/s |
|---|---:|---:|
| gh-proxy.com | 1.96 | 5.50 |
| ghfast.top | 1.74 | 2.40 |
| ghproxy.net | 0.15 | 0.29 |
| github.com 官方 | 0.02 | 0.03 |

同一批源在 12MB 和 65MB 文件上的差距接近 10 倍，说明小文件受 TCP 慢启动影响严重。判断速度用 20MB 以上的样本。

## GitHub tarball（codeload，9.8MB）

| 源 | 平均 MB/s | 峰值 MB/s |
|---|---:|---:|
| gh-proxy.com | 7.22 | 8.82 |
| codeload.github.com 官方 | 2.86 | 5.41 |
| ghfast.top | 2.44 | 2.48 |

codeload 是 GitHub 少数官方直连可用的通道，适合 tarball 场景。

## PyPI（numpy 2.1.3 源码包，19.2MB）

| 源 | 平均 MB/s | 峰值 MB/s |
|---|---:|---:|
| 华为云 | 48.15 | 87.87 |
| 腾讯云 | 40.95 | 80.54 |
| 阿里云 | 39.32 | 53.76 |
| 清华 TUNA | 22.50 | 25.51 |
| pypi.org 官方 | 5.99 | 9.20 |
| USTC | 0.01 | 已停止镜像，返回错误页 |

## npm（@next/swc-win32-x64-msvc，56.6MB）

| 源 | 平均 MB/s | 峰值 MB/s |
|---|---:|---:|
| npmmirror | 27.40 | 37.58 |
| 腾讯云 | 25.01 | 26.64 |
| 华为云 | 10.28 | 10.29 |
| registry.npmjs.org 官方 | 3.76 | 5.63 |

## HuggingFace（all-MiniLM-L6-v2，86.7MB）

| 源 | 平均 MB/s | 峰值 MB/s | 落地地址 |
|---|---:|---:|---|
| ModelScope | 25.03 | 26.08 | cdn-lfs-cn-1.modelscope.cn |
| hf-mirror（`?download=true`） | 10.58 | 14.52 | cas-bridge.xethub.hf.co |
| hf-mirror（普通） | 3.66 | 3.72 | cas-bridge.xethub.hf.co |
| huggingface.co 官方 | — | — | 完全不可达 |

hf-mirror 只做 302，实际字节来自海外 `cas-bridge.xethub.hf.co`，速度不稳定（复测曾降到 4.8 MB/s）。

## Conda（kaleido-core 0.2.1，54.3MB）— 本机未安装

| 源 | 平均 MB/s | 峰值 MB/s |
|---|---:|---:|
| 清华 TUNA | 27.35 | 29.03 |
| 北外 BFSU | 25.96 | 26.21 |
| repo.anaconda.com 官方 | 10.46 | 13.53 |
| 南大 NJU | — | 302 后失败 |
| 阿里云 / 腾讯云 | — | 404，镜像已停 |

## Docker（python:3.12-slim，最大层 28.5MB）— 本机未安装

| 源 | 平均 MB/s | 峰值 MB/s |
|---|---:|---:|
| docker.1panel.live | 6.23 | 9.00 |
| docker.1ms.run | 5.16 | 5.53 |
| dockerproxy.net | 1.98 | 2.03 |
| registry-1.docker.io 官方 | — | 连接超时 |
| docker.nju.edu.cn | — | 403 |
| docker.xuanyuan.me | — | 免费节点限流 |

## 已验证失效的源

| 源 | 状态 |
|---|---|
| gitclone.com | 超时 |
| hub.gitmirror.com | 不可达 |
| kkgithub.com | 不可达 |
| github.moeyy.xyz | 不可达 |
| ghproxy.net | 极慢（0.3 MB/s） |
| USTC PyPI | 已停止服务 |
| mirrors.aliyun.com/anaconda | 404 |
| mirrors.cloud.tencent.com/anaconda | 404 |
| docker.m.daocloud.io | 不可达 |
| dockerproxy.com | 不可达 |
| dockerpull.org | 不可达 |
| mirror.ccs.tencentyun.com | 不可达（仅内网可用） |

## 复测脚本

```
pwsh -NoProfile -File "D:\Code\.config\opencode\skills\fast-download\scripts\probe.ps1" -Type all
```

`-Type` 可选 `github|pip|npm|hf`。脚本对每个候选源发 1MB Range 请求，输出 TTFB 与吞吐排序，不落盘。1MB 样本只用于横向比较，绝对值偏低。

## 全局配置附录

默认使用临时参数。只有用户明确要求持久化时才改这些文件，它们会影响所有项目。

### Git 全局重写

```powershell
git config --global url."https://gh-proxy.com/https://github.com/".insteadOf "https://github.com/"
```

取消：

```powershell
git config --global --unset url."https://gh-proxy.com/https://github.com/".insteadOf
```

副作用：`git push` 也会走代理，可能失败。

### pip

```powershell
pip config set global.index-url https://repo.huaweicloud.com/repository/pypi/simple
pip config set global.trusted-host repo.huaweicloud.com
```

### npm

```powershell
npm config set registry https://registry.npmmirror.com
```

### HuggingFace（用户级环境变量）

```powershell
[Environment]::SetEnvironmentVariable('HF_ENDPOINT', 'https://hf-mirror.com', 'User')
```

### Conda

```yaml
channels:
  - defaults
default_channels:
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/r
custom_channels:
  conda-forge: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
```

### Docker（`daemon.json`）

```json
{
  "registry-mirrors": [
    "https://docker.1panel.live",
    "https://docker.1ms.run"
  ]
}
```
