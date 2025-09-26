# chinese_font_detector.py
from matplotlib.font_manager import FontProperties, findSystemFonts
import matplotlib.font_manager as fm

def get_available_chinese_fonts():
    """获取系统中所有可用的中文字体"""
    common_chinese_fonts = [
        # Windows
        "SimHei", "Microsoft YaHei", "SimSun", "NSimSun", "FangSong", "KaiTi",
        # Linux
        "WenQuanYi Micro Hei", "WenQuanYi Zen Hei",
        # macOS
        "PingFang SC", "PingFang TC", "Heiti SC", "STSong", "STHeiti", "STKaiti"
    ]
    available_fonts = []
    for font_name in common_chinese_fonts:
        try:
            fp = FontProperties(family=font_name)
            if any(font_name.lower() in f.lower() for f in findSystemFonts()):
                available_fonts.append(font_name)
        except:
            continue
    if not available_fonts:
        system_fonts = findSystemFonts()
        chinese_keywords = ['hei', 'song', 'kai', 'fang', '微软', '黑体', '宋体', '苹方']
        for font_path in system_fonts:
            try:
                font_name = fm.get_font(font_path).family_name
                if any(keyword in font_name.lower() for keyword in chinese_keywords):
                    if font_name not in available_fonts:
                        available_fonts.append(font_name)
            except:
                continue
    return list(set(available_fonts))

def get_best_chinese_font():
    """获取系统中最优的可用中文字体"""
    available_fonts = get_available_chinese_fonts()
    preferred_order = ["Microsoft YaHei", "SimHei", "PingFang SC", "WenQuanYi Zen Hei"]
    for font in preferred_order:
        if font in available_fonts:
            return font
    return available_fonts[0] if available_fonts else "DejaVu Sans"

def print_available_chinese_fonts():
    """打印系统中可用的中文字体列表"""
    fonts = get_available_chinese_fonts()
    if not fonts:
        print("未检测到可用的中文字体")
        return
    print(f"检测到 {len(fonts)} 种可用的中文字体:")
    for i, font in enumerate(fonts, 1):
        print(f"{i}. {font}")

if __name__ == "__main__":
    print_available_chinese_fonts()
    print(f"\n推荐使用的中文字体：{get_best_chinese_font()}")