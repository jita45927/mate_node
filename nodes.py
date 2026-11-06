"""Mate Node - 捏脸提示词生成节点包

通过下拉框选择各维度标签（每个标签有预设选项），自动拼接提示词。
三路输出：
- prompt_zh：中文，[标签]内容 逐行格式，适配 Z-Image / Kolors / 混元 / 即梦等中文模型
- prompt_en：英文，[Tag]content 逐行格式，适配 FLUX / SD3.5 等英文自然语言模型
- tags_en：英文逗号分隔短 tag，专为 SD1.5 / SDXL（CLIP 编码器、75 token 上限）优化

预设标签使用预置英文；"其他"自由文本可选本地离线翻译（见 translate.py）。
"""

from .translate import contains_chinese, translate_zh_to_en

_SKIP = "（不使用）"

# 标签数据结构：中文标签、英文标签、选项列表 [(中文, 英文长句, SD短tag), ...]
# 列表第一项为默认值；风格、人种性别默认选中常用项，其余默认"不使用"（不输出）
TAGS = [
    {
        "zh": "风格", "en": "Style",
        "options": [
            ("写实摄影", "realistic photography", "photorealistic, realistic photo"),
            ("3D渲染", "3D render", "3d render"),
            ("2.5D", "2.5D style", "2.5d style"),
            ("二次元", "anime style", "anime style"),
            ("电影胶片", "cinematic film look", "cinematic film still, film grain"),
            ("国风工笔", "traditional Chinese gongbi painting style", "chinese gongbi painting"),
            ("油画质感", "oil painting texture", "oil painting style"),
            (_SKIP, None, None),
        ],
    },
    {
        "zh": "人种性别", "en": "Ethnicity & Gender",
        "options": [
            ("亚洲女性", "Asian woman", "asian woman"),
            ("亚洲男性", "Asian man", "asian man"),
            ("欧美白人女性", "Caucasian woman", "caucasian woman"),
            ("欧美白人男性", "Caucasian man", "caucasian man"),
            ("非裔女性", "African woman", "black woman"),
            ("非裔男性", "African man", "black man"),
            ("拉丁裔女性", "Latina woman", "latina woman"),
            ("拉丁裔男性", "Latino man", "latino man"),
            ("欧亚混血女性", "mixed Eurasian woman", "mixed eurasian woman"),
            ("中东女性", "Middle Eastern woman", "middle eastern woman"),
            (_SKIP, None, None),
        ],
    },
    {
        "zh": "年龄段", "en": "Age",
        "options": [
            (_SKIP, None, None),
            ("少女（16-22岁），面部饱满，皮肤紧致", "16-22 years old, full youthful face, firm skin", "young adult, youthful face, firm skin"),
            ("青年（23-30岁），面部线条清晰", "23-30 years old, well-defined facial lines", "young adult, defined facial lines"),
            ("轻熟（31-40岁），成熟稳重，眼角有细微纹路", "31-40 years old, mature and composed, fine lines at the eye corners", "mature, fine eye wrinkles"),
            ("中年（41-55岁），轮廓略松弛，法令纹与眼尾纹自然", "41-55 years old, slightly relaxed contours, natural nasolabial folds and crow's feet", "middle-aged, nasolabial folds, crow's feet"),
            ("老年（60岁以上），皮肤松弛有皱纹，轮廓下垂", "over 60 years old, loose wrinkled skin, sagging contours", "elderly, wrinkled skin, sagging contours"),
        ],
    },
    {
        "zh": "气质", "en": "Temperament",
        "options": [
            (_SKIP, None, None),
            ("温和、沉静、有书卷气、目光像在思考", "gentle, calm, scholarly air, thoughtful gaze", "gentle, calm, scholarly, thoughtful gaze"),
            ("冷艳疏离，气场强大，不带讨好感", "cold elegant aloofness, powerful aura, unapproachable", "cold elegance, aloof, powerful aura"),
            ("甜美亲切，笑容有感染力，有邻家感", "sweet and friendly, infectious smile, girl-next-door charm", "sweet, friendly, infectious smile, girl next door"),
            ("英气干练，目光锐利，行事果断", "sharp and capable, piercing gaze, decisive", "sharp, capable, piercing gaze"),
            ("忧郁内敛，安静敏感，有故事感", "melancholic and reserved, quiet and sensitive, with a story in her eyes", "melancholic, reserved, quiet"),
            ("活泼灵动，俏皮元气，眼神明亮", "lively and playful, bright energetic eyes", "lively, playful, bright eyes"),
            ("慵懒松弛，漫不经心，随性自然", "languid and relaxed, carefree, effortless", "languid, relaxed, effortless"),
            ("端庄典雅，举止克制，有大家闺秀感", "dignified and elegant, restrained manners, refined grace", "dignified, elegant, refined"),
            ("清冷孤傲，遗世独立，不易接近", "cool and proud, otherworldly, distant", "cool, proud, distant"),
        ],
    },
    {
        "zh": "脸型骨相", "en": "Face Shape",
        "options": [
            (_SKIP, None, None),
            ("长椭圆脸，颧骨平缓，下颌角约115度圆润，下巴长而圆润", "long oval face, flat gentle cheekbones, rounded jaw angle of about 115 degrees, long rounded chin", "long oval face, soft cheekbones, rounded jawline, round chin"),
            ("标准鹅蛋脸，颧骨低平内收，下颌线流畅，下巴尖而不锐", "classic oval face, low tucked-in cheekbones, smooth jawline, tapered but not sharp chin", "oval face, low cheekbones, smooth jawline, tapered chin"),
            ("心形脸，额头较宽，颧骨略高不外扩，下颌收窄，下巴小巧尖翘", "heart-shaped face, wider forehead, slightly high but not flaring cheekbones, narrowing jaw, small pointed chin", "heart-shaped face, wide forehead, small pointed chin"),
            ("圆脸，面部线条柔和，下颌角不明显，下巴短圆，幼态感强", "round face, soft facial lines, indistinct jaw angle, short round chin, youthful look", "round face, soft features, short round chin, youthful look"),
            ("方脸，下颌角明显约120度，轮廓分明，下巴偏方正", "square face, defined jaw angle of about 120 degrees, crisp contours, squarish chin", "square face, defined jawline, square chin"),
            ("菱形脸，颧骨最宽略突出，额头与下巴偏窄，下巴尖", "diamond face, widest slightly prominent cheekbones, narrow forehead and chin, pointed chin", "diamond face, high cheekbones, pointed chin"),
            ("短圆脸，三庭偏短，下颌角低而圆润，下巴短小，娃娃脸比例", "short round face, compact facial thirds, low rounded jaw angle, small chin, baby-face proportions", "short round face, baby-face proportions"),
            ("长脸，中庭偏长，颧骨平缓，下颌线直，下巴偏长", "long face, elongated mid-face, flat cheekbones, straight jawline, long chin", "long face, long mid-face, straight jawline"),
        ],
    },
    {
        "zh": "皮肤", "en": "Skin",
        "options": [
            (_SKIP, None, None),
            ("冷白皮，肤色均匀通透，毛孔细腻，几乎无瑕", "cool porcelain skin, even translucent tone, fine pores, nearly flawless", "porcelain skin, pale skin, flawless skin"),
            ("暖调一白，肤色均匀，自然光泽，气色健康", "fair warm-toned skin, even tone, natural glow, healthy complexion", "fair skin, warm tone, natural glow"),
            ("自然黄调肤色，均匀有光泽，健康紧致", "natural warm beige skin, even and radiant, healthy and firm", "natural beige skin, radiant skin"),
            ("小麦色健康肌，肤色均匀，紧致有光泽", "wheat-toned healthy skin, even tone, firm and glowing", "tanned skin, wheat-toned skin, glowing skin"),
            ("奶油肌，柔焦质感，轻微光泽，毛孔不可见", "creamy skin, soft-focus texture, subtle sheen, invisible pores", "creamy skin, flawless skin, subtle sheen"),
            ("深肤色，均匀有光泽，皮肤紧致，纹理细腻", "deep skin tone, even and radiant, firm skin, fine texture", "dark skin, radiant skin, firm skin"),
            ("自然肤质，保留轻微毛孔与细小瑕疵，真实感强", "natural skin texture, slight pores and minor imperfections, realistic", "natural skin texture, detailed skin, skin pores"),
        ],
    },
    {
        "zh": "眉形", "en": "Eyebrows",
        "options": [
            (_SKIP, None, None),
            ("柳叶眉，细长弯曲，眉峰柔和，眉尾细长微垂", "willow-leaf brows, slender and curved, soft arch, long slightly drooping tails", "willow eyebrows, slender curved brows"),
            ("自然平眉，眉峰不明显，粗细适中，毛流感自然", "natural straight brows, subtle arch, medium thickness, natural hair flow", "straight eyebrows, natural brows"),
            ("剑眉，眉形直而上扬，眉峰锐利，英气十足", "sword brows, straight and upswept, sharp arch, heroic", "sword eyebrows, sharp angled brows"),
            ("弯月眉，弧度圆润流畅，眉峰圆润，眉尾细长", "crescent-moon brows, smooth rounded curve, soft arch, slender tails", "crescent eyebrows, curved brows"),
            ("野生眉，毛流感强，根根分明，自然蓬松", "wild brows, strong hair flow, distinct strands, naturally bushy", "bushy eyebrows, feathered brows"),
            ("欧式挑眉，眉峰高挑锐利，眉尾细长，气场强", "high-arched brows, sharp high arch, slender tails, strong presence", "high arched eyebrows"),
        ],
    },
    {
        "zh": "眼睛", "en": "Eyes",
        "options": [
            (_SKIP, None, None),
            ("杏眼，眼型圆润，双眼皮清晰，眼尾微垂，目光清澈", "almond eyes, rounded shape, defined double eyelids, slightly drooping outer corners, clear gaze", "almond eyes, double eyelids, clear eyes"),
            ("丹凤眼，眼型细长，内眼角尖细下勾，眼尾上扬，神韵内敛", "phoenix eyes, long narrow shape, pointed downturned inner corners, upturned outer corners, restrained charm", "phoenix eyes, narrow upturned eyes"),
            ("桃花眼，眼型细长带弧度，眼尾微弯，卧蚕饱满，笑眼含情", "peach-blossom eyes, long curved shape, gently curved outer corners, full aegyo-sal, affectionate smiling eyes", "peach blossom eyes, smiling eyes, aegyo sal"),
            ("圆眼，眼裂大而圆，双眼皮宽，瞳仁大而黑亮，有无辜感", "large round eyes, wide double eyelids, big dark bright pupils, innocent look", "large round eyes, big pupils, innocent look"),
            ("下垂眼，眼尾低于眼头，眼睑微垂，温柔无辜", "downturned eyes, outer corners lower than inner, slightly drooping lids, gentle and innocent", "downturned eyes, gentle eyes"),
            ("上扬猫眼，眼尾明显上扬，眼型细长，眼神魅惑", "upturned cat eyes, markedly raised outer corners, narrow shape, seductive gaze", "upturned cat eyes, seductive gaze"),
            ("单眼皮细长眼，眼裂窄长，眼皮薄，眼神清冷", "monolid narrow eyes, thin lids, cool clear gaze", "monolid eyes, narrow eyes, cool gaze"),
            ("深邃欧式眼，眼窝深，双眼皮宽而清晰，眉骨高", "deep-set eyes, deep sockets, wide defined double eyelids, high brow bone", "deep-set eyes, defined double eyelids, high brow bone"),
        ],
    },
    {
        "zh": "鼻型", "en": "Nose",
        "options": [
            (_SKIP, None, None),
            ("直鼻，鼻梁挺直，鼻头圆润小巧，鼻翼宽窄适中", "straight nose, straight bridge, small rounded tip, moderately sized nostrils", "straight nose, small nose tip"),
            ("小翘鼻，鼻梁细直，鼻尖微微上翘，鼻头精致", "slightly upturned nose, slim straight bridge, delicately raised tip, refined", "upturned nose, delicate nose tip"),
            ("希腊鼻，鼻梁高挺笔直，山根高，线条流畅", "Greek nose, high straight bridge, high radix, smooth lines", "greek nose, high nose bridge"),
            ("水滴鼻，鼻头圆润饱满如水滴，鼻翼窄，鼻尖微垂", "teardrop nose, full rounded tip like a droplet, narrow nostrils, slightly drooping tip", "teardrop nose, rounded nose tip"),
            ("驼峰鼻，鼻梁中部微凸，轮廓有个性感", "Roman nose, slight bump on the bridge, characterful profile", "roman nose, hooked nose"),
            ("小巧鼻，鼻梁不高但线条柔和，鼻头小巧", "petite nose, low bridge with soft lines, small tip", "petite nose, small nose"),
        ],
    },
    {
        "zh": "嘴型", "en": "Lips",
        "options": [
            (_SKIP, None, None),
            ("樱桃小嘴，唇形小巧，唇峰清晰，唇色自然红润", "cherry lips, small shape, defined cupid's bow, naturally rosy", "cherry lips, small lips, rosy lips"),
            ("M形微笑唇，唇峰M形明显，嘴角自然上扬", "M-shaped smiling lips, pronounced M cupid's bow, naturally upturned corners", "smiling lips, upturned mouth corners"),
            ("饱满厚唇，上下唇饱满圆润，唇形性感", "full plump lips, rounded upper and lower lips, sensual shape", "full lips, plump lips"),
            ("薄唇，唇形纤薄精致，唇线清晰", "thin lips, delicate shape, crisp lip line", "thin lips"),
            ("标准唇，上下唇比例约1:1.2，唇峰柔和，唇形端正", "balanced lips, upper to lower ratio about 1:1.2, soft cupid's bow, well-proportioned", "balanced lips, well-proportioned lips"),
        ],
    },
    {
        "zh": "发型", "en": "Hairstyle",
        "options": [
            (_SKIP, None, None),
            ("长直发，及腰长发，发质柔顺有光泽，中分", "long straight hair, waist-length, silky and glossy, center-parted", "long straight hair, waist-length hair, center part"),
            ("大波浪卷发，及胸长发，卷度自然蓬松，侧分", "big wavy hair, chest-length, natural voluminous curls, side-parted", "big wavy hair, chest-length hair, side part"),
            ("锁骨发，长度及锁骨，发尾微内扣，八字刘海", "collarbone-length hair, slightly inward-curled ends, curtain bangs", "collarbone-length hair, curtain bangs"),
            ("齐耳短发，发尾整齐利落，可露出耳朵", "ear-length short hair, neat crisp ends, ears visible", "ear-length short hair"),
            ("高马尾，束发高而紧，发尾自然垂落，额前有碎发修饰", "high ponytail, tied high and tight, naturally falling ends, wispy strands framing the forehead", "high ponytail, wispy strands"),
            ("丸子头，高盘发髻，鬓边碎发自然，清爽利落", "high bun, coiled top knot, natural wisps at the temples, fresh and neat", "hair bun, top knot"),
            ("法式慵懒卷，中长卷发，卷度松散随意", "French lazy waves, medium-length curls, loose effortless texture", "french waves, loose curls, medium hair"),
            ("双麻花辫，两侧编发垂落，发尾微卷", "twin braids, braided hair falling on both sides, slightly curled ends", "twin braids"),
            ("空气感刘海中长发，发尾微卷，轻盈蓬松", "medium-length hair with airy see-through bangs, lightly curled ends, light and fluffy", "see-through bangs, medium hair, light curls"),
        ],
    },
    {
        "zh": "发色", "en": "Hair Color",
        "options": [
            (_SKIP, None, None),
            ("自然黑发，发色乌黑有光泽", "natural black hair, jet black and glossy", "black hair"),
            ("深棕色，室内接近黑色，阳光下显棕", "dark brown hair, near-black indoors, brown in sunlight", "dark brown hair"),
            ("浅棕亚麻色，色调柔和", "light ash brown hair, soft tone", "light brown hair, ash brown hair"),
            ("酒红色，暗光下偏深，光下显红调", "wine red hair, deep in low light, reddish in the light", "wine red hair"),
            ("奶奶灰银白色", "silver grey hair", "silver grey hair"),
            ("黑褐挑染，深色底色，局部浅色挑染", "dark hair with highlights, dark base with light streaks", "dark hair with highlights"),
        ],
    },
    {
        "zh": "表情", "en": "Expression",
        "options": [
            (_SKIP, None, None),
            ("自然微笑，嘴角轻扬，眼神柔和", "natural soft smile, gently raised corners, soft gaze", "soft smile, gentle eyes"),
            ("开怀大笑，露出牙齿，眉眼弯起，感染力强", "hearty laugh, teeth showing, crescent smiling eyes, infectious", "big laugh, teeth showing"),
            ("平静无表情，神态自然，目光直视镜头", "calm neutral expression, natural, looking straight at the camera", "neutral expression, looking at viewer"),
            ("沉思状，目光微微下移，像在思考", "pensive look, gaze slightly lowered, as if thinking", "pensive, looking down"),
            ("淡淡忧郁，眉心轻蹙，眼神安静", "faint melancholy, slightly furrowed brows, quiet gaze", "melancholic, furrowed brows"),
            ("俏皮表情，轻微歪头，眼神灵动", "playful expression, head slightly tilted, lively eyes", "playful expression, head tilt"),
        ],
    },
    {
        "zh": "姿态", "en": "Pose",
        "options": [
            (_SKIP, None, None),
            ("正脸证件照姿势，面部正对镜头，双肩水平", "front-facing ID photo pose, face directly at the camera, shoulders level", "front view, facing viewer, portrait, shoulders level"),
            ("微侧脸，面部向左侧微转约15度，视线看向镜头", "slight three-quarter view, face turned about 15 degrees to the left, eyes at the camera", "slight three-quarter view, looking at viewer"),
            ("微侧脸，面部向右侧微转约15度，视线看向镜头", "slight three-quarter view, face turned about 15 degrees to the right, eyes at the camera", "slight three-quarter view, looking at viewer"),
            ("三分之二侧面，面部转向一侧约30度，经典肖像角度", "two-thirds profile, face turned about 30 degrees to one side, classic portrait angle", "three-quarter view, portrait"),
            ("正面微低头，下巴微收，视线抬向镜头", "front view with head slightly lowered, chin tucked in, eyes raised to the camera", "head tilted down, looking up at viewer"),
            ("正面微抬头，下巴微抬，视线略向下", "front view with head slightly raised, chin slightly lifted, gaze slightly downward", "head raised, looking down"),
            ("轻微歪头，头部向一侧倾斜约10度", "head slightly tilted about 10 degrees to one side", "head tilt"),
            ("侧面轮廓，面部完全转向一侧", "side profile, face fully turned to one side", "profile view, side view"),
            ("侧身回眸，身体侧向一边，头部转向镜头", "over-the-shoulder pose, body turned to one side, head turned back to the camera", "looking back, over shoulder"),
        ],
    },
    {
        "zh": "妆容", "en": "Makeup",
        "options": [
            (_SKIP, None, None),
            ("素颜，无明显妆感，皮肤自然状态", "no makeup, bare natural skin", "no makeup, bare face"),
            ("日常淡妆，底妆轻薄，眉形自然，唇色接近自然唇色", "light everyday makeup, sheer base, natural brows, natural lip color", "light makeup, natural makeup"),
            ("精致全妆，底妆无瑕，眼妆精致，唇形饱满", "refined full makeup, flawless base, delicate eye makeup, full lips", "full makeup, flawless makeup"),
            ("红唇妆，哑光正红唇，眼妆简洁", "red lip makeup, matte classic red lips, simple eye makeup", "red lips, matte lipstick"),
            ("烟熏妆，深色眼影晕染，眼线明显，气场强", "smoky eye makeup, blended dark eyeshadow, bold eyeliner, strong presence", "smoky eyes, dark eyeshadow"),
            ("裸妆，妆感极淡，强调皮肤质感与轮廓", "nude makeup, barely-there look, emphasizing skin texture and contours", "nude makeup, natural look"),
        ],
    },
    {
        "zh": "背景", "en": "Background",
        "options": [
            (_SKIP, None, None),
            ("纯白色背景", "pure white background", "white background, simple background"),
            ("纯黑色背景", "pure black background", "black background, simple background"),
            ("深灰色背景", "dark grey background", "dark grey background, simple background"),
            ("浅灰色背景", "light grey background", "grey background, simple background"),
            ("绿色背景", "green background", "green background, green screen"),
            ("蓝色背景", "blue background", "blue background, simple background"),
            ("红色背景", "red background", "red background, simple background"),
        ],
    },
]

