"""Mate Node - 国风发型/发饰提示词生成节点

结构与捏脸提示词生成器一致，同样输出三路提示词：
- prompt_zh：中文，[标签]内容 逐行格式，适配中文原生模型
- prompt_en：英文，[Tag]content 逐行格式，适配 FLUX / SD3.5
- tags_en：英文逗号分隔短 tag，适配 SD1.5 / SDXL

组合顺序参考「朝代/形制 + 发髻形态 + 发饰 + 发丝质感 + 整体气质」。
与捏脸节点不同的是：先选择「男性发型 / 女性发型」，
其余标签（朝代、发型、配饰、发丝质感、气质）的选项会按性别在前端动态切换。
"""

from .translate import contains_chinese, translate_zh_to_en

_SKIP = "（不使用）"

_GENDER_ZH = "性别"
_GENDER_EN = "Gender"
_GENDER_MALE = "男性发型"
_GENDER_FEMALE = "女性发型"

_OTHER_ZH = "其他"
_OTHER_EN = "Other"
_TRANSLATE_TOGGLE = "翻译其他为英文"

# ---------------------------------------------------------------------------
# 朝代 / 风格（男女通用）
# ---------------------------------------------------------------------------
DYNASTY = [
    (_SKIP, None, None),
    ("汉代发型", "Han dynasty style", "han dynasty, ancient chinese historical style"),
    ("魏晋南北朝发型", "Wei-Jin and Northern-Southern dynasties style", "wei jin style, ancient chinese historical style"),
    ("唐代发型", "Tang dynasty style", "tang dynasty, ancient chinese historical style"),
    ("宋代发型", "Song dynasty style", "song dynasty, ancient chinese historical style"),
    ("明代发型", "Ming dynasty style", "ming dynasty, ancient chinese historical style"),
    ("清代发型", "Qing dynasty style", "qing dynasty, ancient chinese historical style"),
    ("民国发型", "Republican era style", "republic of china era, retro chinese style"),
    ("仙侠玄幻发型", "xianxia fantasy style", "xianxia, chinese fantasy style"),
    ("架空古风发型", "fictional ancient Chinese style", "ancient chinese fantasy style, guofeng"),
]

