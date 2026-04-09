# Common Qualified/Unqualified Patterns

Derived from analysis of 13 qualified and 10 unqualified sample forms from 上海沁宇堂中医门诊部.

## Qualified Patterns

### Pattern A: Complete 治疗单 with Acupoints

**Example**: Patient with 腰痹(气滞血瘀证) / 腰椎侧弯

- Items: 常规针法(1次/日), 红外线治疗TDP(1区), 中药烫熨(1次), 腰部疾病推拿(1次), 穴位埋入(4穴位)
- Each item has 部位/穴位 clearly specified (e.g., 腰俞、长强、下髎、上髎、中髎、大肠俞、关元俞)
- Treatment log: dates, doctor+patient signatures present
- Diagnosis matches treatment body parts

**Why qualified**: All 7 dimensions pass. Body parts match diagnosis, acupoints specified, pricing correct, log complete.

### Pattern B: Complete 治疗申请单 with Full Log

**Example**: Patient with 混合型颈椎病 / 项痹 / 气滞血瘀证

- Items: 脊柱部位疾病推拿(3/210), 悬空灸(3/63), 常规针法(3/150), 红外线治疗TDP(3/30), 中医拔罐(3/60), 中医拔罐-药物罐加收(3/78)
- Price check: 脊柱推拿 70/次 ✓, 悬空灸 21/次 ✓, 常规针法 50/次 ✓, TDP 10/次 ✓, 拔罐 20/次 ✓, 药物罐加收 26/次 ✓
- Treatment log: all sessions recorded with dates, times, items, dual signatures
- 药物罐(加收) correctly paired with base 中医拔罐

**Why qualified**: Pricing matches 一级 hospital standards, surcharge paired correctly, log complete.

### Pattern C: Multi-Department Treatment with Handwritten Body Parts

**Example**: Patient with 慢性胃炎 / 胃痞病 / 痰湿瘀滞证

- Items: 常规针法(5/250), 悬空灸(5/105), 中药烫熨(5/215), 中医拔罐(5/100), 中医拔罐-药物罐加收(5/130), 穴位埋入(25/375), 脏腑疾病推拿(5/390)
- Body parts handwritten: 中脘、下脘、天枢、足三里 (for 常规针法); 腹部 (for 悬空灸)
- Acupoints appropriate for gastrointestinal condition

**Why qualified**: Handwritten body parts acceptable, acupoints match GI diagnosis, prices correct.

### Pattern D: Stackable Needle Methods

**Example**: Patient with 头痛 / 慢性偏头痛 / 肝郁气滞证

- Items include both 常规针法(5/250) and 特殊穴位(部位)针法(10/150) -- this is ALLOWED
- 特殊穴位针法 CAN stack with 常规针法 per policy
- Also includes 耳穴疗法(5/60) which is independently billable

**Why qualified**: 特殊穴位针法 stacking with 常规针法 is explicitly permitted by policy.

---

## Unqualified Patterns

### Pattern X: Diagnosis-Treatment Mismatch (诊治不符)

**Example**: Patient diagnosed with 扁桃体恶性肿瘤 / 侠瘿痛 / 气阴两虚证

- Treatment includes: 腰部疾病推拿(5/400), 常规针法(5/250), etc.
- 扁桃体 (tonsil) is in the throat area, but 腰部疾病推拿 treats the lower back
- No logical connection between tonsil tumor and lumbar massage

**Dimension failed**: #2 Diagnosis-Treatment Consistency

### Pattern Y: Empty Treatment Log (治疗记录空白)

**Example**: Same patient as Pattern X

- 治疗项目 table lists 7 items with 5 sessions each, totaling 1575 yuan
- Treatment log section (治疗日期/起止时间/治疗项目/患者签名/医师签名) is COMPLETELY BLANK
- No evidence that any treatment was actually performed

**Dimension failed**: #6 Treatment Log Completeness

### Pattern Z: Incomplete Treatment Records

**Example**: Patient diagnosed with 腰痹(湿热蕴结下焦证) / 陈旧性腰肌劳损

- Prescribed 3 sessions (治疗次数: 3天)
- Treatment log has only 1 date entry instead of 3
- Missing doctor signatures for unrecorded sessions

**Dimension failed**: #6 Treatment Log Completeness (recorded sessions < prescribed count)

### Pattern W: Missing Body Part Specification

**Example**: Patient with 疲劳综合征 / 腰肌劳损 / 气血两虚证

- 5 treatment items listed, all with empty 部位 column
- Items: 中医拔罐-药物罐(加收), 中药烫熨, 悬空灸, 中医拔罐, 腰部疾病推拿
- No indication of where treatments are applied

**Dimension failed**: #7 Body Part Specification

### Pattern V: Surcharge Without Base Item or Incorrect Order

**Example**: 中医拔罐-药物罐(加收) listed as item #1, but 中医拔罐 (base item) listed as item #4

- While both items exist, the ordering suggests potential billing irregularity
- In well-formed prescriptions, the base item should precede or be clearly paired with its surcharge

**Dimension potentially flagged**: #4 Surcharge Item Rules

### Pattern U: Treatment Date Gaps

**Example**: Patient with 混合型颈椎病 / 项痹

- Treatment dates span from 2025-11-23 to 2026-03-05 (over 3 months gap)
- Only 3 sessions recorded across this period for an acute condition
- Unusually long intervals suggest irregular treatment continuity

**Dimension flagged**: #6 Treatment Log Completeness (unreasonable time gaps)

---

## Quick Red Flags Checklist

When reviewing a form, immediately flag if you spot any of:

1. Diagnosis mentions organ/body area X, but treatments target area Y
2. Treatment log is empty or has fewer entries than prescribed sessions
3. Both 常规针法 and 特殊针具针法 appear as separate line items (stacking violation)
4. 加收 item exists without its corresponding base item
5. Unit price doesn't match the 一级 hospital price table
6. 部位/穴位 column is completely blank for all items
7. Missing doctor signature or patient signature in treatment log
8. Missing clinic stamp or doctor stamp
