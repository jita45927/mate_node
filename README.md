# Mate Node - ComfyUI 自定义节点包

包含六个节点：**捏脸提示词生成器**、**国风发型/发饰提示词生成器**（标签化拼接，三路输出）、**文本换行连接**（多段文本合并）、**加载图像外补/裁剪**（可视化画板定义输出区域）、**随机提示词权重**（逐片段随机加权）与 **Image Blur + Noise**（模糊 + 噪点）。

| 节点 | 分类 | 用途 |
|---|---|---|
| 捏脸提示词生成器 (Mate) | Mate/捏脸 | 下拉标签 → 中文 / 英文 / SD 短 tag 三路提示词 |
| 国风发型/发饰提示词生成器 (Mate) | Mate/国风 | 按性别切换选项的国风发型 / 配饰标签 → 三路提示词 |
| 文本换行连接 (Mate) | utils/text | 多段文本按顺序换行合并，连接后自动增加备用输入口 |
| 加载图像外补/裁剪 (Mate) | Mate/image | 画板方框定义外补或裁剪区域，输出图像、遮罩与尺寸 |
| 随机提示词权重 | utils/text | 按逗号拆分为每个片段随机分配 `(片段:权重)` |
| Image Blur + Noise | image/effects | 对图像做高斯模糊并叠加噪点 |

## 节点一：捏脸提示词生成器

通过下拉框选择各维度标签（每个标签预设多个选项），自动拼接为结构化提示词，同时输出**中文**、**英文**、**英文短 tag** 三种格式。

### 功能特点

- **17 个标签维度**：风格、人种性别、年龄段、气质、脸型骨相、皮肤、眉形、眼睛、鼻型、嘴型、发型、发色、表情、姿态、妆容、背景，外加「其他」自由文本
- **三路输出**，一节点同时适配多类模型
- **肖像友好**：姿态选项全部为收敛的肖像姿势（正脸、微侧、三分之四侧、微低头/抬头、微歪头、侧脸、侧身回眸），不含夸张动作
- **无冲突设计**：发型标签不含任何颜色，头发颜色完全由「发色」标签独立控制
- **可选本地离线翻译**：「其他」中输入的英文可自动翻译成英文，全程离线、CPU 推理、不占用显存
- **零依赖启动**：翻译依赖全部懒加载，不开启翻译功能时节点可直接使用

## 三路输出说明

| 输出口 | 格式示例 | 适用模型 |
|---|---|---|
| `prompt_zh` | `[风格]写实摄影`<br>`[脸型骨相]长椭圆脸，颧骨平缓，下颌角约115度圆润，下巴长而圆润` | Z-Image、Kolors、混元、即梦、Qwen-Image 等中文原生模型 |
| `prompt_en` | `[Style]realistic photography`<br>`[Face Shape]long oval face, flat gentle cheekbones, rounded jaw angle of about 115 degrees, long rounded chin` | FLUX、SD3.5 等英文自然语言模型 |
| `tags_en` | `photorealistic, realistic photo, asian woman, long oval face, soft cheekbones, rounded jawline, round chin` | SD1.5、SDXL、Pony 等 CLIP 编码器模型 |

### 为什么 `tags_en` 单独做短 tag

SD1.5/SDXL 使用 CLIP 文本编码器，存在 **75 token 上限**，且只对短关键词敏感。因此每个选项都额外维护了一份 SD 专用短 tag 版本：去掉角度数值、连接词和长句结构，压缩为核心关键词，并使用 `photorealistic`、`portrait`、`looking at viewer`、`simple background` 等 SD 训练分布中的高频表达。

> 提示：使用 `tags_en` 时建议只选 6-8 个核心标签，标签顺序已按重要性（风格、人种、脸型优先）排列，超出部分会被 CLIP 截断。

## 安装

将整个 `mate_node` 文件夹放入 ComfyUI 的 `custom_nodes` 目录，重启 ComfyUI 即可。

```
ComfyUI/custom_nodes/mate_node/
├── __init__.py
├── nodes.py
├── guofeng_hairstyle.py
├── text_join.py
├── image_pad_crop.py
├── random_prompt_weights.py
├── blur_noise_node.py
├── translate.py
├── requirements.txt
├── web/
│   ├── image_pad_crop.js
│   ├── guofeng_hairstyle.js
│   └── text_join.js
└── README.md
```

节点位置：右键菜单 → **Mate/捏脸**、**Mate/国风**、**Mate/image**、**utils/text**、**image/effects**，也可在画布上双击搜索节点名称。

## 使用

1. 在各标签下拉框中选择选项
2. 未使用的维度保持默认的「（不使用）」，该行不会出现在输出中
3. 「其他」输入框中可填写任意补充描述
4. 将所需输出口连接到后续节点（CLIP 文本编码、Prompt 显示节点等）

## 本地离线翻译（可选）