# ---------------------------------------------------------------------------
# 女性：发型（按朝代 / 形制）
# ---------------------------------------------------------------------------
FEMALE_HAIR = [
    (_SKIP, None, None),
    # 通用形制
    (
        "高髻，发髻高高盘起于头顶，端庄华贵",
        "high bun, tall chignon coiled high on top of the head, dignified and luxurious",
        "high bun, tall chignon, ancient chinese updo",
    ),
    (
        "盘发，发丝层层盘绕成精致发髻，整洁利落",
        "coiled updo, hair layered and coiled into an elaborate chignon, neat and tidy",
        "coiled updo, elaborate chignon, ancient chinese hairstyle",
    ),
    (
        "低髻，发髻低盘于颈后，温婉沉静",
        "low bun at the nape, hair coiled low behind the neck, gentle and serene",
        "low bun, nape bun, ancient chinese hairstyle",
    ),
    (
        "双丫髻，头顶两侧各绾一个圆髻，余发垂落，少女感十足",
        "twin buns on top, a round bun tied on each side of the head, remaining hair falling down, girlish charm",
        "twin buns, double bun hairstyle, ancient chinese girl hair",
    ),
    (
        "半披半绾，上半部分束起成髻，下半长发自然披散",
        "half-up half-down, upper hair tied into a bun, lower hair flowing naturally",
        "half up half down hair, long black hair, ancient chinese hairstyle",
    ),
    (
        "披发，长发自然垂落披散，发丝柔顺及腰",
        "loose flowing hair, long hair falling naturally, silky waist-length strands",
        "long loose hair, waist-length black hair",
    ),
    (
        "长直发，中分长发垂顺，发质乌黑有光泽",
        "long straight hair, center-parted and sleek, jet black and glossy",
        "long straight black hair, center part",
    ),
    (
        "双麻花辫，两侧编成麻花辫垂落胸前",
        "twin braids, hair braided on both sides and falling over the chest",
        "twin braids, ancient chinese girl hair",
    ),
    (
        "单麻花辫，长发编成一条辫子垂于一侧肩前",
        "single braid, long hair braided into one plait falling over one shoulder",
        "single braid, long braid",
    ),
    (
        "垂鬟分肖髻，两侧各垂一个发髻，余发自然披散至肩背",
        "drooping double buns, buns hanging at both sides, remaining hair falling over the shoulders",
        "double hanging buns, ancient chinese girl hair",
    ),
    # 唐代
    (
        "唐代堕马髻，发髻偏垂头侧，发丝松散，慵懒妩媚",
        "falling-horse chignon, asymmetric drooping bun to one side, loose languid strands, alluring",
        "falling horse bun, asymmetric bun, tang dynasty hairstyle",
    ),
    (
        "唐代双环望仙髻，头顶盘成双环高髻，轻盈如欲飞仙",
        "double-loop immortal bun, twin ring bun coiled high on the head, airy and ethereal",
        "twin ring bun, double loop bun, tang dynasty hairstyle",
    ),
    (
        "唐代灵蛇髻，发髻扭转盘绕如灵蛇，线条柔美灵动",
        "serpentine coiled bun, hair twisted and coiled like a serpent, soft flowing lines",
        "serpentine bun, coiled updo, tang dynasty hairstyle",
    ),
    (
        "唐代凌云髻，发髻高耸入云，层层叠起",
        "cloud-high towering chignon, hair stacked high into the clouds",
        "towering chignon, cloud high bun, tang dynasty hairstyle",
    ),
    (
        "唐代十字髻，发髻在头顶分成十字形，端庄规整",
        "cross-shaped double bun, hair parted into a cross shape on the crown, dignified and neat",
        "cross shaped bun, double bun, tang dynasty hairstyle",
    ),
    (
        "唐代倭堕髻，发髻偏斜低垂，柔美温婉",
        "tilted drooping bun, chignon tilted and hanging low, soft and graceful",
        "tilted bun, drooping bun, tang dynasty hairstyle",
    ),
    (
        "唐代飞仙髻，高耸的环状发髻向上翻卷，发丝如云，两侧垂落飘带",
        "flying-immortal bun, towering looped coifs sweeping upward, cloud-like hair, ribbons falling on both sides",
        "flying immortal bun, high looped bun, tang dynasty hairstyle",
    ),
    # 宋代
    (
        "宋代包髻，发髻低圆，以布帛包裹成圆髻",
        "wrapped chignon, low rounded bun wrapped in cloth",
        "low rounded bun, wrapped chignon, song dynasty hairstyle",
    ),
    (
        "宋代冠梳，头戴冠饰并插长梳，端庄雅致",
        "hair crown with combs, a crown adorned with long combs, refined and elegant",
        "hair crown, hair combs, song dynasty hairstyle",
    ),
    # 明代
    (
        "明代䯼髻，以金银丝编成䯼髻罩于发上，髻形饱满",
        "Ming dynasty di ji bun, gold-wire frame bun covering the hair, full rounded shape",
        "ming dynasty hair bun, gold wire bun, ancient chinese hairstyle",
    ),
    (
        "明代圆髻，发髻圆润并满插簪钗，华贵繁复",
        "round bun fully decorated with hairpins, ornate and luxurious",
        "round bun, many hairpins, ming dynasty hairstyle",
    ),
    # 清代
    (
        "清代两把头，横向分作两把的满族发式，端庄大气",
        "Qing two-handle headdress, Manchu liangbatou with hair divided into two horizontal sections, dignified",
        "liangbatou, two handle headdress, qing dynasty hairstyle",
    ),
    (
        "清代大拉翅，宽大如翅的满族扁方发架，华贵醒目",
        "large winged Manchu headdress, broad wing-like dalachi hair frame, luxurious and striking",
        "dalachi, large winged headdress, qing dynasty hairstyle",
    ),
    (
        "清代钿子，满族钿子头饰，簪花缀珠",
        "Manchu dianzi headdress, ornate headpiece decorated with flowers and pearls",
        "dianzi headdress, qing dynasty hairstyle",
    ),
    (
        "清代燕尾，脑后长发梳成燕尾状垂落",
        "swallow-tail back hair, back hair shaped into a swallow-tail fall",
        "swallow tail hair, qing dynasty hairstyle",
    ),
    # 民国
    (
        "民国手推波纹卷发，发丝呈S形波纹，复古优雅",
        "finger-wave hair, glossy S-shaped vintage waves, retro elegance",
        "finger waves, vintage hairstyle, retro chinese style",
    ),
    # 仙侠 / 玄幻
    (
        "仙侠飞仙髻配散发，上半高髻，下半长发随风飘散",
        "half-up flying-immortal bun, long loose hair flowing in the wind",
        "flying immortal bun, half up hair, flowing long hair, xianxia",
    ),
    (
        "仙侠长发飘散，发丝随风扬起，飘逸出尘",
        "long flowing loose hair, wind-blown strands, ethereal and otherworldly",
        "long flowing hair, wind blown hair, xianxia",
    ),
]

