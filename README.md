# 电商客服机器人

面向人工实时值守的轻量客服辅助原型，使用 Python、FastAPI 和原生 HTML/CSS/JavaScript。
支持四款宿舍蚊帐商品的 FAQ 管理、条件选答、图文回复和本地接待测试。

当前知识库含 69 个场景、207 条答案。商品及话术来自本项目维护资料，
不是通用商品事实；用于其他店铺前应替换、审核。

## 当前功能

- 行业、特殊、自定义三层场景，一个场景支持多个问法和多条答案。
- 按商品、售前/售后客服接待、业务阶段、有效时间选择答案。
- 关键词任意/全部匹配，自定义 > 特殊 > 行业优先级，冲突提示人工。
- 网页维护场景、答案和配图，自动备份，保存后生效。
- 商品绑定、跨款推荐、尺寸适配、重复答复抑制。
- 基础字段检索、可选本地语义匹配、可选大模型选择已批准答案。
- 无模型密钥可用 Mock 演示，知识不足时仅提醒工作台。

目前不接入真实电商平台或订单接口，测试状态由操作人员选择。
系统以 FAQ 为主，不包含独立的生成式 RAG 产品知识问答。

## 在 Windows / VS Code 运行

当前验证环境为 Python 3.14。进入仓库目录后，在终端执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

- 接待测试：<http://127.0.0.1:8002/>
- 知识库管理：<http://127.0.0.1:8002/knowledge>
- 接口文档：<http://127.0.0.1:8002/docs>

启动后保持服务运行。关闭网页不会删除资料；服务退出后需要重新启动。
会话保存在内存中，重启后清空；已保存的知识库仍在文件中。

## 配置模型

只在本地 `.env` 填写 `MODEL_API_KEY`。默认火山 Seed 2.0 Lite：

```dotenv
MODEL_MODE=auto
MODEL_PROVIDER=volcengine
MODEL_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
MODEL_NAME=doubao-seed-2-0-lite-260428
MODEL_THINKING=false
```

可更换兼容接口和模型 ID。真实调用取决于账号权限、余额和网络。
设置 `MODEL_MODE=mock` 可始终使用本地演示模式。
`.env`、日志、备份、虚拟环境和模型权重不会上传到 GitHub。

## 可选：本地语义匹配

基础 FAQ 功能不要求下载模型。需要句向量匹配时执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-semantic.txt
.\.venv\Scripts\python.exe scripts/download_semantic_model.py
```

脚本下载固定版本数据，并校验 ONNX 模型的 SHA-256。权重不在 Git 中；
下载失败不影响基础 FAQ。详见 [语义检索说明](docs/语义检索运行说明.md)。

## 测试

```powershell
$env:MODEL_MODE="mock"
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

项目完整验证为 237 项测试通过。未下载本地向量模型时，相关测试会跳过。
主动运行 `scripts/check_model.py` 且启用真实模型时，会联网使用虚构 FAQ 验证接口。

## 文件位置

| 路径 | 用途 |
| --- | --- |
| `app/` | 接口、商品上下文、场景条件、检索和模型调用 |
| `static/` | 接待页、知识库页和图片 |
| `data/faq.json` | 场景、条件答案、关键词和图片引用 |
| `data/nets_801_804.json` | 结构化参数及尺寸校验资料 |
| `data/source_qa.json` | 原表问答溯源 |
| `data/image_catalog.json` | 图片清单 |
| `data/backups/` | 本地自动备份，不上传 |
| `logs/events.jsonl` | 本地诊断日志，不上传 |
| `tests/` | 自动化测试 |

详细操作见 [场景与条件答案使用说明](docs/场景与条件答案使用说明.md)。
早期版本保留在 [历史开发记录](docs/历史开发记录.md)，以当前说明为准。

## 部署范围

这是本地原型，默认仅监听 `127.0.0.1`。上传 GitHub 用于保存和管理项目，
不会自动部署为在线网站。对外部署前需增加账号权限及相应部署配置。
