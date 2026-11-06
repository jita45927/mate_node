"""Mate Node - 从图片提取工作流原始提示词

ComfyUI 生成的图片（PNG）内嵌了完整工作流信息（prompt / workflow 字段）。
本节点读取这些元数据，回溯 CLIPTextEncode 节点的 text 输入，
还原图片进入 CLIP 文本编码器之前的原始提示词，无论提示词是直接输入、
由文本拼接节点、反推节点还是其他文本处理节点生成的。
"""

import json
import os
import struct
import zlib

import numpy as np
import torch
from PIL import Image, ImageOps

import folder_paths


# ---------------------------------------------------------------------------
# PNG 元数据解析
# ---------------------------------------------------------------------------

def _read_png_text_chunks(filepath):
    """手动解析 PNG 的 tEXt / iTXt 块，返回 {keyword: value} 字典。

    不依赖 PIL 的 info（它在某些版本下会丢失多块或长文本），直接读二进制块更可靠。
    """
    with open(filepath, "rb") as f:
        sig = f.read(8)
        if sig != b"\x89PNG\r\n\x1a\n":
            return {}
        result = {}
        while True:
            header = f.read(8)
            if len(header) < 8:
                break
            length = struct.unpack(">I", header[:4])[0]
            chunk_type = header[4:8]
            data = f.read(length) if length else b""
            f.read(4)  # CRC
            if chunk_type == b"tEXt":
                # keyword\x00text
                if b"\x00" in data:
                    keyword, text = data.split(b"\x00", 1)
                    try:
                        result[keyword.decode("latin-1")] = text.decode("latin-1")
                    except UnicodeDecodeError:
                        pass
            elif chunk_type == b"iTXt":
                # keyword\x00 compression_flag compression_method lang\x00 translated_keyword\x00 text
                try:
                    parts = data.split(b"\x00", 5)
                    if len(parts) >= 6:
                        keyword = parts[0].decode("latin-1")
                        comp_flag = parts[1][0] if len(parts[1]) else 0
                        text = parts[5]
                        if comp_flag:
                            text = zlib.decompress(text)
                        result[keyword] = text.decode("utf-8", errors="replace")
                except Exception:
                    pass
            elif chunk_type == b"IEND":
                break
        return result


def _read_image_metadata(filepath):
    """读取图片内嵌的工作流元数据，返回 (prompt_dict, workflow_dict, raw_meta)。

    优先手动解析 PNG 块；若失败则回退 PIL.info。
    """
    ext = os.path.splitext(filepath)[1].lower()
    raw = {}

    if ext in (".png",):
        raw = _read_png_text_chunks(filepath)
        if not raw:
            try:
                img = Image.open(filepath)
                raw = dict(img.info)
            except Exception:
                raw = {}
    else:
        # JPEG / WebP 等：尝试从 EXIF 的 UserComment 读取（ComfyUI 部分版本会写入）
        try:
            img = Image.open(filepath)
            raw = dict(img.info)
            exif = img._getexif() if hasattr(img, "_getexif") else None
            if exif:
                # 0x9286 = UserComment
                uc = exif.get(0x9286)
                if uc and isinstance(uc, (bytes, bytearray)):
                    try:
                        # 前 8 字节为字符编码标识，去除后解码
                        payload = bytes(uc)[8:]
                        raw["__exif_usercomment"] = payload.decode("utf-8", errors="replace")
                    except Exception:
                        pass
        except Exception:
            raw = {}

    prompt_data = None
    workflow_data = None

    for key in ("prompt",):
        if key in raw and raw[key]:
            try:
                prompt_data = json.loads(raw[key])
            except (json.JSONDecodeError, TypeError):
                pass

    for key in ("workflow", "Workflow"):
        if key in raw and raw[key]:
            val = raw[key]
            # 某些版本 workflow 是 base64 + gzip
            try:
                workflow_data = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                try:
                    import base64
                    decompressed = zlib.decompress(base64.b64decode(val))
                    workflow_data = json.loads(decompressed)
                except Exception:
                    workflow_data = None

    return prompt_data, workflow_data, raw


