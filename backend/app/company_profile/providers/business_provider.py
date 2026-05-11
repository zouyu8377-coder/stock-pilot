from app.company_profile.schemas import CompanyProfile


class BusinessProvider:
    """
    基于规则的 company profile 构建器。
    不调用 AI，纯规则引擎推导。
    """

    def build_profile(
        self,
        symbol: str,
        name: str,
        industry: str,
        tushare_info: dict,
        concept_tags: list[str],
    ) -> CompanyProfile:
        profile = CompanyProfile()
        profile.company_name = name
        profile.main_business = tushare_info.get("main_business", "")
        profile.concept_tags = concept_tags

        # 如果 tushare 没有主营业务，用规则兜底
        if not profile.main_business:
            profile.main_business = self._infer_main_business(name, industry)

        profile.core_products = self._infer_core_products(name, industry)
        profile.industry_chain_position = self._infer_chain_position(name, industry)
        profile.core_logic = self._infer_core_logic(name, industry, concept_tags)
        profile.company_type = self._infer_company_type(name, industry, concept_tags)
        profile.profit_driver = self._infer_profit_driver(name, industry)
        profile.competitive_advantage = self._infer_advantage(name, industry, concept_tags)
        profile.risk_points = self._infer_risks(name, industry)

        return profile

    def _infer_main_business(self, name: str, industry: str) -> str:
        name = name or ""
        industry = industry or ""

        if "酒" in industry or "白酒" in industry:
            return "白酒酿造与销售"
        if "银行" in industry:
            return "存贷款、理财、投行等金融服务"
        if "半导体" in industry or "芯片" in industry or "集成电路" in industry:
            return "半导体芯片设计/制造/封测"
        if "有色" in industry or "小金属" in industry or "金属" in industry:
            return "有色金属采选与深加工"
        if "新能源" in industry or "光伏" in industry:
            return "光伏组件/电池片/储能系统"
        if "汽车" in industry:
            return "整车制造及零部件"
        if "医药" in industry or "医疗" in industry:
            return "药品/医疗器械研发、生产与销售"
        if "食品" in industry or "饮料" in industry:
            return "食品饮料制造与销售"
        if "家电" in industry:
            return "家用电器研发、生产与销售"
        if "券商" in industry or "证券" in industry:
            return "证券经纪、投行、资管"
        if "保险" in industry:
            return "人寿/财产保险及投资"
        if "地产" in industry or "房地产" in industry:
            return "房地产开发与物业管理"
        if "化工" in industry:
            return "化工产品生产与销售"
        if "电子" in industry:
            return "电子元器件制造与销售"
        if "机械" in industry or "设备" in industry:
            return "机械设备研发、生产与销售"
        if "电力" in industry:
            return "发电及电力销售"
        if "煤炭" in industry:
            return "煤炭开采与销售"
        if "石油" in industry or "石化" in industry:
            return "石油勘探、炼化与销售"
        if "钢铁" in industry:
            return "钢铁冶炼与加工"
        if "建材" in industry:
            return "建筑材料生产与销售"
        if "造纸" in industry:
            return "纸浆及纸制品生产"
        if "纺织" in industry or "服装" in industry:
            return "纺织品/服装制造与销售"
        if "交通运输" in industry or "物流" in industry:
            return "运输及物流服务"
        if "通信" in industry or "电信" in industry:
            return "通信网络运营与设备"
        if "计算机" in industry or "软件" in industry:
            return "软件开发及IT服务"
        if "传媒" in industry or "广告" in industry:
            return "媒体内容及广告"

        return ""

    def _infer_core_products(self, name: str, industry: str) -> list[str]:
        name = name or ""
        industry = industry or ""
        products = []

        if "白酒" in industry or "酒" in industry:
            products = ["白酒", "系列酒"]
        elif "银行" in industry:
            products = ["贷款", "理财", "投行服务"]
        elif "半导体" in industry or "芯片" in industry:
            products = ["芯片", "晶圆", "半导体设备"]
        elif "光伏" in industry:
            products = ["光伏组件", "硅片", "电池片"]
        elif "锂电池" in industry or "宁德" in name:
            products = ["动力电池", "储能电池"]
        elif "汽车" in industry:
            products = ["整车", "汽车零部件"]
        elif "医药" in industry or "医疗" in industry:
            products = ["药品", "医疗器械"]
        elif "家电" in industry:
            products = ["空调", "冰箱", "洗衣机", "小家电"]
        elif "券商" in industry or "证券" in industry:
            products = ["经纪业务", "投行业务", "资管业务"]
        elif "保险" in industry:
            products = ["寿险", "财险", "健康险"]
        elif "有色" in industry or "小金属" in industry:
            if "钨" in name:
                products = ["数控刀片", "硬质合金", "钨丝"]
            elif "稀土" in name:
                products = ["稀土氧化物", "磁性材料"]
            elif "锂" in name:
                products = ["碳酸锂", "氢氧化锂"]
            elif "铜" in name or "钼" in name:
                products = ["铜精矿", "钼精矿"]
            else:
                products = ["有色金属产品"]
        elif "食品" in industry or "饮料" in industry:
            products = ["饮料", "乳制品", "调味品"]
        elif "机械" in industry or "设备" in industry:
            products = ["机械设备", "自动化设备"]
        elif "化工" in industry:
            products = ["化工原料", "化工制品"]
        elif "电子" in industry:
            products = ["电子元件", "PCB", "连接器"]
        elif "电力" in industry:
            products = ["火电", "水电", "风电", "光伏"]
        elif "煤炭" in industry:
            products = ["动力煤", "焦煤"]
        elif "石油" in industry or "石化" in industry:
            products = ["原油", "成品油", "化工品"]
        elif "钢铁" in industry:
            products = ["板材", "长材", "特钢"]
        elif "计算机" in industry or "软件" in industry:
            products = ["软件产品", "IT服务", "云服务"]
        elif "通信" in industry:
            products = ["通信设备", "网络服务"]
        elif "传媒" in industry:
            products = ["内容产品", "广告服务"]

        return products

    def _infer_chain_position(self, name: str, industry: str) -> str:
        name = name or ""
        industry = industry or ""

        if "钨" in name or "稀土" in name or "锂" in name or "铜" in name:
            return "上游资源开采 + 中游深加工"
        if "白酒" in industry or "食品" in industry:
            return "下游消费品牌端"
        if "银行" in industry or "保险" in industry or "券商" in industry:
            return "金融服务端"
        if "半导体" in industry:
            if "设备" in name or "北方华创" in name:
                return "上游半导体设备"
            if "材料" in name:
                return "上游半导体材料"
            return "中游芯片设计/制造"
        if "光伏" in industry:
            if "硅" in name or "通威" in name:
                return "上游硅料"
            if "隆基" in name or "晶科" in name or "组件" in name:
                return "中游组件 + 下游电站"
            return "中游电池片/组件"
        if "汽车" in industry:
            if "比亚迪" in name or "整车" in name:
                return "下游整车制造"
            return "中游零部件"
        if "医药" in industry or "医疗" in industry:
            if "器械" in name:
                return "中游医疗器械"
            if "CXO" in name or "服务" in name:
                return "医药研发服务"
            return "下游药品消费"
        if "家电" in industry:
            return "下游消费品制造"
        if "机械" in industry or "设备" in industry:
            return "中游装备制造"
        if "化工" in industry:
            return "中游化工材料"
        if "电子" in industry:
            return "中游电子元器件"
        if "电力" in industry:
            return "上游发电端"
        if "煤炭" in industry or "石油" in industry:
            return "上游能源开采"
        if "钢铁" in industry:
            return "中游冶金加工"
        if "建材" in industry:
            return "中游建筑材料"
        if "造纸" in industry:
            return "中游纸制品"
        if "纺织" in industry or "服装" in industry:
            return "下游消费品"
        if "计算机" in industry or "软件" in industry:
            return "中游软件及IT服务"
        if "通信" in industry:
            return "中游通信设备及服务"
        if "传媒" in industry:
            return "下游内容消费"

        return "中游制造/服务"

    def _infer_core_logic(self, name: str, industry: str, concept_tags: list[str]) -> list[str]:
        name = name or ""
        industry = industry or ""
        logic = []

        # 行业级逻辑
        if "白酒" in industry or "酒" in industry:
            logic = ["高端消费定价权", "品牌护城河", "高毛利模式"]
        elif "银行" in industry:
            logic = ["息差修复", "资产质量改善", "高股息防御"]
        elif "半导体" in industry or "芯片" in industry:
            logic = ["国产替代", "AI算力产业链", "设备材料自主可控"]
        elif "光伏" in industry:
            logic = ["全球能源转型", "产能出清后龙头集中", "储能配套增长"]
        elif "锂电池" in industry or "宁德" in name or "锂" in name:
            logic = ["新能源车渗透率提升", "储能需求爆发", "锂价周期"]
        elif "汽车" in industry:
            logic = ["智能化竞争", "出海扩张", "新能源替代"]
        elif "医药" in industry or "医疗" in industry:
            logic = ["老龄化刚需", "创新药出海", "器械国产替代"]
        elif "家电" in industry:
            logic = ["以旧换新政策", "海外品牌升级", "智能家居生态"]
        elif "有色" in industry or "小金属" in industry:
            if "钨" in name:
                logic = ["高端刀具国产替代", "工业母机产业链", "战略金属管控"]
            elif "稀土" in name:
                logic = ["战略资源管控", "磁性材料需求", "军工配套"]
            elif "锂" in name:
                logic = ["新能源金属", "锂价周期", "南美/非洲资源布局"]
            elif "铜" in name or "钼" in name:
                logic = ["全球铜供需紧张", "新能源用铜增量", "资源并购"]
            else:
                logic = ["金属价格上涨", "全球供应链重构", "战略资源属性"]
        elif "券商" in industry or "证券" in industry:
            logic = ["资本市场改革", "财富管理转型", "成交量弹性"]
        elif "保险" in industry:
            logic = ["代理人改革", "康养需求", "投资端利率敏感"]
        elif "机械" in industry or "设备" in industry:
            logic = ["设备更新政策", "高端制造出海", "进口替代"]
        elif "化工" in industry:
            logic = ["产能集中度提升", "新材料突破", "海外产能转移"]
        elif "电子" in industry:
            logic = ["消费电子复苏", "汽车电子增量", "AI硬件需求"]
        elif "电力" in industry:
            logic = ["绿电转型", "容量电价机制", "高股息防御"]
        elif "煤炭" in industry:
            logic = ["能源安全", "高股息", "供给刚性"]
        elif "石油" in industry or "石化" in industry:
            logic = ["油价周期", "炼化一体化", "新材料延伸"]
        elif "钢铁" in industry:
            logic = ["建筑需求", "特钢升级", "产能控制"]
        elif "计算机" in industry or "软件" in industry:
            logic = ["AI应用落地", "信创替代", "SaaS订阅模式"]
        elif "通信" in industry:
            logic = ["5G/6G建设", "算力网络", "卫星互联网"]
        elif "传媒" in industry:
            logic = ["内容IP变现", "广告复苏", "AI生成内容"]

        # 概念级补充
        if "央企改革" in concept_tags and "央企改革" not in logic:
            logic.append("央企资源整合预期")
        if "军工" in concept_tags and "军工" not in logic:
            logic.append("国防装备采购")
        if "高股息" in concept_tags and "高股息" not in logic:
            logic.append("红利资产配置")
        if "国产替代" in concept_tags and "国产替代" not in logic:
            logic.append("供应链安全")
        if "工业母机" in concept_tags and "工业母机" not in logic:
            logic.append("工业母机自主可控")

        # 个股级特殊逻辑
        if "茅台" in name:
            logic = ["高端消费定价权", "批价风向标", "品牌护城河"]
        elif "比亚迪" in name:
            logic = ["新能源车全球龙头", "垂直整合成本优势", "智能化追赶"]
        elif "宁德时代" in name:
            logic = ["动力电池全球市占率第一", "技术迭代领先", "储能第二曲线"]
        elif "中芯国际" in name:
            logic = ["晶圆代工国产替代", "先进制程突破", "大基金支持"]
        elif "北方华创" in name:
            logic = ["半导体设备平台型龙头", "刻蚀/薄膜设备突破", "国产替代最核心环节"]
        elif "中国平安" in name:
            logic = ["综合金融平台", "代理人渠道改革", "医疗养老生态"]
        elif "招商银行" in name:
            logic = ["零售银行标杆", "财富管理转型", "资产质量优异"]
        elif "中信证券" in name:
            logic = ["投行龙头", "机构业务优势", "资本市场改革受益"]
        elif "海康威视" in name:
            logic = ["安防全球龙头", "AI视觉落地", "EBG业务转型"]
        elif "迈瑞医疗" in name:
            logic = ["医疗器械平台型龙头", "出海加速", "高端产品替代"]
        elif "恒瑞医药" in name:
            logic = ["创新药龙头", "管线逐步兑现", "国际化布局"]
        elif "隆基绿能" in name:
            logic = ["单晶硅片龙头", "BC电池技术", "组件品牌出海"]
        elif "紫金矿业" in name:
            logic = ["全球矿业龙头", "铜金双轮驱动", "逆周期并购能力"]
        elif "中国中免" in name:
            logic = ["免税牌照垄断", "海南自贸港", "出入境客流恢复"]
        elif "三一重工" in name:
            logic = ["工程机械龙头", "海外占比提升", "电动化转型"]
        elif "汇川技术" in name:
            logic = ["工业自动化龙头", "伺服/PLC国产替代", "新能源车电驱增量"]
        elif "金山办公" in name:
            logic = ["办公软件国产替代", "WPS订阅转型", "AI办公助手"]
        elif "科大讯飞" in name:
            logic = ["语音AI龙头", "大模型星火", "教育/医疗场景落地"]

        return logic[:5]

    def _infer_company_type(self, name: str, industry: str, concept_tags: list[str]) -> list[str]:
        types = []

        if "银行" in industry or "保险" in industry or "券商" in industry:
            types.append("金融股")
        if "白酒" in industry or "食品" in industry or "饮料" in industry:
            types.append("消费股")
        if "有色" in industry or "煤炭" in industry or "石油" in industry or "钢铁" in industry:
            types.append("周期股")
        if "医药" in industry or "医疗" in industry:
            types.append("医药股")
        if "半导体" in industry or "芯片" in industry or "电子" in industry:
            types.append("科技股")
        if "新能源" in industry or "光伏" in industry or "锂电池" in industry:
            types.append("新能源")
        if "机械" in industry or "设备" in industry:
            types.append("制造业")
        if "军工" in concept_tags or "国防" in name:
            types.append("军工")
        if "央企" in name or "中国" in name or "中字头" in concept_tags:
            types.append("央企")
        if "国企" in name:
            types.append("国企")
        if "高股息" in concept_tags:
            types.append("高股息")
        if "资源" in name or "矿业" in name or "有色" in industry:
            types.append("资源股")

        if not types:
            types.append("制造业")

        return types

    def _infer_profit_driver(self, name: str, industry: str) -> str:
        name = name or ""
        industry = industry or ""

        if "白酒" in industry or "酒" in industry:
            return "量价齐升 + 产品结构升级"
        if "银行" in industry:
            return "净息差 + 资产规模扩张"
        if "半导体" in industry:
            return "产能利用率 + 技术溢价 + 国产替代放量"
        if "光伏" in industry:
            return "组件出货量 + 一体化成本优势"
        if "锂电池" in industry or "宁德" in name:
            return "电池出货量 + 储能增量 + 材料成本下行"
        if "汽车" in industry:
            return "销量 + 均价 + 规模效应"
        if "医药" in industry or "医疗" in industry:
            return "新药放量 + 器械出海 + 诊疗量恢复"
        if "家电" in industry:
            return "销量 + 均价提升 + 原材料成本"
        if "有色" in industry or "小金属" in industry:
            if "钨" in name:
                return "钨价上涨 + 高端刀具放量"
            if "稀土" in name:
                return "稀土配额 + 磁性材料需求"
            if "锂" in name:
                return "锂价周期 + 自有矿放量"
            return "金属价格 + 产能利用率"
        if "券商" in industry or "证券" in industry:
            return "成交量 + IPO + 资管规模"
        if "保险" in industry:
            return "保费增长 + 投资收益 + 利率环境"
        if "机械" in industry or "设备" in industry:
            return "设备更新政策 + 出海订单 + 进口替代"
        if "化工" in industry:
            return "产品价格 + 产能利用率 + 新材料占比"
        if "电子" in industry:
            return "出货量 + 新品周期 + 客户结构"
        if "电力" in industry:
            return "发电量 + 电价 + 绿电溢价"
        if "煤炭" in industry:
            return "煤价 + 产量 + 长协占比"
        if "石油" in industry or "石化" in industry:
            return "油价 + 炼化价差 + 化工品价格"
        if "钢铁" in industry:
            return "钢价 + 铁矿成本 + 产量"
        if "计算机" in industry or "软件" in industry:
            return "订阅收入 + 项目制 + AI增量"
        if "通信" in industry:
            return "用户增长 + ARPU + 算力网络"
        if "传媒" in industry:
            return "广告复苏 + 内容付费 + IP变现"

        return "收入增长 + 成本控制"

    def _infer_advantage(self, name: str, industry: str, concept_tags: list[str]) -> str:
        name = name or ""
        industry = industry or ""

        if "茅台" in name:
            return "白酒绝对龙头，品牌护城河全球罕见"
        if "宁德时代" in name:
            return "动力电池全球市占率第一，技术迭代最快"
        if "比亚迪" in name:
            return "垂直整合能力最强，成本控制能力行业第一"
        if "中芯国际" in name:
            return "大陆最先进晶圆代工，大基金核心标的"
        if "北方华创" in name:
            return "半导体设备平台型龙头，产品线最全"
        if "中国平安" in name:
            return "综合金融牌照最全，医疗养老生态布局领先"
        if "招商银行" in name:
            return "零售银行标杆，财富管理AUM行业第一"
        if "中信证券" in name:
            return "投行实力行业第一，机构客户基础深厚"
        if "海康威视" in name:
            return "安防全球市占率第一，AI视觉场景落地最广"
        if "迈瑞医疗" in name:
            return "医疗器械平台型龙头，海外收入占比持续提升"
        if "恒瑞医药" in name:
            return "创新药管线最丰富，研发投入行业领先"
        if "隆基绿能" in name:
            return "单晶硅片龙头，BC电池技术领先"
        if "紫金矿业" in name:
            return "全球矿业龙头，逆周期并购能力最强"
        if "中国中免" in name:
            return "免税牌照垄断，海南自贸港最大受益方"
        if "三一重工" in name:
            return "工程机械龙头，海外收入占比持续提升"
        if "汇川技术" in name:
            return "工业自动化国产替代最核心标的，多行业通用平台"
        if "金山办公" in name:
            return "办公软件国产替代唯一龙头，订阅转型顺利"
        if "科大讯飞" in name:
            return "语音AI技术积累最深，大模型落地场景最广"

        if "银行" in industry:
            return "网点覆盖广，客户基础稳"
        if "半导体" in industry:
            return "技术积累深厚，国产替代空间大"
        if "白酒" in industry:
            return "品牌历史悠久，渠道控制力强"
        if "医药" in industry:
            return "研发管线丰富，临床资源充足"
        if "有色" in industry or "小金属" in industry:
            return "资源储量优势，产业链一体化"
        if "机械" in industry:
            return "产品线完整，售后服务网络覆盖广"
        if "新能源" in industry or "光伏" in industry:
            return "规模效应显著，技术降本领先"
        if "家电" in industry:
            return "品牌知名度高，渠道覆盖广"
        if "计算机" in industry or "软件" in industry:
            return "技术壁垒高，客户粘性强"

        return "行业地位稳固，运营能力较强"

    def _infer_risks(self, name: str, industry: str) -> list[str]:
        name = name or ""
        industry = industry or ""
        risks = []

        if "白酒" in industry or "酒" in industry:
            risks = ["消费疲软", "批价下行", "政策风险"]
        elif "银行" in industry:
            risks = ["息差收窄", "地产不良暴露", "宏观经济下行"]
        elif "半导体" in industry:
            risks = ["技术封锁升级", "下游需求疲软", "产能过剩"]
        elif "光伏" in industry:
            risks = ["产能过剩", "价格战", "贸易壁垒"]
        elif "锂电池" in industry or "宁德" in name or "锂" in name:
            risks = ["锂价下跌", "产能过剩", "技术路线变化"]
        elif "汽车" in industry:
            risks = ["价格战", "新能源补贴退坡", "海外政策风险"]
        elif "医药" in industry or "医疗" in industry:
            risks = ["集采降价", "研发失败", "出海合规风险"]
        elif "家电" in industry:
            risks = ["地产销售低迷", "原材料涨价", "海外需求波动"]
        elif "有色" in industry or "小金属" in industry:
            if "钨" in name:
                risks = ["钨价下跌", "制造业需求回落"]
            elif "稀土" in name:
                risks = ["稀土价格下跌", "下游磁材需求疲软"]
            elif "锂" in name:
                risks = ["锂价大幅下跌", "海外资源国政策变化"]
            else:
                risks = ["金属价格下跌", "全球经济衰退"]
        elif "券商" in industry or "证券" in industry:
            risks = ["成交量萎缩", "IPO放缓", "监管收紧"]
        elif "保险" in industry:
            risks = ["利率下行", "权益市场波动", "代理人流失"]
        elif "机械" in industry or "设备" in industry:
            risks = ["基建投资放缓", "海外需求波动", "原材料涨价"]
        elif "化工" in industry:
            risks = ["产品价格波动", "环保政策", "产能过剩"]
        elif "电子" in industry:
            risks = ["消费电子需求疲软", "客户集中度", "技术迭代"]
        elif "电力" in industry:
            risks = ["煤价上涨", "电价下调", "新能源消纳"]
        elif "煤炭" in industry:
            risks = ["煤价下跌", "新能源替代", "安全环保"]
        elif "石油" in industry or "石化" in industry:
            risks = ["油价大跌", "炼化价差收窄", "碳中和政策"]
        elif "钢铁" in industry:
            risks = ["钢价下跌", "铁矿石涨价", "需求疲软"]
        elif "计算机" in industry or "软件" in industry:
            risks = ["IT支出收缩", "人才成本上升", "技术迭代"]
        elif "通信" in industry:
            risks = ["资本开支放缓", "ARPU下降", "同质化竞争"]
        elif "传媒" in industry:
            risks = ["广告主预算收缩", "内容监管", "流量成本上升"]

        if not risks:
            risks = ["宏观经济波动", "行业竞争加剧"]

        return risks[:3]
