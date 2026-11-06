import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_NAME = "MateImagePadCrop";
const PREVIEW_NAME = "mate_preview";
const HIDDEN_WITH_RECT = ["x", "y", "宽", "高"];
const SNAP_PX = 8;          // 吸附阈值（屏幕像素）
const SNAP_RELEASE = 1.5;   // 滞回系数：超过阈值 1.5 倍才解除吸附
const COMMIT_DELAY = 100;   // 提交防抖（毫秒）

// ---------------------------------------------------------------- 通用工具

function getWidget(node, name) {
	return node.widgets?.find((w) => w.name === name);
}

function clamp(v, min, max) {
	return Math.min(max, Math.max(min, v));
}

function setWidgetHidden(widget, hidden) {
	if (!widget) return;
	// 前端布局以 widget.hidden 为准（isWidgetVisible/getLayoutWidgets 都会跳过）。
	// 只设 hidden 而不动 computeSize/draw，既彻底不占位，也不影响取值与序列化。
	widget.hidden = !!hidden;
}

function getRect(node) {
	return {
		x: Math.round(Number(getWidget(node, "x")?.value ?? 0)),
		y: Math.round(Number(getWidget(node, "y")?.value ?? 0)),
		w: Math.max(1, Math.round(Number(getWidget(node, "宽")?.value ?? 512))),
		h: Math.max(1, Math.round(Number(getWidget(node, "高")?.value ?? 512))),
	};
}

function setRect(node, rect) {
	const next = {
		x: Math.round(rect.x),
		y: Math.round(rect.y),
		w: Math.max(1, Math.round(rect.w)),
		h: Math.max(1, Math.round(rect.h)),
	};
	// 内部字段名 -> 节点上的实际输入名（宽/高 为中文键）
	const WIDGET_NAMES = { x: "x", y: "y", w: "宽", h: "高" };
	for (const key of Object.keys(next)) {
		const w = getWidget(node, WIDGET_NAMES[key]);
		if (w) w.value = next[key];
	}
	node._mateRect = next;
	node.setDirtyCanvas(true, true);
}

function setRectToFullImage(node) {
	const img = node._mateImg;
	setRect(node, img
		? { x: 0, y: 0, w: img.naturalWidth, h: img.naturalHeight }
		: { x: 0, y: 0, w: 512, h: 512 });
}

// ---------------------------------------------------------------- 图片读取

/** 解析 combo 值：去掉尾部 [input] 类型标注，并拆分 subfolder */
function parseImageValue(value) {
	if (!value) return null;
	let s = String(value).trim();
	let type = "input";
	const m = s.match(/^(.*?)\s*\[(input|output|temp)\]$/);
	if (m) {
		s = m[1];
		type = m[2];
	}
	if (!s) return null;
	const parts = s.split("/");
	const filename = parts.pop();
	return { filename, subfolder: parts.join("/"), type };
}

async function fetchImageURL(value) {
	const p = parseImageValue(value);
	if (!p) return null;
	try {
		const q = new URLSearchParams({ filename: p.filename, type: p.type });
		if (p.subfolder) q.set("subfolder", p.subfolder);
		const res = await api.fetchApi(`/view?${q.toString()}`, { cache: "no-store" });
		if (!res.ok) return null;
		return URL.createObjectURL(await res.blob());
	} catch (e) {
		console.warn("[Mate] 读取图像失败:", e);
		return null;
	}
}

async function loadNodeImage(node, resetRect) {
	const widget = getWidget(node, "图像");
	const key = widget?.value ?? "";
	// 同一张图重复触发（双层事件监听）时直接复用已加载的图像，避免重复请求
	if (node._mateImg && key === node._mateLoadedValue) {
		if (resetRect) {
			setRectToFullImage(node);
			refreshLayout(node);
		}
		return;
	}
	node._mateLoadToken = (node._mateLoadToken || 0) + 1;
	const token = node._mateLoadToken;

	if (node._mateImageURL) {
		URL.revokeObjectURL(node._mateImageURL);
		node._mateImageURL = null;
	}
	node._mateImg = null;

	if (!widget || !widget.value) {
		setRectToFullImage(node);
		refreshLayout(node);
		return;
	}

	const url = await fetchImageURL(widget.value);
	if (token !== node._mateLoadToken) {
		if (url) URL.revokeObjectURL(url);
		return;
	}
	if (!url) {
		refreshLayout(node);
		return;
	}

	const img = await new Promise((resolve) => {
		const el = new Image();
		el.onload = () => resolve(el);
		el.onerror = () => resolve(null);
		el.src = url;
	});
	if (token !== node._mateLoadToken) {
		URL.revokeObjectURL(url);
		return;
	}
	if (!img) {
		URL.revokeObjectURL(url);
		refreshLayout(node);
		return;
	}

	node._mateImageURL = url;
	node._mateImg = img;
	node._mateLoadedValue = key;
	updatePreviewWidget(node);

	if (resetRect || node._matePendingReset) {
		node._matePendingReset = false;
		setRectToFullImage(node);
	} else {
		node._mateRect = getRect(node);
	}
	refreshLayout(node);
}