# ---------------------------------------------------------------------------
# 工作流回溯：找到进入 CLIP 文本编码器的原始提示词
# ---------------------------------------------------------------------------

# 会输出文本/字符串的节点中常见的文本字段名（按优先级）
_TEXT_FIELDS = (
    "value",          # PrimitiveString / PrimitiveNode / Text 节点
    "string",         # 部分自定义文本节点
    "text",           # 通用文本输入
    "f_string",       # StringFormat 格式化模板
    "content",        # 部分节点
    "text_input",
    "prompt",
    "input",
)


def _is_text_value(val):
    return isinstance(val, str)


def _resolve_ref(ref, prompt_data, seen=None):
    """解析 [node_id, output_slot] 引用，返回该节点输出的文本。"""
    if seen is None:
        seen = set()
    if not isinstance(ref, list) or len(ref) < 1:
        return None
    node_id = str(ref[0])
    if node_id in seen:
        return None  # 防止环
    seen.add(node_id)
    node = prompt_data.get(node_id)
    if not node:
        return None
    return _resolve_node_text(node, node_id, prompt_data, seen)


def _resolve_node_text(node, node_id, prompt_data, seen):
    """尝试从一个节点还原其文本输出。

    策略：
    1. Reroute 节点：直接回溯其唯一输入
    2. 常见文本字段（value / string / text ...）直接取值或递归解析（跳过空值）
    3. text_N 多输入模式（如文本换行连接节点）→ 全部解析后用换行拼接
    4. text_a / text_b + separator 或 string_a / string_b + delimiter → 拼接
    5. text1 / text2 数字后缀模式 → 依次拼接
    6. 兜底：所有非空字符串字面量输入拼接
    7. 实在无法还原时返回占位说明
    """
    inputs = node.get("inputs", {}) or {}
    class_type = node.get("class_type", "")

    # 1. Reroute 节点：直接回溯其输入
    if isinstance(class_type, str) and "reroute" in class_type.lower():
        for val in inputs.values():
            if isinstance(val, list) and val:
                return _resolve_ref(val, prompt_data, seen)

    # 2. 单字段常见模式（跳过空字符串）
    for field in _TEXT_FIELDS:
        if field in inputs:
            val = inputs[field]
            if _is_text_value(val):
                if val.strip():
                    return val
                continue  # 空字符串，尝试下一个字段
            if isinstance(val, list) and val:
                resolved = _resolve_ref(val, prompt_data, seen)
                if resolved is not None and resolved.strip():
                    return resolved

    # 3. text_N 多输入（文本换行连接 / 多段拼接类节点）
    indexed = {}
    for k, v in inputs.items():
        if isinstance(k, str) and k.startswith("text_") and k[5:].isdigit():
            idx = int(k[5:])
            indexed[idx] = v
    if indexed:
        parts = []
        for idx in sorted(indexed):
            val = indexed[idx]
            if _is_text_value(val):
                if val.strip():
                    parts.append(val)
            elif isinstance(val, list):
                resolved = _resolve_ref(val, prompt_data, seen)
                if resolved and resolved.strip():
                    parts.append(resolved)
        if parts:
            return "\n".join(parts)

    # 4. text_a / text_b + separator 或 string_a / string_b + delimiter
    for a_field, b_field, sep_field in (("text_a", "text_b", "separator"),
                                        ("string_a", "string_b", "delimiter")):
        if a_field in inputs and b_field in inputs:
            parts = []
            for field in (a_field, b_field):
                val = inputs[field]
                if _is_text_value(val):
                    parts.append(val)
                elif isinstance(val, list):
                    r = _resolve_ref(val, prompt_data, seen)
                    if r is not None:
                        parts.append(r)
            sep = inputs.get(sep_field, "")
            if not isinstance(sep, str):
                sep = ""
            return sep.join(str(p) for p in parts if p is not None)

    # 5. text1 / text2 数字后缀
    numbered = {}
    for k, v in inputs.items():
        if isinstance(k, str) and k.startswith("text") and k[4:].isdigit():
            numbered[int(k[4:])] = v
    if numbered:
        parts = []
        for idx in sorted(numbered):
            val = numbered[idx]
            if _is_text_value(val):
                parts.append(val)
            elif isinstance(val, list):
                r = _resolve_ref(val, prompt_data, seen)
                if r is not None:
                    parts.append(r)
        if parts:
            return "".join(parts)

    # 6. 兜底：所有非空字符串字面量输入拼接
    literals = [v for v in inputs.values() if _is_text_value(v) and v.strip()]
    if literals:
        return "\n".join(literals)

    return f"[无法自动还原文本输出: {class_type}#{node_id}]"