节点提供「翻译其他为英文」开关，默认关闭。

开启后，当「其他」中包含中文时：

- 中文原文进入 `prompt_zh`
- 翻译后的英文进入 `prompt_en` 和 `tags_en`
- 预设标签始终使用预置英文，不经过翻译

### 自动化部署

首次触发翻译时，节点会自动完成以下步骤，无需手动操作：

1. 检测依赖，缺失则自动 `pip install transformers sentencepiece sacremoses`
2. 经 `hf-mirror.com` 镜像下载 `Helsinki-NLP/opus-mt-zh-en` 模型（约 300MB，仅首次）
3. 强制 **CPU 推理**，不占用显卡显存
4. 翻译结果内存缓存，相同文本不重复翻译

模型下载完成后**完全离线可用**。依赖与模型均缓存在本机，拷贝节点文件夹到其他电脑时会重新自动下载一次。

### 失败回退

任何环节失败（无网络、依赖安装失败、模型下载失败、推理异常）都会**回退输出原文**，节点不会崩溃，仅在 ComfyUI 控制台输出 `[mate_node]` 开头的提示。

> 小翻译模型对文学化、术语化表达（如「金丝眼镜」）容易翻译不准。若翻译质量不满足需求，可修改 [translate.py](translate.py) 接入 Ollama 或云端 API，节点代码无需改动。

## 节点二：加载图像外补/裁剪

分类 `Mate/image`。节点内直接选择或上传图片，点击「外补画板」弹出可视化编辑窗，用虚线方框定义输出区域。

### 输出

| 输出口 | 类型 | 说明 |
|---|---|---|
| `image` | IMAGE | 外补 / 裁剪后的图像 |
| `mask` | MASK | 外补遮罩，1 = 外补区域，0 = 原图区域 |
| `width` | INT | 最终图像宽度（像素） |
| `height` | INT | 最终图像高度（像素） |

### 方框语义

**输出尺寸 = 方框尺寸**：

| 方框与图片关系 | 结果 |
|---|---|
| 大于图片 | 空白处为外补区域 |
| 小于图片 | 纯裁剪，mask 全 0 |
| 与图片交叉 | 既外补又裁剪 |

坐标以原图像素为单位，允许负值（向左 / 向上外补）。

### 参数

| 参数 | 说明 |
|---|---|
| 图像 | 下拉选择输入目录中的图片，或使用上传按钮 |
| 启用长边 | 打开后按「长边」缩放输出 |
| 长边 | 整数，默认 1024。开启时输出长边精确等于该值，等比缩放 |
| 背景填充 | 无（透明 RGBA）/ 白色 / 黑色 / 灰色 / 红色 / 绿色 / 蓝色 |
| 取整倍数 | 8 / 16 / 32 / 64（默认 8）。最终宽高向上取整到该倍数，多出的部分在右侧 / 底部按背景填充补齐，`mask` 对应区域为 1 |
| 遮罩羽化 | 整数，默认 0（不羽化），范围 0–256。数值为羽化半径（像素），对 `mask` 做高斯羽化，图像不受影响 |

> `背景填充 = 无` 时输出 4 通道 RGBA，外补区 alpha = 0。部分下游节点（如 VAEEncode）只接受 3 通道，若报错请改用颜色填充，或先在链路中移除 alpha。

### 画板操作

- 拖动方框内部：移动方框
- 拖动 4 边 / 4 角：调整大小
- 在空白处拖拽：新建方框
- 方框边界靠近原图边界时自动吸附（8 屏幕像素阈值，带滞回防抖）
- 方向键微调 1px，Shift + 方向键 10px
- Enter 应用，Esc 取消

`x` / `y` / `宽` / `高` 四个数值在节点界面上隐藏，由画板维护并随工作流保存。切换图片时方框自动重置为整张新图；重新打开工作流时保留已保存的方框。

## 节点三：随机提示词权重

分类 `utils/text`。按逗号拆分提示词，为每个片段随机追加权重，写成 `(片段:权重)`，原始文本内容不变。

| 参数 | 说明 |
|---|---|
| text | 原始提示词，支持多行 |
| weight_min / weight_max | 随机权重下限 / 上限，默认 0.7 / 1.3 |
| exclude | 逗号分隔的片段，匹配到的保持原样、不加权重 |
| seed | -1 时每次运行权重都不同；固定数值可复现 |

输出 `加权文本`（STRING）。已含 `()` `[]` 权重语法或 `<lora:...>` 尖括号标签的片段会自动跳过，不重复加权。

## 节点四：Image Blur + Noise

分类 `image/effects`。先做高斯模糊、再叠加随机噪点，顺序可通过 `blur_first` 切换。

| 参数 | 说明 |
|---|---|
| image | 输入图像 |
| blur_strength | 模糊强度，0–1，默认 0.1 |
| noise_strength | 噪点强度，0–1，默认 0.1 |
| blur_first | 打开时先模糊后噪点，关闭时先噪点后模糊 |

