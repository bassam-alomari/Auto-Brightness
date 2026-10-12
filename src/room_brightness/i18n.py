"""Complete English/Arabic UI catalog. Device names remain as supplied by Windows."""

from pathlib import Path
import json

STRINGS = {
    "vision_hold": ("Keeping your screen readable", "عم نحافظ على وضوح الشاشة"),
    "protected_help": (
        "A darker image will not lower brightness below your starting comfort level.",
        "الصورة الغامقة ما رح تنزل السطوع تحت مستوى البداية المريح.",
    ),
    "scene_changed_help": (
        "The camera view changed. Brightness is held; stop and start to learn the new view.",
        "المشهد قدام الكاميرا تغيّر. ثبّتنا السطوع؛ وقف وشغّل لتعلّم المشهد الجديد.",
    ),
    "protect_dim": (
        "Safe dimming: confirm darkening before reducing brightness",
        "تعتيم آمن: تأكيد تغيّر الضوء قبل خفض السطوع",
    ),
    "glass_mode": ("Liquid Glass", "السائل الزجاجي"),
    "curve": ("Brightness curve", "منحنى السطوع"),
    "curve_help": (
        "Maps changes to your full comfort range. Stronger response reaches maximum sooner; camera auto-exposure can still hide changes.",
        "بيربط تغيّر الضوء بكامل حدود السطوع. الاستجابة الأقوى بتوصل للأعلى أسرع؛ التعريض التلقائي ممكن يضل يخفي تغيّر الضوء.",
    ),
    "gentle": ("Gentle", "هادئ"),
    "balanced": ("Balanced", "متوازن"),
    "responsive": ("Responsive", "قوي"),
    "manual_set": ("Apply manual brightness", "تطبيق السطوع اليدوي"),
    "manual_tip": (
        "Stop automatic mode before applying a manual value.",
        "وقف الوضع التلقائي قبل تطبيق قيمة يدوية.",
    ),
    "live_meter": ("Last camera check", "آخر فحص للكاميرا"),
    "meter_values": (
        "Light: {level}/255 · Quality: {quality} · Target: {target}%",
        "الضوء: {level}/٢٥٥ · الجودة: {quality} · الهدف: {target}٪",
    ),
    "minimize_tray": ("Minimize to the system tray", "التصغير جنب الساعة"),
    "close_tray": ("Close button hides to tray", "زر الإغلاق يخفي البرنامج جنب الساعة"),
    "show": ("Show", "إظهار"),
    "exit": ("Exit", "خروج"),
    "tray_missing": (
        "Run Setup.cmd to install tray support. The window stays open.",
        "شغّل Setup.cmd لتثبيت دعم أيقونة الساعة. النافذة رح تضل مفتوحة.",
    ),
    "about_short": (
        "Auto Brightness · Local camera estimate, no saved photos or uploads.",
        "سطوع الغرفة · تقدير محلي بالكاميرا، بدون حفظ صور أو رفعها.",
    ),
    "check_interval": ("Check frequency", "وقت الفحص"),
    "interval_help": (
        "Seconds between camera checks (5–600). Shorter checks use more battery. Brightness fades between checks.",
        "المدة بالثواني بين فحوصات الكاميرا (٥–٦٠٠). الفحص المتكرر بصرف بطارية أكثر. السطوع بيتغيّر تدريجيًا بين الفحوصات.",
    ),
    "on_ac": ("On charger · seconds", "على الشاحن · ثواني"),
    "on_battery": ("On battery · seconds", "على البطارية · ثواني"),
    "app": ("Auto Brightness", "الإضاءة التلقائية"),
    "title": ("Comfortable brightness, automatically", "سطوع مريح، بشكل تلقائي"),
    "subtitle": (
        "Set it up once. Your screen follows the room lighting.",
        "اضبطه مرة واحدة، وخلي سطوع الشاشة يتغيّر مع إضاءة الغرفة.",
    ),
    "camera": ("Your camera", "الكاميرا"),
    "camera_help": (
        "Choose the laptop camera. Close video-call apps before measuring.",
        "اختار كاميرا اللابتوب. سكّر تطبيقات مكالمات الفيديو قبل القياس.",
    ),
    "refresh": ("Refresh", "تحديث القائمة"),
    "finding": ("Finding cameras…", "جاري البحث عن الكاميرات…"),
    "no_camera": ("No camera found", "ما لقينا كاميرا"),
    "no_camera_help": (
        "Connect or uncover your camera, allow desktop camera access in Windows, then refresh.",
        "وصل الكاميرا أو افتح غطاءها، واسمح لتطبيقات سطح المكتب تستخدمها من إعدادات Windows، وبعدها حدّث القائمة.",
    ),
    "limits": ("Your comfort range", "حدود السطوع المريحة إلك"),
    "limits_help": (
        "Brightness stays near this range. Slide to adjust.",
        "اختار أقل وأعلى سطوع مريح إلك باستخدام المؤشر.",
    ),
    "minimum": ("In a dim room", "بالغرفة الخافتة"),
    "maximum": ("In a bright room", "بالغرفة المضوية"),
    "restore": ("Restore previous brightness when stopped", "رجّع السطوع السابق عند الإيقاف"),
    "setup": ("A simple setup", "إعداد بخطوات بسيطة"),
    "step1": ("1   Check screen control", "١   افحص التحكم بالشاشة"),
    "step1_help": (
        "A small brightness change, then back to the original level.",
        "رح نغيّر السطوع شوي، وبعدها نرجّعه مثل ما كان.",
    ),
    "step2": ("2   Capture dim lighting", "٢   سجّل إضاءة خافتة"),
    "step2_help": (
        "Dim the room lights and keep your usual sitting position.",
        "خفّف ضو الغرفة وخليك بمكانك المعتاد قدام الشاشة.",
    ),
    "step3": ("3   Capture bright lighting", "٣   سجّل إضاءة قوية"),
    "step3_help": (
        "Turn on more room lights. Keep the camera in the same position.",
        "زيد ضو الغرفة، وخلي الكاميرا ومكانك مثل ما كانوا.",
    ),
    "start": ("Start automatic brightness", "شغّل السطوع التلقائي"),
    "stop": ("Stop", "إيقاف"),
    "ready": ("Ready when you are", "جاهز لما تكون جاهز"),
    "welcome": (
        "Start by checking screen control, then capture both lighting conditions.",
        "ابدأ بفحص الشاشة، وبعدها سجّل الإضاءة الخافتة والقوية.",
    ),
    "testing": ("Checking your screen…", "جاري فحص الشاشة…"),
    "test_help": (
        "The brightness will change briefly and return to its original level.",
        "السطوع رح يتغيّر لوقت قصير، وبعدها يرجع للقيمة الأصلية.",
    ),
    "verified": ("Screen control works", "التحكم بالشاشة شغّال"),
    "verified_help": (
        "Original brightness restored to {value}%. Now capture dim and bright room lighting.",
        "رجّعنا السطوع الأصلي إلى {value}٪. هسّا سجّل ضو الغرفة الخافت والقوي.",
    ),
    "measuring": ("Measuring the room light…", "جاري قياس ضو الغرفة…"),
    "measure_help": (
        "Keep still for a few seconds. The camera closes after the measurement.",
        "خليك بمكانك لثواني. الكاميرا رح تسكّر بعد القياس.",
    ),
    "captured": ("Light reading saved", "حفظنا قياس الإضاءة"),
    "capture_help": (
        "Reading: {value}. Capture the other lighting condition to continue.",
        "القياس: {value}. سجّل الإضاءة الثانية عشان تكمل.",
    ),
    "cal_ready": ("Calibration is ready", "المعايرة جاهزة"),
    "cal_ready_help": (
        "Both lighting readings are saved. You can start automatic brightness.",
        "حفظنا قياس الإضاءة الخافتة والقوية. بتقدر تشغّل السطوع التلقائي.",
    ),
    "dim_value": ("Dim: {value}", "الخافتة: {value}"),
    "bright_value": ("Bright: {value}", "القوية: {value}"),
    "not_saved": ("Not captured", "لسه ما تسجّلت"),
    "running": ("Automatic brightness is on", "السطوع التلقائي شغّال"),
    "running_help": (
        "Current brightness: {brightness}%  ·  Room light reading: {light}",
        "السطوع الحالي: {brightness}٪  •  قياس ضو الغرفة: {light}",
    ),
    "stopping": ("Stopping safely…", "جاري الإيقاف…"),
    "stopping_help": (
        "Closing the camera and restoring brightness if enabled.",
        "بنسكّر الكاميرا وبنرجّع السطوع السابق إذا الخيار مفعّل.",
    ),
    "stopped": ("Automatic brightness is off", "السطوع التلقائي متوقف"),
    "stopped_help": (
        "Camera closed. Your settings are saved for next time.",
        "الكاميرا مسكّرة. إعداداتك محفوظة للمرة الجاي.",
    ),
    "restored_help": (
        "Camera closed. Brightness restored to {value}%.",
        "الكاميرا مسكّرة. رجّعنا السطوع إلى {value}٪.",
    ),
    "privacy": ("Private by design", "خصوصيتك محفوظة"),
    "privacy_help": (
        "No photos saved or uploaded. Check frequency is adjustable in Settings.",
        "ما بنحفظ صور ولا بنرسلها. وقت الفحص قابل للتعديل من الإعدادات.",
    ),
    "saved": ("Preferences save automatically", "الإعدادات بتنحفظ تلقائيًا"),
    "details": ("Technical details", "تفاصيل تقنية"),
    "error": ("Something needs your attention", "في شغلة بدها انتباهك"),
    "error_test": (
        "We could not verify screen control. Use the keyboard brightness keys and try again.",
        "ما قدرنا نتأكد من التحكم بالشاشة. جرّب أزرار السطوع بالكيبورد، وبعدها أعد الفحص.",
    ),
    "error_camera": (
        "We could not read the camera. Close video apps and check Windows camera permissions.",
        "ما قدرنا نقرأ الكاميرا. سكّر تطبيقات الفيديو وتأكد من صلاحيات الكاميرا في Windows.",
    ),
    "error_restore": (
        "We could not confirm brightness restoration. Set it manually with your keyboard.",
        "ما قدرنا نتأكد إن السطوع رجع. اضبطه يدويًا بأزرار الكيبورد.",
    ),
    "error_control": (
        "Automatic brightness stopped because screen control could not be confirmed.",
        "وقفنا السطوع التلقائي لأنه ما قدرنا نتأكد من التحكم بالشاشة.",
    ),
    "error_settings": (
        "Your preferences could not be saved. Check that your user settings folder is writable.",
        "ما قدرنا نحفظ الإعدادات. تأكد إن مجلد إعدادات حسابك بيسمح بالكتابة.",
    ),
    "need_check": ("Check the screen first", "افحص الشاشة أولًا"),
    "need_check_help": (
        "Select “Check screen control” before starting.",
        "اضغط «افحص التحكم بالشاشة» قبل التشغيل.",
    ),
    "need_both": ("Capture both lighting conditions", "سجّل الإضاءتين"),
    "need_both_help": (
        "First dim the room lights and capture. Then turn on more lights and capture again.",
        "خفّف ضو الغرفة وسجّل الخافتة، وبعدها زيد الضو وسجّل القوية.",
    ),
    "too_similar": ("The two readings are too similar", "القراءتين متقاربات"),
    "too_similar_help": (
        "Dim: {dark}, bright: {bright}. Change the room lighting more and capture again. Camera auto-exposure may limit this method.",
        "الخافتة: {dark}، القوية: {bright}. غيّر ضو الغرفة أكثر وأعد القياس. التعريض التلقائي بالكاميرا ممكن يحدّ من دقة هالطريقة.",
    ),
    "changed": ("Camera changed", "تغيّرت الكاميرا"),
    "changed_help": (
        "Capture both lighting conditions again for this camera.",
        "سجّل الإضاءة الخافتة والقوية من جديد لهالكاميرا.",
    ),
    "already": (
        "The app is already running. Use its open window.",
        "البرنامج شغّال أصلًا. استخدم النافذة المفتوحة.",
    ),
    "cannot_start": ("Cannot open the app", "ما قدرنا نفتح البرنامج"),
    "select_camera": ("Select a camera", "اختار كاميرا"),
}


