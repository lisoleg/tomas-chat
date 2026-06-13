# 语料与蒸馏说明 (V3)

## 目录结构

```
data/
├── physics.txt                      # 物理语料（146行）
├── chemistry.txt                    # 化学语料（128行）
├── medicine.txt                     # 医学语料（161行）
├── quantum_computing.txt            # 量子计算语料（599字符）
├── test_ai.txt                      # AI 测试语料
├── physics_distilled.eml            # 物理蒸馏输出（需手动生成）
├── physics_distilled.concepts.json  # 物理概念名称（已提交）
├── chemistry_distilled.eml          # 化学蒸馏输出（需手动生成）
├── chemistry_distilled.concepts.json # 化学概念名称（已提交）
├── medicine_distilled.eml           # 医学蒸馏输出（需手动生成）
└── medicine_distilled.concepts.json  # 医学概念名称（已提交）
```

## 如何生成 EML 文件（使用 Token Bridge V3）

```bash
cd tomas_agi/sim

# 蒸馏语料 → EML 知识图谱
python llm_distiller.py --distill ../data/physics.txt \
    --output ../data/physics_distilled.eml \
    --api-key YOUR_DEEPSEEK_API_KEY

# 使用蒸馏后的 EML 图进行推理
python token_bridge.py --load ../data/physics_distilled.eml \
    --concepts ../data/physics_distilled.concepts.json \
    --query "牛顿定律"
```

## 如何在 Web 前端使用

```bash
cd deepseek-chat
npm install && npm run dev
# 在蒸馏面板中上传 .txt 语料 → 蒸馏 → 推理测试
```

## 预蒸馏文件

如果你想跳过蒸馏步骤，可以从以下位置获取预蒸馏的 EML 文件：

1. **量子计算**（已生成，位于 `data/quantum_distilled_v2.eml`）
2. **人工智能**（已生成，位于 `data/test_ai_distilled.eml`）
3. **物理/化学/医学**（需手动蒸馏，或联系维护者获取）

## 概念名称文件

概念名称文件（`.concepts.json`）已被提交到版本控制，因为它们很小（2-3KB）且包含有用的元数据。

这些文件可以被 Token Bridge 用来显示概念名称（而不是显示 `concept_0`, `concept_1` 等默认名称）。

## 故障排除

### 问题 1：ModuleNotFoundError: No module named 'requests'

**解决方案**：安装 requests

```bash
pip install requests
```

### 问题 2：蒸馏失败：cannot access local variable 'response'

**原因**：requests 导入失败，导致 response 变量未定义

**解决方案**：确保 requests 已正确安装，并且可以被 Python 导入

### 问题 3：EMLVertex object is not subscriptable

**原因**：代码尝试像访问字典一样访问 EMLVertex 对象

**解决方案**：✅ 已在最新版本中修复（使用 `v.id` 而不是 `v['id']`）

---

**如果有任何问题，请查看 `../sim/llm_distiller.py` 中的文档，或在 GitHub 上提交 issue。**
