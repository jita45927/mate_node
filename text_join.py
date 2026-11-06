"""Mate Node - 文本换行连接节点

将多个文本输入按顺序换行拼接为一个完整文本。
前端会在连接一个输入后自动显示下一个备用输入端口。
"""

MAX_TEXT_INPUTS = 20


class TextJoinNode:
    """文本换行连接：多个文本输入，按顺序换行合并"""

    @classmethod
    def INPUT_TYPES(cls):
        optional = {}
        for i in range(1, MAX_TEXT_INPUTS + 1):
            optional[f"text_{i}"] = ("STRING", {"forceInput": True})
        return {"required": {}, "optional": optional}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("文本",)
    FUNCTION = "join"
    CATEGORY = "utils/text"
    DESCRIPTION = "将多个文本输入按顺序换行连接成一个完整文本，连接一个后自动出现下一个输入端口"

    def join(self, **kwargs):
        parts = []
        for i in range(1, MAX_TEXT_INPUTS + 1):
            value = kwargs.get(f"text_{i}")
            if value is None:
                continue
            value = str(value).strip()
            if value:
                parts.append(value)
        return ("\n".join(parts),)


NODE_CLASS_MAPPINGS = {
    "MateTextJoin": TextJoinNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MateTextJoin": "文本换行连接 (Mate)",
}
