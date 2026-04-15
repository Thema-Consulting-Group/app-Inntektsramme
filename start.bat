@echo off
echo Starter Inntektsramme-appen...

:: Check if Docker is already responding
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo Docker Desktop er ikke kjoerende. Starter det naa...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"

    echo Venter paa at Docker Desktop starter ^(kan ta 30-60 sekunder^)...
    :waitloop
    timeout /t 5 /nobreak >nul
    docker info >nul 2>&1
    if %errorlevel% neq 0 goto waitloop
    echo Docker Desktop er klar.
)

docker compose up --build
pause
