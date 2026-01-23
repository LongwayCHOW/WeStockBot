TARGETS = [
    # =========================================
    # 👑 皇冠明珠 (核心资产，定价权)
    # =========================================
    {
        "code": "600519", "name": "贵州茅台", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 25, "sell": 40, "reverse": False, "desc": "PE(极佳<20)"},
            {"metric": "dv_ratio", "buy": 3.5, "sell": 1.5, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "000858", "name": "五粮液", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 16, "sell": 30, "reverse": False, "desc": "PE(极佳<13)"},
            {"metric": "dv_ratio", "buy": 4.0, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "000333", "name": "美的集团", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 15, "sell": 22, "reverse": False, "desc": "PE(极佳<12)"},
            {"metric": "dv_ratio", "buy": 5.0, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "600436", "name": "片仔癀", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 35, "sell": 65, "reverse": False, "desc": "PE(极佳<30)"},
            {"metric": "dv_ratio", "buy": 2.5, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "600329", "name": "达仁堂", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 12, "sell": 28, "reverse": False, "desc": "PE(极佳<10)"},
            {"metric": "dv_ratio", "buy": 3.0, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "300760", "name": "迈瑞医疗", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 22, "sell": 42, "reverse": False, "desc": "PE(极佳<18)"},
            {"metric": "dv_ratio", "buy": 1.5, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "600660", "name": "福耀玻璃", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 16, "sell": 28, "reverse": False, "desc": "PE(极佳<13)"},
            {"metric": "dv_ratio", "buy": 2.5, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "02328", "name": "中国财险(H)", "type": "H",
        "rules": [
            {"metric": "pb", "buy": 0.7, "sell": 1.2, "reverse": False, "desc": "PB"},
            {"metric": "dv_ratio", "buy": 6.5, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "00700", "name": "腾讯控股(H)", "type": "H",
        "rules": [
            # 注: AkShare 返回的是标准 PE，非 Non-IFRS，需自行留意差异
            {"metric": "pe_ttm", "buy": 18, "sell": 30, "reverse": False, "desc": "PE"}
        ]
    },
    {
        "code": "600900", "name": "长江电力", "type": "A",
        "rules": [
            # 股息率: >3.8买, <2.6卖
            {"metric": "dv_ratio", "buy": 3.8, "sell": 2.6, "reverse": True, "desc": "股息率"}
            # CSV 中提到股价 < 25，这里暂只监控股息率，可人工辅助看价格
        ]
    },

    # =========================================
    # 💰 现金奶牛 (高股息，低估值)
    # =========================================
    {
        "code": "00883", "name": "中国海油(H)", "type": "H",
        "rules": [
            {"metric": "pe_ttm", "buy": 7, "sell": None, "reverse": False, "desc": "PE"},
            {"metric": "dv_ratio", "buy": 7.0, "sell": 5.5, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "03988", "name": "中国银行(H)", "type": "H",
        "rules": [
            {"metric": "pb", "buy": 0.4, "sell": 0.65, "reverse": False, "desc": "PB"},
            {"metric": "dv_ratio", "buy": 8.0, "sell": 5.0, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "00939", "name": "建设银行(H)", "type": "H",
        "rules": [
            {"metric": "pb", "buy": 0.48, "sell": 0.70, "reverse": False, "desc": "PB"},
            {"metric": "dv_ratio", "buy": 7.0, "sell": 4.5, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "00941", "name": "中国移动(H)", "type": "H",
        "rules": [
            {"metric": "pe_ttm", "buy": 11, "sell": None, "reverse": False, "desc": "PE"},
            {"metric": "dv_ratio", "buy": 6.5, "sell": 4.5, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "00874", "name": "白云山(H)", "type": "H",
        "rules": [
            {"metric": "pe_ttm", "buy": 10, "sell": 15, "reverse": False, "desc": "PE"},
            {"metric": "dv_ratio", "buy": 4.5, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "000651", "name": "格力电器", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 8, "sell": 12, "reverse": False, "desc": "PE"},
            {"metric": "dv_ratio", "buy": 7.0, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "603288", "name": "海天味业", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 22, "sell": 42, "reverse": False, "desc": "PE(极佳<18)"}
        ]
    },
    {
        "code": "002027", "name": "分众传媒", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 14, "sell": 23, "reverse": False, "desc": "PE(极佳<11)"}
        ]
    },

    # =========================================
    # 🦁 周期猎物 (底部埋伏，顶部逃顶)
    # =========================================
    {
        "code": "01919", "name": "中远海控(H)", "type": "H",
        "rules": [
            {"metric": "pb", "buy": 0.7, "sell": 1.3, "reverse": False, "desc": "PB(运价底部)"},
            {"metric": "dv_ratio", "buy": 8.0, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "601668", "name": "中国建筑", "type": "A",
        "rules": [
            {"metric": "pb", "buy": 0.55, "sell": 0.8, "reverse": False, "desc": "PB"},
            {"metric": "pe_ttm", "buy": 5, "sell": None, "reverse": False, "desc": "PE"}
        ]
    },
    {
        "code": "01099", "name": "国药控股(H)", "type": "H",
        "rules": [
            {"metric": "pe_ttm", "buy": 8, "sell": 14, "reverse": False, "desc": "PE"},
            {"metric": "dv_ratio", "buy": 5.5, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "06030", "name": "中信证券(H)", "type": "H",
        "rules": [
            {"metric": "pb", "buy": 0.9, "sell": 1.7, "reverse": False, "desc": "PB(牛熊周期)"}
        ]
    },
    {
        "code": "600019", "name": "宝钢股份", "type": "A",
        "rules": [
            {"metric": "pb", "buy": 0.55, "sell": 0.9, "reverse": False, "desc": "PB"},
            {"metric": "dv_ratio", "buy": 6.0, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "002714", "name": "牧原股份", "type": "A",
        "rules": [
            # 注: 周期股亏损时 PE 无意义或为负。这里配置仅作参考。
            # CSV: PE < 10 (全行业巨亏), PE > 25 (暴利)
            {"metric": "pe_ttm", "buy": 10, "sell": 25, "reverse": False, "desc": "PE(需结合周期)"}
        ]
    },
    {
        "code": "601088", "name": "中国神华", "type": "A",
        "rules": [
            # CSV 规则提到 H 股 PE < 8，这里监控 A 股股息和 PE
            {"metric": "dv_ratio", "buy": 8.0, "sell": None, "reverse": True, "desc": "股息率"},
            {"metric": "pe_ttm", "buy": None, "sell": 12, "reverse": False, "desc": "PE(卖出)"}
        ]
    },
    {
        "code": "601899", "name": "紫金矿业", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 15, "sell": 30, "reverse": False, "desc": "PE"},
            {"metric": "pb", "buy": None, "sell": 5.5, "reverse": False, "desc": "PB(卖出)"},
            {"metric": "dv_ratio", "buy": 5.0, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    }
]