# “其他”为自由文本输入标签，中文内容可选本地离线翻译后进入英文输出
_OTHER_ZH = "其他"
_OTHER_EN = "Other"
_TRANSLATE_TOGGLE = "翻译其他为英文"


class FacePromptBuilder:
    """捏脸提示词生成器：下拉选择各维度标签，输出中/英/tag 三种提示词"""

    @classmethod
    def INPUT_TYPES(cls):
        required = {}
        for tag in TAGS:
            required[tag["zh"]] = ([zh for zh, _, _ in tag["options"]],)
        required[_OTHER_ZH] = (
            "STRING",
            {"multiline": True, "default": "", "dynamicPrompts": False},
        )
        required[_TRANSLATE_TOGGLE] = ("BOOLEAN", {"default": False})
        return {"required": required}

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("prompt_zh", "prompt_en", "tags_en")
    FUNCTION = "execute"
    CATEGORY = "Mate/捏脸"
    DESCRIPTION = "通过标签下拉框组合生成捏脸提示词，同时输出中文、英文、英文 tag 三种格式"

    def execute(self, **kwargs):
        zh_lines = []
        en_lines = []
        sd_tags = []
        for tag in TAGS:
            value = kwargs.get(tag["zh"])
            if value is None or value == _SKIP:
                continue
            zh_lines.append(f"[{tag['zh']}]{value}")
            en_value, sd_value = next(
                ((en, sd) for zh, en, sd in tag["options"] if zh == value),
                (None, None),
            )
            if en_value:
                en_lines.append(f"[{tag['en']}]{en_value}")
            if sd_value:
                sd_tags.append(sd_value)
        other = kwargs.get(_OTHER_ZH, "").strip()
        if other:
            zh_lines.append(f"[{_OTHER_ZH}]{other}")
            other_en = other
            if kwargs.get(_TRANSLATE_TOGGLE) and contains_chinese(other):
                other_en = translate_zh_to_en(other)
            en_lines.append(f"[{_OTHER_EN}]{other_en}")
            sd_tags.append(other_en)
        return ("\n".join(zh_lines), "\n".join(en_lines), ", ".join(sd_tags))


# 节点类注册表：key 是内部唯一 ID（不要与其他插件重复）
NODE_CLASS_MAPPINGS = {
    "MateFacePromptBuilder": FacePromptBuilder,
}

# 节点在界面上显示的名称
NODE_DISPLAY_NAME_MAPPINGS = {
    "MateFacePromptBuilder": "捏脸提示词生成器 (Mate)",
}
