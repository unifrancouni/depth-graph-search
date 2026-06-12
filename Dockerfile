# Stage 1: builder — install all dependencies including the [api] optional extra
FROM python:3.11-slim AS builder

WORKDIR /app

# Copy only what's needed to resolve dependencies first (layer cache optimisation)
COPY pyproject.toml .
COPY src/ src/

# Install package + api extra into the system site-packages
RUN pip install --no-cache-dir ".[api]"


# Stage 2: final runtime image — copy only installed artifacts, not build tools
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy uvicorn binary
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Copy application source
COPY src/ src/

# Non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "depth_graph_search.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
