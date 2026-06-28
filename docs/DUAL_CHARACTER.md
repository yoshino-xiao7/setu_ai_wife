# 双角色生成说明

## 当前默认策略

双角色默认使用 `DUAL_CHARACTER_STRATEGY=auto`。

`auto` 的行为：

1. 不画角色 A/B 区域时，使用普通单次双角色生成。
2. 同时画出角色 A 和角色 B 区域时，只提取 A/B 的大致位置、上下左右和靠近关系，作为普通正向提示词里的布局参考。
3. 永远不默认使用 inpaint 局部重绘。
4. 永远不默认使用 ComfyUI `ConditioningSetMask` 区域条件。

这样做是为了避免两个常见坏结果：

- 默认左右区域条件过强时，左右两边可能各自又生成两个人。
- 手绘区域条件过强或区域互相覆盖时，A/B 会互相抢身体，容易出现融合、多手、多脚或某个角色消失。

## 为什么不能只靠内置区域提示完美隔离 LoRA

当前 ComfyUI 基础节点能把提示词限制到区域，但不能把 LoRA 本身真正限制到区域。两个角色 LoRA 仍然是全局加载到同一个模型里的。

因此双角色比单角色更容易出现：

- 角色特征串味。
- 两个角色融合成一个角色。
- 额外手脚。
- 一个角色抢走另一个角色的发色、服装或脸部特征。

本项目现在的默认方案是保守优先：降低双角色 LoRA 上限，默认不启用 mask conditioning，只把手绘区域转成布局文本提示，先保证构图和人数稳定。

## 互动场景怎么写

互动关系要写在自然语言或正向提示词里，例如：

```text
八重神子和雷电影在沙滩上牵手奔跑，阳光，海浪，动态构图
```

亲密互动可以更明确，例如：

```text
Yae Miko and Raiden Shogun hugging, close interaction, one character leaning over another, intimate composition, exactly two characters total
```

## 角色 A/B 区域

云端前端在双角色模式下提供“角色布局参考”：

- 角色 A：第一个角色或第一个角色预设。
- 角色 B：第二个角色或第二个角色预设。
- 不画区域：走普通双角色单次生成。
- 只画 A 或只画 B：不启用布局参考，避免单边区域误导构图。
- 同时画 A 和 B：提取 A/B 大致位置关系，作为普通正向提示词的一部分，不会触发区域 mask。

画区域时不要把两个角色都圈进同一区域。最好分别覆盖每个角色的大致位置即可，它不是精准分割遮罩。

## 可调参数

`.env` 可配置：

```dotenv
DUAL_CHARACTER_STRATEGY=auto
DUAL_LORA_STRENGTH_CAP=0.65
DUAL_MASK_CONDITIONING_STRENGTH=0.95
DUAL_INPAINT_DENOISE=0.62
DUAL_INPAINT_MASK_OVERLAP_RATIO=0.08
```

- `DUAL_CHARACTER_STRATEGY=auto`：推荐默认值；不画区域就普通双角色生成，完整画 A/B 时只提取布局文本提示。
- `DUAL_CHARACTER_STRATEGY=mask-conditioning`：显式实验模式，始终使用 ComfyUI `ConditioningSetMask` 区域条件；当前模型下容易融合成一个角色，不建议普通用户默认开启。
- `DUAL_CHARACTER_STRATEGY=single`：完全不使用区域，只把两个角色和两个 LoRA 放入一次生成。
- `DUAL_CHARACTER_STRATEGY=inpaint`：旧实验模式，会二次局部重绘，容易产生遮蔽，只建议临时排查。
- `DUAL_LORA_STRENGTH_CAP`：双角色模式下每个 LoRA 的最高强度，默认 `0.65`，用于降低 LoRA 互相污染。
- `DUAL_MASK_CONDITIONING_STRENGTH`：仅 `mask-conditioning` 策略下生效。越高区域条件越明显，但越容易抢身体和出多肢体。
- `DUAL_INPAINT_DENOISE` 和 `DUAL_INPAINT_MASK_OVERLAP_RATIO` 只在 `inpaint` 策略下生效。

## 后续更强方案

如果还要继续提高双角色稳定性，需要安装更专门的区域控制节点，例如 attention couple / regional LoRA 类节点，或者接入自动分割后再做可选局部修复。仅靠 ComfyUI 内置基础节点，双 LoRA 的区域隔离能力有限。
