# -*- coding: utf-8 -*-
"""
AI Client - 多模型AI智能分析客户端
借鉴 stock-scanner 思路：
  - 支持多种 OpenAI 兼容 API（DeepSeek/OpenAI/智谱/通义）
  - AI 不可用时自动降级到规则引擎分析
  - 配置本地存储 config.json
"""
import json
import os
import time
import logging
import threading

logger = logging.getLogger(__name__)

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

# 支持的AI服务商
AI_PROVIDERS = {
    'deepseek': {
        'name': 'DeepSeek',
        'base_url': 'https://api.deepseek.com/v1',
        'models': ['deepseek-chat', 'deepseek-reasoner']
    },
    'openai': {
        'name': 'OpenAI',
        'base_url': 'https://api.openai.com/v1',
        'models': ['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo']
    },
    'zhipu': {
        'name': '智谱AI',
        'base_url': 'https://open.bigmodel.cn/api/paas/v4',
        'models': ['glm-4-plus', 'glm-4-flash', 'glm-4-air']
    },
    'qwen': {
        'name': '通义千问',
        'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'models': ['qwen-plus', 'qwen-turbo', 'qwen-max']
    },
    'moonshot': {
        'name': 'Kimi',
        'base_url': 'https://api.moonshot.cn/v1',
        'models': ['moonshot-v1-8k', 'moonshot-v1-32k']
    },
    'siliconflow': {
        'name': '硅基流动',
        'base_url': 'https://api.siliconflow.cn/v1',
        'models': ['deepseek-ai/DeepSeek-V3', 'Qwen/Qwen2.5-72B-Instruct']
    },
    'ollama': {
        'name': 'Ollama本地',
        'base_url': 'http://localhost:11434/v1',
        'models': ['qwen3:32b', 'deepseek-r1:14b', 'llama3.1:8b'],
        'local': True,
        'no_key': True,  # 本地模型无需API Key
        'hint': '本地Ollama服务，无需API Key。模型列表自动从本地拉取。'
    }
}

# 无需API Key的提供商（本地模型）
NO_KEY_PROVIDERS = {'ollama'}

DEFAULT_CONFIG = {
    'ai': {
        'enabled': False,
        'provider': 'deepseek',
        'api_key': '',
        'model': 'deepseek-chat',
        'base_url': 'https://api.deepseek.com/v1',
        'temperature': 0.3,
        'timeout': 90,
        'max_tokens': 2000
    }
}

_config_lock = threading.Lock()


def load_config():
    """加载配置文件"""
    with _config_lock:
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                # 合并默认值
                merged = json.loads(json.dumps(DEFAULT_CONFIG))
                merged['ai'].update(config.get('ai', {}))
                return merged
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
        return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(config):
    """保存配置文件"""
    with _config_lock:
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False


def get_ai_config():
    """获取AI配置（隐藏完整key）"""
    config = load_config()
    ai = config.get('ai', {})
    api_key = ai.get('api_key', '')
    masked = ''
    if api_key:
        masked = api_key[:4] + '***' + api_key[-4:] if len(api_key) > 10 else '***'

    provider_info = dict(AI_PROVIDERS.get(ai.get('provider', ''), {}))
    # ollama：动态拉取本地模型
    if ai.get('provider') == 'ollama':
        provider_info['models'] = get_ollama_models(ai.get('base_url', '')) or provider_info.get('models', [])
    return {
        'enabled': bool(ai.get('enabled', False)),
        'provider': ai.get('provider', 'deepseek'),
        'provider_name': provider_info.get('name', ai.get('provider', '')),
        'models': provider_info.get('models', []),
        'model': ai.get('model', ''),
        'base_url': ai.get('base_url', ''),
        'api_key_masked': masked,
        'has_api_key': bool(api_key),
        'temperature': ai.get('temperature', 0.3),
        'local': bool(provider_info.get('local', False)),
        'no_key': bool(provider_info.get('no_key', False)),
        'hint': provider_info.get('hint', '')
    }


def update_ai_config(new_ai):
    """更新AI配置"""
    config = load_config()
    old_ai = config.get('ai', {})
    # 只更新非空字段；api_key 为空字符串时保留原值（除非显式传 __clear__）
    if 'api_key' in new_ai:
        if new_ai['api_key'] and new_ai['api_key'] != '***':
            old_ai['api_key'] = new_ai['api_key']
        elif new_ai.get('clear_key'):
            old_ai['api_key'] = ''

    for field in ['enabled', 'provider', 'model', 'base_url', 'temperature', 'timeout', 'max_tokens']:
        if field in new_ai:
            old_ai[field] = new_ai[field]

    # provider 切换时自动切换默认模型和 base_url
    provider = old_ai.get('provider', 'deepseek')
    if provider in AI_PROVIDERS:
        pinfo = AI_PROVIDERS[provider]
        # ollama：动态拉取本地模型作为候选
        if provider == 'ollama':
            local_models = get_ollama_models()
            if local_models:
                pinfo = {**pinfo, 'models': local_models}
        if not old_ai.get('model') or old_ai.get('model') not in pinfo['models']:
            old_ai['model'] = pinfo['models'][0]
        old_ai['base_url'] = pinfo['base_url']
        # 无需API Key的本地模型自动清空key
        if provider in NO_KEY_PROVIDERS:
            old_ai['api_key'] = ''

    config['ai'] = old_ai
    return save_config(config)


