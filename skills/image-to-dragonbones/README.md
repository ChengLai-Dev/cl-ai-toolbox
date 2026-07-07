# 精简模式补丁

`inference_utils.py` 是 See-through 项目 `common/utils/` 下的模块，加了对 `--taglist compact` 的支持。

## 使用方法

```powershell
# 1. 备份原文件
cp "{SEE_THROUGH}\common\utils\inference_utils.py" "{SEE_THROUGH}\common\utils\inference_utils.py.bak"

# 2. 用本目录的版本替换
copy inference_utils.py "{SEE_THROUGH}\common\utils\inference_utils.py"

# 3. 推理时加 --taglist compact
python run_inference.py --image ... --output ... --taglist compact
```

## 恢复原版

```powershell
copy "{SEE_THROUGH}\common\utils\inference_utils.py.bak" "{SEE_THROUGH}\common\utils\inference_utils.py"
```

## 改了什么

参考 `inference_utils.py` 中 `COMPACT_BODY_DROP`、`COMPACT_HEAD_MERGE`、`COMPACT_HEAD_KEEP` 三个常量和 `taglist_mode` 参数的处理逻辑。
