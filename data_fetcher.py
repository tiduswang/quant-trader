# -*- coding: utf-8 -*-
"""
Data Fetcher - 多市场数据获取器（A股/ETF/港股）
数据源：
  - 新浪财经API: 实时行情（A股/ETF批量、港股 rt_hk）
  - 腾讯行情API: 基本面数据（PE/PB/市值，A股/ETF/港股统一格式）
  - 腾讯K线API: 历史K线（A股/ETF fqkline，港股 hkfqkline）
  - akshare: A股财务指标、个股新闻
"""
import requests
import pandas as pd
import numpy as np
import re
import json
import time
import logging
from datetime import datetime, timedelta
import akshare as ak

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# A股热门股票池（约200只主流股票）
STOCK_POOL = [
    # 白酒/消费
    ('600519','贵州茅台'),('000858','五粮液'),('000568','泸州老窖'),('600809','山西汾酒'),
    ('002304','洋河股份'),('000596','古井贡酒'),('600600','青岛啤酒'),('603369','今世缘'),
    ('002714','牧原股份'),('000876','新希望'),('002746','仙坛股份'),('300498','温氏股份'),
    # 金融
    ('601398','工商银行'),('601939','建设银行'),('601288','农业银行'),('601988','中国银行'),
    ('601628','中国人寿'),('601318','中国平安'),('600036','招商银行'),('600030','中信证券'),
    ('601166','兴业银行'),('600000','浦发银行'),('000001','平安银行'),('600837','海通证券'),
    ('601688','华泰证券'),('300059','东方财富'),('601601','中国太保'),('601336','新华保险'),
    ('002736','国信证券'),('600958','东方证券'),('601318','中国平安'),('600016','民生银行'),
    # 科技/半导体
    ('300750','宁德时代'),('002475','立讯精密'),('300059','东方财富'),('300760','迈瑞医疗'),
    ('002241','歌尔股份'),('300015','爱尔眼科'),('002230','科大讯飞'),('300274','阳光电源'),
    ('300308','中际旭创'),('300124','汇川技术'),('002415','海康威视'),('000063','中兴通讯'),
    ('603501','韦尔股份'),('603986','兆易创新'),('688981','中芯国际'),('688256','寒武纪'),
    ('002371','北方华创'),('300223','北京君正'),('688012','中微公司'),('300661','圣邦股份'),
    ('002049','紫光国微'),('300782','卓胜微'),('300015','爱尔眼科'),('300760','迈瑞医疗'),
    ('688111','金山办公'),('688567','孚能科技'),('300274','阳光电源'),('002129','TCL中环'),
    # 新能源/光伏
    ('300274','阳光电源'),('601012','隆基绿能'),('002129','TCL中环'),('002335','科华数据'),
    ('300316','晶盛机电'),('603806','福斯特'),('688599','天合光能'),('002812','恩捷股份'),
    ('300750','宁德时代'),('002709','天赐材料'),('300037','新宙邦'),('002460','赣锋锂业'),
    ('002466','天齐锂业'),('600884','杉杉股份'),('300073','当升科技'),('300957','贝泰妮'),
    # 医药/医疗
    ('600276','恒瑞医药'),('300015','爱尔眼科'),('300760','迈瑞医疗'),('600436','片仔癀'),
    ('000538','云南白药'),('600196','复星医药'),('002007','华兰生物'),('300142','沃森生物'),
    ('603259','药明康德'),('300122','智飞生物'),('600438','通威股份'),('002326','永太科技'),
    ('603392','万泰生物'),('300601','康泰生物'),('688235','百济神州'),('002422','科伦药业'),
    # 军工/航空航天
    ('600036','招商银行'),('600893','航发动力'),('000768','中航西飞'),('002179','中航光电'),
    ('600760','中航沈飞'),('601698','中国卫通'),('600150','中国船舶'),('000738','航发控制'),
    # 化工/材料
    ('600309','万华化学'),('600585','海螺水泥'),('002746','仙坛股份'),('600346','恒力石化'),
    ('002493','荣盛石化'),('600809','山西汾酒'),('601233','桐昆股份'),('002648','卫星化学'),
    # 地产/基建
    ('000002','万科A'),('001979','招商蛇口'),('600048','保利发展'),('000069','华侨城A'),
    ('601668','中国建筑'),('601800','中国交建'),('601186','中国铁建'),('601390','中国中铁'),
    ('600585','海螺水泥'),('000651','格力电器'),
    # 家电/汽车
    ('000651','格力电器'),('000333','美的集团'),('000521','长虹美菱'),('600690','海尔智家'),
    ('002508','老板电器'),('002032','苏泊尔'),('000100','TCL科技'),('600887','伊利股份'),
    ('002594','比亚迪'),('601238','广汽集团'),('600104','上汽集团'),('601633','长城汽车'),
    ('000625','长安汽车'),('600006','东风汽车'),('601127','赛力斯'),
    # 通信/传媒
    ('002415','海康威视'),('000063','中兴通讯'),('600050','中国联通'),('601728','中国电信'),
    ('300133','华策影视'),('300251','光线传媒'),('002555','三七互娱'),('002415','海康威视'),
    # 煤炭/有色/钢铁
    ('601899','紫金矿业'),('601898','中煤能源'),('601225','陕西煤业'),('600188','兖矿能源'),
    ('600019','宝钢股份'),('600010','包钢股份'),('000878','云南铜业'),('600362','江西铜业'),
    ('600547','山东黄金'),('601899','紫金矿业'),('600219','南山铝业'),
    # 电力/公用
    ('600900','长江电力'),('600886','国投电力'),('600795','国电电力'),('601985','中国核电'),
    ('600025','华能水电'),('600674','川投能源'),
    # 交运/物流
    ('601021','春秋航空'),('600009','上海机场'),('600221','海南航空'),('601111','中国国航'),
    ('600029','南方航空'),('002352','顺丰控股'),('600221','海南航空'),
    # 食品/零售
    ('600887','伊利股份'),('603288','海天味业'),('603517','绝味食品'),('603899','晨光股份'),
    ('605499','东鹏饮料'),('603027','千禾味业'),('600872','中炬高新'),('002714','牧原股份'),
    # 其他蓝筹
    ('601888','中国中免'),('600660','福耀玻璃'),('601169','北京银行'),('601919','中远海控'),
    ('600585','海螺水泥'),('601618','中国中冶'),('601766','中国中车'),('601727','上海电气'),
    ('600839','四川长虹'),('000725','京东方A'),('002384','东山精密'),('600438','通威股份'),
]

