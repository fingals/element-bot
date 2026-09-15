FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir poetry && poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi

COPY . .

ENV PYTHONPATH=/app

EXPOSE 8091
CMD ["python", "-u", "-m", "elementbot.main"]