FEMALE_ORNAMENT = [
    (_SKIP, None, None),
    (
        "步摇，垂挂珠串流苏，随动作轻轻摇晃",
        "buyao, dangling hairpin with swaying tassels",
        "buyao, dangling hairpin, swaying tassels, chinese hair ornament",
    ),
    (
        "金步摇，鎏金垂珠步摇，华贵夺目",
        "gold buyao hairpin, gilded dangling hairpin with hanging beads, luxurious and eye-catching",
        "gold buyao hairpin, gilded hairpin, chinese hair ornament",
    ),
    (
        "簪，素雅发簪斜插于发髻",
        "hairpin, a simple elegant pin inserted diagonally into the bun",
        "hairpin, chinese hair ornament",
    ),
    (
        "钗，双股发钗成对插入发髻",
        "hair fork, double-pronged hairpin inserted in pairs",
        "hair fork, double pronged hairpin, chinese hair ornament",
    ),
    (
        "珠钗，珍珠点缀的双股发钗",
        "pearl hairpin, a double-pronged pin adorned with pearls",
        "pearl hairpin, chinese hair ornament",
    ),
    (
        "珍珠发饰，成串珍珠垂落于发髻两侧",
        "pearl-strand hair ornament, strings of pearls cascading on both sides of the bun",
        "pearl hair ornament, pearl strands, chinese hair ornament",
    ),
    (
        "凤冠，华丽凤形金冠，镶嵌宝石与珍珠",
        "phoenix crown, ornate golden phoenix crown set with gems and pearls",
        "phoenix crown, chinese bridal hair ornament",
    ),
    (
        "花冠，鲜花或绢花编成的花环冠饰",
        "floral crown, a wreath of fresh or silk flowers",
        "flower crown, floral hair wreath",
    ),
    (
        "簪花，鬓边簪戴鲜花，明艳生动",
        "fresh flowers tucked in hair, blossoms pinned beside the temple, bright and vivid",
        "fresh flowers in hair, floral hair ornament",
    ),
    (
        "花钿，眉心点缀红色花形额饰",
        "huadian, red floral forehead ornament centered between the brows",
        "huadian, red forehead ornament, chinese hair ornament",
    ),
    (
        "额黄，额间晕染淡黄色妆饰",
        "yellow forehead makeup, soft yellow tint painted across the forehead",
        "yellow forehead makeup, chinese makeup",
    ),
    (
        "面帘，珠串垂帘遮面，朦胧神秘",
        "beaded face veil, strings of beads hanging before the face, hazy and mysterious",
        "beaded face veil, chinese hair ornament",
    ),
    (
        "发带丝绦，素色长丝带系于发髻间，随风飘动",
        "silk hair ribbon, long plain silk ribbons tied into the bun, flowing in the wind",
        "silk hair ribbon, flowing ribbon, chinese hair ornament",
    ),
    (
        "流苏，细密流苏垂落于发间，灵动飘逸",
        "hair tassels, fine tassels hanging among the hair, light and graceful",
        "hair tassels, chinese hair ornament",
    ),
    (
        "玉簪，温润白玉簪斜插于发髻",
        "jade hairpin, warm white jade pin inserted diagonally into the bun",
        "jade hairpin, chinese hair ornament",
    ),
    (
        "点翠发饰，蓝绿色点翠工艺发饰",
        "diancui hair ornament, blue-green kingfisher-feather craft ornament",
        "diancui hair ornament, chinese hair accessory",
    ),
    (
        "梳篦，半月形发梳插于发髻",
        "hair comb, crescent-shaped comb tucked into the bun",
        "hair comb, chinese hair ornament",
    ),
    (
        "珠花发簪，珍珠与点翠簇拥成花形",
        "beaded flower hairpin, pearls and kingfisher-feather clusters in a flower shape",
        "pearl flower hairpin, chinese hair ornament",
    ),
    (
        "金钗，精致金质发钗成对插入发髻",
        "gold hairpins, delicate golden pins inserted in pairs",
        "gold hairpin, chinese hair ornament",
    ),
    (
        "珠串发箍，珍珠串成的发箍环绕额前",
        "pearl headband, a headband of strung pearls around the forehead",
        "pearl headband, chinese hair ornament",
    ),
]

