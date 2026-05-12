#!/usr/bin/env python3
"""Batch extract Thought + Idea from all input JSONs in data/.
Follows the SKILL.md workflow: analyze patch → extract thought → match/update idea pool → save output.
"""
import json, glob, os, sys, re
from datetime import datetime, timezone, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
POOL_PATH = os.path.join(PROJECT_ROOT, "pool", "idea-pool.json")
TZ = timezone(timedelta(hours=8))

def iso_now():
    return datetime.now(TZ).isoformat()

def read_pool():
    if not os.path.exists(POOL_PATH):
        return {"version": "1.0", "ideas": []}
    with open(POOL_PATH) as f:
        return json.load(f)

def save_pool(pool):
    with open(POOL_PATH, "w") as f:
        json.dump(pool, f, indent=2)
        f.write("\n")

# ── Idea definitions (pre-defined from semantic grouping) ──

IDEAS = [
    {"id": "idea-0001", "title": "RVV LMUL Dynamic Tuning in GEMM Kernels", "riscv_extensions": ["V"]},
    {"id": "idea-0002", "title": "RVV Primitive Operator Implementation", "riscv_extensions": ["V"]},
    {"id": "idea-0003", "title": "RVV JIT Kernel Integration via xbyak_riscv", "riscv_extensions": ["V"]},
    {"id": "idea-0004", "title": "GEMM/Matmul Performance Optimization", "riscv_extensions": ["V"]},
    {"id": "idea-0005", "title": "FP16/Zvfh Extension Support", "riscv_extensions": ["V", "Zvfh"]},
    {"id": "idea-0006", "title": "Build & Compiler Infrastructure for RV64", "riscv_extensions": ["V"]},
    {"id": "idea-0007", "title": "RVV Post-ops and Element-wise Fusion", "riscv_extensions": ["V"]},
    {"id": "idea-0008", "title": "Code Quality and Maintenance for RV64 Port", "riscv_extensions": []},
    {"id": "idea-0009", "title": "Governance, CI and Testing for RV64", "riscv_extensions": []},
    {"id": "idea-0010", "title": "Multi-threading and Parallelism in RVV Kernels", "riscv_extensions": ["V"]},
]

def get_extensions(text):
    """Detect RISC-V extensions from code diff."""
    exts = set()
    if any(kw in text for kw in ['__riscv_v', 'vsetvl', 'vfloat32', 'vint32', 'LMUL', 'lmul',
                                  'vfmul', 'vfadd', 'vfmacc', 'vse32', 'vle32', 'm1)', 'm2)', 'm4)', 'm8)',
                                  'vfloat16', 'vle16', 'vse16']):
        exts.add('V')
    if any(kw in text for kw in ['_Float16', 'f16', 'Zvfh', 'zvfh', '__riscv_vfwcvt', '__riscv_vfncvt']):
        exts.add('Zvfh')
    return sorted(exts)

