import { app } from "../../scripts/app.js";

/**
 * MatePromptExtractor 前端扩展
 *
 * 问题：遮罩编辑器保存后，会把 image 控件的值替换为 clipspace-painted-masked-*.png，
 * 该图片是重新编码的 PNG，不包含原始工作流元数据，导致提示词解析失败。
 *
 * 方案：监听 image 控件的值变化，把"非遮罩编辑器产物"的图片记录到隐藏控件
 * prompt_source 中。当 image 变成 painted-masked 图时，prompt_source 保持不变，
 * 后端即可从 prompt_source 回退提取提示词。
 */

const NODE_NAME = "MatePromptExtractor";
const IMAGE_WIDGET = "image";
const SOURCE_WIDGET = "prompt_source";

// 遮罩编辑器生成的图片前缀（这些图片不含工作流元数据）
const MASK_EDITOR_PREFIXES = [
	"clipspace-painted-masked-",
	"clipspace-painted-",
	"clipspace-paint-",
	"clipspace-mask-",
];

/** 去掉 "filename [input]" 中的类型后缀，返回纯文件名 */
function stripAnnotation(value) {
	if (typeof value !== "string") return "";
	// 匹配末尾的 " [input]" / " [output]" / " [temp]"
	return value.replace(/\s*\[(input|output|temp)\]\s*$/i, "").trim();
}

/** 判断图片是否为遮罩编辑器产物（无元数据） */
function isMaskEditorOutput(value) {
	const name = stripAnnotation(value);
	return MASK_EDITOR_PREFIXES.some((p) => name.startsWith(p));
}

app.registerExtension({
	name: "Mate.PromptExtractor",

	nodeCreated(node) {
		if (node.comfyClass !== NODE_NAME) return;

		const imageWidget = node.widgets?.find((w) => w.name === IMAGE_WIDGET);
		const sourceWidget = node.widgets?.find((w) => w.name === SOURCE_WIDGET);

		if (!imageWidget || !sourceWidget) return;

		// 隐藏 prompt_source 控件，用户无需手动操作
		sourceWidget.options = sourceWidget.options || {};
		sourceWidget.options.serialize = true; // 必须序列化才能传给后端
		Object.defineProperty(sourceWidget, "hidden", {
			get: () => true,
			configurable: true,
		});
		// 某些版本用 options.hideOnZoom / hidden 控制可见性
		sourceWidget.options.hideOnZoom = true;

		/** 用当前 image 值更新 prompt_source（仅当不是遮罩编辑器产物时） */
		function syncSource() {
			const val = imageWidget.value;
			if (val && !isMaskEditorOutput(val)) {
				sourceWidget.value = val;
			}
			// 若是遮罩编辑器产物，保持原有的 prompt_source 不变
		}

		// 初始化：若已有 image 值且不是遮罩产物，同步到 source
		syncSource();

		// 劫持 image 控件的 callback：值变化时判断是否更新 source
		const origCallback = imageWidget.callback;
		imageWidget.callback = function (v) {
			syncSource();
			if (typeof origCallback === "function") {
				try {
					return origCallback.apply(this, arguments);
				} catch (e) {
					/* ignore */
				}
			}
		};

		// 同时劫持 value setter，兼容直接赋值的情况（如遮罩编辑器 writeImageWidgetValue）
		const valueDesc = Object.getOwnPropertyDescriptor(imageWidget, "value");
		const hasAccessor = valueDesc && (valueDesc.get || valueDesc.set);

		if (!hasAccessor) {
			let _val = imageWidget.value;
			Object.defineProperty(imageWidget, "value", {
				get() {
					return _val;
				},
				set(v) {
					_val = v;
					syncSource();
				},
				configurable: true,
			});
		}
	},
});