def _is_text_encoder(class_type):
    if not isinstance(class_type, str):
        return False
    ct = class_type.lower()
    return ("cliptextencode" in ct) or ("textencode" in ct and "clip" in ct) or ct == "cliptextencode"


# CLIP 文本编码器的文本输入字段名（按优先级）
# text: 标准 CLIPTextEncode
# text_g / text_l: SDXL 双文本编码器
# prompt / string / value / text_input: 各种变体
_ENCODER_TEXT_FIELDS = ("text", "text_g", "text_l", "prompt", "string", "value", "text_input")


def _get_encoder_text_input(node):
    """从 CLIP 文本编码节点中取出文本输入（可能是字符串或引用列表）。"""
    inputs = node.get("inputs") or {}
    for field in _ENCODER_TEXT_FIELDS:
        if field in inputs and inputs[field] is not None:
            return inputs[field]
    return None


def _has_positive_negative_inputs(node):
    """判断节点是否同时具有 positive 和 negative 输入（可作为 conditioning 路由节点）。

    除了 KSampler 系列外，CFGGuider、Guider 等节点也具备 positive/negative，
    同样可用于判断正负向。
    """
    inputs = node.get("inputs") or {}
    return "positive" in inputs and "negative" in inputs


def _trace_to_encoders(node_id, prompt_data, result, seen):
    """从一个节点回溯，找到所有上游的 CLIP 文本编码节点 ID。

    用于追踪 KSampler.positive/negative 经过 ConditioningCombine 等中间节点
    最终到达 CLIPTextEncode 的链路。
    """
    if node_id in seen:
        return
    seen.add(node_id)
    node = prompt_data.get(node_id)
    if not node:
        return
    class_type = node.get("class_type", "")
    if _is_text_encoder(class_type):
        result.add(node_id)
        return
    # 非编码节点：回溯所有引用类型的输入
    for val in (node.get("inputs") or {}).values():
        if isinstance(val, list) and val:
            _trace_to_encoders(str(val[0]), prompt_data, result, seen)


def _find_encoder_ids_from_conditioning(cond_ids, prompt_data):
    """给定一组 conditioning 节点 ID，回溯找到所有上游 CLIPTextEncode 节点 ID。"""
    result = set()
    for cid in cond_ids:
        _trace_to_encoders(cid, prompt_data, result, set())
    return result


# ---------------------------------------------------------------------------
# 多分支消歧：基于图像颜色分布匹配提示词中的颜色关键词
# ---------------------------------------------------------------------------