# 市场定义
MARKETS = {
    'a': {'name': 'A股', 'desc': '沪深A股'},
    'etf': {'name': 'ETF', 'desc': '场内基金ETF'},
    'hk': {'name': '港股', 'desc': '香港市场'}
}

# ETF股票池（主流场内ETF）
ETF_POOL = [
    ('510300', '沪深300ETF'), ('510500', '中证500ETF'), ('510050', '上证50ETF'),
    ('159915', '创业板ETF'), ('159949', '创业板50ETF'), ('588000', '科创50ETF'),
    ('512100', '中证1000ETF'), ('510880', '红利ETF'),
    ('512880', '证券ETF'), ('512800', '银行ETF'), ('512690', '酒ETF'),
    ('512010', '医药ETF'), ('512170', '医疗ETF'), ('512480', '半导体ETF'),
    ('512760', '芯片ETF'), ('515030', '新能源车ETF'), ('515790', '光伏ETF'),
    ('515880', '通信ETF'), ('512660', '军工ETF'), ('515000', '科技ETF'),
    ('159928', '消费ETF'), ('512580', '环保ETF'), ('518880', '黄金ETF'),
    ('513100', '纳指ETF'), ('513500', '标普500ETF'), ('159920', '恒生ETF'),
    ('513180', '恒生科技ETF'), ('513050', '中概互联ETF'), ('159919', '沪深300ETF'),
    ('159901', '深证100ETF'), ('510330', '沪深300ETF华夏'), ('588080', '科创板50ETF'),
]

# 港股股票池（主流港股）
HK_POOL = [
    ('00700', '腾讯控股'), ('09988', '阿里巴巴-W'), ('03690', '美团-W'),
    ('01810', '小米集团-W'), ('01211', '比亚迪股份'), ('00388', '香港交易所'),
    ('01299', '友邦保险'), ('00005', '汇丰控股'), ('00941', '中国移动'),
    ('09618', '京东集团-SW'), ('01024', '快手-W'), ('02020', '安踏体育'),
    ('02318', '中国平安'), ('03988', '中国银行'), ('01398', '工商银行'),
    ('00939', '建设银行'), ('01288', '农业银行'), ('01088', '中国神华'),
    ('00883', '中国海洋石油'), ('00857', '中国石油股份'), ('00386', '中国石油化工股份'),
    ('00981', '中芯国际'), ('00763', '中兴通讯'), ('02382', '舜宇光学科技'),
    ('02015', '理想汽车-W'), ('09868', '小鹏汽车-W'), ('09866', '蔚来-SW'),
    ('02628', '中国人寿'), ('09999', '网易-S'), ('09888', '百度集团-SW'),
    ('09961', '携程集团-S'), ('00688', '中国海外发展'), ('01109', '华润置地'),
    ('00728', '中国电信'), ('00916', '龙源电力'), ('01171', '兖矿能源'),
    ('02331', '李宁'), ('00020', '商汤-W'), ('01833', '平安好医生'),
    ('00268', '金蝶国际'), ('00772', '阅文集团'), ('01060', '阿里影业'),
    ('01299', '友邦保险'), ('03633', '中裕能源'), ('00981', '中芯国际'),
    ('01876', '百威亚太'), ('02313', '申洲国际'), ('00175', '吉利汽车'),
]

# 各市场股票池
MARKET_POOLS = {
    'a': STOCK_POOL,
    'etf': ETF_POOL,
    'hk': HK_POOL,
}


