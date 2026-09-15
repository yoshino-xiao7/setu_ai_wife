from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHARACTERS_PATH = ROOT / "config" / "characters.json"
WAI = "waiIllustriousSDXL_v170.safetensors"
PREVIEW = "https://www.downloadmost.com/NoobAI-XL/danbooru-character/preview/{slug}.jpg"

NATIVE = [
    ("hu_tao", "胡桃", "原神", "hu tao (genshin impact), genshin impact", "1girl, red eyes, brown hair, long hair, twintails, flower-shaped pupils, symbol-shaped pupils, hat, chinese clothes, plum blossoms, ghost", "hu_tao"),
    ("ganyu", "甘雨", "原神", "ganyu (genshin impact), genshin impact", "1girl, goat horns, ahoge, purple eyes, blue hair, long hair, lock necklace, detached sleeves, bell, medium breasts", "ganyu"),
    ("keqing", "刻晴", "原神", "keqing (genshin impact), genshin impact", "1girl, purple eyes, purple hair, cone hair bun, long hair, twintails, hair ornament, medium breasts, gloves", "keqing"),
    ("furina", "芙宁娜", "原神", "furina (genshin impact), genshin impact", "1girl, heterochromia, blue eyes, white hair, streaked hair, blue hair, drop-shaped pupils, top hat, blue jacket, shorts", "furina"),
    ("nahida", "纳西妲", "原神", "nahida (genshin impact), genshin impact", "1girl, green eyes, white hair, green hair, gradient hair, pointy ears, side ponytail, white dress, hair ornament", "nahida"),
    ("arlecchino", "阿蕾奇诺", "原神", "arlecchino (genshin impact), genshin impact", "1girl, red eyes, black hair, two-tone hair, white hair, x-shaped pupils, symbol-shaped pupils, short hair, black nails, sharp eyes", "arlecchino"),
    ("mavuika", "玛薇卡", "原神", "mavuika (genshin impact), genshin impact", "1girl, red eyes, orange hair, very long hair, sunglasses, large breasts, bike shorts, jacket", "mavuika"),
    ("shenhe", "申鹤", "原神", "shenhe (genshin impact), genshin impact", "1girl, pale skin, blue eyes, white hair, very long hair, braided ponytail, hair over one eye, large breasts, bodysuit", "shenhe"),
    ("yelan", "夜兰", "原神", "yelan (genshin impact), genshin impact", "1girl, green eyes, black hair, multicolored hair, blue hair, aqua hair, long hair, large breasts, bodysuit, dice", "yelan"),
    ("nilou", "妮露", "原神", "nilou (genshin impact), genshin impact", "1girl, aqua eyes, red hair, long hair, veil, harem outfit, jewelry, midriff, dancer", "nilou"),
    ("yoimiya", "宵宫", "原神", "yoimiya (genshin impact), genshin impact", "1girl, red eyes, yellow eyes, blonde hair, long hair, ponytail, hair ornament, bandage, orange kimono", "yoimiya"),
    ("eula", "优菈", "原神", "eula (genshin impact), genshin impact", "1girl, yellow eyes, light blue hair, medium hair, medium breasts, cape, leotard, thighs", "eula"),
    ("changli", "长离", "鸣潮", "changli (wuthering waves), wuthering waves", "1girl, red eyes, white hair, pink hair, gradient hair, mole under eye, long hair, china dress, phoenix", "changli_(wuthering_waves)"),
    ("jinhsi", "今汐", "鸣潮", "jinhsi (wuthering waves), wuthering waves", "1girl, yellow eyes, white hair, long hair, white dress, horns, jewelry", "jinhsi_(wuthering_waves)"),
    ("camellya", "椿", "鸣潮", "camellya (wuthering waves), wuthering waves", "1girl, red eyes, black hair, pink hair, twintails, flower, black dress, hair flower", "camellya_(wuthering_waves)"),
    ("shorekeeper", "守岸人", "鸣潮", "shorekeeper (wuthering waves), wuthering waves", "1girl, purple eyes, white hair, star-shaped pupils, long hair, white dress, ethereal", "shorekeeper_(wuthering_waves)"),
    ("carlotta", "卡洛塔", "鸣潮", "carlotta (wuthering waves), wuthering waves", "1girl, pink eyes, white hair, long hair, hair ornament, dress, elegant", "carlotta_(wuthering_waves)"),
    ("yinlin", "吟霖", "鸣潮", "yinlin (wuthering waves), wuthering waves", "1girl, red eyes, black hair, purple hair, pointy ears, long hair, chinese clothes, electro", "yinlin_(wuthering_waves)"),
    ("encore", "恩核", "鸣潮", "encore (wuthering waves), wuthering waves", "1girl, purple eyes, red hair, long hair, twintails, wooly, cute", "encore_(wuthering_waves)"),
    ("ellen_joe", "艾莲", "绝区零", "ellen joe, zenless zone zero", "1girl, shark girl, shark tail, red eyes, black hair, colored inner hair, red hair, maid, black dress, red necktie, yellow eyes", "ellen_joe"),
    ("zhu_yuan", "朱鸢", "绝区零", "zhu yuan, zenless zone zero", "1girl, orange eyes, black hair, long hair, ponytail, police uniform, large breasts, holster", "zhu_yuan"),
    ("jane_doe", "简·杜", "绝区零", "jane doe (zenless zone zero), zenless zone zero", "1girl, mouse girl, mouse ears, mouse tail, black eyes, black hair, pantyhose, jacket, midriff", "jane_doe_(zenless_zone_zero)"),
    ("burnice", "柏妮思", "绝区零", "burnice white, zenless zone zero", "1girl, green eyes, blonde hair, long hair, twintails, black shorts, flame, cocktail shaker", "burnice_white"),
    ("yanagi", "月城柳", "绝区零", "tsukishiro yanagi, zenless zone zero", "1girl, glasses, green eyes, green hair, long hair, ponytail, suit, pantyhose", "tsukishiro_yanagi"),
    ("miyabi", "星见雅", "绝区零", "hoshimi miyabi, zenless zone zero", "1girl, fox girl, fox ears, fox tail, yellow eyes, black hair, long hair, katana, school uniform", "hoshimi_miyabi"),
    ("kafka", "卡芙卡", "崩坏：星穹铁道", "kafka (honkai: star rail), honkai: star rail", "1girl, purple eyes, purple hair, sunglasses, spider web print, jacket, pantyhose, large breasts", "kafka"),
    ("firefly", "流萤", "崩坏：星穹铁道", "firefly (honkai: star rail), honkai: star rail", "1girl, cyan eyes, grey hair, two-tone hair, white hair, hair between eyes, trailblazer", "firefly_(honkai:_star_rail)"),
    ("sparkle", "花火", "崩坏：星穹铁道", "sparkle (honkai: star rail), honkai: star rail", "1girl, pink eyes, black hair, red hair, twintails, fox mask, hair ornament, kimono", "sparkle_(honkai:_star_rail)"),
    ("robin", "知更鸟", "崩坏：星穹铁道", "robin (honkai: star rail), honkai: star rail", "1girl, aqua eyes, hair between eyes, teal hair, halo, white dress, wings, idol", "robin_(honkai:_star_rail)"),
    ("acheron", "黄泉", "崩坏：星穹铁道", "acheron (honkai: star rail), honkai: star rail", "1girl, purple eyes, black hair, streaked hair, purple hair, very long hair, lightning, coat", "acheron_(honkai:_star_rail)"),
    ("black_swan", "黑天鹅", "崩坏：星穹铁道", "black swan (honkai: star rail), honkai: star rail", "1girl, aqua eyes, hair between eyes, grey hair, purple hair, veil, large breasts, bare shoulders", "black_swan_(honkai:_star_rail)"),
    ("silver_wolf", "银狼", "崩坏：星穹铁道", "silver wolf (honkai: star rail), honkai: star rail", "1girl, heterochromia, grey hair, punchy bangs, jacket, shorts, crossover, holographic", "silver_wolf_(honkai:_star_rail)"),
    ("ruan_mei", "阮·梅", "崩坏：星穹铁道", "ruan mei (honkai: star rail), honkai: star rail", "1girl, aqua eyes, teal hair, hair bun, chinese clothes, hair ornament, elegant", "ruan_mei"),
]


def main() -> None:
    payload = json.loads(CHARACTERS_PATH.read_text(encoding="utf-8"))
    characters = payload["characters"]
    existing = {item["id"] for item in characters}
    for char_id, name, category, trigger, default_positive, slug in NATIVE:
        if char_id in existing:
            continue
        characters.append(
            {
                "id": char_id,
                "name": name,
                "category": category,
                "category_type": "游戏角色",
                "lora_name": "",
                "lora_strength": 0.8,
                "trigger_words": trigger,
                "default_positive": default_positive,
                "style_tags": "anime style, detailed eyes, high quality",
                "preview_image": PREVIEW.format(slug=slug),
                "recommended_checkpoint": WAI,
                "notes": f"{category}角色{name}。WAI/Anima 原生 Danbooru 标签即可还原，无需 LoRA。",
            }
        )
    payload["characters"] = characters
    CHARACTERS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"characters={len(characters)}")


if __name__ == "__main__":
    main()