# 颜色关键词 -> 代表性 RGB (用于与图像像素做容差匹配)
# 只包含真正的颜色词，不包含物体名（如"岗亭""建筑"虽带颜色但本质是物体）
_COLOR_KEYWORDS = {
    # 红色系
    "红色": (200, 30, 30), "红": (200, 30, 30), "red": (200, 30, 30),
    "深红": (130, 20, 20), "暗红": (100, 15, 15),
    "粉色": (230, 130, 160), "粉红": (230, 130, 160), "pink": (230, 130, 160),
    "桃红": (220, 100, 130), "玫红": (200, 50, 100), "magenta": (200, 50, 150),
    "橙色": (230, 140, 30), "橙": (230, 140, 30), "orange": (230, 140, 30),
    # 黄色系
    "黄色": (230, 210, 50), "黄": (230, 210, 50), "yellow": (230, 210, 50),
    "金色": (210, 170, 50), "金": (210, 170, 50), "gold": (210, 170, 50),
    # 绿色系
    "绿色": (50, 150, 50), "绿": (50, 150, 50), "green": (50, 150, 50),
    "深绿": (20, 90, 30), "墨绿": (20, 70, 40), "翠绿": (30, 160, 80),
    "草绿": (100, 170, 60), "青色": (30, 180, 170), "cyan": (30, 180, 170),
    # 蓝色系
    "蓝色": (40, 90, 180), "蓝": (40, 90, 180), "blue": (40, 90, 180),
    "深蓝": (20, 40, 120), "天蓝": (80, 160, 220), "sky": (80, 160, 220),
    "紫色": (130, 50, 160), "紫": (130, 50, 160), "purple": (130, 50, 160),
    # 棕/土色系
    "棕色": (120, 80, 50), "棕": (120, 80, 50), "brown": (120, 80, 50),
    "褐色": (110, 75, 45), "土色": (140, 110, 70), "卡其": (180, 160, 120),
    # 白/灰色系
    "白色": (230, 230, 230), "白": (230, 230, 230), "white": (230, 230, 230),
    "灰色": (150, 150, 150), "灰": (150, 150, 150), "gray": (150, 150, 150),
    "黑色": (30, 30, 30), "黑": (30, 30, 30), "black": (30, 30, 30),
    # 自然景物的典型颜色（作为颜色线索，非物体本身）
    "草坪": (80, 150, 50), "草地": (80, 150, 50),
    "江水": (40, 110, 160), "河水": (40, 110, 160), "湖水": (40, 110, 160),
    "海水": (30, 90, 140),
    "薄雾": (170, 180, 190), "雾": (160, 170, 180), "mist": (180, 190, 200),
    "樱花": (230, 150, 170), "梅花": (200, 60, 80),
}


def _extract_color_keywords(text):
    """从文本中提取颜色关键词，返回去重后的 [(keyword, rgb), ...]（按 RGB 去重）"""
    if not isinstance(text, str):
        return []
    tl = text.lower()
    seen_rgbs = set()
    found = []
    for kw, rgb in _COLOR_KEYWORDS.items():
        if kw.lower() in tl and rgb not in seen_rgbs:
            seen_rgbs.add(rgb)
            found.append((kw, rgb))
    return found


def _compute_color_presence(image, rgb_targets, tol=45):
    """计算图像中各目标颜色的像素占比，返回 {rgb_tuple: fraction}。"""
    if image is None:
        return {}
    try:
        from PIL import Image as PILImage
        if isinstance(image, PILImage.Image):
            arr = np.array(image.convert("RGB"))
        elif isinstance(image, np.ndarray):
            arr = image if image.ndim == 3 else np.stack([image] * 3, axis=-1)
            if arr.shape[-1] == 4:
                arr = arr[..., :3]
            arr = (arr * 255).astype(np.uint8) if arr.max() <= 1.0 else arr.astype(np.uint8)
        else:
            return {}
    except Exception:
        return {}

    if arr.size == 0:
        return {}
    pixels = arr.reshape(-1, 3).astype(np.int16)
    total = len(pixels)
    result = {}
    for rgb in rgb_targets:
        diff = np.abs(pixels - np.array(rgb, dtype=np.int16))
        mask = np.all(diff <= tol, axis=1)
        result[rgb] = np.sum(mask) / total
    return result


def _score_prompt_by_color(text, color_presence):
    """根据提示词中颜色关键词在图像中的实际占比打分（求和，鼓励更多匹配色）。"""
    keywords = _extract_color_keywords(text)
    if not keywords:
        return 0.0
    score = 0.0
    for kw, rgb in keywords:
        score += color_presence.get(rgb, 0.0)
    return score


