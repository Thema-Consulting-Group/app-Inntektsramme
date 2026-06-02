# =============================================================================
#  Inntektsramme – Docker image
#  Base: rocker/r-ver gives us R 4.5 on Ubuntu LTS + Rscript on PATH
# =============================================================================
FROM rocker/r-ver:4.5.2

# ---------------------------------------------------------------------------
# 1. System libraries needed by R packages and Python
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    libcurl4-openssl-dev \
    libssl-dev \
    libxml2-dev \
    libfontconfig1-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    libfreetype6-dev \
    libpng-dev \
    libtiff5-dev \
    libjpeg-dev \
    libuv1-dev \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# Make python3 / pip3 available as python / pip
RUN ln -sf /usr/bin/python3 /usr/bin/python \
 && ln -sf /usr/bin/pip3 /usr/bin/pip

# ---------------------------------------------------------------------------
# 2. R packages
#    Install in one RUN layer so Docker can cache it effectively.
# ---------------------------------------------------------------------------
RUN Rscript -e "\
  options(\
    repos = c(CRAN = 'https://packagemanager.posit.co/cran/__linux__/noble/latest'),\
    HTTPUserAgent = sprintf('R/%s R (%s)', getRversion(), paste(getRversion(), R.version[['platform']], R.version[['arch']], R.version[['os']]))\
  ); \
  pkgs <- c('tidyverse', 'Benchmarking', 'dplyr', 'openxlsx', \
            'writexl', 'readxl', 'plyr', 'pxweb', 'XML', \
            'RCurl', 'zoo', 'DBI', 'reshape2'); \
  install.packages(pkgs, dependencies = TRUE); \
  cat('R packages installed OK\n')"

# ---------------------------------------------------------------------------
# 3. Python packages  (lean list — see requirements-docker.txt)
# ---------------------------------------------------------------------------
WORKDIR /app
COPY requirements-docker.txt ./
RUN pip install --no-cache-dir --break-system-packages -r requirements-docker.txt

# ---------------------------------------------------------------------------
# 4. Copy repo content
# ---------------------------------------------------------------------------
COPY . .

# Ensure runtime-writable directories exist (Bootstrap excluded from image)
RUN mkdir -p /app/Data/Bootstrap /app/Results

# ---------------------------------------------------------------------------
# 5. Runtime configuration
# ---------------------------------------------------------------------------
EXPOSE 8000

# Optional password protection — set these in Railway / Render / docker run -e
# Leave blank to disable auth.
ENV APP_USER="" \
    APP_PASS=""

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
