# =============================================================================
#  Inntektsramme – Docker image
#  Base: rocker/r-ver gives us R 4.5.2 on Ubuntu LTS
# =============================================================================
FROM rocker/r-ver:4.5.2

# ---------------------------------------------------------------------------
# 1. System libraries needed by R packages and Python
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
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
    && rm -rf /var/lib/apt/lists/*

# Make python3 / pip3 available as python / pip
RUN ln -sf /usr/bin/python3 /usr/bin/python \
 && ln -sf /usr/bin/pip3 /usr/bin/pip

# ---------------------------------------------------------------------------
# 2. R packages
#    Install in one RUN layer so Docker can cache it effectively.
# ---------------------------------------------------------------------------
RUN Rscript -e "\
  options(repos = c(CRAN = 'https://cran.rstudio.com/')); \
  pkgs <- c('tidyverse', 'Benchmarking', 'dplyr', 'openxlsx', \
            'writexl', 'readxl', 'plyr', 'pxweb', 'XML', \
            'RCurl', 'zoo', 'DBI', 'reshape2'); \
  install.packages(pkgs, dependencies = TRUE); \
  cat('R packages installed OK\n')"

# ---------------------------------------------------------------------------
# 3. Python packages
# ---------------------------------------------------------------------------
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# ---------------------------------------------------------------------------
# 4. Copy repo content
# ---------------------------------------------------------------------------
COPY . .

# ---------------------------------------------------------------------------
# 5. Expose Streamlit port and set default run command
# ---------------------------------------------------------------------------
EXPOSE 8501

# Streamlit config: disable the welcome page and CORS for container use
ENV STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_HEADLESS=true

CMD ["streamlit", "run", "app.py"]
