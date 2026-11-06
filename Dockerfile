# ==============================================================================
# Web Data Forge - Production Hardened Containerfile
# Python 3.12-slim, Non-Root execution, Healthchecked
# ==============================================================================

FROM python:3.12-slim AS runtime

# 1. Install minimal system utilities required for health checks
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# 2. Security: Create dedicated unprivileged user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# 3. Set standard working directory
WORKDIR /app

# 4. Environment Variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true

# 5. Layer Caching: Install dependencies first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy application source, fixtures, and documentation
COPY src/ ./src/
COPY tests/fixtures/ ./tests/fixtures/
COPY pyproject.toml README.md LICENSE ./

# 7. Create persistent data volume directory and ensure non-root ownership
RUN mkdir -p /app/data && \
    chown -R appuser:appgroup /app

# 8. Switch to non-root user
USER appuser

# 9. Expose Streamlit default port
EXPOSE 8501

# 10. Container Health Check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# 11. Run Streamlit Studio Application
CMD ["streamlit", "run", "src/web_data_forge/ui/app.py"]
