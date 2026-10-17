# D14-R2：演示级镜像（ADR-0018）。容器内不跑 pytest；runserver 为演示取舍（gunicorn/静态/HTTPS → v2）。
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# git：sync_git_repo / make_demo_repo 需要
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# bind mount 属主与容器不一致 → 显式信任所有目录（已知坑，ADR-0018 记录）
RUN git config --global --add safe.directory '*'

WORKDIR /app

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/base.txt

COPY . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]