STRINGS.update(
    {
        "language": ("Language", "اللغة"),
        "system": ("System", "حسب النظام"),
        "appearance": ("Appearance", "المظهر"),
        "light_mode": ("Light", "فاتح"),
        "dark_mode": ("Dark", "داكن"),
        "settings": ("Settings", "الإعدادات"),
        "home": ("Overview", "الرئيسية"),
        "simple_title": ("A little more comfortable.", "راحة أكثر، بكل بساطة."),
        "simple_subtitle": (
            "Your screen adapts to the room. You stay in control.",
            "شاشتك بتتكيّف مع ضو الغرفة، والتحكم بضل بإيدك.",
        ),
        "automatic": ("Automatic brightness", "السطوع التلقائي"),
        "screen_level": ("Screen brightness", "سطوع الشاشة"),
        "one_click": (
            "Choose your camera and press Start. No manual light calibration.",
            "اختار الكاميرا واضغط تشغيل. ما بدك تطفي الضو وتشغّله للمعايرة.",
        ),
        "start_simple": ("Start", "تشغيل"),
        "auto_ready": ("Ready to start", "جاهز للتشغيل"),
        "auto_welcome": (
            "We check screen control and learn the current room lighting when you start.",
            "لما تشغّل البرنامج، بنفحص التحكم بالشاشة وبنتعرف على إضاءة الغرفة الحالية.",
        ),
        "learning": ("Getting to know your room", "بنتعرف على ضو الغرفة"),
        "learning_help": (
            "Keep your normal sitting position for a few seconds. No light changes needed.",
            "خليك بمكانك المعتاد لثواني. ما بدك تغيّر ضو الغرفة.",
        ),
        "watching": ("Adapting gently", "بنتكيّف مع الإضاءة بهدوء"),
        "watching_help": (
            "Brightness changes gradually when room lighting changes. You can adjust it in Windows anytime.",
            "السطوع بتغيّر تدريجيًا مع ضو الغرفة. بتقدر تعدّله من Windows بأي وقت.",
        ),
        "manual_hold": ("Your brightness choice comes first", "اختيارك للسطوع إله الأولوية"),
        "manual_help": (
            "Keeping your chosen brightness for {seconds}s, then learning a fresh reference.",
            "بنثبت السطوع اللي اخترته لمدة {seconds} ثانية، وبعدها بنتعرف على الإضاءة من جديد.",
        ),
        "unstable": ("Keeping brightness steady", "بنحافظ على السطوع الحالي"),
        "unstable_help": (
            "The camera reading is unclear. We will wait for a stable measurement.",
            "قراءة الكاميرا مش واضحة. بنستنى قياس ثابت قبل أي تغيير.",
        ),
        "personalize": ("Make it yours", "اضبطه على راحتك"),
        "personalize_help": (
            "Language and appearance follow Windows unless you choose otherwise.",
            "اللغة والمظهر بتبعوا Windows، إلا إذا اخترت غير هيك.",
        ),
        "startup": ("Open when I sign in to Windows", "افتح البرنامج لما أدخل على Windows"),
        "startup_help": (
            "Opens the window after sign-in. The camera starts only when you press Start.",
            "بفتح النافذة بعد تسجيل الدخول. الكاميرا بتشتغل بس لما تضغط تشغيل.",
        ),
        "startup_error": (
            "Could not update the startup option. See technical details.",
            "ما قدرنا نحدّث خيار بدء التشغيل. شوف التفاصيل التقنية.",
        ),
        "restore_new": (
            "Restore my previous brightness when stopped",
            "رجّع السطوع اللي اخترته عند الإيقاف",
        ),
        "meter_note": (
            "A camera-based estimate, not a dedicated light sensor.",
            "تقدير باستخدام الكاميرا، مش حساس ضوء مخصص.",
        ),
        "manual_zero": (
            "Brightness is below 10%. Keeping your choice; raise it to resume adaptation.",
            "السطوع أقل من ١٠٪. بنحترم اختيارك؛ ارفعه عشان يرجع التكيّف التلقائي.",
        ),
    }
)


LANGUAGES = {
    "auto": "System",
    "en": "English",
    "ar": "العربية",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "pt": "Português",
    "zh": "中文",
    "hi": "हिन्दी",
}


CATALOGS = json.loads((Path(__file__).with_name("languages.json")).read_text(encoding="utf-8"))


ARABIC_STYLES = json.loads(
    (Path(__file__).with_name("arabic_styles.json")).read_text(encoding="utf-8")
)


def literal(language, english, arabic=None, dialect="msa"):
    if language == "ar":
        value = ARABIC_STYLES.get(dialect, ARABIC_STYLES["msa"]).get(english, arabic or english)
        if "Windows" in value:
            value = "\u200f" + value.replace("Windows", "ويندوز")
        return value.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
    for key, pair in STRINGS.items():
        if pair[0] == english:
            return CATALOGS.get(language, {}).get(
                key, CATALOGS.get(language, {}).get("@" + english, english)
            )
    return CATALOGS.get(language, {}).get("@" + english, english)


def text(language, key, _dialect="msa", **values):
    english, arabic = STRINGS[key]
    return literal(language, english, arabic, _dialect).format(**values)