// ---------------------------------------------------------------- 节点预览

const checkerCache = new WeakMap();

function drawChecker(ctx, x, y, w, h, cell = 10) {
	let pattern = checkerCache.get(ctx);
	if (!pattern) {
		const c = document.createElement("canvas");
		c.width = c.height = cell * 2;
		const g = c.getContext("2d");
		g.fillStyle = "#353535";
		g.fillRect(0, 0, c.width, c.height);
		g.fillStyle = "#454545";
		g.fillRect(0, 0, cell, cell);
		g.fillRect(cell, cell, cell, cell);
		pattern = ctx.createPattern(c, "repeat");
		checkerCache.set(ctx, pattern);
	}
	ctx.save();
	ctx.fillStyle = pattern || "#3a3a3a";
	ctx.fillRect(x, y, w, h);
	ctx.restore();
}

function createPreviewWidget(node) {
	if (node._matePreviewEl) return getWidget(node, PREVIEW_NAME);
	if (!node.addDOMWidget) return null;

	const holder = document.createElement("div");
	holder.style.cssText =
		"width:100%;display:flex;align-items:center;justify-content:center;overflow:hidden;pointer-events:none;";
	node._matePreviewEl = holder;

	const img = document.createElement("img");
	img.draggable = false;
	img.style.cssText = "max-width:100%;max-height:100%;object-fit:contain;display:none;";
	holder.appendChild(img);
	node._matePreviewImg = img;

	const hint = document.createElement("div");
	hint.textContent = "点击「外补画板」选择图像";
	hint.style.cssText = "color:rgba(255,255,255,0.55);font-size:12px;";
	holder.appendChild(hint);
	node._matePreviewHint = hint;

	const widget = node.addDOMWidget(PREVIEW_NAME, "mate_preview", holder, {
		serialize: false,
		hideOnZoom: false,
	});
	if (widget) {
		// 高度由图片比例决定，随节点宽度自动适配
		widget.computeSize = (width) => {
			const w = Math.max(140, width || node.size?.[0] || 260);
			const image = node._mateImg;
			const h = image
				? Math.max(70, Math.min(420, Math.round(w * image.naturalHeight / image.naturalWidth)))
				: 140;
			node._matePreviewH = h;
			if (node._matePreviewEl) node._matePreviewEl.style.height = `${h}px`;
			return [width, h];
		};
		widget.serialize = false;
	}
	return widget;
}

// 图片直接用 DOM <img> 呈现：浏览器会立即重绘，不依赖画布的脏标记刷新
function updatePreviewWidget(node) {
	const img = node._matePreviewImg;
	const hint = node._matePreviewHint;
	if (!img || !hint) return;
	if (node._mateImageURL) {
		img.src = node._mateImageURL;
		img.style.display = "block";
		hint.style.display = "none";
	} else {
		img.removeAttribute("src");
		img.style.display = "none";
		hint.style.display = "block";
	}
}

function refreshLayout(node) {
	relayout(node);
}

function relayout(node) {
	const redraw = () => {
		node.setDirtyCanvas?.(true, true);
		node.graph?.setDirtyCanvas?.(true, true);
		app.canvas?.setDirty?.(true, true);
		// 直接强制重绘一帧，绕过脏标记（部分前端版本不会因脏标记自动重绘节点）
		app.canvas?.draw?.(true, true);
	};
	requestAnimationFrame(() => {
		const computed = node.computeSize ? node.computeSize() : [node.size[0], node.size[1]];
		const w = Math.max(node.size[0], 260);
		const h = Math.max(computed[1], 120);
		// 先抖动 1px 再设回目标尺寸，确保尺寸变化事件触发
		node.setSize([w, h + 1]);
		node.setSize([w, h]);
		redraw();
		// 前端重排是异步的，稍后再补两次重绘，保证图片解码完成后必定可见
		setTimeout(redraw, 80);
		setTimeout(redraw, 240);
	});
}