def _disambiguate_prompts(prompts, image):
    """当存在多个候选提示词时，用颜色匹配选择与图像最相符的一个。

    若无法可靠区分（如没有颜色关键词或分数接近），则返回全部。
    """
    if len(prompts) <= 1 or image is None:
        return prompts

    # 收集所有候选提示词涉及的颜色
    all_rgbs = set()
    for p in prompts:
        for _, rgb in _extract_color_keywords(p):
            all_rgbs.add(rgb)

    if not all_rgbs:
        # 没有颜色关键词，无法消歧，返回全部
        return prompts

    color_presence = _compute_color_presence(image, list(all_rgbs))
    if not color_presence:
        return prompts

    scores = [_score_prompt_by_color(p, color_presence) for p in prompts]
    max_score = max(scores)
    if max_score <= 0:
        return prompts

    # 最高分的索引
    best_idx = scores.index(max_score)
    # 第二高分（若存在）
    others = [s for i, s in enumerate(scores) if i != best_idx]
    second_score = max(others) if others else 0.0

    # 只有当最高分明显高于第二分时才消歧（阈值 1.5 倍）
    if second_score > 0 and max_score < second_score * 1.5:
        return prompts

    return [prompts[best_idx]]


def extract_prompts_from_workflow(prompt_data, image=None):
    """从 API 工作流中提取正向 / 负向提示词。

    参数:
        prompt_data: 工作流的 API 格式字典
        image: 可选，PIL.Image 或 numpy 数组，用于多分支消歧。
               当存在多个生成分支时，通过颜色匹配选择与图片最相符的提示词。

    返回 (positive, negative, all_prompts)
    """
    if not isinstance(prompt_data, dict):
        return "", "", []

    # 第一步：找到所有文本编码节点并解析其文本输入
    encoders = {}  # node_id -> text
    for nid, node in prompt_data.items():
        class_type = node.get("class_type", "")
        if not _is_text_encoder(class_type):
            continue
        text_input = _get_encoder_text_input(node)
        if text_input is None:
            continue
        if _is_text_value(text_input):
            text = text_input
        elif isinstance(text_input, list) and text_input:
            text = _resolve_ref(text_input, prompt_data) or ""
        else:
            text = ""
        # 跳过空文本的编码器，避免污染正负向判断
        if text and text.strip():
            encoders[nid] = text

    # 第二步：通过具有 positive/negative 输入的节点（KSampler / CFGGuider / Guider 等）
    # 判断正负向。回溯 conditioning 中间节点到真正的 CLIPTextEncode。
    positive_cond_ids = set()
    negative_cond_ids = set()
    for nid, node in prompt_data.items():
        if not _has_positive_negative_inputs(node):
            continue
        inputs = node.get("inputs") or {}
        for key, target_set in (("positive", positive_cond_ids), ("negative", negative_cond_ids)):
            val = inputs.get(key)
            if isinstance(val, list) and val:
                target_set.add(str(val[0]))

    # 回溯到实际的 CLIPTextEncode 节点 ID
    positive_ids = _find_encoder_ids_from_conditioning(positive_cond_ids, prompt_data)
    negative_ids = _find_encoder_ids_from_conditioning(negative_cond_ids, prompt_data)

    positive_parts = []
    negative_parts = []
    others = []

    for nid, text in encoders.items():
        if nid in positive_ids:
            positive_parts.append(text)
        elif nid in negative_ids:
            negative_parts.append(text)
        else:
            others.append(text)

    # 若无法通过采样器/路由节点区分正负向，则根据文本内容启发式判断
    if not positive_parts and not negative_parts:
        neg_keywords = (
            "bad", "worst", "low quality", "lowres", "blurry", "ugly",
            "deformed", "disfigured", "extra limbs", "missing limbs",
            "watermark", "signature", "jpeg artifacts", "out of frame",
            "mutation", "duplicate", "nsfw", "nude",
        )
        all_texts = list(encoders.values())
        for t in all_texts:
            tl = t.lower()
            if any(kw in tl for kw in neg_keywords):
                negative_parts.append(t)
            else:
                positive_parts.append(t)

    # 第三步：若没有任何 CLIP 文本编码器（如直接用 prompt 字段驱动的模型，
    # 或文生图/图生图模型节点直接接收提示词），则回退到直接提示词节点。
    if not encoders:
        direct_prompts = _extract_direct_prompts(prompt_data)
        if direct_prompts:
            # 直接提示词全部归为正向（这类工作流通常无负向概念）
            positive_parts = direct_prompts

    # 第四步：多分支消歧。当存在多个候选正向提示词时（如工作流有多个生成分支），
    # 利用图像颜色分布与提示词颜色关键词匹配，选择最相符的提示词。
    if len(positive_parts) > 1 and image is not None:
        positive_parts = _disambiguate_prompts(positive_parts, image)

    positive = "\n".join(t for t in positive_parts if t)
    negative = "\n".join(t for t in negative_parts if t)
    # 合并所有提示词用于展示（去重）
    all_prompts = []
    seen_texts = set()
    for t in list(encoders.values()) + positive_parts + negative_parts:
        if t and t not in seen_texts:
            seen_texts.add(t)
            all_prompts.append(t)

    return positive, negative, all_prompts


