# 仪表盘模块 API

提供服务器整体状态快照，供仪表盘页面展示。

**路由前缀**: `/api/dashboard`
**相关文件**: `modules/dashboard/routes.py`, `modules/dashboard/collectors.py`

---

## 端点列表

### GET /api/dashboard/overview

获取服务器整体状态概览，包含 CPU、内存、磁盘、GPU、系统信息及额外挂载盘。

**权限**: 任意已登录用户（user / admin）

**请求参数**: 无

**成功响应** `200`:

```json
{
  "hostname": "system-NF5468M6",
  "uptime": "12 days, 3:45:22",
  "cpu": {
    "percent": 12.5,
    "count": 160
  },
  "memory": {
    "total": 541065216000,
    "used": 102400000000,
    "percent": 18.9
  },
  "disk": {
    "total": 3758096384000,
    "used": 1073741824000,
    "percent": 28.6
  },
  "gpu": {
    "name": "NVIDIA A800 80GB PCIe",
    "memory_used": 2048,
    "memory_total": 81920,
    "utilization": 5
  },
  "extra_disks": [
    {
      "mountpoint": "/mnt/sda",
      "total": 16000000000000,
      "used": 8000000000000,
      "percent": 50.0
    }
  ]
}
```

数据为实时采集，每次请求均重新采集。
