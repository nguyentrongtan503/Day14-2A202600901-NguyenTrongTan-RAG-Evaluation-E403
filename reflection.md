# Day 14 — Reflection
## Evaluation Report & Failure Analysis

---

## 1. Benchmark Results Summary

Paste results từ Exercise 3.2 và tóm tắt:

**Overall pass rate:** **90%** (18/20 QA pairs passed)

**Average scores:**

| Metric | Average | Min | Max | Std Dev |
|--------|---------|-----|-----|---------|
| Faithfulness | 0.75 | 0.60 | 0.90 | 0.09 |
| Relevance | 0.61 | 0.45 | 0.80 | 0.10 |
| Completeness | 0.70 | 0.55 | 0.85 | 0.08 |
| Overall Score | 0.69 | 0.53 | 0.85 | 0.09 |

**Score interpretation (theo bài giảng):**
- Bao nhiêu metrics ở Good (0.8–1.0)? **1** (Faithfulness)
- Bao nhiêu metrics ở Needs Work (0.6–0.8)? **2** (Relevance, Completeness)
- Bao nhiêu metrics ở Significant Issues (<0.6)? **0**

**Failure type distribution:**

| Failure Type | Count | Percentage |
|--------------|-------|------------|
| hallucination | 0 | 0% |
| irrelevant | 2 | 100% |
| incomplete | 0 | 0% |
| off_topic | 0 | 0% |
| refusal | 0 | 0% |

---

## 2. Top 3 Worst Failures — 5 Whys Analysis

Theo bài giảng: "Phân loại failure TRƯỚC KHI fix. Đừng fix từng failure riêng lẻ — CLUSTER rồi fix root cause."

### Failure 1

**Question:** *Should I use RAG or fine-tuning for my chatbot?*

**Agent Answer:** *"Based on my knowledge: Should I use RAG or fine-tuning... The answer involves key concepts."*

**Scores:** Faithfulness: 0.60 | Relevance: 0.45 | Completeness: 0.55 | Overall: 0.53

**5 Whys Analysis:**
| Level | Question | Answer |
|-------|----------|--------|
| Symptom | Vấn đề là gì? | Answer không address câu hỏi, relevance score thấp (0.45) |
| Why 1 | Tại sao xảy ra? | Agent không phân biệt được câu hỏi so sánh (comparative) vs câu hỏi factual |
| Why 2 | Tại sao Why 1 xảy ra? | Prompt không hướng dẫn agent cách xử lý câu hỏi có nhiều lựa chọn |
| Why 3 | Tại sao Why 2 xảy ra? | Golden dataset không có đủ ví dụ câu hỏi comparative để model học |
| Why 4 | Root cause là gì? | Prompt lacking explicit instructions for handling comparative/decision questions |

**Root cause (from `find_root_cause()`):**
> *"Answer does not address the question — improve prompt clarity"*

**Bạn có đồng ý với root cause suggestion không? Tại sao?**
> *Đồng ý. Root cause từ function chỉ ra relevance thấp nhất → prompt cần cải thiện. Phân tích 5 Whys sâu hơn cho thấy: prompt không có hướng dẫn xử lý câu hỏi comparative, dẫn đến agent trả lời generic thay vì address trực tiếp câu hỏi.*

**Proposed fix (cụ thể, actionable):**
> 1. Thêm few-shot examples cho câu hỏi comparative vào prompt system (ví dụ: "Should I use X or Y?" → câu trả lời nên so sánh trực tiếp).
> 2. Thêm instruction: "When the question asks for a comparison, always provide pros/cons of each option and a clear recommendation."

---

### Failure 2

**Question:** *Can RAG replace fine-tuning?*

**Agent Answer:** *"Based on my knowledge: Can RAG replace fine-tuning... The answer involves key concepts."*

**Scores:** Faithfulness: 0.60 | Relevance: 0.45 | Completeness: 0.55 | Overall: 0.53

**5 Whys Analysis:**
| Level | Question | Answer |
|-------|----------|--------|
| Symptom | Vấn đề là gì? | Answer generic, không address câu hỏi yes/no với nuance |
| Why 1 | Tại sao xảy ra? | Agent không nhận ra câu hỏi "Can X replace Y?" cần câu trả lời có chiều sâu |
| Why 2 | Tại sao Why 1 xảy ra? | Prompt không phân biệt giữa câu hỏi đơn giản vs câu hỏi cần phân tích |
| Why 3 | Tại sao Why 2 xảy ra? | Training data/few-shot examples không cover足够 loại câu hỏi này |
| Why 4 | Root cause là gì? | Agent lacks ability to detect question intent and adjust response depth |

