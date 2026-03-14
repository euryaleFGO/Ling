@echo off
chcp 65001 >nul
cd /d E:\Avalon\Chaldea\Liying
echo ============================================================
echo 修复 YAML 兼容性问题
echo ============================================================
echo.
echo 正在激活 conda 环境: Liying
call conda activate F:\envs\Liying
echo.
echo 问题: HyperPyYAML 需要 ruamel.yaml 0.18.14，但当前是 0.18.6
echo.
echo 正在升级 ruamel.yaml 到 0.18.14...
pip install --upgrade ruamel.yaml==0.18.14
echo.
echo 正在安装 ruamel.yaml.clib...
pip install ruamel.yaml.clib==0.2.12
echo.
echo 正在安装 HyperPyYAML...
pip install HyperPyYAML==1.2.2
echo.
echo ============================================================
echo 修复完成！
echo ============================================================
echo.
echo 现在可以重新运行: python test_tts.py
echo.
pause