function applyLongSideVisibility(node) {
	const toggle = getWidget(node, "启用长边");
	const valueWidget = getWidget(node, "长边");
	if (!toggle || !valueWidget) return;
	const enabled = !!toggle.value;
	valueWidget.hidden = false;
	valueWidget.options = valueWidget.options || {};
	valueWidget.options.disabled = !enabled;
	valueWidget.disabled = !enabled;
	const el = valueWidget.element || valueWidget.inputEl;
	if (el) el.disabled = !enabled;
}

// ---------------------------------------------------------------- 画板编辑器

const STYLE_ID = "mate-padcrop-style";

function ensureStyle() {
	if (document.getElementById(STYLE_ID)) return;
	const style = document.createElement("style");
	style.id = STYLE_ID;
	style.textContent = `
#mate-padcrop-dialog {
	border: none;
	padding: 0;
	border-radius: 10px;
	background: #24262b;
	color: #e6e8ec;
	max-width: 94vw;
	max-height: 92vh;
	box-shadow: 0 18px 60px rgba(0, 0, 0, 0.6);
}
#mate-padcrop-dialog::backdrop { background: rgba(0, 0, 0, 0.55); }
.mate-pc-wrap { display: flex; flex-direction: column; min-width: 320px; }
.mate-pc-head {
	display: flex; align-items: center; justify-content: space-between;
	padding: 10px 16px; background: #2d3036; border-bottom: 1px solid #3a3e45;
	font-size: 13px; letter-spacing: 0.5px;
}
.mate-pc-close {
	background: none; border: none; color: #9aa0aa; font-size: 20px;
	cursor: pointer; line-height: 1; padding: 0 4px;
}
.mate-pc-close:hover { color: #fff; }
.mate-pc-body { display: flex; gap: 12px; padding: 12px; align-items: stretch; }
.mate-pc-stage {
	position: relative; flex: 1 1 auto; overflow: auto; background: #1b1d21;
	border: 1px solid #3a3e45; border-radius: 6px; display: flex;
	align-items: center; justify-content: center; min-width: 280px; min-height: 240px;
}
.mate-pc-canvas { display: block; touch-action: none; }
.mate-pc-empty {
	position: absolute; inset: 0; display: flex; align-items: center;
	justify-content: center; color: #9aa0aa; font-size: 13px; pointer-events: none;
}
.mate-pc-side { width: 210px; flex: 0 0 210px; display: flex; flex-direction: column; gap: 8px; }
.mate-pc-row { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.mate-pc-row label { width: 34px; color: #9aa0aa; }
.mate-pc-row input {
	width: 100%; background: #1b1d21; color: #e6e8ec;
	border: 1px solid #3a3e45; border-radius: 4px; padding: 3px 6px; font-size: 12px;
}
.mate-pc-pair { display: flex; gap: 6px; }
.mate-pc-info {
	font-size: 11px; line-height: 1.7; color: #9aa0aa; white-space: pre-line;
	border-top: 1px solid #3a3e45; padding-top: 8px;
}
.mate-pc-tip { font-size: 11px; color: #7f8794; line-height: 1.6; }
.mate-pc-foot {
	display: flex; align-items: center; gap: 8px; padding: 10px 16px;
	border-top: 1px solid #3a3e45; background: #2d3036;
}
.mate-pc-foot .mate-pc-grow { flex: 1 1 auto; }
.mate-pc-btn {
	padding: 6px 14px; border-radius: 5px; border: 1px solid #3a3e45;
	background: #33373e; color: #e6e8ec; cursor: pointer; font-size: 12px;
}
.mate-pc-btn:hover { background: #3d424a; }
.mate-pc-btn[data-kind="primary"] { background: #2a8af6; border-color: #2a8af6; }
.mate-pc-btn[data-kind="primary"]:hover { background: #3b97f8; }
.mate-pc-btn:disabled { opacity: 0.4; cursor: not-allowed; }
`;
	document.head.appendChild(style);
}

function snapEdge(value, target, threshold, wasSnapped) {
	const d = Math.abs(value - target);
	if (d <= threshold) return [target, true];
	if (wasSnapped && d <= threshold * SNAP_RELEASE) return [target, true];
	return [value, false];
}

class BoardEditor {
	constructor() {
		ensureStyle();
		this.node = null;
		this.img = null;
		this.rect = { x: 0, y: 0, w: 1, h: 1 };
		this.content = null;
		this.scale = 1;
		this.dw = 1;
		this.dh = 1;
		this.drag = null;
		this.snap = { left: false, top: false, right: false, bottom: false };
		this.commitTimer = null;
		this._build();
	}

