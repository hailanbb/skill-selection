#!/usr/bin/env bash
set -e

# 自动解析真实脚本所在目录（兼容 /usr/local/bin/tg115 软链接调用）
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
    DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
APP_DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"

cd "$APP_DIR"

if [ -x "$APP_DIR/venv/bin/python3" ]; then
    exec "$APP_DIR/venv/bin/python3" "$APP_DIR/cli.py" "$@"
else
    exec python3 "$APP_DIR/cli.py" "$@"
fi