def get_ollama_models(base_url=None):
    """拉取本地Ollama已安装模型列表"""
    try:
        import requests
        base = (base_url or load_config().get('ai', {}).get('base_url', '')
                or AI_PROVIDERS['ollama']['base_url'])
        # ollama原生接口 /api/tags
        tags_url = base.rstrip('/').replace('/v1', '') + '/api/tags'
        resp = requests.get(tags_url, timeout=5)
        if resp.status_code == 200:
            models = [m.get('name', '') for m in resp.json().get('models', [])]
            if models:
                return models
    except Exception as e:
        logger.debug(f"获取Ollama模型列表失败: {e}")
    return AI_PROVIDERS['ollama']['models']


class AIClient:
    """AI分析客户端（OpenAI兼容接口）"""

    def __init__(self):
        self._session = None
        self._last_error = None
        self._last_error_time = 0

    def _get_session(self):
        """延迟创建requests session"""
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
        return self._session

    def is_available(self):
        """检查AI是否可用（本地ollama无需API Key）"""
        config = load_config()
        ai = config.get('ai', {})
        if not ai.get('enabled'):
            return False
        provider = ai.get('provider', '')
        if provider not in NO_KEY_PROVIDERS and not ai.get('api_key'):
            return False
        # 错误冷却：最近60秒内有错误则视为不可用
        if self._last_error and (time.time() - self._last_error_time) < 60:
            return False
        return True

    def status(self):
        """获取AI状态详情"""
        cfg = get_ai_config()
        cfg['available'] = self.is_available()
        provider = cfg.get('provider', '')
        if not cfg['enabled']:
            cfg['reason'] = 'AI功能未启用，请在设置中启用AI'
        elif provider in NO_KEY_PROVIDERS:
            if self._last_error and (time.time() - self._last_error_time) < 60:
                cfg['reason'] = f'最近调用失败: {self._last_error}'
            else:
                cfg['reason'] = '本地Ollama已启用（无需API Key）'
        elif not cfg['has_api_key']:
            cfg['reason'] = '未配置API Key，将使用内置规则引擎分析'
        elif self._last_error and (time.time() - self._last_error_time) < 60:
            cfg['reason'] = f'最近调用失败: {self._last_error}'
        else:
            cfg['reason'] = 'AI服务可用'
        return cfg

    def chat(self, messages, stream=False, temperature=None, max_tokens=None):
        """
        调用AI聊天接口
        返回 (success, content) ；stream=True 时返回 (success, generator)
        """
        config = load_config()
        ai = config.get('ai', {})
        provider = ai.get('provider', '')
        if provider not in NO_KEY_PROVIDERS and not ai.get('api_key'):
            return False, "未配置API Key"

        base_url = ai.get('base_url', '').rstrip('/')
        url = f"{base_url}/chat/completions"
        payload = {
            'model': ai.get('model', 'deepseek-chat'),
            'messages': messages,
            'temperature': temperature if temperature is not None else ai.get('temperature', 0.3),
            'max_tokens': max_tokens if max_tokens is not None else ai.get('max_tokens', 2000),
            'stream': stream
        }

        headers = {'Content-Type': 'application/json'}
        if provider not in NO_KEY_PROVIDERS:
            headers['Authorization'] = f"Bearer {ai['api_key']}"

        try:
            session = self._get_session()
            resp = session.post(url, json=payload, headers=headers,
                                timeout=ai.get('timeout', 90), stream=stream)
            if resp.status_code != 200:
                err = resp.text[:200]
                self._last_error = f"HTTP {resp.status_code}: {err}"
                self._last_error_time = time.time()
                return False, self._last_error

            if stream:
                return True, self._iter_stream(resp)
            else:
                data = resp.json()
                content = data['choices'][0]['message']['content']
                self._last_error = None
                return True, content
        except Exception as e:
            self._last_error = str(e)
            self._last_error_time = time.time()
            logger.error(f"AI调用失败: {e}")
            return False, str(e)

    @staticmethod
    def _iter_stream(resp):
        """流式解析SSE响应"""
        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode('utf-8', errors='ignore')
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                break
            try:
                import json as _json
                chunk = _json.loads(data)
                delta = chunk['choices'][0].get('delta', {})
                content = delta.get('content', '')
                if content:
                    yield content
            except Exception:
                continue

    def analyze_stock(self, prompt):
        """非流式分析股票（一次调用）"""
        messages = [
            {"role": "system", "content": "你是一位专业的A股量化分析师，精通技术分析、基本面分析和市场情绪分析，"
                                          "擅长为投资者提供可执行的买卖建议。分析时请注意：1) 给出明确的观点和操作建议；"
                                          "2) 说明买入/卖出的具体理由；3) 给出具体的价格区间；4) 提示潜在风险；"
                                          "5) 语气专业客观，不夸大收益。输出使用简洁的Markdown格式。"},
            {"role": "user", "content": prompt}
        ]
        return self.chat(messages)

    def analyze_stock_stream(self, prompt):
        """流式分析股票"""
        messages = [
            {"role": "system", "content": "你是一位专业的A股量化分析师，精通技术分析、基本面分析和市场情绪分析，"
                                          "擅长为投资者提供可执行的买卖建议。分析时请注意：1) 给出明确的观点和操作建议；"
                                          "2) 说明买入/卖出的具体理由；3) 给出具体的价格区间；4) 提示潜在风险；"
                                          "5) 语气专业客观，不夸大收益。输出使用简洁的Markdown格式。"},
            {"role": "user", "content": prompt}
        ]
        return self.chat(messages, stream=True)


# 全局AI客户端实例
_ai_client = None


def get_ai_client():
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client


if __name__ == '__main__':
    # 快速测试
    logging.basicConfig(level=logging.INFO)
    cfg = get_ai_config()
    print(json.dumps(cfg, ensure_ascii=False, indent=2))
    client = get_ai_client()
    print(f"AI可用: {client.is_available()}")