# 直接提示词节点：模型节点或文本节点直接包含 prompt 文本输入


def _is_text_multiline_node(class_type):
    if not isinstance(class_type, str):
        return False
    ct = class_type.lower()
    return "text" in ct and ("multiline" in ct or "multiligne" in ct)


def _extract_direct_prompts(prompt_data):
    """当工作流中没有 CLIPTextEncode 时，从直接包含 prompt 文本的节点提取提示词。

    策略：
    1. 从 SaveImage 节点回溯，只提取连接到输出的生成分支的 prompt（过滤孤立节点）
    2. 若没有，则收集所有 Text Multiline 节点的文本
    """
    # 从所有 SaveImage 节点向上回溯，收集可达的带 prompt 输入的节点
    save_ids = [
        nid for nid, node in prompt_data.items()
        if node.get("class_type") == "SaveImage"
    ]

    prompts = []
    visited = set()
    for save_id in save_ids:
        stack = [save_id]
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            curnode = prompt_data.get(cur)
            if not curnode:
                continue
            inputs = curnode.get("inputs") or {}
            # 当前节点若有 prompt 输入，提取其文本
            if "prompt" in inputs:
                val = inputs["prompt"]
                if _is_text_value(val) and val.strip():
                    prompts.append(val)
                elif isinstance(val, list) and val:
                    resolved = _resolve_ref(val, prompt_data)
                    if resolved and resolved.strip():
                        prompts.append(resolved)
            # 继续向上回溯所有 list 引用输入
            for v in inputs.values():
                if isinstance(v, list) and v:
                    stack.append(str(v[0]))

    if prompts:
        return prompts

    # 兜底：收集所有 Text Multiline 节点的文本
    for nid, node in prompt_data.items():
        if not _is_text_multiline_node(node.get("class_type", "")):
            continue
        text = (node.get("inputs") or {}).get("text", "")
        if isinstance(text, str) and text.strip():
            prompts.append(text)

    return prompts


# ---------------------------------------------------------------------------
# ComfyUI 节点定义
# ---------------------------------------------------------------------------

