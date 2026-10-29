@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 复用上层 MySQL\bi 里已下载的 Metabase，避免重复下载 ~400MB
set "JAR=%~dp0..\..\bi\metabase.jar"
if not exist "%JAR%" set "JAR=%~dp0metabase.jar"
if not exist "%JAR%" (
  echo [!] 没找到 metabase.jar
  echo     请把 metabase.jar 放到 %~dp0 或 ..\..\bi\ 下
  pause
  exit /b 1
)

rem 豆瓣项目独立的应用库与端口，和 film-analytics（3000）互不干扰
if not exist "%~dp0data" mkdir "%~dp0data"
set "MB_DB_FILE=%~dp0data\metabase.db"
set "MB_JETTY_PORT=3001"

rem 优先用 JDK 17；没有就退回 PATH 里的 java
set "JAVA=C:\Program Files\Java\jdk-17\bin\java.exe"
if not exist "%JAVA%" set "JAVA=java"

rem 已经在跑就只打开浏览器
netstat -ano | findstr /r /c:":3001 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo Metabase 已在 3001 端口运行，直接打开浏览器。
  start "" "http://127.0.0.1:3001"
  exit /b 0
)

echo ============================================
echo  Metabase 启动中（首次约 30 秒）
echo  地址：http://127.0.0.1:3001
echo  看板：豆瓣电影数据看板
echo  账号见 .env 中的 METABASE_ADMIN_EMAIL
echo  按 Ctrl+C 停止
echo ============================================
echo.

start "" "http://127.0.0.1:3001"
"%JAVA%" -jar "%JAR%"

pause
