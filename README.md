## AI News Pusher / AI 每日资讯推送工具

一个基于 **Python + GitHub Actions + Server酱 + OpenAI GPT-4o-mini** 的自动化工具，每天早上 **8 点（北京时间）** 自动抓取 AI 圈最新资讯并推送到你的微信。

### 功能概览

- **RSS 聚合**：从多个 AI 媒体和官方博客抓取 RSS 内容（标题、摘要、链接、发布时间等）。
- **智能摘要**：调用 **GPT-4o-mini**，自动从候选文章中选出 **3–5 条最重要的新闻**，生成简洁中文摘要（每条不超过 50 字）。
- **微信推送**：通过 **Server酱** 将整理好的「AI 日报」以 Markdown 格式推送到微信。
- **定时任务**：使用 **GitHub Actions**，每天早上 **8:00（北京时间）** 自动执行。
- **成本优化**：只调用一次 GPT，总结 3–5 条重点新闻，并带有简单缓存机制，预计花费约 **0.1–0.3 元/天**。

---

### 项目结构

```text
ai-news-pusher/
├── .github/
│   └── workflows/
│       └── daily_push.yml        # GitHub Actions 定时任务配置
├── src/
│   ├── rss_fetcher.py            # RSS 抓取模块（异步）
│   ├── content_summarizer.py     # GPT 摘要模块（异步）
│   └── wechat_pusher.py          # Server酱微信推送模块（异步）
├── config/
│   └── rss_sources.json          # RSS 源配置
├── cache/
│   └── last_articles.json        # 简单缓存（运行时自动生成）
├── main.py                       # 主入口脚本（调度各模块）
├── requirements.txt              # Python 依赖
├── .env.example                  # 环境变量示例
└── README.md
```

---

### RSS 源配置

配置文件：`config/rss_sources.json`

已内置的默认 RSS 源如下（可自行扩展或修改）：

```json
{
  "sources": [
    {
      "name": "机器之心",
      "url": "https://www.jiqizhixin.com/rss",
      "category": "综合"
    },
    {
      "name": "量子位",
      "url": "https://www.qbitai.com/rss",
      "category": "综合"
    },
    {
      "name": "AI科技评论",
      "url": "https://www.leiphone.com/category/ai/feed",
      "category": "深度"
    },
    {
      "name": "OpenAI Blog",
      "url": "https://openai.com/blog/rss.xml",
      "category": "官方"
    }
  ]
}
```

你可以按同样格式添加更多 RSS 源。

---

### 消息格式示例

推送到微信的内容（Markdown）示例如下：

```text
📰 AI日报 - 2026-03-11

🔥 今日热点
1. [标题一](https://example.com/article1)
   来源：机器之心 | 分类：综合
   某某大模型发布，性能大幅超越前代版本，推动行业应用落地。

2. [标题二](https://example.com/article2)
   来源：OpenAI Blog | 分类：官方
   OpenAI 发布最新研究成果，展示多模态模型在复杂任务上的突破。
```

---

### 环境准备

#### 1. Fork 项目

1. 在 GitHub 上将本项目 **Fork** 到你自己的账号下，仓库名可以保持为 `ai-news-pusher`。

#### 2. 获取 Server酱 SendKey

1. 打开 `https://sct.ftqq.com/` 注册并登录。
2. 在「发送消息」页面中获取你的 **SendKey**（形如 `SCTxxxxxxxxxxxx`）。

#### 3. 准备 OpenAI API Key

1. 在 OpenAI 官网创建 API Key。
2. 推荐使用官方基础 URL：`https://api.openai.com/v1`。
3. 模型使用：`gpt-4o-mini`（低成本）。

#### 4. 本地运行（可选，用于调试）

1. 克隆你 Fork 后的仓库到本地：

```bash
git clone https://github.com/<your-username>/ai-news-pusher.git
cd ai-news-pusher
```

2. 创建并激活虚拟环境（可选但推荐）：

```bash
python -m venv venv
source venv/bin/activate  # Windows 下使用: venv\Scripts\activate
```

3. 安装依赖：

```bash
pip install -r requirements.txt
```

4. 复制环境变量示例并填写：

```bash
cp .env.example .env
```

编辑 `.env`，填写你的配置：

```text
OPENAI_API_KEY=你的_openai_api_key
OPENAI_BASE_URL=https://api.openai.com/v1   # 如使用官方，保持默认即可
SERVER_CHAN_KEY=你的_server_chan_sendkey
```

5. 手动运行一次脚本测试：

```bash
python main.py
```

如果本地运行成功，你会在微信中看到一条「AI日报」推送。

---

### 在 GitHub Actions 上部署（推荐）

#### 1. 配置仓库 Secrets

在你 Fork 后的仓库页面：

