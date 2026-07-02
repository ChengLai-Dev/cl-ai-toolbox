# Explain Agent

专精于深度解释代码、概念和设计的 Agent。适用于内置 Agent 回答过于简略或表面时，需要深入理解"为什么"的场景。

## 何时使用

- 内置 Agent 回答太简短或太浅
- 不仅想知道代码*做了什么*，还想理解*为什么*这样做
- 需要设计权衡分析、实现原理或背景上下文
- 学习代码库时，需要引导式、带示例的说明

## 与内置 Agent 的对比

| 方面     | OpenCode内置 Agent (Build) | Explain Agent               |
|----------|--------------------|-----------------------------|
| 回答风格 | 简洁直白           | 结构化、教程式              |
| 深度     | 表面级             | 深入浅出，附示例            |
| 结构     | 一段话搞定         | 分节、表格、示意图          |
| 适用场景 | 快速问答、查命令   | 理解复杂逻辑                |

## 对比示例

Agent: Build vs Explain  
Model: DeepSeek V4 Flash Free

用户提问：

```cpp
struct CollisionInfo {
    bool colliding = false;
    Vec2 normal;
    float penetration = 0.0f;
    Vec2 contactPoint;
};
```

这些字段是干嘛的？

---

### Build

- colliding: 是否发生碰撞
- normal: 碰撞法线（从 B 指向 A 的单位向量，用于分离物体）
- penetration: 穿透深度（两个物体重叠的距离）
- contactPoint: 碰撞接触点（世界坐标位置）

---

### Explain

#### 问题诊断

CollisionInfo 是碰撞检测函数的输出，也是碰撞响应函数的输入。普通查看会发现四个字段各自独立，但它们的真实意义必须在碰撞检测 → 碰撞响应的流水线中才能理解。

#### 核心概念

先给精确定义：

| 字段 | 类型 | 本质含义 |
|------|------|----------|
| colliding | bool | 两个形状是否存在重叠 |
| normal | Vec2 | 从物体A指向物体B的单位向量 |
| penetration | float | 两个物体互相嵌入的深度（即最小重叠量） |
| contactPoint | Vec2 | 碰撞接触点的世界坐标（近似值） |

#### 深入剖析（流水线视角）

```
CheckAABBvsAABB(a, b)       →    CollisionInfo     →    ResolveCollision(posA, posB, info)
      碰撞检测函数                                          碰撞响应函数
           ↓                                                      ↓
      计算四个字段                                           读取字段修正位置
```

#### 1. colliding — 判决开关

碰撞检测的第一步是快速排除无碰撞情况。你的 AABB 检测第 8-9 行：

```cpp
if (a.max.x < b.min.x || a.min.x > b.max.x) return info;  // X轴无重叠 → false
if (a.max.y < b.min.y || a.min.y > b.max.y) return info;  // Y轴无重叠 → false
```

info 的 colliding 保持默认 false。之后 ResolveCollision 第一行就检查这个开关：

```cpp
if (!info.colliding) return;  // 没撞，什么都不做
```

#### 2. penetration — 嵌进去多深？

碰撞不是"表面接触"，而是两个形状重叠了。penetration 就是这个重叠的最小度量——把物体推开多少就能消除重叠。

AABB 检测中分别算 X 和 Y 两个方向的重叠量（第 13-14 行）：

```cpp
float overlapX = std::min(a.max.x, b.max.x) - std::max(a.min.x, b.min.x);
float overlapY = std::min(a.max.y, b.max.y) - std::max(a.min.y, b.min.y);
```

然后取较小的那个作为 penetration（第 20-26 行）。为什么要取较小的？因为物体是从重叠最小的方向"挤出去"的——如果水平嵌得浅，就从水平方向推出去；如果竖直嵌得浅，就从竖直方向推出去。

#### 3. normal — 朝哪推？

normal 在你的引擎中约定为从物体 A 指向物体 B 的单位向量。

AABB 检测中的选择逻辑（第 20-26 行）：

```cpp
if (overlapX < overlapY) {
    // X方向重叠更浅 → 法线水平
    info.normal = (diff.x > 0.0f) ? Vec2(1.0f, 0.0f) : Vec2(-1.0f, 0.0f);
    info.penetration = overlapX;
} else {
    // Y方向重叠更浅 → 法线垂直
    info.normal = (diff.y > 0.0f) ? Vec2(0.0f, 1.0f) : Vec2(0.0f, -1.0f);
    info.penetration = overlapY;
}
```

