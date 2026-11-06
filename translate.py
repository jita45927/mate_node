"""本地离线翻译模块（transformers + Helsinki-NLP/opus-mt-zh-en）

仅用于"其他"自由文本的翻译；预设标签使用 nodes.py 中预置的英文。
特点：
- 依赖缺失时自动 pip 安装（每会话一次）；模型经 hf-mirror.com 镜像下载（国内可直连），首次约 300MB，之后完全离线
- 强制 CPU 推理，不占用显卡显存
- 懒加载：第一次真正翻译时才下载/加载模型，不影响节点启动速度
- 内存缓存：相同文本不重复翻译
- 失败回退：依赖缺失 / 下载失败 / 翻译异常时返回原文，节点不崩溃
"""

_MODEL_ID = "Helsinki-NLP/opus-mt-zh-en"
_HF_MIRROR = "https://hf-mirror.com"
_MAX_LEN = 512
_PIP_PACKAGES = ["transformers", "sentencepiece", "sacremoses"]

_CACHE = {}
_MODEL = None
_TOKENIZER = None
_INIT_ERROR = None
_PIP_TRIED = False


def _ensure_dependencies():
    """导入翻译依赖；缺失时自动 pip 安装（每次会话仅尝试一次）"""
    global _INIT_ERROR, _PIP_TRIED

    def _try_import():
        import torch  # noqa: F401
        import huggingface_hub  # noqa: F401
        import transformers  # noqa: F401

    try:
        _try_import()
        return True
    except ImportError:
        pass

    if _PIP_TRIED:
        return False
    _PIP_TRIED = True

    print(f"[mate_node] 缺少翻译依赖，正在自动安装: {' '.join(_PIP_PACKAGES)} ...")
    try:
        import importlib
        import subprocess
        import sys

        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", *_PIP_PACKAGES,
             "--disable-pip-version-check", "--quiet"],
            timeout=600,
        )
        importlib.invalidate_caches()
        _try_import()
        print("[mate_node] 翻译依赖自动安装完成")
        return True
    except Exception as e:
        _INIT_ERROR = (
            f"依赖自动安装失败: {e}，请手动在 ComfyUI 的 venv 中执行: "
            f"pip install {' '.join(_PIP_PACKAGES)}"
        )
        print(f"[mate_node] {_INIT_ERROR}")
        return False


def _load_model():
    """懒加载翻译模型与分词器；失败时记录原因并返回 False"""
    global _MODEL, _TOKENIZER, _INIT_ERROR
    if _MODEL is not None and _TOKENIZER is not None:
        return True
    if _INIT_ERROR is not None:
        return False

    if not _ensure_dependencies():
        return False

    try:
        from huggingface_hub import snapshot_download
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    except ImportError:
        return False

    try:
        print(f"[mate_node] 正在加载本地翻译模型 {_MODEL_ID}"
              "（首次经 hf-mirror 下载约 300MB，之后离线可用）...")
        # huggingface_hub 的镜像地址在库导入时已固定，
        # 因此通过 snapshot_download 的 endpoint 参数显式指定镜像，
        # 下载完成后从本地目录加载，不再访问网络
        model_dir = snapshot_download(repo_id=_MODEL_ID, endpoint=_HF_MIRROR)
        _TOKENIZER = AutoTokenizer.from_pretrained(model_dir)
        _MODEL = AutoModelForSeq2SeqLM.from_pretrained(model_dir)
        _MODEL.eval()  # 始终留在 CPU，不占用显存
        print("[mate_node] 本地翻译模型已加载（CPU 模式）")
        return True
    except Exception as e:
        _INIT_ERROR = f"翻译模型初始化失败: {e}"
        print(f"[mate_node] {_INIT_ERROR}，将输出原文")
        _MODEL = None
        _TOKENIZER = None
        return False


def contains_chinese(text):
    return any("\u4e00" <= c <= "\u9fff" for c in text)


def translate_zh_to_en(text):
    """中文 -> 英文；任何失败都回退为原文"""
    text = text.strip()
    if not text:
        return text
    if text in _CACHE:
        return _CACHE[text]

    if not _load_model():
        return text

    try:
        import torch

        inputs = _TOKENIZER(
            text, return_tensors="pt", truncation=True, max_length=_MAX_LEN
        )
        with torch.no_grad():
            outputs = _MODEL.generate(**inputs, max_length=_MAX_LEN)
        result = _TOKENIZER.decode(outputs[0], skip_special_tokens=True).strip() or text
    except Exception as e:
        print(f"[mate_node] 翻译失败，使用原文: {e}")
        return text

    _CACHE[text] = result
    return result
