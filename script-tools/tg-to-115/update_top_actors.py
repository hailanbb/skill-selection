#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智能获取并更新排名前 100+ 热门女优白名单 (自动补齐中/日/繁/英多语言别名并与现有 actors.json 无损合并)"""

import os
import sys
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACTORS_JSON = os.path.join(BASE_DIR, "actors.json")
ACTORS_TXT = os.path.join(BASE_DIR, "actors.txt")

# 权威精选 Top 110+ 热门女优多语言全套别名库 (覆盖现役顶流、历年 FANZA 榜单与经典殿堂级)
PRESET_TOP_ACTORS = {
    "河北彩花": ["河北彩花", "河北彩伽", "かわきたさいか", "Saika Kawakita"],
    "三上悠亚": ["三上悠亚", "三上悠亞", "三上悠亜", "みかみゆあ", "鬼头桃菜", "Yua Mikami"],
    "深田咏美": ["深田咏美", "深田詠美", "深田えいみ", "天海心", "ふかだえいみ", "Eimi Fukada"],
    "相泽南": ["相泽南", "相澤南", "相沢みなみ", "あいざわみなみ", "Minami Aizawa"],
    "安斋拉拉": ["安斋拉拉", "安齋拉拉", "安斎らら", "RION", "宇都宫紫苑", "宇都宮しおん", "Rara Anzai"],
    "新有菜": ["新有菜", "新ありな", "桥本有菜", "橋本ありな", "はしもとありな", "Arina Hashimoto"],
    "楪可怜": ["楪可怜", "楪カレン", "枫可怜", "楓カレン", "かえでかれん", "Karen Yuzuriha"],
    "铃村爱里": ["铃村爱里", "鈴村愛里", "鈴村あいり", "すずむらあいり", "Airi Suzumura"],
    "高桥圣子": ["高桥圣子", "高橋聖子", "高橋しょう子", "唯川めぐみ", "たかはししょうこ", "Shoko Takahashi"],
    "樱空桃": ["樱空桃", "櫻空桃", "桜空もも", "さくらもも", "Momo Sakura"],
    "桃乃木香奈": ["桃乃木香奈", "桃乃木かな", "もものぎかな", "Kana Momonogi"],
    "明日花绮罗": ["明日花绮罗", "明日花綺羅", "明日花キララ", "あすかきらら", "Kirara Asuka"],
    "天使萌": ["天使萌", "天使もえ", "あまつかもえ", "Moe Amatsuka"],
    "葵司": ["葵司", "葵つかさ", "あおいつかさ", "Tsukasa Aoi"],
    "山岸逢花": ["山岸逢花", "山岸あいか", "やまぎしあいか", "Aika Yamagishi"],
    "明里䌷": ["明里䌷", "明里紬", "明里つむぎ", "あかりつむぎ", "Tsumugi Akari"],
    "本庄铃": ["本庄铃", "本莊鈴", "本庄鈴", "ほんじょうすず", "Suzu Honjo"],
    "本乡爱": ["本乡爱", "本鄉愛", "二阶堂梦", "二階堂夢", "本郷愛", "にかいどうゆめ", "Ai Hongo"],
    "八挂海": ["八挂海", "八掛海", "八掛うみ", "やつがけうみ", "Umi Yatsugake"],
    "凉森玲梦": ["凉森玲梦", "涼森玲夢", "涼森れむ", "すずもりれむ", "Remu Suzumori"],
    "七泽美亚": ["七泽美亚", "七澤美亞", "七沢みあ", "ななさわみあ", "Mia Nanasawa"],
    "小仓由菜": ["小仓由菜", "小倉由菜", "おぐらゆな", "Yuna Ogura"],
    "伊藤舞雪": ["伊藤舞雪", "いとうまゆき", "Mayuki Ito"],
    "筱田优": ["筱田优", "篠田優", "篠田ゆう", "しのだゆう", "Yu Shinoda"],
    "吉高宁宁": ["吉高宁宁", "吉高寧寧", "吉高寧々", "よしたかねね", "Nene Yoshitaka"],
    "宫下玲奈": ["宫下玲奈", "宮下玲奈", "みやしたれいな", "Reina Miyashita"],
    "宫岛芽衣": ["宫岛芽衣", "宮島芽衣", "宮島めい", "みやじまめい", "Mei Miyajima"],
    "七森莉莉": ["七森莉莉", "七ツ森りり", "七ツ森莉莉", "ななつもりりり", "Riri Nanatsumori"],
    "石川澪": ["石川澪", "石川みお", "いしかわみお", "Mio Ishikawa"],
    "永野一香": ["永野一香", "永野いち夏", "ながのいちか", "Ichika Nagano"],
    "松本一香": ["松本一香", "松本いちか", "まつもといちか", "Ichika Matsumoto"],
    "小野六花": ["小野六花", "おのりっか", "Rikka Ono"],
    "唯井真寻": ["唯井真寻", "唯井真尋", "唯井まひろ", "ただいまひろ", "Mahiro Tadai"],
    "岬奈奈美": ["岬奈奈美", "岬ななみ", "みさきななみ", "Nanami Misaki"],
    "木下日葵": ["木下日葵", "木下ひまり", "きのしたひまり", "Himari Kinoshita"],
    "栗山莉绪": ["栗山莉绪", "栗山莉緒", "くりやまりお", "Rio Kuriyama"],
    "仓木华": ["仓木华", "倉木華", "倉木しおり", "くらきはな", "Hana Kuraki"],
    "金松季步": ["金松季步", "金松季歩", "かねまつきほ", "Kiho Kanematsu"],
    "恋渊桃奈": ["恋渊桃奈", "恋渕桃奈", "恋渕ももな", "こいぶちももな", "Momona Koibuchi"],
    "渚恋生": ["渚恋生", "渚こい", "なぎさこい", "Koi Nagisa"],
    "西宫梦": ["西宫梦", "西宮夢", "にしみやゆめ", "Yume Nishimiya"],
    "美谷朱里": ["美谷朱里", "みたにあかり", "Akari Mitani"],
    "香水纯": ["香水纯", "香水純", "香水じゅん", "かすみじゅん", "Jun Kasumi"],
    "野野浦暖": ["野野浦暖", "野々浦暖", "ののうらのん", "Non Nonoura"],
    "田中七海": ["田中七海", "田中なな実", "たなかななみ", "Nanami Tanaka"],
    "白峰美羽": ["白峰美羽", "白峰ミウ", "しらみねみう", "Miu Shiramine"],
    "七濑爱丽丝": ["七濑爱丽丝", "七瀨愛麗絲", "七瀬アリス", "ななせありす", "Alice Nanase"],
    "浅野心": ["浅野心", "淺野心", "浅野こころ", "あさのこころ", "Kokoro Asano"],
    "户田真琴": ["户田真琴", "戸田真琴", "とだまこと", "Makoto Toda"],
    "波多野结衣": ["波多野结衣", "波多野結衣", "はたのゆい", "Yui Hatano"],
    "上原亚衣": ["上原亚衣", "上原亜衣", "うえはらあい", "Ai Uehara"],
    "大槻响": ["大槻响", "大槻響", "大槻ひびき", "おおつきひびき", "Hibiki Otsuki"],
    "希岛爱理": ["希岛爱理", "希島愛理", "希島あいり", "きじまあいり", "Airi Kijima"],
    "辻井穗乃果": ["辻井穗乃果", "辻井ほのか", "つじいほのか", "Honoka Tsujii"],
    "友田彩也香": ["友田彩也香", "ともださやか", "Ayaka Tomoda"],
    "美乃雀": ["美乃雀", "美乃すずめ", "みのすずめ", "Suzume Bino"],
    "枫富爱": ["枫富爱", "楓ふうあ", "かえでふうあ", "Fua Kaede"],
    "逢见梨花": ["逢见梨花", "逢見りか", "おうみりか", "Rika Oumi"],
    "橘玛丽": ["橘玛丽", "橘メアリー", "たちばなめありー", "Mary Tachibana"],
    "根尾朱里": ["根尾朱里", "根尾あかり", "ねおあかり", "Akari Neo"],
    "天海翼": ["天海翼", "天海つばさ", "あまみつばさ", "Tsubasa Amami"],
    "纱仓真菜": ["纱仓真菜", "紗倉まな", "さくらまな", "Mana Sakura"],
    "麻生希": ["麻生希", "あそうのぞみ", "Nozomi Aso"],
    "结城留美奈": ["结城留美奈", "結城るみな", "ゆうきるみな", "Rumina Yuki"],
    "八木奈奈": ["八木奈奈", "八木奈々", "やぎなな", "Nana Yagi"],
    "星空萌爱": ["星空萌爱", "星空もあ", "ほしぞらもあ", "Moa Hoshizora"],
    "齐藤亚美里": ["齐藤亚美里", "斉藤あみり", "さいとうあみり", "Amiri Saito"],
    "田野忧": ["田野忧", "田野憂", "たのうい", "Ui Tano"],
    "美园和花": ["美园和花", "美園和花", "みそのわか", "Waka Misono"],
    "樱萌子": ["樱萌子", "桜もこ", "さくらもこ", "Moko Sakura"],
    "东条夏": ["东条夏", "東條なつ", "とうじょうなつ", "Natsu Tojo"],
    "柴崎春": ["柴崎春", "柴崎はる", "しばさきはる", "Haru Shibasaki"],
    "浅田结梨": ["浅田结梨", "浅田結梨", "あさだゆり", "Yuri Asada"],
    "梦乃爱华": ["梦乃爱华", "夢乃あいか", "ゆめのあいか", "Aika Yumeno"],
    "希咲爱丽丝": ["希咲爱丽丝", "希咲アリス", "きさきありす", "Alice Kisaki"],
    "北野未奈": ["北野未奈", "きたのみな", "Mina Kitano"],
    "铃木真夕": ["铃木真夕", "鈴木真夕", "すずきまゆ", "Mayu Suzuki"],
    "铃木心春": ["铃木心春", "鈴木心春", "すずきこはる", "Koharu Suzuki"],
    "希美真由": ["希美真由", "希美まゆ", "のぞみまゆ", "Mayu Nozomi"],
    "椎名由奈": ["椎名由奈", "椎名ゆな", "しいなゆな", "Yuna Shiina"],
    "初川南": ["初川南", "初川みなみ", "はつかわみなみ", "Minami Hatsukawa"],
    "有坂深雪": ["有坂深雪", "ありさかみゆき", "Miyuki Arisaka"],
    "佐山爱": ["佐山爱", "佐山愛", "さやまあい", "Ai Sayama"],
    "苍井空": ["苍井空", "蒼井そら", "あおいそら", "Sola Aoi"],
    "冲田杏梨": ["冲田杏梨", "沖田杏梨", "おきたあんり", "Anri Okita"],
    "樱井步": ["樱井步", "櫻井步", "桜井あゆ", "さくらいあゆ", "Ayumi Sakurai"],
    "水户香奈": ["水户香奈", "水戸かな", "みとかな", "Kana Mito"],
    "水端麻美": ["水端麻美", "水端あさみ", "みずはなあさみ", "Asami Mizuhata"],
    "庵姬花": ["庵姬花", "庵ひめか", "いおりひめか", "Himeka Iori"],
    "逢泽真里亚": ["逢泽真里亚", "逢沢まりあ", "あいざわまりあ", "Maria Aizawa"],
    "筱田步美": ["筱田步美", "篠田あゆみ", "しのだあゆみ", "Ayumi Shinoda"],
    "古川伊织": ["古川伊织", "古川いおり", "ふるかわいおり", "Iori Furukawa"],
    "浅见玲奈": ["浅见玲奈", "浅見玲奈", "あさみれいな", "Reina Asami"],
    "白石茉莉奈": ["白石茉莉奈", "しらいしまりな", "Marina Shiraishi"],
    "吉泽明步": ["吉泽明步", "吉沢明歩", "よしざわあきほ", "Akiho Yoshizawa"],
    "莲实克蕾儿": ["莲实克蕾儿", "蓮實克蕾兒", "蓮実クレア", "はすみくれあ", "Kurea Hasumi"],
    "希崎洁西卡": ["希崎洁西卡", "希崎潔西卡", "希崎ジェシカ", "きざきじぇしか", "Jessica Kizaki"],
    "希志爱野": ["希志爱野", "希志愛野", "希志あいの", "きしあいの", "Aino Kishi"],
    "宝生莉莉": ["宝生莉莉", "寶生莉莉", "宝生リリー", "芽森しずく", "Lily Hosho"],
    "向井蓝": ["向井蓝", "向井藍", "むかいあい", "Ai Mukai"],
    "森泽佳奈": ["森泽佳奈", "森澤佳奈", "森沢かな", "飯岡かなこ", "Kana Morisawa"],
    "椎名空": ["椎名空", "椎名そら", "しいなそら", "Sora Shiina"],
    "原纱央莉": ["原纱央莉", "原紗央莉", "はらさおり", "Saori Hara"],
    "一之濑亚美莉": ["一之濑亚美莉", "一之瀨亞美莉", "一ノ瀬アメリ", "Ameri Ichinose"],
    "武藤彩香": ["武藤彩香", "武藤あやか", "むとうあやか", "Ayaka Muto"],
    "水咲萝拉 (泷泽萝拉)": ["水咲萝拉 (泷泽萝拉)", "水咲萝拉", "水咲ローラ", "泷泽萝拉", "滝沢ローラ", "Laura Misaki", "Rola Takizawa"],
    "蒂亚": ["蒂亚", "蒂亞", "ティア", "Tia"],
    "藤井兰兰": ["藤井兰兰", "藤井蘭蘭", "藤井蘭々", "ふじいらんらん", "Ranran Fujii"],
    "设乐夕阳": ["设乐夕阳", "設樂夕陽", "設楽ゆうひ", "したらゆうひ", "Yuuhi Shitara"],
    "辉月杏梨": ["辉月杏梨", "輝月あんり", "きづきあんり", "Anri Kizuki"],
    "桃谷绘里香": ["桃谷绘里香", "桃谷繪里香", "桃谷エリカ", "ももたにえりか", "Erika Momodani"],
    "梦实香奈惠": ["梦实香奈惠", "夢實香奈惠", "夢実かなえ", "ゆめみかなえ", "Kanae Yumemi"],
    "林由奈": ["林由奈", "林ゆな", "はやしゆな", "Yuna Hayashi"],
    "miru": ["miru", "坂道美琉", "坂道みる", "さかみちみる"],
    "山手梨爱": ["山手梨爱", "山手梨愛", "やまてりあ", "Ria Yamate"],
    "松下纱荣子": ["松下纱荣子", "松下紗栄子", "まつしたさえこ", "Saeko Matsushita"],
}