def classify_patch(subject, diff):
    """Determine which idea a patch belongs to."""
    s = subject.lower()
    d = diff.lower()
    
    # GEMM LMUL tuning (idea-0001 specific)
    if 'tuning lmul' in s or 'lmul' in s and ('gemm' in s or 'kernel performance' in s):
        return "idea-0001"
    
    # GEMM/Matmul performance (idea-0004)
    if any(kw in s for kw in ['gemm', 'matmul']):
        if any(kw in s for kw in ['performance', 'optimiz', 'improve', 'loop unrolling', 'bias fusion',
                                   'variable', 'simd']):
            return "idea-0004"
        if 'row/col' in s or 'post-op' in s or 'fix' in s:
            return "idea-0002"  # matmul primitive implementation
        if 'gemm' in s:
            return "idea-0004"
    
    # JIT kernels (idea-0003)
    if 'jit' in s and any(kw in s for kw in ['brgemm', 'gemm', 'conv', 'kernel', 'layer', 'xbyak', 'rvc']):
        return "idea-0003"
    if 'xbyak' in d:
        return "idea-0003"
    if 'jit_generator' in s:
        return "idea-0003"
    if 'vector-length-agnostic' in s:
        return "idea-0003"
    
    # FP16/Zvfh (idea-0005)
    if any(kw in s for kw in ['f16', 'Zvfh', 'zvfh', 'half-precision']):
        return "idea-0005"
    if 'runtime Zvfh' in s or 'runtime isa' in s:
        return "idea-0005"
    
    # Build/CMake (idea-0006)
    if any(kw in s for kw in ['cmake', 'build flag', 'march', 'build:', 'compilation check', 'gcc ice']):
        return "idea-0006"
    if 'platform.cmake' in d:
        return "idea-0006"
    
    # Post-ops (idea-0007)
    if 'postop' in s or 'post_op' in s or ('post' in s and 'op' in s):
        return "idea-0007"
    if 'eltwise' in s and ('post' in s or 'fusion' in s):
        return "idea-0007"
    
    # Multi-threading (idea-0010)
    if any(kw in s for kw in ['multithread', 'parallel', 'parallel_nd']):
        return "idea-0010"
    
    # Governance/CI (idea-0009)
    if any(kw in s for kw in ['governance', 'code owner', 'maintainer', 'ci test', 'benchdnn', 'weekly ci']):
        return "idea-0009"
    
    # Code quality (idea-0008)
    if any(kw in s for kw in ['clang-format', 'eol', 'copyright', 'deadcode', 'dead code',
                                'remove', 'cleanup', 'rebase', 'header guard', 'fix clang']):
        return "idea-0008"
    if any(kw in s for kw in ['review feedback', 'address review']):
        return "idea-0008"
    
    # Default: primitive implementations (idea-0002)
    if any(kw in s for kw in ['convolution', 'conv:', 'pooling', 'pool:', 'batch_normalization',
                                'bnorm', 'layer_normalization', 'layernorm', 'group_normalization',
                                'softmax', 'binary', 'eltwise', 'inner product', 'ip:', 'reorder',
                                'nchw', 'nhwc']):
        return "idea-0002"
    
    # Fallback
    return "idea-0002"

