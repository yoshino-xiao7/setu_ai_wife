# 双角色生成说明

## 当前默认策略

双角色默认使用 `DUAL_CHARACTER_STRATEGY=mask-conditioning`。

流程是一轮采样：

1. 云端前端提交两个角色、两个 LoRA、正向/反向提示词和可选角色 A/B 区域。
2. Worker 生成角色 A/B 的黑白区域图。
3. ComfyUI 使用内置 `ConditioningSetMask` 节点，让角色 A/B 的提示词主要影响对应区域。
4. 最终仍然只从空 latent 生成一次图片，不对已有图片做二次局部重绘。

这个策略的重点是：区域图只约束提示词作用范围，不作为 inpaint 遮罩参与像素重绘，因此不会把画面某块抹掉再盖上一层。

## 为什么不再默认 inpaint

之前默认使用 `DUAL_CHARACTER_STRATEGY=inpaint`，流程是：

1. 先生成一张没有角色 LoRA 的底图。
2. 用角色 A 遮罩对底图局部重绘。
3. 再用角色 B 遮罩对第二张图局部重绘。

这个流程确实能减少一部分 LoRA 特征混合，但副作用很重：

- 不画手动区域时，默认左右半屏遮罩也会触发大面积 inpaint。
- 手动画范围时，画出来的区域会被当作需要重绘的像素区域，而不是单纯的构图提示。
- 亲密互动、遮挡、上下叠放时，两次重绘会互相覆盖，容易出现遮蔽、硬边、身体被盖住、互动姿势被破坏。
- 遮罩越大、`DUAL_INPAINT_DENOISE` 越高，角色越像 LoRA，但越容易破坏原图结构。

所以 inpaint 现在保留为实验模式，不再作为默认策略。

## 互动场景怎么写

互动关系要写在自然语言或正向提示词里，例如：

```text
八重神子和雷电影在沙滩上牵手奔跑，阳光，海浪，动态构图
```

亲密互动可以更明确，例如：

```text
Yae Miko and Raiden Shogun hugging, close interaction, one character leaning over another, intimate composition, two distinct characters
```

## 角色 A/B 区域

云端前端在双角色模式下提供“角色区域提示”：

- 角色 A：第一个角色或第一个角色预设。
- 角色 B：第二个角色或第二个角色预设。
- 不画区域：Worker 使用默认左右区域作为提示词范围。
- 画了区域：Worker 使用你画出的 A/B 区域作为提示词范围，适合拥抱、接吻、上下叠放、遮挡互动。

区域不用精确描边，最好覆盖角色的头发、脸、上半身、主要服装范围。它现在不会作为重绘遮罩盖住画面，只是给 ComfyUI 的区域提示词使用。

## 可调参数

`.env` 可配置：

```dotenv
DUAL_CHARACTER_STRATEGY=mask-conditioning
DUAL_MASK_CONDITIONING_STRENGTH=1.15
DUAL_INPAINT_DENOISE=0.62
DUAL_INPAINT_MASK_OVERLAP_RATIO=0.08
```

- `DUAL_CHARACTER_STRATEGY=mask-conditioning`：推荐默认值，单次生成，区域提示词约束。
- `DUAL_CHARACTER_STRATEGY=single`：完全不使用区域，只把两个角色和两个 LoRA 放入一次生成。
- `DUAL_CHARACTER_STRATEGY=inpaint`：旧实验模式，会二次局部重绘，容易产生遮蔽，只建议调试时临时使用。
- `DUAL_MASK_CONDITIONING_STRENGTH`：区域提示词强度，建议范围 `0.9` 到 `1.3`。
- `DUAL_INPAINT_DENOISE` 和 `DUAL_INPAINT_MASK_OVERLAP_RATIO` 只在 `inpaint` 策略下生效。

## 后续更强方案

如果还要继续提高双角色稳定性，可以考虑：

- 安装区域 LoRA 或 attention couple 类 ComfyUI 自定义节点。
- 接入人像/角色自动分割模型，自动生成更准确的角色区域。
- 对脸部和服装做可选局部修复，但不作为默认双角色流程。
