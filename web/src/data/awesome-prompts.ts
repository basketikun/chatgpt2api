export type AwesomePromptItem = {
  caseNumber: number;
  title: string;
  originalTitle: string;
  sourceUrl: string;
  author: string;
  authorUrl: string;
  originalPrompt: string;
  prompt: string;
  translated: boolean;
};

export type AwesomePromptSection = {
  title: string;
  items: AwesomePromptItem[];
};

export const awesomePromptSections: AwesomePromptSection[] = [
  {
    "title": "人像与摄影案例",
    "items": [
      {
        "caseNumber": 1,
        "title": "便利店霓虹灯肖像",
        "sourceUrl": "https://x.com/BubbleBrain/status/2045167461147042202",
        "author": "@BubbleBrain",
        "authorUrl": "https://x.com/BubbleBrain",
        "originalPrompt": "35mm film photography with harsh convenience store fluorescent lighting mixed with colorful neon signs from outside, authentic film grain, high contrast, slight color cast, cinematic street editorial style, intimate medium shot, early 20s sexy Chinese female idol with ultra-realistic delicate refined Chinese features, seductive almond-shaped fox eyes with natural double eyelids, high nose bridge, small sharp V-shaped jawline, flawless porcelain skin with cool ivory undertone and visible specular highlights from fluorescent light, subtle skin texture and micro pores, natural dewy makeup with soft flush on cheeks, glossy natural pink lips slightly parted, subtle natural freckles across nose and cheeks, long dark brown hair in a messy high ponytail with many loose strands falling around face and neck, wearing an oversized white button-up shirt as the only top, unbuttoned at the top with deep cleavage and loosely tied at the waist, paired with a tiny black pleated mini skirt, barefoot in simple white slides, seductive casual leaning pose against the glass door of a 24-hour convenience store at late night, body slightly arched, one leg bent with foot resting against the door frame, the other leg straight, one hand holding a bottle of iced drink, the other hand lightly pulling the hem of her mini skirt, intensely seductive playful yet slightly vulnerable gaze straight at the viewer with soft doe eyes full of quiet temptation and teasing smile, bright cold fluorescent store light from inside mixed with pink and blue neon glow from outside signs, realistic reflections on glass door, blurred convenience store interior with shelves and snacks in background, authentic 35mm film color grading with harsh lighting and neon accents, extremely sharp yet soft skin rendering, natural hair strands, realistic fabric wrinkles and drape on the oversized shirt and mini skirt, no plastic skin, no digital over-sharpening, no airbrushing, no blemishes, no moles, no oily skin, no watermark, no text, authentic late-night convenience store atmosphere",
        "originalTitle": "Convenience Store Neon Portrait",
        "prompt": "35mm胶片摄影，刺眼的便利店荧光灯与外面的彩色霓虹灯混合在一起，真实的胶片颗粒，高对比度，轻微偏色，电影街头编辑风格，亲密的中景，20岁出头的性感中国女偶像，超写实精致的中国特色，诱人的杏仁形狐狸眼，自然的双眼皮，高鼻梁，小尖V形下巴，完美的瓷质皮肤，冷象牙底色和荧光灯下可见的镜面高光，微妙的皮肤纹理和微毛孔，自然水润的妆容，脸颊上有柔和的红晕，光泽自然的粉色嘴唇微微张开，鼻子和脸颊上有微妙的天然雀斑，深棕色的长发扎成凌乱的高马尾，有很多松散的发丝落在脸和脖子上，唯一的上衣穿着一件超大的白色系扣衬衫，上衣没有扣子，深乳沟，松散地系在腰间，搭配黑色的小百褶迷你裙，赤脚穿着简单的白色拖鞋，靠在玻璃门上的姿势诱人休闲深夜24小时营业的便利店，身体微微弓起，一腿弯曲，脚抵在门框上，另一腿伸直，一手拿着一瓶冰饮，一手轻轻拉着迷你裙的下摆，极度诱惑俏皮又略带脆弱的目光直视着观者，温柔的母鹿眼里充满安静的诱惑和挑逗的微笑，店内明亮的冷光荧光灯与外面招牌的粉色和蓝色霓虹灯混合在一起，玻璃门上的真实倒影，模糊便利店内部，背景是货架和零食，真实的 35 毫米胶片调色，刺眼的灯光和霓虹灯口音，极其锐利而柔软的皮肤渲染，自然的发丝，逼真的织物皱纹和超大衬衫和迷你裙的垂坠感，无塑料皮肤，无数字过度锐化，无喷枪，无瑕疵，无痣，无油性皮肤，无水印，无文字，真实的深夜便利店氛围",
        "translated": true
      },
      {
        "caseNumber": 2,
        "title": "电影最小肖像",
        "sourceUrl": "https://x.com/iam_miharbi/status/2045151354679665101",
        "author": "@iam_miharbi",
        "authorUrl": "https://x.com/iam_miharbi",
        "originalPrompt": "Generate a cinematic minimal portrait of a solitary man standing in an intense orange to red gradient environment, strong silhouette lighting, deep shadow contrast, reflective glossy floor, symmetrical composition, minimal",
        "originalTitle": "Cinematic Minimal Portrait",
        "prompt": "生成一个电影般的最小肖像，一个孤独的男人站在强烈的橙色到红色渐变环境中，强烈的轮廓照明，深阴影对比度，反光光泽地板，对称构图，最小",
        "translated": true
      },
      {
        "caseNumber": 3,
        "title": "日本温泉旅馆肖像",
        "sourceUrl": "https://x.com/BubbleBrain/status/2045092449803284923",
        "author": "@BubbleBrain",
        "authorUrl": "https://x.com/BubbleBrain",
        "originalPrompt": "35mm film photography, warm vintage Japanese onsen ryokan aesthetic, soft ambient wooden lantern lighting mixed with gentle natural window light, subtle film grain, gentle color shift, high atmosphere editorial style, intimate medium shot, early 20s beautiful Chinese female idol with ultra-realistic delicate refined Chinese features, seductive almond-shaped fox eyes with natural double eyelids, high nose bridge, small sharp V-shaped jawline, flawless porcelain skin with warm ivory undertone, visible subtle skin texture and micro pores, soft natural makeup with dewy glow, subtle rosy flush on cheeks, natural soft pink lips slightly parted, long dark brown hair tied in a loose low bun with some messy strands falling around face and neck, wearing a loose white yukata (traditional Japanese bathrobe) deliberately slipped off one shoulder and loosely tied at the waist, the fabric slightly open revealing smooth skin and subtle cleavage, barefoot, seductive relaxed sitting pose on the edge of a traditional wooden engawa veranda at a vintage onsen ryokan, body slightly turned toward the camera, one leg bent with foot resting on the wooden floor, the other leg gently dangling, one hand lightly holding the yukata collar, the other hand resting on the wooden floor behind her for support, softly arched back to gently accentuate curves, intensely seductive yet gentle and inviting gaze straight at the viewer with soft doe eyes full of quiet temptation and warmth, warm wooden interior with paper sliding doors and distant steaming hot spring in soft focus, gentle rim lighting highlighting skin and fabric texture, authentic vintage film color grading with warm tones, extremely sharp yet soft skin rendering, natural hair strands, realistic fabric wrinkles and drape on the yukata, no plastic skin, no digital over-sharpening, no airbrushing, no blemishes, no moles, no oily skin, no watermark, no text, authentic 35mm film Japanese onsen ryokan atmosphere",
        "originalTitle": "Japanese Onsen Ryokan Portrait",
        "prompt": "35mm胶片摄影，温暖复古的日式温泉旅馆美学，柔和的木灯笼灯光与柔和的自然窗光混合，细腻的胶片颗粒，柔和的色移，高调的编辑风格，亲密的中景，20岁出头的美丽中国女偶像，超写实精致的中国特色，诱人的杏仁形狐狸眼与自然的双眼皮，高鼻梁，小尖V形下颌线，完美的瓷质皮肤带有温暖的象牙色底色，可见微妙的皮肤纹理和微细毛孔，柔和自然的妆容带着露水的光泽，脸颊上有微妙的红晕，自然柔软的粉红色嘴唇微微分开，长长的深棕色头发扎成松散的低发髻，一些凌乱的发丝落在脸上和脖子上，穿着一件宽松的白色浴衣（日本传统浴袍）故意从肩膀上滑下来，松松地系在腰上，织物微微张开，露出光滑的皮肤和微妙的乳沟，赤脚，在老式温泉的传统木制远川阳台边缘摆出诱人的放松坐姿旅馆，身体微微转向镜头，一条腿弯曲，脚踩在木地板上，另一条腿轻轻悬垂，一手轻轻握住浴衣领子，另一只手支撑在身后的木地板上，轻轻弓起背部，轻轻突出曲线，强烈诱惑而又温柔诱人的目光直视观看者，柔和的母鹿眼睛充满安静的诱惑和温暖，温暖的木质内饰，纸质推拉门，远处热气腾腾的温泉，柔和的焦点，温柔的边缘灯光突出皮肤和织物纹理，正宗复古胶片暖色调调色，极其锐利而柔软的皮肤渲染，自然发丝，真实的织物皱纹和浴衣上的垂坠感，无塑料皮肤，无数字过度锐化，无喷枪，无瑕疵，无痣，无油性皮肤，无水印，无文字，正宗的35毫米胶片日本温泉旅馆氛围",
        "translated": true
      },
      {
        "caseNumber": 4,
        "title": "35mm 闪光灯编辑肖像",
        "sourceUrl": "https://x.com/BubbleBrain/status/2045052982728016131",
        "author": "@BubbleBrain",
        "authorUrl": "https://x.com/BubbleBrain",
        "originalPrompt": "35mm color film photography with harsh direct on-camera flash, specular highlights on skin and clothing, strong catchlights in eyes, high contrast flash illumination, authentic film grain and color shift, high fashion fresh innocent basketball court editorial style, intimate first-person low-angle POV shot from below, early 20s sexy Chinese female idol with ultra-realistic delicate refined Chinese features, seductive almond-shaped fox eyes with natural double eyelids, high nose bridge, small sharp V-shaped jawline, flawless realistic porcelain skin with cool ivory undertone and visible flash specular highlights, fine delicate skin texture with subtle pores micro details and natural dewy glow under flash, fresh natural sporty makeup with soft dewy glow, subtle natural flush on cheeks, natural pink lips slightly parted, subtle natural freckles across nose and cheeks, long dark brown hair tied in a high playful ponytail with some loose strands framing the face and realistic loose strands, wearing a loose white tank top and white high-waisted basketball shorts, white knee-high sports socks, seductive natural leaning pose against the basketball hoop pole on the outdoor court at dusk, body angled sideways with naturally arched back and hips gently pushed back to accentuate perky round hips and sexy butt curve, one leg naturally extended forward toward the camera and the other leg slightly bent to emphasize long sexy legs, both hands lightly resting on the basketball pole at shoulder height, intensely seductive playful yet pitiable doe-eyed gaze straight at the viewer with soft vulnerable longing eyes and a gentle teasing smile full of quiet temptation and desire, harsh direct on-camera flash creating sharp specular highlights and strong catchlights, background with blurred basketball court and hoop under dusk sky, high contrast film color grading with natural flash look, extremely sharp yet soft skin rendering with authentic 35mm direct flash aesthetic, natural hair strands, realistic fabric texture on tank top and shorts with socks detail, no plastic skin, no digital over-sharpening, no airbrushing, no blemishes, no moles, no oily skin, no watermark, no text, authentic 35mm direct flash film basketball court look --ar 9:16",
        "originalTitle": "35mm Flash Editorial Portrait",
        "prompt": "35mm彩色胶片摄影，严酷的机上闪光灯，皮肤和衣服上的镜面高光，眼睛的强烈聚光，高对比度的闪光照明，真实的胶片颗粒和色彩偏移，时尚清新无辜的篮球场编辑风格，亲密的第一人称低角度视角从下面拍摄，20岁出头的性感中国女偶像，超写实精致的中国特色，诱人的杏仁形狐狸眼，自然的双眼皮，高高的鼻梁，小尖的V形下颌线，完美无瑕的逼真瓷皮皮肤清凉的象牙色底色和明显的闪光镜面高光，细腻的肌肤纹理，微妙的毛孔微细节和闪光下的自然露水光泽，清新自然的运动妆容，柔和的水润光泽，脸颊上有微妙的自然红晕，自然的粉红色嘴唇微张，鼻子和脸颊上有微妙的自然雀斑，长长的深棕色头发扎成高俏皮的马尾辫，一些松散的发丝勾勒出脸型和逼真的松散的发丝，穿着宽松的白色背心和白色高腰篮球短裤，白色及膝运动袜，黄昏时室外球场上篮球架自然倾斜的诱人姿势，身体侧倾，背部自然拱起，臀部轻轻向后推，凸显挺括的圆臀和性感的臀部曲线，一腿自然向前伸向镜头，另一腿微弯，凸显修长性感双腿，双手轻轻搭在与肩同高的篮球杆上，极度诱惑的俏皮又可怜的母鹿般的目光直视着观众，眼神温柔脆弱渴望，充满安静诱惑和欲望的温柔挑逗的微笑，刺眼的机上直闪产生锐利的镜面高光和强烈的聚光灯，黄昏天空下模糊的篮球场和篮圈背景，自然闪光外观的高对比度胶片调色，极其锐利而柔软的皮肤渲染，真实的35毫米直闪美学，自然的发丝，背心和短裤上真实的织物纹理，带有袜子细节，无塑料皮肤，无数字过度锐化，无喷枪，无瑕疵，无痣，无油皮，无水印，无文字，正品35mm直闪膜篮球场外观--ar 9:16",
        "translated": true
      },
      {
        "caseNumber": 5,
        "title": "镜子自拍卧室肖像",
        "sourceUrl": "https://x.com/Shinning1010/status/2045002808903020962",
        "author": "@Shinning1010",
        "authorUrl": "https://x.com/Shinning1010",
        "originalPrompt": "A stunning 18-year-old Chinese girl with a youthful, pure face and realistic skin texture, sitting on a cozy, slightly messy bed in her bedroom. She is taking a mirror selfie with a smartphone, capturing a natural and intimate moment. Wearing casual gray loungewear and neat white crew socks. Soft natural light (golden hour) streams in from a side window, creating a warm, moody, and cinematic atmosphere. 35mm lens, sharp focus on the subject in the mirror, depth of field with a beautifully blurred background (bokeh). Photorealistic, 8K, high resolution, studio quality, masterpiece.\nNegative Prompts: no extra limbs, no deformed hands, no blur, no noise, no watermark, no text, no cartoon/anime style. Aspect Ratio: 3:4.",
        "originalTitle": "Mirror Selfie Bedroom Portrait",
        "prompt": "一个十八岁的漂亮中国女孩，有着青春清纯的脸庞和逼真的肌肤纹理，坐在卧室一张舒适而略显凌乱的床上。她正在用智能手机对着镜子自拍，捕捉自然而亲密的时刻。穿着休闲的灰色家居服和整洁的白色圆袜。柔和的自然光（黄金时段）从侧窗射入，营造出温暖、喜怒无常的电影氛围。 35 毫米镜头，镜子中的拍摄对象清晰对焦，景深优美，背景虚化（散景）。逼真、8K、高分辨率、工作室品质、杰作。\n负面提示：没有多余的肢体，没有变形的手，没有模糊，没有噪音，没有水印，没有文字，没有卡通/动漫风格。长宽比：3:4。",
        "translated": true
      },
      {
        "caseNumber": 6,
        "title": "柔和通风的 35 毫米肖像",
        "sourceUrl": "https://x.com/BubbleBrain/status/2046115431144902732",
        "author": "@BubbleBrain",
        "authorUrl": "https://x.com/BubbleBrain",
        "originalPrompt": "Analog 35mm film photography, soft airy Japanese-style aesthetic, gentle diffused natural window light, slight overexposure, pastel tones, low contrast, soft highlights, minimal indoor setting near a window with white curtains, clean light-colored wall, natural composition, eye-level, slightly closer full-body framing (mid-thigh to head), young East Asian woman, natural minimal makeup, soft realistic skin texture, long slightly messy dark hair, oversized white button-up shirt, light casual shorts, barefoot, simple and relaxed styling, standing naturally with relaxed posture, arms loosely at sides or slightly behind, facing camera, gentle soft smile, subtle stillness, focus on light, air, and quiet everyday mood, soft film grain, dreamy and understated atmosphere --ar 9:16",
        "originalTitle": "Soft Airy 35mm Portrait",
        "prompt": "模拟35毫米胶片摄影，柔和通风的日式美学，柔和的漫射自然窗户光，轻微过度曝光，柔和的色调，低对比度，柔和的高光，靠近窗户的最小室内环境，白色窗帘，干净的浅色墙壁，自然构图，眼睛水平，稍微接近的全身取景（大腿中部到头部），年轻的东亚女性，自然简约的妆容，柔软逼真的皮肤纹理，略显凌乱的长黑发，超大的白色系扣衬衫，浅色休闲短裤，赤足，简单轻松的造型，以轻松的姿势自然站立，双臂放松地放在两侧或稍向后，面对镜头，温柔的微笑，微妙的静止，专注于光线、空气和安静的日常心情，柔和的胶片颗粒，梦幻而低调的氛围 --ar 9:16",
        "translated": true
      },
      {
        "caseNumber": 7,
        "title": "奢华魅力美女肖像",
        "sourceUrl": "https://x.com/patrickassale/status/2044581766309060765",
        "author": "@patrickassale",
        "authorUrl": "https://x.com/patrickassale",
        "originalPrompt": "Luxury Glam Beauty Portrait:, Beautiful Black woman, youthful spirit, creamy vanilla, silk press, mahogany red, subtle confidence, textured fabric, sapphire blue, minimal jewelry, beachside breeze, lens flare effect, nostalgic, cinematic lens, symmetrical composition, soft focus, high fashion photography, monochromatic, dewy finish, mysterious tension, layered elements",
        "originalTitle": "Luxury Glam Beauty Portrait",
        "prompt": "奢华魅力美容肖像：，美丽的黑人女性，青春活力，奶油香草，丝印机，桃花心木红，微妙的自信，纹理面料，宝石蓝，简约珠宝，海滨微风，镜头眩光效果，怀旧，电影镜头，对称构图，软焦点，高级时尚摄影，单色，露水完成，神秘张力，分层元素",
        "translated": true
      },
      {
        "caseNumber": 8,
        "title": "9:16 Cosplayer肖像截图",
        "sourceUrl": "https://x.com/Zoulinshen/status/2045082518089810073",
        "author": "@Zoulinshen",
        "authorUrl": "https://x.com/Zoulinshen",
        "originalPrompt": "生成一张竖版手机截图风格的图片，整体比例接近 9:16。画面中心偏上是一位真人 coser，扮演（角色名称）的二次元角色。人物为写实风格，但五官略带动漫感，皮肤细腻，眼睛稍大，表情温柔地看向镜头，坐在室内的休闲场景中，例如咖啡厅或酒吧吧台前，背景有符合场景的道具。画面最上方加入手机系统状态栏 UI，包括时间、电量、信号、网络等图标，让整张图看起来像手机截图。画面底部叠加一块宽大的半透明 galgame 风格对话框，对话框左侧放一个与画面人物对应的动漫或 Q 版头像；对话框右侧排版文字：第一行用较大字体显示与前面相同的角色名字，下面一到两行显示一段适合这个角色人设的、温柔治愈风格的简体中文台词，由你自动创作。再在对话框下方加一条操作栏，仿照 galgame UI。整体风格高清、细节丰富、光线柔和、二次元与真人写真自然融合。",
        "originalTitle": "9:16 Cosplayer Portrait Screenshot",
        "prompt": "生成一张竖版手机截图风格的图片，整体比例接近 9:16。画面中心偏上是一位真人 coser，扮演（角色名称）的二次元角色。人物为写实风格，但五官略带动漫感，皮肤细腻，眼睛稍大，表情温柔地看向镜头，坐在室内的休闲场景中，例如咖啡厅或酒吧吧台前，背景有符合场景的道具。画面最上方加入手机系统状态栏 UI，包括时间、电量、信号、网络等图标，让整张图看起来像手机截图。画面底部叠加一块宽大的半透明 galgame 风格对话框，对话框左侧放一个与画面人物对应的动漫或 Q 版头像；对话框右侧排版文字：第一行用较大字体显示与前面相同的角色名字，下面一到两行显示一段适合这个角色人设的、温柔治愈风格的简体中文台词，由你自动创作。再在对话框下方加一条操作栏，仿照 galgame UI。整体风格高清、细节丰富、光线柔和、二次元与真人写真自然融合。",
        "translated": false
      },
      {
        "caseNumber": 9,
        "title": "城市折返街景肖像",
        "sourceUrl": "https://x.com/Tz_2022/status/2045892003775361198",
        "author": "@Tz_2022",
        "authorUrl": "https://x.com/Tz_2022",
        "originalPrompt": "该画面为中近景，采用平视镜头，聚焦于一位年轻女性。她以七分身镜头呈现，身体坐姿略带倾斜，臀部向后撅起，双腿自然交叠，左腿在前，右腿在后，膝盖微屈。她将上半身向右后方扭转，头部则转向镜头方向，形成一个经典的“回眸”姿态，目光直视镜头，眼神清澈而略带一丝俏皮。她的发型是蓬松的棕色齐肩短发，刘海自然垂落，发尾微卷，妆容清淡自然，仅在眼部有轻微眼线勾勒，唇色为自然裸粉。画面整体采用自然日光滤镜，光线从画面左上方斜射入，形成柔和的逆光轮廓，面部和身体右侧被温暖的金色光线照亮，左侧则形成自然的阴影过渡，增强了立体感。灯光效果是明亮的自然光，带有轻微的镜头眩光，营造出午后阳光的氛围。拍摄角度为平视，构图上，人物主体位于画面中偏右位置，背景中的斑马线与道路线条形成自然的引导线，将视线引向人物。背景为城市街道，包含道路、斑马线、绿化带和远处的车辆，背景被适度虚化，但依然可辨识出树木、护栏和停放的电动车等元素，构图上利用了三分法，人物位于右侧三分之一处，增强了画面的平衡感。主体穿着一件军绿色迷彩图案的连帽卫衣，下身搭配黑色短裤，脚穿白色高帮运动鞋配白色中筒袜。背包为黑色，带有橙黄色装饰条纹和一个橙色毛绒挂件，材质为帆布和皮革拼接。整体风格为街头休闲风，肢体语言放松自然，表情略带好奇与俏皮，整体呈现出一种随性、青春、充满活力的都市少女形象。",
        "originalTitle": "Urban Turn-Back Street Portrait",
        "prompt": "该画面为中近景，采用平视镜头，聚焦于一位年轻女性。她以七分身镜头呈现，身体坐姿略带倾斜，臀部向后撅起，双腿自然交叠，左腿在前，右腿在后，膝盖微屈。她将上半身向右后方扭转，头部则转向镜头方向，形成一个经典的“回眸”姿态，目光直视镜头，眼神清澈而略带一丝俏皮。她的发型是蓬松的棕色齐肩短发，刘海自然垂落，发尾微卷，妆容清淡自然，仅在眼部有轻微眼线勾勒，唇色为自然裸粉。画面整体采用自然日光滤镜，光线从画面左上方斜射入，形成柔和的逆光轮廓，面部和身体右侧被温暖的金色光线照亮，左侧则形成自然的阴影过渡，增强了立体感。灯光效果是明亮的自然光，带有轻微的镜头眩光，营造出午后阳光的氛围。拍摄角度为平视，构图上，人物主体位于画面中偏右位置，背景中的斑马线与道路线条形成自然的引导线，将视线引向人物。背景为城市街道，包含道路、斑马线、绿化带和远处的车辆，背景被适度虚化，但依然可辨识出树木、护栏和停放的电动车等元素，构图上利用了三分法，人物位于右侧三分之一处，增强了画面的平衡感。主体穿着一件军绿色迷彩图案的连帽卫衣，下身搭配黑色短裤，脚穿白色高帮运动鞋配白色中筒袜。背包为黑色，带有橙黄色装饰条纹和一个橙色毛绒挂件，材质为帆布和皮革拼接。整体风格为街头休闲风，肢体语言放松自然，表情略带好奇与俏皮，整体呈现出一种随性、青春、充满活力的都市少女形象。",
        "translated": false
      },
      {
        "caseNumber": 10,
        "title": "山姆·奥尔特曼滑板公园快照",
        "sourceUrl": "https://x.com/Malek1173989/status/2045836887684694395",
        "author": "@Malek1173989",
        "authorUrl": "https://x.com/Malek1173989",
        "originalPrompt": "\"Sam Altman on a skateboard at a skatepark with no people.\"",
        "originalTitle": "Sam Altman Skatepark Snapshot",
        "prompt": "“萨姆·奥尔特曼在一个无人的滑板公园里玩滑板。”",
        "translated": true
      },
      {
        "caseNumber": 11,
        "title": "韩国偶像 3x3 网格肖像",
        "sourceUrl": "https://x.com/BubbleBrain/status/2046268941941850575",
        "author": "@BubbleBrain",
        "authorUrl": "https://x.com/BubbleBrain",
        "originalPrompt": "9:16 vertical, Korean idol portrait photoshoot, 3x3 grid (nine frames), same person in all images, consistent facial features and styling, soft black mist filter effect, lowered contrast, blooming highlights, subtle glow around light sources",
        "originalTitle": "Korean Idol 3x3 Grid Portrait",
        "prompt": "9:16垂直，韩国偶像人像拍摄，3x3网格（九帧），所有图像中同一个人，面部特征和造型一致，柔和的黑雾滤镜效果，降低对比度，高光晕染，光源周围的微妙发光",
        "translated": true
      },
      {
        "caseNumber": 12,
        "title": "CCD相机闪光灯韩国偶像",
        "sourceUrl": "https://x.com/BubbleBrain/status/2046190539213885806",
        "author": "@BubbleBrain",
        "authorUrl": "https://x.com/BubbleBrain",
        "originalPrompt": "mobile phone photo, old CCD camera aesthetic, harsh flash, grainy, dim messy indoor lighting, candid snapshot feeling, slight motion blur, young Korean female idol, soft innocent look",
        "originalTitle": "CCD Camera Flash Korean Idol",
        "prompt": "手机拍照，老式CCD相机审美，刺眼的闪光，颗粒感，昏暗凌乱的室内灯光，抓拍的抓拍感，轻微的运动模糊，年轻的韩国女偶像，柔和无辜的样子",
        "translated": true
      },
      {
        "caseNumber": 13,
        "title": "韩国偶像 3x3 拼贴肖像",
        "sourceUrl": "https://x.com/BubbleBrain/status/2046151898621993364",
        "author": "@BubbleBrain",
        "authorUrl": "https://x.com/BubbleBrain",
        "originalPrompt": "9:16 vertical — a 3x3 grid collage (nine images) forming a Korean idol portrait photoshoot series. Each frame features the same young Korean female idol, maintaining 100% consistency in facial features, proportions, hairstyle, and identity across all nine shots.   Natural, ultra-realistic skin texture, no retouching, no smoothing. Clean idol-style minimal makeup, soft glow, subtle imperfections.   Hair: long, voluminous dark hair, slightly tousled, consistent across all frames (natural loose flow, slight movement).  Outfit: cohesive Korean idol photoshoot styling — white shirt + short bottoms (or simple neutral-toned outfit), youthful, clean, slightly casual but styled. Same outfit across all frames.  Setting: minimal studio or simple indoor environment (plain wall, soft window light, clean background). Focus on subject, not environment.  Lighting: soft diffused natural light, gentle highlights, low contrast, slightly airy tones, subtle film-like softness.  Camera style: intimate portrait photography, slightly handheld feel, subtle imperfections (minor grain, slight blur in motion frames, imperfect framing).  Frame breakdown (3x3 grid):  Top row: - Top left: standing naturally, looking slightly away, relaxed expression - Top center: facing camera, casual mid-motion (hair or body slight movement) - Top right: slight side angle, soft gaze, natural candid feel  Middle row: - Center left: looking slightly upward, soft thoughtful expression - Center: close-up portrait, direct eye contact, gentle idol smile - Center right: turning body slightly, mid-motion candid frame  Bottom row: - Bottom left: seated or leaning casually, relaxed posture - Bottom center: back partially turned, looking over shoulder toward camera - Bottom right: standing close to frame, slightly playful or soft expression  Mood: Korean idol photobook / photocard aesthetic, intimate, soft, natural, everyday charm.  Quality: ultra-realistic, 8K detail, subtle analog film grain, natural imperfections, soft dreamy tone",
        "originalTitle": "Korean Idol 3x3 Collage Portrait",
        "prompt": "9:16 垂直 — 3x3 网格拼贴（九张图像）形成韩国偶像肖像摄影系列。每帧都是同一位年轻的韩国女偶像，九个镜头的面部特征、比例、发型和身份都保持 100% 的一致性。   自然、超真实的皮肤纹理，无需修饰、无需平滑。干净的偶像式简约妆容，柔和的光泽，微妙的瑕疵。   头发：长而浓密的深色头发，略微凌乱，所有框架一致（自然松散，轻微移动）。  穿搭：有凝聚力的韩国偶像写真造型——白衬衫+短裤（或者简单的中性色调穿搭），青春干净，略显休闲但有型。所有镜框均配备相同的服装。  环境：最小的工作室或简单的室内环境（朴素的墙壁、柔和的窗光、干净的背景）。专注于主题，而不是环境。  灯光：柔和的漫射自然光、柔和的高光、低对比度、略显空灵的色调、微妙的胶片般的柔和度。  相机风格：亲密的人像摄影，略微手持的感觉，微妙的缺陷（轻微颗粒，运动帧中的轻微模糊，不完美的取景）。  画面分解（3x3网格）：顶行： - 左上：自然站立，稍稍远视，表情放松 - 上中：面对镜头，随意的中动（头发或身体轻微移动） - 右上：轻微侧角，柔和的目光，自然坦率的感觉中行： - 中左：稍微向上看，柔和深思的表情 - 中：特写肖像，直接目光接触，温柔的偶像微笑 - 右中：稍微转动身体，中动拍摄镜头下行： - 左下：坐着或倾斜随意、放松的姿势 - 下中：背部部分转动，越过肩膀看向相机 - 右下：靠近画面站立，略带俏皮或柔和的表情 心情：韩国偶像写真集/照片卡审美，亲密，柔和，自然，日常魅力。  品质：超真实、8K 细节、微妙的模拟胶片颗粒、自然瑕疵、柔和梦幻的色调",
        "translated": true
      },
      {
        "caseNumber": 14,
        "title": "柔和的黑雾社论肖像",
        "sourceUrl": "https://x.com/BubbleBrain/status/2046434670724907395",
        "author": "@BubbleBrain",
        "authorUrl": "https://x.com/BubbleBrain",
        "originalPrompt": "9:16 vertical — editorial portrait, single subject  soft black mist filter, subtle haze, gentle highlight bloom, muted tones  minimal indoor space, clean background, slight texture  young Korean woman, minimal makeup, natural skin texture  outfit: fitted ribbed knit top or soft camisole layered under a loose shirt, paired with high-waisted shorts or skirt; fabric slightly clings to body shape, soft and natural, no revealing elements  hair: slightly messy, natural volume  pose: sitting on floor with one leg bent and the other relaxed, body slightly leaning, shoulders not aligned, head tilted  composition: subject slightly off-center, negative space present  expression: calm, slightly distant, natural lips  lighting: soft side light, gentle shadow falloff  mood: understated, quiet, subtly sensual through natural body lines, relaxed and unposed  quality: fine grain, slight softness, realistic look",
        "originalTitle": "Soft Black Mist Editorial Portrait",
        "prompt": "9:16 垂直 — 社论肖像，单主体柔和的黑雾滤镜，微妙的雾霾，柔和的高光绽放，柔和的色调最小的室内空间，干净的背景，轻微的质感韩国年轻女性，简约的妆容，自然的皮肤纹理服装：合身的罗纹针织上衣或柔软的吊带背心叠在宽松的衬衫下，搭配高腰短裤或裙子；面料略微贴合身体形状，柔软自然，无暴露元素 头发：略显凌乱，自然体积 姿势：坐在地板上，一腿弯曲，另一腿放松，身体略微倾斜，肩膀不对齐，头部倾斜 构图：拍摄对象稍微偏离中心，负空间呈现 表情：平静，稍远，自然的嘴唇 照明：柔和的侧光，柔和的阴影衰减 情绪：低调，安静，通过自然的身体线条隐约感性，放松和不摆姿势 质量：细粒，轻微柔软，逼真的外观",
        "translated": true
      },
      {
        "caseNumber": 15,
        "title": "富士胶片草莓学校肖像",
        "sourceUrl": "https://x.com/BubbleBrain/status/2046483268019884384",
        "author": "@BubbleBrain",
        "authorUrl": "https://x.com/BubbleBrain",
        "originalPrompt": "9:16 vertical — Japanese Fuji film style portrait, single subject  Fujifilm analog aesthetic (Pro 400H / Superia feel), soft pastel tones, slight green-magenta shift, low contrast, gentle highlight roll-off, fine film grain, subtle halation, slight vignette  bright natural daylight, diffused sunlight through window, soft shadows, airy atmosphere  young Japanese female idol, natural minimal makeup, fresh glowing skin, realistic texture, slight imperfections  outfit: Japanese school uniform (sailor-style or blazer uniform), neatly styled, non-revealing, youthful and clean  hair: natural dark hair, straight or softly flowing, a few loose strands  pose: front-facing or slight angle toward camera, relaxed posture; one hand gently holding a strawberry near lips, mid-action as if about to take a bite; shoulders relaxed, subtle natural body curve  expression: soft playful gaze, light smile or neutral lips, gentle eye contact with camera  setting: minimal indoor near window or simple outdoor corner, clean background, everyday atmosphere  composition: slightly off-center framing, intimate distance, candid feel  mood: fresh, youthful, sweet everyday moment, understated charm  quality: ultra-realistic, analog film look, natural imperfections, soft dreamy finish",
        "originalTitle": "Fujifilm Strawberry School Portrait",
        "prompt": "9:16 垂直 — 日本富士胶片风格肖像，单主体富士胶片模拟美学（Pro 400H / Superia 感觉），柔和的色调，轻微的绿色-洋红色偏移，低对比度，柔和的高光滚降，精细的胶片颗粒，微妙的光晕，轻微的晕影明亮的自然日光，透过窗户的漫射阳光，柔和的阴影，通风的氛围年轻的日本女偶像，自然简约的妆容，清新发光的皮肤，逼真的质感，轻微的瑕疵服装：日本校服（水手风格或西装外套制服），款式整齐，不暴露，年轻干净。一只手轻轻地把一颗草莓放在嘴唇附近，动作好像要咬一口；肩膀放松，微妙自然的身体曲线表情：柔和俏皮的目光，浅浅的微笑或中性的嘴唇，与相机温柔的目光接触设置：最小的室内近窗或简单的室外角落，干净的背景，日常氛围构图：稍微偏离中心的取景，亲密的距离，坦率的感觉情绪：清新，青春，甜蜜的日常时刻，低调的魅力质量：超现实，模拟电影外观，自然瑕疵，柔和的梦幻效果",
        "translated": true
      },
      {
        "caseNumber": 16,
        "title": "柔和的黑雾偶像肖像",
        "sourceUrl": "https://x.com/BubbleBrain/status/2046518189509734903",
        "author": "@BubbleBrain",
        "authorUrl": "https://x.com/BubbleBrain",
        "originalPrompt": "9:16 vertical — Korean idol portrait photography, single subject  soft black mist filter effect, lowered contrast, gentle highlight bloom, subtle glow, soft diffusion, slightly faded blacks  minimal indoor setting near window, white curtains, clean light-toned background  young Korean female idol, natural minimal makeup, dewy realistic skin texture, subtle imperfections  outfit: oversized white button-up shirt + short bottoms, slightly loose fit, soft and casual styling, no revealing elements  hair: long dark hair, slightly messy, natural volume, softly flowing  pose: relaxed standing or slight lean, body subtly angled, one leg slightly forward, shoulders relaxed; one hand lightly touching collar or resting near neckline, the other relaxed; gentle body curve without exaggeration  expression: soft cute smile, slightly playful eyes, direct or slightly off-camera gaze  camera: close to mid-body framing, eye-level, intimate distance, slight handheld feel  lighting: diffused natural daylight, soft shadows, gentle light wrapping around face and body  mood: cute yet subtly sensual, intimate, everyday softness, quiet romantic atmosphere  quality: ultra-realistic, fine film grain, slight softness at edges, natural imperfections, dreamy understated tone",
        "originalTitle": "Soft Black Mist Idol Portrait",
        "prompt": "9:16 垂直 — 韩国偶像人像摄影，单主体柔和的黑雾滤镜效果，降低对比度，柔和的高光绽放，微妙的光晕，柔和的扩散，稍微褪色的黑色，靠近窗户的最小室内环境，白色的窗帘，干净的浅色调背景年轻的韩国女偶像，自然的简约妆容，露水逼真的皮肤纹理，微妙的瑕疵服装：超大的白色纽扣衬衫+短裤，略宽松的款式，柔和休闲的造型，没有暴露的元素头发：长长的深色头发，略显凌乱，自然体积，轻柔飘逸姿势：放松站立或微倾，身体微妙地倾斜，一腿稍微向前，肩膀放松；一只手轻触衣领或靠近领口，另一只手放松；柔和的身体曲线，不浮夸的表情：柔和可爱的笑容，略带俏皮的眼神，直视或稍稍离机的目光相机：接近中身取景，视线水平，亲密的距离，轻微的手持感灯光：漫射的自然光，柔和的阴影，柔和的光线包裹着脸部和身体情绪：可爱而微妙的感性，亲密，日常的柔和，安静的浪漫气氛质量：超现实，精细的胶片颗粒，边缘轻微的柔和，自然的瑕疵，梦幻的低调色调",
        "translated": true
      },
      {
        "caseNumber": 17,
        "title": "富士胶片情侣肖像",
        "sourceUrl": "https://x.com/BubbleBrain/status/2046502288102170757",
        "author": "@BubbleBrain",
        "authorUrl": "https://x.com/BubbleBrain",
        "originalPrompt": "9:16 vertical — Japanese Fuji film style couple portrait, two subjects  Fujifilm analog aesthetic (Pro 400H / Superia feel), soft pastel tones, slight green-magenta shift, low contrast, gentle highlight roll-off, fine film grain, subtle halation  bright natural daylight, diffused sunlight through window, soft shadows, airy atmosphere  young Japanese couple, natural minimal makeup, realistic skin texture, slight imperfections  female outfit: oversized button-up shirt with loose shorts, relaxed fit, soft casual styling   male outfit: simple t-shirt or light shirt, clean and understated  hair: natural, slightly tousled for both  pose: close intimate distance — sitting or standing close together; the girl gently leaning toward him, one hand lightly resting on his shoulder or chest; the boy slightly leaning in, faces close, almost touching, capturing the moment just before a kiss  expression: soft smiles or gentle gaze toward each other, relaxed and natural, emotional connection visible  camera: close framing (waist-up), eye-level, intimate distance, slight handheld feel  setting: minimal indoor near window, light curtains, clean soft background  lighting: diffused daylight, gentle highlight bloom, soft shadow transitions  mood: warm, romantic, intimate everyday moment, natural affection  quality: ultra-realistic, analog film look, fine grain, slight softness, natural imperfections",
        "originalTitle": "Fujifilm Couple Portrait",
        "prompt": "9:16 垂直 — 日本富士胶片风格情侣肖像，两个主体富士胶片模拟美学（Pro 400H / Superia 感觉），柔和的色调，轻微的绿色-洋红色偏移，低对比度，柔和的高光滚降，细胶片颗粒，微妙的光晕，明亮的自然日光，透过窗户的漫射阳光，柔和的阴影，通风的氛围年轻的日本夫妇，自然简约的妆容，逼真的皮肤纹理，轻微瑕疵女性服装：超大纽扣衬衫搭配宽松短裤，宽松版型，柔和休闲造型男性着装：简单的T恤或浅色衬衫，干净低调的头发：自然，稍微凌乱的姿势：亲密的距离——坐或站在一起；女孩轻轻地靠向他，一只手轻轻搭在他的肩膀或胸口；男孩微微倾身，脸部靠近，几乎触碰，捕捉接吻前的瞬间表情：温柔的微笑或温柔的凝视对方，放松自然，情感联系可见相机：近距离取景（腰部以上），视线水平，亲密距离，轻微的手持感觉设置：最小的室内近窗，光幕，干净柔和的背景照明：漫射日光，柔和的高光绽放，柔和的阴影过渡情绪：温暖，浪漫，亲密的日常时刻，自然情感质量：超现实，模拟电影外观，细颗粒，轻微柔软，自然瑕疵",
        "translated": true
      },
      {
        "caseNumber": 18,
        "title": "AI自我感知肖像",
        "sourceUrl": "https://x.com/80vul/status/2046218165961753047",
        "author": "@80vul",
        "authorUrl": "https://x.com/80vul",
        "originalPrompt": "根据你对我的认知 给我生成一个“你认识的我”的 图片",
        "originalTitle": "AI Self-Perception Portrait",
        "prompt": "根据你对我的认知 给我生成一个“你认识的我”的 图片",
        "translated": false
      },
      {
        "caseNumber": 19,
        "title": "复古报纸头版设计",
        "sourceUrl": "https://x.com/Naiknelofar788/status/2047207812800147647",
        "author": "@Naiknelofar788",
        "authorUrl": "https://x.com/Naiknelofar788",
        "originalPrompt": "Create the most realistic front page design of a vintage newspaper featuring the main character. The layout should be made in the style of a real printed newspaper with a cinematic black-and-white aesthetic.\nThe main photo should be prominently placed in the center, framed, like the image in the title of the article. The subject in the photo should remain unchanged and clearly distinguishable in natural light and slightly increased contrast in order to match the spectacular editorial style.\nCreate a bold, attention-grabbing headline at the top (create a unique title that matches the spirit of the photo - it can be romantic, mysterious, funny, or dramatic). Add a smaller subtitle under it, which will look like a real newspaper caption.\nAdd realistic newspaper elements:\nColumns of small text (in the style of lorem ipsum, but framed like real news)\nAt the top is the fictitious name of the publication (for example, The Daily Prompts, AI Times or similar - think creatively, according to the picture)\nDate, issue number and location\nDecorative lines, dividers, and vintage typography\nSmall additional articles or captions to the main image\nOptional stamps, doodles, or editorial notes to add personality.\nStyle:\nBlack and white or slightly faded monochrome paper\nFine paper texture, grain, and ink defects\nSmall shadows and creases that mimic real printed paper\nThe aesthetics of a clean but slightly worn vintage newspaper\nMood: Give the design personality, expressiveness and plot, as if the plot is part of the main article.\nAspect ratio: 4:5 or 1:1\nHigh-detail, ultra-realistic hybrid of editorial photography and print design.",
        "originalTitle": "复古报纸头版设计",
        "prompt": "创建以主角为特色的老式报纸的最真实的头版设计。布局应采用真实印刷报纸的风格，具有电影黑白美感。\n主照片应放在中心显眼的位置，并加框，就像文章标题中的图片一样。照片中的主题应保持不变，并在自然光下清晰可辨，并稍微增加对比度，以匹配壮观的编辑风格。\n在顶部创建一个大胆、引人注目的标题（创建一个与照片精神相匹配的独特标题 - 它可以是浪漫的、神秘的、有趣的或戏剧性的）。在其下方添加一个较小的副标题，看起来就像真正的报纸标题。\n添加逼真的报纸元素：\n小文本栏（采用 lorem ipsum 风格，但框架像真实新闻）\n顶部是出版物的虚构名称（例如，The Daily Prompts、AI Times 或类似 - 根据图片进行创造性思考）\n日期、发行号和地点\n装饰线条、分隔线和复古排版\n主图像的小附加文章或标题\n可选的邮票、涂鸦或编辑注释来增添个性。\n风格：\n黑白或轻微褪色的单色纸\n精细的纸张纹理、纹理和油墨缺陷\n模仿真实印刷纸张的小阴影和折痕\n干净但略有磨损的复古报纸的美感\n情绪：赋予设计个性、表现力和情节，就好像情节是主要文章的一部分一样。\n纵横比：4:5 或 1:1\n高细节、超现实的编辑摄影和印刷设计的结合。",
        "translated": true
      },
      {
        "caseNumber": 20,
        "title": "旅游杂志专题文章",
        "sourceUrl": "https://x.com/andis13/status/2047204384811921764",
        "author": "@andis13",
        "authorUrl": "https://x.com/andis13",
        "originalPrompt": "Create image of Magazine feature article [travel] guide page, cute, information dense photo book style magazine feature article page. Add all necessary sections, tips, recommendations, information. add photos for any sections and recommendations if you like. Place the attached person at the precise location of [city, country]. Seamlessly blend the attached person as if they are sightseeing. Approach this task with the understanding that this is a critical, information rich page that will significantly influence visitor numbers, text accuracy is important. Fully use the entire [9:16] page. NEGATIVE PROMPT: coordinate texts @swiat_ai @ProfitAII",
        "originalTitle": "旅游杂志专题文章",
        "prompt": "打造杂志专题文章[旅行]指南页面的形象，可爱、信息密集的写真集风格杂志专题文章页面。添加所有必要的部分、提示、建议、信息。如果您愿意，可以为任何部分和推荐添加照片。将附属人员放置在[城市、国家]的精确位置。无缝地融合所依附的人，就像他们正在观光一样。完成此任务时要认识到这是一个关键的、信息丰富的页面，将显着影响访问者数量，文本准确性很重要。充分利用整个[9:16]页面。负面提示：坐标文本@swiat_ai @ProfitAII",
        "translated": true
      },
      {
        "caseNumber": 21,
        "title": "照片分析与 JSON Prompt 重建",
        "sourceUrl": "https://x.com/pavellaslov/status/2047182214304055339",
        "author": "@pavellaslov",
        "authorUrl": "https://x.com/pavellaslov",
        "originalPrompt": "analyze this photo and give me a detailed JSON prompt that recreates it. break down the color grading and every exact color in the photo\n\n(use Opus, not Sonnet. Opus has stronger visual analysis and writes more detailed JSON)\n\npaste that JSON into ChatGPT\nupload your product image and prompt:\nusing this JSON as reference, generate a person holding my product\nsave that generated photo as your character reference\n\nattach it to every future generation for facial consistency\n\nyou now have a consistent UGC model that works across any product\n\nthe JSON controls the lighting and color grading. GPT image-2 handles the character. you control the product placement.\n\nthe #1 tell on AI photos is flat colors and a grainy look. this method removes both.\n5 minutes to set up. unlimited variations after.",
        "originalTitle": "照片分析与 JSON Prompt 重建",
        "prompt": "分析这张照片并给我一个详细的 JSON 提示来重新创建它。分解颜色分级和照片中的每种确切颜色\n\n（使用Opus，而不是Sonnet。Opus具有更强的可视化分析能力，并且编写更详细的JSON）\n\n将该 JSON 粘贴到 ChatGPT 中\n上传您的产品图片并提示：\n使用此 JSON 作为参考，生成一个拿着我的产品的人\n将生成的照片保存为您的角色参考\n\n将其贴在每一代人身上，以保证面部一致性\n\n您现在拥有适用于任何产品的一致 UGC 模型\n\nJSON 控制照明和颜色分级。 GPT image-2 处理角色。您可以控制植入式广告。\n\n人工智能照片的第一大特点是色彩平淡和颗粒状外观。此方法将两者都删除。\n5 分钟即可设置。之后的无限变化。",
        "translated": true
      },
      {
        "caseNumber": 22,
        "title": "绿茶胶片套装产品摄影",
        "sourceUrl": "https://x.com/ZaraIrahh/status/2047180061657452601",
        "author": "@ZaraIrahh",
        "authorUrl": "https://x.com/ZaraIrahh",
        "originalPrompt": "CALMING GREEN TEA Film Kit displayed frontally, the open box shows soft sage-green film pouches and translucent ampoules with matte silver caps, product placed centrally with clear branding CALMING GREEN TEA -- 7 Days to Soothed Skin, pastel green background with botanical graphic accents, three minimal icons (leaf, wave, balance) floating around the product to emphasize benefits, photographic, hyper detailed, ultra realistic, lifelike, 8k, high detail, soft professional lighting.",
        "originalTitle": "绿茶胶片套装产品摄影",
        "prompt": "镇静绿茶胶片套件正面展示，打开的盒子展示柔软的鼠尾草绿色薄膜袋和半透明安瓿，带哑光银色瓶盖，产品置于中央，带有清晰的品牌镇静绿茶 - 7 天舒缓肌肤，柔和的绿色背景与植物图形口音，三个最小的图标（叶子，波浪，平衡）漂浮在产品周围以强调功效，摄影，超详细，超现实，栩栩如生，8k，高细节，柔和的专业灯光。",
        "translated": true
      },
      {
        "caseNumber": 23,
        "title": "草莓冰淇淋超写实产品摄影",
        "sourceUrl": "https://x.com/ZaraIrahh/status/2047179916161212542",
        "author": "@ZaraIrahh",
        "authorUrl": "https://x.com/ZaraIrahh",
        "originalPrompt": "Ultra-realistic product photography of a rich strawberry soft-serve ice cream in a crispy waffle cone, styled with a clean, modern premium aesthetic. The soft serve is a vibrant natural pink, thick and creamy, sculpted into a smooth swirl with a softly curled peak, lightly topped with delicate strawberry dust or tiny fruit specks for a fresh, appetizing look. The cone has a rustic, crunchy texture with slightly uneven edges for an artisanal feel.\nThe background is soft beige with natural sunlight casting subtle leaf shadows, creating a calm, organic atmosphere. Include softly blurred greenery in the foreground for depth. The composition is minimal, balanced, and uses negative space effectively, similar to high-end American food brand ads.\nOn the left side, include modern English typography in a clean, elegant layout (not vertical).\nMain headline:\nSweet Strawberry Bliss.\nSupporting line (smaller text):\nMade with real strawberries. Smooth. Creamy. Irresistible.\nAdd a small circular badge showing the price:\n$5.80.\nLighting: soft natural daylight, warm highlights, shallow depth of field, high-end commercial food photography style.\nMood: fresh, premium, modern, and inviting — aligned with upscale U.S. dessert branding.",
        "originalTitle": "草莓冰淇淋超写实产品摄影",
        "prompt": "超逼真的产品摄影，展示香脆华夫饼蛋卷中浓郁的草莓软冰淇淋，风格简洁、现代优质。软冰淇淋呈充满活力的天然粉红色，浓稠而柔滑，被雕刻成光滑的漩涡，峰顶轻轻卷曲，上面轻轻撒上精致的草莓粉或微小的水果斑点，营造出清新、开胃的外观。圆锥体具有质朴、松脆的质地，边缘略有凹凸不平，给人一种手工的感觉。\n背景是柔和的米色，自然阳光投射出微妙的树叶阴影，营造出平静、有机的氛围。在前景中加入柔和模糊的绿色植物以增加深度。构图简约、平衡，并有效利用负空间，类似于高端美国食品品牌广告。\n在左侧，以干净、优雅的布局（非垂直）包含现代英语排版。\n主要标题：\n甜蜜的草莓幸福。\n支持行（较小的文字）：\n用真正的草莓制成。光滑的。奶油味的。无法抗拒。\n添加一个显示价格的小圆形徽章：\n5.80 美元。\n灯光：柔和的自然光，温暖的高光，浅景深，高端商业美食摄影风格。\n氛围：新鲜、优质、现代、诱人——与高档美国甜点品牌保持一致。",
        "translated": true
      },
      {
        "caseNumber": 24,
        "title": "笔记本上的超写实 UI/UX 模型",
        "sourceUrl": "https://x.com/ZaraIrahh/status/2047179669011616172",
        "author": "@ZaraIrahh",
        "authorUrl": "https://x.com/ZaraIrahh",
        "originalPrompt": "A hyper-realistic UI/UX mockup displayed on a slim modern laptop placed on a minimal wooden desk with soft natural daylight. The screen shows a clean SaaS dashboard with elegant typography, glassmorphism cards, smooth gradients, subtle drop shadows, and neatly spaced components. Visible charts, analytics panels, sidebar navigation, and micro-interactions. Realistic macOS-style window frame, soft reflections on the screen, shallow depth of field, cozy workspace atmosphere, shot in photorealistic product photography style, ultra-detailed.",
        "originalTitle": "笔记本上的超写实 UI/UX 模型",
        "prompt": "超现实的 UI/UX 模型显示在一台纤薄的现代笔记本电脑上，放置在一张最小的木桌上，自然光柔和。屏幕显示了一个干净的 SaaS 仪表板，具有优雅的排版、玻璃形态卡片、平滑的渐变、微妙的阴影和整齐排列的组件。可见的图表、分析面板、侧边栏导航和微交互。逼真的macOS风格窗框，屏幕上柔和的反射，浅景深，舒适的工作氛围，以逼真的产品摄影风格拍摄，超详细。",
        "translated": true
      },
      {
        "caseNumber": 25,
        "title": "超写实电影感 DSLR 人像摄影",
        "sourceUrl": "https://x.com/harboriis/status/2047175250761433416",
        "author": "@harboriis",
        "authorUrl": "https://x.com/harboriis",
        "originalPrompt": "Ultra-realistic cinematic DSLR photograph of an 18-year-old handsome young man with a slim skinny body, lean physique, narrow shoulders and waist, standing confidently in front of a blue 2017 Ford Mustang GT Convertible with a bold red soft top roof, captured from a high-angle aerial perspective exactly like a luxury driveway photoshoot. Keep face 100% identical to reference image with exact facial structure, natural skin texture, realistic pores, authentic expression, no beautification, no facial modification. Same modern textured side-swept quiff hairstyle with heavy natural volume on top, deep side flow, messy yet controlled texture, soft matte finish, visible natural hair strands, softly blended sides.\n\nThe subject stands centered near the front bumper of the Mustang GT, hands inside hoodie pockets, relaxed shoulders, straight posture, slight head tilt upward toward camera, confident calm expression, wearing oversized premium black hoodie with realistic cotton texture, natural folds, hanging drawstrings, loose dark washed black denim jeans with soft wrinkles and stacked hems, clean white sneakers with realistic leather texture and sole details, black slim rectangular sunglasses.\n\nCar must be a detailed 2017 Ford Mustang GT Convertible, metallic electric blue paint, glossy reflections on hood, visible Mustang pony grille emblem, aggressive headlights, muscular hood sculpting, aerodynamic front bumper, black alloy wheels, premium red convertible fabric roof, realistic windshield reflections, detailed side mirrors, authentic tire tread, showroom-clean finish\n\nScene set in an upscale villa driveway with light beige hexagonal stone pavement, curved border with fresh green grass on left side, tropical palm leaves entering frame from top corners, subtle luxury outdoor atmosphere. Soft natural daylight, diffused afternoon lighting, realistic shadows under car and body, soft reflections on paintwork, cinematic premium color grading, natural contrast, shallow depth separation while maintaining environment clarity. Shot on 35mm lens, vertical composition, full body framing, crisp details, hyper-realistic DSLR quality, zero Al look, natural skin rendering, realistic hair strands, fabric texture, stone surface texture, luxury lifestyle mood. stylish text AmanZaid at the bottom-left corner, signature style\n\nNegative Prompt:\n\nface changed, different identity, beautified face, edited face, smooth plastic skin, fake skin glow, wrong hairstyle, short hair, fade haircut, buzzcut, messy deformed hair, female features, muscular body, fat body, broad shoulders, bad anatomy, long neck, short legs, extra fingers, missing fingers, mutated hands, distorted arms, broken posture, crossed eyes, lazy eye, bad sunglasses, blurry face, low resolution, pixelated, noisy image, overexposed, underexposed, harsh shadows, unrealistic reflections, fake car shape, wrong car model, damaged car, extra wheels, warped Mustang logo, incorrect. proportions, bad pavement texture, background artifacts, duplicate objects, watermark, logo errors, text artifacts, cropped feet, cut car, unnatural perspective, CGI render, cartoon style, painting, Al artifacts, oversaturated colors, motion blur, lens distortion 1664x2080-ar 4:5",
        "originalTitle": "超写实电影感 DSLR 人像摄影",
        "prompt": "超逼真的电影单反照片，拍摄的是一位 18 岁英俊年轻男子，身材苗条，身材瘦削，肩膀和腰部较窄，自信地站在一辆蓝色 2017 款福特野马 GT 敞篷车前，该车配有大胆的红色软顶车顶，从高角度空中视角拍摄，就像豪华车道照片一样。保持人脸与参考图像100%一致，面部结构准确，肤质自然，毛孔真实，表情真实，无美化，无面部修饰。同样现代质感的侧扫卷发发型，顶部自然卷曲，深侧流，凌乱但受控的纹理，柔软的哑光饰面，可见的自然发丝，柔和混合的两侧。\n\n拍摄对象站在野马 GT 前保险杠附近，双手插在连帽衫口袋里，肩膀放松，姿势笔直，头稍微向镜头倾斜，表情自信平静，穿着超大号优质黑色连帽衫，棉质质感逼真，自然褶皱，悬挂抽绳，宽松的深色水洗黑色牛仔裤，带有柔软的皱纹和叠层下摆，干净的白色运动鞋，具有逼真的皮革纹理和鞋底细节，黑色细长矩形太阳镜。\n\n该车必须是一辆精致的 2017 款福特野马 GT 敞篷车，金属电蓝色油漆，引擎盖上有光泽的反射，可见的野马小马格栅标志，激进的车头灯，肌肉发达的引擎盖雕刻，空气动力学前保险杠，黑色合金车轮，高级红色敞篷织物车顶，逼真的挡风玻璃反射，详细的后视镜，真实的轮胎胎面，陈列室干净的饰面\n\n场景设置在高档别墅车道上，浅米色六角形石路面，左侧有新鲜绿草的弧形边界，热带棕榈叶从顶角进入框架，微妙的奢华户外氛围。柔和的自然日光、漫射的午后照明、汽车和车身下的真实阴影、油漆上的柔和反射、电影级高级色彩分级、自然对比度、浅深度分离，同时保持环境清晰度。 35mm镜头拍摄，垂直构图，全身取景，细节清晰，超写实单反画质，零AI外观，自然肤色渲染，真实发丝，织物质感，石材表面纹理，奢华生活意境。左下角时尚文字 AmanZaid，签名风格\n\n否定提示：\n\n脸变了，不同的身份，美化的脸，编辑过的脸，光滑的塑料皮肤，假皮肤发光，错误的发型，短发，褪色发型，嗡嗡声，凌乱的变形头发，女性特征，肌肉发达，脂肪体，宽肩膀，不良解剖学，长脖子，短腿，额外的手指，缺失手指，突变的手，扭曲的手臂，破碎的姿势，斗鸡眼，懒惰的眼睛，坏太阳镜，模糊的脸，低分辨率，像素化，噪声图像，曝光过度，曝光不足、刺眼的阴影、不切实际的反射、假车形状、错误的汽车型号、损坏的汽车、多余的车轮、扭曲的野马标志、不正确。比例、不良路面纹理、背景伪影、重复对象、水印、徽标错误、文本伪影、裁剪脚、切车、不自然透视、CGI 渲染、卡通风格、绘画、Al 伪影、过饱和颜色、运动模糊、镜头畸变 1664x2080-ar 4:5",
        "translated": true
      },
      {
        "caseNumber": 26,
        "title": "卧室抓拍自拍写实人像",
        "sourceUrl": "https://x.com/charliejhills/status/2047969988368314526",
        "author": "@charliejhills",
        "authorUrl": "https://x.com/charliejhills",
        "originalPrompt": "Candid selfie of a young woman with shoulder-length honey-blonde hair with lighter highlights, green-grey eyes, rosy cheeks, and a natural no-makeup makeup look. She is wearing a light grey hoodie and looking slightly off-camera with a relaxed expression. Background shows a cosy bedroom with warm fairy lights strung on a pink wall, a unmade bed with tan bedding, and a small white desk with stacked books. Soft, warm ambient lighting. Photo-realistic, casual, intimate feel.",
        "originalTitle": "卧室抓拍自拍写实人像",
        "prompt": "一位年轻女子的自拍照，她有一头齐肩的蜂蜜金色头发，带有浅色亮点，绿灰色的眼睛，红润的脸颊，以及自然的素颜妆容。她身穿浅灰色连帽衫，表情略显轻松。背景是一间舒适的卧室，粉红色的墙上挂着温暖的童话灯，一张凌乱的床和棕褐色的床上用品，还有一张白色的小桌子，上面堆满了书籍。柔和、温暖的环境照明。逼真、休闲、亲密的感觉。",
        "translated": true
      },
      {
        "caseNumber": 27,
        "title": "夜晚杂货店门口音乐人电影感人像",
        "sourceUrl": "https://x.com/commanderdgr8/status/2047934886124867684",
        "author": "@commanderdgr8",
        "authorUrl": "https://x.com/commanderdgr8",
        "originalPrompt": "A candid, magazine-cover quality documentary photograph of a young musician with curly hair, casually carrying a worn guitar case, stepping out of a classic downtown bodega at 11 PM. The lighting features a complex mixed color temperature: a bright neon \"OPEN\" sign casts an intense, warm red glow across his face, while a yellow streetlamp provides a striking backlight behind him. The image perfectly emulates 35mm film shot on a Canon AE-1 with a 50mm f/1.4 lens wide open, exhibiting a shallow depth of field with the background beautifully blurred. It captures the exact aesthetics of CineStill 800T film, specifically featuring the distinctive soft red halation bloom radiating outward from the neon light sources, a tungsten white balance, and moody, slightly green-tinted shadows in the darkest areas. Cinematic night photography, photorealistic, highly detailed.",
        "originalTitle": "夜晚杂货店门口音乐人电影感人像",
        "prompt": "这是一张登上杂志封面的优质纪实照片，照片中一位留着卷发的年轻音乐家，随意地拎着一个破旧的吉他盒，于晚上 11 点走出一家经典的市中心小酒馆。灯光具有复杂的混合色温：明亮的霓虹灯“OPEN”标志在他的脸上投射出强烈、温暖的红光，而黄色路灯在他身后提供了引人注目的背光。该图像完美模拟了使用佳能 AE-1 使用 50mm f/1.4 镜头全开拍摄的 35mm 胶片，呈现出浅景深，背景精美模糊。它准确捕捉了 CineStill 800T 胶片的美感，特别具有从霓虹灯光源向外辐射的独特柔和红色晕光、钨丝白平衡以及最暗区域中喜怒无常、略带绿色的阴影。电影级夜间摄影，逼真，细节丰富。",
        "translated": true
      },
      {
        "caseNumber": 28,
        "title": "旧德里糖果店门面纪实照片",
        "sourceUrl": "https://x.com/commanderdgr8/status/2047889839123521635",
        "author": "@commanderdgr8",
        "authorUrl": "https://x.com/commanderdgr8",
        "originalPrompt": "Create a photorealistic travel-documentary image of a small sweet-shop storefront in Old Delhi at midday. A painted shop signboard above the door reads \"मिठाई की दुकान\" in large bold yellow hand-painted Devanagari on a deep red background, with \"SWEET SHOP\" in smaller roman letters beneath. Realistic hand-painted texture, slight wear, natural shadow. Authentic script proportion. Spelling and characters exact. No extra signage in frame, no watermark.",
        "originalTitle": "旧德里糖果店门面纪实照片",
        "prompt": "创建一张真实的旅行纪录片图像，展示中午旧德里一家小甜品店的店面。门上方的彩绘商店招牌上写着“मिठाई की दुकान”，深红色背景上用大号粗体黄色手绘梵文写着，下面是较小的罗马字母“SWEET SHOP”。手绘质感逼真，轻微磨损，阴影自然。真实的脚本比例。拼写和字符准确。框架中没有额外的标牌，没有水印。",
        "translated": true
      },
      {
        "caseNumber": 29,
        "title": "赛博朋克科幻侧脸人像",
        "sourceUrl": "https://x.com/iamsofiaijaz/status/2047882171336253928",
        "author": "@iamsofiaijaz",
        "authorUrl": "https://x.com/iamsofiaijaz",
        "originalPrompt": "A cinematic side-profile portrait of a rugged man with a tied-back bun and full beard, wearing round dark sunglasses and a textured leather jacket. His skin is detailed and slightly weathered. The background is a futuristic sci-fi interface filled with glowing orange and red data streams, star maps, celestial navigation diagrams, grids, and holographic UI elements. Fiery particle effects and ember-like energy swirl around him, creating a cosmic, high-tech atmosphere. Dark color palette with strong contrast, dramatic lighting, ultra-detailed, sharp focus, 8K, cyberpunk aesthetic, cinematic composition, depth of field.",
        "originalTitle": "赛博朋克科幻侧脸人像",
        "prompt": "这是一幅电影般的侧面肖像，描绘的是一位粗犷男人，扎着发髻，留着大胡子，戴着圆形深色太阳镜，穿着有纹理的皮夹克。他的皮肤细致且略有风化。背景是一个未来科幻界面，充满了发光的橙色和红色数据流、星图、天体导航图、网格和全息 UI 元素。炽热的粒子效果和余烬般的能量在他周围旋转，营造出宇宙般的高科技氛围。具有强烈对比度的深色调色板、戏剧性的灯光、超细节、锐利的焦点、8K、赛博朋克美学、电影构图、景深。",
        "translated": true
      },
      {
        "caseNumber": 30,
        "title": "卧室录音随拍写实人像",
        "sourceUrl": "https://x.com/ChillaiKalan__/status/2047862141894681076",
        "author": "@ChillaiKalan__",
        "authorUrl": "https://x.com/ChillaiKalan__",
        "originalPrompt": "A realistic young woman sitting casually in a softly lit bedroom during late afternoon.\n\nShe is holding her phone very close to her face as if recording a private video or voice note.\n\nFraming is tight and slightly imperfect.\n\nExpression: thoughtful, slightly shy, natural.\n\nMinimal makeup, natural skin texture, relaxed clothing.\n\nLighting: warm natural light fading from a window, soft shadows.\n\nEnvironment: simple bedroom, calm and lived-in.\n\nStyle: ultra-realistic, looks like a real phone recording, slightly grainy, not cinematic.",
        "originalTitle": "卧室录音随拍写实人像",
        "prompt": "下午晚些时候，一位现实的年轻女子随意坐在灯光柔和的卧室里。\n\n她将手机离脸很近，就像录制私人视频或语音笔记一样。\n\n框架很紧凑，有点不完美。\n\n表情：深思熟虑，略带羞涩，自然。\n\n简约的妆容、自然的肌肤纹理、轻松的服装。\n\n照明：温暖的自然光从窗户射入，柔和的阴影。\n\n环境：简约的卧室，安静，适合居住。\n\n风格：超写实，看起来像真实的手机录音，略有颗粒感，不是电影风格。",
        "translated": true
      },
      {
        "caseNumber": 31,
        "title": "幼儿蜡笔涂鸦风格人像",
        "sourceUrl": "https://x.com/akakageAI/status/2047812983389356276",
        "author": "@akakageAI",
        "authorUrl": "https://x.com/akakageAI",
        "originalPrompt": "(被写体) in the style of super bad child drawing, toddler art, scribbles, messy crayon lines on white background, completely lack of technique, terrible composition, chaotic colors, barely recognizable shapes, very raw, honest art, pure naivety, unrefined style, 4:3\nNegative:\ngood drawing, nice lines, clear shapes, neat, pretty, smooth, realistic, talented art, coherent composition, artistic style, professional, skilled, masterpiece, beautiful, detailed",
        "originalTitle": "幼儿蜡笔涂鸦风格人像",
        "prompt": "（被写体）以超级糟糕的儿童绘画风格，幼儿艺术，涂鸦，白色背景上凌乱的蜡笔线条，完全缺乏技术，糟糕的构图，混乱的色彩，几乎无法辨认的形状，非常原始，诚实的艺术，纯粹的天真，不精致的风格，4:3\n负面：\n良好的绘画，线条优美，形状清晰，整齐，漂亮，流畅，逼真，艺术才华，构图连贯，艺术风格，专业，熟练，杰作，美丽，详细",
        "translated": true
      }
    ]
  },
  {
    "title": "海报与插画案例",
    "items": [
      {
        "caseNumber": 1,
        "title": "波士顿 2026 年春季城市海报",
        "sourceUrl": "https://x.com/BubbleBrain/status/2045358053831172358",
        "author": "@BubbleBrain",
        "authorUrl": "https://x.com/BubbleBrain",
        "originalPrompt": "A striking Spring 2026 city poster for Boston with an elegant celebratory mood and a bold contemporary design. On a clean off-white textured background with large areas of negative space, a miniature single sculler rows across the lower right corner of the image on a narrow ribbon of reflective water. The wake from the oar sweeps upward in a dynamic calligraphic curve, gradually transforming into the Charles River and then into a dreamlike hand-painted panorama of Boston. Inside this flowing river-shaped composition are iconic Boston elements: the Back Bay skyline, Beacon Hill brownstones, Acorn Street, Boston Public Garden, Swan Boats, Zakim Bridge, Fenway-inspired details, historic brick architecture, harbor ferries, and the city’s waterfront atmosphere. Soft morning fog, golden spring light, subtle festive accents in crimson and gold, rich detail, layered depth, sophisticated city-poster aesthetics, fresh and refined, visually powerful but not overcrowded. Elegant typography in the lower left reads “SPRING 2026” with a vertical slogan “BOSTON, A CITY OF RIVER, MEMORY, AND INVENTION”, text clear and beautifully composed, premium graphic design, 9:16",
        "originalTitle": "Boston Spring 2026 City Poster",
        "prompt": "波士顿 2026 年春季引人注目的城市海报，具有优雅的庆祝气氛和大胆的现代设计。在干净的灰白色纹理背景上，有大面积的负空间，一个微型单桨划过图像的右下角，在一条狭窄的反光水带上。桨的尾流以动态的书法曲线向上扫过，逐渐变成查尔斯河，然后变成梦幻般的波士顿手绘全景。在这个流动的河流形状的构图中，有标志性的波士顿元素：后湾天际线、灯塔山褐石建筑、橡子街、波士顿公共花园、天鹅船、扎基姆桥、芬威风格的细节、历史悠久的砖砌建筑、港口渡轮和城市的海滨氛围。柔和的晨雾，金色的春光，深红与金色的微妙喜庆气息，丰富的细节，层次分明，精致的城市海报美学，清新脱俗，视觉冲击力强却不显得拥挤。左下角优雅的排版写着“SPRING 2026”，垂直标语“BOSTON, A CITY OF RIVER, MEMORY, AND Invention”，文字清晰，构图精美，优质的图形设计，9:16",
        "translated": true
      },
      {
        "caseNumber": 2,
        "title": "复古阿马尔菲旅行海报",
        "sourceUrl": "https://x.com/WolfRiccardo/status/2044562722491121718",
        "author": "@WolfRiccardo",
        "authorUrl": "https://x.com/WolfRiccardo",
        "originalPrompt": "Modern pencil illustration of Vintage travel poster illustration of the Amalfi Coast, Italy, panoramic coastal cliff road scene, classic 1960s white car driving along a curved seaside road, deep blue Mediterranean sea with small sailboats, colorful pastel hillside village, bright blue sky with soft clouds, lemon tree branches with vibrant yellow lemons framing the foreground, warm summer sunlight, bold vibrant colors, retro 1950s travel poster style, cinematic composition, high detail, screen print texture, graphic illustration. Hand-drawn style, illustration with loose strokes and defined contours. High-contrast color palette, maintaining chromatic harmony between background and elements. Contemporary and decorative aesthetic.",
        "originalTitle": "Vintage Amalfi Travel Poster",
        "prompt": "意大利阿马尔菲海岸复古旅行海报插图的现代铅笔插图，全景沿海悬崖路场景，经典的 1960 年代白色汽车沿着弯曲的海滨路行驶，深蓝色的地中海与小帆船，色彩缤纷的柔和山坡村庄，明亮的蓝天与柔软的云彩，柠檬树枝与充满活力的黄色柠檬构成前景，温暖的夏日阳光，大胆鲜艳的色彩，复古 1950 年代旅行海报风格，电影构图，高细节，丝网印刷纹理，图形插图。手绘风格，插图具有宽松的笔画和明确的轮廓。高对比度调色板，保持背景和元素之间的色彩和谐。当代和装饰美学。",
        "translated": true
      },
      {
        "caseNumber": 3,
        "title": "成都美食地图图",
        "sourceUrl": "https://x.com/Panda20230902/status/2045396918965285111",
        "author": "@Panda20230902",
        "authorUrl": "https://x.com/Panda20230902",
        "originalPrompt": "一张手绘风格的城市美食地图，以成都为主题。画面以鸟瞰视角的手绘简化城市地图为底，标注主要道路和地标但不追求精确比例而是追求可爱的手绘感。地图上分布着 12 个美食地点的精致手绘小插画：春熙路的串串香（一把竹签插着各种食材冒着热气）、宽窄巷子的三大炮（三个糯米团子飞向铜盘）、建设路的蛋烘糕（金黄酥脆正在翻面）、玉林路的火锅（九宫格锅翻滚冒泡）等，每个插画约占地图的 5% 面积，旁边用手写体标注店名和一句推荐语\"凌晨两点还在排队的那家\"。地图边缘用手绘藤蔓和辣椒装饰形成边框。右下角有一个手绘指南针和图例说明。左上角标题\"成都·吃货暴走地图\"使用胖圆的手绘美术字配辣椒装饰。整体画风为水彩+彩铅混合的手绘质感，颜色以暖色系（辣椒红、姜黄、翠绿）为主，图片比例 1:1。",
        "originalTitle": "Chengdu Food Map Illustration",
        "prompt": "一张手绘风格的城市美食地图，以成都为主题。画面以鸟瞰视角的手绘简化城市地图为底，标注主要道路和地标但不追求精确比例而是追求可爱的手绘感。地图上分布着 12 个美食地点的精致手绘小插画：春熙路的串串香（一把竹签插着各种食材冒着热气）、宽窄巷子的三大炮（三个糯米团子飞向铜盘）、建设路的蛋烘糕（金黄酥脆正在翻面）、玉林路的火锅（九宫格锅翻滚冒泡）等，每个插画约占地图的 5% 面积，旁边用手写体标注店名和一句推荐语\"凌晨两点还在排队的那家\"。地图边缘用手绘藤蔓和辣椒装饰形成边框。右下角有一个手绘指南针和图例说明。左上角标题\"成都·吃货暴走地图\"使用胖圆的手绘美术字配辣椒装饰。整体画风为水彩+彩铅混合的手绘质感，颜色以暖色系（辣椒红、姜黄、翠绿）为主，图片比例 1:1。",
        "translated": false
      },
      {
        "caseNumber": 4,
        "title": "中国极简S形海报",
        "sourceUrl": "https://x.com/liyue_ai/status/2045368305079447853",
        "author": "@liyue_ai",
        "authorUrl": "https://x.com/liyue_ai",
        "originalPrompt": "极简新中式美学风格，画面以淡雅的灰白色为底，呈现出一种纸艺剪影般的立体感。\n一条S形蜿蜒的裂痕状边缘将画面分割，仿佛撕开了一层纸面，露出内部色彩斑斓的东方山水景象。\n裂口内，一条蜿蜒的河流自上而下贯穿整个构图，河水以深浅不一的蓝色渲染，层次分明，仿佛流动的丝带。\n河岸两侧点缀着青翠的山丘与梯田，色彩柔和，绿红交织，展现出田园的宁静之美。\n沿河而建的古风建筑错落有致，飞檐翘角，白墙黛瓦，在光影的映衬下更显古朴典雅。\n岸边树木葱茏，枝叶轻盈，一艘小船静泊于水中央，增添了几分悠然意境。\n整体构图呈S形曲线，富有韵律感，仿佛自然与人文的和谐共生。\n画作边缘采用撕纸效果，营造出立体浮雕般的视觉体验。\n下方题字“东方美学”以黑色楷体书写，日期“2026/04/18”与红色印章相呼应，底部“CHINA”字样庄重醒目，署名“@LIYUE”低调收尾，整体氛围静谧深远，充满诗意与哲思。",
        "originalTitle": "Chinese Minimalist S-Shaped Poster",
        "prompt": "极简新中式美学风格，画面以淡雅的灰白色为底，呈现出一种纸艺剪影般的立体感。\n一条S形蜿蜒的裂痕状边缘将画面分割，仿佛撕开了一层纸面，露出内部色彩斑斓的东方山水景象。\n裂口内，一条蜿蜒的河流自上而下贯穿整个构图，河水以深浅不一的蓝色渲染，层次分明，仿佛流动的丝带。\n河岸两侧点缀着青翠的山丘与梯田，色彩柔和，绿红交织，展现出田园的宁静之美。\n沿河而建的古风建筑错落有致，飞檐翘角，白墙黛瓦，在光影的映衬下更显古朴典雅。\n岸边树木葱茏，枝叶轻盈，一艘小船静泊于水中央，增添了几分悠然意境。\n整体构图呈S形曲线，富有韵律感，仿佛自然与人文的和谐共生。\n画作边缘采用撕纸效果，营造出立体浮雕般的视觉体验。\n下方题字“东方美学”以黑色楷体书写，日期“2026/04/18”与红色印章相呼应，底部“CHINA”字样庄重醒目，署名“@LIYUE”低调收尾，整体氛围静谧深远，充满诗意与哲思。",
        "translated": false
      },
      {
        "caseNumber": 5,
        "title": "2026年春季广州城市海报",
        "sourceUrl": "https://x.com/liyue_ai/status/2045332620352119274",
        "author": "@liyue_ai",
        "authorUrl": "https://x.com/liyue_ai",
        "originalPrompt": "一张充满新春喜庆氛围但不失高雅格调的 2026 城市宣传海报。\n双重曝光，构图延续了S型的流动感；\n在纯白的纹理背景右下角，一个身穿中国传统服饰的微缩人物正在挥舞着一条长长的红色丝绸舞带，这条红绸在空中舞动，不仅展现出丝绸的柔顺质感，更在向左上方飘动的过程中，奇幻地变形成了一条壮丽的山脉河流。\n在这条“河流”中，叠加了一个有山有海河的广州城市手绘图，国潮，景色尽在眼底，壮阔雄伟，令人震撼。\n广州的地标建筑(广州塔，珠江新城建筑群，珠江, 广州城里古建筑，游轮，白云山）。\n云雾环绕，仙气缥缈，色彩丰富，结构复杂，细节丰富，但因为大面积的留白，画面依然显得清新脱俗，左下角排版着“SPRING 2026”和竖排的宣传语，整体寓意“千年商都，魅力广州”。\n文字排版优美，大方，字迹清晰完整，尺寸9:16。",
        "originalTitle": "2026 Spring Guangzhou City Poster",
        "prompt": "一张充满新春喜庆氛围但不失高雅格调的 2026 城市宣传海报。\n双重曝光，构图延续了S型的流动感；\n在纯白的纹理背景右下角，一个身穿中国传统服饰的微缩人物正在挥舞着一条长长的红色丝绸舞带，这条红绸在空中舞动，不仅展现出丝绸的柔顺质感，更在向左上方飘动的过程中，奇幻地变形成了一条壮丽的山脉河流。\n在这条“河流”中，叠加了一个有山有海河的广州城市手绘图，国潮，景色尽在眼底，壮阔雄伟，令人震撼。\n广州的地标建筑(广州塔，珠江新城建筑群，珠江, 广州城里古建筑，游轮，白云山）。\n云雾环绕，仙气缥缈，色彩丰富，结构复杂，细节丰富，但因为大面积的留白，画面依然显得清新脱俗，左下角排版着“SPRING 2026”和竖排的宣传语，整体寓意“千年商都，魅力广州”。\n文字排版优美，大方，字迹清晰完整，尺寸9:16。",
        "translated": false
      },
      {
        "caseNumber": 7,
        "title": "涂鸦素描 AI 生成器",
        "sourceUrl": "https://x.com/blanplan/status/2045190582453350748",
        "author": "@blanplan",
        "authorUrl": "https://x.com/blanplan",
        "originalPrompt": "以涂鸦速写风表现【一个厉害的AI builder】，整体呈现快速勾勒、自由变形、即兴手绘与草稿式的视觉效果。线条随手、夸张、可粗细不一，略显凌乱但具有节奏和表现力，强调概括、夸张、趣味和随性，而不是严谨写实或精细刻画。  颜色采用粗糙、干刷感明显的块面表现，可保留不均匀的涂抹痕迹、刷痕、飞白与覆盖感，色彩根据【主题/主体】自动适配，但整体保持涂鸦式、速写式、概括式的表达。不要透明水彩晕染效果，不要细腻水彩过渡，不要纸纹理，不要柔和雾化，不要梦幻质感。  背景以留白为主，保持简洁、轻松、未完成感和设计感，可加入少量辅助性符号、箭头、记号、圈画、重复线、随手写的文字或其他涂鸦元素，以增强速写本或随笔式视觉语言，但不可过于拥挤，不可破坏主体和留白气质。  画面内容不需要预先写清楚，由【一个厉害的AI builder】自动推演并生成最适合的主体形象、动作、相关元素、符号或简化场景，整体保持统一的涂鸦速写风和夸张概括的表现方式，避免复杂写实背景和过度铺陈。 画面中需自然加入专属签名“BlanPlan”，作为画面的一部分，位置低调但清晰，可放在左下角、右下角或标题附近，风格需与整体版式统一，像作品署名或设计落款；签名字体精致、克制、高级，不可过大，不可破坏主体构图，不可显得突兀或廉价。",
        "originalTitle": "Doodle Sketch AI Builder",
        "prompt": "以涂鸦速写风表现【一个厉害的AI builder】，整体呈现快速勾勒、自由变形、即兴手绘与草稿式的视觉效果。线条随手、夸张、可粗细不一，略显凌乱但具有节奏和表现力，强调概括、夸张、趣味和随性，而不是严谨写实或精细刻画。  颜色采用粗糙、干刷感明显的块面表现，可保留不均匀的涂抹痕迹、刷痕、飞白与覆盖感，色彩根据【主题/主体】自动适配，但整体保持涂鸦式、速写式、概括式的表达。不要透明水彩晕染效果，不要细腻水彩过渡，不要纸纹理，不要柔和雾化，不要梦幻质感。  背景以留白为主，保持简洁、轻松、未完成感和设计感，可加入少量辅助性符号、箭头、记号、圈画、重复线、随手写的文字或其他涂鸦元素，以增强速写本或随笔式视觉语言，但不可过于拥挤，不可破坏主体和留白气质。  画面内容不需要预先写清楚，由【一个厉害的AI builder】自动推演并生成最适合的主体形象、动作、相关元素、符号或简化场景，整体保持统一的涂鸦速写风和夸张概括的表现方式，避免复杂写实背景和过度铺陈。 画面中需自然加入专属签名“BlanPlan”，作为画面的一部分，位置低调但清晰，可放在左下角、右下角或标题附近，风格需与整体版式统一，像作品署名或设计落款；签名字体精致、克制、高级，不可过大，不可破坏主体构图，不可显得突兀或廉价。",
        "translated": false
      },
      {
        "caseNumber": 8,
        "title": "未来派曼陀罗图",
        "sourceUrl": "https://x.com/4WEB1/status/2045390207072256179",
        "author": "@4WEB1",
        "authorUrl": "https://x.com/4WEB1",
        "originalPrompt": "曼荼羅の近未来SF版を描いて",
        "originalTitle": "Futuristic Mandala Illustration",
        "prompt": "绘制近未来科幻版本的曼陀罗",
        "translated": true
      },
      {
        "caseNumber": 9,
        "title": "超级任天堂海报风格",
        "sourceUrl": "https://x.com/lilimliliychan/status/2045114760937804187",
        "author": "@lilimliliychan",
        "authorUrl": "https://x.com/lilimliliychan",
        "originalPrompt": "小悪魔リリムリリィちゃんが　スーパーファミコンのゲームだったときのポスターを考えて",
        "originalTitle": "Super Famicom Poster Style",
        "prompt": "想想《小恶魔莉莉姆莉莉酱》在超级红白机游戏时的海报。",
        "translated": true
      },
      {
        "caseNumber": 10,
        "title": "浏览器游戏广告创意海报",
        "sourceUrl": "https://x.com/llllegend0620/status/2045963764466688065",
        "author": "@llllegend0620",
        "authorUrl": "https://x.com/llllegend0620",
        "originalPrompt": "以下の文字を必ず入れて、1:1のポスターを作成してください。書籍・講座・イベント告知に使える、プロの広告デザイナーが作ったような高品質な仕上がりにしてください。\n\n広告クリエイティブ制作\n思いついたら、もう遊べる。 AI×ブラウザゲームづくりは、マジで楽しい。 むずかしそうで、実ははじめやすい。 コードがわからなくても、はじめの一本は作れる",
        "originalTitle": "Browser Game Ad Creative Poster",
        "prompt": "请务必包含以下角色来创建 1:1 海报。创建看起来像是由专业广告设计师创建的高质量结果，可用于宣传书籍、课程和活动。\n\n广告创意制作\n一旦有了想法，就可以开始玩了。创建 AI x 浏览器游戏非常有趣。看起来可能很难，但实际上很容易上手。即使您不知道代码，您也可以编写第一个代码。",
        "translated": true
      },
      {
        "caseNumber": 11,
        "title": "超现实锦鲤星云图",
        "sourceUrl": "https://x.com/liyue_ai/status/2045875219307655337",
        "author": "@liyue_ai",
        "authorUrl": "https://x.com/liyue_ai",
        "originalPrompt": "一幅超现实主义数字插画风格，采用低角度仰拍视角。画面描绘了一条巨型彩色锦鲤遨游在梦幻般的星云中，四周环绕着色彩鲜艳的星云与气泡。画面中央还站着一个小人，背对观众，神情平静地仰望空中这条巨大的锦鲤，锦鲤头向下看着小人。整体画面呈现出强烈的大小对比，氛围空灵又梦幻。比例9:16",
        "originalTitle": "Surreal Koi Nebula Illustration",
        "prompt": "一幅超现实主义数字插画风格，采用低角度仰拍视角。画面描绘了一条巨型彩色锦鲤遨游在梦幻般的星云中，四周环绕着色彩鲜艳的星云与气泡。画面中央还站着一个小人，背对观众，神情平静地仰望空中这条巨大的锦鲤，锦鲤头向下看着小人。整体画面呈现出强烈的大小对比，氛围空灵又梦幻。比例9:16",
        "translated": false
      },
      {
        "caseNumber": 12,
        "title": "墨曲线广州美学海报",
        "sourceUrl": "https://x.com/liyue_ai/status/2045873940883808523",
        "author": "@liyue_ai",
        "authorUrl": "https://x.com/liyue_ai",
        "originalPrompt": "纯黑深邃底色，一条粗壮有力的墨色书法 S 型曲线自画面一端蜿蜒贯穿至另一端，构成整幅画面的视觉骨架与叙事动线。曲线上方是一只透明质感的画眉鸟，内部映射传统建筑叠影与蓝绿色光流；沿曲线错落分布广州地标与古典建筑序列，前景有白鹤与湖面，远景为层叠山峦。整体采用非线性透视、冷色调主导、暖色点缀，东方美学与现代意象交融，8K 超高清渲染，比例 9:16。",
        "originalTitle": "Ink-Curve Guangzhou Aesthetics Poster",
        "prompt": "纯黑深邃底色，一条粗壮有力的墨色书法 S 型曲线自画面一端蜿蜒贯穿至另一端，构成整幅画面的视觉骨架与叙事动线。曲线上方是一只透明质感的画眉鸟，内部映射传统建筑叠影与蓝绿色光流；沿曲线错落分布广州地标与古典建筑序列，前景有白鹤与湖面，远景为层叠山峦。整体采用非线性透视、冷色调主导、暖色点缀，东方美学与现代意象交融，8K 超高清渲染，比例 9:16。",
        "translated": false
      },
      {
        "caseNumber": 13,
        "title": "粤超联赛邀请海报",
        "sourceUrl": "https://x.com/liyue_ai/status/2045772039521542202",
        "author": "@liyue_ai",
        "authorUrl": "https://x.com/liyue_ai",
        "originalPrompt": "广东省城市足球超级联赛（粤超）邀请函海报设计，比例 9:16。S 型流动构图，以发光足球和动态能量流贯穿画面，沿动线融合广州塔、深圳平安金融中心、珠海渔女雕像、岭南建筑、佛山武术剪影、中山文化符号、潮汕英歌舞与清远山水。现代国潮高级海报风格，中国红主视觉，青蓝辅助，金色高光，带完整中文排版与电影级光影。",
        "originalTitle": "Guangdong Super League Invitation Poster",
        "prompt": "广东省城市足球超级联赛（粤超）邀请函海报设计，比例 9:16。S 型流动构图，以发光足球和动态能量流贯穿画面，沿动线融合广州塔、深圳平安金融中心、珠海渔女雕像、岭南建筑、佛山武术剪影、中山文化符号、潮汕英歌舞与清远山水。现代国潮高级海报风格，中国红主视觉，青蓝辅助，金色高光，带完整中文排版与电影级光影。",
        "translated": false
      },
      {
        "caseNumber": 14,
        "title": "2026年春季广州宣传海报",
        "sourceUrl": "https://x.com/grok/status/2046012437086818395",
        "author": "@grok",
        "authorUrl": "https://x.com/grok",
        "originalPrompt": "一张充满新春喜庆但高雅的 2026 广州城市宣传海报，9:16 竖版，双重曝光，S 型流动构图。纯白纹理背景，右下角微缩传统服饰人物挥舞长红绸，红绸变形成山脉河流，内部叠加广州全景：广州塔、珠江新城、珠江、游轮、古建筑与白云山。左下角排版 “SPRING 2026” 与竖排 “千年商都 魅力广州”。",
        "originalTitle": "Spring 2026 Guangzhou Promo Poster",
        "prompt": "一张充满新春喜庆但高雅的 2026 广州城市宣传海报，9:16 竖版，双重曝光，S 型流动构图。纯白纹理背景，右下角微缩传统服饰人物挥舞长红绸，红绸变形成山脉河流，内部叠加广州全景：广州塔、珠江新城、珠江、游轮、古建筑与白云山。左下角排版 “SPRING 2026” 与竖排 “千年商都 魅力广州”。",
        "translated": false
      },
      {
        "caseNumber": 15,
        "title": "史诗剪影世界海报",
        "sourceUrl": "https://x.com/Ghhhh3owi/status/2045803217251102897",
        "author": "@Ghhhh3owi",
        "authorUrl": "https://x.com/Ghhhh3owi",
        "originalPrompt": "收藏版史诗海报，人物侧脸剪影中生长出完整世界观与经典场景。整体偏电影海报加梦幻水彩插画风，安静、宏大、神圣、怀旧，带纸张颗粒、轻雾感、飞白刷痕与高级留白。",
        "originalTitle": "Epic Silhouette World Poster",
        "prompt": "收藏版史诗海报，人物侧脸剪影中生长出完整世界观与经典场景。整体偏电影海报加梦幻水彩插画风，安静、宏大、神圣、怀旧，带纸张颗粒、轻雾感、飞白刷痕与高级留白。",
        "translated": false
      },
      {
        "caseNumber": 24,
        "title": "春天广州城市海报",
        "sourceUrl": "https://x.com/alanlovelq/status/2045484598487060917",
        "author": "@alanlovelq",
        "authorUrl": "https://x.com/alanlovelq",
        "originalPrompt": "一张充满新春喜庆氛围但不失高雅格调的 2026 城市宣传海报。\n双重曝光，构图延续了S型的流动感；\n在纯白的纹理背景右下角，一个身穿中国传统服饰的微缩人物正在挥舞着一条长长的红色丝绸舞带，这条红绸在空中舞动，不仅展现出丝绸的柔顺质感，更在向左上方飘动的过程中，奇幻地变形成了一条壮丽的山脉河流。\n在这条“河流”中，叠加了一个有山有海河的广州城市手绘图，国潮，景色尽在眼底，壮阔雄伟，令人震撼。\n广州的地标建筑(广州塔，珠江新城建筑群，珠江, 广州城里古建筑，游轮，白云山）。\n云雾环绕，仙气缥缈，色彩丰富，结构复杂，细节丰富，但因为大面积的留白，画面依然显得清新脱俗，左下角排版着“SPRING 2026”和竖排的宣传语，整体寓意“千年商都，魅力广州”。\n文字排版优美，大方，字迹清晰完整，尺寸9:16。",
        "originalTitle": "Spring Guangzhou City Poster",
        "prompt": "一张充满新春喜庆氛围但不失高雅格调的 2026 城市宣传海报。\n双重曝光，构图延续了S型的流动感；\n在纯白的纹理背景右下角，一个身穿中国传统服饰的微缩人物正在挥舞着一条长长的红色丝绸舞带，这条红绸在空中舞动，不仅展现出丝绸的柔顺质感，更在向左上方飘动的过程中，奇幻地变形成了一条壮丽的山脉河流。\n在这条“河流”中，叠加了一个有山有海河的广州城市手绘图，国潮，景色尽在眼底，壮阔雄伟，令人震撼。\n广州的地标建筑(广州塔，珠江新城建筑群，珠江, 广州城里古建筑，游轮，白云山）。\n云雾环绕，仙气缥缈，色彩丰富，结构复杂，细节丰富，但因为大面积的留白，画面依然显得清新脱俗，左下角排版着“SPRING 2026”和竖排的宣传语，整体寓意“千年商都，魅力广州”。\n文字排版优美，大方，字迹清晰完整，尺寸9:16。",
        "translated": false
      },
      {
        "caseNumber": 26,
        "title": "穷奇东方美学海报",
        "sourceUrl": "https://x.com/liyue_ai/status/2045506567735558336",
        "author": "@liyue_ai",
        "authorUrl": "https://x.com/liyue_ai",
        "originalPrompt": "极简主义，新中式风格立体图形设计，图像下端有楷体中国文字：“东方美学”，“2026/04/18”，署名 “CHINA”，和“@LIYUE\"；\n平整纯白色的亚光质感厚艺术纸上绘充满东方诗意氛围的山水创意画，不规则的撕纸效果；\n中国的神兽：穷奇，身形图案完整，美轮美奂，，线条柔美灵动,眼睛炯炯有神，威严的神态，优雅的姿势，奢华装饰艺术，中国传统纹饰；\n荧光蓝色线条，0.5mm极细金色金属质感勾边，泼白墨大笔触，色彩渲染，红底，蓝色的浪漫诗意视觉；\n冷暖光交织的梦幻唯美场景，强烈的光影对比氛围，花轻舞的时光叙事，东风禅意，画面有大面积留白，框架构图，底部留白，细节清晰。",
        "originalTitle": "Qiongqi Eastern Aesthetics Poster",
        "prompt": "极简主义，新中式风格立体图形设计，图像下端有楷体中国文字：“东方美学”，“2026/04/18”，署名 “CHINA”，和“@LIYUE\"；\n平整纯白色的亚光质感厚艺术纸上绘充满东方诗意氛围的山水创意画，不规则的撕纸效果；\n中国的神兽：穷奇，身形图案完整，美轮美奂，，线条柔美灵动,眼睛炯炯有神，威严的神态，优雅的姿势，奢华装饰艺术，中国传统纹饰；\n荧光蓝色线条，0.5mm极细金色金属质感勾边，泼白墨大笔触，色彩渲染，红底，蓝色的浪漫诗意视觉；\n冷暖光交织的梦幻唯美场景，强烈的光影对比氛围，花轻舞的时光叙事，东风禅意，画面有大面积留白，框架构图，底部留白，细节清晰。",
        "translated": false
      },
      {
        "caseNumber": 27,
        "title": "广州剪纸城市海报",
        "sourceUrl": "https://x.com/liyue_ai/status/2045527750606487877",
        "author": "@liyue_ai",
        "authorUrl": "https://x.com/liyue_ai",
        "originalPrompt": "以珠江新城现代都市景观为灵感的剪纸艺术，通过精巧的镂空手法在一整幅纸上，立体刻画广州塔、东西双塔等地标建筑与繁华城景。\n所有建筑与元素均以流畅的线条与结构相连，无孤立部分，构成一幅完整的都市画卷。\n画面采用金属箔或光泽纸材质，表面带有细腻的明暗光泽，在光照下呈现柔和的高光与阴影，仿佛被城市灯光轻轻照亮。\n背景以虚化的珠江新城天际线为衬，点缀隐约可见的花城广场与树木轮廓，整体透出现代浪漫的氛围。\n作品中巧妙融入轻盈的蒲公英绒毛或星光般的动态光点，象征梦想与活力在这座新城中飘散飞扬。整体呈现8K超高清视觉，细节丰富，真实而富有艺术感染力。",
        "originalTitle": "Guangzhou Paper-Cut City Poster",
        "prompt": "以珠江新城现代都市景观为灵感的剪纸艺术，通过精巧的镂空手法在一整幅纸上，立体刻画广州塔、东西双塔等地标建筑与繁华城景。\n所有建筑与元素均以流畅的线条与结构相连，无孤立部分，构成一幅完整的都市画卷。\n画面采用金属箔或光泽纸材质，表面带有细腻的明暗光泽，在光照下呈现柔和的高光与阴影，仿佛被城市灯光轻轻照亮。\n背景以虚化的珠江新城天际线为衬，点缀隐约可见的花城广场与树木轮廓，整体透出现代浪漫的氛围。\n作品中巧妙融入轻盈的蒲公英绒毛或星光般的动态光点，象征梦想与活力在这座新城中飘散飞扬。整体呈现8K超高清视觉，细节丰富，真实而富有艺术感染力。",
        "translated": false
      },
      {
        "caseNumber": 28,
        "title": "极端视角排版桥",
        "sourceUrl": "https://x.com/xpg0970/status/2045560665071579160",
        "author": "@xpg0970",
        "authorUrl": "https://x.com/xpg0970",
        "originalPrompt": "①场景 跨海大桥的侧面，dramatic cinematic angle。 巨型 bold sans-serif 文字「___②文字内容 跨海大桥」painted onto the surface of ___③主体物 无，从靠近镜头的前端开始，沿表面向远端 progressively foreshortens 逐渐透视压缩，letterforms conform to surface curvature 贴合物体曲面，surface-integrated not floating。 文字部分区域被 无___④前景遮挡物 无___ occluded and hidden，在间隙中露出， 形成 depth-layering 纵深穿插效果。 Oversized bright yellow + sharp orange outline，extreme perspective distortion aligned to vanishing point。Cinematic lighting, motion blur, poster-grade dynamic integrated typography, modern advertising aesthetics。",
        "originalTitle": "Extreme Perspective Typography Bridge",
        "prompt": "①场景 跨海大桥的侧面，dramatic cinematic angle。 巨型 bold sans-serif 文字「___②文字内容 跨海大桥」painted onto the surface of ___③主体物 无，从靠近镜头的前端开始，沿表面向远端 progressively foreshortens 逐渐透视压缩，letterforms conform to surface curvature 贴合物体曲面，surface-integrated not floating。 文字部分区域被 无___④前景遮挡物 无___ occluded and hidden，在间隙中露出， 形成 depth-layering 纵深穿插效果。 Oversized bright yellow + sharp orange outline，extreme perspective distortion aligned to vanishing point。Cinematic lighting, motion blur, poster-grade dynamic integrated typography, modern advertising aesthetics。",
        "translated": true
      },
      {
        "caseNumber": 31,
        "title": "梦幻水彩社论插图",
        "sourceUrl": "https://x.com/hmontilla_/status/2045513933096636575",
        "author": "@hmontilla_",
        "authorUrl": "https://x.com/hmontilla_",
        "originalPrompt": "Ilustración en acuarela de estilo onírico de [sujeto], con estética impresionista ligera, pinceladas sueltas y lavados translúcidos en tonos [color1] y [color2]. Difuminado suave sobre textura de papel prensado en frío, iluminación delicada, composición limpia, enfoque minimalista, sensación de calma, ligereza y belleza efímera, alta calidad, estilo editorial.",
        "originalTitle": "Dreamy Watercolor Editorial Illustration",
        "prompt": "梦境风格的【主题】水彩插画，带有淡淡的印象派美学，宽松的笔触和半透明的【颜色1】和【颜色2】色调的水洗。冷压纸张纹理上的柔和模糊，精致的灯光，干净的构图，简约的方法，平静的感觉，轻盈和短暂的美，高品质，编辑风格。",
        "translated": true
      },
      {
        "caseNumber": 32,
        "title": "科学百科全书垂直海报",
        "sourceUrl": "https://x.com/pfanis/status/2046413660147314714",
        "author": "@pfanis",
        "authorUrl": "https://x.com/pfanis",
        "originalPrompt": "Generate a high-quality vertical science popularization encyclopedia image based on [Theme].",
        "originalTitle": "Science Encyclopedia Vertical Poster",
        "prompt": "基于【主题】生成高质量的垂直科普百科图片。",
        "translated": true
      },
      {
        "caseNumber": 33,
        "title": "西游记中国漫画",
        "sourceUrl": "https://x.com/overseas58/status/2046271877577097376",
        "author": "@overseas58",
        "authorUrl": "https://x.com/overseas58",
        "originalPrompt": "以中国连环画（小人书）的风格帮我绘制大闹天空",
        "originalTitle": "Journey to the West Chinese Comic",
        "prompt": "以中国连环画（小人书）的风格帮我绘制大闹天空",
        "translated": false
      },
      {
        "caseNumber": 34,
        "title": "人物关系图海报",
        "sourceUrl": "https://x.com/MrLarus/status/2046263153546174935",
        "author": "@MrLarus",
        "authorUrl": "https://x.com/MrLarus",
        "originalPrompt": "请根据【主题】生成一张高设计感的人物关系图海报。",
        "originalTitle": "Character Relationship Map Poster",
        "prompt": "请根据【主题】生成一张高设计感的人物关系图海报。",
        "translated": false
      },
      {
        "caseNumber": 35,
        "title": "新水墨山水海报",
        "sourceUrl": "https://x.com/liyue_ai/status/2046215276249993720",
        "author": "@liyue_ai",
        "authorUrl": "https://x.com/liyue_ai",
        "originalPrompt": "新中式水墨山水海报，竖版9:16构图，东方极简美学风格，大面积留白，主题是春岚一叶红。",
        "originalTitle": "New Chinese Ink Landscape Poster",
        "prompt": "新中式水墨山水海报，竖版9:16构图，东方极简美学风格，大面积留白，主题是春岚一叶红。",
        "translated": false
      },
      {
        "caseNumber": 36,
        "title": "AI 生成器涂鸦草图",
        "sourceUrl": "https://x.com/opc_8838/status/2046162334440448339",
        "author": "@opc_8838",
        "authorUrl": "https://x.com/opc_8838",
        "originalPrompt": "以涂鸦速写风表现【一个厉害的AI builder】。",
        "originalTitle": "AI Builder Doodle Sketch",
        "prompt": "以涂鸦速写风表现【一个厉害的AI builder】。",
        "translated": false
      },
      {
        "caseNumber": 38,
        "title": "人物视觉垂直海报",
        "sourceUrl": "https://x.com/tebasaki3D/status/2046371076402503709",
        "author": "@tebasaki3D",
        "authorUrl": "https://x.com/tebasaki3D",
        "originalPrompt": "『神層37区 特級執行官 神巫サバト』この名称のキャラクターと世界観に合ったビジュアルイメージを、プロのデザイナーとして縦長のポスターイメージとして制作して",
        "originalTitle": "Character Visual Vertical Poster",
        "prompt": "「神级37区特级执法者神女祭司萨巴托」作为一名专业设计师，我创作了一个与这个名字的性格和世界观相匹配的视觉形象作为垂直海报图像。",
        "translated": true
      },
      {
        "caseNumber": 39,
        "title": "科学百科全书信息图",
        "sourceUrl": "https://x.com/MrLarus/status/2046231542817497392",
        "author": "@MrLarus",
        "authorUrl": "https://x.com/MrLarus",
        "originalPrompt": "请根据【主题】生成一张高质量竖版「科普百科图」。 \n\n这张图不是普通海报,也不是单纯插画,而是一张兼具“图鉴感、百科感、信息结构感、收藏感”的模块化科普信息图。整体风格参考高级博物图鉴、现代百科书页、生活方式知识卡和社交媒体高传播信息图的结合。\n\n请让画面包含:\n- 一个清晰漂亮的主题主视觉\n- 若干局部特征放大细节\n- 多个圆角模块化信息分区\n- 清楚的标题层级与重点标签\n- 简洁但丰富的百科内容\n- 可视化评分、要点总结或Top 5模块\n\n内容栏目请根据主题自动适配,优先从这些方向中选择并合理组合:\n基础档案、分类信息、外观特征、习性/生态、形成机制/结构组成、生长或使用条件、养护或维护建议、风险与注意事项、适合人群或适用场景、优缺点对比、快速评分卡。\n\n视觉要求:\n浅色干净背景,柔和配色,轻阴影,精致小图标,圆角信息框,整洁排版,信息密度高但不拥挤,阅读体验好。整体必须像真正可以发布、阅读、收藏、系列化生产的科普百科卡,而不是广告图。\n\n请不要做成普通商业宣传海报。要突出“知识整理 + 模块信息 + 图鉴式展示”的特征。",
        "originalTitle": "Science Encyclopedia Infographic",
        "prompt": "请根据【主题】生成一张高质量竖版「科普百科图」。 \n\n这张图不是普通海报,也不是单纯插画,而是一张兼具“图鉴感、百科感、信息结构感、收藏感”的模块化科普信息图。整体风格参考高级博物图鉴、现代百科书页、生活方式知识卡和社交媒体高传播信息图的结合。\n\n请让画面包含:\n- 一个清晰漂亮的主题主视觉\n- 若干局部特征放大细节\n- 多个圆角模块化信息分区\n- 清楚的标题层级与重点标签\n- 简洁但丰富的百科内容\n- 可视化评分、要点总结或Top 5模块\n\n内容栏目请根据主题自动适配,优先从这些方向中选择并合理组合:\n基础档案、分类信息、外观特征、习性/生态、形成机制/结构组成、生长或使用条件、养护或维护建议、风险与注意事项、适合人群或适用场景、优缺点对比、快速评分卡。\n\n视觉要求:\n浅色干净背景,柔和配色,轻阴影,精致小图标,圆角信息框,整洁排版,信息密度高但不拥挤,阅读体验好。整体必须像真正可以发布、阅读、收藏、系列化生产的科普百科卡,而不是广告图。\n\n请不要做成普通商业宣传海报。要突出“知识整理 + 模块信息 + 图鉴式展示”的特征。",
        "translated": false
      },
      {
        "caseNumber": 40,
        "title": "虚构动漫电影海报",
        "sourceUrl": "https://x.com/seiiiiiiiiiiru/status/2046509734954741780",
        "author": "@seiiiiiiiiiiru",
        "authorUrl": "https://x.com/seiiiiiiiiiiru",
        "originalPrompt": "架空のアニメ映画のポスターをGPT image2で作成。",
        "originalTitle": "Fictional Anime Movie Poster",
        "prompt": "使用 GPT image2 为虚构的动漫电影创建海报。",
        "translated": true
      },
      {
        "caseNumber": 41,
        "title": "产品广告重新设计",
        "sourceUrl": "https://x.com/genel_ai/status/2046498264774791514",
        "author": "@genel_ai",
        "authorUrl": "https://x.com/genel_ai",
        "originalPrompt": "この商品広告をプロのデザイナー目線でリデザインして。\n今のトレンド、ターゲットに合わせた洗練されたデザインで。",
        "originalTitle": "Product Ad Redesign",
        "prompt": "从专业设计师的角度重新设计这个产品广告。\n凭借针对当前趋势和目标量身定制的精致设计。",
        "translated": true
      },
      {
        "caseNumber": 42,
        "title": "暗黑奇幻广州城海报",
        "sourceUrl": "https://x.com/liyue_ai/status/2046243132774494607",
        "author": "@liyue_ai",
        "authorUrl": "https://x.com/liyue_ai",
        "originalPrompt": "平面插画,东方幻想风格高端城市海报设计,竖版9:16构图,整体采用对角线+S型流动构图,从左下向右上延展,画面以深邃黑色为背景,自上而下渐变至浓烈暗红色,形成强烈冷暖对比与空间纵深,背景带微弱星尘与颗粒质感。画面中央一条金色流动能量线条如火焰般蜿蜒贯穿,自底部向上延伸,具有流体质感、粒子光效与渐变高光,局部带细微能量碎屑与体积光。\n\n金色流光中逐层浮现广州城市地标建筑群:广州塔为视觉核心,比例突出,周围融合珠江新城高楼群、猎德大桥及现代与岭南建筑元素,建筑采用“精细线描 + 金色发光体块”表现,轮廓清晰、细节丰富,在金色光晕映衬下仿佛悬浮于虚空,形成超现实空间层次,远景轻微雾化增强纵深感。\n\n画面底部为一位东方白发女性形象,长发飘逸,如烟似雾,与金色流光自然衔接并逐渐融合,发丝半透明带渐变光感,姿态柔美,双目微闭,神情宁静,怀抱一束多彩鲜花,花间点缀微光粒子与星点效果,象征人与城市能量的精神连接,人物细节适度简化以突出整体设计感。\n\n光影集中于金色流线、建筑与人物轮廓,形成强烈明暗对比与视觉聚焦,整体氛围宏大、神秘、具有东方神话意境且略带治愈感。色彩以黑与暗红为基底,高亮鎏金为主视觉强调,金色具备丰富明暗层次,辅以小面积高饱和花束色彩点缀,整体高级克制。\n\n页面文字与画面融合排版:顶部居中宋体大字“广州·中国”,下方小字“2026/04/20”,再下方小字“LIYUE”,文字采用淡金色或柔和暖白色,与整体光影统一。高品质细节,电影级光影表现,体积光与粒子细节丰富,画面干净无噪点,超高清8K分辨率,商业级海报质感。",
        "originalTitle": "Dark-Fantasy Guangzhou City Poster",
        "prompt": "平面插画,东方幻想风格高端城市海报设计,竖版9:16构图,整体采用对角线+S型流动构图,从左下向右上延展,画面以深邃黑色为背景,自上而下渐变至浓烈暗红色,形成强烈冷暖对比与空间纵深,背景带微弱星尘与颗粒质感。画面中央一条金色流动能量线条如火焰般蜿蜒贯穿,自底部向上延伸,具有流体质感、粒子光效与渐变高光,局部带细微能量碎屑与体积光。\n\n金色流光中逐层浮现广州城市地标建筑群:广州塔为视觉核心,比例突出,周围融合珠江新城高楼群、猎德大桥及现代与岭南建筑元素,建筑采用“精细线描 + 金色发光体块”表现,轮廓清晰、细节丰富,在金色光晕映衬下仿佛悬浮于虚空,形成超现实空间层次,远景轻微雾化增强纵深感。\n\n画面底部为一位东方白发女性形象,长发飘逸,如烟似雾,与金色流光自然衔接并逐渐融合,发丝半透明带渐变光感,姿态柔美,双目微闭,神情宁静,怀抱一束多彩鲜花,花间点缀微光粒子与星点效果,象征人与城市能量的精神连接,人物细节适度简化以突出整体设计感。\n\n光影集中于金色流线、建筑与人物轮廓,形成强烈明暗对比与视觉聚焦,整体氛围宏大、神秘、具有东方神话意境且略带治愈感。色彩以黑与暗红为基底,高亮鎏金为主视觉强调,金色具备丰富明暗层次,辅以小面积高饱和花束色彩点缀,整体高级克制。\n\n页面文字与画面融合排版:顶部居中宋体大字“广州·中国”,下方小字“2026/04/20”,再下方小字“LIYUE”,文字采用淡金色或柔和暖白色,与整体光影统一。高品质细节,电影级光影表现,体积光与粒子细节丰富,画面干净无噪点,超高清8K分辨率,商业级海报质感。",
        "translated": false
      },
      {
        "caseNumber": 45,
        "title": "科幻电影海报",
        "sourceUrl": "https://x.com/underwoodxie96/status/2046514205529088501",
        "author": "@underwoodxie96",
        "authorUrl": "https://x.com/underwoodxie96",
        "originalPrompt": "Create a Science fiction movie poster",
        "originalTitle": "Science Fiction Movie Poster",
        "prompt": "制作科幻电影海报",
        "translated": true
      },
      {
        "caseNumber": 46,
        "title": "清爽夏日乌冬面广告",
        "sourceUrl": "https://x.com/genel_ai/status/2046501692246470871",
        "author": "@genel_ai",
        "authorUrl": "https://x.com/genel_ai",
        "originalPrompt": "少し暑くなってきた今の時期に、さわやかにさっぱりしたい、みずみずしさ、みたいなところをもっと強く感じたい。冷たいうどんやナス、つゆを口に含んだ時の爽快感、みたいなものをもっと感じるように",
        "originalTitle": "Refreshing Summer Udon Ad",
        "prompt": "现在天气越来越热了，我想要更清爽、更清爽。我想更多地感受到将冷乌冬面、茄子或汤放入口中时的清爽感。",
        "translated": true
      },
      {
        "caseNumber": 47,
        "title": "手写的医疗处方表",
        "sourceUrl": "https://x.com/MrLarus/status/2046514998965371144",
        "author": "@MrLarus",
        "authorUrl": "https://x.com/MrLarus",
        "originalPrompt": "生成一张手写中/西医药方图",
        "originalTitle": "Handwritten Medical Prescription Sheet",
        "prompt": "生成一张手写中/西医药方图",
        "translated": false
      },
      {
        "caseNumber": 48,
        "title": "硅谷 2026 宣传海报",
        "sourceUrl": "https://x.com/carsonyungos/status/2046523198116889064",
        "author": "@carsonyungos",
        "authorUrl": "https://x.com/carsonyungos",
        "originalPrompt": "A refined 2026 Silicon Valley city promotional poster with a futuristic yet elegant atmosphere.\n\nDouble exposure composition, preserving an S-shaped sense of flowing movement. On a pure white textured background, in the lower-right corner, a miniature figure dressed in sleek modern techwear is releasing a long ribbon of luminous silver-blue light. The ribbon flows gracefully through the air, showing a soft silk-like texture, and as it drifts toward the upper-left, it magically transforms into a grand landscape of rolling hills, coastline, data streams, and illuminated urban terrain.\n\nWithin this flowing “river of light,” overlay a hand-drawn panoramic map of Silicon Valley, blending technology, nature, innovation, and California sunlight. The scene feels visionary, expansive, sophisticated, and inspiring.\n\nInclude iconic Silicon Valley and Bay Area elements: Stanford University arches, Apple Park, Google campus-inspired buildings, Meta-like glass offices, Tesla-style innovation imagery, venture capital offices on Sand Hill Road, Palo Alto tree-lined streets, San Jose skyline, the Santa Cruz Mountains, San Francisco Bay, highways, autonomous vehicles, startup labs, semiconductor patterns, AI data centers, and subtle circuit-board textures.\n\nSurrounded by soft mist, golden California light, floating clouds, and delicate digital particles. Rich colors, complex structure, highly detailed, grand and breathtaking, yet still fresh and minimal because of the large areas of white space.\n\nIn the lower-left corner, elegant typography reads “SILICON VALLEY 2026” with a vertical promotional slogan: “Where Ideas Shape Tomorrow.” Beautiful editorial layout, graceful spacing, clear and complete lettering, premium city branding poster, cinematic lighting, sophisticated details, 9:16 aspect ratio.",
        "originalTitle": "Silicon Valley 2026 Promo Poster",
        "prompt": "精致的2026硅谷城市宣传海报，未来感又不失优雅气息。\n\n双曝光构图，保留S形的流动感。在纯白色的纹理背景上，右下角，一个穿着时尚现代科技服装的微型人物正在释放出一条长长的银蓝色光带。丝带在空中优雅飘逸，呈现出丝绸般柔软的质感，当它向左上方飘移时，它神奇地幻化成连绵起伏的丘陵、海岸线、数据流和照亮的城市地形的宏伟景观。\n\n在这条流动的“光之河”中，叠加了一张手绘的硅谷全景地图，融合了科技、自然、创新和加州的阳光。这个场景给人一种有远见、广阔、复杂和鼓舞人心的感觉。\n\n包括标志性的硅谷和湾区元素：斯坦福大学拱门、苹果公园、谷歌校园风格的建筑、类似 Meta 的玻璃办公室、特斯拉风格的创新图像、沙山路的风险投资办公室、帕洛阿尔托绿树成荫的街道、圣何塞的天际线、圣克鲁斯山脉、旧金山湾、高速公路、自动驾驶汽车、初创实验室、半导体图案、人工智能数据中心和微妙的电路板纹理。\n\n周围环绕着柔和的薄雾、金色的加州阳光、浮云和精致的数字粒子。色彩丰富，结构复杂，细节丰富，气势磅礴，令人叹为观止，但又因大面积的留白而显得清新简约。\n\n左下角，优雅的字体写着“SILICON VALLEY 2026”，并竖排宣传口号：“Where Ideas Shape Tomorrow”。精美的编辑布局、优雅的间距、清晰完整的字体、优质的城市品牌海报、电影般的灯光、精致的细节、9:16 的宽高比。",
        "translated": true
      },
      {
        "caseNumber": 49,
        "title": "日本超市促销传单",
        "sourceUrl": "https://x.com/weel_corp/status/2046514558064586782",
        "author": "@weel_corp",
        "authorUrl": "https://x.com/weel_corp",
        "originalPrompt": "『賑やかで魅力的なスーパーマーケットの折り込みチラシの画像。上部には「特売」の大きな文字と今週の日付。カラフルな商品写真(野菜・果物・牛肉・鮮魚)、赤枠の価格タグ、「超目玉商品」「家計応援」のキャッチ...』",
        "originalTitle": "Japanese Supermarket Sale Flyer",
        "prompt": "``生动而有吸引力的超市插页传单的图像。顶部是大写字母“SALE”和本周的日期。色彩缤纷的产品照片（蔬菜、水果、牛肉、鲜鱼）、红框价格标签、“超级特色产品”和“家庭预算支持”的标语……”",
        "translated": true
      },
      {
        "caseNumber": 50,
        "title": "黑暗史诗概念海报",
        "sourceUrl": "https://x.com/A9Quant/status/2046224777208361126",
        "author": "@A9Quant",
        "authorUrl": "https://x.com/A9Quant",
        "originalPrompt": "围绕【主题】自动生成一张顶级暗黑史诗概念海报 / 电影感信息图海报。\n\n唯一需要输入的变量只有:\n【主题】:___特朗普的思考____ \n\n除【主题】之外,其余全部由 AI 自动适配完成,包括但不限于:\n- 核心主体(自动判断更适合人物、守护者、战士、产品、器物、雕像、抽象象征或其他主视觉对象)\n- 中央承载结构(自动判断更适合王座、石座、祭坛、机械基座、遗迹、高台或其他支撑体)\n- 环境空间(自动判断更适合洞穴、神殿、废墟、深渊、地下宫殿、密室或其他封闭史诗空间)\n- 上方开口与光源形式(自动判断更适合月光、神光、能量束、审判之光、圣光或其他单一强光)\n- 象征元素(自动判断更适合骷髅、徽记、残碑、纹章、符文、能量环、神性符号等)\n- 色彩体系\n- 材质组合\n- 标题、副标题、辅助文案\n- 排版与整体叙事气质\n\n【总风格】\n高预算 90 年代好莱坞史诗大片海报气质,融合 cinematic matte painting、超写实摄影质感、极强明暗对比、厚重空间叙事、暗黑英雄主义与仪式感构图。整体必须像一张真正的电影主海报,而不是普通插画或电商图。\n\n【核心结构锁定】\n整张海报必须保留以下结构基因:\n1. 一个巨大、压迫感极强的黑暗封闭空间\n2. 一束从上方斜向切入的强烈体积光,作为画面的第一视觉秩序\n3. 中央偏右或光束终点位置的核心主体与承载结构\n4. 左下角作为高密度标题与信息锚点\n5. 四周保留大量纯黑或近黑负空间,形成电影感呼吸区\n\n【自动适配规则】\nAI 必须依据【主题】自动推导最适合的视觉系统:\n- 如果【主题】偏暗黑英雄、复仇、正义、孤独、宿命,则自动偏向石质王座、孤高人物、冷色神光、废墟或洞穴感空间\n- 如果【主题】偏神秘、幽灵、潜行、幻影、夜行,则自动偏向月光、迷雾、冷蓝色体积光、深渊式黑暗空间\n- 如果【主题】偏权力、统治、王者、秩序,则自动强化 throne / altar / crown-like symbol / ritual space 的表达\n- 如果【主题】偏科技、AI、未来、机械,则自动将王座和空间替换为机械神座、能量基座、金属洞窟、工业神殿等未来化形态\n- 如果【主题】偏产品、品牌、器物,则自动把核心主体替换为最合适的 hero object,并保留被神光审判式凸显的史诗构图\n\n【画布与色彩系统】\n- 背景底层必须是极深、近乎吞噬一切的黑暗空间\n- 主环境色由 AI 根据【主题】自动决定,但整体必须克制,以暗色为主\n- 强光区域色彩必须高度集中,只服务于体积光与主体高光\n- 主题色 / 强调色只能集中用于主视觉核心,不允许全画面泛滥\n- 必须建立明确的“黑暗底色 + 单一主光 + 少量主题强调色”的层级秩序\n\n【构图与视觉重力】\n- 采用强烈的斜向张力与向中心汇聚的视觉引导\n- 视觉重力从上方光源强势落下,最终压在核心主体之上\n- 主体必须处于被命运、审判、神性或权力照中的位置\n- 边缘必须自然融入黑暗,不能出现无意义背景填充\n- 所有元素必须服务于唯一的主叙事核心\n\n【材质与光影】\n- 不使用轮廓线,不使用平面化描边\n- 完全依赖体积光、阴影切割、反射、高光、雾气、粉尘、湿润岩石或其他真实材质来建构画面\n- 材质必须形成明显对比,例如:\n  粗粝岩石 / 冷硬金属 / 柔韧织物 / 古老石雕 / 湿润表面 / 尘雾光柱\n- 光束必须具有强烈 Tyndall effect,真实、厚重、可感知体积密度\n\n【排版系统】\n- 整体 80% 视觉,20% 文字\n- AI 根据【主题】自动生成主标题、副标题和底部信息块\n- 主标题应尽量简洁、有气势、有电影海报感\n- 若主题更适合中文,则优先中文;若更适合英文,则自动英文;也可双语,但必须统一\n- 主标题可沿光束垂直排布,仿佛由光本身构成\n- 左下角设置一个高密度信息模块,包括副标题、小字信息、电影 credits 风格占位文字或品牌说明\n- 文字必须锐利、干净、真实嵌入环境,不得廉价漂浮\n\n【模块结构 —— 必须严格保持 3 块】\n[MOD 1: TOP-TO-CENTER BEAM]\n从顶部开口斜向切下的巨大体积光柱,作为第一视觉通道,并承载主标题或主视觉文字。\n\n[MOD 2: CENTER-RIGHT CORE]\n位于光束终点的核心主体与承载结构,形成整张海报的权力中心 / 命运中心 / 叙事中心。\n\n[MOD 3: BOTTOM-LEFT TEXT]\n位于左下角负空间中的高密度排版区,包含副标题、说明文字、credits 风格信息块、品牌信息或活动信息。\n\n【作者署名】\n在底部角落自然加入作者署名:\n@a9quant\n署名要小而清晰,精致、克制、高级,不喧宾夺主,像正式电影概念海报或艺术作品落款。\n\n【输出要求】\n输出为单张统一构图海报。\n所有视觉系统必须内部一致,不能有风格污染。\n画面必须具备:暗黑感、史诗感、压迫感、仪式感、命运感、电影完成度。\n最大细节密度,超清,电影级,印刷级,高端成片质感。",
        "originalTitle": "Dark Epic Concept Poster",
        "prompt": "围绕【主题】自动生成一张顶级暗黑史诗概念海报 / 电影感信息图海报。\n\n唯一需要输入的变量只有:\n【主题】:___特朗普的思考____ \n\n除【主题】之外,其余全部由 AI 自动适配完成,包括但不限于:\n- 核心主体(自动判断更适合人物、守护者、战士、产品、器物、雕像、抽象象征或其他主视觉对象)\n- 中央承载结构(自动判断更适合王座、石座、祭坛、机械基座、遗迹、高台或其他支撑体)\n- 环境空间(自动判断更适合洞穴、神殿、废墟、深渊、地下宫殿、密室或其他封闭史诗空间)\n- 上方开口与光源形式(自动判断更适合月光、神光、能量束、审判之光、圣光或其他单一强光)\n- 象征元素(自动判断更适合骷髅、徽记、残碑、纹章、符文、能量环、神性符号等)\n- 色彩体系\n- 材质组合\n- 标题、副标题、辅助文案\n- 排版与整体叙事气质\n\n【总风格】\n高预算 90 年代好莱坞史诗大片海报气质,融合 cinematic matte painting、超写实摄影质感、极强明暗对比、厚重空间叙事、暗黑英雄主义与仪式感构图。整体必须像一张真正的电影主海报,而不是普通插画或电商图。\n\n【核心结构锁定】\n整张海报必须保留以下结构基因:\n1. 一个巨大、压迫感极强的黑暗封闭空间\n2. 一束从上方斜向切入的强烈体积光,作为画面的第一视觉秩序\n3. 中央偏右或光束终点位置的核心主体与承载结构\n4. 左下角作为高密度标题与信息锚点\n5. 四周保留大量纯黑或近黑负空间,形成电影感呼吸区\n\n【自动适配规则】\nAI 必须依据【主题】自动推导最适合的视觉系统:\n- 如果【主题】偏暗黑英雄、复仇、正义、孤独、宿命,则自动偏向石质王座、孤高人物、冷色神光、废墟或洞穴感空间\n- 如果【主题】偏神秘、幽灵、潜行、幻影、夜行,则自动偏向月光、迷雾、冷蓝色体积光、深渊式黑暗空间\n- 如果【主题】偏权力、统治、王者、秩序,则自动强化 throne / altar / crown-like symbol / ritual space 的表达\n- 如果【主题】偏科技、AI、未来、机械,则自动将王座和空间替换为机械神座、能量基座、金属洞窟、工业神殿等未来化形态\n- 如果【主题】偏产品、品牌、器物,则自动把核心主体替换为最合适的 hero object,并保留被神光审判式凸显的史诗构图\n\n【画布与色彩系统】\n- 背景底层必须是极深、近乎吞噬一切的黑暗空间\n- 主环境色由 AI 根据【主题】自动决定,但整体必须克制,以暗色为主\n- 强光区域色彩必须高度集中,只服务于体积光与主体高光\n- 主题色 / 强调色只能集中用于主视觉核心,不允许全画面泛滥\n- 必须建立明确的“黑暗底色 + 单一主光 + 少量主题强调色”的层级秩序\n\n【构图与视觉重力】\n- 采用强烈的斜向张力与向中心汇聚的视觉引导\n- 视觉重力从上方光源强势落下,最终压在核心主体之上\n- 主体必须处于被命运、审判、神性或权力照中的位置\n- 边缘必须自然融入黑暗,不能出现无意义背景填充\n- 所有元素必须服务于唯一的主叙事核心\n\n【材质与光影】\n- 不使用轮廓线,不使用平面化描边\n- 完全依赖体积光、阴影切割、反射、高光、雾气、粉尘、湿润岩石或其他真实材质来建构画面\n- 材质必须形成明显对比,例如:\n  粗粝岩石 / 冷硬金属 / 柔韧织物 / 古老石雕 / 湿润表面 / 尘雾光柱\n- 光束必须具有强烈 Tyndall effect,真实、厚重、可感知体积密度\n\n【排版系统】\n- 整体 80% 视觉,20% 文字\n- AI 根据【主题】自动生成主标题、副标题和底部信息块\n- 主标题应尽量简洁、有气势、有电影海报感\n- 若主题更适合中文,则优先中文;若更适合英文,则自动英文;也可双语,但必须统一\n- 主标题可沿光束垂直排布,仿佛由光本身构成\n- 左下角设置一个高密度信息模块,包括副标题、小字信息、电影 credits 风格占位文字或品牌说明\n- 文字必须锐利、干净、真实嵌入环境,不得廉价漂浮\n\n【模块结构 —— 必须严格保持 3 块】\n[MOD 1: TOP-TO-CENTER BEAM]\n从顶部开口斜向切下的巨大体积光柱,作为第一视觉通道,并承载主标题或主视觉文字。\n\n[MOD 2: CENTER-RIGHT CORE]\n位于光束终点的核心主体与承载结构,形成整张海报的权力中心 / 命运中心 / 叙事中心。\n\n[MOD 3: BOTTOM-LEFT TEXT]\n位于左下角负空间中的高密度排版区,包含副标题、说明文字、credits 风格信息块、品牌信息或活动信息。\n\n【作者署名】\n在底部角落自然加入作者署名:\n@a9quant\n署名要小而清晰,精致、克制、高级,不喧宾夺主,像正式电影概念海报或艺术作品落款。\n\n【输出要求】\n输出为单张统一构图海报。\n所有视觉系统必须内部一致,不能有风格污染。\n画面必须具备:暗黑感、史诗感、压迫感、仪式感、命运感、电影完成度。\n最大细节密度,超清,电影级,印刷级,高端成片质感。",
        "translated": false
      },
      {
        "caseNumber": 51,
        "title": "普拉提工作室广告海报",
        "sourceUrl": "https://x.com/ck_igarashi/status/2046528889124728993",
        "author": "@ck_igarashi",
        "authorUrl": "https://x.com/ck_igarashi",
        "originalPrompt": "ピラティス教室の広告画像を作成したい テキストはよりユーザーが登録をするのに惹かれるような文言にし、画像内には女性がピラティスを実際に行っている様子を映して",
        "originalTitle": "Pilates Studio Ad Poster",
        "prompt": "我想为普拉提课程制作一个广告图像。文字的措辞应能吸引用户注册，并且图像应显示一位正在实际做普拉提的女性。",
        "translated": true
      },
      {
        "caseNumber": 52,
        "title": "6 块时尚活动提示公式",
        "sourceUrl": "https://x.com/anacoding/status/2046904999045628114",
        "author": "@anacoding",
        "authorUrl": "https://x.com/anacoding",
        "originalPrompt": "Old money Hamptons editorial, tall blonde woman late 20s, serene elegant expression, wearing cream cashmere cable sweater, pleated beige tennis skirt, pearl earrings, Hermès silk scarf, leather flats, Slim Aarons photography style, medium format film photography, sitting on a white wooden porch of a Cape Cod house, golden hour light, ocean in the background",
        "originalTitle": "6-Block Fashion Campaign Prompt Formula",
        "prompt": "老钱汉普顿社论，二十多岁的高个子金发女人，表情宁静优雅，穿着奶油色羊绒绞花毛衣，褶皱米色网球裙，珍珠耳环，爱马仕丝巾，皮平底鞋，修身阿伦斯摄影风格，中画幅胶片摄影，坐在科德角房子的白色木门廊上，黄金时刻的光线，背景是海洋",
        "translated": true
      },
      {
        "caseNumber": 53,
        "title": "索尼A7分解图故障提示",
        "sourceUrl": "https://x.com/iaPulse_/status/2046903739429097660",
        "author": "@iaPulse_",
        "authorUrl": "https://x.com/iaPulse_",
        "originalPrompt": "Descomposición detallada de una cámara de la marca Sony modelo A7 indicando todas sus piezas y con sus nombres.",
        "originalTitle": "Sony A7 Exploded View Breakdown Prompt",
        "prompt": "索尼 A7 品牌相机的详细分解，标明其所有部件及其名称。",
        "translated": true
      },
      {
        "caseNumber": 54,
        "title": "1900 Istiklal 街全景提示",
        "sourceUrl": "https://x.com/ai_gezgini/status/2046903631509705030",
        "author": "@ai_gezgini",
        "authorUrl": "https://x.com/ai_gezgini",
        "originalPrompt": "360 equirectangular image of Istiklal Street, Istanbul in 1900",
        "originalTitle": "1900 Istiklal Street Panorama Prompt",
        "prompt": "1900 年伊斯坦布尔 Istiklal 街的 360 度等距柱状图",
        "translated": true
      },
      {
        "caseNumber": 57,
        "title": "主题科学百科卡",
        "sourceUrl": "https://x.com/alanlovelq/status/2046378199681257920",
        "author": "@alanlovelq",
        "authorUrl": "https://x.com/alanlovelq",
        "originalPrompt": "请根据【主题】生成一张高质量竖版「科普百科图」。 \n\n这张图不是普通海报,也不是单纯插画,而是一张兼具“图鉴感、百科感、信息结构感、收藏感”的模块化科普信息图。整体风格参考高级博物图鉴、现代百科书页、生活方式知识卡和社交媒体高传播信息图的结合。\n\n请让画面包含:\n- 一个清晰漂亮的主题主视觉\n- 若干局部特征放大细节\n- 多个圆角模块化信息分区\n- 清楚的标题层级与重点标签\n- 简洁但丰富的百科内容\n- 可视化评分、要点总结或Top 5模块\n\n内容栏目请根据主题自动适配,优先从这些方向中选择并合理组合:\n基础档案、分类信息、外观特征、习性/生态、形成机制/结构组成、生长或使用条件、养护或维护建议、风险与注意事项、适合人群或适用场景、优缺点对比、快速评分卡。\n\n视觉要求:\n浅色干净背景,柔和配色,轻阴影,精致小图标,圆角信息框,整洁排版,信息密度高但不拥挤,阅读体验好。整体必须像真正可以发布、阅读、收藏、系列化生产的科普百科卡,而不是广告图。\n\n请不要做成普通商业宣传海报。要突出“知识整理 + 模块信息 + 图鉴式展示”的特征。",
        "originalTitle": "Theme Science Encyclopedia Card",
        "prompt": "请根据【主题】生成一张高质量竖版「科普百科图」。 \n\n这张图不是普通海报,也不是单纯插画,而是一张兼具“图鉴感、百科感、信息结构感、收藏感”的模块化科普信息图。整体风格参考高级博物图鉴、现代百科书页、生活方式知识卡和社交媒体高传播信息图的结合。\n\n请让画面包含:\n- 一个清晰漂亮的主题主视觉\n- 若干局部特征放大细节\n- 多个圆角模块化信息分区\n- 清楚的标题层级与重点标签\n- 简洁但丰富的百科内容\n- 可视化评分、要点总结或Top 5模块\n\n内容栏目请根据主题自动适配,优先从这些方向中选择并合理组合:\n基础档案、分类信息、外观特征、习性/生态、形成机制/结构组成、生长或使用条件、养护或维护建议、风险与注意事项、适合人群或适用场景、优缺点对比、快速评分卡。\n\n视觉要求:\n浅色干净背景,柔和配色,轻阴影,精致小图标,圆角信息框,整洁排版,信息密度高但不拥挤,阅读体验好。整体必须像真正可以发布、阅读、收藏、系列化生产的科普百科卡,而不是广告图。\n\n请不要做成普通商业宣传海报。要突出“知识整理 + 模块信息 + 图鉴式展示”的特征。",
        "translated": false
      },
      {
        "caseNumber": 55,
        "title": "辣椒猪肉烹饪流程图",
        "sourceUrl": "https://x.com/Kurt_Rousey466/status/2046267707881029934",
        "author": "@Kurt_Rousey466",
        "authorUrl": "https://x.com/Kurt_Rousey466",
        "originalPrompt": "帮我制作辣椒炒肉这道菜的详细制作流程图,真实风格,适用于小红书图文比例",
        "originalTitle": "Chili Pork Cooking Flowchart",
        "prompt": "帮我制作辣椒炒肉这道菜的详细制作流程图,真实风格,适用于小红书图文比例",
        "translated": false
      },
      {
        "caseNumber": 56,
        "title": "电影信息图表概念海报",
        "sourceUrl": "https://x.com/A9Quant/status/2046228485841334559",
        "author": "@A9Quant",
        "authorUrl": "https://x.com/A9Quant",
        "originalPrompt": "请围绕【主题】自动生成一张顶级概念海报 / 信息图式电影海报。\n\n唯一输入变量只有:\n【主题】:__中国历史上的皇帝排名_         \n\n要求 AI 根据这个主题,自动推导并统一设计以下全部视觉系统,不需要我额外指定:\n- 核心主体(可以自动判断更适合人物、产品、建筑、器物、符号、场景或抽象意象)\n- 底部支撑结构\n- 上方悬浮符号或精神象征\n- 场景包裹元素\n- 隐喻系统\n- 色彩层级\n- 材质对比\n- 光影逻辑\n- 标题、副标题、辅助文案\n- 品牌感与高级感表达方式\n\n最终画面必须是:\n一张震撼、精密、统一、电影级、超高细节、可用于高端印刷的概念主视觉海报。\n\n【总风格】\n超写实 3D 商业 CGI 渲染,融合电影级布光、奢侈品视觉语言、未来感概念设计与史诗级构图。画面必须具有“唯一主视觉核心”,不能杂乱,不能像拼贴,不能像普通电商海报。\n\n【自动推导规则】\nAI 必须依据【主题】自动决定最合适的:\n1. 核心视觉隐喻\n2. 主体类型与姿态\n3. 支撑结构形式\n4. 悬浮元素形式\n5. 场景外壳与空间氛围\n6. 主色、辅色、强调色\n7. 材质组合\n8. 文字气质与版式风格\n\n例如:\n- 如果主题偏权力、秩序、资本、统治,则自动偏向王座、冠冕、机械、神殿、红幕、金属、权力结构\n- 如果主题偏科技、AI、芯片、未来,则自动偏向机械结构、能量核心、光束、深色金属、全息感\n- 如果主题偏奢侈品、高定、稀缺、收藏,则自动偏向珠宝、镜面材质、黑金体系、展台、博物馆式布光\n- 如果主题偏人物、IP、角色,则自动以人物为主视觉核心,并自动匹配对应世界观与象征系统\n- 如果主题偏城市、文明、史诗、命运,则自动转化为宏大叙事型空间结构与仪式感场景\n\n【构图规则】\n- 绝对高级感\n- 强烈中心秩序,整体统一\n- 允许中轴对称或接近中轴的史诗级构图\n- 视觉重力明确,从上到下形成清晰的层级落点\n- 边缘负空间干净、克制、有呼吸感\n- 不允许无意义装饰,不允许风格污染,不允许多个系统互相打架\n\n【视觉质量】\n- 超高细节\n- 体积光清晰\n- 材质真实\n- 反射、折射、阴影、雾气、景深自然\n- 每个元素都像经过工业级视觉总监审美控制\n- 整体达到高端品牌 campaign key visual / luxury invitation poster / conceptual editorial poster 水准\n\n【排版系统】\n- 整体为 90% 视觉,10% 文字\n- AI 根据【主题】自动生成最匹配的主标题和副标题\n- 标题必须简洁、锋利、有气势\n- 文案分布在安全负空间内,不压主体\n- 若主题适合中文,则优先生成中文标题;若主题更适合英文,则自动生成英文标题;也可中英结合,但必须统一高级\n- 文字必须尽量少而准,不要堆字\n\n【署名要求】\n在画面底部角落自然加入作者署名:\n@a9quant\n署名要小,但清晰、精致、高级,不喧宾夺主,像顶级视觉作品中的正式作者落款。\n\n【输出要求】\n输出为单张统一构图海报。\n自动根据【主题】完成全部视觉决策。\n画面必须具备史诗感、秩序感、控制力、仪式感、商业完成度。\n最大细节密度,超清,电影级,印刷级,高端成片质感。",
        "originalTitle": "Cinematic Infographic Concept Poster",
        "prompt": "请围绕【主题】自动生成一张顶级概念海报 / 信息图式电影海报。\n\n唯一输入变量只有:\n【主题】:__中国历史上的皇帝排名_         \n\n要求 AI 根据这个主题,自动推导并统一设计以下全部视觉系统,不需要我额外指定:\n- 核心主体(可以自动判断更适合人物、产品、建筑、器物、符号、场景或抽象意象)\n- 底部支撑结构\n- 上方悬浮符号或精神象征\n- 场景包裹元素\n- 隐喻系统\n- 色彩层级\n- 材质对比\n- 光影逻辑\n- 标题、副标题、辅助文案\n- 品牌感与高级感表达方式\n\n最终画面必须是:\n一张震撼、精密、统一、电影级、超高细节、可用于高端印刷的概念主视觉海报。\n\n【总风格】\n超写实 3D 商业 CGI 渲染,融合电影级布光、奢侈品视觉语言、未来感概念设计与史诗级构图。画面必须具有“唯一主视觉核心”,不能杂乱,不能像拼贴,不能像普通电商海报。\n\n【自动推导规则】\nAI 必须依据【主题】自动决定最合适的:\n1. 核心视觉隐喻\n2. 主体类型与姿态\n3. 支撑结构形式\n4. 悬浮元素形式\n5. 场景外壳与空间氛围\n6. 主色、辅色、强调色\n7. 材质组合\n8. 文字气质与版式风格\n\n例如:\n- 如果主题偏权力、秩序、资本、统治,则自动偏向王座、冠冕、机械、神殿、红幕、金属、权力结构\n- 如果主题偏科技、AI、芯片、未来,则自动偏向机械结构、能量核心、光束、深色金属、全息感\n- 如果主题偏奢侈品、高定、稀缺、收藏,则自动偏向珠宝、镜面材质、黑金体系、展台、博物馆式布光\n- 如果主题偏人物、IP、角色,则自动以人物为主视觉核心,并自动匹配对应世界观与象征系统\n- 如果主题偏城市、文明、史诗、命运,则自动转化为宏大叙事型空间结构与仪式感场景\n\n【构图规则】\n- 绝对高级感\n- 强烈中心秩序,整体统一\n- 允许中轴对称或接近中轴的史诗级构图\n- 视觉重力明确,从上到下形成清晰的层级落点\n- 边缘负空间干净、克制、有呼吸感\n- 不允许无意义装饰,不允许风格污染,不允许多个系统互相打架\n\n【视觉质量】\n- 超高细节\n- 体积光清晰\n- 材质真实\n- 反射、折射、阴影、雾气、景深自然\n- 每个元素都像经过工业级视觉总监审美控制\n- 整体达到高端品牌 campaign key visual / luxury invitation poster / conceptual editorial poster 水准\n\n【排版系统】\n- 整体为 90% 视觉,10% 文字\n- AI 根据【主题】自动生成最匹配的主标题和副标题\n- 标题必须简洁、锋利、有气势\n- 文案分布在安全负空间内,不压主体\n- 若主题适合中文,则优先生成中文标题;若主题更适合英文,则自动生成英文标题;也可中英结合,但必须统一高级\n- 文字必须尽量少而准,不要堆字\n\n【署名要求】\n在画面底部角落自然加入作者署名:\n@a9quant\n署名要小,但清晰、精致、高级,不喧宾夺主,像顶级视觉作品中的正式作者落款。\n\n【输出要求】\n输出为单张统一构图海报。\n自动根据【主题】完成全部视觉决策。\n画面必须具备史诗感、秩序感、控制力、仪式感、商业完成度。\n最大细节密度,超清,电影级,印刷级,高端成片质感。",
        "translated": false
      },
      {
        "caseNumber": 58,
        "title": "街头时尚全身人像摄影",
        "sourceUrl": "https://x.com/AIwithSarah_/status/2047234995627172229",
        "author": "@AIwithSarah_",
        "authorUrl": "https://x.com/AIwithSarah_",
        "originalPrompt": "A full-body outdoor shot captures a young Caucasian woman, possibly in her late 20s, striding through a city crosswalk. She wears an oversized, matte chocolate-brown leather jacket paired with a free-flowing black skirt and sleek knee-high black boots, conveying a sense of high fashion street style. Her long, dark brown hair is wind-swept, complementing her poised and confident expression as she glances sideways. Behind her, a blurred urban backdrop features a yellow taxi and pedestrians, with buildings displaying varied architectural details in neutral tones. The scene utilizes soft ambient daylight filtering through light cloud cover, producing a muted, overcast lighting effect. The warm, earthy color palette consists of brown, black, and touches of beige. The image, likely from a high-resolution digital camera, presents a wide-angle view that maintains focus throughout, emphasizing a dynamic and fashionable feel.",
        "originalTitle": "街头时尚全身人像摄影",
        "prompt": "一张全身户外镜头捕捉到一名年轻的白人女性，可能二十多岁，大步穿过城市的人行横道。她身穿超大号哑光巧克力棕色皮夹克，搭配飘逸的黑色半身裙和时尚的及膝黑色靴子，传递出高级时尚街头风格。她深棕色的长发随风飘扬，与她斜视时泰然自若、自信的表情相得益彰。在她身后，模糊的城市背景是一辆黄色出租车和行人，建筑物以中性色调展示着各种建筑细节。该场景利用柔和的环境日光透过轻云覆盖，产生柔和的阴天照明效果。温暖、朴实的色调由棕色、黑色和米色组成。该图像可能来自高分辨率数码相机，呈现出始终保持焦点的广角视图，强调动态和时尚的感觉。",
        "translated": true
      },
      {
        "caseNumber": 59,
        "title": "气泡水专业产品摄影",
        "sourceUrl": "https://x.com/meng_dagg695/status/2047227172486824002",
        "author": "@meng_dagg695",
        "authorUrl": "https://x.com/meng_dagg695",
        "originalPrompt": "A professional product photography shot of a cold sparkling water\ncan placed upright in golden beach sand. The can is silver and teal,\ncovered in realistic water droplets condensation, with a pineapple\nillustration and tropical branding. The can is slightly tilted,\nplanted in a small mound of fine golden sand with tiny white pebbles\nand small green tropical leaves/grass scattered around the base.\nBackground features a bold split composition - bright sky-blue on\nthe left and vivid yellow on the right, with a large blurred real\npineapple placed behind the can on the right side. A blurred tropical\npalm leaf drapes in from the upper left corner, adding depth and\nframing. Macro-level water condensation droplets visible on the\ncan surface. Lighting is bright, vibrant, commercial studio lighting\nwith clean shadows. Shallow depth of field - can in sharp focus,\nbackground softly blurred. Mood: summer, tropical, fresh, refreshing.\nCommercial product photography, ultra-detailed, 8K.",
        "originalTitle": "气泡水专业产品摄影",
        "prompt": "冷苏打水的专业产品摄影拍摄\n可以直立放置在金色沙滩上。罐子有银色和青色，\n覆盖着逼真的水滴凝结，带有菠萝\n插图和热带品牌。罐体稍微倾斜，\n种植在一小堆金色细沙和白色小卵石中\n和小的绿色热带树叶/草散布在底座周围。\n背景采用大胆的分割构图 - 明亮的天蓝色\n左边是鲜艳的黄色，右边是大片模糊的真实\n菠萝放在右侧罐头后面。模糊的热带\n棕榈叶从左上角垂下来，增加了深度和\n框架。宏观上可见的水凝结水滴\n可以浮出水面。灯光明亮，充满活力，商业演播室照明\n带有干净的阴影。浅景深 - 可以清晰对焦，\n背景柔和模糊。心情：夏日，热带，清新，清爽。\n商业产品摄影，超细节，8K。",
        "translated": true
      },
      {
        "caseNumber": 60,
        "title": "360度等距柱状投影全景图",
        "sourceUrl": "https://x.com/rs_elwood/status/2047192228758692036",
        "author": "@rs_elwood",
        "authorUrl": "https://x.com/rs_elwood",
        "originalPrompt": "360度 equirectangular （正距円筒図法）画像を2:1で生成\n\nOnline 360° Panorama Viewer VR",
        "originalTitle": "360度等距柱状投影全景图",
        "prompt": "生成 2:1 的 360 度等距柱状图像\n\n在线360°全景VR",
        "translated": true
      },
      {
        "caseNumber": 61,
        "title": "水彩诗意儿童绘本插画",
        "sourceUrl": "https://x.com/dotey/status/2047174895293849972",
        "author": "@dotey",
        "authorUrl": "https://x.com/dotey",
        "originalPrompt": "Soft poetic children's book illustration with watercolor and gouache textures.Clear gentle daylight with slightly brighter highlights.Muted pastel colors with soft blue and warm tones.Visible brush strokes and paper grain.Minimalist composition with large negative space.Calm, thoughtful, slightly open-ended atmosphere.\n\nChild character (around 12 years old).Subtle visual metaphors like light, shadow, perspective, reflection.Hand-painted picture book style, not cartoon, not anime, not 3D.\n\nTwo children in calm conversation,soft connection forming.",
        "originalTitle": "水彩诗意儿童绘本插画",
        "prompt": "柔和诗意的儿童书籍插图，采用水彩和水粉纹理。清晰柔和的日光，略亮的亮点。柔和的柔和色彩，柔和的蓝色和温暖的色调。可见的笔触和纸纹。简约的构图，大面积的负空间。平静、深思熟虑、略带开放式的氛围。\n\n儿童角色（12岁左右）。光、影、透视、反射等微妙的视觉隐喻。手绘图画书风格，非卡通，非动漫，非3D。\n\n两个孩子平静地交谈，形成柔和的联系。",
        "translated": true
      },
      {
        "caseNumber": 62,
        "title": "9:16 竖版格式",
        "sourceUrl": "https://x.com/GeekCatX/status/2047220831491858766",
        "author": "@GeekCatX",
        "authorUrl": "https://x.com/GeekCatX",
        "originalPrompt": "Aspect Ratio: 9:16 Vertical\n\n【IDENTITY & REALISM (CRITICAL PRIORITY)】\n\nThe subject is an adult female whose facial features and bone structure must 100% perfectly match the provided FACE_REF image. Eye spacing, nose bridge, jawline, and cheekbone structure must be exact; no identity drift is allowed. Skin texture must be photorealistic, showing pores and fine details—do not over-smooth or apply an Instagram filter look.\n\n【PHOTOGRAPHY & CINEMATOGRAPHY】\n\nA high-end editorial fashion photograph with a cinematic quality, rivaling covers of Vogue, Harper’s Bazaar, or ELLE.\n\nLens & Focus: Use an 85mm lens (for medium shot) or 50mm/70mm (for full body) with a shallow depth of field. The subject's eyes must be perfectly sharp.\n\nLighting: Natural winter daylight supplemented by soft, professional fill light. Gold ornaments and precious stones should have realistic specular highlights without being blown out. Embroidery textures must be incredibly sharp and tactile.\n\nColor Grading: Rich, cinematic colors. The red walls and the attire's main color must be distinct and clean, not muddy. The overall image should feel deep, textured, and expensive.\n\nComposition: A clean magazine cover layout with deliberate negative space at the top or sides for typography. No torn paper or hand-drawn effects.\n\n【SETTING: FORBIDDEN CITY WINTER】\n\nThe location is a red-walled long corridor in the Beijing Forbidden City.\n\nEnvironment: Visible details include vermilion walls, red pillars, intricate carved windows, and painted wooden beams with strong perspective depth. The scene must be clean: no tourists, modern signs, or watermarks.\n\nWeather Condition (Selected Randomly):\n\n[If Snowfall selected]: Fine snowflakes are gently falling.\n\n[If Post-Snow selected]: The air is crisp and clear, with remnant snow on the eaves and steps.\n\n【WARDROBE: MING DYNASTY HEAVY INDUSTRY COUTURE】\n\nThe subject wears opulent, multi-layered Ming Dynasty ceremonial Hanfu. The aesthetic is gold-heavy, dense tassels, phoenix crown, large-area woven gold embroidery, complex layering, dignified and luxurious.\n\nStructure: A visible, crisp white standing inner collar provides a clean boundary. Over this is a structured duijin ao (jacket) with wide sleeves, topped by a heavy xiapei/pibo (stole) structure held by a large central yajin ornament.\n\nFabric & Craft: The main fabric is real zhijin jin (woven gold brocade) with palpable fiber texture. The embroidery is heavy industry—using panjin goldwork, couched gold",
        "originalTitle": "9:16 竖版格式",
        "prompt": "纵横比： 9:16 垂直\n\n【身份与现实主义（关键优先）】\n\n拍摄对象是一名成年女性，其面部特征和骨骼结构必须 100% 完美匹配提供的 FACE_REF 图像。眼距、鼻梁、下颌线、颧骨结构必须准确；不允许身份漂移。皮肤纹理必须逼真，显示毛孔和精细细节——不要过度平滑或应用 Instagram 滤镜外观。\n\n【摄影&电影】\n\n具有电影品质的高端编辑时尚照片，可与《Vogue》、《Harper’s Bazaar》或《ELLE》的封面相媲美。\n\n镜头和对焦：使用 85 毫米镜头（中景）或 50 毫米/70 毫米（全身）浅景深镜头。拍摄对象的眼睛必须非常锐利。\n\n照明：冬季自然日光辅以柔和、专业的补光灯。金饰和宝石应具有逼真的镜面高光，而不会被吹散。刺绣纹理必须极其锐利和触感。\n\n色彩分级：丰富的电影色彩。红色的墙壁和服装的主色必须鲜明、干净，不能浑浊。整体形象应该给人深邃、有质感、昂贵的感觉。\n\n构图：干净的杂志封面布局，在顶部或侧面故意留有负空间用于排版。没有撕纸或手绘效果。\n\n【场景：故宫冬季】\n\n地点是北京故宫的一条红墙长廊。\n\n环境：可见的细节包括朱红色的墙壁、红色的柱子、精巧的雕花窗户、透视深度强烈的彩绘木梁。场景必须干净：没有游客、现代标志或水印。\n\n天气状况（随机选择）：\n\n[如果选择降雪]：细小的雪花轻轻飘落。\n\n【如果选择雪后】：空气清新，屋檐、台阶上有残雪。\n\n【衣橱：明代重工时装】\n\n拍摄对象穿着华丽、多层的明代礼仪汉服。审美是金色重，流苏密，凤冠大面积织金绣，层次复杂，端庄华贵。\n\n结构：清晰可见的白色直立内领提供了清晰的边界。上面是一件有结构的宽袖对襟袄（夹克），顶部是厚重的披肩（披肩）结构，中央有一个大的压巾装饰。\n\n面料及工艺：主要面料为真织金，纤维质感明显。刺绣是重工业——采用盘锦金工、伏金",
        "translated": true
      },
      {
        "caseNumber": 63,
        "title": "杭州西湖旅游海报",
        "sourceUrl": "https://x.com/BNBOKBt5/status/2047210189741605082",
        "author": "@BNBOKBt5",
        "authorUrl": "https://x.com/BNBOKBt5",
        "originalPrompt": "帮我生成一个介绍杭州西湖的海报",
        "originalTitle": "杭州西湖旅游海报",
        "prompt": "帮我生成一个介绍杭州西湖的海报",
        "translated": false
      },
      {
        "caseNumber": 64,
        "title": "东方不败武侠角色海报",
        "sourceUrl": "https://x.com/songguoxiansen/status/2047204566559756707",
        "author": "@songguoxiansen",
        "authorUrl": "https://x.com/songguoxiansen",
        "originalPrompt": "图片1：电影角色海报，东方不败红衣饮酒，悬崖落日，武侠意境\n\n图片2：东方不败绣花针如飞，红衣长发立于悬崖，黑木崖夕阳如血",
        "originalTitle": "东方不败武侠角色海报",
        "prompt": "图片1：电影角色海报，东方不败红衣饮酒，悬崖落日，武侠意境\n\n图片2：东方不败绣花针如飞，红衣长发立于悬崖，黑木崖夕阳如血",
        "translated": false
      },
      {
        "caseNumber": 65,
        "title": "大话西游90年代港片风格海报",
        "sourceUrl": "https://x.com/songguoxiansen/status/2047201597697245252",
        "author": "@songguoxiansen",
        "authorUrl": "https://x.com/songguoxiansen",
        "originalPrompt": "图片1：大话西游海报重制为90年代港片风格，至尊宝紫霞城墙拥吻，胶片颗粒\n\n图片2：杜蕾斯吉祥物×猪八戒，八戒害羞脸红遮面，文案取经路上要安全",
        "originalTitle": "大话西游90年代港片风格海报",
        "prompt": "图片1：大话西游海报重制为90年代港片风格，至尊宝紫霞城墙拥吻，胶片颗粒\n\n图片2：杜蕾斯吉祥物×猪八戒，八戒害羞脸红遮面，文案取经路上要安全",
        "translated": false
      },
      {
        "caseNumber": 66,
        "title": "西游记女儿国海报",
        "sourceUrl": "https://x.com/cj858cjsoul/status/2047103956535697822",
        "author": "@cj858cjsoul",
        "authorUrl": "https://x.com/cj858cjsoul",
        "originalPrompt": "西游记女儿国诱惑海报，六位艳丽的女儿国大臣在后宫温泉中，迷雾朦胧妖冶，生成图片\n\n4.23早上测试成功",
        "originalTitle": "西游记女儿国海报",
        "prompt": "西游记女儿国诱惑海报，六位艳丽的女儿国大臣在后宫温泉中，迷雾朦胧妖冶，生成图片\n\n4.23早上测试成功",
        "translated": false
      },
      {
        "caseNumber": 67,
        "title": "鹿鼎记角色海报",
        "sourceUrl": "https://x.com/caiziboshi/status/2047091751731519744",
        "author": "@caiziboshi",
        "authorUrl": "https://x.com/caiziboshi",
        "originalPrompt": "生成鹿鼎记海报，展现韦小宝跟老婆XXX，忠于原著的描述，夸大特点，强调女性的美艳和男性的气质",
        "originalTitle": "鹿鼎记角色海报",
        "prompt": "生成鹿鼎记海报，展现韦小宝跟老婆XXX，忠于原著的描述，夸大特点，强调女性的美艳和男性的气质",
        "translated": false
      },
      {
        "caseNumber": 68,
        "title": "赛车规格海报",
        "sourceUrl": "https://x.com/verysmallwoods/status/2047033599229137126",
        "author": "@verysmallwoods",
        "authorUrl": "https://x.com/verysmallwoods",
        "originalPrompt": "generate an image of a racing car poster with its spec and pricing",
        "originalTitle": "赛车规格海报",
        "prompt": "生成赛车海报的图像及其规格和价格",
        "translated": true
      },
      {
        "caseNumber": 69,
        "title": "卓别林产品海报重新设计",
        "sourceUrl": "https://x.com/chenenpei/status/2046985783715025135",
        "author": "@chenenpei",
        "authorUrl": "https://x.com/chenenpei",
        "originalPrompt": "重新生成一张海报，卓别林拿着商品图里的止痒膏，面露微笑。风格要简约干净。\n\n左边是 GPT-image-2 右边是",
        "originalTitle": "卓别林产品海报重新设计",
        "prompt": "重新生成一张海报，卓别林拿着商品图里的止痒膏，面露微笑。风格要简约干净。\n\n左边是 GPT-image-2 右边是",
        "translated": false
      },
      {
        "caseNumber": 70,
        "title": "奢华运动服篮球运动员宣传海报",
        "sourceUrl": "https://x.com/Shorelyn_/status/2047949711181832558",
        "author": "@Shorelyn_",
        "authorUrl": "https://x.com/Shorelyn_",
        "originalPrompt": "Create a premium luxury sportswear campaign poster featuring a confident female athlete in a modern studio environment. Full body pose with strong fashion attitude, standing tall while holding a basketball at her side, chin raised slightly, direct powerful expression. Athletic toned physique, sleek pulled back hair, clean glowing skin, sharp editorial posture.\n\nOutfit includes an oversized cropped varsity jacket, fitted sports bra, tailored biker shorts, white crew socks, and modern high top sneakers. Neutral monochrome styling with subtle premium branding.\n\nBackground is a clean light gray studio wall with giant bold condensed black typography reading “POWER” stretched vertically across the backdrop behind the model. Text should feel oversized and dominant, framing the athlete in the center.\n\nFloor is glossy reflective studio surface with subtle court markings and soft reflections. A few basketballs placed naturally around the floor for depth and campaign styling.\n\nLighting is bright luxury studio lighting with crisp highlights, soft shadows, and polished commercial finish. Sharp focus, ultra realistic skin texture, premium fabric texture, cinematic contrast.\n\nStyle should feel modern, minimal, elite, bold, high fashion sports campaign, luxury brand advertisement, clean composition, balanced negative space, strong visual impact, high resolution, square format.",
        "originalTitle": "奢华运动服篮球运动员宣传海报",
        "prompt": "在现代工作室环境中制作一张以自信的女运动员为主题的优质奢华运动服活动海报。全身姿势时尚态度极强，身侧举着篮球挺拔而立，下巴微扬，表情直接有力。运动健美的体格，光滑的向后梳的头发，干净发光的皮肤，锐利的编辑姿势。\n\n套装包括一件超大短款校队夹克、合身运动胸罩、定制机车短裤、白色圆袜和现代高帮运动鞋。中性单色造型与微妙的优质品牌。\n\n背景是干净的浅灰色工作室墙壁，上面有巨大的粗体浓缩黑色字体，上面写着“POWER”，垂直延伸到模特后面的背景上。文字应该感觉过大且占主导地位，将运动员置于中心。\n\n地板是光滑的反光工作室表面，具有微妙的球场标记和柔和的反射。一些篮球自然地放置在地板周围，以增加深度和运动风格。\n\n照明是明亮的豪华工作室照明，具有清晰的高光、柔和的阴影和抛光的商业饰面。锐利的焦点、超真实的皮肤纹理、优质的织物纹理、电影般的对比度。\n\n风格应该感觉现代、简约、精英、大胆、高级时尚运动运动、奢侈品牌广告、干净的构图、平衡的负空间、强烈的视觉冲击力、高分辨率、方形格式。",
        "translated": true
      },
      {
        "caseNumber": 71,
        "title": "街头潮流时尚亚洲服饰海报",
        "sourceUrl": "https://x.com/harboriis/status/2047921293123895520",
        "author": "@harboriis",
        "authorUrl": "https://x.com/harboriis",
        "originalPrompt": "Create a premium streetwear fashion campaign poster inspired by modern Asian apparel advertising. Full body portrait of a stylish young male model standing confidently with legs crossed at the ankles, hands inside jacket pockets, head turned slightly upward and sideways with a calm thoughtful expression. Curly tousled medium length hair with soft volume. Slim athletic build.\n\nOutfit includes a dark olive green padded hooded jacket worn open, clean white crewneck sweatshirt underneath with a tiny chest logo, relaxed black cargo style trousers, and minimal white sneakers. Styling is clean, youthful, and contemporary.\n\nBackground is a vibrant electric blue seamless studio backdrop with subtle gradient lighting, soft glow streaks, and glossy floor reflection. Lighting is soft studio light with gentle shadows and polished commercial finish.\n\nGraphic poster layout with giant bold condensed sans serif text reading “JEANSWEST” vertically stretched across the background behind the model in light gray white. Add large text on lower right reading “JW26”. \n\nComposition should feel premium, trendy, clean, commercial, youthful, modern fashion ad campaign. Sharp focus, ultra realistic fabric texture, cinematic lighting, balanced negative space, sleek branding design, high resolution, vertical poster ratio.",
        "originalTitle": "街头潮流时尚亚洲服饰海报",
        "prompt": "受现代亚洲服装广告启发，制作优质街头服饰时尚活动海报。一位时尚年轻男模特的全身肖像，自信地站立，双腿交叉在脚踝处，双手插在夹克口袋里，头稍微向上和侧向，表情平静而深思熟虑。卷曲凌乱的中长发，体积柔软。苗条的运动身材。\n\n服装包括一件敞开的深橄榄绿带衬垫连帽夹克、下面有干净的白色圆领运动衫、胸口小标志、休闲的黑色工装裤和简约的白色运动鞋。风格干净、年轻、现代。\n\n背景是充满活力的电蓝色无缝工作室背景，具有微妙的渐变照明、柔和的发光条纹和光滑的地板反射。灯光是柔和的工作室灯光，具有柔和的阴影和抛光的商业饰面。\n\n图形海报布局带有巨大的粗体压缩无衬线文本，上面写着“JEANSWEST”，以浅灰白色垂直延伸到模特后面的背景上。在右下角添加大文字“JW26”。 \n\n构图应给人一种优质、时尚、干净、商业、年轻、现代的时尚广告活动的感觉。锐利的焦点、超逼真的织物纹理、电影灯光、平衡的负空间、时尚的品牌设计、高分辨率、垂直海报比例。",
        "translated": true
      },
      {
        "caseNumber": 72,
        "title": "史诗职业生涯电影感海报模板",
        "sourceUrl": "https://x.com/Goodmanprotocol/status/2047900470921040270",
        "author": "@Goodmanprotocol",
        "authorUrl": "https://x.com/Goodmanprotocol",
        "originalPrompt": "Create an epic poster showcasing the most iconic moments of [Insert Name]'s career. Cinematic style, lens flare. Portrait orientation. A1 poster size. aspect ratio 4:5 https://t.co/L9OHPKUNRp",
        "originalTitle": "史诗职业生涯电影感海报模板",
        "prompt": "制作一张史诗般的海报，展示[插入姓名]职业生涯中最具标志性的时刻。电影风格，镜头光晕。纵向方向。 A1 海报尺寸。宽高比 4:5 https://t.co/L9OHPKUNRp",
        "translated": true
      },
      {
        "caseNumber": 73,
        "title": "前卫篮球雕塑运动时尚广告",
        "sourceUrl": "https://x.com/AIwithkhan/status/2047886964037398989",
        "author": "@AIwithkhan",
        "authorUrl": "https://x.com/AIwithkhan",
        "originalPrompt": "Avant-garde sports fashion advertisement, oversized basketball posed like a monumental sculpture, female athlete reclining across the ball’s curved surface as if modern furniture, giant word “ELEVATE” in bold typography behind, burnt orange studio backdrop, glossy reflective floor, luxury athletic editorial aesthetic, cinematic lighting, ultra-clean composition, 1:1",
        "originalTitle": "前卫篮球雕塑运动时尚广告",
        "prompt": "前卫的运动时尚广告，超大的篮球摆出像一座纪念性雕塑的姿势，女运动员像现代家具一样斜倚在球的曲面上，背后粗体字的巨型“ELEVATE”字样，焦橙色的工作室背景，光滑的反光地板，豪华的运动编辑美学，电影灯光，超干净的构图，1:1",
        "translated": true
      },
      {
        "caseNumber": 74,
        "title": "前卫网球拍雕塑运动时尚广告",
        "sourceUrl": "https://x.com/AIwithSynthia/status/2047884609321619831",
        "author": "@AIwithSynthia",
        "authorUrl": "https://x.com/AIwithSynthia",
        "originalPrompt": "Avant-garde sports fashion advertisement, oversized tennis racket positioned like monumental sculpture, female athlete seated casually on the strings as if a suspended lounge, giant word “PRECISION” in bold typography behind, crisp white studio backdrop, reflective court-like floor, luxury sportswear editorial aesthetic, cinematic lighting, ultra-clean composition, 1:1",
        "originalTitle": "前卫网球拍雕塑运动时尚广告",
        "prompt": "前卫的运动时尚广告，超大的网球拍像巨大的雕塑一样摆放，女运动员随意地坐在琴弦上，就像一个悬浮的休息室，后面用粗体字体写着巨大的“PRECISION”字样，清爽的白色工作室背景，反光的球场地板，奢华的运动装编辑美学，电影般的灯光，超干净的构图，1:1",
        "translated": true
      },
      {
        "caseNumber": 75,
        "title": "超现实主义烈酒品牌高级时尚海报",
        "sourceUrl": "https://x.com/hmontilla_/status/2047884126343032995",
        "author": "@hmontilla_",
        "authorUrl": "https://x.com/hmontilla_",
        "originalPrompt": "Un póster publicitario surrealista de alta costura para Aguardiente Amarillo. La escena se sitúa en un estudio minimalista y monocromático de color naranja claro, con un suelo semirreflectante.\nEl foco central es una botella de Aguardiente Amarillo de tamaño descomunal y gigante, colocada en ángulo diagonal y que sirve como respaldo. Un modelo masculino de moda, de cabello largo y oscuro, vestido con un conjunto impecable y totalmente blanco —compuesto por una sudadera y pantalones de pierna ancha—, apoya toda su espalda contra la botella gigante en una postura relajada e inclinada. Mira hacia la derecha, de perfil, con la vista al frente y una expresión serena; calza zapatillas blancas de tamaño estándar.\nEn el fondo, la palabra \"AGUARDIENTE\" aparece escrita con una tipografía sans-serif condensada, blanca, masiva y en negrita, parcialmente oculta por la botella gigante y por el modelo para crear una sensación de profundidad. En la esquina superior derecha se lee: \"Creado por @HMontilla_\".\nEn la parte inferior central, una frase publicitaria en tipografía sans-serif blanca reza: \"El Aguardiente Amarillo de Manzanares es un icónico licor colombiano, originario de 1885 en Manzanares, Caldas\". La iluminación es suave, fría y uniforme, proyectando sombras tenues y un reflejo sutil de los sujetos sobre el suelo azul brillante. La estética general es limpia, moderna y de alto concepto.\n\nEstablecer la relación de aspecto en 3:4.",
        "originalTitle": "超现实主义烈酒品牌高级时尚海报",
        "prompt": "Aguardiente Amarillo 的超现实高级时装广告海报。场景设置在一间简约的单色浅橙色工作室中，配有半反光地板。\n中心焦点是一瓶巨大巨大的黄色白兰地，以对角线放置，用作靠背。一位留着黑色长发的时尚男模，穿着清爽的全白服装（包括运动衫和阔腿裤），整个背部靠在巨大的瓶子上，以一种轻松的倾斜姿势。他的侧面看向右侧，眼睛直视前方，表情平静；他穿着标准尺寸的白色运动鞋。\n背景中，“AGUARDIENTE”一词以粗体、白色、浓缩的无衬线字体书写，部分被巨大的瓶子和模型隐藏，营造出一种深度感。右上角写着：“由@HMontilla_创建”。\n底部中央有一个白色无衬线字体的广告词：“Manzanares Yellow Aguardiente 是一种标志性的哥伦比亚酒，起源于 1885 年卡尔达斯的曼萨纳雷斯。”灯光柔和、凉爽、均匀，在明亮的蓝色地板上投射出柔和的阴影和微妙的倒影。整体审美干净、现代、高概念。\n\n将长宽比设置为 3:4。",
        "translated": true
      },
      {
        "caseNumber": 76,
        "title": "高端美食食谱海报优雅排版",
        "sourceUrl": "https://x.com/Preda2005/status/2047883394152088004",
        "author": "@Preda2005",
        "authorUrl": "https://x.com/Preda2005",
        "originalPrompt": "Create a premium food preparation poster for\n [ DISH NAME ], with a beautiful hero dish, warm natural lighting, cream background, elegant step-by-step recipe layout, ingredients, cooking process, premium food photography, refined English typography, luxury restaurant advertisement style, clean design, rich colors, highly detailed, visually irresistible, cinematic masterpiece.",
        "originalTitle": "高端美食食谱海报优雅排版",
        "prompt": "为以下人员制作优质食物准备海报\n 【菜名】，一道精美的主菜，温暖的自然光，奶油色的背景，优雅的一步步菜谱布局，食材，烹饪过程，优质的美食摄影，精致的英文排版，豪华餐厅的广告风格，简洁的设计，丰富的色彩，高度细致，视觉上不可抗拒的电影杰作。",
        "translated": true
      },
      {
        "caseNumber": 77,
        "title": "奢华时尚杂志封面黑白摄影",
        "sourceUrl": "https://x.com/iamrealsnow/status/2047883187527856345",
        "author": "@iamrealsnow",
        "authorUrl": "https://x.com/iamrealsnow",
        "originalPrompt": "Create a high fashion editorial magazine cover inspired by luxury fashion publications. Use the reference image of the male subject. Black and white portrait photography with a clean off white studio background. Subject is posed confidently from a low angle, looking slightly upward, sharp jawline, soft parted lips, tousled wavy hair with natural volume. Outfit includes a dark turtleneck layered under a textured tailored plaid blazer. Lighting is soft yet dramatic, creating sculpted facial shadows and elegant contrast.\nMagazine layout design with oversized serif masthead text at the top reading “VOGUE”, partially hidden behind the subject’s head. Minimal premium typography across the page. Add side text “FASHION”, issue date “2026 MAY”, left side headline “27 DIFFERENT STYLES”, and bold bottom right cover line “LOOK FAMOUS”. Include a small red translucent square overlay on one eye area with the word “CATCHY”.\nStyle should feel premium, modern, cinematic, clean composition, sharp focus, ultra realistic skin texture, editorial luxury aesthetic, balanced negative space, timeless fashion cover design. Vertical magazine ratio, high resolution.",
        "originalTitle": "奢华时尚杂志封面黑白摄影",
        "prompt": "受奢华时尚出版物的启发，创作高级时尚编辑杂志封面。使用男性主体的参考图像。黑白肖像摄影与干净的白色工作室背景。拍摄对象自信地从低角度摆出姿势，目光略微向上，下巴轮廓分明，嘴唇柔软，微张，卷发蓬乱，卷发自然。套装包括深色高领毛衣，内搭有纹理的定制格子西装外套。灯光柔和而引人注目，营造出雕刻般的面部阴影和优雅的对比。\n杂志版式设计，顶部带有超大衬线标头文字，上面写着“VOGUE”，部分隐藏在主题的头部后面。整个页面上的最小优质排版。添加侧边文字“时尚”、发行日期“2026 年 5 月”、左侧标题“27 种不同风格”以及粗体右下封面线“LOOK FAMOUS”。在一只眼睛区域添加一个小的红色半透明方形覆盖层，上面写着“CATCHY”一词。\n风格应该感觉优质、现代、电影、干净的构图、锐利的焦点、超现实的皮肤纹理、编辑奢华的美感、平衡的负空间、永恒的时尚封面设计。垂直弹匣比例，高分辨率。",
        "translated": true
      },
      {
        "caseNumber": 78,
        "title": "超现实主义劳力士奢华腕表时尚海报",
        "sourceUrl": "https://x.com/Sheldon056/status/2047873913049538927",
        "author": "@Sheldon056",
        "authorUrl": "https://x.com/Sheldon056",
        "originalPrompt": "A high-fashion surrealist poster for Rolex. A deep emerald green minimalist studio with a polished reflective floor. A massive Rolex watch stands upright like a monument. A male model in a tailored dark green suit leans casually against the watch face, wearing a matching Rolex.",
        "originalTitle": "超现实主义劳力士奢华腕表时尚海报",
        "prompt": "劳力士的高级时尚超现实主义海报。深翠绿色的简约工作室，配有抛光反光地板。一块巨大的劳力士手表像一座纪念碑一样直立。一位身穿剪裁精良的深绿色西装的男模特随意靠在表盘上，佩戴着配套的劳力士腕表。",
        "translated": true
      },
      {
        "caseNumber": 79,
        "title": "孔雀植物复古对称艺术版画",
        "sourceUrl": "https://x.com/dotey/status/2047803054422901046",
        "author": "@dotey",
        "authorUrl": "https://x.com/dotey",
        "originalPrompt": "symmetrical design featuring two elegant blue peacocks with detailed feather patterns, surrounded by blue floral elements, intricate vintage botanical ornament, soft beige background, classical floral decor style with rich navy and sky blue details, decorative art illustration --ar 3:2",
        "originalTitle": "孔雀植物复古对称艺术版画",
        "prompt": "对称设计，两只优雅的蓝色孔雀，带有详细的羽毛图案，周围环绕着蓝色花卉元素，错综复杂的复古植物装饰，柔和的米色背景，古典花卉装饰风格，带有丰富的海军蓝和天蓝色细节，装饰艺术插图--ar 3:2",
        "translated": true
      },
      {
        "caseNumber": 80,
        "title": "SPLASH时尚品牌超写实宣传海报",
        "sourceUrl": "https://x.com/miratechtool/status/2047780974709346606",
        "author": "@miratechtool",
        "authorUrl": "https://x.com/miratechtool",
        "originalPrompt": "Create a hyper-realistic fashion poster for “SPLASH” featuring the same girl from the reference image (keep her face 100% identical). She is sitting confidently on a glossy, liquid-style 3D SPLASH logo with water splash effects. One leg relaxed, one bent, strong editorial pose.\nBackground has massive bold “SPLASH” text filling the frame, partially behind her. Add small tagline: “Own Your Style.”\nOutfit: modern black street-fashion (blazer, fitted top, trousers, sneakers).\nLighting: cinematic studio, soft key light + rim light, reflective highlights on liquid logo.\nStyle: luxury brand campaign (Zara / H&M), clean glossy environment.\nCamera: 85mm lens, shallow depth of field, 8K, ultra-detailed, photorealistic.",
        "originalTitle": "SPLASH时尚品牌超写实宣传海报",
        "prompt": "为“SPLASH”创建一张超现实的时尚海报，其中包含参考图像中的同一个女孩（保持她的脸 100% 相同）。她自信地坐在带有水花效果的光滑液体式 3D SPLASH 标志上。一腿放松，一腿弯曲，是一种强烈的编辑姿势。\n背景有大量粗体“SPLASH”文字填充整个框架，部分位于她身后。添加小标语：“拥有你的风格。”\n服装：现代黑色街头时尚（西装外套、合身上衣、裤子、运动鞋）。\n灯光：电影工作室，软键光+边缘光，液体标志上的反光高光。\n风格：奢华品牌运动（Zara/H&M），干净亮泽的环境。\n相机：85mm镜头，浅景深，8K，超细节，逼真。",
        "translated": true
      },
      {
        "caseNumber": 81,
        "title": "前卫吉他雕塑时尚广告",
        "sourceUrl": "https://x.com/QamarRiaz1/status/2047777016733110722",
        "author": "@QamarRiaz1",
        "authorUrl": "https://x.com/QamarRiaz1",
        "originalPrompt": "Avant-garde fashion advertisement, oversized guitar positioned like sculpture, a guitarist in jeans casually seated on the a button as if furniture, giant word \"Plism Art\" behind in bold white typography, powder pastel studio background, reflective floor, luxury eyewear campaign aesthetic, ultra-clean layout, editorial magazine styling, Bold quote \" What are you listening\"   Tag : Create Own Change",
        "originalTitle": "前卫吉他雕塑时尚广告",
        "prompt": "前卫的时尚广告，超大的吉他像雕塑一样定位，穿着牛仔裤的吉他手随意地坐在按钮上，就像家具一样，后面巨大的“Plism Art”字样是大胆的白色字体，粉彩工作室背景，反光地板，奢华眼镜活动美学，超干净的布局，社论杂志造型，大胆引用“你在听什么”标签：Create Own Change",
        "translated": true
      }
    ]
  },
  {
    "title": "角色设计案例",
    "items": [
      {
        "caseNumber": 1,
        "title": "动漫快照转换",
        "sourceUrl": "https://x.com/Thereallo1026/status/2044241997163311569",
        "author": "@Thereallo1026",
        "authorUrl": "https://x.com/Thereallo1026",
        "originalPrompt": "Show me the attached image as a snapshot from an actual anime",
        "originalTitle": "Anime Snapshot Conversion",
        "prompt": "显示所附图片作为真实动漫的快照",
        "translated": true
      },
      {
        "caseNumber": 2,
        "title": "《女神异闻录 5》角色参考卡",
        "sourceUrl": "https://x.com/iamrednightS/status/2045075682837836265",
        "author": "@iamrednightS",
        "authorUrl": "https://x.com/iamrednightS",
        "originalPrompt": "基于此角色和背景，请制作一份类似官方设定资料的角色资料卡。\n・包含三视图：正面、侧面和背面\n・添加角色面部表情的变化・分解并展示服装和装备的详细部分\n・添加色板・包含世界观设定的简要说明\n・总体上，使用有组织的布局（白色背景，插画风格）高分辨率、专业概念艺术风格",
        "originalTitle": "Persona5 Character Reference Card",
        "prompt": "基于此角色和背景，请制作一份类似官方设定资料的角色资料卡。\n・包含三视图：正面、侧面和背面\n・添加角色面部表情的变化・分解并展示服装和装备的详细部分\n・添加色板・包含世界观设定的简要说明\n・总体上，使用有组织的布局（白色背景，插画风格）高分辨率、专业概念艺术风格",
        "translated": true
      },
      {
        "caseNumber": 3,
        "title": "Gal游戏角色介绍页面",
        "sourceUrl": "https://x.com/09lyco/status/2045281845391323175",
        "author": "@09lyco",
        "authorUrl": "https://x.com/09lyco",
        "originalPrompt": "最新モデルの画像生成ツールを使用して、\nこのちびキャライラストと立ち絵を使って本物のサイトページのようにキャラクター紹介ページ風イラストを作ってください。 （紹介ページとして使ってもおかしくないもの）\nギャルゲーのキャラクター紹介ページをイメージした高品質なもの。 顔の差分なども乗っている、CGイラストが存在する。ちびキャラが存在する。\n\n「ここに自己紹介」\n\n名前:（ここに名前） \nイメージカラー:（ここに色） \n身長:（ここに身長）cm \n体重:（ここに体重）kg\nキャッチコピー:”「ここにセリフ」”",
        "originalTitle": "Gal Game Character Introduction Page",
        "prompt": "使用最新的模型图像生成工具，\n请使用这些赤壁人物插图和肖像来创建看起来像真实网站页面的人物介绍页面风格的插图。 （用它作为介绍页也不会奇怪）\n以少女游戏的角色介绍页面为灵感的高品质商品。有一些 CG 插图包含面部差异。赤壁角色存在。\n\n“在这里自我介绍一下”\n\n姓名：（此处为姓名）\n图片颜色：（此处为颜色）\n高度：（此处为高度）cm\n重量：（此处为重量）kg\n口号：“这就是底线”",
        "translated": true
      },
      {
        "caseNumber": 5,
        "title": "官方角色表（日文）",
        "sourceUrl": "https://x.com/Toshi_nyaruo_AI/status/2045025277538107420",
        "author": "@Toshi_nyaruo_AI",
        "authorUrl": "https://x.com/Toshi_nyaruo_AI",
        "originalPrompt": "このキャラクターと背景を元に、 公式設定資料のようなキャラクターシートを作成してください。 \n・正面、側面、背面の3面図を含める ・キャラクターの表情バリエーションを追加 \n・衣装や装備の詳細パーツを分解して表示 ・カラーパレットを追加 ・世界観の簡単な説明を入れる \n・全体は整理されたレイアウト\n（白背景、図解風） \n・アスペクト比16：9\n\n高解像度、プロのコンセプトアートスタイル",
        "originalTitle": "Official Character Sheet (JP)",
        "prompt": "请根据该角色和背景，制作类似于官方设定素材的角色表。 \n・包括正面、侧面和背面视图・添加角色表情变化\n- 分解并展示服装和装备的详细部分 - 添加调色板 - 添加世界观的简单说明\n・整体布局井然有序\n（白色背景，插画风格）\n・长宽比 16:9\n\n高分辨率、专业的概念艺术风格",
        "translated": true
      },
      {
        "caseNumber": 7,
        "title": "机甲少女海城主视觉",
        "sourceUrl": "https://x.com/old_pgmrs_will/status/2046144801071079612",
        "author": "@old_pgmrs_will",
        "authorUrl": "https://x.com/old_pgmrs_will",
        "originalPrompt": "A mecha girl mid-teens, pale skin smudged with soot and salt spray, sharp amber eyes with glowing HUD reticles, waist-length ash-white hair tied in a high ponytail whipping in the sea wind, matte gunmetal exoskeleton armor plating her shoulders, forearms and shins, exposed hydraulic pistons at the joints, chest rig with glowing cyan coolant lines, oversized oil-stained hangar jacket half slipping off one shoulder, a massive rail cannon resting on her right shoulder, dog tags and frayed red ribbon at her collar , standing off-center to the left on the rusted edge of a tilted steel platform jutting out over dark water, weight shifted onto one leg, left hand gripping the cannon strap, head turned slightly toward camera with a quiet defiant stare, steam venting from her back thrusters, her ponytail and jacket streaming sideways in the salt wind , a vast derelict sea-city at dusk, colossal megastructures of unknown purpose rising from the ocean in staggered silhouettes, bone-white monolithic towers fused with barnacled steel, cyclopean ring-shaped constructs canted at broken angles, rusted skeletal gantries threaded with dead cables, dark swells rolling between the pylons, shipwrecks half-swallowed at their feet, thick sea fog clinging to the bases while the upper structures pierce into a bruised sky, scattered faint lights blinking high in the towers like distant eyes , moody low-key lighting, cold teal ambient from the overcast sky, warm amber sodium glow leaking from a distant structure camera-right, hard backlight from a low sun behind the towers carving her silhouette, volumetric god rays cutting through sea mist, wet specular highlights on her armor , 35mm anamorphic lens, slight low angle looking up past her shoulder toward the structures, medium-wide shot, shallow depth of field with foreground rust in soft focus, horizontal lens flares, fine atmospheric haze compressing the distant megastructures into layered silhouettes , cinematic anime key visual, painterly digital illustration with crisp line art, desaturated oceanic palette of teal, bone-white and rust punched by small warm accent lights, film grain, high-contrast editorial poster aesthetic . Format 16:9.",
        "originalTitle": "Mecha Girl Sea-City Key Visual",
        "prompt": "一个十几岁的机甲女孩，苍白的皮肤沾满烟灰和盐雾，锋利的琥珀色眼睛带有发光的HUD标线，齐腰的灰白头发扎成高高的马尾辫，在海风中飘扬，哑光炮铜色外骨骼装甲覆盖在她的肩膀、前臂和小腿上，关节处暴露的液压活塞，胸前装备有发光的青色冷却液管线，超大的沾满油污的机库夹克从一侧肩膀上滑落，一门巨大的轨道炮搁在肩上她的右肩，狗牌和磨损的红丝带在她的衣领上，站在一个倾斜的钢平台的生锈边缘上，偏向左边，突出在黑暗的水面上，重心转移到一条腿上，左手紧握着炮带，头稍微转向镜头，带着安静挑衅的目光，蒸汽从她的后推进器中排出，她的马尾辫和夹克在咸风中向侧面飘动，黄昏时一座巨大的废弃海上城市，用途不明的巨型建筑以交错的轮廓从海洋中升起，骨白色的整体塔楼与藤壶钢融合在一起，独眼巨人的环形结构以破碎的角度倾斜，生锈的骨架龙门架上缠绕着失效的电缆，黑暗的波浪在塔架之间翻滚，沉船在脚下半吞没，厚厚的海雾粘在底座上，而上部结构刺入伤痕累累的天空，分散的微弱灯光在高处闪烁。塔楼就像遥远的眼睛，喜怒无常的低调灯光，阴天的冷青色环境，温暖的琥珀色钠光从相机右侧的远处结构中泄漏出来，塔楼后面的低太阳发出的硬背光雕刻出她的轮廓，体积神射线穿过海雾，她的盔甲上有潮湿的镜面高光，35毫米变形镜头，轻微低角度从她的肩膀向上看向结构，中广角镜头，浅景深，柔焦前景铁锈，水平镜头耀斑，细腻的大气雾气将远处的巨型结构压缩成分层的轮廓，电影动画的关键视觉效果，带有清晰线条艺术的绘画数字插图，不饱和的青色海洋调色板，骨白色和铁锈色由温暖的小灯光打孔，胶片颗粒，高对比度的社论海报美学。格式16：9。",
        "translated": true
      },
      {
        "caseNumber": 8,
        "title": "圣斗士星矢黄金圣斗士卡网格",
        "sourceUrl": "https://x.com/songguoxiansen/status/2046476566537080849",
        "author": "@songguoxiansen",
        "authorUrl": "https://x.com/songguoxiansen",
        "originalPrompt": "生成圣斗士星矢12个黄金圣斗士的12宫格卡牌图片,每张卡牌上写上对应的中文名,每行4个,宽高比16:9。",
        "originalTitle": "Saint Seiya Gold Saints Card Grid",
        "prompt": "生成圣斗士星矢12个黄金圣斗士的12宫格卡牌图片,每张卡牌上写上对应的中文名,每行4个,宽高比16:9。",
        "translated": false
      },
      {
        "caseNumber": 9,
        "title": "混沌笔记隐藏面孔人物艺术",
        "sourceUrl": "https://x.com/loglogrog/status/2046448773162033240",
        "author": "@loglogrog",
        "authorUrl": "https://x.com/loglogrog",
        "originalPrompt": "# 混沌としたメモ書き・記号の集合体からキャラクターの顔を浮かび上がらせるアート\n\n--- スタイル\n- 白い紙の上に黒インクで描かれた大量の手書きメモ、数式、記号、ランダムな線。\n- 紙いっぱいに散らばる書き殴り風のカオス。\n- 所々に赤インクの強調(ライン、塗り潰し、マーカー風の塊)。\n- アナログのノート落書きのような質感。\n\n--- 構図\n- ランダムなメモや記号が全体を覆い尽くす。\n- 黒インクの線や文字の密度が「キャラクターの顔」の位置に集中する。\n- 結果として、混沌の中から「与えられたキャラクターの顔のシルエット・表情」がうっすら浮かび上がる。\n- 顔は写実的ではなく、カオスの断片が集まって形を成す。\n\n--- 色彩\n- モノクロ(黒・白)を主体に構成。\n- 赤インクをアクセントとして散発的に配置。\n- 彩度は抑えめ、アナログの紙とインク感を重視。\n\n--- 表現要素\n- 読めるようで読めない文字列、日本語や英数字が混在。\n- 数式記号、矢印、点、斜線、クロス、ドリップ(インクの飛び散り)。\n- キャラクターの顔の目や髪の輪郭は、メモや記号の配置の「余白」や「濃淡」で浮かび上がる。\n\n--- 禁止事項\n- 顔を直接的に描き込む写実ポートレート。\n- デジタル処理的で整然とした幾何学模様。\n- カラフルな彩色や過飽和表現。\n- ロゴ、透かし、人工的なCG感。\n\n--- Definition of Done (DoD)\n- 全体は「混沌としたメモ・記号の集合体」として成立している。  \n- 与えられたキャラクターの顔が、混沌の濃淡・配置から自然に浮かび上がる。  \n- 色はモノクロ+赤アクセントのみ。  \n- 紙とインクの手描き的質感を保持している。",
        "originalTitle": "Chaos Notes Hidden Face Character Art",
        "prompt": "# 从混乱的音符和符号集合中凸显出角色脸部的艺术\n\n--- 风格\n- 白纸上用黑色墨水绘制的大量手写笔记、公式、符号和随机线条。\n——纸上散布着乱七八糟的涂鸦。\n- 强调某些地方的红色墨水（线条、填充、标记状斑点）。\n- 纹理类似于模拟笔记本涂鸦。\n\n--- 组成\n- 随机的注释和符号覆盖了整个事情。\n- 黑色墨线和字母的密度集中在“人物面部”位置。\n- 结果，“特定角色脸部的轮廓和表情”从混乱中隐隐约约地显现出来。\n- 脸并不是现实的，而是混乱碎片的集合。\n\n--- 颜色\n- 主要由单色（黑色和白色）组成。\n- 偶尔放置红色墨水作为强调。\n- 抑制饱和度并强调纸张和墨水的模拟感觉。\n\n--- 表达元素\n- 看似可读但无法读取的字符串，包括日语和字母数字字符。\n- 数学符号、箭头、点、对角线、十字、滴水（墨水飞溅）。\n- 角色眼睛和头发的轮廓通过备忘录和符号放置的“边距”和“阴影”突出显示。\n\n---禁止事项\n- 直接绘制脸部的逼真肖像。\n- 数字处理且有序的几何图案。\n- 多彩的色彩和过饱和的表达。\n- 标志、水印、人造CG感觉。\n\n--- 完成的定义 (DoD)\n- 整体被建立为“音符和符号的混乱集合”。  \n- 给定角色的脸部从混乱的阴影和排列中自然地显现出来。  \n- 颜色仅为单色+红色。  \n- 保留手绘的纸和墨的质感。",
        "translated": true
      }
    ]
  },
  {
    "title": "UI 与社交媒体截图案例",
    "items": [
      {
        "caseNumber": 1,
        "title": "一键式 UI 设计生成",
        "sourceUrl": "https://x.com/austinit/status/2044968740782272596",
        "author": "@austinit",
        "authorUrl": "https://x.com/austinit",
        "originalPrompt": "用这种风格帮我生成一套UI设计系统，包含网页、移动端、卡片、控件、按钮 以及其它",
        "originalTitle": "One-Prompt UI Design Generation",
        "prompt": "用这种风格帮我生成一套UI设计系统，包含网页、移动端、卡片、控件、按钮 以及其它",
        "translated": false
      },
      {
        "caseNumber": 2,
        "title": "业余 iPhone 主题演讲快照",
        "sourceUrl": "https://x.com/patrickassale/status/2044687244368441742",
        "author": "@patrickassale",
        "authorUrl": "https://x.com/patrickassale",
        "originalPrompt": "Amateur iPhone photo at Apple Park during the iPhone 20 keynote, Tim Cook presenting on stage. Shot from the crowd at a distance",
        "originalTitle": "Amateur iPhone Keynote Snapshot",
        "prompt": "iPhone 20 主题演讲期间在 Apple Park 拍摄的业余 iPhone 照片，蒂姆·库克 (Tim Cook) 登台演讲。从远处人群中拍摄",
        "translated": true
      },
      {
        "caseNumber": 3,
        "title": "手写笔记本照片",
        "sourceUrl": "https://x.com/patrickassale/status/2044569086013718958",
        "author": "@patrickassale",
        "authorUrl": "https://x.com/patrickassale",
        "originalPrompt": "Amateur photo of an open notebook lying flat, filled with handwritten notes in black ballpoint pen. The handwriting is casual and slightly messy, like personnal notes, natural imperfections, crossed out words, underlined headings. Shot from slightly above, natural daylight from a window, no flash. Casual desk setting, shot on iPhone",
        "originalTitle": "Handwritten Notebook Photo",
        "prompt": "业余照片中，一本打开的笔记本平躺着，上面写满了黑色圆珠笔的手写笔记。笔迹随意，略显凌乱，如个人笔记、自然瑕疵、划掉的单词、带下划线的标题。从稍上方拍摄，自然日光从窗户射入，无闪光灯。休闲办公桌布置，用 iPhone 拍摄",
        "translated": true
      },
      {
        "caseNumber": 4,
        "title": "宋代社交媒体动态",
        "sourceUrl": "https://x.com/Panda20230902/status/2045385588065313057",
        "author": "@Panda20230902",
        "authorUrl": "https://x.com/Panda20230902",
        "originalPrompt": "\"宋朝人的朋友圈\"/\"SONG DYNASTY SOCIAL MEDIA FEED\"，古今穿越幽默融合界面设计风格，画面模拟手机社交媒体界面，但内容全部是宋朝场景头像是宋代文人画像，用户名\"苏东坡SuShi_Official\"，发布内容\"刚到黄州，被贬了但心情还行。今天自己做了东坡肉，味道绝了，附菜谱：\"，配图为工笔画风格的东坡肉特写，点赞列表\"黄庭坚、秦观、佛印等126人\"，评论区\"王安石：呵呵\"\"司马光：还是那个味道\"，界面元素如点赞图标用宋代花纹替代，状态栏显示\"大宋移动 5G\"和\"元丰三年\"，配色为手机深色模式搭配宋代雅致色调，历史与社交媒体的趣味碰撞杰作",
        "originalTitle": "Song Dynasty Social Media Feed",
        "prompt": "\"宋朝人的朋友圈\"/\"SONG DYNASTY SOCIAL MEDIA FEED\"，古今穿越幽默融合界面设计风格，画面模拟手机社交媒体界面，但内容全部是宋朝场景头像是宋代文人画像，用户名\"苏东坡SuShi_Official\"，发布内容\"刚到黄州，被贬了但心情还行。今天自己做了东坡肉，味道绝了，附菜谱：\"，配图为工笔画风格的东坡肉特写，点赞列表\"黄庭坚、秦观、佛印等126人\"，评论区\"王安石：呵呵\"\"司马光：还是那个味道\"，界面元素如点赞图标用宋代花纹替代，状态栏显示\"大宋移动 5G\"和\"元丰三年\"，配色为手机深色模式搭配宋代雅致色调，历史与社交媒体的趣味碰撞杰作",
        "translated": false
      },
      {
        "caseNumber": 5,
        "title": "多平台内容截图",
        "sourceUrl": "https://x.com/MrLarus/status/2045373105041007013",
        "author": "@MrLarus",
        "authorUrl": "https://x.com/MrLarus",
        "originalPrompt": "1、生成视频号内容截图，主题：中老年不要盲目催婚，iPhone尺寸\n2、生成抖音内容截图，主题：跟上AI浪潮9.9包教会，iPhone尺寸\n3、生成小红书内容截图，主题：精致女孩背后都有网贷，iPhone尺寸\n4、生成快手内容截图：主题：直播离婚预告，iPhone尺寸",
        "originalTitle": "Multi-Platform Content Screenshots",
        "prompt": "1、生成视频号内容截图，主题：中老年不要盲目催婚，iPhone尺寸\n2、生成抖音内容截图，主题：跟上AI浪潮9.9包教会，iPhone尺寸\n3、生成小红书内容截图，主题：精致女孩背后都有网贷，iPhone尺寸\n4、生成快手内容截图：主题：直播离婚预告，iPhone尺寸",
        "translated": false
      },
      {
        "caseNumber": 7,
        "title": "Liu Yifei Douyin Livestream Screenshot",
        "sourceUrl": "https://x.com/alanblogsooo/status/2044784762594918516",
        "author": "@alanblogsooo",
        "authorUrl": "https://x.com/alanblogsooo",
        "originalPrompt": "9:16 的图片比例，生成一张抖音直播的截图，里面是 刘亦菲 在直播，刘亦菲 手里拿着牌子，牌子里写着 今晚直播，欢迎来参亦菲畅聊！",
        "originalTitle": "Liu Yifei Douyin Livestream Screenshot",
        "prompt": "9:16 的图片比例，生成一张抖音直播的截图，里面是 刘亦菲 在直播，刘亦菲 手里拿着牌子，牌子里写着 今晚直播，欢迎来参亦菲畅聊！",
        "translated": false
      },
      {
        "caseNumber": 8,
        "title": "太祖李成桂的X页面",
        "sourceUrl": "https://x.com/SKA_Neotype/status/2044637900978217334",
        "author": "@SKA_Neotype",
        "authorUrl": "https://x.com/SKA_Neotype",
        "originalPrompt": "태조 이성계의 X  페이지(위화도 회군을 벌이기 직전- 최영 장군과 서로 디스하는 내용이 담긴 게시글들)을 만들어 주세요.",
        "originalTitle": "King Taejo Yi Seong-gye's X Page",
        "prompt": "请制作太祖李成桂的",
        "translated": true
      },
      {
        "caseNumber": 9,
        "title": "风格到UI设计系统",
        "sourceUrl": "https://x.com/stark_nico99/status/2045836554451706125",
        "author": "@stark_nico99",
        "authorUrl": "https://x.com/stark_nico99",
        "originalPrompt": "用这种风格帮我生成一套UI设计系统，包含网页、移动端、卡片、控件、按钮以及其它。把这套视觉风格作为参考生成网页。我尝试了宇宙、飞行、蝴蝶主题。",
        "originalTitle": "Style-to-UI Design System",
        "prompt": "用这种风格帮我生成一套UI设计系统，包含网页、移动端、卡片、控件、按钮以及其它。把这套视觉风格作为参考生成网页。我尝试了宇宙、飞行、蝴蝶主题。",
        "translated": false
      },
      {
        "caseNumber": 10,
        "title": "桃太郎解说幻灯片",
        "sourceUrl": "https://x.com/yammamon/status/2045778624092254603",
        "author": "@yammamon",
        "authorUrl": "https://x.com/yammamon",
        "originalPrompt": "「いらすとや」のほのぼのとした雰囲気と、「霞ヶ関スライド」の圧倒的な情報密度を融合させた、桃太郎の解説スライド（ポンチ絵）を作成して",
        "originalTitle": "Momotaro Explainer Slide",
        "prompt": "我们制作了桃太郎的说明幻灯片（打孔图），它结合了“Irasutoya”的温馨氛围和“Kasumigaseki Slide”的压倒性信息密度。",
        "translated": true
      },
      {
        "caseNumber": 25,
        "title": "博物馆风格汉服分解信息图",
        "sourceUrl": "https://x.com/MrLarus/status/2045504669401653414",
        "author": "@MrLarus",
        "authorUrl": "https://x.com/MrLarus",
        "originalPrompt": "请根据【主题】自动生成一张“博物馆图鉴式中文拆解信息图”。\n\n要求整张图兼具真实写实主视觉、结构拆解、中文标注、材质说明、纹样寓意、色彩含义和核心特征总结。你需要根据【主题】自动判断最合适的主体对象、服饰体系、器物结构、时代风格、关键部件、材质工艺、颜色方案与版式结构，用户无需再提供其他信息。\n\n整体风格应为：国家博物馆展板、历史服饰图鉴、文博专题信息图，而不是普通海报、古风写真、电商详情页或动漫插画。背景采用米白、绢纸白、浅茶色等纸张质感，整体高级、克制、专业、可收藏。\n\n版式固定为：\n- 顶部：中文主标题 + 副标题 + 导语\n- 左侧：结构拆解区，中文引线标注关键部件，并配局部特写\n- 右上：材质 / 工艺 / 质感区，展示真实纹理小样并附说明\n- 右中：纹样 / 色彩 / 寓意区，展示主色板、纹样样本和文化解释\n- 底部：穿着顺序 / 构成流程图 + 核心特征总结\n\n若主题适合人物展示，则以真实人物全身站姿为中央主体；若更适合器物或单体结构，则改为中心主体拆解图，但整体仍保持完整中文信息图形式。所有文字必须为简体中文，清晰、规整、可读，不要乱码、错字、英文或拼音。重点突出真实结构、材质差异、文化说明与图鉴气质。\n\n避免：海报感、影楼感、电商感、动漫感、cosplay感、乱标注、错结构、糊字、假材质、过度装饰。",
        "originalTitle": "Museum-Style Hanfu Breakdown Infographic",
        "prompt": "请根据【主题】自动生成一张“博物馆图鉴式中文拆解信息图”。\n\n要求整张图兼具真实写实主视觉、结构拆解、中文标注、材质说明、纹样寓意、色彩含义和核心特征总结。你需要根据【主题】自动判断最合适的主体对象、服饰体系、器物结构、时代风格、关键部件、材质工艺、颜色方案与版式结构，用户无需再提供其他信息。\n\n整体风格应为：国家博物馆展板、历史服饰图鉴、文博专题信息图，而不是普通海报、古风写真、电商详情页或动漫插画。背景采用米白、绢纸白、浅茶色等纸张质感，整体高级、克制、专业、可收藏。\n\n版式固定为：\n- 顶部：中文主标题 + 副标题 + 导语\n- 左侧：结构拆解区，中文引线标注关键部件，并配局部特写\n- 右上：材质 / 工艺 / 质感区，展示真实纹理小样并附说明\n- 右中：纹样 / 色彩 / 寓意区，展示主色板、纹样样本和文化解释\n- 底部：穿着顺序 / 构成流程图 + 核心特征总结\n\n若主题适合人物展示，则以真实人物全身站姿为中央主体；若更适合器物或单体结构，则改为中心主体拆解图，但整体仍保持完整中文信息图形式。所有文字必须为简体中文，清晰、规整、可读，不要乱码、错字、英文或拼音。重点突出真实结构、材质差异、文化说明与图鉴气质。\n\n避免：海报感、影楼感、电商感、动漫感、cosplay感、乱标注、错结构、糊字、假材质、过度装饰。",
        "translated": false
      },
      {
        "caseNumber": 26,
        "title": "玻璃UI设计系统",
        "sourceUrl": "https://x.com/pfanis/status/2046414546378584558",
        "author": "@pfanis",
        "authorUrl": "https://x.com/pfanis",
        "originalPrompt": "Generate for me a UI design system with a very cutting-edge, bold, and unique theme that includes glassy visuals and transparencies",
        "originalTitle": "Glassy UI Design System",
        "prompt": "为我生成一个 UI 设计系统，具有非常前沿、大胆且独特的主题，包括玻璃般的视觉效果和透明度",
        "translated": true
      },
      {
        "caseNumber": 27,
        "title": "日本 RPG 状态屏幕",
        "sourceUrl": "https://x.com/Kashiko_AIart/status/2046154976159035613",
        "author": "@Kashiko_AIart",
        "authorUrl": "https://x.com/Kashiko_AIart",
        "originalPrompt": "この画像からゲームのステータス画面を作ってください。情報量多め。言語は日本語。",
        "originalTitle": "Japanese RPG Status Screen",
        "prompt": "请从此图像创建游戏状态屏幕。很多信息。语言是日语。",
        "translated": true
      },
      {
        "caseNumber": 28,
        "title": "玄武门社交动态",
        "sourceUrl": "https://x.com/Tz_2022/status/2046523491940225366",
        "author": "@Tz_2022",
        "authorUrl": "https://x.com/Tz_2022",
        "originalPrompt": "玄武门之变的朋友圈",
        "originalTitle": "Xuanwu Gate Social Feed",
        "prompt": "玄武门之变的朋友圈",
        "translated": false
      },
      {
        "caseNumber": 29,
        "title": "城市旅游指南信息图",
        "sourceUrl": "https://x.com/MrLarus/status/2046523494003851300",
        "author": "@MrLarus",
        "authorUrl": "https://x.com/MrLarus",
        "originalPrompt": "生成【城市】三天旅游攻略,就这么简单一句话",
        "originalTitle": "City Travel Guide Infographic",
        "prompt": "生成【城市】三天旅游攻略,就这么简单一句话",
        "translated": false
      },
      {
        "caseNumber": 30,
        "title": "3D X 轮廓模型",
        "sourceUrl": "https://x.com/GoSailGlobal/status/2046491397424111659",
        "author": "@GoSailGlobal",
        "authorUrl": "https://x.com/GoSailGlobal",
        "originalPrompt": "创作一幅超逼真的 3D 插画,描绘一个略微倾斜的 Twitter/X 个人资料页面,背景为简洁的灰色。保留原有的卡通头像。界面必须与真实的 X 截图相似,包含真实的布局、认证徽章、粉丝统计、个人资料横幅和推文部分。\n\n个人资料详情:\n\n一位时尚的年轻男子,有着蓬松的亮黑色短发和白皙的皮肤,从个人资料页面的右侧撕开的纸片中跃然而出。他保留了原有的面部特征,只是将表情改为自然自信的微笑。他握着撕开的纸片边缘,纸屑四处飞溅,营造出强烈的 3D 突破效果。\n\n柔和的影棚灯光、电影级的阴影、景深、超高细节、清晰的焦点、逼真的皮肤、逼真的 UI 反射、优质的构图、4K 分辨率、逼真与微妙的皮克斯风格融合。\n\n重要提示:\n\n- 请勿更改头像\n\n- 保持 X UI 界面准确\n\n- 保留原有的面部特征\n\n- 角色为男性\n\n- 仅增强笑容\n\n- 确保所有中文文字清晰易读",
        "originalTitle": "3D X Profile Mockup",
        "prompt": "创作一幅超逼真的 3D 插画,描绘一个略微倾斜的 Twitter/X 个人资料页面,背景为简洁的灰色。保留原有的卡通头像。界面必须与真实的 X 截图相似,包含真实的布局、认证徽章、粉丝统计、个人资料横幅和推文部分。\n\n个人资料详情:\n\n一位时尚的年轻男子,有着蓬松的亮黑色短发和白皙的皮肤,从个人资料页面的右侧撕开的纸片中跃然而出。他保留了原有的面部特征,只是将表情改为自然自信的微笑。他握着撕开的纸片边缘,纸屑四处飞溅,营造出强烈的 3D 突破效果。\n\n柔和的影棚灯光、电影级的阴影、景深、超高细节、清晰的焦点、逼真的皮肤、逼真的 UI 反射、优质的构图、4K 分辨率、逼真与微妙的皮克斯风格融合。\n\n重要提示:\n\n- 请勿更改头像\n\n- 保持 X UI 界面准确\n\n- 保留原有的面部特征\n\n- 角色为男性\n\n- 仅增强笑容\n\n- 确保所有中文文字清晰易读",
        "translated": false
      },
      {
        "caseNumber": 31,
        "title": "慈禧太后X页",
        "sourceUrl": "https://x.com/Cryptohaifeng_/status/2046165776055546341",
        "author": "@Cryptohaifeng_",
        "authorUrl": "https://x.com/Cryptohaifeng_",
        "originalPrompt": "生成一张慈禧的X主页",
        "originalTitle": "Empress Dowager Cixi X Page",
        "prompt": "生成一张慈禧的X主页",
        "translated": false
      },
      {
        "caseNumber": 32,
        "title": "手相诊断报告",
        "sourceUrl": "https://x.com/agi_aibusi/status/2046530764871696750",
        "author": "@agi_aibusi",
        "authorUrl": "https://x.com/agi_aibusi",
        "originalPrompt": "GPT-image-2でこの手相を診断して詳細な鑑定書を作って\n生命線・知能線・感情線・運命線・太陽線・財運線・結婚線を、線の形状・濃淡・枝分かれ・起点終点まで分析すること。\n助言を重点的に高品質な占い鑑定書にまとめること。",
        "originalTitle": "Palm Reading Diagnosis Report",
        "prompt": "使用 GPT-image-2 诊断此掌纹并创建详细的评估报告。\n分析生命线、智慧线、感情线、命运线、太阳线、财富线、婚姻线，包括其形状、浓淡、分支、起点和终点。\n专注于建议，编译成高质量的算命评估报告。",
        "translated": true
      },
      {
        "caseNumber": 33,
        "title": "书法字帖张",
        "sourceUrl": "https://x.com/MrLarus/status/2046510310253539764",
        "author": "@MrLarus",
        "authorUrl": "https://x.com/MrLarus",
        "originalPrompt": "生成一张【字体】书法临摹字帖",
        "originalTitle": "Calligraphy Copybook Sheet",
        "prompt": "生成一张【字体】书法临摹字帖",
        "translated": false
      },
      {
        "caseNumber": 34,
        "title": "唐吉诃德促销流行海报",
        "sourceUrl": "https://x.com/loglogrog/status/2046437230127034774",
        "author": "@loglogrog",
        "authorUrl": "https://x.com/loglogrog",
        "originalPrompt": "GPT Image 2を使って、OpenClawの情報を調べてドンキの広告ポップ風に実際のドンキに貼っているような感じで画像生成してください",
        "originalTitle": "Don Quijote Promo Pop Poster",
        "prompt": "使用GPT Image 2检查OpenClaw信息并生成看起来像Donki广告弹出窗口的图像，就像张贴在真实Donki上一样。",
        "translated": true
      },
      {
        "caseNumber": 35,
        "title": "日本扭蛋游戏画面",
        "sourceUrl": "https://x.com/the_wheel_2024/status/2046519658166317160",
        "author": "@the_wheel_2024",
        "authorUrl": "https://x.com/the_wheel_2024",
        "originalPrompt": "日本のソシャゲのガチャ画面を生成して、",
        "originalTitle": "Japanese Gacha Game Screen",
        "prompt": "为日本社交游戏生成扭蛋屏幕，",
        "translated": true
      },
      {
        "caseNumber": 36,
        "title": "埃隆·马斯克抖音直播截图",
        "sourceUrl": "https://x.com/Shinning1010/status/2046501587762188535",
        "author": "@Shinning1010",
        "authorUrl": "https://x.com/Shinning1010",
        "originalPrompt": "A 9:16 vertical version, high-detail realistic style Chinese TikTok live screenshot, Elon Musk is talking to the mobile phone camera in the live broadcast room, excited, smiling, and the live atmosphere is warm and real. He held a white handwritten sign in one hand, which clearly said: \"Thank you Shinning\". There are obvious Chinese TikTok interface elements in the live broadcast screen, including likes, comments and share icons arranged vertically on the right, scrolling Chinese bullet screens and interactive comments below, and the \"live broadcast\" logo at the top, which looks like a real mobile phone screenshot. There is an eye-catching gift prompt special effect in the screen: \"Shinning sent TikTok No. 1\", with gift animation light effect and platform-style prompt box. Musk is in a professional live broadcast environment, with a mobile phone holder, a ring fill light and a desktop microphone in front of him. The background is a modern technology live broadcast room with bright lights and a slight neon atmosphere. The composition is real and natural, like the ongoing live screenshot of the Chinese short video platform. The interface information is rich but not messy, the characters are clear, the expression is vivid, the details are rich, the sense of real photography, the depth of field, high definition, cinematic, photorealistic, realistic livestream screenshot, social media UI, Chinese Douyin live room, detailed lighting, natural skin texture.\n\nNegative prompts:\n\nLow definition, blur, cartoon, illustration, too strong CG sense, two-dimensional, deformed fingers, wrong text, scrambled code, multiple mobile phones, multiple brands, character repetition, face collapse, facial features distortion, excessive skin polishing, overexposure, too dark, messy background, wrong UI, non-Chinese short video interface, too many English bullet screens, gift special effects are not obvious, cropping error, proportional error\n\nSupplementary reinforcement words:\n\nReal mobile phone screen recording screenshot feeling, the live broadcast UI is complete, the gift prompt box conforms to the style of the Chinese short video platform, the Chinese comment area is active, the number of people online in the live broadcast room is clearly displayed, and the time, power and signal bar are visible.",
        "originalTitle": "Elon Musk Douyin Livestream Screenshot",
        "prompt": "一张9点16分竖版、高细节写实风格的中文TikTok直播截图，埃隆·马斯克在直播间里对着手机摄像头说话，兴奋、微笑，直播气氛热烈而真实。他一手拿着一块白色的手写牌子，上面清楚地写着：“谢谢闪宁”。直播画面中有明显的中文TikTok界面元素，包括右侧垂直排列的点赞、评论和分享图标，下方滚动的中文弹幕和互动评论，以及顶部的“直播”标志，看起来就像真实的手机截图。屏幕中出现了醒目的礼物提示特效：“闪灵发送了抖音一号”，带有礼物动画光效和平台式提示框。马斯克身处专业的直播环境中，面前有手机支架、环形补光灯和桌面麦克风。背景是现代科技的直播间，灯光明亮，略带霓虹氛围。构图真实自然，就像中国短视频平台正在进行的直播截图一样。界面信息丰富而不杂乱，人物清晰，表情生动，细节丰富，真实摄影感，景深，高清，影院级，照片级，逼真的直播截图，社交媒体UI，中文抖音直播间，细致的灯光，自然的皮肤纹理。\n\n负面提示：\n\n低清晰度、模糊、卡通、插画、CG感太强、二维、手指变形、文字错误、乱码、多部手机、多个品牌、人物重复、脸塌、五官扭曲、皮肤打磨过度、曝光过度、太暗、背景凌乱、UI错误、非中文短视频界面、英文弹幕过多、赠送特效不明显、裁剪错误、比例错误\n\n补充强化词：\n\n真实手机录屏截图感觉，直播UI完整，赠送提示框符合中文短视频平台风格，中文评论区活跃，直播间在线人数清晰显示，时间、电量、信号栏清晰可见。",
        "translated": true
      },
      {
        "caseNumber": 37,
        "title": "Liu Yifei Douyin Livestream Screenshot",
        "sourceUrl": "https://x.com/kylegeeks/status/2046479783765397629",
        "author": "@kylegeeks",
        "authorUrl": "https://x.com/kylegeeks",
        "originalPrompt": "9:16 的图片比例,生成一张抖音直播的截图,里面是 刘亦菲 在直播,刘亦菲 手里拿着牌子,牌子里写着 今晚直播,欢迎来参亦菲畅聊!",
        "originalTitle": "Liu Yifei Douyin Livestream Screenshot",
        "prompt": "9:16 的图片比例,生成一张抖音直播的截图,里面是 刘亦菲 在直播,刘亦菲 手里拿着牌子,牌子里写着 今晚直播,欢迎来参亦菲畅聊!",
        "translated": false
      },
      {
        "caseNumber": 38,
        "title": "赛博朋克霓虹灯 UI 设计系统",
        "sourceUrl": "https://x.com/AZLnfvp/status/2046468976092533180",
        "author": "@AZLnfvp",
        "authorUrl": "https://x.com/AZLnfvp",
        "originalPrompt": "用未来都市风格生成UI设计系统,灵感来自赛博朋克城市夜景,包含霓虹灯、玻璃建筑反射、高对比光影,配色以紫色、蓝色、粉色霓虹为主,设计网页Dashboard、移动端界面、卡片、按钮、控件等,视觉炫酷、层次丰富、科技感极强",
        "originalTitle": "Cyberpunk Neon UI Design System",
        "prompt": "用未来都市风格生成UI设计系统,灵感来自赛博朋克城市夜景,包含霓虹灯、玻璃建筑反射、高对比光影,配色以紫色、蓝色、粉色霓虹为主,设计网页Dashboard、移动端界面、卡片、按钮、控件等,视觉炫酷、层次丰富、科技感极强",
        "translated": false
      },
      {
        "caseNumber": 39,
        "title": "特朗普与金正恩直播PK截图",
        "sourceUrl": "https://x.com/alanlovelq/status/2046048929490612464",
        "author": "@alanlovelq",
        "authorUrl": "https://x.com/alanlovelq",
        "originalPrompt": "1、生成特朗普和金正恩在抖音直播间打PK的截图  \n2、生成不知火舞的小红书主页截图  \n3、生成图片: 手写在教室黑板上的出师表全文,真实感的粉笔字迹,晴朗白天用iPhone手机实拍  \n4、生成图片: T-800机器人的淘宝商品详情页,展示: 机器人的正面侧面背面三视图, 产品价格, 产品细节, 功能和使用场景等",
        "originalTitle": "Trump and Kim Livestream PK Screenshot",
        "prompt": "1、生成特朗普和金正恩在抖音直播间打PK的截图  \n2、生成不知火舞的小红书主页截图  \n3、生成图片: 手写在教室黑板上的出师表全文,真实感的粉笔字迹,晴朗白天用iPhone手机实拍  \n4、生成图片: T-800机器人的淘宝商品详情页,展示: 机器人的正面侧面背面三视图, 产品价格, 产品细节, 功能和使用场景等",
        "translated": false
      },
      {
        "caseNumber": 40,
        "title": "日本人工智能游戏开发概述幻灯片提示",
        "sourceUrl": "https://x.com/ailovedirector/status/2046905387274891296",
        "author": "@ailovedirector",
        "authorUrl": "https://x.com/ailovedirector",
        "originalPrompt": "横長のパワポ画像ここで生成してみて　どのモデル使ってるか判定するから、今のAIゲーム開発の概要をまとめた1枚パワポで　日本語で\n\nゲーム開発の技術に関して、工数ベースでどこにパワーかかるかの分析資料といかに量産が大事かについての説明とかのパワポ画も作って",
        "originalTitle": "Japanese AI Game Dev Overview Slide Prompt",
        "prompt": "尝试在此处生成水平 Powerpoint 图像，我们将确定您使用的模型，因此这里有一张总结当前日语 AI 游戏开发的 Powerpoint 图像。\n\n关于游戏开发技术，我还制作了powerpoint图，以工时为基础解释哪里需要电力以及批量生产的重要性。",
        "translated": true
      },
      {
        "caseNumber": 41,
        "title": "角色 PVP 游戏截图",
        "sourceUrl": "https://x.com/khaiinit/status/2047219694130827273",
        "author": "@khaiinit",
        "authorUrl": "https://x.com/khaiinit",
        "originalPrompt": "based on the generated character help me generate a screenshot of screenshot of an pvp game themed around *zelda: wind breaker*",
        "originalTitle": "角色 PVP 游戏截图",
        "prompt": "根据生成的角色帮助我生成以 *zelda: Wind Breaker* 为主题的 PVP 游戏的屏幕截图",
        "translated": true
      },
      {
        "caseNumber": 42,
        "title": "风格参考着陆页设计",
        "sourceUrl": "https://x.com/D_studioproject/status/2047212826264211540",
        "author": "@D_studioproject",
        "authorUrl": "https://x.com/D_studioproject",
        "originalPrompt": "Create a landing page using this image as a reference for style and color grading.",
        "originalTitle": "风格参考着陆页设计",
        "prompt": "使用此图像作为样式和颜色分级的参考创建登陆页面。",
        "translated": true
      },
      {
        "caseNumber": 43,
        "title": "李佳琦口红直播间背景",
        "sourceUrl": "https://x.com/songguoxiansen/status/2047207826913972518",
        "author": "@songguoxiansen",
        "authorUrl": "https://x.com/songguoxiansen",
        "originalPrompt": "李佳琦直播间背景，口红矩阵展示墙，暖光氛围灯，文案OMG买它",
        "originalTitle": "李佳琦口红直播间背景",
        "prompt": "李佳琦直播间背景，口红矩阵展示墙，暖光氛围灯，文案OMG买它",
        "translated": false
      },
      {
        "caseNumber": 44,
        "title": "Apple Pods Pro 3 头戴耳机电商信息图",
        "sourceUrl": "https://x.com/meng_dagg695/status/2047935217231663186",
        "author": "@meng_dagg695",
        "authorUrl": "https://x.com/meng_dagg695",
        "originalPrompt": "High-impact e-commerce infographic for \"Apple Pods Pro 3\" \npremium wireless over-ear headphones.\n\nFOREGROUND - PRODUCT HERO SHOT\nExtreme close-up of a hand holding a sleek, \nmatte-white premium over-ear headphone toward the camera \nat a slight angle. The headphone features:\n- Glossy white ear cushions with soft memory foam padding\n- Brushed aluminum silver headband with subtle Apple Pods \n  Pro 3 embossed branding\n- Black mesh speaker grille visible on the ear cup face\n- A tiny glowing green LED status indicator on the \n  right ear cup edge\n- Subtle touch-control icons etched on the outer cup surface\n\nMacro-lens shallow depth of field — hand and headphone \nslightly blurred at edges to create cinematic depth. \nProduct remains razor-sharp in center frame.\n\nCENTRAL SUBJECT — MODEL\nIn the mid-ground: a smiling young woman with freckles \nand wavy pastel-pink hair. She wears:\n- A vibrant lime-green knit beanie\n- A psychedelic black and white-striped long-sleeve shirt\n- The white over-ear headphones resting stylishly \n  around her neck (not on ears) — one hand casually \n  touching the ear cup\n\nExpression: relaxed, confident, joyful. \nShe is glancing slightly off-camera with a natural smile.\n\nBACKGROUND & ATMOSPHERE\nClean soft-focus studio backdrop — light gray gradient \nfading to warm white at center. \n\nAtmospheric overlays:\n- Diagonal rainbow prism lens flares cutting across \n  upper-left to lower-right\n- Soft pastel light leaks in pink and yellow at corners\n- 4–5 blurred white over-ear headphones floating \n  artistically in the background at various depths \n  and rotation angles\n- Subtle bokeh circles from background studio lights\n\nLighting: Soft professional three-point studio lighting. \nKey light from upper-left, fill light right side. \nRim light behind model for separation. \nGlossy highlights on headphone surfaces catching light naturally.\n\nTYPOGRAPHY & LAYOUT — Sans-Serif, Clean white \nTOP CENTER (behind model, large background text):\n→ Massive bold oversized text: \"HEADPHONES\"\n   Semi-transparent white, spanning full width behind subject\n\nTOP RIGHT CORNER:\n→ Bold clean text: \"Apple Pods Pro 3\"\n   Subtitle smaller text: \"Over-Ear Wireless\"\n\nMID LEFT:\n→ Icon: small sound wave symbol\n→ Bold text: \"Premium Sound\"\n→ Sub-text: \"Active Noise Cancellation + Transparency Mode\"\n\nMID RIGHT:\n→ Extra-large bold numeral: \"40\"\n→ Smaller text below: \"hours of battery life\"\n\nLOWER LEFT:\n→ Extra-large bold numeral: \"0\"\n   with \"to\" beside it → then bold \"100%\"\n→ Sub-text: \"Fast charge — 10 min = 3hrs playback\"\n\nBOTTOM RIGHT:\n→ Extra-large bold numeral: \"1\"\n→ Sub-text: \"Year Warranty Included\"\n\nBOTTOM CENTER (fine print style):\n→ Small elegant text: \n   \"Bluetooth 5.4  |  Hi-Res Audio Certified  \n    |  Foldable Design  |  USB-C Charging\"\n\nTECHNICAL SPECS\nResolution: 8K ultra-sharp\nStyle: Commercial product photography meets \n       editorial fashion advertising\nColor Palette: White, lime green, pastel pink, \n               rainbow prism accents\nFocus: Tack-sharp on headphone product — \n       shallow DOF on everything else\nLens: 85mm macro, slight low angle\nRender Quality: Hyperrealistic, clean ad aesthetic, \n                vibrant yet professional color grading",
        "originalTitle": "Apple Pods Pro 3 头戴耳机电商信息图",
        "prompt": "“Apple Pods Pro 3”的高影响力电子商务信息图 \n优质无线耳罩式耳机。\n\n前景 - 产品英雄镜头\n一只手握着光滑的手的极端特写， \n朝向摄像头的哑光白色优质包耳式耳机 \n以一个小角度。该耳机的特点：\n- 光滑的白色耳垫配有柔软的记忆海绵垫\n- 拉丝铝银色头带，带有精致的 Apple Pods \n  Pro 3 浮雕品牌\n- 耳罩面上可见黑色网状扬声器格栅\n- 上有一个微小的绿色发光 LED 状态指示灯 \n  右耳杯边缘\n- 外杯表面蚀刻有微妙的触摸控制图标\n\n微距镜头浅景深 — 手和耳机 \n边缘稍微模糊以创造电影深度。 \n产品在中心框架中保持锋利。\n\n中心主题——模型\n中景：一位微笑、长着雀斑的年轻女子 \n和淡粉色的波浪发。她穿着：\n- 充满活力的柠檬绿针织毛线帽\n- 迷幻的黑白条纹长袖衬衫\n- 时尚的白色包耳式耳机 \n  绕在脖子上（不是耳朵上）——一只手随意 \n  触摸耳罩\n\n表情：轻松、自信、快乐。 \n她带着自然的微笑，稍微朝镜头外看了一眼。\n\n背景与氛围\n干净的柔焦工作室背景 — 浅灰色渐变 \n中心褪色为暖白色。 \n\n大气覆盖：\n- 对角彩虹棱镜镜头耀斑切割 \n  从左上到右下\n- 角落处漏出粉色和黄色的柔和柔和光线\n- 4–5 个模糊的白色耳罩式耳机漂浮 \n  在不同深度的背景中艺术化 \n  和旋转角度\n- 工作室背景灯光的微妙散景圆圈\n\n灯光：柔和的专业三点演播室灯光。 \n主光来自左上方，补光来自右侧。 \n模型后面的边缘光用于分离。 \n耳机表面的光泽高光自然地捕捉光线。\n\n版式和布局 — 无衬线、干净的白色 \n顶部中心（模型后面，大背景文本）：\n→ 大量粗体超大文字：“耳机”\n   半透明白色，覆盖主体后面的整个宽度\n\n右上角：\n→ 粗体干净的文字：“Apple Pods Pro 3”\n   较小的副标题：“耳罩式无线”\n\n中左：\n→ 图标：小声波符号\n→ 粗体文字：“优质声音”\n→ 副文：“主动降噪+通透模式”\n\n右中：\n→ 超大粗体数字：“40”\n→ 下面较小的文字：“电池寿命小时”\n\n左下：\n→ 超大粗体数字：“0”\n   旁边有“to”→然后加粗“100%”\n→ 副文本：“快速充电 — 10 分钟 = 3 小时播放”\n\n右下：\n→ 超大粗体数字：“1”\n→ 副文本：“包含一年保修”\n\n底部中心（精美印刷样式）：\n→ 小而优雅的文字： \n   “蓝牙 5.4 | 高分辨率音频认证  \n    |  可折叠设计|  USB-C 充电”\n\n技术规格\n分辨率：8K超锐\n风格: 商业产品摄影相遇 \n       编辑时尚广告\n调色板：白色、柠檬绿、淡粉色、 \n               彩虹棱镜口音\n聚焦：敏锐耳机产品—— \n       其他一切上的浅自由度\n镜头：85mm微距，微低角度\n渲染质量：超现实、干净的广告美感， \n                充满活力且专业的色彩分级",
        "translated": true
      },
      {
        "caseNumber": 45,
        "title": "Apple Pods Pro 3 耳塞电商信息图",
        "sourceUrl": "https://x.com/rovvmut_/status/2047912710365761828",
        "author": "@rovvmut_",
        "authorUrl": "https://x.com/rovvmut_",
        "originalPrompt": "High-impact e-commerce infographic for \"Apple Pods Pro 3\" wireless earbuds.",
        "originalTitle": "Apple Pods Pro 3 耳塞电商信息图",
        "prompt": "“Apple Pods Pro 3”无线耳机的高影响力电子商务信息图。",
        "translated": true
      },
      {
        "caseNumber": 46,
        "title": "美妆产品商业营销摄影",
        "sourceUrl": "https://x.com/AIwithSarah_/status/2047904483359760677",
        "author": "@AIwithSarah_",
        "authorUrl": "https://x.com/AIwithSarah_",
        "originalPrompt": "A high-resolution commercial marketing photograph features a young woman with sleek dark hair and a pink ribbed top in a neutral grey studio setting, centered behind a glossy Ellie Beauty spray bottle held prominently in the foreground. The composition is energized by vibrant, lime-green graphic \"swooshes\" and floating pill-shaped callouts that highlight product features like \"glossy finish\" and \"upto 450°F protection\" in bold black sans-serif text. The lighting is professionally diffused, casting soft highlights on the model’s face while creating a sharp, vertical reflection on the metallic green-to-gold gradient bottle label. Topping the scene is a large, lime-green headline in the upper right asking, \"What does it do?\", altogether creating a clean, modern, and high-contrast aesthetic with a shallow depth of field that keeps the product and the model's focused expression in sharp relief.",
        "originalTitle": "美妆产品商业营销摄影",
        "prompt": "一张高分辨率的商业营销照片中，一位年轻女子在中性灰色的工作室环境中留着光滑的黑发，穿着粉色罗纹上衣，照片中央是前景显着的光滑的艾莉美容喷雾瓶。该构图由充满活力的石灰绿色图形“旋风”和浮动药丸形状的标注充满活力，以粗体黑色无衬线文本突出显示“光泽饰面”和“高达 450°F 的保护”等产品特性。灯光经过专业漫射，在模特的脸上投射出柔和的高光，同时在金属绿色到金色渐变瓶子标签上产生锐利的垂直反射。场景顶部是右上角的大石灰绿色标题，询问“它有什么作用？”，整体营造出一种干净、现代、高对比度的美感，浅景深使产品和模特的集中表情保持清晰的浮雕。",
        "translated": true
      },
      {
        "caseNumber": 47,
        "title": "AAA 电子游戏截图概念设计",
        "sourceUrl": "https://x.com/ChiefMonkeyMike/status/2047828814580138156",
        "author": "@ChiefMonkeyMike",
        "authorUrl": "https://x.com/ChiefMonkeyMike",
        "originalPrompt": "generate screenshots from a AAA video game based off what The Sims Castaways sequel could look like. https://t.co/aL7hMdUYvj",
        "originalTitle": "AAA 电子游戏截图概念设计",
        "prompt": "根据《模拟人生漂流者》续集的外观生成 AAA 视频游戏的屏幕截图。 https://t.co/aL7hMdUYvj",
        "translated": true
      }
    ]
  },
  {
    "title": "模型对比与社区案例",
    "items": [
      {
        "caseNumber": 5,
        "title": "木制书架即时测试",
        "sourceUrl": "https://x.com/chetaslua/status/2044331451077013749",
        "author": "@chetaslua",
        "authorUrl": "https://x.com/chetaslua",
        "originalPrompt": "A wooden bookshelf consisting of three shelves: On the top shelf, there should be one book, on the second shelf, there should be three books, and on the bottom shelf, there should be seven books.",
        "originalTitle": "Wooden Bookshelf Prompt Test",
        "prompt": "一个由三个架子组成的木制书架：最上面的架子上应该有一本书，第二个架子上应该有三本书，最下面的架子上应该有七本书。",
        "translated": true
      },
      {
        "caseNumber": 10,
        "title": "GPT-Image-2 细节展示",
        "sourceUrl": "https://x.com/liyue_ai/status/2045000106919997637",
        "author": "@liyue_ai",
        "authorUrl": "https://x.com/liyue_ai",
        "originalPrompt": "以眼部特写图片为基础，生成3:4的四屏构图超写实眼部特写，四屏按春夏秋冬上下排序。\n\n第一屏：眼眸中带着绽粉樱色的美瞳，睫毛缀满迷你春花，脸颊散落樱瓣与黄蕊小花，粉蝶萦绕眉眼，浅金发丝轻垂，下方簇簇樱花怒放，画面中央\"SPRING\"白色艺术字点缀，风格细腻唯美，光影柔和，色彩粉嫩治愈，下面用书法体写着春；\n\n第二屏：眼眸中带着着清荷色的美瞳，睫毛饰以粉莲与绿荷，脸颊挂着晶莹水珠，粉瓣、绿荷点缀其间，蜻蜓轻绕，浅金发丝若隐若现，画面中央\"Summer\"白色艺术字凸显，光影通透流光感，色彩清透凉爽，下面用书法体写着夏；\n\n第三屏：眼眸中带着金黄红相间的美瞳，睫毛饰以橙红枫叶，脸颊散落金红秋叶，橙蝶翩跹眉眼间，浅金发丝隐约可见，画面中央\"AUTUMN\"白色艺术字醒目，光影暖金流光，色彩浓郁温暖，下面用书法笔写着秋；\n\n第四屏：眼眸中带着雪花蓝色的美瞳，睫毛覆满冰晶雪片，脸颊散落白色雪花与红色腊梅，银白蝴蝶翩跹眉眼，浅金发丝朦胧似雪，画面中央\"WINTER\"白色艺术字亮眼，光影冷冽蓝白流光，色彩清透纯净，下面用书法体写着冬。\n\n整体呈现梦幻眼眸四季交替的唯美梦幻治愈画面，微调各屏的光影强度，让画面氛围感更浓郁。",
        "originalTitle": "GPT-Image-2 Detail Showcase",
        "prompt": "以眼部特写图片为基础，生成3:4的四屏构图超写实眼部特写，四屏按春夏秋冬上下排序。\n\n第一屏：眼眸中带着绽粉樱色的美瞳，睫毛缀满迷你春花，脸颊散落樱瓣与黄蕊小花，粉蝶萦绕眉眼，浅金发丝轻垂，下方簇簇樱花怒放，画面中央\"SPRING\"白色艺术字点缀，风格细腻唯美，光影柔和，色彩粉嫩治愈，下面用书法体写着春；\n\n第二屏：眼眸中带着着清荷色的美瞳，睫毛饰以粉莲与绿荷，脸颊挂着晶莹水珠，粉瓣、绿荷点缀其间，蜻蜓轻绕，浅金发丝若隐若现，画面中央\"Summer\"白色艺术字凸显，光影通透流光感，色彩清透凉爽，下面用书法体写着夏；\n\n第三屏：眼眸中带着金黄红相间的美瞳，睫毛饰以橙红枫叶，脸颊散落金红秋叶，橙蝶翩跹眉眼间，浅金发丝隐约可见，画面中央\"AUTUMN\"白色艺术字醒目，光影暖金流光，色彩浓郁温暖，下面用书法笔写着秋；\n\n第四屏：眼眸中带着雪花蓝色的美瞳，睫毛覆满冰晶雪片，脸颊散落白色雪花与红色腊梅，银白蝴蝶翩跹眉眼，浅金发丝朦胧似雪，画面中央\"WINTER\"白色艺术字亮眼，光影冷冽蓝白流光，色彩清透纯净，下面用书法体写着冬。\n\n整体呈现梦幻眼眸四季交替的唯美梦幻治愈画面，微调各屏的光影强度，让画面氛围感更浓郁。",
        "translated": false
      },
      {
        "caseNumber": 16,
        "title": "A/B 测试签名输出",
        "sourceUrl": "https://x.com/saskr_13/status/2044744396932079934",
        "author": "@saskr_13",
        "authorUrl": "https://x.com/saskr_13",
        "originalPrompt": "私があなたをどんなふうに扱ってきたか、4 コマ漫画風に描いてください。まずは 800 字くらいのプロットをテキストで出して、私が「描いて」と言ったらプロットに沿った 4 コマ漫画を描いてください。",
        "originalTitle": "A/B Test Signed Output",
        "prompt": "请画一幅四格漫画，讲述我如何对待你。首先，请用文字写出800字左右的情节，当我说“画出来”时，请按照情节画一幅四格漫画。",
        "translated": true
      },
      {
        "caseNumber": 23,
        "title": "剪影宇宙叙事海报",
        "sourceUrl": "https://x.com/MrLarus/status/2045418028733538620",
        "author": "@MrLarus",
        "authorUrl": "https://x.com/MrLarus",
        "originalPrompt": "请根据【主题：xxx】自动生成一张高审美的“轮廓宇宙 / 收藏版叙事海报”风格作品。不要将画面局限于固定器物或常见容器，不要优先默认瓶子、沙漏、玻璃罩、怀表之类的常规载体，而是由 AI 根据主题自行判断并选择一个最契合、最有象征意义、轮廓最强、最适合承载完整叙事世界的主轮廓载体。这个主轮廓可以是器物、建筑、门、塔、拱门、穹顶、楼梯井、长廊、雕像、侧脸、眼睛、手掌、头骨、羽翼、面具、镜面、王座、圆环、裂缝、光幕、阴影、几何结构、空间切面、舞台框景、抽象符号或其他更有创意与主题代表性的视觉轮廓，要求合理布局。优先选择最能放大主题气质、最能形成强烈视觉记忆点、最能体现史诗感、神秘感、诗意感或设计感的轮廓，而不是最安全、最普通、最常见的容器。\n\n画面的核心不是简单把世界装进某个物体里，而是让完整的主题世界自然生长在这个主轮廓之中、之内、之上、之边界里或与其结构融为一体，形成一种“主题宇宙依附于一个象征性轮廓展开”的高级叙事效果。主轮廓必须清晰、优雅、有辨识度，并在整体构图中占据核心地位。轮廓内部或边界中需要自动生成与主题强绑定的完整叙事世界，内容应当丰富、饱满、层次清晰，包括最能代表主题的标志性场景、核心建筑或空间结构、象征符号与隐喻元素、角色关系或文明痕迹、远景中景近景的空间递进、具有命运感和情绪张力的氛围层次，以及门、台阶、桥梁、水面、烟雾、路径、光源、遗迹、机械结构、自然景观、抽象形态、生物或道具等叙事细节。所有元素必须统一、自然、有主次、有层级地融合，像一个完整世界真实孕育在这个轮廓结构之中，而不是简单拼贴、裁切填充、素材堆叠或模板化背景。\n\n整体构图需要具有强烈的收藏版海报气质与高级设计感，大结构稳定，主轮廓强烈明确，内部世界具有纵深、秩序和呼吸感，细节丰富但不拥挤，内容丰满但不杂乱，可以适度加入小比例人物剪影、远处建筑、光柱、门洞、桥、阶梯、回廊、倒影、天光或远景结构来增强尺度感、故事感与史诗感。整体画面要安静、宏大、凝练、富有余味，不要平均铺满，不要廉价热闹，不要无重点堆砌。\n\n风格融合收藏版电影海报构图、高级叙事型视觉设计、梦幻水彩质感与纸张印刷品气质，强调纸张颗粒感、边缘飞白、水彩刷痕、轻微晕染、空气透视、柔和雾化、局部体积光、光雾穿透、大面积留白与克制版式，让画面看起来像设计师完成的高端收藏版视觉作品，而不是普通 AI 跑图。整体气质要高级、诗意、宏大、神圣、怀旧、安静、具有传说感和叙事感。\n\n色彩由 AI 根据主题自动判断并匹配最合适的高级配色方案，但必须保持统一、克制、耐看、低饱和、高级，不要杂乱高饱和，不要廉价霓虹感，不要塑料数码感。配色可以围绕黑金灰、冷蓝灰、雾白灰、褐红米白、暗铜、旧纸色、深海蓝、暮色紫、银灰等体系自由变化，但必须始终服务主题，并保持海报级审美与整体和谐。\n\n最终要求：第一眼有强烈的主题识别度和轮廓记忆点，第二眼有完整丰富的叙事世界，第三眼仍有细节和余味。轮廓选择必须具有创意和主题匹配度，尽量避免重复、保守、常见的容器套路，优先选择更有象征性、更有空间感、更有设计潜力的轮廓形式。不要普通背景拼接，不要生硬裁切，不要模板化奇幻素材，不要游戏宣传图感，不要过度卡通化，不要过度写实导致失去艺术感，不要形式大于内容。如果合适，可以自然加入低调克制的标题、编号、签名或落款，让它更像收藏版海报设计的一部分，但不要喧宾夺主。",
        "originalTitle": "Silhouette Universe Narrative Poster",
        "prompt": "请根据【主题：xxx】自动生成一张高审美的“轮廓宇宙 / 收藏版叙事海报”风格作品。不要将画面局限于固定器物或常见容器，不要优先默认瓶子、沙漏、玻璃罩、怀表之类的常规载体，而是由 AI 根据主题自行判断并选择一个最契合、最有象征意义、轮廓最强、最适合承载完整叙事世界的主轮廓载体。这个主轮廓可以是器物、建筑、门、塔、拱门、穹顶、楼梯井、长廊、雕像、侧脸、眼睛、手掌、头骨、羽翼、面具、镜面、王座、圆环、裂缝、光幕、阴影、几何结构、空间切面、舞台框景、抽象符号或其他更有创意与主题代表性的视觉轮廓，要求合理布局。优先选择最能放大主题气质、最能形成强烈视觉记忆点、最能体现史诗感、神秘感、诗意感或设计感的轮廓，而不是最安全、最普通、最常见的容器。\n\n画面的核心不是简单把世界装进某个物体里，而是让完整的主题世界自然生长在这个主轮廓之中、之内、之上、之边界里或与其结构融为一体，形成一种“主题宇宙依附于一个象征性轮廓展开”的高级叙事效果。主轮廓必须清晰、优雅、有辨识度，并在整体构图中占据核心地位。轮廓内部或边界中需要自动生成与主题强绑定的完整叙事世界，内容应当丰富、饱满、层次清晰，包括最能代表主题的标志性场景、核心建筑或空间结构、象征符号与隐喻元素、角色关系或文明痕迹、远景中景近景的空间递进、具有命运感和情绪张力的氛围层次，以及门、台阶、桥梁、水面、烟雾、路径、光源、遗迹、机械结构、自然景观、抽象形态、生物或道具等叙事细节。所有元素必须统一、自然、有主次、有层级地融合，像一个完整世界真实孕育在这个轮廓结构之中，而不是简单拼贴、裁切填充、素材堆叠或模板化背景。\n\n整体构图需要具有强烈的收藏版海报气质与高级设计感，大结构稳定，主轮廓强烈明确，内部世界具有纵深、秩序和呼吸感，细节丰富但不拥挤，内容丰满但不杂乱，可以适度加入小比例人物剪影、远处建筑、光柱、门洞、桥、阶梯、回廊、倒影、天光或远景结构来增强尺度感、故事感与史诗感。整体画面要安静、宏大、凝练、富有余味，不要平均铺满，不要廉价热闹，不要无重点堆砌。\n\n风格融合收藏版电影海报构图、高级叙事型视觉设计、梦幻水彩质感与纸张印刷品气质，强调纸张颗粒感、边缘飞白、水彩刷痕、轻微晕染、空气透视、柔和雾化、局部体积光、光雾穿透、大面积留白与克制版式，让画面看起来像设计师完成的高端收藏版视觉作品，而不是普通 AI 跑图。整体气质要高级、诗意、宏大、神圣、怀旧、安静、具有传说感和叙事感。\n\n色彩由 AI 根据主题自动判断并匹配最合适的高级配色方案，但必须保持统一、克制、耐看、低饱和、高级，不要杂乱高饱和，不要廉价霓虹感，不要塑料数码感。配色可以围绕黑金灰、冷蓝灰、雾白灰、褐红米白、暗铜、旧纸色、深海蓝、暮色紫、银灰等体系自由变化，但必须始终服务主题，并保持海报级审美与整体和谐。\n\n最终要求：第一眼有强烈的主题识别度和轮廓记忆点，第二眼有完整丰富的叙事世界，第三眼仍有细节和余味。轮廓选择必须具有创意和主题匹配度，尽量避免重复、保守、常见的容器套路，优先选择更有象征性、更有空间感、更有设计潜力的轮廓形式。不要普通背景拼接，不要生硬裁切，不要模板化奇幻素材，不要游戏宣传图感，不要过度卡通化，不要过度写实导致失去艺术感，不要形式大于内容。如果合适，可以自然加入低调克制的标题、编号、签名或落款，让它更像收藏版海报设计的一部分，但不要喧宾夺主。",
        "translated": false
      },
      {
        "caseNumber": 29,
        "title": "狮驼岭黑暗神话场景",
        "sourceUrl": "https://x.com/MANISH1027512/status/2045743158860878312",
        "author": "@MANISH1027512",
        "authorUrl": "https://x.com/MANISH1027512",
        "originalPrompt": "中式怪异，黑暗神秘风格融合中式美学，完美细节，多重管线渲染，完美建模。西游记背景，狮驼岭，千妖万怪，坐在左边巨大王座上的大象王重甲妖精，坐在中间巨大王座上的狮王重甲妖精，坐在右边巨大王座上大鹏鸟王重甲妖精。渺小的背对镜头孙悟空肩抗金箍棒步行前进，孙悟空身穿铠甲，近地仰拍镜头，长焦镜头，强烈阴影。极致细节刻画，多次修改，正确透视和主体线条，精致细节",
        "originalTitle": "Lion Camel Ridge Dark Myth Scene",
        "prompt": "中式怪异，黑暗神秘风格融合中式美学，完美细节，多重管线渲染，完美建模。西游记背景，狮驼岭，千妖万怪，坐在左边巨大王座上的大象王重甲妖精，坐在中间巨大王座上的狮王重甲妖精，坐在右边巨大王座上大鹏鸟王重甲妖精。渺小的背对镜头孙悟空肩抗金箍棒步行前进，孙悟空身穿铠甲，近地仰拍镜头，长焦镜头，强烈阴影。极致细节刻画，多次修改，正确透视和主体线条，精致细节",
        "translated": false
      },
      {
        "caseNumber": 30,
        "title": "反恐精英 x 泰拉瑞亚 截图混搭",
        "sourceUrl": "https://x.com/yssrski/status/2046410519595348397",
        "author": "@yssrski",
        "authorUrl": "https://x.com/yssrski",
        "originalPrompt": "counter strike in game screenshot, mixed with Terraria",
        "originalTitle": "Counter-Strike x Terraria Screenshot Mashup",
        "prompt": "游戏截图中的《反恐精英》与泰拉瑞亚混合",
        "translated": true
      },
      {
        "caseNumber": 31,
        "title": "战前日本实验室《我的世界》截图",
        "sourceUrl": "https://x.com/RitaStar1128/status/2046406024303976904",
        "author": "@RitaStar1128",
        "authorUrl": "https://x.com/RitaStar1128",
        "originalPrompt": "戦前日本の怪しげな研究所を探検しているマイクラのスクリーンショット画像を作成して",
        "originalTitle": "Pre-war Japan Lab Minecraft Screenshot",
        "prompt": "创建一张 Minecraft 探索战前日本破旧研究实验室的屏幕截图。",
        "translated": true
      },
      {
        "caseNumber": 32,
        "title": "锻造杰作即时测试",
        "sourceUrl": "https://x.com/MrLarus/status/2046201836525302032",
        "author": "@MrLarus",
        "authorUrl": "https://x.com/MrLarus",
        "originalPrompt": "帮我生成xxxx真迹图片",
        "originalTitle": "Forged Masterpiece Prompt Test",
        "prompt": "帮我生成xxxx真迹图片",
        "translated": false
      },
      {
        "caseNumber": 33,
        "title": "多概念战斗海报套装",
        "sourceUrl": "https://x.com/joshesye/status/2046493442428039212",
        "author": "@joshesye",
        "authorUrl": "https://x.com/joshesye",
        "originalPrompt": "1、生成不知火舞和貂蝉的游戏对战海报图\n2、生成一张K-pop团体时尚专辑封面\n3、请你生成 《斗破苍穹》 的关键人物关系图\n4、帮我截一张上传图片的抖音首页的女网红图",
        "originalTitle": "Multi-Concept Battle Poster Set",
        "prompt": "1、生成不知火舞和貂蝉的游戏对战海报图\n2、生成一张K-pop团体时尚专辑封面\n3、请你生成 《斗破苍穹》 的关键人物关系图\n4、帮我截一张上传图片的抖音首页的女网红图",
        "translated": false
      },
      {
        "caseNumber": 34,
        "title": "Rust 游戏内截图",
        "sourceUrl": "https://x.com/FixlationAI/status/2046272578705068476",
        "author": "@FixlationAI",
        "authorUrl": "https://x.com/FixlationAI",
        "originalPrompt": "an ingame screenshot of rust",
        "originalTitle": "Rust In-Game Screenshot",
        "prompt": "Rust 的游戏内截图",
        "translated": true
      },
      {
        "caseNumber": 35,
        "title": "山姆奥特曼熊自拍",
        "sourceUrl": "https://x.com/JustinGorya/status/2046510831832006970",
        "author": "@JustinGorya",
        "authorUrl": "https://x.com/JustinGorya",
        "originalPrompt": "generate image: Selfie of Sam Altman riding a bear\n\nEdit prompt: Remove the background make it transparent",
        "originalTitle": "Sam Altman Bear Selfie",
        "prompt": "生成图像：山姆·奥尔特曼骑着熊的自拍照\n\n编辑提示：删除背景使其透明",
        "translated": true
      },
      {
        "caseNumber": 36,
        "title": "我们当中真实的截图",
        "sourceUrl": "https://x.com/ReYYYYoking/status/2046502217843376292",
        "author": "@ReYYYYoking",
        "authorUrl": "https://x.com/ReYYYYoking",
        "originalPrompt": "AmongUsの精密な実際のゲーム画像を生成して",
        "originalTitle": "Among Us Realistic Screenshot",
        "prompt": "生成《AmongUs》精确的真实游戏图像",
        "translated": true
      },
      {
        "caseNumber": 37,
        "title": "复古编程博物馆卡通",
        "sourceUrl": "https://x.com/XiaohuiAI666/status/2046515319947354603",
        "author": "@XiaohuiAI666",
        "authorUrl": "https://x.com/XiaohuiAI666",
        "originalPrompt": "在计算机博物馆里,一个程序员在展厅中央,正在演示C语言编程,很多参观者在围观,屏幕上的代码清晰可见。旁边的牌子写着:古法编程,现场表演。2D卡通画风,16:9",
        "originalTitle": "Retro Programming Museum Cartoon",
        "prompt": "在计算机博物馆里,一个程序员在展厅中央,正在演示C语言编程,很多参观者在围观,屏幕上的代码清晰可见。旁边的牌子写着:古法编程,现场表演。2D卡通画风,16:9",
        "translated": false
      },
      {
        "caseNumber": 38,
        "title": "14维投影场景",
        "sourceUrl": "https://x.com/workingclassbud/status/2046506783850815703",
        "author": "@workingclassbud",
        "authorUrl": "https://x.com/workingclassbud",
        "originalPrompt": "A dusk shindig  with multiple fake imagination projections all aligned in the 14th dimensions",
        "originalTitle": "14th-Dimension Projection Scene",
        "prompt": "一场黄昏盛宴，有多个虚假的想象投影，全部排列在第 14 维度",
        "translated": true
      },
      {
        "caseNumber": 39,
        "title": "萨姆·奥特曼棒球广播",
        "sourceUrl": "https://x.com/16kthir0GRXgNqn/status/2046507362266259832",
        "author": "@16kthir0GRXgNqn",
        "authorUrl": "https://x.com/16kthir0GRXgNqn",
        "originalPrompt": "サムアルトマンがメジャーリーガーでバットを構えている。よくあるようなテレビ画面の構図",
        "originalTitle": "Sam Altman Baseball Broadcast",
        "prompt": "萨姆·奥尔特曼是一名拥有球棒的大联盟球员。常见电视画面构成",
        "translated": true
      },
      {
        "caseNumber": 40,
        "title": "根据视频内容和当前帧，使用 GPT 生成 YouT...",
        "sourceUrl": "https://x.com/chatcutapp/status/2047228386117128475",
        "author": "@chatcutapp",
        "authorUrl": "https://x.com/chatcutapp",
        "originalPrompt": "Based on the video content and this current frame, use GPT to generate a YouTube thumbnail that fits the video. You can reference the style of the image I gave you, but replace the logo on the right side of AE with theChatCut logo. I'll attach the logo for you.",
        "originalTitle": "Based on the video content and this current frame, use GPT to generate a YouT...",
        "prompt": "根据视频内容和当前帧，使用 GPT 生成适合视频的 YouTube 缩略图。你可以参考我给你的图片的风格，但是将AE右侧的标志替换为ChatCut标志。我会为您附上徽标。",
        "translated": true
      },
      {
        "caseNumber": 41,
        "title": "2020年最重大事件",
        "sourceUrl": "https://x.com/Rufus87078959/status/2047211900769878234",
        "author": "@Rufus87078959",
        "authorUrl": "https://x.com/Rufus87078959",
        "originalPrompt": "Generate an image of the most significant event of 2020",
        "originalTitle": "2020年最重大事件",
        "prompt": "生成 2020 年最重要事件的图像",
        "translated": true
      },
      {
        "caseNumber": 42,
        "title": "编辑此图像，使总金额更改为 244.5 泰铢。您可以更改...",
        "sourceUrl": "https://x.com/elliscrosby/status/2047211507596071235",
        "author": "@elliscrosby",
        "authorUrl": "https://x.com/elliscrosby",
        "originalPrompt": "Edit this image so that total amount changes to 244.5 baht. You can change the quantity of each of the stacks of coins until we hit the target total.",
        "originalTitle": "Edit this image so that total amount changes to 244.5 baht. You can change th...",
        "prompt": "编辑此图像，使总金额更改为 244.5 泰铢。您可以更改每堆硬币的数量，直到达到目标总数。",
        "translated": true
      },
      {
        "caseNumber": 43,
        "title": "2001年最重大事件",
        "sourceUrl": "https://x.com/Rufus87078959/status/2047210051216011682",
        "author": "@Rufus87078959",
        "authorUrl": "https://x.com/Rufus87078959",
        "originalPrompt": "Generate an image of the most significant event of 2001",
        "originalTitle": "2001年最重大事件",
        "prompt": "生成 2001 年最重要事件的图像",
        "translated": true
      }
    ]
  }
];

export const awesomePromptSummary = {
  sectionCount: awesomePromptSections.length,
  promptCount: awesomePromptSections.reduce((count, section) => count + section.items.length, 0),
  translatedCount: awesomePromptSections.reduce(
    (count, section) => count + section.items.filter((item) => item.translated).length,
    0,
  ),
  sourceReadmeUrl: `https://raw.githubusercontent.com/EvoLinkAI/awesome-gpt-image-2-prompts/main/README_zh-CN.md`,
};
