# 应用图标备选方案

当前参考照片：

- `C:\Users\SYKQW\OneDrive\文档\Playground\微信图片_20260408194648_382_6.jpg`

当前已落地版本：

- `C:\Users\SYKQW\OneDrive\文档\Playground\video-subtitle-learning-app\src-tauri\icons\icon.ico`
- `C:\Users\SYKQW\OneDrive\文档\Playground\video-subtitle-learning-app\src-tauri\icons\icon-preview.png`

后续如果要继续做新图标，优先保持这些统一要求：

- 正方形构图，适合 Windows 应用图标
- 主体尽量居中，避免太靠边
- 小尺寸下仍能认出是“橘猫”
- 避免复杂背景和太细的文字
- 色调尽量和当前应用一致：深色底、暖橙色点缀

## 方案 1：更可爱一点的 Q 版橘猫

定位：

- 更亲和
- 更适合长期做应用主图标
- 比真实照片更稳定，缩小后更清楚

关键词方向：

- Q版
- 圆脑袋
- 大眼睛
- 小粉鼻子
- 橘白猫
- 柔软毛感
- 可爱但不幼稚

生成提示词：

```text
Use case: logo-brand
Asset type: desktop app icon
Primary request: create a cute chibi orange-and-white cat icon based on the reference cat photo
Subject: orange-and-white cat head, round face, pink nose, soft fluffy fur, slightly mischievous but friendly expression
Style/medium: clean stylized illustration, polished app-icon quality
Composition/framing: centered cat head portrait, large face, minimal negative space, optimized for small icon sizes
Lighting/mood: warm, soft, friendly
Color palette: deep navy background with warm orange and cream white fur
Constraints: no text, no watermark, no extra objects, keep the cat recognizable as an orange-and-white domestic cat
Avoid: overly realistic rendering, messy fur edges, cluttered background, horror vibe, aggressive expression
```

推荐用途：

- 最适合作为最终桌面版主图标

## 方案 2：更像 logo 的扁平插画版

定位：

- 更像品牌标志
- 更干净、更现代
- 更适合做应用、网站、文档统一视觉

关键词方向：

- 扁平化
- 简化线条
- 高识别度猫头轮廓
- logo 感
- 图形化

生成提示词：

```text
Use case: logo-brand
Asset type: app logo icon
Primary request: create a flat logo-style icon of an orange-and-white cat inspired by the reference cat photo
Subject: simplified orange-and-white cat head with clear facial silhouette, small mouth, pink nose, relaxed eyes
Style/medium: flat vector-style illustration, minimal and brand-like
Composition/framing: centered cat face, bold simple shapes, strong silhouette, icon-ready
Lighting/mood: flat graphic design, no realistic lighting
Color palette: dark navy background, warm orange, cream white, subtle gold accent
Constraints: no text, no watermark, no gradients that are too noisy, keep shapes readable at 16x16 and 32x32
Avoid: photorealism, overly detailed fur, complex shadows, random decorations
```

推荐用途：

- 最适合以后做“品牌统一感”
- 如果你后面还想做启动页、网页 favicon、文档封面，这版会最稳

## 方案 3：更“表情包”一点的猫猫头版

定位：

- 更有记忆点
- 更有个人风格
- 适合偏轻松、有点梗感的产品气质

关键词方向：

- 猫猫头
- 微妙表情
- 有点坏笑
- 表情包感
- 夸张一点但不能崩

生成提示词：

```text
Use case: illustration-story
Asset type: expressive desktop app icon
Primary request: create a meme-like cat-head icon based on the reference orange-and-white cat photo
Subject: orange-and-white cat head with a funny half-squint expression, slightly open mouth, playful meme energy
Style/medium: stylized digital illustration, expressive and humorous, still clean enough for app icon use
Composition/framing: oversized cat head, centered, close-up portrait, compact framing for strong recognizability
Lighting/mood: playful, cheeky, internet-meme energy
Color palette: dark background with warm orange-white cat colors
Constraints: no text, no speech bubble, no watermark, expression should be funny but not ugly
Avoid: grotesque distortion, horror expression, cluttered composition, too much realism
```

推荐用途：

- 如果你希望这个软件更有“个人作品感”，这版会很有辨识度

## 我对三版的建议

- 如果你想要最稳的主图标：选“Q 版橘猫”
- 如果你想要更像正式产品：选“扁平插画版”
- 如果你想要更有趣、更像你的个人风格：选“表情包猫猫头版”

## 后续落地方式

等你准备正式生成时，直接告诉我下面三选一即可：

- `Q版橘猫`
- `扁平插画版`
- `表情包猫猫头版`

我会继续做：

1. 生成对应图
2. 输出预览图
3. 替换 `src-tauri/icons/icon.ico`
4. 帮你重新打包桌面版
