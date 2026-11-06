import torch
import torch.nn.functional as F


def gaussian_kernel1d(kernel_size, sigma, device, dtype):
    x = torch.arange(kernel_size, device=device, dtype=dtype) - (kernel_size - 1) / 2
    k = torch.exp(-x * x / (2 * sigma * sigma))
    return k / k.sum()


def apply_blur(image, strength):
    b, h, w, c = image.shape
    x = image.permute(0, 3, 1, 2)
    kernel_size = max(3, int(round(strength * 30)) | 1)
    sigma = max(0.3, strength * 8.0)
    k = gaussian_kernel1d(kernel_size, sigma, x.device, x.dtype)
    pad = kernel_size // 2
    kh = k.view(1, 1, 1, kernel_size).expand(c, 1, 1, kernel_size)
    kv = k.view(1, 1, kernel_size, 1).expand(c, 1, kernel_size, 1)
    x = F.conv2d(F.pad(x, (pad, pad, 0, 0), mode="reflect"), kh, groups=c)
    x = F.conv2d(F.pad(x, (0, 0, pad, pad), mode="reflect"), kv, groups=c)
    return x.permute(0, 2, 3, 1)


def apply_noise(image, strength):
    return (image + torch.randn_like(image) * (strength * 0.25)).clamp(0.0, 1.0)


class ImageBlurNoise:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "blur_strength": ("FLOAT", {"default": 0.1, "min": 0.0, "max": 1.0, "step": 0.01}),
                "noise_strength": ("FLOAT", {"default": 0.1, "min": 0.0, "max": 1.0, "step": 0.01}),
                "blur_first": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "apply"
    CATEGORY = "image/effects"

    def apply(self, image, blur_strength, noise_strength, blur_first):
        out = image
        ops = []
        if blur_strength > 0:
            ops.append(lambda x: apply_blur(x, blur_strength))
        if noise_strength > 0:
            ops.append(lambda x: apply_noise(x, noise_strength))
        if not blur_first:
            ops.reverse()
        for op in ops:
            out = op(out)
        return (out,)


NODE_CLASS_MAPPINGS = {"ImageBlurNoise": ImageBlurNoise}
NODE_DISPLAY_NAME_MAPPINGS = {"ImageBlurNoise": "Image Blur + Noise"}