def load_existing_actors() -> dict:
    if os.path.exists(ACTORS_JSON):
        try:
            with open(ACTORS_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def merge_actors(base_actors: dict, new_actors: dict) -> tuple:
    """无损智能合并：保留用户原有主键，补全新女优并扩充新别名"""
    merged = dict(base_actors)
    added_count = 0
    updated_alias_count = 0

    for name, aliases in new_actors.items():
        # 判断是否已存在（主名匹配，或别名中有交集）
        matched_key = None
        if name in merged:
            matched_key = name
        else:
            name_lower = name.lower()
            for k, v in merged.items():
                if k.lower() == name_lower or any(a.lower() == name_lower for a in v):
                    matched_key = k
                    break

        if matched_key:
            # 扩充别名
            cur_aliases = merged[matched_key]
            cur_lower = [a.lower() for a in cur_aliases]
            new_add = [a for a in aliases if a.lower() not in cur_lower]
            if new_add:
                cur_aliases.extend(new_add)
                updated_alias_count += len(new_add)
        else:
            merged[name] = list(aliases)
            added_count += 1

    return merged, added_count, updated_alias_count


def update_actors_file(backup: bool = True) -> dict:
    existing = load_existing_actors()
    merged, added_count, updated_alias_count = merge_actors(existing, PRESET_TOP_ACTORS)

    if backup and os.path.exists(ACTORS_JSON):
        bak_path = f"{ACTORS_JSON}.bak"
        try:
            with open(ACTORS_JSON, "r", encoding="utf-8") as src, open(bak_path, "w", encoding="utf-8") as dst:
                dst.write(src.read())
        except Exception:
            pass

    # 格式化排序写入
    tmp_path = f"{ACTORS_JSON}.tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, ACTORS_JSON)

    return {
        "total": len(merged),
        "added": added_count,
        "updated_aliases": updated_alias_count,
    }


def main():
    print("=" * 64)
    print("      Top 100+ 热门女优白名单智能更新工具")
    print("=" * 64)
    res = update_actors_file(backup=True)
    print(f"[*] 更新完成！")
    print(f"  当前女优库总计 : {res['total']} 位")
    print(f"  本次新增收录   : {res['added']} 位")
    print(f"  扩充多语言别名 : {res['updated_aliases']} 个")
    print(f"  配置文件路径   : {ACTORS_JSON}")
    print(f"[*] 后台运行中的 monitor 服务将在 2 秒内自动热重载生效！")
    print("=" * 64)


if __name__ == "__main__":
    main()
