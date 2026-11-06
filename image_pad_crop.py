"""Mate Node - 加载图像外补/裁剪节点

节点内直接加载图片，矩形区域由前端「外补画板」编辑（坐标为原图像素，允许负值）。
输出尺寸 = 矩形尺寸：
- 矩形大于原图    -> 空白处为外补区域
- 矩形在原图内部  -> 纯裁剪
- 矩形与原图交叉  -> 既有外补又有裁剪
"""

import hashlib
import os

import numpy as np
import torch
from PIL import Image, ImageOps

import folder_paths

try:
    from nodes import MAX_RESOLUTION
except Exception:
    MAX_RESOLUTION = 16384

# 背景填充色（RGB，0~1）
FILL_COLORS = {
    "白色": (1.0, 1.0, 1.0),
    "黑色": (0.0, 0.0, 0.0),
    "红色": (1.0, 0.0, 0.0),
    "绿色": (0.0, 1.0, 0.0),
    "蓝色": (0.0, 0.0, 1.0),
}
BACKGROUND_OPTIONS = ["无", "白色", "黑色", "红色", "绿色", "蓝色"]


class MateImagePadCrop:
    """加载图像后按矩形区域外补 / 裁剪"""

    @classmethod
    def INPUT_TYPES(cls):
        input_dir = folder_paths.get_input_directory()
        files = [
            f for f in os.listdir(input_dir)
            if os.path.isfile(os.path.join(input_dir, f))
        ]
        files = folder_paths.filter_files_content_types(files, ["image"])
        return {
            "required": {
                "图像": (sorted(files), {"image_upload": True}),
                "启用长边": ("BOOLEAN", {"default": False}),
                "长边": ("INT", {"default": 1024, "min": 1, "max": MAX_RESOLUTION, "step": 1}),
                "背景填充": (BACKGROUND_OPTIONS, {"default": "无"}),
                # 以下四项由前端画板写入，界面中隐藏
                "x": ("INT", {"default": 0, "min": -MAX_RESOLUTION, "max": MAX_RESOLUTION, "step": 1}),
                "y": ("INT", {"default": 0, "min": -MAX_RESOLUTION, "max": MAX_RESOLUTION, "step": 1}),
                "宽": ("INT", {"default": 512, "min": 1, "max": MAX_RESOLUTION, "step": 1}),
                "高": ("INT", {"default": 512, "min": 1, "max": MAX_RESOLUTION, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK", "INT", "INT")
    RETURN_NAMES = ("image", "mask", "width", "height")
    FUNCTION = "execute"
    CATEGORY = "Mate/image"
    DESCRIPTION = "按画板矩形对图像外补或裁剪，输出图像、外补遮罩与最终像素尺寸"

    @classmethod
    def IS_CHANGED(cls, 图像, **kwargs):
        image_path = folder_paths.get_annotated_filepath(图像)
        m = hashlib.md5()
        with open(image_path, "rb") as f:
            m.update(f.read())
        return m.digest().hex()

    def execute(self, 图像, 启用长边, 长边, 背景填充, x, y, 宽, 高):
        image_path = folder_paths.get_annotated_filepath(图像)
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"找不到图像文件: {image_path}")

        img = ImageOps.exif_transpose(Image.open(image_path))
        transparent = 背景填充 == "无"
        img = img.convert("RGBA" if transparent else "RGB")

        src = torch.from_numpy(
            np.asarray(img).astype(np.float32) / 255.0
        )[None]  # [1, H, W, C]
        src_h, src_w = src.shape[1], src.shape[2]

        # 防御性钳制：前端已限制，但手改工作流 JSON 仍可能传入非法值
        rect_w = max(1, int(宽))
        rect_h = max(1, int(高))
        out_ch = 4 if transparent else 3

        # 输出画布 (尺寸 = 矩形尺寸)
        canvas = torch.zeros((1, rect_h, rect_w, out_ch), dtype=torch.float32)
        if not transparent:
            canvas[..., :3] = torch.tensor(
                FILL_COLORS.get(背景填充, (0.0, 0.0, 0.0)), dtype=torch.float32
            )

        # 矩形与原图的交叠区（矩形坐标系）
        sx0 = max(0, int(x))
        sx1 = min(src_w, int(x) + rect_w)
        sy0 = max(0, int(y))
        sy1 = min(src_h, int(y) + rect_h)
        dx = sx0 - int(x)
        dy = sy0 - int(y)

        mask = torch.ones((1, rect_h, rect_w), dtype=torch.float32)
        if sx1 > sx0 and sy1 > sy0:
            patch = src[:, sy0:sy1, sx0:sx1, :]
            if out_ch == 3:
                patch = patch[..., :3]
            elif patch.shape[-1] == 3:
                alpha = torch.ones((*patch.shape[:-1], 1), dtype=torch.float32)
                patch = torch.cat([patch, alpha], dim=-1)
            w_len = sx1 - sx0
            h_len = sy1 - sy0
            canvas[:, dy:dy + h_len, dx:dx + w_len, :] = patch
            mask[:, dy:dy + h_len, dx:dx + w_len] = 0.0

        # 长边缩放（在外补/裁剪之后，保持宽高比）
        if 启用长边:
            target = max(1, int(长边))
            if rect_w >= rect_h:
                new_w = target
                new_h = max(1, round(rect_h * target / rect_w))
            else:
                new_h = target
                new_w = max(1, round(rect_w * target / rect_h))

            canvas = torch.nn.functional.interpolate(
                canvas.permute(0, 3, 1, 2),
                size=(new_h, new_w),
                mode="bilinear",
                align_corners=False,
            ).permute(0, 2, 3, 1).clamp(0.0, 1.0)

            scaled = torch.nn.functional.interpolate(
                mask[:, None],
                size=(new_h, new_w),
                mode="bilinear",
                align_corners=False,
            )[:, 0]
            # 二值化，保持外补边界清晰
            mask = (scaled > 0.5).float()
        else:
            new_w, new_h = rect_w, rect_h

        return (canvas.contiguous(), mask.contiguous(), new_w, new_h)


NODE_CLASS_MAPPINGS = {
    "MateImagePadCrop": MateImagePadCrop,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MateImagePadCrop": "加载图像外补/裁剪 (Mate)",
}
