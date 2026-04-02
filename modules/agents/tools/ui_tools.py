"""UI 渲染工具集 — 通过 @tool 生成前端可渲染的交互式组件（图表、表格、表单、卡片）"""

from __future__ import annotations

import uuid
from typing import Literal

from langchain_core.tools import tool


@tool
def render_chart(
    title: str,
    chart_type: Literal["line", "bar", "pie", "gauge", "heatmap"],
    labels: list[str],
    datasets: list[dict],
    actions: list[dict] | None = None,
    description: str | None = None,
) -> dict:
    """渲染交互式图表到聊天界面。展示系统指标趋势、对比数据、占比分布。

    Args:
        title: 图表标题。
        chart_type: 图表类型 — line(折线图)、bar(柱状图)、pie(饼图)、gauge(仪表盘)、heatmap(热力图)。
        labels: X 轴标签或分类名称列表。
        datasets: 数据集列表，每项含 label(str)、data(list[float])，可选 color(str)、unit(str)。
        actions: 可交互操作列表，每项含 id、label、action_type 等。
        description: 图表补充说明。

    Returns:
        带有 _ui 标记的组件字典，前端识别后渲染为交互式图表。
    """
    return {
        "_ui": True,
        "id": f"chart_{uuid.uuid4().hex[:8]}",
        "type": "chart",
        "version": "1.0",
        "title": title,
        "chartType": chart_type,
        "data": {"labels": labels, "datasets": datasets},
        "actions": actions or [],
        "description": description,
    }


@tool
def render_table(
    title: str,
    columns: list[dict],
    rows: list[dict],
    sortable: bool = True,
    filterable: bool = True,
    searchable: bool = True,
    page_size: int = 10,
    actions: list[dict] | None = None,
    description: str | None = None,
) -> dict:
    """渲染交互式数据表格。展示进程列表、容器、用户等结构化数据。

    Args:
        title: 表格标题。
        columns: 列定义列表，每项含 key(str)、label(str)，可选 type(str)、align(str)。
        rows: 数据行列表，每行为 key-value 字典。
        sortable: 是否允许列排序。
        filterable: 是否允许列筛选。
        searchable: 是否允许全文搜索。
        page_size: 每页行数。
        actions: 行操作按钮列表。
        description: 表格补充说明。

    Returns:
        带有 _ui 标记的组件字典，前端识别后渲染为交互式表格。
    """
    return {
        "_ui": True,
        "id": f"table_{uuid.uuid4().hex[:8]}",
        "type": "table",
        "version": "1.0",
        "title": title,
        "schema": columns,
        "data": rows,
        "features": {
            "sortable": sortable,
            "filterable": filterable,
            "searchable": searchable,
            "paginated": True,
            "pageSize": page_size,
        },
        "actions": actions or [],
        "description": description,
    }


@tool
def render_form(
    title: str,
    fields: list[dict],
    initial_values: dict | None = None,
    actions: list[dict] | None = None,
    description: str | None = None,
) -> dict:
    """渲染配置表单。收集用户输入用于创建/编辑资源。

    Args:
        title: 表单标题。
        fields: 字段定义列表，每项含 name(str)、type(str)、label(str)，可选 options、default、required 等。
        initial_values: 字段初始值字典。
        actions: 操作按钮列表，默认包含提交按钮。
        description: 表单补充说明。

    Returns:
        带有 _ui 标记的组件字典，前端识别后渲染为交互式表单。
    """
    return {
        "_ui": True,
        "id": f"form_{uuid.uuid4().hex[:8]}",
        "type": "form",
        "version": "1.0",
        "title": title,
        "fields": fields,
        "initialValues": initial_values or {},
        "actions": actions or [{"id": "submit", "label": "提交", "action_type": "agent", "variant": "primary"}],
        "description": description,
    }


@tool
def render_card(
    title: str,
    status: Literal["healthy", "warning", "error", "unknown"],
    metrics: list[dict],
    details: str | None = None,
    actions: list[dict] | None = None,
) -> dict:
    """渲染状态卡片。展示服务/服务器健康状态和关键指标。

    Args:
        title: 卡片标题。
        status: 健康状态 — healthy/warning/error/unknown。
        metrics: 指标列表，每项含 label(str)、value(str|int|float)，可选 unit(str)、trend(str)。
        details: 详细说明文本。
        actions: 操作按钮列表。

    Returns:
        带有 _ui 标记的组件字典，前端识别后渲染为状态卡片。
    """
    return {
        "_ui": True,
        "id": f"card_{uuid.uuid4().hex[:8]}",
        "type": "card",
        "version": "1.0",
        "title": title,
        "status": status,
        "metrics": metrics,
        "details": details,
        "actions": actions or [],
    }