1. 打开 `Settings` → `Secrets and variables` → `Actions` → `New repository secret`。
2. 新建以下 Secrets（名称区分大小写）：

- `OPENAI_API_KEY`：你的 OpenAI API Key
- `OPENAI_BASE_URL`：`https://api.openai.com/v1`（如果使用兼容 OpenAI 的第三方服务，可以替换为对应 Base URL；如不需要可留空，不创建也可以）
- `SERVER_CHAN_KEY`：你的 Server酱 SendKey

#### 2. 启用 GitHub Actions

1. 打开仓库的 `Actions` 页面，若提示需要启用 Workflow，点击「Enable」。
2. 项目中已经包含 `.github/workflows/daily_push.yml`，默认配置为：
   - **每天 UTC 0:00 触发**（即北京时间早上 8:00）
   - 支持手动触发（`workflow_dispatch`）

#### 3. 手动触发测试

1. 在 `Actions` 页面中选择 `AI News Daily Push` workflow。
2. 点击右侧的「Run workflow」，选择分支后执行。
3. 等待几分钟，若日志中显示 `Server酱推送成功`，并在微信中收到推送，则说明部署成功。

---

### 核心模块说明

#### 1. RSS 抓取模块 `src/rss_fetcher.py`

- 使用 `aiohttp` 并发拉取多个 RSS 源。
- 使用 `feedparser` 解析 RSS 内容。
- 只保留 **最近 24 小时** 内的文章。
- 提取字段：**标题、摘要、链接、发布时间、来源名称、分类**。
- 具备完整错误处理：网络超时、状态码异常、RSS 解析失败等都会记录到日志中。

#### 2. 内容总结模块 `src/content_summarizer.py`

- 使用 **OpenAI Async 客户端** (`AsyncOpenAI`)。
- 调用 `gpt-4o-mini` 模型。
- 将候选文章（最多 30 条）组织成 prompt，由模型：
  - 按重要性选出 3–5 条。
  - 为每条生成 **50 字以内**的中文摘要。
  - 返回 JSON 数组（`title`, `summary`, `link`, `source`, `category`）。
- 如解析 JSON 失败，则自动回退，不中断主流程。

#### 3. 微信推送模块 `src/wechat_pusher.py`

- 使用 `aiohttp` 调用 Server酱 API：`https://sctapi.ftqq.com/<SendKey>.send`。
- 消息格式为 Markdown：
  - 标题示例：`📰 AI日报 - 2026-03-11`
  - 列表展示：热点标题 + 摘要 + 原文链接 + 来源/分类信息。
- 内置 **重试机制**：默认最多 3 次，带简单退避。

#### 4. 主调度脚本 `main.py`

- 主要流程：
  1. 加载 `.env` / 环境变量 & RSS 配置。
  2. 抓取所有 RSS 源的文章（24 小时内）。
  3. 比对缓存（标题+链接集合）避免重复调用 GPT。
  4. 调用 GPT 生成摘要；如失败则回退到简单标题列表。
  5. 通过 Server酱推送到微信。
  6. 成功后更新缓存（保存在 `cache/last_articles.json`）。
- 使用 `asyncio.run(run())` 作为入口函数，整体为异步流程。

---

### 成本控制

- 使用 **gpt-4o-mini** 模型，单次调用 Token 消耗较低。
- 默认仅保留最近 24 小时的文章，并只传入最多 30 篇作为候选。
- 开启简单缓存：
  - 如果当天抓取的文章集合（标题+链接）与上次完全一致，将 **跳过 GPT 调用**，直接复用上次的摘要结果。
- 粗略估算：在多数场景下，日均成本约为 **0.1–0.3 元**。

---

### 常见问题

- **Q: 可以添加/删除 RSS 源吗？**  
  **A:** 可以，直接编辑 `config/rss_sources.json`，按相同结构增删即可。

- **Q: 一直收不到微信推送？**  
  **A:** 请检查：
  - `SERVER_CHAN_KEY` 是否填写正确；
  - Server酱后台是否已绑定你的微信；
  - GitHub Actions 日志中是否有「推送失败」错误信息。

- **Q: OpenAI API 报错怎么办？**  
  **A:** 
  - 先确认 `OPENAI_API_KEY` 是否正确；
  - 如使用自建/第三方兼容服务，请确认 `OPENAI_BASE_URL` 与模型名是否匹配；
  - 如果 GPT 一直失败，脚本会自动用原始标题+摘要作为降级方案，仍然会推送。

---

### 贡献与扩展方向

- 增加更多 AI / 数据科学 / Cloud 相关资讯源。
- 根据个人喜好增加「分类过滤」或「关键词过滤」。
- 把推送渠道扩展到钉钉群机器人、飞书群机器人、企业微信机器人等。
- 在摘要中自动加入英文标题或关键技术关键词。

欢迎根据自身需求进行二次开发和定制。