	_build() {
		const dialog = document.createElement("dialog");
		dialog.id = "mate-padcrop-dialog";
		dialog.innerHTML = `
			<div class="mate-pc-wrap">
				<div class="mate-pc-head">
					<span>外补 / 裁剪画板</span>
					<button class="mate-pc-close" type="button" title="关闭">×</button>
				</div>
				<div class="mate-pc-body">
					<div class="mate-pc-stage">
						<canvas class="mate-pc-canvas" tabindex="0"></canvas>
						<div class="mate-pc-empty" hidden>请先在节点中选择图像</div>
					</div>
					<div class="mate-pc-side">
						<div class="mate-pc-row"><label>x</label><input class="mate-pc-num" data-key="x" type="number" step="1"></div>
						<div class="mate-pc-row"><label>y</label><input class="mate-pc-num" data-key="y" type="number" step="1"></div>
						<div class="mate-pc-pair">
							<div class="mate-pc-row"><label>宽</label><input class="mate-pc-num" data-key="w" type="number" step="1" min="1"></div>
							<div class="mate-pc-row"><label>高</label><input class="mate-pc-num" data-key="h" type="number" step="1" min="1"></div>
						</div>
						<div class="mate-pc-info"></div>
						<div class="mate-pc-tip">拖动边框裁剪或外补，靠近原图边界自动吸附。方向键微调 1px，Shift + 方向键 10px。</div>
					</div>
				</div>
				<div class="mate-pc-foot">
					<button class="mate-pc-btn" data-act="reset" type="button">重置为整图</button>
					<span class="mate-pc-grow"></span>
					<button class="mate-pc-btn" data-act="cancel" type="button">取消</button>
					<button class="mate-pc-btn" data-act="apply" data-kind="primary" type="button">应用</button>
				</div>
			</div>
		`;
		document.body.appendChild(dialog);

		this.dialog = dialog;
		this.canvas = dialog.querySelector(".mate-pc-canvas");
		this.ctx = this.canvas.getContext("2d");
		this.emptyHint = dialog.querySelector(".mate-pc-empty");
		this.infoBox = dialog.querySelector(".mate-pc-info");
		this.applyBtn = dialog.querySelector('[data-act="apply"]');
		this.numInputs = Array.from(dialog.querySelectorAll(".mate-pc-num"));

		dialog.querySelector(".mate-pc-close").addEventListener("click", () => this.close(false));
		dialog.querySelector('[data-act="cancel"]').addEventListener("click", () => this.close(false));
		dialog.querySelector('[data-act="apply"]').addEventListener("click", () => this.close(true));
		dialog.querySelector('[data-act="reset"]').addEventListener("click", () => this.reset());

		dialog.addEventListener("keydown", (e) => this._onKey(e));

		this.canvas.addEventListener("pointerdown", (e) => this._onDown(e));
		this.canvas.addEventListener("pointermove", (e) => this._onMove(e));
		this.canvas.addEventListener("pointerup", (e) => this._onUp(e));
		this.canvas.addEventListener("pointercancel", (e) => this._onUp(e));
		this.canvas.addEventListener("contextmenu", (e) => e.preventDefault());

		this.numInputs.forEach((input) => {
			input.addEventListener("change", () => this._onFieldChange());
		});
	}

	open(node) {
		this.node = node;
		this.img = node._mateImg || null;
		this.rect = getRect(node);
		this.content = null;
		this.drag = null;
		this.snap = { left: false, top: false, right: false, bottom: false };

		this.emptyHint.hidden = !!this.img;
		this.applyBtn.disabled = !this.img;

		if (!this.dialog.open) this.dialog.showModal();
		this.layout();
		this.render();
		this.syncFields();
		this.canvas.focus();
	}

	close(save) {
		if (save && this.node && this.img) {
			setRect(this.node, this.rect);
			relayout(this.node);
		}
		this.drag = null;
		this.node = null;
		this.img = null;
		this.dialog.close();
	}

	reset() {
		if (!this.img) return;
		this.rect = { x: 0, y: 0, w: this.img.naturalWidth, h: this.img.naturalHeight };
		this.render();
		this.syncFields();
	}

	// ---- 布局与坐标 ----
	_layoutMax() {
		const maxW = Math.max(360, Math.min(window.innerWidth * 0.7, 1400));
		const maxH = Math.max(260, window.innerHeight * 0.66);
		return { maxW, maxH };
	}

	_bounds() {
		if (!this.img) return { x: 0, y: 0, w: 1, h: 1 };
		const W = this.img.naturalWidth;
		const H = this.img.naturalHeight;
		const r = this.rect;
		const x0 = Math.min(0, r.x);
		const y0 = Math.min(0, r.y);
		const x1 = Math.max(W, r.x + r.w);
		const y1 = Math.max(H, r.y + r.h);
		const margin = Math.max(24, Math.round(Math.max(W, H) * 0.05));
		return { x: x0 - margin, y: y0 - margin, w: (x1 - x0) + margin * 2, h: (y1 - y0) + margin * 2 };
	}