# ---------------------------------------------------------------------------
# 男性：发型 / 配饰
# ---------------------------------------------------------------------------
MALE_HAIR = [
    (_SKIP, None, None),
    (
        "束发，头发全部向后梳拢，以发带束成高髻",
        "hair tied up in a high topknot, hair combed back entirely and bound with a ribbon",
        "topknot, high topknot, ancient chinese male hairstyle",
    ),
    (
        "玉冠束发，长发束起并以玉冠固定，温润端正",
        "long hair tied with a jade guan crown, neat and refined",
        "jade guan crown, topknot, ancient chinese male hairstyle",
    ),
    (
        "发冠束发，发髻高束并以金属发冠装饰，华贵庄重",
        "ornate hair crown, hair tied high beneath a silver or gilded crown, luxurious and solemn",
        "hair crown, silver crown, ancient chinese male hairstyle",
    ),
    (
        "高马尾束发，长发高束成马尾，以发带系紧",
        "high ponytail with hair ribbon, long hair tied high and bound with a ribbon",
        "high ponytail, hair ribbon, ancient chinese male hairstyle",
    ),
    (
        "半束半散，上半部分束成发髻，下半长发自然披散",
        "half-tied long hair, half flowing loose, upper hair gathered into a bun",
        "half tied hair, long hair, ancient chinese male hairstyle",
    ),
    (
        "散发披肩，长发自然垂落，发丝及肩或过肩",
        "loose long hair over shoulders, hair falling naturally past the shoulders",
        "long loose hair, shoulder length hair, ancient chinese male hairstyle",
    ),
    (
        "纶巾束发，头戴纶巾或头巾，儒雅飘逸",
        "scholar's headscarf, lunjin headwear tied around the hair, elegant and flowing",
        "lunjin, scholar headscarf, ancient chinese male headwear",
    ),
    (
        "发簪束发，以木簪横向固定发髻，质朴自然",
        "wooden hairpin holding the topknot, a simple pin fixed across the bun, rustic and natural",
        "wooden hairpin, topknot, ancient chinese male hairstyle",
    ),
    (
        "道士髻，头顶盘成圆形道髻，以木簪固定",
        "Taoist topknot bun, round bun on the crown fixed with a wooden pin",
        "taoist bun, wooden hairpin, ancient chinese hairstyle",
    ),
    (
        "发髻配发带，束发后余出发带飘垂脑后",
        "topknot with headband, ribbon tails hanging behind after tying",
        "topknot, headband, ancient chinese male hairstyle",
    ),
    (
        "幞头束发，头戴黑色软幞头，发髻包裹其中",
        "futou headwear, black soft futou cap wrapping the bun",
        "futou hat, ancient chinese male headwear",
    ),
    (
        "儒巾束发，头戴儒巾，书卷气十足",
        "scholar's headscarf, confucian scholar headwear, literary air",
        "scholar headscarf, ancient chinese male headwear",
    ),
    (
        "冠冕束发，头戴帝王冠冕，长发收于冠下",
        "imperial crown, long hair gathered beneath an ornate ceremonial crown",
        "imperial crown, ancient chinese male hairstyle",
    ),
    (
        "散发配发冠，长发散落肩背，头戴金冠",
        "loose hair with golden crown, long hair flowing over the shoulders beneath an ornate golden crown",
        "golden crown, loose long hair, ancient chinese male hairstyle",
    ),
    (
        "低马尾，长发松松束于脑后，随性自然",
        "low ponytail, long hair loosely tied at the back of the head, casual and natural",
        "low ponytail, long hair",
    ),
    (
        "民国短发，耳上短发利落干净，略带分头",
        "Republican-era short hair, neat cropped hair above the ears, slight side part",
        "short hair, short black hair, side part",
    ),
]

