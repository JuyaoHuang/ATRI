@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "REPO_URL=https://github.com/JuyaoHuang/atri.git"
set "TARGET_DIR=atri"
set "PYPI_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
set "NPM_REGISTRY=https://registry.npmmirror.com"
set "SKIP_CLONE=0"

if not "%REPO_URL_OVERRIDE%"=="" set "REPO_URL=%REPO_URL_OVERRIDE%"
if not "%TARGET_DIR_OVERRIDE%"=="" set "TARGET_DIR=%TARGET_DIR_OVERRIDE%"
if not "%PYPI_INDEX_OVERRIDE%"=="" set "PYPI_INDEX=%PYPI_INDEX_OVERRIDE%"
if not "%NPM_REGISTRY_OVERRIDE%"=="" set "NPM_REGISTRY=%NPM_REGISTRY_OVERRIDE%"

:parse_args
if "%~1"=="" goto after_parse
if /I "%~1"=="--repo-url" (
  set "REPO_URL=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--target-dir" (
  set "TARGET_DIR=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--pypi-index" (
  set "PYPI_INDEX=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--npm-registry" (
  set "NPM_REGISTRY=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--skip-clone" (
  set "SKIP_CLONE=1"
  shift
  goto parse_args
)
if /I "%~1"=="-h" goto help
if /I "%~1"=="--help" goto help
echo Unknown option: %~1
goto help_error

:after_parse
call :need_cmd git || exit /b 1
call :need_cmd uv || exit /b 1
call :need_cmd npm || exit /b 1

if exist "pyproject.toml" if exist "config.yaml" if exist ".gitmodules" (
  set "REPO_DIR=%CD%"
  goto repo_ready
)

if "%SKIP_CLONE%"=="1" (
  echo --skip-clone was set, but current directory is not an atri repository.
  exit /b 1
)

if exist "%TARGET_DIR%\.git" (
  pushd "%TARGET_DIR%" || exit /b 1
  set "REPO_DIR=!CD!"
  popd
  goto repo_ready
)

echo Cloning atri from: %REPO_URL%
git clone --recurse-submodules "%REPO_URL%" "%TARGET_DIR%"
if errorlevel 1 exit /b 1

pushd "%TARGET_DIR%" || exit /b 1
set "REPO_DIR=%CD%"
popd

:repo_ready
pushd "%REPO_DIR%" || exit /b 1

echo Repository: %CD%
echo Syncing submodules...
git submodule sync --recursive
if errorlevel 1 exit /b 1
git submodule update --init --recursive
if errorlevel 1 exit /b 1

if not exist ".env" if exist ".env.example" (
  echo Creating .env from .env.example
  copy ".env.example" ".env" >nul
)

echo Installing backend dependencies with uv
echo PyPI index: %PYPI_INDEX%
set "UV_DEFAULT_INDEX=%PYPI_INDEX%"
uv sync
if errorlevel 1 exit /b 1

if not exist "frontend\package.json" (
  echo frontend\package.json was not found. Check submodule status.
  exit /b 1
)

echo Installing frontend dependencies with npm
echo npm registry: %NPM_REGISTRY%
pushd "frontend" || exit /b 1
npm install --registry "%NPM_REGISTRY%"
if errorlevel 1 exit /b 1
popd

echo.
echo Install finished.
echo.
echo Next steps:
echo   1. Edit .env and fill OPENAI_API_KEY / COMPRESS_API_KEY.
echo   2. Start backend:
echo        uv run python -m src.main
echo   3. Start frontend in another terminal:
echo        cd frontend
echo        npm run dev
echo.
echo URLs:
echo   Frontend: http://localhost:5200
echo   Backend:  http://localhost:8430
echo   Swagger:  http://localhost:8430/docs
popd
exit /b 0

:need_cmd
where %1 >nul 2>nul
if errorlevel 1 (
  echo Missing required command: %1
  exit /b 1
)
exit /b 0

:help
echo Usage:
echo   install.bat [options]
echo.
echo Options:
echo   --repo-url URL       Git repository URL to clone when not already in atri.
echo   --target-dir DIR     Clone target directory. Default: atri
echo   --pypi-index URL     PyPI mirror for uv sync.
echo                        Default: https://pypi.tuna.tsinghua.edu.cn/simple
echo                        Aliyun alternative: https://mirrors.aliyun.com/pypi/simple/
echo   --npm-registry URL   npm registry mirror.
echo                        Default: https://registry.npmmirror.com
echo   --skip-clone         Do not clone. Require current directory to be atri.
echo   -h, --help           Show this help.
echo.
echo Environment overrides:
echo   REPO_URL_OVERRIDE, TARGET_DIR_OVERRIDE, PYPI_INDEX_OVERRIDE, NPM_REGISTRY_OVERRIDE
exit /b 0

:help_error
call :help
exit /b 2