	layout() {
		if (!this.img) {
			this.canvas.width = 480;
			this.canvas.height = 300;
			this.dw = 480;
			this.dh = 300;
			this.scale = 1;
			this.content = { x: 0, y: 0, w: 1, h: 1 };
			return;
		}
		const { maxW, maxH } = this._layoutMax();
		this.content = this._bounds();
		const s = Math.min(maxW / this.content.w, maxH / this.content.h);
		this.scale = Math.max(0.02, s);

		this.dw = Math.max(1, Math.round(this.content.w * this.scale));
		this.dh = Math.max(1, Math.round(this.content.h * this.scale));

		const dpr = window.devicePixelRatio || 1;
		this.canvas.width = Math.round(this.dw * dpr);
		this.canvas.height = Math.round(this.dh * dpr);
		this.canvas.style.width = `${this.dw}px`;
		this.canvas.style.height = `${this.dh}px`;
		const cssW = Math.max(120, Math.min(this.dw, maxW) + 24);
		const cssH = Math.max(100, Math.min(this.dh, maxH) + 24);
		this.canvas.parentElement.style.width = `${cssW}px`;
		this.canvas.parentElement.style.height = `${cssH}px`;

		this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
	}

	ensureContent() {
		if (!this.img) return;
		const cur = this.content;
		const W = this.img.naturalWidth;
		const H = this.img.naturalHeight;
		const r = this.rect;
		const needExpand =
			r.x < cur.x || r.y < cur.y ||
			r.x + r.w > cur.x + cur.w || r.y + r.h > cur.y + cur.h;
		if (needExpand) {
			this.layout();
		}
		// 至少覆盖原图
		if (cur.x > 0 || cur.y > 0 || cur.x + cur.w < W || cur.y + cur.h < H) {
			this.layout();
		}
	}

	imgToScreen(px, py) {
		return {
			x: (px - this.content.x) * this.scale,
			y: (py - this.content.y) * this.scale,
		};
	}

	screenToImg(sx, sy) {
		return {
			x: sx / this.scale + this.content.x,
			y: sy / this.scale + this.content.y,
		};
	}

	rectScreen() {
		const p = this.imgToScreen(this.rect.x, this.rect.y);
		return { x: p.x, y: p.y, w: this.rect.w * this.scale, h: this.rect.h * this.scale };
	}

	pos(e) {
		const box = this.canvas.getBoundingClientRect();
		return { x: e.clientX - box.left, y: e.clientY - box.top };
	}

	// ---- 渲染 ----
	render() {
		const ctx = this.ctx;
		ctx.clearRect(0, 0, this.dw, this.dh);
		drawChecker(ctx, 0, 0, this.dw, this.dh, 12);

		if (!this.img) return;

		const imgPos = this.imgToScreen(0, 0);
		const iw = this.img.naturalWidth * this.scale;
		const ih = this.img.naturalHeight * this.scale;

		ctx.drawImage(this.img, imgPos.x, imgPos.y, iw, ih);
		ctx.strokeStyle = "rgba(255,255,255,0.45)";
		ctx.lineWidth = 1;
		ctx.strokeRect(imgPos.x + 0.5, imgPos.y + 0.5, iw - 1, ih - 1);

		const rs = this.rectScreen();

		// 方框外遮罩
		ctx.save();
		ctx.beginPath();
		ctx.rect(0, 0, this.dw, this.dh);
		ctx.rect(rs.x, rs.y, rs.w, rs.h);
		ctx.fillStyle = "rgba(0,0,0,0.5)";
		ctx.fill("evenodd");
		ctx.restore();

		// 虚线方框
		const snapped = this.snap.left || this.snap.top || this.snap.right || this.snap.bottom;
		ctx.save();
		ctx.setLineDash([6, 4]);
		ctx.lineWidth = 1.6;
		ctx.strokeStyle = snapped ? "#57d98a" : "#4da3ff";
		ctx.strokeRect(rs.x, rs.y, rs.w, rs.h);
		ctx.restore();

		// 手柄
		const handles = this.handlePoints(rs);
		ctx.fillStyle = snapped ? "#57d98a" : "#4da3ff";
		for (const h of handles) {
			ctx.fillRect(h.x - 3.5, h.y - 3.5, 7, 7);
		}

		// 尺寸标注
		const label = `${this.rect.w} × ${this.rect.h}`;
		ctx.font = "12px sans-serif";
		const tw = ctx.measureText(label).width;
		let lx = clamp(rs.x + 6, 4, this.dw - tw - 12);
		let ly = rs.y - 8;
		if (ly < 14) ly = Math.min(this.dh - 6, rs.y + rs.h + 16);
		ctx.fillStyle = "rgba(0,0,0,0.7)";
		ctx.fillRect(lx - 4, ly - 12, tw + 8, 17);
		ctx.fillStyle = "#fff";
		ctx.fillText(label, lx, ly);
	}