def generate_thought(subject, diff):
    """Generate a concise thought sentence from the patch."""
    s = subject.lower()
    
    # Base patterns
    base = "RVV intrinsics"
    if 'jit' in subject.lower() or 'xbyak' in subject.lower():
        base = "RVV JIT kernel"
    
    # Extract technique description from subject
    technique = subject.strip()
    # Remove common prefixes
    for prefix in ['cpu: rv64: ', 'cpu: riscv: ', 'cpu: risc-v: ', 'build: risc-v: ',
                   'src: cpu: rv64: ', 'tests: ', 'riscv64: ']:
        if technique.lower().startswith(prefix):
            technique = technique[len(prefix):]
    
    # Detect extension
    exts = get_extensions(diff)
    ext_str = f" on RISC-V{'/' + '/'.join(exts) if exts else ''} hardware"
    
    if 'lmul' in s:
        return f"Use LMUL dynamic tuning (m1→m8/m4/m2) to maximize vector register utilization in GEMM kernels{ext_str}"
    
    if 'jit' in s and 'brgemm' in s:
        return f"Implement RVV JIT brgemm kernel with runtime code generation for f32 matrix blocks{ext_str}"
    
    if 'jit' in s and 'gemm' in s and 'matmul' in s:
        return f"Apply RVV JIT gemm kernel to improve matmul performance through runtime-generated vector code{ext_str}"
    
    if 'jit' in s and '1x1' in s:
        return f"Implement RVV JIT 1x1 convolution kernel for efficient pointwise convolution{ext_str}"
    
    if 'vector-length-agnostic' in s:
        return f"Develop vector-length-agnostic RVV JIT convolution kernel for portable performance across VLEN configurations{ext_str}"
    
    if 'winograd' in s:
        return f"Apply RVV Winograd convolution algorithm to reduce arithmetic complexity in small-kernel convolutions{ext_str}"
    
    if 'xbyak' in s:
        return f"Integrate third-party xbyak_riscv JIT library to enable RVV runtime code generation for all primitives{ext_str}"
    
    if 'gemm' in s and ('improve' in s or 'performance' in s or 'optimiz' in s):
        return f"Optimize RVV GEMM f32 kernel through SIMD vectorization, loop optimizations, and improved instruction scheduling{ext_str}"
    
    if 'gemm' in s and ('loop unrolling' in s or 'variable' in s):
        return f"Implement variable loop unrolling in RVV GEMM kernel to balance code size and instruction-level parallelism{ext_str}"
    
    if 'gemm' in s and 'bias' in s:
        return f"Add bias fusion to RVV GEMM kernel to eliminate separate bias addition pass and reduce memory traffic{ext_str}"
    
    if 'gemm' in s and 'pre comput' in s:
        return f"Pre-compute loop-invariant values in RVV brgemm kernel to reduce repeated calculations and improve throughput{ext_str}"
    
    if 'matmul' in s and 'row/col' in s:
        return f"Implement RVV row-major and column-major matmul kernels with bias and ReLU post-op fusion{ext_str}"
    
    if 'matmul' in s and ('performance' in s or 'improve' in s):
        return f"Improve RVV matmul performance by integrating with optimized GEMM kernel for f32 data{ext_str}"
    
    if 'convolution' in s and 'vectorize' in s:
        return f"Vectorize convolution post-ops (bias, ReLU) using RVV intrinsics for in-kernel fusion{ext_str}"
    
    if 'convolution' in s or ('conv:' in s and 'improve' in s):
        return f"Optimize RVV gemm-based convolution kernel through improved im2col transformation{ext_str}"
    
    if 'conv:' in s and 'refactor' in s:
        return f"Refactor RVV convolution kernel validation logic for cleaner code organization{ext_str}"
    
    if 'batch_normalization' in s or 'bnorm' in s:
        return f"Implement RVV-accelerated batch normalization forward pass using vectorized f32 intrinsics{ext_str}"
    
    if 'layer_normalization' in s or 'layernorm' in s:
        return f"Implement RVV layer normalization using vectorized intrinsics for f32 data{ext_str}"
    
    if 'group_normalization' in s:
        return f"Implement RVV group normalization using vectorized intrinsics for f32 data{ext_str}"
    
    if 'softmax' in s and 'jit' in s:
        return f"Apply RVV JIT affine kernel optimization for softmax f32 with runtime ISA code generation{ext_str}"
    
    if 'softmax' in s:
        return f"Implement RVV-accelerated softmax using vectorized intrinsics for f32 data{ext_str}"
    
    if 'binary' in s and ('add' in s or 'support' in s or 'feature' in s):
        return f"Implement RVV-accelerated binary element-wise operations using vectorized intrinsics{ext_str}"
    
    if 'binary' in s and 'fix' in s:
        return f"Fix RVV binary operations: memory allocation, templatization, layout checks, and Zvfh guards{ext_str}"
    
    if 'binary' in s and ('remove' in s or 'deadcode' in s):
        return f"Remove dead f16 code from RVV binary implementation to clean up unsupported code paths{ext_str}"
    
    if 'eltwise' in s and 'zvfh' in s:
        return f"Guard FP16 eltwise kernels behind DNNL_RISCV_USE_ZVFH_INTRINSICS compile-time flag{ext_str}"
    
    if 'eltwise' in s and ('add' in s or 'feature' in s):
        return f"Implement RVV-accelerated element-wise operations (ReLU, tanh, sigmoid, etc.) using vectorized intrinsics{ext_str}"
    
    if 'eltwise' in s and 'fix' in s:
        return f"Fix RVV eltwise kernel templatization and conditional compilation guards{ext_str}"
    
    if 'eltwise' in s and 'rebase' in s:
        return f"Rebase RVV eltwise implementation and remove unsupported f16 dead code paths{ext_str}"
    
    if 'pooling' in s and 'nchw' in s and ('f16' in s or 'fp16' in s):
        return f"Add FP16 NCHW average pooling support using RVV intrinsics with Zvfh extension{ext_str}"
    
    if 'pooling' in s and 'nchw' in s:
        return f"Implement NCHW data layout pooling using RVV intrinsics for f32 data{ext_str}"
    
    if 'pooling' in s and 'nhwc' in s and ('f16' in s or 'fp16' in s):
        return f"Add FP16 NHWC pooling support using RVV intrinsics with Zvfh extension{ext_str}"
    
    if 'pooling' in s and 'nhwc' in s:
        return f"Implement NHWC data layout pooling integration using RVV intrinsics{ext_str}"
    
    if 'pooling' in s and 'multithread' in s:
        return f"Enable multithreaded RVV average pooling using parallel_nd for thread-level parallelism{ext_str}"
    
    if 'pooling' in s and 'simplify' in s:
        return f"Simplify RVV pooling dispatch condition for cleaner code organization{ext_str}"
    
    if 'pooling' in s and 'verbose' in s:
        return f"Add verbose dispatch support to RVV pooling for debugging and logging{ext_str}"
    
    if 'pooling' in s and ('maxpool' in s or 'optimize' in s):
        return f"Optimize RVV max pooling kernel for improved f32 performance{ext_str}"
    
    if 'pooling' in s and ('edge crash' in s or 'fix' in s):
        return f"Fix RVV pooling edge case crashes and correct kernel dispatch logic{ext_str}"
    
    if 'inner product' in s or ('ip:' in s and 'fix' in s):
        return f"Implement RVV inner product using GEMM kernel integration for f32 performance{ext_str}"
    
    if 'reorder' in s:
        return f"Implement RVV reorder kernel for f32 to u8 data type conversion in matmul pipeline{ext_str}"
    
    if 'postops' in s or 'post_ops' in s:
        if 'binary' in s:
            return f"Add RVV binary post-ops support for primitive fusion in deep learning kernels{ext_str}"
        if 'eltwise' in s:
            return f"Integrate RVV eltwise post-ops into primitive pipeline for in-kernel activation fusion{ext_str}"
        if 'fix' in s or 'remove' in s:
            return f"Fix and cleanup RVV post-ops implementation: remove verbose info, fix dispatch, fix multiple postops loop{ext_str}"
        return f"Implement and optimize RVV post-operation support for primitive fusion{ext_str}"
    
    if 'cmake' in s or 'build flag' in s or 'march' in s:
        if 'dynamic' in s or 'enable' in s:
            return f"Enable dynamic -march flag selection (rv64gc vs rv64gcv) in CMake based on RVV intrinsic compilation capability{ext_str}"
        return f"Configure CMake build system for RV64: RVV intrinsic detection, compiler flags, and toolchain setup{ext_str}"
    
    if 'gcc ice' in s:
        return f"Work around GCC ICE (Internal Compiler Error) by adjusting compiler optimization flags for RV64{ext_str}"
    
    if 'clang-format' in s:
        return f"Fix clang-format formatting errors in RV64 source files for consistent code style{ext_str}"
    
    if 'eol' in s:
        return f"Add end-of-line at EOF in RV64 source files to comply with POSIX standards{ext_str}"
    
    if 'copyright' in s:
        return f"Add or update copyright headers in RV64 source files to reflect proper entity attribution{ext_str}"
    
    if 'deadcode' in s or ('dead' in s and 'code' in s):
        return f"Remove dead f16 code from RVV implementation to eliminate unused code paths{ext_str}"
    
    if 'governance' in s:
        return f"Add RV64 team as code owner for RV64-related components in project governance{ext_str}"
    
    if 'maintainer' in s:
        return f"Establish maintainers for RV64 component in project governance structure{ext_str}"
    
    if 'ci test' in s or 'weekly ci' in s:
        return f"Add weekly CI test configuration for RV64 platform to ensure ongoing compatibility{ext_str}"
    
    if 'benchdnn' in s and 'f16' in s:
        return f"Enable f16 graph test coverage for RV64 in benchdnn test framework{ext_str}"
    
    if 'benchdnn' in s:
        return f"Temporarily skip failing f16 graph tests on RV64 in benchdnn test framework{ext_str}"
    
    if 'review feedback' in s or 'address' in s:
        return f"Address code review feedback for RVV GEMM kernel: clean up and stabilize f32 performance{ext_str}"
    
    if 'header guard' in s:
        return f"Align header guard naming conventions across RV64, PPC64, and S390X platforms{ext_str}"
    
    if 'runtime' in s and 'zvfh' in s:
        return f"Add runtime Zvfh extension detection and platform support flags for RV64{ext_str}"
    
    if 'macros' in s or 'CPU_INSTANCE' in s:
        return f"Add CPU_INSTANCE_RV64GCV_ZVFH macro for conditional RV64+Zvfh primitive registration{ext_str}"
    
    if 'encapsulate' in s:
        return f"Encapsulate RISC-V CPU member variables for better code organization and abstraction{ext_str}"
    
    if 'register jit' in s:
        return f"Register RVV JIT code with jit_utils framework to enable JIT dump debugging{ext_str}"
    
    if 'rebalance' in s:
        return f"Rebalance weekly CI test partitions for RV64 to optimize test distribution{ext_str}"
    
    if 'dropout' in s:
        return f"Add dropout attribute check to RVV matmul primitive for training support{ext_str}"
    
    if 'all -inf' in s or 'softmax_accurate' in s:
        return f"Handle all-negative-infinity input case in RVV softmax accurate path to prevent NaN{ext_str}"
    
    if 'parallel' in s:
        return f"Fix parallel execution method in RVV inner product to avoid data races{ext_str}"
    
    if 'negat' in s:
        return f"Fix RVV pooling incorrect results on negative input values{ext_str}"
    
    if 'missing' in s and 'include' in s:
        return f"Add missing primitive header include in RV64 source files{ext_str}"
    
    if 'template' in s or 'de-templat' in s:
        return f"De-templatize RVV NCHW pooling implementation for simpler code structure{ext_str}"
    
    if 'channels' in s and 'blocked' in s:
        return f"Remove channel-blocked layout support from RVV eltwise to simplify code{ext_str}"
    
    # Fallback: generic
    return f"{technique}{ext_str}"