MALE_ORNAMENT = [
    (_SKIP, None, None),
    (
        "玉冠，白玉发冠束于发髻之上",
        "jade crown, white jade crown set over the topknot",
        "jade crown, chinese hair ornament",
    ),
    (
        "金冠，鎏金发冠装饰发髻，华贵庄重",
        "golden crown, gilded crown adorning the bun, luxurious and solemn",
        "golden crown, chinese hair ornament",
    ),
    (
        "银冠，银色发冠束发，清冷利落",
        "silver crown, silver hair crown holding the hair, cool and crisp",
        "silver crown, chinese hair ornament",
    ),
    (
        "玉簪，素白玉簪横穿发髻",
        "jade hairpin, plain white jade pin across the bun",
        "jade hairpin, chinese hair ornament",
    ),
    (
        "木簪，质朴木簪固定发髻",
        "wooden hairpin, rustic wooden pin holding the bun",
        "wooden hairpin, chinese hair ornament",
    ),
    (
        "发带，素色布带束于额前与脑后",
        "headband, plain cloth band tied around the head",
        "headband, chinese hair ribbon",
    ),
    (
        "抹额，绣纹抹额系于额前，英气利落",
        "forehead band, embroidered band across the forehead, crisp and dashing",
        "forehead band, embroidered headband",
    ),
    (
        "纶巾，青丝纶巾束发，儒雅飘逸",
        "scholar's headscarf, silk lunjin tied around the hair, elegant and flowing",
        "lunjin, scholar headscarf, chinese male headwear",
    ),
    (
        "幞头，黑色软幞头，垂脚后垂",
        "futou, black soft futou cap with hanging tails",
        "futou hat, ancient chinese headwear",
    ),
    (
        "乌纱帽，黑色乌纱官帽，端正规整",
        "black gauze official hat, formal and neat",
        "black gauze hat, ancient chinese official headwear",
    ),
    (
        "束发冠，金属束发冠扣于发髻",
        "hair crown ring, metal crown ring clasping the bun",
        "hair crown, chinese hair ornament",
    ),
    (
        "发绳，简洁发绳束起长发",
        "hair tie, a simple cord tied around the hair",
        "hair tie, chinese hairstyle",
    ),
]

# ---------------------------------------------------------------------------
# 发丝质感（男女通用，不含颜色，避免与发色标签冲突）
# ---------------------------------------------------------------------------
HAIR_TEXTURE = [
    (_SKIP, None, None),
    (
        "顺滑长发，发丝根根分明，自然光泽",
        "silky hair with detailed strands and natural gloss",
        "silky hair, detailed hair strands, natural gloss",
    ),
    (
        "柔顺垂坠，发丝细腻服帖",
        "smooth flowing hair, fine and sleek strands",
        "smooth hair, fine strands, sleek hair",
    ),
    (
        "蓬松轻盈，发丝有空气感",
        "soft fluffy hair with airy volume",
        "fluffy hair, airy hair, soft volume",
    ),
    (
        "松散自然，几缕碎发垂落额前",
        "loosely styled hair with natural wispy strands framing the forehead",
        "loose hair, wispy strands, natural hair",
    ),
    (
        "风吹飘动，发丝随风扬起",
        "wind-blown hair, flowing strands lifted by the wind",
        "wind blown hair, flowing hair strands",
    ),
    (
        "缎面光泽，发丝层次清晰",
        "satin-sheen hair, clearly layered strands",
        "satin hair, glossy hair, layered hair strands",
    ),
    (
        "微卷蓬松，发丝柔软有弧度",
        "soft wavy hair, gentle curves and voluminous texture",
        "soft wavy hair, voluminous hair, gentle curls",
    ),
]

