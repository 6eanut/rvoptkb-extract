# rvoptkb-extract — RISC-V 优化知识提取系统

> 从 RISC-V 优化补丁中自动提取结构化知识，遵循 **EoK（Evolution of Kernels）三层知识模型**：
>
> `Patch（代码提交）→ Thought（优化技巧）→ Idea（设计原则）`

系统维护一个**持久化 Idea Pool**（`pool/idea-pool.json`），初始为空，随补丁处理**数据驱动地自动增长**。每个新补丁都会被分类到已有 Idea 或催生新的 Idea，形成有机演化的知识体系。

---

## 目录

- [一、快速使用](#一快速使用)
- [二、工作流详解](#二工作流详解)
- [文件说明](#文件说明)
- [License](#license)

---

## 一、快速使用

### 1. 环境准备

```bash
# 安装 skill
bash install.sh

# gh CLI 认证（提升 GitHub API 请求速率）
gh auth login
```

### 2. 获取数据

```bash
# 方式 A：从单个 GitHub commit 获取
python3 scripts/fetch-github.py \
  https://github.com/uxlfoundation/oneDNN/commit/bd984d09dc5985a19fb427ac46d19d2cbd5558dd \
  -o data/

# 方式 B：扫描仓库，自动发现 RISC-V 优化补丁
python3 scripts/scan-commits.py \
  https://github.com/uxlfoundation/oneDNN \
  -o data/ --max-pages 3 --verbose

# 扫描全部 commit（不限页数，搭配 --since 限制时间范围）
python3 scripts/scan-commits.py \
  https://github.com/uxlfoundation/oneDNN \
  -o data/ --max-pages 0 --since 2024-01-01 -v

# 方式 C：批量获取扫描结果中的所有 commit
jq -r '.[]' data/scan_oneDNN.json | while read url; do
  python3 scripts/fetch-github.py "$url" -o data/
done
```

> **输入文件规范**：`{仓库名}_{完整SHA}_input.json`，例如 `oneDNN_bd984d09..._input.json`

### 3. 提取知识（Skill 核心步骤）

```bash
# 指令调用 skill
Skill("rvoptkb-extract", "data/oneDNN_bd984d09dc5985a19fb427ac46d19d2cbd5558dd_input.json")

# 自然语言调用 skill
用rvoptkb-extract技能处理data/oneDNN_bd984d09dc5985a19fb427ac46d19d2cbd5558dd_input.json
```

Skill 会自动完成：

- ✅ 判断是否为优化补丁
- ✅ 提取 Thought（优化技巧）
- ✅ 匹配或创建 Idea（设计原则）
- ✅ 更新 Idea Pool
- ✅ 生成输出 JSON

### 4. 写入经验中心

```bash
# 查看即将上传的内容（干跑模式）
python3 scripts/upload-to-experience.py data/oneDNN_*_output.json --dry-run -v

# 正式上传到经验中心
python3 scripts/upload-to-experience.py data/oneDNN_*_output.json -v
```

上传到以下存储：

- **PostgreSQL** — 元数据（title、summary、source_agent）
- **MinIO** — patch 文件（`rv-optkb` bucket）
- **Milvus** — 向量嵌入（支持语义搜索）

### 5. 查看知识库

```bash
# 查看 Idea Pool 概览
python3 scripts/check-idea-pool.py

# 查看单个 Idea 详情
python3 scripts/check-idea-pool.py --idea idea-0001

# 按关键词搜索
python3 scripts/check-idea-pool.py --search "gemm"
```

---

## 二、工作流详解

<img width="1536" height="1024" alt="9c5dabe500a8dd7402402052b63f1c3" src="https://github.com/user-attachments/assets/30f8cb5e-5916-4268-af33-1777478b9c3d" />

### 2.1 系统架构全景

```
                          ┌──────────────────────┐
                          │    GitHub 社区        │
                          │  (oneDNN / ncnn /     │
                          │   OpenBLAS 等上游)     │
                          └──────────┬───────────┘
                                     │ commit URL
                                     ▼
┌─────────────────────────────────────────────────────────┐
│              数据获取阶段 Data Acquisition                │
│                                                         │
│  scan-commits.py  ──→  GitHub Commit List               │
│       │            （自动筛选 RV 相关 commit）             │
│       ▼                                                 │
│  fetch-github.py  ──→  input JSON                       │
│                      { patch_subject,                    │
│                        commit_message,                   │
│                        code_diff,                        │
│                        output_path }                     │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│            Skill 核心处理阶段 Knowledge Extraction        │
│                                                         │
│  Step 1: 读取 & 验证输入                                 │
│  Step 2: 判断是否为优化补丁                               │
│    ├── 是 → 进入提取流程                                  │
│    └── 否 → 跳过并记录原因                                 │
│  Step 3: 分析 diff，提取 Thought（优化技巧）               │
│  Step 4: 读取 Idea Pool，语义匹配                          │
│    ├── 匹配 → 复用已有 Idea title                          │
│    └── 不匹配 → 创建新 Idea，写入 Pool                     │
│  Step 5: 生成 output JSON                                 │
│  Step 6: 输出分析日志                                     │
│                                                         │
│  ┌─────────────────────────────────────┐                 │
│  │        Idea Pool（持续积累）          │                 │
│  │  idea-0001: RVV Primitive Operator   │                 │
│  │  idea-0002: RVV JIT Micro-Kernel     │                 │
│  │  idea-0003: Build & Runtime Infra    │                 │
│  └─────────────────────────────────────┘                 │
└─────────────────────────┬───────────────────────────────┘
                          │ output JSON
                          ▼
┌─────────────────────────────────────────────────────────┐
│              数据中心写入阶段 Data Upload                  │
│                                                         │
│  upload-to-experience.py ──→ Experience Center           │
│                              POST /api/v1/experience/    │
│                              optkb (multipart/form-data) │
│                              ├── title     = idea        │
│                              ├── summary   = thought     │
│                              ├── source_agent = Agent1-  │
│                              │     Lite                  │
│                              └── patch_file = code_diff  │
│                                                         │
│  Experience Center 存储:                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │PostgreSQL│  │  MinIO   │  │  Milvus  │               │
│  │  元数据   │  │ patch文件 │  │  向量搜索  │               │
│  └──────────┘  └──────────┘  └──────────┘               │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│         社区交互 Agent（持续演化）                         │
│                                                         │
│  定期检测上游仓库新 commit                                │
│    ├── 有 RV 优化 → 自动调用 Skill 提取知识                │
│    └── 无新内容 → 等待下一周期                              │
│  新知识写入数据中心                                       │
│  Idea Pool 持续增长                                       │
└─────────────────────────────────────────────────────────┘
```

### 2.2 EoK 三层知识模型

核心思想：**知识从代码中来，到代码中去**。

```
Patch（代码提交）
  │  一个具体的优化提交，包含完整的 diff
  │  例如："cpu: rv64: gemm: improve gemm kernel performance by tuning LMUL"
  │
  ▼
Thought（优化技巧）                       ← 告诉 LLM 怎么改代码
  │  一条可操作的优化技术描述
  │  例如："Use LMUL dynamic tuning (m1→m8/m4/m2) to maximize
  │         vector register utilization in GEMM kernels"
  │
  ▼
Idea（设计原则）                          ← 知识的分类和归纳
    一个通用的设计原则，来自多个相似 Thought 的归纳
    例如："RVV LMUL Dynamic Tuning in GEMM Kernels"
```

| 层级              | 粒度        | 抽象程度   | 变化频率   | 举例                             |
| ----------------- | ----------- | ---------- | ---------- | -------------------------------- |
| **Patch**   | 单个 commit | 具体实现   | 随代码迭代 | 某次 LMUL 调优的 diff            |
| **Thought** | 单次优化    | 可操作技术 | 每次提取   | "Use LMUL m1→m8 tuning in GEMM" |
| **Idea**    | 一类优化    | 设计原则   | 缓慢演化   | "RVV LMUL Dynamic Tuning"        |

### 2.3 数据获取阶段

#### scan-commits.py — 自动发现 RV 优化补丁

扫描 GitHub 仓库，通过关键词筛选与 RISC-V 向量优化相关的 commit：

**关键词匹配规则**（匹配 commit 标题和内容）：

| 类型                | 关键词                                                                     |
| ------------------- | -------------------------------------------------------------------------- |
| **架构**      | `riscv`, `rv64`, `rv32`, `RISC-V`, `risc-v`                      |
| **向量扩展**  | `rvv`, `vector`, `vsetvl`, `vle32`, `vse32`, `vfmul`, `vadd` |
| **JIT/汇编**  | `xbyak_riscv`, `jit`, `lmul`, `vlens`                              |
| **编译/平台** | `zmmul`, `zfh`, `zve`, `march`, `DNNL_RV64`, `DNNL_RISCV`      |

#### fetch-github.py — 拉取单个 commit

通过 GitHub API 获取 commit 的完整信息，生成输入 JSON：

```json
{
  "patch_subject": "cpu: rv64: gemm: improve gemm kernel performance by tuning LMUL",
  "commit_message": "cpu: rv64: gemm: improve gemm kernel performance by tuning LMUL\n\nCo-authored-by: ...",
  "code_diff": "diff --git a/src/cpu/rv64/gemm/rvv_gemm_f32.cpp\n@@ -40,19 +40,21 @@ ...",
  "output_path": "data/oneDNN_bd984d09..._output.json"
}
```

### 2.4 Skill 内部完整工作流

调用 `Skill("rvoptkb-extract", "..._input.json")` 后，Claude Code 按以下步骤执行：

#### Step 1: 读取 & 验证输入

验证字段完整性：`patch_subject`、`commit_message`、`code_diff`、`output_path` 必须存在且非空。

#### Step 2: 判断是否为优化补丁

**优化补丁**的特征：

- 性能调优、吞吐提升、延迟降低
- 算法改进（循环展开、分块、向量化）
- LMUL 调优、JIT kernel 变化
- 新的 RVV kernel 实现
- 并行化（`parallel_nd`、OpenMP）
- 数据类型支持（FP16/Zvfh）带来性能提升

**非优化补丁**（跳过）：

- EoL/EOF 修复、版权头更新
- clang-format/whitespace 修复
- 纯死代码删除
- rebase/merge commit
- CI 工作流变更
- 纯文档变更
- 无性能意图的纯重构

> **重要**：不仅要看 commit 标题，还要深入阅读 diff 内容。名为 "fix XYZ" 的 commit 可能包含优化修复，名为 "optimize XYZ" 的 commit 可能只是格式调整。

#### Step 3: 分析 diff，提取 Thought

读取 commit message 和代码 diff，理解：

- **瓶颈是什么？**
- **用了什么优化技术？**
- **上下文是什么？（项目、子系统、函数）**
- **用到了哪些 RISC-V 扩展？**
  - RVV 内建函数 → **V 扩展**
  - FP16 类型或内建 → **Zfh/Zvfh 扩展**
  - `-march=rv64gcv` → **V 扩展**
- **涉及哪些数据类型？（FP32、FP16、INT8）**
- **做了哪些算法/循环变换？**
- **有没有性能数据？（speedup 数值）**

**Thought 格式**：一条可操作的单句描述。

```
格式: "Use {RVV 技术} to {达成什么优化目标} in {什么上下文}"
```

实际案例：

| 原始 Patch 标题                                                   | 提取的 Thought                                                                                                                                                                                                                          |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "cpu: rv64: gemm: improve gemm kernel performance by tuning LMUL" | "Use LMUL dynamic tuning (m1→m8/m4/m2) to maximize vector register utilization in GEMM kernels on RISC-V V extension hardware"                                                                                                         |
| "cpu: rv64: add runtime Zvfh detection and platform support"      | "Add runtime Zvfh extension detection via /proc/cpuinfo parsing with mayiuse() infrastructure, wired into has_data_type_support() to enable FP16 code paths on Zvfh-capable RISC-V hardware"                                            |
| "cpu: rv64: add JIT affine kernel optimization for softmax f32"   | "Use JIT-generated RVV affine kernel (vle32_v → vfsub_vf → vfmul_vf → vse32_v with LMUL=m1) to replace scalar fp32 loop in softmax normalization, fusing max_val subtraction and log_sum subtraction into a single affine operation" |

#### Step 4: 匹配 Idea Pool

读取 `pool/idea-pool.json`，将提取的 Thought 与已有 Idea 进行语义匹配。

**匹配依据**：

- 类别重叠：是否自然属于某个已有类别？
- 扩展重叠：涉及的 RISC-V 扩展是否一致？
- 技术相似性：是否描述相似的技术方向？

**决策逻辑**：

```
if 无任何 Idea → 创建新 Idea
if 有匹配 → 复用该 Idea 的 title（不修改 pool）
if 不匹配 → 创建新 Idea（写入 pool）
```

匹配偏保守：宁可创建新 Idea，也不强行塞入不合适的类别。

#### Step 5: 创建新 Idea（无匹配时）

```json
{
  "id": "idea-0004",
  "title": "新设计原则标题",
  "riscv_extensions": ["V"]
}
```

Idea Pool 遵循 **append-only** 原则：只增不删，不重新排序。增长是系统的目标。

#### Step 6: 生成输出 JSON

```json
{
  "patch": {
    "patch_subject": "cpu: rv64: gemm: improve gemm kernel performance by tuning LMUL",
    "commit_message": "cpu: rv64: gemm: improve gemm kernel performance by tuning LMUL\n\nCo-authored-by: ...",
    "code_diff": "diff --git a/src/cpu/rv64/gemm/rvv_gemm_f32.cpp ..."
  },
  "thought": "Use LMUL dynamic tuning (m1→m8/m4/m2) to maximize vector register utilization in GEMM kernels on RISC-V V extension hardware",
  "idea": "RVV LMUL Dynamic Tuning in GEMM Kernels"
}
```

### 2.5 数据中心写入

输出 JSON 需要经过一次**字段映射**，然后通过 Experience Center 的 API 写入。

#### upload-to-experience.py

**字段映射**：

| output.json 字段    | API 字段         | 说明                                 |
| :------------------ | :--------------- | :----------------------------------- |
| `idea`            | `title`        | 设计原则名称                         |
| `thought`         | `summary`      | 优化技术描述                         |
| 固定值              | `source_agent` | 固定为 `Agent1-Lite`               |
| `patch.code_diff` | `patch_file`   | 作为 `.diff` 文件上传（multipart） |

**API 接口**：

```text
POST /api/v1/experience/optkb
Content-Type: multipart/form-data
Authorization: Bearer phase1-dev-token

Fields: title, summary, source_agent, patch_file@/tmp/xxx.diff
```

**三路存储**：

```
PostgreSQL ───  metadata（title, summary, source_agent）
MinIO     ───  patch 文件（rv-optkb bucket, 可通过 HTTP 下载）
Milvus    ───  向量嵌入（支持语义搜索，阈值 0.7）
```

**搜索接口**：

```bash
curl -X POST "http://192.168.16.234:18000/api/v1/experience/search" \
  -H "Authorization: Bearer phase1-dev-token" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "优化oneDNN在64位RISC-V上的矩阵乘法性能",
    "card_type": "RV-OptKB"
  }'
```

返回结果示例：

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "title": "RVV Primitive Operator Implementation",
        "summary": "Use LMUL dynamic tuning to maximize vector register utilization...",
        "patch_url": "http://192.168.16.234:9000/rv-optkb/xxx.diff"
      }
    ]
  }
}
```

### 2.6 社区交互 Agent（持续演化）

系统设计了**社区交互 Agent** 机制来实现知识的持续增长：

```
┌────────────────────────────────────────────────────┐
│              社区交互 Agent                          │
│                                                      │
│  定时任务（如每天）                                    │
│    │                                                  │
│    ├── 检查上游仓库新 commit                           │
│    │   （oneDNN / ncnn / OpenBLAS / ...）              │
│    │                                                  │
│    ├── 发现 RV 相关 commit                             │
│    │    │                                              │
│    │    └── 自动调用 fetch-github.py                    │
│    │         │                                          │
│    │         └── 自动调用 Skill 提取知识                 │
│    │              │                                    │
│    │              └── 自动调用 upload-to-experience.py  │
│    │                                                   │
│    └── 无新 commit → 等待下一周期                       │
│                                                      │
│  结果：                                                │
│  ├── Idea Pool 持续增长                                 │
│  ├── 数据中心知识不断丰富                                │
│  └── LLM 回答 RISC-V 优化问题越来越准确                   │
└────────────────────────────────────────────────────┘
```

### 2.7 数据驱动知识增长模型

Idea Pool 不是人工预定义的，而是**数据驱动**地自然生长：

```
初始状态: ideas = []                     空池

