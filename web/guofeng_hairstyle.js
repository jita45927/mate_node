import { app } from "../../scripts/app.js";

const NODE_NAME = "MateGuofengHairstylePromptBuilder";
const GENDER_WIDGET = "性别";
const FEMALE_VALUE = "女性发型";

// 从节点输入定义中读取后端注入的性别分组选项
let genderSpec = null;

function extractGenderSpec(nodeData) {
	const required = nodeData?.input?.required || {};
	const spec = {};
	for (const [name, def] of Object.entries(required)) {
		// 兼容旧版 [type, options] 数组与新版对象两种输入定义
		const opts = Array.isArray(def) ? def[1] : def;
		if (!opts) continue;
		if (!Array.isArray(opts.mate_male) || !Array.isArray(opts.mate_female)) continue;
		spec[name] = { male: opts.mate_male, female: opts.mate_female };
	}
	return spec;
}

function getWidget(node, name) {
	return node.widgets?.find((w) => w.name === name);
}

function applyGender(node) {
	if (!genderSpec) return;
	const genderWidget = getWidget(node, GENDER_WIDGET);
	if (!genderWidget) return;
	const isFemale = genderWidget.value === FEMALE_VALUE;

	for (const [name, groups] of Object.entries(genderSpec)) {
		if (name === GENDER_WIDGET) continue;
		const widget = getWidget(node, name);
		if (!widget) continue;
		const values = isFemale ? groups.female : groups.male;
		if (!values.length) continue;
		if (widget.options?.values === values) continue;

		widget.options = widget.options || {};
		widget.options.values = values;
		// 当前值不属于新性别列表时，回落到该列表第一项（默认「不使用」）
		if (!values.includes(widget.value)) {
			widget.value = values[0];
		}
	}
	node.setDirtyCanvas?.(true, true);
}

function setupNode(node) {
	const genderWidget = getWidget(node, GENDER_WIDGET);
	if (genderWidget) {
		const prev = genderWidget.callback;
		genderWidget.callback = function () {
			const res = prev?.apply(this, arguments);
			applyGender(node);
			return res;
		};
	}

	// 新版前端通过 onWidgetChanged 派发变更，callback 不一定被调用
	const prevChanged = node.onWidgetChanged;
	node.onWidgetChanged = function (name, ...rest) {
		prevChanged?.apply(this, [name, ...rest]);
		if (name === GENDER_WIDGET) applyGender(node);
	};

	applyGender(node);
}

app.registerExtension({
	name: "Mate.GuofengHairstyle",
	async beforeRegisterNodeDef(nodeType, nodeData) {
		if (nodeData.name !== NODE_NAME) return;

		genderSpec = extractGenderSpec(nodeData);

		const onNodeCreated = nodeType.prototype.onNodeCreated;
		nodeType.prototype.onNodeCreated = function () {
			const res = onNodeCreated?.apply(this, arguments);
			setupNode(this);
			return res;
		};

		const onConfigure = nodeType.prototype.onConfigure;
		nodeType.prototype.onConfigure = function () {
			const res = onConfigure?.apply(this, arguments);
			// 恢复保存的性别后，重新过滤其余标签的可选项
			applyGender(this);
			return res;
		};
	},
});