# ---------------------------------------------------------------------------
# 气质（男女各自）
# ---------------------------------------------------------------------------
FEMALE_TEMPERAMENT = [
    (_SKIP, None, None),
    ("端庄典雅，举止克制，仪态大方", "dignified and elegant, restrained manners, poised bearing", "dignified, elegant, poised"),
    ("温婉柔美，眉眼含情，气质亲和", "gentle and graceful, affectionate eyes, approachable air", "gentle, graceful, soft"),
    ("清冷出尘，神色淡然，不染尘俗", "cool and ethereal, calm expression, unworldly", "cool, ethereal, aloof"),
    ("娇俏灵动，眼神明亮，俏皮可爱", "charming and lively, bright eyes, playful and cute", "lively, playful, bright eyes"),
    ("雍容华贵，气场强大，贵气逼人", "regal and luxurious, powerful aura, aristocratic presence", "regal, luxurious, noble"),
    ("仙气飘飘，轻盈出尘，如画中仙子", "ethereal fairy-like presence, light and otherworldly, like a painting immortal", "ethereal, fairy-like, otherworldly"),
    ("英气飒爽，目光锐利，巾帼不让须眉", "heroic and dashing, sharp gaze, valiant bearing", "heroic, sharp, valiant"),
    ("哀婉忧郁，眉间含愁，令人怜惜", "sorrowful and melancholic, faint sorrow between the brows, poignant", "melancholic, sorrowful, wistful"),
    ("妩媚风情，眼波流转，明艳动人", "alluring and charming, expressive eyes, radiant beauty", "alluring, charming, radiant"),
    ("书卷才情，文雅知性，沉静内敛", "literary and refined, cultured and intellectual, quiet and reserved", "literary, refined, cultured"),
    ("少女清纯，天真烂漫，清澈干净", "pure maidenly charm, innocent and cheerful, clear and clean", "pure, innocent, youthful"),
    ("古典美人，东方韵味，含蓄隽永", "classical oriental beauty, subtle lasting charm", "classical beauty, oriental charm, elegant"),
]

MALE_TEMPERAMENT = [
    (_SKIP, None, None),
    ("温润如玉，谦和有礼，目光柔和", "gentle as jade, modest and courteous, soft gaze", "gentle, modest, soft gaze"),
    ("冷峻清傲，神色疏离，不怒自威", "cold and proud, distant expression, commanding without anger", "cold, proud, commanding"),
    ("俊朗潇洒，身姿挺拔，风度翩翩", "handsome and dashing, upright posture, elegant demeanor", "handsome, dashing, elegant"),
    ("儒雅书卷，文质彬彬，沉稳内敛", "scholarly and refined, gentle and cultivated, calm and reserved", "scholarly, refined, calm"),
    ("英武刚毅，眉目锋利，气宇轩昂", "martial and resolute, sharp brows, imposing presence", "martial, resolute, imposing"),
    ("出尘仙气，飘逸脱俗，不染凡尘", "ethereal and otherworldly, graceful and unworldly", "ethereal, otherworldly, graceful"),
    ("忧郁深沉，眉间藏事，沉默寡言", "melancholic and deep, stories hidden between the brows, taciturn", "melancholic, deep, taciturn"),
    ("少年意气，明朗张扬，生机勃勃", "youthful spirit, bright and unrestrained, full of vitality", "youthful, bright, energetic"),
    ("沉稳威严，城府深沉，不露喜怒", "composed and authoritative, deep and unreadable, showing no emotion", "authoritative, composed, imposing"),
    ("风流倜傥，洒脱不羁，眉眼含笑", "romantic and free-spirited, unrestrained, smiling eyes", "romantic, free-spirited, smiling"),
    ("仙风道骨，清瘦出尘，淡然自若", "immortal-like bearing, lean and ethereal, serene and detached", "immortal, ethereal, serene"),
    ("古典俊逸，端方持重，气度不凡", "classically handsome, upright and composed, extraordinary bearing", "classical handsome, upright, elegant"),
]

