FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_DEBUG=false
WORKDIR /app

FROM base AS dependencies
RUN pip install --no-cache-dir uv==0.13.6
COPY pyproject.toml uv.lock .python-version ./
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
RUN uv sync --locked --no-dev

FROM dependencies AS development
RUN uv sync --locked
ENV PATH="/app/.venv/bin:$PATH"
COPY . .
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM base AS production
ENV PATH="/app/.venv/bin:$PATH"
COPY --from=dependencies /app/.venv /app/.venv
RUN useradd --system --uid 10001 --create-home appuser
COPY . .
RUN DJANGO_DEBUG=true DJANGO_SECRET_KEY=build-only-static-assets python manage.py collectstatic --noinput
USER 10001:10001
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "--error-logfile", "-"]