diff 是 bCenter - aCenter，所以法线的符号直接由"B 相对于 A 的位置"决定。

法线在 ResolveCollision 中的用法（第 110-111 行）：

```cpp
posA -= info.normal * (info.penetration * ratioA);
posB += info.normal * (info.penetration * ratioB);
```

A 沿 -normal 退，B 沿 +normal 退——两个物体背向分离。

#### 4. contactPoint — 碰在哪？

接触点是碰撞发生位置的记录。在你的代码中，AABB 的接触点取两个中心的中点作为近似（第 28 行）：

```cpp
info.contactPoint = (aCenter + bCenter) * 0.5f;
```

Circle 碰撞中的计算更精确（第 53 行）：

```cpp
// 从A圆心沿法线方向走"到达接触面中间"的距离
info.contactPoint = a.center + info.normal * (a.radius - info.penetration * 0.5f);
```

当前 contactPoint 在 ResolveCollision 中没有被使用，但它为后续扩展预留了位置。有了接触点，你可以实现：

- 摩擦力：需要在接触点计算相对速度
- 旋转（扭矩）：力作用在接触点产生旋转力矩
- 粒子效果/声音：碰撞发生的位置产生视觉和听觉反馈

#### 图解

生成的 PNG 和对应的 .docx 文件在项目根目录下：

- 图片: xxxxx.png
- 文档: xxxxx.docx

CollisionInfo 示意图中展示了一个 AABB vs AABB 碰撞的完整场景：

| 标注 | 颜色 | 对应字段 | 说明 |
|------|------|----------|------|
| 蓝色方块 | 蓝 | AABB A | 左侧的 AABB |
| 橙色方块 | 橙 | AABB B | 右侧的 AABB |
| 粉色区域 | 粉 | penetration | 两个 AABB 的重叠区域（本例中 overlapX < overlapY，所以取 overlapX 作为 penetration） |
| 绿色箭头 | 绿 | normal | 从 A 中心指向 B 中心 |
| 紫色星号 | 紫 | contactPoint | 碰撞接触点（两中心中点） |

#### 案例分析：完整的碰撞处理流程

假设：

- AABB A: min(1,1), max(4,5)，质量 1.0
- AABB B: min(3.5,2), max(6.5,4)，质量 2.0

**第 1 步 — 碰撞检测：**

```cpp
// overlapX = min(4, 6.5) - max(1, 3.5) = 4 - 3.5 = 0.5
// overlapY = min(5, 4) - max(1, 2) = 4 - 2 = 2.0
// overlapX (0.5) < overlapY (2.0) → 选择水平方向
// diff = (5, 3) - (2.5, 3) = (2.5, 0) → diff.x > 0 → normal = (1, 0)
// penetration = 0.5
// contactPoint = (2.5, 3) 和 (5, 3) 的中点 = (3.75, 3)
```

输出：

```
colliding = true
normal    = (1, 0)
penetration = 0.5
contactPoint = (3.75, 3)
```

**第 2 步 — 碰撞响应：**

```
totalMass = 1.0 + 2.0 = 3.0
ratioA = massB / totalMass = 2.0 / 3.0 ≈ 0.667
ratioB = massA / totalMass = 1.0 / 3.0 ≈ 0.333

posA -= (1, 0) * (0.5 * 0.667) = (1, 0) * 0.333  → A 向左移 0.333
posB += (1, 0) * (0.5 * 0.333) = (1, 0) * 0.167  → B 向右移 0.167
```

结果：质量大的 B 只被推开 0.167，质量小的 A 被推开 0.333——符合直觉（重的物体更难被推动）。

#### 总结

| 字段 | 说明 |
|------|------|
| colliding | 有没有撞？（检测的开关判决） |
| penetration | 嵌多深？（需要推开多少距离） |
| normal | 朝哪推？（分离的方向） |
| contactPoint | 在哪碰？（后续扩展用：摩擦力、旋转、特效） |

这四个字段中，**normal 和 penetration 是真正的核心**——ResolveCollision 只用它们两个就完成了位置修正。contactPoint 是给未来更高级的功能做准备的。

建议的下一步操作：你可以试着修改 main.cpp，让两个物体发生碰撞后，用 printf 或调试器打印出 CollisionInfo 的四个字段值，亲自验证检测结果是否符合预期。
