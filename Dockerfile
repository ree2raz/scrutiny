# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Copy everything needed for installation and runtime
COPY pyproject.toml ./
COPY src ./src
COPY web ./web
COPY transcripts ./transcripts
COPY fdcpa_rubric.json ./fdcpa_rubric.json
COPY web_app.py ./web_app.py

# Install the package
RUN pip install --no-cache-dir -e "."

# Hugging Face Spaces expects the app to listen on 7860
ENV PORT=7860
EXPOSE 7860

CMD ["uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "7860"]
