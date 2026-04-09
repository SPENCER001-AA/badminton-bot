import os
from datetime import datetime
from flask import Flask, request, render_template_string
from config import CONFIG
from scheduler import create_task, load_tasks
from query import query_open_times

app = Flask(__name__)


HTML = """
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <title>羽毛球抢位系统</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {
      font-family: Arial, sans-serif;
      max-width: 980px;
      margin: 20px auto;
      padding: 0 16px;
      line-height: 1.5;
    }
    h1, h2 {
      margin-bottom: 12px;
    }
    form {
      border: 1px solid #ddd;
      border-radius: 10px;
      padding: 16px;
      margin-bottom: 24px;
    }
    label {
      display: block;
      margin-top: 12px;
      font-weight: bold;
    }
    input, select, button {
      width: 100%;
      padding: 10px;
      margin-top: 6px;
      box-sizing: border-box;
      font-size: 16px;
    }
    button {
      margin-top: 16px;
      cursor: pointer;
    }
    .msg {
      padding: 10px 12px;
      border-radius: 8px;
      margin-bottom: 16px;
    }
    .ok {
      background: #eef9ee;
      border: 1px solid #b7e0b7;
    }
    .err {
      background: #fff3f3;
      border: 1px solid #f0b5b5;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 12px;
      font-size: 14px;
    }
    th, td {
      border: 1px solid #ddd;
      padding: 8px;
      text-align: left;
      vertical-align: top;
    }
    th {
      background: #f7f7f7;
    }
    .small {
      color: #666;
      font-size: 13px;
    }
    .card {
      border: 1px solid #ddd;
      border-radius: 10px;
      padding: 16px;
      margin-bottom: 24px;
    }
  </style>
</head>
<body>
  <h1>羽毛球抢位系统</h1>

  {% if message %}
    <div class="msg {{ 'ok' if success else 'err' }}">{{ message }}</div>
  {% endif %}

  <form method="post" action="{{ url_for('query_times_view') }}">
    <h2>第一步：查询开放时间</h2>

    <label>社区</label>
    <select name="center_index">
      {% for i, center in centers %}
        <option value="{{ i }}" {% if i == selected_center_index %}selected{% endif %}>
          {{ center["short"] }}
        </option>
      {% endfor %}
    </select>

    <label>目标日期</label>
    <input type="text" name="target_date_text" value="{{ selected_date }}">

    <button type="submit">查询开放时间</button>
  </form>

  {% if queried_times is not none %}
    <div class="card">
      <h2>第二步：保存任务</h2>

      {% if queried_times %}
        <form method="post" action="{{ url_for('create_task_view') }}">
          <input type="hidden" name="center_index" value="{{ selected_center_index }}">
          <input type="hidden" name="target_date_text" value="{{ selected_date }}">

          <label>选择场次</label>
          <select name="target_time">
            {% for t in queried_times %}
              <option value="{{ t }}">{{ t }}</option>
            {% endfor %}
          </select>

          <label>参与人</label>
          <select name="participant_name">
            {% for p in participants %}
              <option value="{{ p }}" {% if p == default_participant %}selected{% endif %}>
                {{ p }}
              </option>
            {% endfor %}
          </select>

          <button type="submit">保存任务</button>
        </form>
      {% else %}
        <p>没有查询到时间</p>
      {% endif %}
    </div>
  {% endif %}

  <h2>任务列表</h2>

  {% for task in tasks %}
    <div class="card">
      <b>{{ task["center_name"] }}</b><br>
      {{ task["target_date_text"] }}<br>
      {{ task["target_time"] }}<br>
      {{ task["participant_name"] }}<br>
      状态：{{ task["status"] }}
    </div>
  {% endfor %}
</body>
</html>
"""


def render_home(message="", success=True, queried_times=None, selected_center_index=None, selected_date=None):
    tasks = load_tasks()

    return render_template_string(
        HTML,
        message=message,
        success=success,
        tasks=tasks,
        centers=list(enumerate(CONFIG["centers"])),
        participants=CONFIG["participants"],
        default_participant=CONFIG["default_participant"],
        selected_center_index=selected_center_index or CONFIG["default_center_index"],
        selected_date=selected_date or CONFIG["target_date_text"],
        queried_times=queried_times,
    )


@app.route("/")
def home():
    return render_home()


@app.route("/query-times", methods=["POST"])
def query_times_view():
    center_index = int(request.form["center_index"])
    target_date_text = request.form["target_date_text"]

    results = query_open_times(
        center_index=center_index,
        target_date_text=target_date_text,
        verbose=False
    )

    times = list({r["time"] for r in results if r.get("time")})

    return render_home(
        message="查询完成",
        success=True,
        queried_times=times,
        selected_center_index=center_index,
        selected_date=target_date_text,
    )


@app.route("/create-task", methods=["POST"])
def create_task_view():
    task = create_task(
        center_index=int(request.form["center_index"]),
        target_date_text=request.form["target_date_text"],
        target_time=request.form["target_time"],
        participant_name=request.form["participant_name"],
    )

    return render_home("任务创建成功" if task else "重复任务", success=bool(task))


# 👇 关键：支持云端端口
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False)