# 资产创建配方（通用）

> 本文件只写**跨项目通用**的机制与配方，具体数值用占位符 `<...>` 表示。
> 项目私有的类路径 / 目录规范 / 属性清单，见各自项目的文档。

## 通用流程

```
create            → 建资产（返回蓝图对象引用）
get_default_object→ 取 CDO（真正读写的对象）
list_properties   → 拿 schema（字段名 + 类型 + 枚举白名单）← 写之前必做
set_properties    → 写入（内存态）
get_properties    → 读回验证 ← 必做，set 返回 true 不代表写进去了
save_assets       → 落盘（接**数组**，可一次存多个）
```

多步操作请用 `execute_tool_script` 批处理（见 SKILL.md「批量执行」），
一是省往返，二是它带编辑器事务，失败自动回滚。

## 一、建"蓝图型"资产

`BlueprintTools.create` 内部走 `BlueprintFactory` + `parent_class`，
所以**任何以蓝图形式承载的资产**（GameplayEffect、GameplayAbility、蓝图 DataAsset 等）
都用它建。

```python
bp = tool("editor_toolset.toolsets.blueprint.BlueprintTools.create", {
    "folder_path": "<Folder>",              # 如 /Game/MyGame/Abilities
    "asset_name": "<AssetName>",
    "asset_type": {"refPath": "<ParentClassPath>"},   # 如 /Script/GameplayAbilities.GameplayEffect
})["returnValue"]
```

注意：
- 这样建出来的资产，`get_asset_class` 报的是 `Blueprint`（蓝图是载体）——**不要据此认为建错了**。
  判断真实类型用 `get_default_object` + `ObjectTools.get_class`。
- 目录不存在时会被自动创建。

## 二、CDO 的路径约定

蓝图的 CDO 路径是固定的：

```
<包路径>.<资产名>.Default__<资产名>_C
```

例：资产 `/Game/MyGame/Abilities/GE_Foo.GE_Foo`
→ CDO `/Game/MyGame/Abilities/GE_Foo.Default__GE_Foo_C`

所以知道资产路径就能直接推 CDO，**不必每次都调 `get_default_object`**。
（用 `get_default_object` 更稳妥，尤其是刚建完还没编译/加载时。）

## 三、字段名从 `list_properties` 来

`list_properties` 返回的是 **JSON Schema**，不是值。它给出：

- 字段名（首字母小写，如 `durationPolicy`、`modifiers`）
- 类型（`type` / `properties` / `items`）
- 枚举白名单（`enum` 数组）← 直接照着填，别猜

`set_properties` 的 `values` 是**字符串形式的 JSON**；`get_properties` 的 `properties` 是**必填数组**。

## 四、"三件套"结构体：名字 + owner + field-path

有些结构体字段由三部分组成，典型是 `FGameplayAttribute`：

```json
{
  "attributeName":  "<AttributeName>",                      // FName
  "attributeOwner": {"refPath": "<AttributeSetClassPath>"}, // UStruct*（AttributeSet 类）
  "attribute":      "<AttributeSetClassPath>:<AttributeName>"  // TFieldPath → 真正的 FProperty*
}
```

**三件缺一不可**，只写前两个的后果：

- 编辑器里**看起来正常**：加载资产时 `FGameplayAttribute::PostSerialize` 会用
  `AttributeOwner + AttributeName` 兜底解析出 `FProperty*`。
- **打包后失效**：`PostSerialize` 被包在 `#if WITH_EDITORONLY_DATA` 里，cooked 构建中不编译，
  `GetUProperty()` 也不做惰性解析（它只 `return Attribute.Get()`）→ 属性解析不出来，效果静默不生效。

所以 `attribute`（field-path）必须显式写入。路径格式：`<AttributeSetClassPath>:<PropertyName>`。

## 五、GameplayEffect 配方（占位符版）

```json
{
  "durationPolicy": "Instant",
  "modifiers": [
    {
      "attribute": {
        "attributeName": "<AttributeName>",
        "attribute": "<AttributeSetClassPath>:<AttributeName>",
        "attributeOwner": {"refPath": "<AttributeSetClassPath>"}
      },
      "modifierOp": "AddBase",
      "modifierMagnitude": {
        "magnitudeCalculationType": "ScalableFloat",
        "scalableFloatMagnitude": {"value": <Magnitude>}
      }
    }
  ]
}
```

枚举白名单（来自 `list_properties` 的 schema）：

| 字段 | 可选值 |
|---|---|
| `durationPolicy` | `Instant` / `Infinite` / `HasDuration` |
| `modifierOp` | `AddBase` / `MultiplyAdditive` / `DivideAdditive` / `MultiplyCompound` / `AddFinal` / `Max`（旧别名 `Additive` / `Multiplicitive` / `Division` / `Override`） |
| `magnitudeCalculationType` | `ScalableFloat` / `AttributeBased` / `CustomCalculationClass` / `SetByCaller` |

其它常用字段：

| 字段 | 用途 |
|---|---|
| `durationMagnitude.scalableFloatMagnitude.value` | `HasDuration` 时的持续秒数（`Infinite` 用 -1） |
| `period` | 周期效果的间隔秒数 |
| `stackingType` / `stackLimitCount` | 堆叠方式与上限 |
| `gameplayCues` | 挂 GameplayCue |
| `assetTags` / `grantedTags` | 资产标签 / 授予标签 |

## 六、落盘

```python
tool("editor_toolset.toolsets.asset.AssetTools.save_assets",
     {"asset_paths": ["/Game/MyGame/Abilities/GE_Foo", "/Game/MyGame/Abilities/GE_Bar"]})
```

- 传**空数组** = 保存所有脏资产
- 传路径数组 = 只存这些
- `bp["refPath"]` 形如 `/Game/.../GE_Foo.GE_Foo`，取 `.split(".")[0]` 即为 `save_assets` 要的路径
- 用 `is_dirty(asset_path)` 验证是否真的存下来了

## 七、验证配方：临时资产自检

不确定配方是否可用时，**不要拿真实资产试**。用「临时名字 + 不落盘 + 结尾删除」自检：

```python
def run():
    out = {}
    tmp = []
    for name, attr, value in [("GE_TmpCheck1", "<Attr>", 10.0)]:
        r = create_and_verify(name, attr, value)   # create → set → 读回
        tmp.append(r["asset"].split(".")[0])
        out[name] = r
    # 不调 save_assets；直接删除，磁盘不留痕
    out["deleted"] = [
        tool("editor_toolset.toolsets.asset.AssetTools.delete", {"path": p})["returnValue"]
        for p in tmp
    ]
    return out
```

要点：

- **不调 `save_assets`** → 资产只存在内存里，`delete` 后磁盘无残留
- 脚本本身带事务，中途失败会自动回滚
- 返回 `create_and_verify` 的**读回值**（不是写入值）才算验证通过
- 想让 AI 看到"是否真的写进去了"，就把读回值放进 `run()` 的返回 dict

