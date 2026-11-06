import { app } from "../../scripts/app.js";

const NODE_NAME = "MateTextJoin";
const INPUT_RE = /^text_(\d+)$/;
const MAX_INPUTS = 20;

function getTextInputs(node) {
	return (node.inputs || []).filter((input) => INPUT_RE.test(input.name));
}

function inputNumber(input) {
	return Number(input.name.match(INPUT_RE)[1]);
}

function syncInputs(node) {
	const inputs = getTextInputs(node);
	if (!inputs.length) return;

	const isConnected = (input) => node.isInputConnected(node.inputs.indexOf(input));
	const linkedNumbers = inputs.filter(isConnected).map(inputNumber);
	const linkedSet = new Set(linkedNumbers);

	// 备用槽优先取已连接最大编号之后的第一个空槽，保证它总在最下方
	let spare = 1;
	if (linkedNumbers.length) {
		const maxLinked = Math.max(...linkedNumbers);
		for (let n = maxLinked + 1; n <= MAX_INPUTS; n++) {
			if (!linkedSet.has(n)) {
				spare = n;
				break;
			}
		}
		if (spare > MAX_INPUTS) {
			spare = 0;
			for (let n = 1; n <= MAX_INPUTS; n++) {
				if (!linkedSet.has(n)) {
					spare = n;
					break;
				}
			}
		}
	}

	// 只保留已连接的槽和唯一一个备用槽
	const removable = inputs
		.filter((input) => !isConnected(input) && inputNumber(input) !== spare)
		.sort((a, b) => inputNumber(b) - inputNumber(a));

	for (const input of removable) {
		const index = node.inputs.indexOf(input);
		if (index >= 0) node.removeInput(index);
	}

	// 备用槽此前被移除时重新补上，保证连接后下方总有一个空端口
	if (spare > 0 && !getTextInputs(node).some((input) => inputNumber(input) === spare)) {
		node.addInput(`text_${spare}`, "STRING");
	}

	// 端口显示为更易读的名称（后端 key 仍为 text_N）
	for (const input of getTextInputs(node)) {
		if (!input.label) input.label = `文本 ${inputNumber(input)}`;
	}

	node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
	name: "Mate.TextJoin",
	async beforeRegisterNodeDef(nodeType, nodeData) {
		if (nodeData.name !== NODE_NAME) return;

		const onNodeCreated = nodeType.prototype.onNodeCreated;
		nodeType.prototype.onNodeCreated = function () {
			const res = onNodeCreated?.apply(this, arguments);
			// 延迟到工作流输入恢复之后，避免误删已保存的链接槽
			setTimeout(() => syncInputs(this), 0);
			return res;
		};

		const onConfigure = nodeType.prototype.onConfigure;
		nodeType.prototype.onConfigure = function () {
			const res = onConfigure?.apply(this, arguments);
			setTimeout(() => syncInputs(this), 0);
			return res;
		};

		const onConnectionsChange = nodeType.prototype.onConnectionsChange;
		nodeType.prototype.onConnectionsChange = function (type, index, connected, linkInfo) {
			const res = onConnectionsChange?.apply(this, arguments);
			if (type === 1) setTimeout(() => syncInputs(this), 0);
			return res;
		};
	},
});
