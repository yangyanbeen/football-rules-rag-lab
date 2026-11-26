# E39 逐条引用支持审计

本报告只检查最终选中段是否在既有 source-review 台账中被判定为直接支持；不把“答案看起来正确”当作引用支持，也不新增模型调用。

- 范围：90 题真实 E39 Worker 结果
- 直接支持：**100/155（64.52%）**
- 未直接支持：55 条

## 按段统计

| 段 ID | 直接支持 | 引用总数 | 支持率 |
|---|---:|---:|---:|
| L01-01 | 2 | 2 | 100.00% |
| L01-02 | 1 | 1 | 100.00% |
| L01-03 | 1 | 1 | 100.00% |
| L01-05 | 1 | 1 | 100.00% |
| L01-06 | 2 | 2 | 100.00% |
| L01-07 | 0 | 2 | 0.00% |
| L02-01 | 1 | 1 | 100.00% |
| L02-02 | 2 | 2 | 100.00% |
| L03-01 | 3 | 3 | 100.00% |
| L03-02 | 0 | 3 | 0.00% |
| L03-03 | 1 | 1 | 100.00% |
| L03-04 | 3 | 3 | 100.00% |
| L04-01 | 2 | 3 | 66.67% |
| L04-02 | 1 | 1 | 100.00% |
| L04-03 | 1 | 1 | 100.00% |
| L05-01 | 1 | 1 | 100.00% |
| L05-02 | 1 | 1 | 100.00% |
| L05-03 | 2 | 3 | 66.67% |
| L05-04 | 1 | 2 | 50.00% |
| L06-01 | 1 | 1 | 100.00% |
| L06-02 | 1 | 3 | 33.33% |
| L06-04 | 1 | 2 | 50.00% |
| L06-05 | 0 | 1 | 0.00% |
| L06-06 | 2 | 2 | 100.00% |
| L07-01 | 4 | 4 | 100.00% |
| L07-02 | 1 | 2 | 50.00% |
| L07-03 | 3 | 3 | 100.00% |
| L08A-01 | 1 | 1 | 100.00% |
| L08A-02 | 1 | 1 | 100.00% |
| L08A-03 | 2 | 2 | 100.00% |
| L08B-02 | 2 | 2 | 100.00% |
| L08B-03 | 2 | 2 | 100.00% |
| L08B-04 | 2 | 2 | 100.00% |
| L09-01 | 1 | 1 | 100.00% |
| L09-02 | 3 | 4 | 75.00% |
| L09-03 | 0 | 2 | 0.00% |
| L09-04 | 1 | 1 | 100.00% |
| L10-01 | 1 | 1 | 100.00% |
| L10-02 | 2 | 3 | 66.67% |
| L11-01 | 1 | 1 | 100.00% |
| L11-03 | 0 | 1 | 0.00% |
| L11-06 | 1 | 2 | 50.00% |
| L11-09 | 1 | 1 | 100.00% |
| L12-01 | 0 | 2 | 0.00% |
| L12-02 | 0 | 2 | 0.00% |
| L12-03 | 0 | 1 | 0.00% |
| L12-04 | 1 | 1 | 100.00% |
| L12-05 | 1 | 3 | 33.33% |
| L12-06 | 1 | 2 | 50.00% |
| L12-07 | 2 | 2 | 100.00% |
| L12-08 | 1 | 3 | 33.33% |
| L12-10 | 2 | 2 | 100.00% |
| L12-11 | 1 | 1 | 100.00% |
| L12-12 | 1 | 3 | 33.33% |
| L12-14 | 1 | 1 | 100.00% |
| L12-15 | 1 | 2 | 50.00% |
| L12-16 | 0 | 1 | 0.00% |
| L13-01 | 0 | 1 | 0.00% |
| L13-02 | 1 | 1 | 100.00% |
| L13-05 | 2 | 3 | 66.67% |
| L13-06 | 0 | 2 | 0.00% |
| L13-07 | 1 | 1 | 100.00% |
| L14-02 | 2 | 2 | 100.00% |
| L14-03 | 3 | 4 | 75.00% |
| L14-04 | 1 | 2 | 50.00% |
| L14-05 | 2 | 2 | 100.00% |
| L14-06 | 0 | 1 | 0.00% |
| L15-01 | 2 | 2 | 100.00% |
| L15-02 | 1 | 1 | 100.00% |
| L15-04 | 1 | 3 | 33.33% |
| L15-05 | 1 | 5 | 20.00% |
| L16-01 | 2 | 3 | 66.67% |
| L16-02 | 1 | 2 | 50.00% |
| L16-03 | 2 | 3 | 66.67% |
| L16-04 | 1 | 4 | 25.00% |
| L17-01 | 2 | 3 | 66.67% |
| L17-03 | 1 | 2 | 50.00% |
| L17-04 | 1 | 1 | 100.00% |
| L17-05 | 1 | 1 | 100.00% |
| L17-06 | 0 | 1 | 0.00% |

## 未直接支持的逐条记录

| 题号 | 段 ID | 评分 | 状态 |
|---|---|---|---|
| D004 | L12-12 | correct | answered |
| D005 | L03-02 | correct | answered |
| D007 | L11-06 | correct | answered |
| D008 | L09-02 | correct | answered |
| D009 | L13-06 | correct | answered |
| D011 | L09-03 | correct | answered |
| D013 | L12-05 | correct | answered |
| D014 | L12-03 | correct | answered |
| D015 | L16-02 | correct | answered |
| D018 | L16-04 | correct | answered |
| D018 | L16-01 | correct | answered |
| D019 | L16-04 | correct | answered |
| D023 | L12-01 | correct | answered |
| D025 | L03-02 | correct | answered |
| D027 | L15-04 | correct | answered |
| D030 | L12-12 | correct | answered |
| T002 | L17-03 | correct | answered |
| T002 | L01-07 | correct | answered |
| T004 | L14-04 | correct | answered |
| T006 | L12-08 | correct | answered |
| T007 | L03-02 | incorrect | answered |
| T007 | L11-03 | incorrect | answered |
| T007 | L12-02 | incorrect | answered |
| T008 | L04-01 | correct | answered |
| T010 | L12-16 | correct | answered |
| T010 | L06-02 | correct | answered |
| T011 | L05-04 | correct | answered |
| T011 | L12-06 | correct | answered |
| T013 | L06-02 | correct | answered |
| T014 | L06-05 | correct | answered |
| T014 | L06-04 | correct | answered |
| T016 | L07-02 | correct | answered |
| T017 | L10-02 | correct | answered |
| T020 | L09-03 | correct | answered |
| T020 | L14-06 | correct | answered |
| T021 | L12-15 | correct | answered |
| T022 | L17-06 | partial | answered |
| T025 | L12-08 | correct | answered |
| T026 | L12-01 | correct | answered |
| T029 | L12-02 | correct | answered |
| T029 | L15-05 | correct | answered |
| T030 | L13-01 | correct | answered |
| T030 | L13-05 | correct | answered |
| T031 | L13-06 | correct | answered |
| T034 | L14-03 | partial | answered |
| T034 | L05-03 | partial | answered |
| T035 | L15-04 | correct | answered |
| T035 | L15-05 | correct | answered |
| T037 | L15-05 | correct | answered |
| T037 | L12-05 | correct | answered |
| T038 | L17-01 | correct | answered |
| T038 | L16-03 | correct | answered |
| T039 | L01-07 | correct | answered |
| T040 | L15-05 | correct | answered |
| T040 | L16-04 | correct | answered |
