#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$OSTYPE" != linux* ]]; then printf '%s\n' '安装脚本用于Linux；开发测试可直接用Node运行。' >&2; exit 1; fi
# root使用系统级服务，普通用户使用用户级服务；不在安装时自动启动后台。
if [[ "${EUID}" == 0 ]]; then printf '%s\n' '以root安装：将创建root账户的命令和系统级服务。'; fi
command -v node >/dev/null || { printf '%s\n' '请先安装Node.js 22.13或更新版本。' >&2; exit 1; }
command -v npm >/dev/null || { printf '%s\n' '未找到npm，请安装与Node.js配套的npm。' >&2; exit 1; }
node -e 'const [a,b]=process.versions.node.split(".").map(Number);if(a<22||(a===22&&b<13))process.exit(1)' || { printf '%s\n' 'Node.js版本过低，需要22.13或更新。'; exit 1; }
cd -- "$APP_DIR"
npm ci --ignore-scripts --no-audit --no-fund
npm run build
node scripts/install-user.js
printf '\n%s\n' '安装完成。后台启用方法参见上方提示和INSTALL.md；不要移动已安装的源码目录。'