class MatePromptExtractor:
    """从 ComfyUI 生成的图片中提取原始提示词（进入 CLIP 编码器之前的文本）。"""

    @classmethod
    def INPUT_TYPES(cls):
        # 同时列出 input 和 output 目录中的图片，方便从预览拖拽的图片也能被选中
        files = []
        for folder in (folder_paths.get_input_directory(), folder_paths.get_output_directory()):
            try:
                if os.path.isdir(folder):
                    for name in os.listdir(folder):
                        full = os.path.join(folder, name)
                        if os.path.isfile(full):
                            files.append(name)
            except Exception:
                pass
        files = folder_paths.filter_files_content_types(files, ["image"])
        # 去重并排序
        files = sorted(set(files))
        return {
            "required": {
                "image": (files, {"image_upload": True}),
            },
            "optional": {
                # 由前端扩展自动维护：记录带有工作流元数据的原始图片。
                # 当遮罩编辑器把 image 替换为无元数据的 painted-masked 图时，
                # 仍可从 prompt_source 提取提示词。用户无需手动设置。
                "prompt_source": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "IMAGE", "MASK")
    RETURN_NAMES = ("正向提示词", "负向提示词", "图像", "遮罩")
    FUNCTION = "extract"
    CATEGORY = "Mate/extract"
    DESCRIPTION = "加载一张 ComfyUI 生成的图片，提取其中内嵌工作流的原始正向/负向提示词（进入 CLIP 文本编码器之前的文本），并原样输出图像。"

    @classmethod
    def VALIDATE_INPUTS(cls, image):
        # 与原生 LoadImage 一致：用 annotated_filepath 校验，
        # 这样遮罩编辑器保存后产生的 "filename [input]" 形式也能通过校验，
        # 否则严格的 combo 校验会因后缀不在列表中而返回 400。
        # 当 image 来自上游节点连接时，值为 None，直接放行。
        if image is None:
            return True
        if not folder_paths.exists_annotated_filepath(image):
            return f"Invalid image file: {image}"
        return True

    def extract(self, image, prompt_source=""):
        # 使用 ComfyUI 自带的 annotated 路径解析，支持 "filename [input/output/temp]" 格式
        image_path = folder_paths.get_annotated_filepath(image)

        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"找不到图片文件: {image}，请确认文件存在于 input 或 output 目录中。")

        # 读取图片（保留 alpha 通道用于遮罩提取）
        img = Image.open(image_path)
        # 处理 EXIF 方向信息，与 LoadImage 一致
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        # 图像输出：转为 RGB（丢弃 alpha，避免透明通道干扰图像显示）
        img_rgb = img.convert("RGB")
        image_np = np.array(img_rgb).astype(np.float32) / 255.0
        image_tensor = torch.from_numpy(image_np)[None,]

        h, w = image_tensor.shape[1], image_tensor.shape[2]

        # 遮罩输出：与原生 LoadImage 一致，从 alpha 通道提取
        # 遮罩编辑器保存时会把遮罩写入 alpha 通道（绘制区域 alpha=0，未绘制区域 alpha=255）
        # 因此 mask = 1.0 - alpha，这样绘制区域为白色(1.0)，未绘制为黑色(0.0)
        if 'A' in img.getbands():
            alpha = np.array(img.getchannel('A')).astype(np.float32) / 255.0
            mask = 1.0 - torch.from_numpy(alpha)
        else:
            # 无 alpha 通道时输出全零遮罩（空白画布，供用户在遮罩编辑器中绘制）
            mask = torch.zeros((h, w), dtype=torch.float32)

        mask = mask.unsqueeze(0)  # MASK 输出形状为 [1, H, W]

        # 提取工作流元数据：优先从当前图片提取；
        # 若当前图片无元数据（如遮罩编辑器生成的 painted-masked 图），
        # 则回退到前端记录的原始图片 prompt_source。
        prompt_data, workflow_data, raw = _read_image_metadata(image_path)
        if not prompt_data and prompt_source:
            try:
                src_path = folder_paths.get_annotated_filepath(prompt_source)
                if os.path.isfile(src_path):
                    prompt_data, workflow_data, raw = _read_image_metadata(src_path)
            except Exception:
                pass

        positive, negative, all_prompts = extract_prompts_from_workflow(prompt_data, image=img)

        return (positive, negative, image_tensor, mask)


NODE_CLASS_MAPPINGS = {
    "MatePromptExtractor": MatePromptExtractor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MatePromptExtractor": "图片提示词提取 (Mate)",
}
