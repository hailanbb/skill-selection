#!/usr/bin/env bash
set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

echo "=========================================================="
echo "     正在部署 Telegram -> 多 115 定向云下载管理系统     "
echo "=========================================================="

# 1. 检查基础依赖
if ! command -v python3 >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
    echo "[*] 安装基础系统依赖 (python3, python3-venv, curl)..."
    if [ "$(id -u)" -eq 0 ]; then
        apt update && apt install -y python3 python3-pip python3-venv curl
    else
        sudo apt update && sudo apt install -y python3 python3-pip python3-venv curl
    fi
fi

if ! dpkg -s python3-venv >/dev/null 2>&1; then
    echo "[*] 安装 python3-venv..."
    if [ "$(id -u)" -eq 0 ]; then
        apt update && apt install -y python3-venv
    else
        sudo apt update && sudo apt install -y python3-venv
    fi
fi

# 2. 创建虚拟环境
if [ ! -d "$APP_DIR/venv" ]; then
    echo "[*] 创建 Python 虚拟环境 (venv)..."
    python3 -m venv "$APP_DIR/venv"
fi
source "$APP_DIR/venv/bin/activate"

# 3. 安装 Python 依赖（优先使用清华高速镜像，失败自动回退官方源）
echo "[*] 安装核心依赖 (telethon, grpcio, grpcio-tools, torrentool)..."
pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    telethon grpcio grpcio-tools torrentool || \
pip install --no-cache-dir \
    telethon grpcio grpcio-tools torrentool

# 4. 下载并编译 CloudDrive2 官方 gRPC 协议
echo "[*] 下载 CloudDrive2 官方 gRPC 协议定义 (clouddrive.proto)..."
curl -sSL https://www.clouddrive2.com/api/clouddrive.proto -o clouddrive.proto

echo "[*] 编译 Python gRPC 模块..."
python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. clouddrive.proto

# 5. 创建运行目录与初始化配置
mkdir -p data records logs
if [ ! -f "$APP_DIR/config.json" ] && [ -f "$APP_DIR/config.example.json" ]; then
    cp "$APP_DIR/config.example.json" "$APP_DIR/config.json"
    echo "[*] 已从模板生成 config.json，请通过菜单 [4 配置] 或手动编辑填入凭据。"
fi

# 6. 设置可执行权限并注册全局快捷命令 tg115
chmod +x "$APP_DIR/install.sh" "$APP_DIR/tg115.sh" "$APP_DIR/cli.py" "$APP_DIR/monitor.py" "$APP_DIR/cd2_ops.py"

if [ "$(id -u)" -eq 0 ]; then
    ln -sf "$APP_DIR/tg115.sh" /usr/local/bin/tg115
else
    sudo ln -sf "$APP_DIR/tg115.sh" /usr/local/bin/tg115
fi

echo "=========================================================="
echo "                      部署完成！                          "
echo "=========================================================="
echo "现在可以在 Ubuntu 终端的任意目录直接输入以下命令打开管理菜单："
echo ""
echo "    tg115"
echo ""
echo "（或在当前目录运行 ./tg115.sh）"
echo "=========================================================="
