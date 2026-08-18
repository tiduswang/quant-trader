# 量化交易分析系统 (quant-trader)

一个基于 Flask 的本地量化分析 Web 程序，覆盖 A股 / ETF / 港股三大市场（约 9500+ 只标的全量池），提供：

- **实时行情与个股分析**：K线走势、技术指标（MA / RSI / MACD / 布林带 / KDJ / 支撑压力位）
- **推荐股（选股）引擎**：采用 stock-scanner 三维度评分体系
  - 综合评分 = 技术面 × 0.4 + 基本面 × 0.4 + 情绪面 × 0.2（权重可调）
  - 信号 7 档分级：强烈推荐买入 / 推荐买入 / 建议买入 / 谨慎买入 / 持有观望 / 建议减仓 / 建议卖出
  - **筛选模式**：可按行业板块（496个）选股、按指定股票代码分析、设定 AI 深度解读的最低综合分
  - **流式进度**：扫描全程显示进度条、阶段提示与剩余时间预估，不再"长时间无反馈"
- **AI 智能分析**：支持硅基流动、DeepSeek 等云端大模型，也支持本地 Ollama
- **选股参数可调**：技术面 / 基本面 / 情绪面的全部权重、阈值、加减分值均可在网页上调节并持久化
- **拼音/代码/名称搜索**：全市场模糊搜索
- **三市场扫描**：A股 5200+、ETF 1500+、港股 2700+ 全量扫描

---

## 一、程序位置（本机）

```
C:\Users\sony_\WorkBuddy\2026-08-14-22-57-08\quant-trader\
```

### 目录结构

```
quant-trader/
├── app.py                      # Flask 主程序（Web 服务入口，端口 5003）
├── data_fetcher.py             # 行情/财务/新闻数据抓取（akshare + 新浪）
├── analysis_engine.py          # 技术指标计算（MA/RSI/MACD/布林带等）
├── recommendation_engine.py    # 技术面评分
├── fundamental_engine.py       # 基本面评分
├── sentiment_engine.py         # 情绪面评分（新闻利好/利空）
├── ai_recommendation_engine.py # 综合评分 + 信号分级 + AI 解读
├── strategy_params.py          # 选股参数管理（默认值/读写/持久化）
├── ai_client.py                # AI 大模型客户端（云端/本地 Ollama）
├── config.json                 # 配置文件（AI 密钥、选股参数）
├── requirements.txt            # Python 依赖清单
├── test_strategy.py            # 评分逻辑离线自测脚本
├── templates/
│   └── index.html              # 前端页面
└── static/
    ├── css/style.css
    └── js/app.js               # 前端交互逻辑
```

> 无需数据库；数据全部实时抓取，配置持久化在 `config.json`。

---

## 二、在其他电脑安装运行

### 前置要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows / macOS / Linux 均可 |
| Python | **3.10 及以上**（开发环境为 3.13） |
| 网络 | 需能访问国内财经数据源（新浪、东方财富） |

### 第 1 步：拷贝程序

把整个 `quant-trader` 文件夹复制到目标电脑（U盘、网盘、git 仓库均可）。
以下文件**不要**拷贝，属本机运行残留：

```
__pycache__/        # Python 缓存
server.log          # 运行日志
test_analysis.json  # 测试残留
```

### 第 2 步：安装 Python 依赖

在 `quant-trader` 目录下打开终端（Windows 可用 PowerShell 或 CMD）：

```bash
# 建议先创建虚拟环境（可选但推荐）
python -m venv venv

# Windows 激活虚拟环境
venv\Scripts\activate
# macOS / Linux 激活虚拟环境
# source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

如不建虚拟环境，直接执行：

```bash
pip install -r requirements.txt
```

> 国内网络若安装慢，可换源：`pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

### 第 3 步：配置 AI（可选）

程序不配 AI 也能跑（行情、评分、选股全部可用），只是没有"AI 解读"文案。

先把配置模板复制一份：

```bash
cp config.example.json config.json    # Windows CMD: copy config.example.json config.json
```

然后编辑 `config.json` 的 `ai` 节：

```json
{
  "ai": {
    "enabled": true,
    "provider": "siliconflow",
    "api_key": "你的API密钥",
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "base_url": "https://api.siliconflow.cn/v1",
    "temperature": 0.3,
    "timeout": 60,
    "max_tokens": 2000
  }
}
```

常用 provider 任选其一：

| provider | base_url | 说明 |
|---|---|---|
| `siliconflow` | https://api.siliconflow.cn/v1 | 硅基流动（有免费模型） |
| `deepseek` | https://api.deepseek.com/v1 | DeepSeek 官方 |
| `ollama` | http://localhost:11434/v1 | 本地 Ollama（免密钥，需先装 Ollama 并拉取模型） |

也可以启动后在网页的 **设置（AI配置）** 界面里填写并保存，效果相同。

### 第 4 步：启动

```bash
python app.py
```

看到类似以下输出即成功：

```
 * Running on http://0.0.0.0:5003
```

### 第 5 步：访问

浏览器打开：

```
http://localhost:5003
```

如需局域网内其他设备（手机/其他电脑）访问，用本机局域网 IP 访问，例如 `http://192.168.1.100:5003`（Windows 防火墙首次会弹出放行提示，请允许）。

---

## 三、常见问题

| 问题 | 处理办法 |
|---|---|
| A股扫描偶发失败/超时 | 新浪行情源有瞬时限流，程序会自动重试，稍后再点一次即可 |
| 首次启动很慢 | 首次会拉取三市场 9500+ 只股票清单并缓存 24 小时，属正常 |
| AI 解读报错 | 检查 `config.json` 的 api_key / base_url；用 Ollama 先确认 `ollama list` 有模型 |
| 端口被占用 | 改 `app.py` 末尾 `app.run(port=5003)` 中的端口号 |
| 港股扫描无成交量排名 | 新浪港股源不带成交额字段，属数据源限制 |

---

## 四、验证安装是否成功

```bash
# 1. 依赖自检
python -c "import flask, akshare, pandas, numpy, requests; print('deps ok')"

# 2. 评分逻辑离线自测（不需要网络、不需要 AI）
python test_strategy.py
```

自测脚本应输出全部 6 组测试通过。

---

## 免责声明

本程序仅供学习研究，输出内容（评分、信号、AI 解读）均不构成投资建议。股市有风险，入市需谨慎。
