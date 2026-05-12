# rvoptkb-extract

> 从 RISC-V 优化补丁中提取结构化知识（Thought + Idea），遵循 EoK（Evolution of Kernels）三层知识模型：
>
> `Patch（代码提交）→ Thought（优化技巧）→ Idea（设计原则）`

系统维护一个 **Idea Pool**（`pool/idea-pool.json`），初始为空，随补丁处理自动增长。

---

## 快速开始

```bash
# 1. 从 GitHub 拉取一个 commit → 生成输入 JSON
python3 scripts/fetch-github.py \
  https://github.com/uxlfoundation/oneDNN/commit/bd984d09dc5985a19fb427ac46d19d2cbd5558dd \
  -o data/

# 2. 扫描仓库，自动发现 RISC-V 优化补丁
#    --max-pages 控制扫描页数（每页最多 100 个 commit）
#    设为 0 则扫描全部 commit（搭配 --since 限制时间范围更实用）
python3 scripts/scan-commits.py \
  https://github.com/uxlfoundation/oneDNN \
  -o data/ --max-pages 3 --verbose

# 扫描整个仓库的全部 RISC-V 优化 commit（不限制页数，但指定时间范围避免扫太多）
python3 scripts/scan-commits.py \
  https://github.com/uxlfoundation/oneDNN \
  -o data/ --max-pages 0 --since 2024-01-01 -v

# 3. 批量处理发现的 commit
jq -r '.[]' data/scan_oneDNN.json | while read url; do
  python3 scripts/fetch-github.py "$url" -o data/
done

# 4. 调用 skill 提取 Thought + Idea，更新 Idea Pool
Skill("rvoptkb-extract", "data/oneDNN_bd984d09dc5985a19fb427ac46d19d2cbd5558dd_input.json")

# 5. 查看 Idea Pool
python3 scripts/check-idea-pool.py --verbose
```

---

## 架构

```
GitHub Commit URL
       │
       ▼
┌──────────────────────────────┐
│   fetch-github.py / .sh      │  拉取 commit 内容
│   → 生成 input JSON          │
└──────────┬───────────────────┘
           │
           ▼  input JSON
           │
┌──────────────────────────────┐
│   skill/SKILL.md             │  分析并提取知识
│                              │
│   ① 读取并验证输入           │
│   ② 提取 THOUGHT（优化技巧）  │
│   ③ 匹配已有 IDEA            │
│   ④ 若无匹配 → 创建新 Idea   │
│   ⑤ 保存 Idea Pool           │
│   ⑥ 生成输出 JSON            │
└──────────┬───────────────────┘
           │
           ├──▶ output JSON（精简记录）
           └──▶ pool/idea-pool.json（持续积累）
```

---

## 文件说明

| 文件 | 作用 |
|------|------|
| `skill/SKILL.md` | 主 skill 定义（通过 `install.sh` 安装） |
| `scripts/fetch-github.py` | Python 3 脚本：GitHub commit URL → 输入 JSON |
| `scripts/fetch-github.sh` | Shell 替代方案：`gh` + `jq` |
| `scripts/scan-commits.py` | 自动扫描仓库中的 RISC-V 优化补丁 |
| `scripts/check-idea-pool.py` | 查询和查看 Idea Pool |
| `schema/input-schema.json` | 输入 JSON 的 schema |
| `schema/output-schema.json` | 输出 JSON 的 schema |
| `schema/idea-pool-schema.json` | Idea Pool 的 schema |
| `pool/idea-pool.json` | Idea Pool（持久化，初始为空） |
| `data/` | 生成的输入/输出 JSON 文件 |
| `examples/` | 示例输入/输出 |
| `install.sh` | 安装脚本 |

---

## 输入 / 输出 格式

### 输入 JSON

```json
{
  "patch_subject": "cpu: rv64: gemm: improve gemm kernel performance by tuning LMUL",
  "commit_message": "cpu: rv64: gemm: improve gemm kernel performance by tuning LMUL",
  "code_diff": "diff --git a/... b/...",
  "output_path": "data/oneDNN_SHA_output.json"
}
```

文件名规范：`{仓库名}_{完整SHA}_input.json`

### 输出 JSON（精简记录）

```json
{
  "patch": {
    "patch_subject": "...",
    "commit_message": "...",
    "code_diff": "..."
  },
  "thought": "Use LMUL dynamic tuning to maximize vector register utilization...",
  "idea": "RVV LMUL Dynamic Tuning in GEMM Kernels"
}
```

> 输出 JSON 只记录关键信息。完整的 Idea Pool 数据在 `pool/idea-pool.json`，用 `check-idea-pool.py` 查看。

### Idea Pool 结构

每个 Idea 只包含 id、title、riscv_extensions 三个字段，title 本身就是对 idea 的描述：

```json
{
  "id": "idea-0001",
  "title": "RVV LMUL Dynamic Tuning in GEMM Kernels",
  "riscv_extensions": ["V"]
}
```

---

## Idea Pool 生命周期

1. **初始**：空池 `"ideas": []`
2. **第一个补丁**：创建 `idea-0001`
3. **后续补丁**：
   - 与已有 Idea 相似 → 复用该 Idea 的 title
   - 完全不同 → 创建新 Idea（`idea-0002`, `idea-0003`, ...）
4. **自然增长**：分类来自实际补丁，而非预定义

---

## License

MIT