# 标签数据结构：性别标签的 male/female 各自只有一个选项；
# 其余标签的 male/female 为对应性别可选的选项列表，第一项为默认的「不使用」
TAGS = [
    {
        "zh": _GENDER_ZH, "en": _GENDER_EN,
        "male": [(_GENDER_MALE, "male", "male")],
        "female": [(_GENDER_FEMALE, "female", "female")],
    },
    {"zh": "朝代", "en": "Dynasty", "male": DYNASTY, "female": DYNASTY},
    {"zh": "发型", "en": "Hairstyle", "male": MALE_HAIR, "female": FEMALE_HAIR},
    {"zh": "配饰", "en": "Hair Ornament", "male": MALE_ORNAMENT, "female": FEMALE_ORNAMENT},
    {"zh": "发丝质感", "en": "Hair Texture", "male": HAIR_TEXTURE, "female": HAIR_TEXTURE},
    {"zh": "气质", "en": "Temperament", "male": MALE_TEMPERAMENT, "female": FEMALE_TEMPERAMENT},
]


def _gender_options(tag, gender_key):
    return [zh for zh, _, _ in tag[gender_key]]


def _lookup(tag, value, gender_key):
    return next(
        ((en, sd) for zh, en, sd in tag[gender_key] if zh == value),
        (None, None),
    )


class GuofengHairstylePromptBuilder:
    """国风发型/发饰提示词生成器：按性别分组的下拉标签，输出中/英/tag 三种提示词"""

    @classmethod
    def INPUT_TYPES(cls):
        required = {}
        for tag in TAGS:
            male = _gender_options(tag, "male")
            female = _gender_options(tag, "female")
            # 合并列表用于后端校验；前端按 mate_male / mate_female 动态过滤
            merged = list(dict.fromkeys(male + female))
            required[tag["zh"]] = (
                merged,
                {"mate_male": male, "mate_female": female},
            )
        required[_OTHER_ZH] = (
            "STRING",
            {"multiline": True, "default": "", "dynamicPrompts": False},
        )
        required[_TRANSLATE_TOGGLE] = ("BOOLEAN", {"default": False})
        return {"required": required}

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("prompt_zh", "prompt_en", "tags_en")
    FUNCTION = "execute"
    CATEGORY = "Mate/国风"
    DESCRIPTION = "按性别选择国风发型与发饰标签，同时输出中文、英文、英文 tag 三种格式"

    def execute(self, **kwargs):
        gender_key = "female" if kwargs.get(_GENDER_ZH) == _GENDER_FEMALE else "male"
        zh_lines = []
        en_lines = []
        sd_tags = []
        for tag in TAGS:
            # 性别只用于切换选项分组，不作为提示词内容输出
            if tag["zh"] == _GENDER_ZH:
                continue
            value = kwargs.get(tag["zh"])
            if value is None or value == _SKIP:
                continue
            # 只处理与当前性别匹配的选项，忽略不匹配的残留值
            if value not in [zh for zh, _, _ in tag[gender_key]]:
                continue
            zh_lines.append(f"[{tag['zh']}]{value}")
            en_value, sd_value = _lookup(tag, value, gender_key)
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
    "MateGuofengHairstylePromptBuilder": GuofengHairstylePromptBuilder,
}

# 节点在界面上显示的名称
NODE_DISPLAY_NAME_MAPPINGS = {
    "MateGuofengHairstylePromptBuilder": "国风发型/发饰提示词生成器 (Mate)",
}
