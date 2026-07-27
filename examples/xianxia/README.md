# 修仙世界书测试样例

这个样例用一段黑石巷战斗检验 Rusty 是否能同时遵守世界规则、任务主线、人物口吻、决策习惯和统一招式描写。

## 资产边界

- `rewrite_prompt.json`：跨项目复用的修仙改写方法、场景识别和写作约束。
- `project_anchor.json`：仅属于当前项目的青冥洲世界书、玄墟天门主线和招式库。
- `characters.json`：人物性格、关系、对话风格、行动限制和条件化决策顺序。
- `source.txt`：待改写章节。
- `expected_rewrite.txt`：用于自动测试的示范输出，不是必须逐字复现的唯一答案。
- `style_source_excerpt.txt`：公版《西游记》第七十回的短摘录，用于验证“从真实文字抽取风格”工作流。
- `extracted_style_baseline.json`：从摘录中提炼的人工审校基准，用来核对模型抽取结果是否合理。
- `baseline_evaluation.json`：对示范改写的逐项验收记录，明确标注它不是实时 API 输出。

世界设定和招式不是“文风”，因此不会写入可复用提示词包。当前版本把世界书与招式库保存在项目大纲锚点的结构化 JSON 中，把人物决策规则保存在人物卡的 `profile.decision_policy` 中。

## 测试目标

1. 韩烬近身突袭时，顾长青先踢膝或勾踝，不直接起掌。
2. `踏虚七步` 是借力换位，不写成瞬移。
3. `青崖叠浪掌` 保持三重、半息延迟、浪拍石岸和右臂发麻等固定特征。
4. 苏晚照只冻结潮湿地面封路，不直接冻结同境修士。
5. 顾长青和苏晚照使用短句；韩烬用反问和赤炉盟威胁掩饰心虚。
6. 本章不提前开启玄墟天门，也不凭空出现第三枚残图。

自动测试位于 `tests/test_xianxia_example.py`。如要建立一个可在桌面端打开的演示工程，可运行：

```powershell
python examples/xianxia/seed_demo.py --database D:\Temp\rusty-xianxia.db --workspace D:\Temp\rusty-xianxia
```

脚本只建立工程、提示词、世界书和人物卡，不配置模型或调用 API。

如果测试数据库已经配置了可用模型和 API 密钥，可以运行完整的真实模型实验：

```powershell
python examples/xianxia/run_live_style_trial.py `
  --database D:\Temp\rusty-xianxia-live.db `
  --workspace D:\Temp\rusty-xianxia-live `
  --output D:\Temp\rusty-xianxia-live-result.json
```

这个脚本先从公版摘录生成风格模板，再把模板绑定到黑石巷项目，最后通过 Rusty 的摘要、场景识别与锚点改写流水线生成结果。输出 JSON 会同时保存原文摘录、抽取提示词、平淡输入和模型改写，便于人工验收。
