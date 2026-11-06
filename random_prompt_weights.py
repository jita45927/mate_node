"""随机提示词权重：按逗号拆分提示词，为每个片段随机分配权重

移入 mate_node 包时由 V3（comfy_api）注册方式改写为 V1（NODE_CLASS_MAPPINGS）方式，
因为 ComfyUI 加载包时 V1 分支优先，同一包内不能混用两种注册入口。
节点的参数、默认值与分配逻辑保持不变。
"""

import random
import re

# 已有强调/权重语法，或 LoRA 等尖括号标签的片段不重复打权重
_SKIP_SEGMENT = re.compile(r"[()\[\]]|<[^<>]+>")


def _parse_excluded(text: str) -> set[str]:
    return {part.strip().lower() for part in text.split(",") if part.strip()}


def _assign_weights(text: str, rng: random.Random, weight_min: float, weight_max: float, excluded: set[str]) -> str:
    out_lines = []
    for line in text.split("\n"):
        parts = []
        for part in line.split(","):
            stripped = part.strip()
            if not stripped or stripped == "BREAK" or _SKIP_SEGMENT.search(stripped) or stripped.lower() in excluded:
                parts.append(part)
                continue
            leading = part[: len(part) - len(part.lstrip())]
            trailing = part[len(part.rstrip()) :]
            weight = round(rng.uniform(weight_min, weight_max), 2)
            parts.append(f"{leading}({stripped}:{weight}){trailing}")
        out_lines.append(",".join(parts))
    return "\n".join(out_lines)


class RandomPromptWeights:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"default": "", "multiline": True}),
                "weight_min": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 10.0, "step": 0.01}),
                "weight_max": ("FLOAT", {"default": 1.3, "min": 0.0, "max": 10.0, "step": 0.01}),
                "exclude": ("STRING", {"default": "", "multiline": False}),
                "seed": (
                    "INT",
                    {
                        "default": -1,
                        "min": -1,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "control_after_generate": True,
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("加权文本",)
    FUNCTION = "execute"
    CATEGORY = "utils/text"
    DESCRIPTION = "按逗号拆分提示词，为每个片段随机分配权重，文本内容不变。seed 为 -1 时每次运行权重都不同；设为固定值可复现。"

    @classmethod
    def IS_CHANGED(cls, text, weight_min, weight_max, exclude, seed):
        # seed < 0 时每次运行结果都不同，跳过缓存
        if seed < 0:
            return float("nan")
        return ""

    def execute(self, text, weight_min, weight_max, exclude, seed):
        rng = random.Random(seed) if seed >= 0 else random.Random()
        return (_assign_weights(text, rng, weight_min, weight_max, _parse_excluded(exclude)),)


NODE_CLASS_MAPPINGS = {"RandomPromptWeights": RandomPromptWeights}
NODE_DISPLAY_NAME_MAPPINGS = {"RandomPromptWeights": "随机提示词权重"}