# ========== 拼音搜索索引（动态全量） ==========
_SEARCH_INDEX = None
_SEARCH_INDEX_TIME = 0
_SEARCH_INDEX_TTL = 86400  # 24小时


def _build_pinyin_index_from_list(stock_list):
    """从股票列表构建拼音首字母索引"""
    from pypinyin import pinyin, Style
    index = []
    for item in stock_list:
        code = item['code']
        name = item['name']
        market = item.get('market', 'a')
        clean = re.sub(r'[^\u4e00-\u9fff]', '', name)
        if clean:
            initials = ''.join(p[0][0] for p in pinyin(clean, style=Style.FIRST_LETTER))
            full_pinyin = ''.join(p[0] for p in pinyin(clean, style=Style.NORMAL))
        else:
            initials = ''
            full_pinyin = ''
        index.append({
            'code': code, 'name': name, 'market': market,
            'pinyin_initials': initials,
            'pinyin_full': full_pinyin,
        })
    return index


def _fetch_full_stock_lists():
    """从 akshare 拉取三市场完整股票列表（仅代码+名称，不含实时行情）"""
    lists = {'a': [], 'etf': [], 'hk': []}
    try:
        # A股：stock_info_a_code_name 最可靠
        df = _retry_call(ak.stock_info_a_code_name, retries=3, delay=2.0)
        for _, row in df.iterrows():
            code = str(row.get('code', ''))
            name = str(row.get('name', ''))
            # 排除北交所（920/8开头）
            if code.startswith(('920', '8')) and len(code) == 6:
                continue
            if code and name:
                lists['a'].append({'code': code, 'name': name, 'market': 'a'})
    except Exception as e:
        logger.warning(f"akshare A股列表获取失败，降级到硬编码池: {e}")
        lists['a'] = [{'code': c, 'name': n, 'market': 'a'} for c, n in STOCK_POOL]

    try:
        # ETF：fund_etf_spot_em
        df = _retry_call(ak.fund_etf_spot_em, retries=3, delay=2.0)
        for _, row in df.iterrows():
            code = str(row.get('代码', ''))
            name = str(row.get('名称', ''))
            if code and name:
                lists['etf'].append({'code': code, 'name': name, 'market': 'etf'})
    except Exception as e:
        logger.warning(f"akshare ETF列表获取失败，降级到硬编码池: {e}")
        lists['etf'] = [{'code': c, 'name': n, 'market': 'etf'} for c, n in ETF_POOL]

    try:
        # 港股：stock_hk_spot
        df = _retry_call(ak.stock_hk_spot, retries=3, delay=2.0)
        for _, row in df.iterrows():
            code = str(row.get('代码', ''))
            name = str(row.get('中文名称', ''))
            if code and name:
                lists['hk'].append({'code': code, 'name': name, 'market': 'hk'})
    except Exception as e:
        logger.warning(f"akshare 港股列表获取失败，降级到硬编码池: {e}")
        lists['hk'] = [{'code': c, 'name': n, 'market': 'hk'} for c, n in HK_POOL]

    return lists


_FULL_LISTS_CACHE = None
_FULL_LISTS_TIME = 0


def _get_full_lists():
    """获取全量股票列表（带24小时缓存）"""
    global _FULL_LISTS_CACHE, _FULL_LISTS_TIME
    if _FULL_LISTS_CACHE is not None and (time.time() - _FULL_LISTS_TIME) < _SEARCH_INDEX_TTL:
        return _FULL_LISTS_CACHE
    _FULL_LISTS_CACHE = _fetch_full_stock_lists()
    _FULL_LISTS_TIME = time.time()
    return _FULL_LISTS_CACHE


def get_search_index():
    """获取搜索索引（懒加载，24小时刷新）"""
    global _SEARCH_INDEX, _SEARCH_INDEX_TIME
    if _SEARCH_INDEX is not None and (time.time() - _SEARCH_INDEX_TIME) < _SEARCH_INDEX_TTL:
        return _SEARCH_INDEX
    lists = _get_full_lists()
    total = sum(len(v) for v in lists.values())
    index = []
    for market in ('a', 'etf', 'hk'):
        index.extend(_build_pinyin_index_from_list(lists[market]))
    _SEARCH_INDEX = index
    _SEARCH_INDEX_TIME = time.time()
    logger.info(f"搜索索引已构建: {total} 只 (A股{len(lists['a'])} / ETF{len(lists['etf'])} / 港股{len(lists['hk'])})")
    return _SEARCH_INDEX


def _is_sh_code(code):
    """判断是否上海市场代码：5/6/9开头（5=沪市基金/ETF）"""
    return code.startswith(('5', '6', '9'))


def _get_secid(code, market='a'):
    """根据股票代码生成东方财富secid"""
    if market == 'hk':
        return f'116.{code}'  # 港股
    if _is_sh_code(code):
        return f'1.{code}'  # 上海
    else:
        return f'0.{code}'  # 深圳


