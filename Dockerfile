FROM python:3.12-slim

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libgomp1 imagemagick \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Install Python dependencies before copying the full source to
# maximise layer cache reuse on source-only changes.
COPY requirements.txt .
RUN uv pip install -r requirements.txt --system

# Copy source and install the package
COPY . .
RUN uv pip install . --system

# Replace Streamlit's bundled favicon with the ICOS one
RUN convert web/favicon.ico -thumbnail 32x32 /usr/local/lib/python3.12/site-packages/streamlit/static/favicon.png

# Run as non-root
RUN useradd --create-home --shell /bin/false appuser \
    && chown -R appuser /app
USER appuser

EXPOSE 5000

CMD ["sh", "-c", "cd web && streamlit run streamlit_app.py --server.port ${PORT:-5000} --server.address 0.0.0.0"]
