# 行情拉取落盘规范

## 绝对红线
**禁止读取、import、复制本机任何其他文件夹里的代码**。本任务所有逻辑自己写，只允许：
- 读取本模块 `data/` 下的批次 JSON（数据）
- 调用行情 MCP 工具取数

## 输入
批次文件：`data/batch_NN.json`
格式：数组，每项 `{"sec":"sz002185","code":"002185","name":"华天科技","industry":"..."}`
- `sec` = 带市场前缀代码，用于请求
- `code` = 6 位纯数字，用于文件名

## 取数
工具：`mcp__westock-mcp__data_kline`（先用 ToolSearch 加载，再用 DeferExecuteTool 调用）

参数：
- `codes` = 该批内 `sec` 逗号连接，全量一次传入
- `period` = `"day"`
- `fq` = `"qfq"`
- `limit` = `160`
- `end` = `"2026-10-13"`

## 落盘
对每个返回成功的 symbol，写文件 `data/klines/{6位code}.json`：

```json
{
  "code": "002185",
  "name": "华天科技",
  "industry": "集成电路封测",
  "source": "westock data_kline qfq day",
  "fetched_at": "<ISO8601 +08:00>",
  "bar_count": 160,
  "start": "2026-02-09",
  "end": "2026-10-13",
  "bars": [
    {"date":"2026-02-09","open":8.45,"close":8.56,"high":8.56,"low":8.41,"volume":491773.0,"amount":418413282.19}
  ]
}
```

字段映射（必须严格）：
- `close` ← 接口返回的 `last`
- `open` / `high` / `low` / `volume` / `amount` 同名直取
- bars 按日期**升序**（接口返回是降序，必须 reverse）

## 异常处理
- 某个 symbol 报错或无 nodes：跳过，**不要写文件**，记入失败清单
- 接口整体失败：最多重试 1 次

## 回报（SendMessage 给 main）
只回一行统计，不要回传行情数据本身：
`batch_NN: ok=<成功数> fail=<失败数> failed_codes=[...]`