def _get_sina_code(code, market='a'):
    """根据股票代码生成新浪格式代码"""
    if market == 'hk':
        return f'rt_hk{code}'  # 港股
    if _is_sh_code(code):
        return f'sh{code}'
    else:
        return f'sz{code}'


def _get_tx_code(code, market='a'):
    """根据股票代码生成腾讯格式代码"""
    if market == 'hk':
        return f'hk{code}'
    if _is_sh_code(code):
        return f'sh{code}'
    else:
        return f'sz{code}'


def _retry_call(func, retries=3, delay=1.0, *args, **kwargs):
    """带退避重试的调用包装（akshare数据源可能瞬态拒绝连接）"""
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(delay * (attempt + 1))


def _safe_float(val, default=0.0):
    """安全转float，处理 NaN/None/空字符串"""
    try:
        v = float(val)
        if np.isnan(v) or np.isinf(v):
            return default
        return v
    except (ValueError, TypeError):
        return default


def _safe_int(val, default=0):
    """安全转int，处理 NaN/None/空字符串"""
    return int(_safe_float(val, default))


class DataFetcher:
    """A股数据获取器"""

    def __init__(self):
        self._cache = {}
        self._cache_time = {}
        self._cache_ttl = 300  # 5分钟缓存
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })

    def _is_cache_valid(self, key):
        if key not in self._cache:
            return False
        elapsed = time.time() - self._cache_time.get(key, 0)
        return elapsed < self._cache_ttl

    def get_stock_list(self, market='a'):
        """获取股票池列表（去重，动态拉取全量）
        market: a=沪深A股, etf=场内ETF, hk=港股
        """
        lists = _get_full_lists()
        raw = lists.get(market, [])
        seen = set()
        result = []
        for item in raw:
            code = item['code']
            if code not in seen:
                seen.add(code)
                result.append({'code': code, 'name': item['name']})
        return result

    # ========== akshare 批量行情（全市场一次性获取） ==========

    def _fetch_akshare_a_quotes(self):
        """akshare A股全量实时行情 (stock_zh_a_spot, 新浪源)"""
        try:
            df = _retry_call(ak.stock_zh_a_spot, retries=3, delay=2.0)
            results = []
            for _, row in df.iterrows():
                raw_code = str(row.get('代码', ''))
                if raw_code.startswith('bj'):
                    continue
                code = raw_code[2:] if raw_code[:2] in ('sh', 'sz') else raw_code
                name = str(row.get('名称', ''))
                if 'ST' in name or '退' in name:
                    continue
                current = _safe_float(row.get('最新价'))
                pre_close = _safe_float(row.get('昨收'))
                if current <= 0 or pre_close <= 0:
                    continue
                pct = _safe_float(row.get('涨跌幅'))
                results.append({
                    'code': code, 'name': name, 'price': current,
                    'pct_change': round(pct, 2),
                    'change': round(current - pre_close, 2),
                    'volume': _safe_int(row.get('成交量')),
                    'amount': _safe_float(row.get('成交额')),
                    'high': _safe_float(row.get('最高')),
                    'low': _safe_float(row.get('最低')),
                    'open': _safe_float(row.get('今开')),
                    'pre_close': pre_close,
                })
            logger.info(f"akshare A股行情: {len(results)} 只")
            return results
        except Exception as e:
            logger.warning(f"akshare A股行情获取失败，降级到新浪批量: {e}")
            return None

    def _fetch_akshare_etf_quotes(self):
        """akshare ETF全量实时行情 (fund_etf_spot_em, 东方财富源)"""
        try:
            df = _retry_call(ak.fund_etf_spot_em, retries=3, delay=2.0)
            results = []
            for _, row in df.iterrows():
                code = str(row.get('代码', ''))
                name = str(row.get('名称', ''))
                current = _safe_float(row.get('最新价'))
                if current <= 0:
                    continue
                pct = _safe_float(row.get('涨跌幅'))
                results.append({
                    'code': code, 'name': name, 'price': current,
                    'pct_change': round(pct, 2),
                    'change': _safe_float(row.get('涨跌额')),
                    'volume': _safe_int(row.get('成交量')),
                    'amount': _safe_float(row.get('成交额')),
                    'high': _safe_float(row.get('最高')),
                    'low': _safe_float(row.get('最低')),
                    'open': _safe_float(row.get('开盘价')),
                    'pre_close': _safe_float(row.get('昨收价')),
                })
            logger.info(f"akshare ETF行情: {len(results)} 只")
            return results
        except Exception as e:
            logger.warning(f"akshare ETF行情获取失败，降级到新浪批量: {e}")
            return None

    def _fetch_akshare_hk_quotes(self):
        """akshare 港股全量实时行情 (stock_hk_spot, 新浪源)"""
        try:
            df = _retry_call(ak.stock_hk_spot, retries=3, delay=2.0)
            results = []
            for _, row in df.iterrows():
                code = str(row.get('代码', ''))
                name = str(row.get('中文名称', ''))
                current = _safe_float(row.get('最新价'))
                if current <= 0:
                    continue
                pct = _safe_float(row.get('涨跌幅'))
                results.append({
                    'code': code, 'name': name, 'price': current,
                    'pct_change': round(pct, 2),
                    'change': _safe_float(row.get('涨跌额')),
                    'volume': 0, 'amount': 0,
                    'high': 0, 'low': 0, 'open': 0, 'pre_close': 0,
                })
            logger.info(f"akshare 港股行情: {len(results)} 只")
            return results
        except Exception as e:
            logger.warning(f"akshare 港股行情获取失败，降级到新浪批量: {e}")
            return None

    def _fetch_sina_quotes(self, codes, name_map):
        """新浪A股/ETF批量实时行情"""
        results = []
        batch_size = 50
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            sina_codes = [_get_sina_code(c, 'a') for c in batch]
            url = f'https://hq.sinajs.cn/list={",".join(sina_codes)}'

            try:
                headers = {'Referer': 'https://finance.sina.com.cn'}
                resp = self._session.get(url, headers=headers, timeout=10)
                lines = resp.text.strip().split('\n')

                for line in lines:
                    m = re.match(r'var hq_str_(\w+)="(.+)";', line.strip())
                    if not m:
                        continue
                    sina_code = m.group(1)
                    fields = m.group(2).split(',')
                    if len(fields) < 10:
                        continue

                    code = sina_code[2:]  # 去掉sh/sz前缀
                    name = fields[0] or name_map.get(code, '')
                    open_p = float(fields[1]) if fields[1] else 0
                    pre_close = float(fields[2]) if fields[2] else 0
                    current = float(fields[3]) if fields[3] else 0
                    high = float(fields[4]) if fields[4] else 0
                    low = float(fields[5]) if fields[5] else 0
                    volume = int(float(fields[8])) if fields[8] else 0
                    amount = float(fields[9]) if fields[9] else 0

                    if current <= 0 or pre_close <= 0:
                        continue

                    pct_change = (current - pre_close) / pre_close * 100
                    change = current - pre_close

                    # 过滤ST和退市
                    if 'ST' in name or '退' in name:
                        continue

                    results.append({
                        'code': code,
                        'name': name,
                        'price': current,
                        'pct_change': round(pct_change, 2),
                        'change': round(change, 2),
                        'volume': volume,
                        'amount': amount,
                        'high': high,
                        'low': low,
                        'open': open_p,
                        'pre_close': pre_close
                    })
            except Exception as e:
                logger.error(f"批量行情获取失败(批次{i // batch_size}): {e}")

            time.sleep(0.1)  # 避免请求过快

        return results

    def _fetch_hk_quotes(self, codes, name_map):
        """新浪港股实时行情（rt_hk 前缀，字段顺序与A股不同）"""
        results = []
        batch_size = 40
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            hk_codes = [f'rt_hk{c}' for c in batch]
            url = f'https://hq.sinajs.cn/list={",".join(hk_codes)}'

            try:
                headers = {'Referer': 'https://finance.sina.com.cn'}
                resp = self._session.get(url, headers=headers, timeout=10)
                resp.encoding = 'gbk'
                lines = resp.text.strip().split('\n')

                for line in lines:
                    m = re.match(r'var hq_str_rt_hk(\w+)="(.+)";', line.strip())
                    if not m:
                        continue
                    code = m.group(1)
                    fields = m.group(2).split(',')
                    if len(fields) < 12:
                        continue

                    # 港股字段: 0英文名 1中文名 2昨收 3今开 4最高 5最低 6现价 7涨跌 8涨跌幅 ...
                    name = fields[1] or name_map.get(code, '')
                    pre_close = float(fields[2]) if fields[2] else 0
                    open_p = float(fields[3]) if fields[3] else 0
                    high = float(fields[4]) if fields[4] else 0
                    low = float(fields[5]) if fields[5] else 0
                    current = float(fields[6]) if fields[6] else 0
                    change = float(fields[7]) if fields[7] else 0
                    pct_change = float(fields[8]) if fields[8] else 0
                    amount = float(fields[11]) if len(fields) > 11 and fields[11] else 0
                    volume = int(float(fields[12])) if len(fields) > 12 and fields[12] else 0

                    if current <= 0 or pre_close <= 0:
                        continue

                    results.append({
                        'code': code,
                        'name': name,
                        'price': current,
                        'pct_change': round(pct_change, 2),
                        'change': round(change, 2),
                        'volume': volume,
                        'amount': amount,
                        'high': high,
                        'low': low,
                        'open': open_p,
                        'pre_close': pre_close
                    })
            except Exception as e:
                logger.error(f"港股行情获取失败(批次{i // batch_size}): {e}")

            time.sleep(0.1)

        return results

    def get_realtime_quotes(self, codes=None, market='a'):
        """
        获取实时行情
        codes: 股票代码列表，不传则获取全市场行情（优先 akshare 批量）
        market: a=沪深A股, etf=场内ETF, hk=港股
        """
        if codes is None:
            # 全市场扫描：优先 akshare 批量接口
            cache_key = f'bulk_quotes_{market}'
            if self._is_cache_valid(cache_key):
                return self._cache[cache_key]

            bulk = None
            if market == 'a':
                bulk = self._fetch_akshare_a_quotes()
            elif market == 'etf':
                bulk = self._fetch_akshare_etf_quotes()
            elif market == 'hk':
                bulk = self._fetch_akshare_hk_quotes()

            if bulk:
                self._cache[cache_key] = bulk
                self._cache_time[cache_key] = time.time()
                return bulk

            # 降级：新浪批量获取硬编码池（全量太慢）
            logger.warning(f"akshare {market} 批量行情失败，降级到硬编码池新浪批量")
            pool = MARKET_POOLS.get(market, STOCK_POOL)
            fb_codes = [c for c, n in pool]
            fb_names = {c: n for c, n in pool}
            if market == 'hk':
                return self._fetch_hk_quotes(fb_codes, fb_names)
            return self._fetch_sina_quotes(fb_codes, fb_names)

        # 指定代码：新浪批量（小批量快速获取）
        stock_list = self.get_stock_list(market)
        name_map = {s['code']: s['name'] for s in stock_list}
        # 补充不在列表中的代码
        for c in codes:
            if c not in name_map:
                name_map[c] = c
        if market == 'hk':
            return self._fetch_hk_quotes(codes, name_map)
        return self._fetch_sina_quotes(codes, name_map)

    def _fetch_tx_kline(self, symbol, market, days=120):
        """腾讯历史K线（A股/ETF用 fqkline，港股用 hkfqkline）"""
        tx_code = _get_tx_code(symbol, market)
        try:
            if market == 'hk':
                url = 'https://web.ifzq.gtimg.cn/appstock/app/hkfqkline/get'
            else:
                url = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
            params = {'param': f'{tx_code},day,,,{days},qfq'}
            resp = self._session.get(url, params=params, timeout=15)
            data = resp.json()

            node = data.get('data', {}).get(tx_code, {})
            rows = node.get('qfqday') or node.get('day') or []
            if not rows:
                return pd.DataFrame()

            records = []
            prev_close = None
            for item in rows:
                date_str = item[0]
                open_p = float(item[1])
                close = float(item[2])
                high = float(item[3])
                low = float(item[4])
                volume = float(item[5]) if len(item) > 5 else 0

                if prev_close and prev_close > 0:
                    pct_change = (close - prev_close) / prev_close * 100
                    change = close - prev_close
                else:
                    pct_change = 0
                    change = 0

                records.append({
                    'date': pd.to_datetime(date_str),
                    'open': open_p,
                    'close': close,
                    'high': high,
                    'low': low,
                    'volume': volume,
                    'amount': volume * close,
                    'amplitude': (high - low) / prev_close * 100 if prev_close and prev_close > 0 else 0,
                    'pct_change': pct_change,
                    'change': change,
                    'turnover': 0
                })
                prev_close = close

            df = pd.DataFrame(records)
            if df.empty:
                return pd.DataFrame()
            if len(df) > days:
                df = df.tail(days).reset_index(drop=True)
            return df
        except Exception as e:
            logger.error(f"腾讯K线获取失败({tx_code}): {e}")
            return pd.DataFrame()

    def get_stock_history(self, symbol, days=120, market='a'):
        """获取个股历史日K数据
        market: a=沪深A股, etf=场内ETF, hk=港股
        A股走新浪K线API，ETF/港股走腾讯K线API
        """
        cache_key = f"hist_{market}_{symbol}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        if market in ('etf', 'hk'):
            df = self._fetch_tx_kline(symbol, market, days)
            if not df.empty:
                self._cache[cache_key] = df
                self._cache_time[cache_key] = time.time()
            return df

        try:
            sina_code = _get_sina_code(symbol, 'a')
            url = 'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData'
            params = {
                'symbol': sina_code,
                'scale': '240',   # 日K（240分钟）
                'ma': 'no',
                'datalen': str(days + 30)
            }

            resp = self._session.get(url, params=params, timeout=15)
            data = resp.json()

            if not data:
                return pd.DataFrame()

            records = []
            prev_close = None
            for item in data:
                open_p = float(item['open'])
                close = float(item['close'])
                high = float(item['high'])
                low = float(item['low'])
                volume = float(item['volume'])

                if prev_close and prev_close > 0:
                    pct_change = (close - prev_close) / prev_close * 100
                    change = close - prev_close
                else:
                    pct_change = 0
                    change = 0

                records.append({
                    'date': pd.to_datetime(item['day']),
                    'open': open_p,
                    'close': close,
                    'high': high,
                    'low': low,
                    'volume': volume,
                    'amount': volume * close,  # 估算成交额
                    'amplitude': (high - low) / prev_close * 100 if prev_close and prev_close > 0 else 0,
                    'pct_change': pct_change,
                    'change': change,
                    'turnover': 0
                })
                prev_close = close

            df = pd.DataFrame(records)
            if df.empty:
                return pd.DataFrame()

            # 只保留最近days天
            if len(df) > days:
                df = df.tail(days).reset_index(drop=True)

            self._cache[cache_key] = df
            self._cache_time[cache_key] = time.time()
            return df

        except Exception as e:
            logger.error(f"获取{symbol}历史数据失败: {e}")
            return pd.DataFrame()

    def get_stock_news(self, symbol, market='a'):
        """获取个股新闻（akshare，仅A股可用；港股/ETF返回空列表）"""
        if market != 'a':
            return []
        try:
            df = _retry_call(ak.stock_news_em, symbol=symbol)
            if df is None or df.empty:
                return []
            result = []
            for _, row in df.head(15).iterrows():
                result.append({
                    'title': str(row.get('新闻标题', '')),
                    'content': str(row.get('新闻内容', ''))[:200],
                    'date': str(row.get('发布时间', '')),
                    'source': str(row.get('文章来源', '')),
                    'url': str(row.get('新闻链接', ''))
                })
            return result
        except Exception as e:
            logger.error(f"获取{symbol}新闻失败: {e}")
            return []

    def get_market_news(self):
        """获取市场财经新闻"""
        try:
            df = ak.news_economic_baidu(symbol="全部", date=datetime.now().strftime("%Y%m%d"))
            if df is not None and not df.empty:
                result = []
                for _, row in df.head(20).iterrows():
                    result.append({
                        'title': str(row.get('title', '')),
                        'content': str(row.get('content', ''))[:200],
                        'date': str(row.get('date', '')),
                        'source': '百度财经'
                    })
                return result
        except:
            pass

        # 备用：从股票池中获取热门股票的新闻
        try:
            # 取几只热门股票的新闻聚合
            popular = ['600519', '000001', '300750', '601318', '000858']
            all_news = []
            for code in popular:
                news = self.get_stock_news(code)
                for n in news[:3]:
                    n['source'] = f"个股新闻-{n.get('source','')}"
                    all_news.append(n)
                if len(all_news) >= 20:
                    break
                time.sleep(0.2)
            return all_news[:20]
        except:
            return []

    def get_sector_performance(self):
        """获取板块行情（使用新浪指数数据近似）"""
        # 由于板块API不稳定，使用主要行业ETF/指数代替
        sector_indices = [
            ('银行', 'sh000012'), ('证券', 'sz399975'), ('医药', 'sh000037'),
            ('消费', 'sz399932'), ('科技', 'sz399905'), ('军工', 'sh000819'),
            ('新能源', 'sz399808'), ('半导体', 'sz399959'),
        ]
        result = []
        sina_codes = [c for _, c in sector_indices]
        try:
            headers = {'Referer': 'https://finance.sina.com.cn'}
            url = f'https://hq.sinajs.cn/list={",".join(sina_codes)}'
            resp = self._session.get(url, headers=headers, timeout=10)
            lines = resp.text.strip().split('\n')
            for i, line in enumerate(lines):
                m = re.match(r'var hq_str_(\w+)="(.+)";', line.strip())
                if m and i < len(sector_indices):
                    fields = m.group(2).split(',')
                    if len(fields) >= 4:
                        name = sector_indices[i][0]
                        pre_close = float(fields[2]) if fields[2] else 1
                        current = float(fields[3]) if fields[3] else 0
                        pct = (current - pre_close) / pre_close * 100 if pre_close else 0
                        result.append({
                            'name': name,
                            'pct_change': round(pct, 2),
                            'lead_stock': '',
                            'lead_pct': 0
                        })
        except Exception as e:
            logger.error(f"获取板块行情失败: {e}")
        return sorted(result, key=lambda x: x['pct_change'], reverse=True)

    def get_hot_stocks(self):
        """获取热门股票/涨幅榜/成交额榜"""
        quotes = self.get_realtime_quotes()
        if not quotes:
            return {'top_gainers': [], 'top_volume': []}

        # 涨幅前10
        top_gainers = sorted(quotes, key=lambda x: x.get('pct_change', 0), reverse=True)[:10]
        # 成交额前10
        top_volume = sorted(quotes, key=lambda x: x.get('amount', 0), reverse=True)[:10]

        return {
            'top_gainers': [{'code': s['code'], 'name': s['name'], 'price': s['price'],
                            'pct_change': s['pct_change'], 'amount': s['amount']} for s in top_gainers],
            'top_volume': [{'code': s['code'], 'name': s['name'], 'price': s['price'],
                           'pct_change': s['pct_change'], 'amount': s['amount']} for s in top_volume]
        }

    def get_fundamental_info(self, symbol, market='a'):
        """
        获取基本面数据（腾讯行情API）
        返回: {pe, pb, total_mv(亿), float_mv(亿), turnover_rate, name, code, price}
        market: a=沪深A股, etf=场内ETF, hk=港股
        注意：港股PB在字段[47]（A股在[46]）；ETF无PE/PB
        """
        cache_key = f"fund_{market}_{symbol}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        try:
            tx_code = _get_tx_code(symbol, market)

            url = f'https://qt.gtimg.cn/q={tx_code}'
            resp = self._session.get(url, timeout=10)
            resp.encoding = 'gbk'
            line = resp.text.strip()
            if '="' not in line:
                return None

            val = line.split('="', 1)[1].rstrip('";')
            fields = val.split('~')
            if len(fields) < 50:
                return None

            def _f(idx, default=0):
                try:
                    return float(fields[idx]) if fields[idx] else default
                except (ValueError, IndexError):
                    return default

            # 港股PB在[47]（[46]为英文名），A股PB在[46]
            pb_idx = 47 if market == 'hk' else 46

            result = {
                'code': symbol,
                'name': fields[1],
                'price': _f(3),
                'pe': _f(39),          # 市盈率(动)
                'pb': _f(pb_idx),      # 市净率
                'total_mv': _f(45),    # 总市值(亿)
                'float_mv': _f(44),    # 流通市值(亿)
                'turnover_rate': _f(38),  # 换手率
                'pe_ttm': _f(53, 0),   # 市盈率TTM
            }
            if result['pe'] <= 0:
                result['pe'] = result.get('pe_ttm', 0)

            self._cache[cache_key] = result
            self._cache_time[cache_key] = time.time()
            return result
        except Exception as e:
            logger.error(f"获取{symbol}基本面失败: {e}")
            return None

    def get_financial_abstract(self, symbol, market='a'):
        """获取财务指标摘要（akshare，缓存6小时；仅A股可用）"""
        if market != 'a':
            return {}
        cache_key = f"fin_abs_{symbol}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        if cache_key in self._cache_time and (time.time() - self._cache_time[cache_key]) < 21600:
            return self._cache[cache_key]

        try:
            import akshare as ak
            df = ak.stock_financial_abstract(symbol=symbol)
            if df is None or df.empty:
                return {}

            # 只取最新一期的常用指标
            result = {}
            # 前两列是 选项/指标
            data_cols = df.columns[2:]
            latest_col = data_cols[0] if len(data_cols) > 0 else None

            indicator_map = {
                '归母净利润': 'net_profit',
                '营业总收入': 'revenue',
                '净资产收益率': 'roe',
                '每股收益': 'eps',
                '资产负债率': 'debt_ratio',
                '毛利率': 'gross_margin',
                '净利率': 'net_margin'
            }

            for _, row in df.iterrows():
                indicator = str(row.get('指标', ''))
                if indicator in indicator_map:
                    key = indicator_map[indicator]
                    if latest_col and latest_col in df.columns:
                        val = row.get(latest_col, None)
                        # 指标可能是 "常用指标"/"同比增长"/"单季度" 等选项
                        option = str(row.get('选项', ''))
                        if option in ('常用指标', '同比增长', '按报告期'):
                            result[f"{key}_{option}"] = val
                            if option == '常用指标' and key not in result:
                                result[key] = val

            # 计算同比增长率（最新一期 vs 去年同期）
            for _, row in df.iterrows():
                indicator = str(row.get('指标', ''))
                option = str(row.get('选项', ''))
                if option == '同比增长' and indicator in ('归母净利润', '营业总收入'):
                    key = 'net_profit_yoy' if indicator == '归母净利润' else 'revenue_yoy'
                    if latest_col and latest_col in df.columns:
                        val = row.get(latest_col, None)
                        try:
                            result[key] = float(val)
                        except (TypeError, ValueError):
                            result[key] = None

            self._cache[cache_key] = result
            self._cache_time[cache_key] = time.time()
            return result
        except Exception as e:
            logger.error(f"获取{symbol}财务摘要失败: {e}")
            return {}

    def get_index_data(self):
        """获取主要指数数据（新浪API）"""
        indices = [
            ('上证指数', 'sh000001'), ('深证成指', 'sz399001'),
            ('创业板指', 'sz399006'), ('科创50', 'sh000688')
        ]
        result = []
        sina_codes = [c for _, c in indices]
        try:
            headers = {'Referer': 'https://finance.sina.com.cn'}
            url = f'https://hq.sinajs.cn/list={",".join(sina_codes)}'
            resp = self._session.get(url, headers=headers, timeout=10)
            lines = resp.text.strip().split('\n')
            for i, line in enumerate(lines):
                m = re.match(r'var hq_str_(\w+)="(.+)";', line.strip())
                if m and i < len(indices):
                    fields = m.group(2).split(',')
                    if len(fields) >= 4:
                        name = indices[i][0]
                        code = indices[i][1]
                        pre_close = float(fields[2]) if fields[2] else 1
                        current = float(fields[3]) if fields[3] else 0
                        pct = (current - pre_close) / pre_close * 100 if pre_close else 0
                        result.append({
                            'name': name,
                            'code': code,
                            'price': current,
                            'pct_change': round(pct, 2)
                        })
        except Exception as e:
            logger.error(f"获取指数数据失败: {e}")
        return result
