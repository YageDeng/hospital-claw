# Knowledge Base Design: MinerU Document Explorer for Hospital Training Docs

**Date:** 2026-04-07
**Status:** Approved
**Scope:** Process and summarize TCM training documents, build a local knowledge base, refactor existing skills to use KB as single source of truth

---

> **2026-04-09 compatibility update:** The original design assumed a `qmd index` workflow. On this machine, `qmd 1.0.5` does not provide `index`, so implementation now uses Markdown conversion + `qmd collection add --mask "**/*.md"` for searchable inputs, and collection-relative `qmd wiki ingest` + `qmd wiki write` for wiki output. Treat the implementation plan and issue log as the operational source of truth for command syntax.

## 1. Architecture Overview

The system has 4 layers:

```
┌─────────────────────────────────────────────────────┐
│                  Ingestion Layer                     │
│  ┌────────────┐ ┌──────────────┐ ┌───────────────┐  │
│  │ Manual docs│ │ YB Policy    │ │ Skill rules   │  │
│  │ (PDF/DOCX/ │ │ Monitor      │ │ (manual       │  │
│  │  PPTX/XLSX)│ │ (auto-fetch) │ │  additions)   │  │
│  └─────┬──────┘ └──────┬───────┘ └───────┬───────┘  │
│        └───────────┬───┴─────────────────┘           │
│                    ▼                                 │
│        knowledge-base-update skill                   │
│        (unified ingestion command)                   │
└────────────────────┬────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────┐
│              MinerU Document Explorer                │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │ Indexing  │  │ LLM Wiki  │  │ Hybrid Search    │  │
│  │ (qmd idx) │  │ Generator │  │ (BM25+vec+rerank)│  │
│  └──────────┘  └───────────┘  └──────────────────┘  │
└────────────────────┬────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────┐
│               Knowledge Base (output)                │
│  docs/knowledge-base/                                │
│  ├── wiki/          (interlinked topic pages)        │
│  └── index/         (MinerU search index)            │
└────────────────────┬────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────┐
│               Consumer Layer                         │
│  ┌──────────────────┐  ┌─────────────────────────┐  │
│  │ MCP Server       │  │ Versioned Skills         │  │
│  │ (qmd mcp --http) │  │ v2: KB-powered           │  │
│  │ 15 query tools   │  │ v1: archived originals   │  │
│  └──────────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**Key principle:** Documents flow in from 3 sources → processed by MinerU → stored as wiki + index in `docs/knowledge-base/` → consumed by MCP server and refactored skills.

**Dual purpose:** The knowledge base serves both skill authoring (developer workflow — browsing wiki pages for accurate policy details) and agent runtime (MCP queries during patient interactions).

---

## 2. Document Processing & Indexing

### 2.1 Source Documents

26 files in `docs/医院材料学习/`, ~148 MB total:

| Format | Count | Size | MinerU Support |
|--------|-------|------|----------------|
| PDF    | 17    | 114 MB | Native |
| PPTX   | 2     | 34 MB  | Native |
| DOCX   | 4     | 0.17 MB | Native |
| XLSX   | 3     | 0.07 MB | Pre-convert to markdown |

### 2.2 XLSX Handling

XLSX files are pricing mapping tables and inspection results — critical tabular data. A Python helper script converts them before ingestion:

- Extract each sheet as a markdown table using `openpyxl`
- Preserve column headers and data
- Save as `.md` files in `docs/knowledge-base/.staging/`
- Index the markdown versions via MinerU

### 2.3 Indexing Commands

```bash
qmd index docs/医院材料学习/              # PDFs, DOCX, PPTX
qmd index docs/knowledge-base/.staging/   # converted XLSX → MD
```

### 2.4 Search Pipeline

Once indexed, MinerU provides hybrid search:
- **BM25** — keyword matching
- **Vector embeddings** — semantic similarity (embeddinggemma-300M, ~300MB)
- **LLM reranking** — result quality (qwen3-reranker-0.6b, ~640MB)
- **Query expansion** — broader recall (qmd-query-expansion-1.7B, ~1.1GB)

Models auto-download on first use (~2GB total).

### 2.5 Prerequisites

| Requirement | Version |
|-------------|---------|
| Node.js     | >= 22   |
| Python      | >= 3.10 |
| Python packages | `pymupdf`, `python-docx`, `python-pptx`, `openpyxl` |

---

## 3. Wiki Structure & Organization

### 3.1 Taxonomy

Seed with 5 domain categories, let MinerU auto-organize subtopics within each:

```
docs/knowledge-base/wiki/
├── 医保价格政策/                    # Insurance pricing policies
│   ├── 针法类价格标准.md
│   ├── 灸法类价格标准.md
│   ├── 推拿类价格标准.md
│   ├── 拔罐类价格标准.md
│   ├── 加收项规则.md
│   └── ...
│
├── 治疗方法规则/                    # Treatment method rules
│   ├── 针法互斥与叠加规则.md
│   ├── 穴位埋入操作规范.md
│   ├── 中药烫熨规范.md
│   └── ...
│
├── 合规检查标准/                    # Compliance & inspection standards
│   ├── 七大审查维度.md
│   ├── 表单完整性要求.md
│   ├── 诊治一致性标准.md
│   ├── 医保检查案例分析.md
│   └── ...
│
├── 信息化建设/                     # IT & digitalization
│   ├── 协爱集团信息化方案.md
│   ├── 医保信息安全要求.md
│   └── ...
│
└── 医院运营管理/                    # Hospital operations
    ├── 降本增效策略.md
    ├── 履约考核指标.md
    ├── 监管应对体系.md
    └── ...
