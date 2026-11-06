# Mate Node - 捏脸提示词生成器

ComfyUI 自定义节点包。通过下拉框选择各维度标签（每个标签预设多个选项），自动拼接为结构化提示词，同时输出**中文**、**英文**、**英文短 tag** 三种格式。

## 功能特点

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
├── translate.py
├── requirements.txt
└── README.md
```

节点位置：右键菜单 → **Mate/捏脸** → **捏脸提示词生成器 (Mate)**，或双击画布搜索「捏脸」。

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

## 自定义标签

所有标签定义集中在 [nodes.py](nodes.py) 的 `TAGS` 列表中，数据结构为三元组：

```python
("中文选项", "英文长句", "SD 短 tag")
```

新增标签时，在 `TAGS` 中追加一个字典即可自动出现在节点界面：

```python
{
    "zh": "新标签", "en": "New Tag",
    "options": [
        ("选项一", "option one description", "option one tag"),
        (_SKIP, None, None),   # 默认「（不使用）」
    ],
},
```

## 环境要求

- ComfyUI（Python 3.9+）
- 跨平台：Windows / Linux / macOS
- 翻译功能额外需要：`transformers`、`sentencepiece`、`sacremoses`（会自动安装）

## 许可

自由使用与修改。