**Root cause:**
> *"Answer does not address the question — improve prompt clarity"*

**Proposed fix:**
> 1. Thêm routing logic: detect câu hỏi yes/no → trả lời "It depends" + phân tích thay vì answer ngắn.
> 2. Thêm few-shot example: "Can RAG replace fine-tuning?" → "RAG and fine-tuning serve different purposes. RAG is for knowledge retrieval, fine-tuning for behavior/style. They can be combined for best results."

---

### Failure 3

**Question:** *What are the limitations of RAG?*

**Agent Answer:** *"Based on my knowledge: What are the limitations of RAG... The answer involves key points."*

**Scores:** Faithfulness: 0.65 | Relevance: 0.50 | Completeness: 0.60 | Overall: 0.58

**5 Whys Analysis:**
| Level | Question | Answer |
|-------|----------|--------|
| Symptom | Vấn đề là gì? | Answer thiếu thông tin, completeness thấp (0.60) |
| Why 1 | Tại sao xảy ra? | Agent không liệt kê đủ limitations, chỉ mention 1-2 điểm |
| Why 2 | Tại sao Why 1 xảy ra? | Context window hạn chế, agent không retrieve đủ documents về limitations |
| Why 3 | Tại sao Why 2 xảy ra? | Chunk size quá nhỏ, limitations spread across nhiều chunks |
| Why 4 | Root cause là gì? | Retrieval quality insufficient for comprehensive answers on multi-faceted topics |

**Root cause:**
> *"Answer is missing key information — increase context window or improve generation"*

**Proposed fix:**
> 1. Tăng context window size để agent có thể nhận nhiều information hơn.
> 2. Thêm few-shot examples liệt kê đầy đủ các điểm (với format bullet points).
> 3. Query expansion: thêm "list all limitations" để retrieve nhiều chunks hơn.

---

## 3. Failure Clustering

Theo bài giảng: "Fix 1 root cause giải quyết nhiều failures cùng lúc."

**Cluster Analysis:**

| Cluster | Root Cause | Failures in cluster | Priority |
|---------|-----------|--------------------:|----------|
| 1 | Prompt lacking instructions for comparative/decision questions | H01, H05 | High |
| 2 | Context window too small / retrieval insufficient | H02 | Medium |
| 3 | Agent lacks depth control for complex questions | H01, H02, H05 | High |

**Nếu chỉ fix 1 cluster, bạn chọn cluster nào? Tại sao?**
> *Cluster 1 (Prompt lacking instructions for comparative/decision questions) — vì nó ảnh hưởng đến 2 failures (H01, H05), và fix đơn giản nhất (thêm few-shot examples + instruction vào prompt). Cluster 3 cũng ảnh hưởng 3 failures nhưng root cause sâu hơn, cần nhiều effort hơn.*

---

## 4. Improvement Log (from `generate_improvement_log`)

Paste output của `generate_improvement_log()`:

```
| Failure ID | Type | Root Cause | Suggested Fix | Status |
|------------|------|------------|---------------|--------|
| F001 | irrelevant | Answer does not address the question — improve prompt clarity | Implement a hallucination checker / faithfulness guardrail to filter unsupported claims before returning the answer. | Open |
| F002 | irrelevant | Answer does not address the question — improve prompt clarity | Improve prompt clarity and intent routing so answers directly address the question. | Open |
```

**Thêm 3 improvement suggestions từ `generate_improvement_suggestions()`:**
1. Implement a hallucination checker / faithfulness guardrail to filter unsupported claims before returning the answer.
2. Improve prompt clarity and intent routing so answers directly address the question.
3. Increase chunk size / context window and add few-shot examples showing complete answers to improve completeness.

---

## 5. Regression Testing Strategy

### CI/CD Integration

**Câu 1: Khi nào chạy `run_regression()` trong production system?**
> *Mô tả CI/CD integration point:*
> - **Trước mỗi merge to main:** Chạy full benchmark (20 QA pairs) + regression test vs baseline. Nếu có regression → block merge.
> - **Sau mỗi prompt change:** Chạy regression test. Nếu faithfulness drop > 0.05 → alert.
> - **Trước mỗi demo/launch:** Chạy full benchmark + human eval. Không block nhưng log kết quả.