```

### 3.2 Wiki Page Format

Each `.md` page contains:
- Header with category and last-updated date
- Extracted knowledge organized by subtopic
- Source citations (which document(s) the information came from)
- Cross-links to related wiki pages

### 3.3 Generation Strategy

1. Index all documents first
2. Run MinerU's wiki ingest with the 5-category seed taxonomy
3. MinerU reads across all indexed docs, merges related content from different sources into consolidated wiki pages
4. Content that doesn't fit the 5 categories → MinerU auto-creates new subcategories

---

## 4. MCP Integration

### 4.1 Server Configuration

HTTP daemon mode in `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "qmd": {
      "url": "http://localhost:8181/mcp"
    }
  }
}
```

Start before agent sessions: `qmd mcp --http --daemon`

### 4.2 Tool Groups for Skills

| Group | Tools | Use Case |
|-------|-------|----------|
| **Retrieve** | `search`, `query`, `vsearch` | Look up pricing rules, compliance standards, policy details |
| **Deep Read** | `doc_toc`, `doc_read`, `doc_grep` | Navigate into a specific source document for exact wording |
| **Wiki** | `wiki_list`, `wiki_read`, `wiki_search` | Browse the structured wiki for consolidated knowledge |

### 4.3 Runtime Query Example

`tcm-treatment-plan` v2 generating a treatment plan:
1. Agent receives patient symptoms
2. Skill instructs: "Query the knowledge base for current pricing for 针法类 items at 一级机构"
3. MCP `query` tool returns the latest pricing from indexed policy docs
4. Skill instructs: "Check wiki page for 针法互斥与叠加规则"
5. MCP `wiki_read` returns the consolidated stacking rules
6. Agent generates the plan using live data instead of hardcoded tables

### 4.4 Fallback Behavior

If the MCP server is not running, refactored skills should still function — they log a warning that KB is unavailable and note that results may not reflect the latest policy updates. The skill logic itself remains sound; only the data source changes.

---

## 5. Knowledge Base Update Skill

### 5.1 Overview

New skill at `skills/knowledge-base-update/SKILL.md` unifying all 3 ingestion paths.

### 5.2 Three Ingestion Modes

| Mode | Trigger | What It Does |
|------|---------|--------------|
| **`docs`** | "Update KB with new documents" | Scans `docs/医院材料学习/` for files not yet indexed, converts XLSX if needed, runs `qmd index`, regenerates affected wiki pages |
| **`policy`** | "Fetch latest policies and update KB" | Calls `sh-yb-policy-monitor` to fetch new policies from ybj.sh.gov.cn, saves to `docs/医院材料学习/`, then runs the `docs` flow |
| **`rules`** | "Add new rule to knowledge base" | Accepts manually authored rule content, saves as markdown in `docs/knowledge-base/.manual-rules/`, indexes it, updates relevant wiki pages |

### 5.3 Update Workflow

```
1. Detect changes
   ├── docs mode:   diff file list vs index manifest
   ├── policy mode: run sh-yb-policy-monitor fetch
   └── rules mode:  accept user input, save to .manual-rules/