	handlePoints(rs) {
		const cx = rs.x + rs.w / 2;
		const cy = rs.y + rs.h / 2;
		return [
			{ x: rs.x, y: rs.y }, { x: cx, y: rs.y }, { x: rs.x + rs.w, y: rs.y },
			{ x: rs.x, y: cy }, { x: rs.x + rs.w, y: cy },
			{ x: rs.x, y: rs.y + rs.h }, { x: cx, y: rs.y + rs.h }, { x: rs.x + rs.w, y: rs.y + rs.h },
		];
	}

	hitTest(p) {
		if (!this.img) return null;
		const rs = this.rectScreen();
		const tol = 9;
		const nearL = Math.abs(p.x - rs.x) <= tol;
		const nearR = Math.abs(p.x - (rs.x + rs.w)) <= tol;
		const nearT = Math.abs(p.y - rs.y) <= tol;
		const nearB = Math.abs(p.y - (rs.y + rs.h)) <= tol;
		const inX = p.x >= rs.x && p.x <= rs.x + rs.w;
		const inY = p.y >= rs.y && p.y <= rs.y + rs.h;
		if (nearL && nearT) return "lt";
		if (nearR && nearT) return "rt";
		if (nearL && nearB) return "lb";
		if (nearR && nearB) return "rb";
		if (nearL && inY) return "l";
		if (nearR && inY) return "r";
		if (nearT && inX) return "t";
		if (nearB && inX) return "b";
		if (inX && inY) return "move";
		return null;
	}

	cursorFor(mode) {
		if (!mode) return "crosshair";
		if (mode === "move") return "move";
		if (mode === "l" || mode === "r") return "ew-resize";
		if (mode === "t" || mode === "b") return "ns-resize";
		if (mode === "lt" || mode === "rb") return "nwse-resize";
		if (mode === "rt" || mode === "lb") return "nesw-resize";
		return "crosshair";
	}