输出 `IMAGE`。

## 节点五：国风发型/发饰提示词生成器

分类 `Mate/国风`。结构与捏脸提示词生成器一致，同样输出 `prompt_zh` / `prompt_en` / `tags_en` 三路提示词。

### 标签顺序

1. **性别**：男性发型 / 女性发型
2. **朝代**：汉代发型、魏晋南北朝发型、唐代发型、宋代发型、明代发型、清代发型、民国发型、仙侠玄幻发型、架空古风发型
3. **发型**：按朝代覆盖的高髻、盘发、低髻、双丫髻，唐代堕马髻 / 双环望仙髻 / 灵蛇髻 / 凌云髻 / 十字髻 / 倭堕髻 / 飞仙髻，宋代包髻 / 冠梳，明代䯼髻 / 圆髻满插簪钗，清代两把头 / 大拉翅 / 钿子 / 燕尾，民国手推波纹与仙侠披发等
4. **配饰**：步摇、金步摇、簪、钗、珠钗、珍珠发饰、凤冠、花冠、簪花、花钿、额黄、面帘、发带丝绦、流苏、玉簪、点翠、梳篦等
5. **发丝质感**：顺滑、柔顺垂坠、蓬松轻盈、松散碎发、风吹飘动、缎面光泽、微卷蓬松
6. **气质**：端庄典雅、温婉柔美、清冷出尘、雍容华贵、英气飒爽、仙气飘飘等
7. **其他**：自由文本输入，可配合「翻译其他为英文」开关

### 性别联动

选择「男性发型」时，朝代后的发型、配饰、发丝质感、气质下拉框只列出男性选项；切换到「女性发型」后立即切换为女性选项。

切换性别时，若已选值不属于新性别，会自动回落到该标签的「（不使用）」。已保存的工作流重新加载时，会按保存的性别恢复对应的选项列表。

### 输出示例

| 输出口 | 示例 |
|---|---|
| `prompt_zh` | `[朝代]唐代发型`<br>`[发型]唐代飞仙髻，高耸的环状发髻向上翻卷，发丝如云，两侧垂落飘带`<br>`[配饰]金步摇，鎏金垂珠步摇，华贵夺目`<br>`[发丝质感]顺滑长发，发丝根根分明，自然光泽`<br>`[气质]端庄典雅，举止克制，仪态大方` |
| `prompt_en` | `[Dynasty]Tang dynasty style`<br>`[Hairstyle]flying-immortal bun, towering looped coifs sweeping upward, cloud-like hair, ribbons falling on both sides`<br>`[Hair Ornament]gold buyao hairpin, gilded dangling hairpin with hanging beads`<br>`[Hair Texture]silky hair with detailed strands and natural gloss` |
| `tags_en` | `tang dynasty, ancient chinese historical style, flying immortal bun, high looped bun, gold buyao hairpin, gilded hairpin, silky hair, detailed hair strands, dignified, elegant` |

## 节点六：文本换行连接

分类 `utils/text`。用于把多个节点生成的提示词合成一段完整文本，例如把捏脸提示词的输出和国风发型提示词的输出连接起来。

- **动态输入口**：初始只有一个 `文本 1` 输入端口；每接入一段文本，下方自动增加一个备用输入端口
- **顺序拼接**：按 `文本 1`、`文本 2`、`文本 3` … 的顺序，用换行符连接
- **空文本忽略**：未连接或内容为空的输入不会产生多余空行
- **上限**：最多 20 段文本同时接入
- 输出口 `文本`（STRING），可直接连接到 CLIP 文本编码等后续节点

> 输入端的显示名称由前端扩展维护，后端实际输入键为 `text_1` 到 `text_20`；断开某个连接后，其余已连接文本不会被删除。

## 自定义标签

所有标签定义集中在 [nodes.py](nodes.py)（捏脸）与 [guofeng_hairstyle.py](guofeng_hairstyle.py)（国风发型）的 `TAGS` 列表中，数据结构为三元组：

```python
("中文选项", "英文长句", "SD 短 tag")
```

捏脸节点在 `TAGS` 中追加带 `options` 的字典即可自动出现在节点界面：

```python
{
    "zh": "新标签", "en": "New Tag",
    "options": [
        ("选项一", "option one description", "option one tag"),
        (_SKIP, None, None),   # 默认「（不使用）」
    ],
},
```

国风发型节点按性别分组，每个标签使用 `male` / `female` 两份列表：

```python
{"zh": "朝代", "en": "Dynasty", "male": DYNASTY, "female": DYNASTY},
```

## 环境要求

- ComfyUI（Python 3.9+）
- 跨平台：Windows / Linux / macOS
- 翻译功能额外需要：`transformers`、`sentencepiece`、`sacremoses`（会自动安装）

## 许可

自由使用与修改。