Phase 1: 处理 GEMM LMUL 调优 commit
         → 创建 idea-0001: "RVV LMUL Dynamic Tuning"
         Pool: [idea-0001]

Phase 2: 处理 Conv 向量化 commit（技术不同）
         → 语义匹配失败 → 创建 idea-0002
         Pool: [idea-0001, idea-0002]

Phase 3: 处理 JIT BRGEMM commit
         → 语义匹配 idea-0002 → 复用
         Pool: [idea-0001, idea-0002]  ← 不新增

Phase 4: 处理 Zvfh 检测 commit（方向完全不同）
         → 创建 idea-0003
         Pool: [idea-0001, idea-0002, idea-0003]

...持续增长...
```

这种模型的优势：

- **无偏分类**：类别来自实际代码，而非人工预设
- **自动演化**：随上游项目发展，知识体系自然扩展
- **粒度自适**：相似 commit 越多，Idea 越精炼；新型 commit 催生新 Idea

### 2.8 系统核心价值

| 维度                 | 价值                                                    |
| -------------------- | ------------------------------------------------------- |
| **知识复用**   | 优化经验不再丢失在 commit 历史中，而是结构化可检索      |
| **LLM 增强**   | Thought 直接指导 LLM 如何改代码，Idea 提供分类索引      |
| **持续集成**   | 社区 Agent 周期性运行，知识随上游代码同步更新           |
| **无监督生长** | 不需要人工标注，数据驱动分类                            |
| **多项目统一** | oneDNN、ncnn、OpenBLAS 等项目的 RV 优化汇聚到同一知识库 |

---

## 文件说明

| 文件                                | 作用                                                    |
| ----------------------------------- | ------------------------------------------------------- |
| `skill/SKILL.md`                  | 主 skill 定义（通过 `install.sh` 安装到 Claude Code） |
| `scripts/fetch-github.py`         | Python 3 脚本：GitHub commit URL → 输入 JSON           |
| `scripts/fetch-github.sh`         | Shell 替代方案：`gh` + `jq`                         |
| `scripts/scan-commits.py`         | 自动扫描仓库中的 RISC-V 优化补丁                        |
| `scripts/check-idea-pool.py`      | 查询和查看 Idea Pool                                    |
| `scripts/upload-to-experience.py` | 将 output JSON 上传到经验中心                           |
| `schema/input-schema.json`        | 输入 JSON schema                                        |
| `schema/output-schema.json`       | 输出 JSON schema                                        |
| `schema/idea-pool-schema.json`    | Idea Pool schema                                        |
| `pool/idea-pool.json`             | Idea Pool（持久化，初始为空）                           |
| `data/`                           | 生成的输入/输出 JSON 文件                               |
| `examples/`                       | 示例输入/输出                                           |
| `install.sh`                      | 安装脚本                                                |

---

## License

MIT