	// ---- 交互 ----
	_onDown(e) {
		if (!this.img) return;
		this.canvas.focus();
		const p = this.pos(e);
		const hit = this.hitTest(p);
		if (!hit) {
			const a = this.screenToImg(p.x, p.y);
			this.drag = { mode: "create", anchor: a, start: p, startRect: { ...this.rect } };
			this.rect = { x: Math.round(a.x), y: Math.round(a.y), w: 1, h: 1 };
		} else {
			this.drag = { mode: hit, start: p, startRect: { ...this.rect } };
		}
		this.snap = { left: false, top: false, right: false, bottom: false };
		if (this.canvas.setPointerCapture) {
			try { this.canvas.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
		}
		e.preventDefault();
		this.render();
	}

	_onMove(e) {
		const p = this.pos(e);
		if (!this.drag) {
			this.canvas.style.cursor = this.cursorFor(this.hitTest(p));
			return;
		}
		this._applyDrag(p);
		this.ensureContent();
		this.render();
		this.syncFields();
	}

	_onUp(e) {
		if (!this.drag) return;
		this.drag = null;
		if (this.canvas.releasePointerCapture) {
			try { this.canvas.releasePointerCapture(e.pointerId); } catch (_) { /* ignore */ }
		}
		this.scheduleCommit();
	}

	_applyDrag(p) {
		if (!this.img || !this.drag) return;
		const d = this.drag;
		const th = SNAP_PX / this.scale;
		const startImg = this.screenToImg(d.start.x, d.start.y);
		const nowImg = this.screenToImg(p.x, p.y);
		const dx = nowImg.x - startImg.x;
		const dy = nowImg.y - startImg.y;

		const W = this.img.naturalWidth;
		const H = this.img.naturalHeight;
		const MIN = 1;
		let r = { ...d.startRect };

		if (d.mode === "create") {
			const ax = d.anchor.x;
			const ay = d.anchor.y;
			let x1 = Math.min(ax, nowImg.x);
			let x2 = Math.max(ax, nowImg.x);
			let y1 = Math.min(ay, nowImg.y);
			let y2 = Math.max(ay, nowImg.y);
			[x1, this.snap.left] = snapEdge(x1, 0, th, this.snap.left);
			[y1, this.snap.top] = snapEdge(y1, 0, th, this.snap.top);
			[x2, this.snap.right] = snapEdge(x2, W, th, this.snap.right);
			[y2, this.snap.bottom] = snapEdge(y2, H, th, this.snap.bottom);
			r = { x: x1, y: y1, w: Math.max(MIN, x2 - x1), h: Math.max(MIN, y2 - y1) };
		} else if (d.mode === "move") {
			let nx = r.x + dx;
			let ny = r.y + dy;
			[nx, this.snap.left] = snapEdge(nx, 0, th, this.snap.left);
			if (!this.snap.left) {
				let flagged;
				[nx, flagged] = snapEdge(nx + r.w, W, th, this.snap.right);
				this.snap.right = flagged;
				if (flagged) nx = W - r.w;
			}
			[ny, this.snap.top] = snapEdge(ny, 0, th, this.snap.top);
			if (!this.snap.top) {
				let flagged;
				[ny, flagged] = snapEdge(ny + r.h, H, th, this.snap.bottom);
				this.snap.bottom = flagged;
				if (flagged) ny = H - r.h;
			}
			r.x = nx;
			r.y = ny;
		} else {
			if (d.mode.includes("l")) {
				let nx = r.x + dx;
				[nx, this.snap.left] = snapEdge(nx, 0, th, this.snap.left);
				const right = r.x + r.w;
				nx = Math.min(nx, right - MIN);
				r.w = right - nx;
				r.x = nx;
			}
			if (d.mode.includes("r")) {
				let nr = r.x + r.w + dx;
				[nr, this.snap.right] = snapEdge(nr, W, th, this.snap.right);
				r.w = Math.max(MIN, nr - r.x);
			}
			if (d.mode.includes("t")) {
				let ny = r.y + dy;
				[ny, this.snap.top] = snapEdge(ny, 0, th, this.snap.top);
				const bottom = r.y + r.h;
				ny = Math.min(ny, bottom - MIN);
				r.h = bottom - ny;
				r.y = ny;
			}
			if (d.mode.includes("b")) {
				let nb = r.y + r.h + dy;
				[nb, this.snap.bottom] = snapEdge(nb, H, th, this.snap.bottom);
				r.h = Math.max(MIN, nb - r.y);
			}
		}

		const limitX = W * 4;
		const limitY = H * 4;
		r.x = clamp(r.x, -limitX, limitX);
		r.y = clamp(r.y, -limitY, limitY);
		r.w = clamp(r.w, MIN, limitX);
		r.h = clamp(r.h, MIN, limitY);

		this.rect = {
			x: Math.round(r.x),
			y: Math.round(r.y),
			w: Math.max(1, Math.round(r.w)),
			h: Math.max(1, Math.round(r.h)),
		};
	}

	scheduleCommit() {
		if (this.commitTimer) clearTimeout(this.commitTimer);
		this.commitTimer = setTimeout(() => {
			this.commitTimer = null;
			if (!this.node || !this.img) return;
			setRect(this.node, this.rect);
		}, COMMIT_DELAY);
	}

	_onKey(e) {
		if (e.key === "Escape") {
			e.preventDefault();
			this.close(false);
			return;
		}
		if (e.key === "Enter") {
			e.preventDefault();
			this.close(true);
			return;
		}
		const step = e.shiftKey ? 10 : 1;
		let moved = true;
		if (e.key === "ArrowLeft") this.rect.x -= step;
		else if (e.key === "ArrowRight") this.rect.x += step;
		else if (e.key === "ArrowUp") this.rect.y -= step;
		else if (e.key === "ArrowDown") this.rect.y += step;
		else moved = false;
		if (!moved) return;
		e.preventDefault();
		this.render();
		this.syncFields();
		this.scheduleCommit();
	}

	_onFieldChange() {
		const next = { ...this.rect };
		for (const input of this.numInputs) {
			const key = input.dataset.key;
			const val = Number(input.value);
			if (!Number.isFinite(val)) continue;
			next[key] = val;
		}
		if (!this.img) return;
		next.w = Math.max(1, Math.round(next.w));
		next.h = Math.max(1, Math.round(next.h));
		next.x = Math.round(next.x);
		next.y = Math.round(next.y);
		this.rect = next;
		this.render();
		this.syncFields();
		this.scheduleCommit();
	}

	syncFields() {
		for (const input of this.numInputs) {
			const key = input.dataset.key;
			const val = this.rect[key];
			if (document.activeElement !== input) input.value = String(val);
		}
		this.updateInfo();
	}

	updateInfo() {
		if (!this.img || !this.node) {
			this.infoBox.textContent = "";
			return;
		}
		const W = this.img.naturalWidth;
		const H = this.img.naturalHeight;
		const r = this.rect;
		const padL = Math.max(0, -r.x);
		const padT = Math.max(0, -r.y);
		const padR = Math.max(0, r.x + r.w - W);
		const padB = Math.max(0, r.y + r.h - H);
		const cropL = clamp(r.x, 0, W);
		const cropT = clamp(r.y, 0, H);
		const cropR = clamp(W - (r.x + r.w), 0, W);
		const cropB = clamp(H - (r.y + r.h), 0, H);

		let outW = r.w;
		let outH = r.h;
		const toggle = getWidget(this.node, "启用长边");
		const longSideWidget = getWidget(this.node, "长边");
		if (toggle?.value && longSideWidget) {
			const N = Math.max(1, Math.round(Number(longSideWidget.value) || 1024));
			if (r.w >= r.h) {
				outW = N;
				outH = Math.max(1, Math.round(r.h * N / r.w));
			} else {
				outH = N;
				outW = Math.max(1, Math.round(r.w * N / r.h));
			}
		}

		this.infoBox.textContent =
			`原图 ${W} × ${H}\n` +
			`输出 ${outW} × ${outH}\n` +
			`外补 左${padL} 上${padT} 右${padR} 下${padB}\n` +
			`裁剪 左${cropL} 上${cropT} 右${cropR} 下${cropB}`;
	}
}

const editor = new BoardEditor();

// ---------------------------------------------------------------- 节点装配

function setupNode(node) {
	if (node._mateSetupDone) return;
	node._mateSetupDone = true;
	node._matePendingReset = true;

	for (const name of HIDDEN_WITH_RECT) {
		setWidgetHidden(getWidget(node, name), true);
	}
	applyLongSideVisibility(node);

	const button = node.addWidget("button", "外补画板", null, () => editor.open(node));
	if (button) button.serialize = false;

	// 新版前端会为本节点的 IMAGE 输出在节点上叠加一张结果图预览（DOM 覆盖层），
	// 与本节点自带的加载图预览重复。hideOutputImages 是该覆盖层的官方开关。
	node.hideOutputImages = true;

	// ComfyUI 前端在节点产出 IMAGE 后会把执行结果图写入 node.imgs，并据此自动追加
	// $$canvas-image-preview 内置预览控件（带分辨率标注），与本节点的加载图预览重复。
	// 内置预览的唯一触发条件是 node.imgs 非空，这里把该属性锁定为空即可彻底阻止。
	Object.defineProperty(node, "imgs", {
		get: () => undefined,
		set: () => {},
		configurable: true,
	});

	createPreviewWidget(node);

	const imageWidget = getWidget(node, "图像");
	if (imageWidget) {
		const prev = imageWidget.callback;
		imageWidget.callback = function () {
			const r = prev?.apply(this, arguments);
			loadNodeImage(node, true);
			return r;
		};
	}

	// 新版前端通过 onWidgetChanged 派发控件变更，callback 不一定被调用；
	// 两条通路都监听，确保换图后立刻重新加载并重绘预览。
	const prevChanged = node.onWidgetChanged;
	node.onWidgetChanged = function (name, ...rest) {
		prevChanged?.apply(this, [name, ...rest]);
		if (name === "图像") loadNodeImage(node, true);
		if (name === "启用长边") {
			applyLongSideVisibility(node);
			relayout(node);
		}
	};

	const longSideToggle = getWidget(node, "启用长边");
	if (longSideToggle) {
		const prev = longSideToggle.callback;
		longSideToggle.callback = function () {
			const r = prev?.apply(this, arguments);
			applyLongSideVisibility(node);
			relayout(node);
			return r;
		};
	}

	node._mateRect = getRect(node);
	loadNodeImage(node, false);
	setTimeout(() => relayout(node), 0);
}

app.registerExtension({
	name: "Mate.ImagePadCrop",
	beforeRegisterNodeDef(nodeType, nodeData) {
		if (nodeData.name !== NODE_NAME) return;

		const onNodeCreated = nodeType.prototype.onNodeCreated;
		nodeType.prototype.onNodeCreated = function () {
			const res = onNodeCreated?.apply(this, arguments);
			setupNode(this);
			return res;
		};

		const onConfigure = nodeType.prototype.onConfigure;
		nodeType.prototype.onConfigure = function () {
			const res = onConfigure?.apply(this, arguments);
			// 工作流加载：以保存的矩形为准，不做重置
			this._matePendingReset = false;
			this._mateRect = getRect(this);
			loadNodeImage(this, false);
			setTimeout(() => relayout(this), 0);
			return res;
		};
	},
});
