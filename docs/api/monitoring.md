# 系统监控模块 API

提供实时指标快照、历史指标查询和 GPU 详情接口。

**路由前缀**: `/api/monitoring`
**相关文件**: `modules/monitoring/routes.py`, `modules/monitoring/collectors.py`

---

## 端点列表

### GET /api/monitoring/realtime

获取当前系统所有指标的实时快照。

**权限**: 任意已登录用户（user / admin）

**请求参数**: 无

**成功响应** `200`:

```json
{
  "cpu": {
    "percent": 15.2,
    "count_logical": 160,
    "count_physical": 80,
    "freq_current": 2300.0
  },
  "memory": {
    "total": 541065216000,
    "available": 438272000000,
    "used": 102793216000,
    "percent": 19.0
  },
  "swap": {
    "total": 8589934592,
    "used": 1073741824,
    "percent": 12.5
  },
  "disk": {
    "total": 3758096384000,
    "used": 1073741824000,
    "free": 2684354560000,
    "percent": 28.6
  },
  "gpu": {
    "name": "NVIDIA A800 80GB PCIe",
    "utilization": 5,
    "memory_used": 2048,
    "memory_total": 81920,
    "temperature": 42
  },
  "network": {
    "bytes_sent": 1234567890,
    "bytes_recv": 9876543210
  },
  "timestamp": "2026-03-24T10:30:00"
}
```

---

### GET /api/monitoring/history

查询历史指标数据（从 SQLite `metrics` 表读取，由后台定时采集写入）。

**权限**: 任意已登录用户（user / admin）

**查询参数**:

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| metric | string | 必填 | `cpu` / `memory` / `gpu` / `disk` / `all` | 指标名称 |
| hours | int | 24 | 1 ~ 720 | 查询最近多少小时 |

**成功响应** `200`:

```json
[
  {
    "timestamp": "2026-03-24T09:00:00",
    "value": 12.5
  },
  {
    "timestamp": "2026-03-24T09:05:00",
    "value": 14.2
  }
]
```

当 `metric=all` 时，`value` 字段为 JSON 字符串（完整指标对象序列化结果）。

---

### GET /api/monitoring/gpu

获取详细 GPU 信息（通过 `nvidia-smi` 采集）。

**权限**: 任意已登录用户（user / admin）

**请求参数**: 无

**成功响应** `200`:

```json
{
  "available": true,
  "name": "NVIDIA A800 80GB PCIe",
  "driver_version": "535.129.03",
  "cuda_version": "12.2",
  "memory_used_mb": 2048,
  "memory_total_mb": 81920,
  "memory_free_mb": 79872,
  "utilization_gpu": 5,
  "utilization_memory": 2,
  "temperature": 42,
  "power_draw": 85.5,
  "power_limit": 300.0
}
```

若无 GPU 或 nvidia-smi 不可用：

```json
{
  "available": false,
  "error": "nvidia-smi not found"
}
```
