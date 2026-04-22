# 仓库清理记录

> 本文件记录 commit `e3eb2d6` 的清理内容与后续注意事项。

## 目的

原仓库追踪了大量非必要内容（第三方发行包、自身打包副本、孤儿 submodule、模型权重碎片），导致 clone 缓慢、diff 噪声大。本次清理**只从 git 索引移除**这些内容，**工作区文件保留**不丢，但未来不再被追踪。

## 清理前后对比

| 指标 | 清理前 | 清理后 |
|---|---|---|
| 追踪文件数 | 671 | 331 |
| 最大单文件 | `en-us.lm.bin` 27MB | `scripts/setup_database.py` 约 9KB |
| `deploy/tts_server/` | 在仓 185MB | 本地保留，不入仓 |

本次 commit 变更：`341 files changed, 7 insertions(+), 911015 deletions(-)`

## 被移除的内容清单

### 1. `deploy/tts_server/` 整体（≈185MB）

> 已加入 `.gitignore`，工作区文件保留作为部署参考

- `Rhubarb-Lip-Sync-1.13.0-Linux/`：第三方 Linux 发行包
  - `rhubarb`（7.3MB 可执行）
  - `res/sphinx/en-us.lm.bin`（27MB 语音识别模型）
  - `res/sphinx/cmudict-en-us.dict`（3.2MB）
  - `extras/EsotericSoftwareSpine/rhubarb-for-spine-1.13.0.jar`（17MB）
  - `include/{gmock,gtest}/*.h`：GoogleMock/GoogleTest 头文件
- `tts_server_pack/`：`deploy/tts_server/` 的自身副本（93MB，内容几乎一致）
- `cosyvoice/` / `engine/` / `third_party/`：与 `src/backend/tts/` 下内容重复

### 2. 孤儿 submodule

仓库里有两个 gitlink 但根目录没有 `.gitmodules`：

- `models/ASR/fsmn-vad`（`160000 commit 931934ce…`）
- `models/ASR/paraformer-zh-streaming`（`160000 commit 5bb33a93…`）

模型应由 ModelScope 按需下载（例如 `scripts/setup_database.py` 或启动脚本），不进仓。

### 3. 模型 tokenizer 碎片

- `models/TTS/CosyVoice2-0.5B/CosyVoice-BlankEN/merges.txt`（≈400KB）
- `models/embedding/all-MiniLM-L6-v2/onnx/vocab.txt`（≈200KB）

`.gitignore` 原本就有 `models/` 规则，但这些文件此前已被 track，需 `git rm --cached` 让规则重新生效。

## 新增的 `.gitignore` 规则

```gitignore
# 部署打包产物（CosyVoice + Rhubarb-Lip-Sync 等第三方发行包，按需下载/打包，不入仓）
deploy/tts_server/
deploy/*_pack/
Rhubarb-Lip-Sync-*/
# Sphinx 语音识别离线模型（随 Rhubarb 分发）
**/res/sphinx/
```

另：上一次 commit 已经加过的（`d8cd5d5`）：

```gitignore
src/frontend/live2d/dependency-reduced-pom.xml   # Maven shade 构建产物
src/frontend/live2d/libLive2DCubismCore.dylib    # Live2D SDK 原生库（License 限制）
src/frontend/live2d/libLive2DCubismCore.so
```

## 保留的 Windows 资产

| 文件 | 保留原因 |
|---|---|
| `src/frontend/live2d/Live2DCubismCore.dll` | Windows 开发者 clone 即能跑 Live2D，原作者故意入仓 |
| `scripts/install_dependencies.bat` / `deploy.bat` / `fix_yaml_compatibility.bat` | Windows 一键脚本 |
| `models/TTS/.gitkeep` / `models/embedding/.gitkeep` / `models/README.txt` | 目录占位与说明 |

## 被清理内容如何恢复或使用

### `deploy/tts_server/` 本地工作区

文件仍在磁盘上（185MB），仅不再入 git。如要部署：

```bash
# 直接打包
tar czf tts_server.tgz deploy/tts_server/
# 或 rsync 到服务器
rsync -a deploy/tts_server/ zert@<server>:/opt/tts_server/
```

### 模型按需下载

```python
# CosyVoice2
from modelscope import snapshot_download
snapshot_download("iic/CosyVoice2-0.5B", local_dir="models/TTS/CosyVoice2-0.5B")

# Paraformer / fsmn-vad 同理走 modelscope（或 FunASR 自动下载）
```

## 仓库体积说明

- `git rm --cached` 只改索引，**不改历史**。`.git/objects/` 里这些 blob 还在。
- 新 clone 下来不会拉 `deploy/tts_server/` 文件，但 `.git/` 仍携带历史 objects。
- 如果要**真正压缩 `.git/` 体积**（清理所有历史中的大文件），需要改写历史：

  ```bash
  # 推荐用 git-filter-repo
  pip install git-filter-repo
  git filter-repo --path deploy/tts_server/ --invert-paths
  git filter-repo --path models/ASR/fsmn-vad --invert-paths
  # ...
  ```

  **代价**：commit 哈希全变，所有协作者必须重新 clone。除非仓库向公网发布、体积敏感，一般不做。

## 未来准入规则建议

- 任何**第三方二进制发行包**（Linux 可执行、DLL/dylib/so 以外的，见 License）：不入仓，通过脚本下载
- 任何**模型权重/tokenizer**：不入仓，通过 ModelScope/HF 下载
- 任何**构建产物**（Maven shade 产物、Python egg、打包 tar/zip）：不入仓
- 任何**私密配置**（`.env` / `api_keys.json`）：不入仓，`.env.example` / `api_keys.example.txt` 示例文件可以入仓

---

**相关 commits**：

- `e3eb2d6` chore: 清理仓库非必要追踪内容（本次）
- `d8cd5d5` fix: 修复 f-string 语法并加入 macOS 兼容路径