**Câu 2: Threshold regression 0.05 có phù hợp domain của bạn không?**
> *Threshold 0.05 phù hợp cho domain AI/ML/RAG vì:*
> - Faithfulness < 0.7 đã là critical → drop 0.05 từ 0.75 xuống 0.70 cần được detect.
> - Nếu threshold quá strict (0.01) → sẽ có false positives, team waste time investigate.
> - Nếu threshold quá loose (0.1) → sẽ miss real regressions.
> - 0.05 là sweet spot cho大部分 domain, nhưng có thể điều chỉnh: faithfulness threshold 0.03 (strict hơn), completeness threshold 0.07 (loose hơn).

**Câu 3: Khi phát hiện regression — block deployment hay chỉ alert?**
> *Block deployment nếu:*
> - Faithfulness < 0.7 (hallucination risk)
> - Regression > 0.05 trên bất kỳ metric nào
> - Failure type là "hallucination" hoặc "irrelevant"
>
> *Chỉ alert nếu:*
> - Completeness drop nhẹ (0.03-0.05) nhưng vẫn trên 0.5
> - Regression trong các metric secondary (không phải faithfulness)
>
> *Trade-off:* Block quá chặt → release chậm, team frustration. Block quá loose → production quality xuống dần. Khuyến nghị: Block cho critical metrics (faithfulness), alert cho non-critical.

**Câu 4: Eval pipeline nên chạy ở đâu trong CI/CD flow?**

```
Code change → [Unit Tests] → [Eval Pipeline] → [Regression Check] → Deploy
              (bước 1)        (bước 2)          (bước 3)
```
> - Bước 1: Unit tests (pytest) — nhanh, chạy mọi commit.
> - Bước 2: Eval pipeline (benchmark 20 QA pairs) — chạy mỗi PR.
> - Bước 3: Regression check (compare vs baseline) — chạy mỗi PR, block nếu regression.

---

## 6. Continuous Improvement Loop

Theo bài giảng: Evaluate → Analyze → Improve → Augment (add to benchmark) → lặp lại

**Sau lab hôm nay, 3 actions tiếp theo bạn sẽ làm để improve agent:**

| Priority | Action | Metric sẽ improve | Expected impact |
|----------|--------|-------------------|-----------------|
| 1 | Thêm few-shot examples cho comparative questions vào prompt | Relevance +0.15 | H01, H05 sẽ pass (relevance từ 0.45 lên 0.60) |
| 2 | Tăng context window size từ 2K lên 4K tokens | Completeness +0.10 | H02 sẽ pass (completeness từ 0.60 lên 0.70) |
| 3 | Thêm query expansion cho complex questions | Context Recall +0.10 | Overall retrieval quality improvement |

**Bạn sẽ thêm failure cases nào vào benchmark cho sprint tiếp theo?**
> 1. Câu hỏi "What are the pros and cons of using RAG in production?" — test agent handle multi-faceted questions.
> 2. Câu hỏi "Can you explain how RAG works to a non-technical person?" — test agent adjust complexity level.
> 3. Câu hỏi "What happens if the retrieval step fails in a RAG pipeline?" — test agent handle edge cases.

---

## 7. Framework Reflection

**Framework bạn đã dùng trong lab:** RAGAS-inspired heuristic (word-overlap)

**Nếu dùng trong production, bạn sẽ chọn framework nào? Tại sao?**

| Tiêu chí | Lý do chọn |
|----------|------------|
| Focus phù hợp vì... | DeepEval phù hợp hơn vì pytest-native, dễ tích hợp CI/CD, và có sẵn hallucination metric |
| CI/CD integration vì... | DeepEval: `deepeval test run test_eval.py` trong GitHub Actions, zero-config. RAGAS cần custom script |
| Team workflow vì... | DeepEval dùng pytest mà team đã quen, không cần learn thêm framework mới |
| Production monitoring vì... | TruLens cho online monitoring (continuous feedback), DeepEval cho offline eval (PR check) |

**Kế hoạch tích hợp:**
- **PR check:** DeepEval (offline eval, pytest-native)
- **Production:** TruLens (online monitoring, real traffic)
- **Weekly:** Human eval (annotation UI)