2. Pre-process
   ├── Convert XLSX → markdown (if any)
   └── Validate file formats

3. Index
   └── qmd index <new-files-only>  (incremental)

4. Wiki regeneration
   └── qmd wiki ingest (updates affected pages, preserves manual edits)

5. Report
   ├── List of new/updated documents
   ├── Wiki pages created or modified
   └── Any errors or unsupported files
```

### 5.4 Index Manifest

`docs/knowledge-base/.manifest.json` tracks:
- Every indexed file's path, content hash, and index timestamp
- On re-run, only new or changed files get re-indexed

---

## 6. Skill Versioning & Refactoring

### 6.1 Version Folder Structure

```
skills/
├── tcm-treatment-plan/
│   ├── v1/                       # Original — hardcoded rules
│   │   ├── SKILL.md
│   │   └── 方案参考.md
│   ├── v2/                       # Refactored — KB-powered
│   │   ├── SKILL.md
│   │   └── 方案参考.md
│   └── SKILL.md                  # Copy of latest version (v2)
│
├── tcm-treatment-review/
│   ├── v1/                       # Original
│   │   ├── SKILL.md
│   │   ├── standards.md
│   │   └── examples.md
│   ├── v2/                       # Refactored — queries KB for pricing
│   │   ├── SKILL.md
│   │   ├── standards.md          # Replaced with KB reference
│   │   └── examples.md           # Kept — examples are skill-specific
│   └── SKILL.md                  # Copy of latest version
│
├── sh-yb-policy-monitor/
│   ├── v1/
│   │   ├── SKILL.md
│   │   └── scripts/fetch_policies.py
│   ├── v2/                       # Enhanced — feeds into KB update
│   │   ├── SKILL.md
│   │   └── scripts/fetch_policies.py
│   └── SKILL.md
│
└── knowledge-base-update/        # New skill (starts at v1)
    ├── v1/
    │   └── SKILL.md
    └── SKILL.md
