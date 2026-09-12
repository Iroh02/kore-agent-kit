"""Tool registry. Add a tool = write a function + one schema entry.

Each tool returns a STRING (what the model sees). Keep returns short and
factual; long dumps burn context and make the agent wander.
"""
import ast
import csv
import datetime as dt
import operator
import statistics

from . import config, rag

# ---------------------------------------------------------------- tools


def search_docs(query: str, k: int = 4) -> str:
    """Retrieve grounding passages from the indexed corpus."""
    hits = rag.search(query, k=int(k))
    if not hits:
        return "No matching passages found."
    return "\n\n".join(
        f"[{i + 1}] source={h['source']} score={h['score']}\n{h['text']}"
        for i, h in enumerate(hits)
    )


_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _ev(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp):
        return _OPS[type(node.op)](_ev(node.left), _ev(node.right))
    if isinstance(node, ast.UnaryOp):
        return _OPS[type(node.op)](_ev(node.operand))
    raise ValueError("unsupported expression")


def calculate(expression: str) -> str:
    """Arithmetic without letting the model do mental maths."""
    try:
        return str(_ev(ast.parse(expression, mode="eval").body))
    except Exception as e:  # noqa: BLE001
        return f"Could not evaluate '{expression}': {e}"


def table_query(file: str, metric: str, group_by: str = "", agg: str = "sum") -> str:
    """Aggregate a numeric column in a CSV under data/, optionally grouped."""
    path = config.DATA_DIR / file
    if not path.exists():
        available = [p.name for p in config.DATA_DIR.glob("*.csv")]
        return f"No such file '{file}'. Available CSVs: {available}"
    buckets = {}
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            try:
                value = float(str(row.get(metric, "")).replace(",", ""))
            except (TypeError, ValueError):
                continue
            buckets.setdefault(row.get(group_by, "ALL") if group_by else "ALL", []).append(value)
    if not buckets:
        return f"Column '{metric}' had no numeric values."
    fn = {"sum": sum, "mean": statistics.mean, "max": max, "min": min,
          "count": len, "median": statistics.median}.get(agg, sum)
    lines = [f"{key}: {round(fn(vals), 4)}" for key, vals in
             sorted(buckets.items(), key=lambda kv: -fn(kv[1]))]
    return f"{agg}({metric}) by {group_by or 'all rows'}:\n" + "\n".join(lines[:25])


def forecast(file: str, period: str, metric: str, periods_ahead: int = 3) -> str:
    """Least-squares trend projection over an ordered period column.

    Deliberately the dumbest model that works. If the judges ask why not
    ARIMA or Prophet: eight data points, and a straight line you can explain
    beats a black box you cannot. Swap it out when you have real history.
    """
    path = config.DATA_DIR / file
    if not path.exists():
        return f"No such file '{file}'. Available CSVs: {[p.name for p in config.DATA_DIR.glob('*.csv')]}"
    rows = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            try:
                rows.append((row[period], float(str(row[metric]).replace(",", ""))))
            except (KeyError, TypeError, ValueError):
                continue
    if len(rows) < 3:
        return f"Need at least 3 usable rows; found {len(rows)}."
    rows.sort(key=lambda r: r[0])
    ys = [v for _, v in rows]
    xs = list(range(len(ys)))
    mx, my = statistics.mean(xs), statistics.mean(ys)
    denom = sum((x - mx) ** 2 for x in xs) or 1e-9
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    intercept = my - slope * mx
    resid = statistics.pstdev([y - (slope * x + intercept) for x, y in zip(xs, ys)])
    out = [
        f"history: {rows[0][0]} to {rows[-1][0]} ({len(ys)} periods)",
        f"trend: {round(slope, 1)} {metric} per period (residual sd {round(resid, 1)})",
    ]
    for i in range(1, int(periods_ahead) + 1):
        point = slope * (len(ys) - 1 + i) + intercept
        out.append(
            f"  +{i}: {round(point, 1)}  (range {round(point - 1.96 * resid, 1)} to {round(point + 1.96 * resid, 1)})"
        )
    return "\n".join(out)


def today(_: str = "") -> str:
    """Current date. Models hallucinate dates constantly; give them this."""
    return dt.date.today().isoformat()


# ------- ADD YOUR TOOL HERE: def my_tool(arg: str) -> str: return "..."
# ...then append its schema to SCHEMAS and its name to REGISTRY below.

REGISTRY = {
    "search_docs": search_docs,
    "calculate": calculate,
    "table_query": table_query,
    "forecast": forecast,
    "today": today,
}

SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "Search the indexed knowledge base for passages relevant to a question. Always use this before answering anything factual about the provided data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "k": {"type": "integer", "description": "Number of passages, default 4"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate an arithmetic expression, e.g. '1200 * 0.05'. Use for any number you would otherwise compute in your head.",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "table_query",
            "description": "Aggregate a numeric column of a CSV file in the data folder, optionally grouped by another column.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "CSV filename, e.g. transactions.csv"},
                    "metric": {"type": "string", "description": "Numeric column to aggregate"},
                    "group_by": {"type": "string", "description": "Optional column to group by"},
                    "agg": {"type": "string", "enum": ["sum", "mean", "max", "min", "count", "median"]},
                },
                "required": ["file", "metric"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forecast",
            "description": "Project a numeric column forward using a linear trend over an ordered period column. Returns the trend, the projection and a confidence range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "CSV filename, e.g. monthly_cost.csv"},
                    "period": {"type": "string", "description": "Ordered period column, e.g. period"},
                    "metric": {"type": "string", "description": "Numeric column to project"},
                    "periods_ahead": {"type": "integer", "description": "How many periods forward, default 3"},
                },
                "required": ["file", "period", "metric"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "today",
            "description": "Get today's date in ISO format.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]
