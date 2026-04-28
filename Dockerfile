# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Enable bytecode compilation for faster startup.
ENV UV_COMPILE_BYTECODE=1
# Prevent uv from trying to use its own managed Python.
ENV UV_SYSTEM_PYTHON=1

# Copy only dependency manifests first — this layer is cached
# unless pyproject.toml or uv.lock changes.
COPY pyproject.toml uv.lock ./

# Install dependencies only (not the package itself).
# This layer is cached when the lockfile hasn't changed.
RUN uv pip install --system -r pyproject.toml

# Copy application code — this layer rebuilds on code changes.
COPY src ./src
COPY web ./web
COPY transcripts ./transcripts
COPY fdcpa_rubric.json ./fdcpa_rubric.json
COPY web_app.py ./web_app.py

# Install the package itself in editable mode (deps already installed).
RUN uv pip install --system --no-deps -e .

# Hugging Face Spaces expects the app to listen on 7860
ENV PORT=7860
EXPOSE 7860

CMD ["uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "7860"]