```

### 6.2 What Changes in v2

| Skill | v1 (Current) | v2 (Refactored) |
|-------|-------------|-----------------|
| `tcm-treatment-plan` | Hardcoded pricing tables, rules in SKILL.md (~186 lines) | Thin orchestration: instructs agent to query KB for pricing/rules, keeps only treatment logic and output template |
| `tcm-treatment-review` | Hardcoded `standards.md` with full price tables | 7-dimension review logic stays, pricing lookups go through KB. `standards.md` becomes a "query KB for latest" instruction |
| `sh-yb-policy-monitor` | Fetches policies, saves locally | Same + triggers KB update after fetching |

### 6.3 Versioning Rules

- `v1` = original pre-KB version (archived as-is)
- `v2` = KB-powered refactor
- Future: `v3`, `v4`... as policies change or skill logic evolves
- Each version folder is a complete, self-contained snapshot — rollback by copying a previous version to root
- Root `SKILL.md` is always a copy of the latest version (copy, not symlink, for Windows compatibility)

---

## 7. Directory Structure (Complete)

```
hospital-claw/
├── .cursor/
│   └── mcp.json                          # MinerU MCP server config
│
├── docs/
│   ├── 医院材料学习/                       # Source training documents (26 files)
│   │   ├── *.pdf
│   │   ├── *.docx
│   │   ├── *.pptx
│   │   └── *.xlsx
│   │
│   ├── knowledge-base/                    # Generated knowledge base
│   │   ├── wiki/                          # Interlinked wiki pages (5 categories)
│   │   │   ├── 医保价格政策/
│   │   │   ├── 治疗方法规则/
│   │   │   ├── 合规检查标准/
│   │   │   ├── 信息化建设/
│   │   │   └── 医院运营管理/
│   │   ├── index/                         # MinerU search index
│   │   ├── .staging/                      # XLSX → MD conversions
│   │   ├── .manual-rules/                 # Manually authored rules
│   │   └── .manifest.json                 # Index tracking manifest
│   │
│   └── superpowers/specs/                 # Design documents
│
├── skills/
│   ├── tcm-treatment-plan/    (v1/, v2/, SKILL.md)
│   ├── tcm-treatment-review/  (v1/, v2/, SKILL.md)
│   ├── sh-yb-policy-monitor/  (v1/, v2/, SKILL.md)
│   └── knowledge-base-update/ (v1/, SKILL.md)
│
└── wechat-router/                         # Existing WeChat monitor app
```

---

## 8. Implementation TODO

- [ ] **Phase 1: Setup**
  - [ ] Install Node.js >= 22 (verify with `node --version`)
  - [ ] Install MinerU Document Explorer (`npm install -g mineru-document-explorer`)
  - [ ] Install Python dependencies (`pip install pymupdf python-docx python-pptx openpyxl`)
  - [ ] Verify installation (`qmd --version`)

- [ ] **Phase 2: Document Processing**
  - [ ] Write XLSX → markdown conversion script
  - [ ] Run XLSX conversion for the 3 Excel files
  - [ ] Index all documents (`qmd index`)
  - [ ] Verify index with test queries

- [ ] **Phase 3: Wiki Generation**
  - [ ] Configure seed taxonomy (5 categories)
  - [ ] Run wiki generation (`qmd wiki ingest`)
  - [ ] Review generated wiki pages for accuracy
  - [ ] Fix any miscategorized or missing content

- [ ] **Phase 4: MCP Integration**
  - [ ] Create `.cursor/mcp.json` with MinerU HTTP config
  - [ ] Start MCP daemon and verify with health check
  - [ ] Test MCP queries from agent context

- [ ] **Phase 5: Skill Versioning**
  - [ ] Archive `tcm-treatment-plan` current files → `v1/`
  - [ ] Archive `tcm-treatment-review` current files → `v1/`
  - [ ] Archive `sh-yb-policy-monitor` current files → `v1/`

- [ ] **Phase 6: Skill Refactoring**
  - [ ] Create `tcm-treatment-plan/v2/SKILL.md` — replace hardcoded pricing with KB queries
  - [ ] Create `tcm-treatment-review/v2/SKILL.md` — replace `standards.md` with KB lookups
  - [ ] Create `sh-yb-policy-monitor/v2/SKILL.md` — add KB update trigger after fetch
  - [ ] Create `knowledge-base-update/v1/SKILL.md` — new unified update skill
  - [ ] Copy latest versions to root `SKILL.md` for each skill

- [ ] **Phase 7: Testing & Validation**
  - [ ] Test `knowledge-base-update` skill with each ingestion mode (docs, policy, rules)
  - [ ] Test `tcm-treatment-plan` v2 with a sample patient case
  - [ ] Test `tcm-treatment-review` v2 with a sample treatment form
  - [ ] Verify fallback behavior when MCP server is not running
  - [ ] Verify incremental indexing (add a new doc, re-run update)
