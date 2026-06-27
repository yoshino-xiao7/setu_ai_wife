# 本地提示词知识库

本项目的“本地知识库”用于指导 Ollama 翻译中文自然语言提示词。它不会修改模型权重，也不会让 Ollama 自动永久学习；它是在每次调用 Ollama 前，先从本机 JSON 文件里匹配角色名、作品名、别名、LoRA 触发词，再把命中的知识作为上下文传给 Ollama。

默认文件：

```text
config/prompt_knowledge.json
```

默认环境变量：

```dotenv
PROMPT_KNOWLEDGE_PATH=config/prompt_knowledge.json
```

## 工作方式

例如用户输入：

```text
八重神子和雷电影在沙滩上奔跑
```

worker 会先在 `prompt_knowledge.json` 中命中：

```text
八重神子 => Yae Miko
雷电影 => Raiden Ei
```

然后把这些命中结果一起发给 Ollama，并要求 Ollama 必须使用这些英文名，不要自行音译或保留中文。

## 条目格式

```json
{
  "aliases": ["八重神子", "神子", "八重宫司"],
  "target": "Yae Miko",
  "franchise": "Genshin Impact",
  "tags": ["Yae Miko", "Genshin Impact fanart"],
  "note": "Optional extra instruction"
}
```

字段说明：

- `aliases`：中文名、别名、简称。命中任意一个就会使用该条。
- `target`：必须使用的英文名或英文提示词。
- `franchise`：作品名，用于帮助 Ollama 理解角色来源。
- `tags`：推荐加入的英文 tag，可选。
- `note`：额外备注，可选。

## 加 LoRA 触发词

如果某个 LoRA 需要固定触发词，可以加类似条目：

```json
{
  "aliases": ["卡提希娅", "cartethyia"],
  "target": "cartethyia",
  "franchise": "Wuthering Waves",
  "tags": ["cartethyia", "long hair", "anime girl"],
  "note": "Use cartethyia as the LoRA trigger word when this character is requested."
}
```

## 修改后如何生效

修改 `config/prompt_knowledge.json` 后，重启本机 worker：

```powershell
cd C:\Users\rdpuser\Documents\setu_cd\setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts\start_cloud_all.ps1 -Restart
```

## 当前已内置

当前已加入一批常见二游角色名映射：

- 原神 / Genshin Impact
- 崩坏：星穹铁道 / Honkai: Star Rail
- 鸣潮 / Wuthering Waves
- 绝区零 / Zenless Zone Zero
- 明日方舟 / Arknights