def process_all():
    pool = read_pool()
    existing_ideas = {idea["id"]: idea for idea in pool["ideas"]}
    
    input_files = sorted(glob.glob(os.path.join(DATA_DIR, "*_input.json")))
    print(f"Processing {len(input_files)} input files...")
    
    stats = {"new_ideas": 0, "matched": 0, "outputs": 0}
    new_ideas_added = []
    
    for fpath in input_files:
        basename = os.path.basename(fpath)
        output_basename = basename.replace("_input.json", "_output.json")
        output_path = os.path.join(DATA_DIR, output_basename)
        
        with open(fpath) as f:
            data = json.load(f)
        
        subject = data.get("patch_subject", "")
        diff = data.get("code_diff", "")
        
        # Determine idea
        idea_id = classify_patch(subject, diff)
        thought_text = generate_thought(subject, diff)
        exts = get_extensions(diff)
        
        # Ensure idea exists in pool
        if idea_id not in existing_ideas:
            idea_def = next((i for i in IDEAS if i["id"] == idea_id), None)
            if idea_def:
                # Check if already added in this batch
                existing_idea = next((i for i in new_ideas_added if i["id"] == idea_id), None)
                if existing_idea:
                    idea = existing_idea
                else:
                    pool["ideas"].append(idea_def)
                    existing_ideas[idea_id] = idea_def
                    new_ideas_added.append(idea_def)
                    stats["new_ideas"] += 1
                    idea = idea_def
            else:
                # Fallback: create generic idea
                new_id = f"idea-{len(pool['ideas']) + 1:04d}"
                idea = {
                    "id": new_id,
                    "title": subject[:60],
                    "riscv_extensions": exts
                }
                pool["ideas"].append(idea)
                existing_ideas[idea_id] = idea
                new_ideas_added.append(idea)
                stats["new_ideas"] += 1
        else:
            idea = existing_ideas[idea_id]
            # Broaden extensions if needed
            for ext in exts:
                if ext not in idea.get("riscv_extensions", []):
                    idea.setdefault("riscv_extensions", []).append(ext)
                    idea["riscv_extensions"].sort()
            stats["matched"] += 1
        
        idea_title = idea.get("title", "V Extension Optimization")

        # Build output
        output = {
            "patch": {
                "patch_subject": subject,
                "commit_message": data.get("commit_message", ""),
                "code_diff": diff
            },
            "thought": thought_text,
            "idea": idea_title
        }
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)
        
        stats["outputs"] += 1
        
        sha = basename.split("_")[2][:10] if len(basename.split("_")) > 2 else "?"
        subj_short = subject[:70]
        print(f"  [{sha}] → {idea_id} | {subj_short}")
    
    # Save updated pool
    save_pool(pool)
    
    print(f"\n{'='*55}")
    print(f"  Total processed: {stats['outputs']}")
    print(f"  New ideas created: {stats['new_ideas']}")
    print(f"  Matched to existing: {stats['matched']}")
    print(f"  Total ideas in pool: {len(pool['ideas'])}")
    print(f"  Pool saved to: {POOL_PATH}")
    print(f"{'='*55}")

if __name__ == "__main__":
    process_all()
