# 火山模型与 FAQ 配置

已配置 Seed 2.0 Lite，模型 ID 为 `doubao-seed-2-0-lite-260428`。
API 地址为 `https://ark.cn-beijing.volces.com/api/v3`。本地 `.env` 保存密钥，
`.env.example` 只保存空白占位。`.env` 不提交、不进入交付压缩包。

使用现有 httpx 调用兼容的 `/chat/completions`，不必额外安装 OpenAI SDK。
控制台提供的 `/responses` 是另一种受支持的调用形式；目前只做文字问法理解，
知识库图片由本地程序发送，不交给模型生成。关闭深度思考，要求 JSON 输出。
`MODEL_NAME` 可换成控制台提供的准确模型 ID 或接入点 ID。
支持 `MODEL_API_KEY`，也兼容控制台示例的 `ARK_API_KEY`；前者优先。

## FAQ 在哪里

- `data/faq.json`：统一 FAQ 主文件。
- `docs/FAQ知识库阅读版.md`：便于阅读的导出快照。
- `data/nets_801_804.json`：结构化商品参数、上下文与尺寸校验。
- `data/source_qa.json`：原始表格问答和审核记录，用于追溯。
- `data/image_catalog.json`：图片清单和原始位置。

现有资料迁移为 207 条记录，176 条 active；其中保留原表 110 条记录。
记录数包含商品字段回复、原表问答和店铺规则，不等于 207 个独立意图。
待核实和人工处理记录不会进入模型候选。未改写用户已批准的标准答案。

## 每条记录怎么维护

每条包含 `id`、`intent`、`question_variants`（多个真实问法）、
`standard_answer`、`category`、`scope`、`product_ids`、`answer_product_id`、
`images`、`sources`、`boundaries`、`status` 和 `updated_at`。

- product：具体商品事实，必须匹配当前已确认商品。
- store：通用店铺政策，不要求确认商品。
- catalog：跨款推荐，不切换当前咨询商品。
- active：参与自动回复；其他状态保留给人工核实。

同一个意思新增真实问法到 `question_variants`；新意图新增记录，
`origin` 写 `custom`，填写已批准答案和适用范围。新增 custom 记录会参与
精确匹配、向量检索和模型候选。修改后重启服务即可重建本地索引。
阅读版是快照，不会自动同步。`scripts/build_faq.py` 为一次性迁移工具，
已有 FAQ 时拒绝覆盖，避免丢失后续人工编辑。

## 回复流程

商品识别 → 已批准规则/精确 FAQ → 基础字段检索和本地语义检索 →
必要时模型从当前商品、通用店铺、跨款推荐的已启用候选中选一个 →
直接发送标准答案和关联图片。

兼容已有规则和尺寸校验，没有将动态尺寸适配改成盲目文本匹配。
模型不能自由生成参数和销售承诺；输出不在候选集合内会被拒绝。
资料不足时只提醒工作台，后续消息继续辅助；相同答复继续去重。
来源位置和图片路径不发送给问题理解模型。

## 验证

2026-10-14：实际接口 HTTP 200，JSON 输出成功。两条虚构 FAQ 的真实模型
测试均通过（支架稳固意图匹配、无关问题跳过），耗时约 1.5 秒和 2.1 秒。
结果见 `docs/model_connection_check.json`。这不是正式销售知识库的准确率评测。
自动审批拒绝了完整实际 FAQ 候选集的联网测试，因此改用虚构数据验证接口。
实际 FAQ 的商品隔离、原话、图片、状态筛选在本地自动化测试中验证。
全部 188 项本地自动化测试通过。当前新版工作台使用 http://127.0.0.1:8002/；
8000 的旧服务未终止，避免中断归属无法充分确认的进程。

运行本地测试：`MODEL_MODE=mock` 下执行 `python -m unittest discover -s tests -q`。
主动运行 `python scripts/check_model.py` 可再次验证真实接口，仅发送虚构 FAQ。
实时系统在需要模型辅助时，会发送客户问题、最近六条对话和经过筛选的标准答案候选。

## 打开工作台

在项目目录启动 `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`，
浏览器打开 `http://127.0.0.1:8000/`。日志为 `logs/events.jsonl`，
`debug.retrieval.method` 可以区分 `faq_exact`、`semantic_onnx` 和
`llm_intent_selection`。`api_intent_success` 表示本次确实调用了模型；
命中固定话术时不需要调用模型。
