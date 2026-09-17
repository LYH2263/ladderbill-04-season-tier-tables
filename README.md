# 12-ladderbill（阶梯电费）

Ladderbill — 居民阶梯电价分段累进（含尖峰系数）

## 启动

```bash
docker compose up --build
```

| 入口 | 地址 |
| --- | --- |
| 前端 | http://localhost:4100 |
| API | http://localhost:9100 |

## 主链

抄表录入 → 阶梯分段计费 → 账单明细

## 季节档位表

- 可落库多套季节方案（标识 / 名称 / 生效月份 / 完整阶梯序列 / 启用开关），启用方案的生效月份两两互斥，保存冲突返回具体月份与冲突方案标识（HTTP 409）。
- `GET /api/season-schemes/resolve?period=YYYY-MM` 按账期解析应用方案；无命中回退全局默认 tiers，回包带 `fallback: true` 与 `reason`（`no_period` / `no_matching_scheme`）。
- `POST /api/bill` 支持 `period` 与 `scheme_key`；未显式指定档表时按解析结果计费，回包 `tier_source` 标记所用方案或回退原因。
- `POST /api/season-schemes/{key}/trial` 只读试算，返回分段摘要与方案名，不写运行记录。
- 前端「季节方案」页维护方案列表与编辑，「测算台」展示本次所用方案名或 fallback 标记。

## 技术栈

Python 3.12 + FastAPI + SQLite；Vue 3 + Vite + Nginx。
