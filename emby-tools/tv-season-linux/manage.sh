#!/usr/bin/env bash
# root管理入口：程序与Node分目录保存，卸载程序时保留Node。
set -euo pipefail
TVFLOW_APP='/home/tv-season-linux'
TVFLOW_NODE_DIR='/home/tvflow-node'
TVFLOW_REPO='https://github.com/hailanbb/skill-selection.git'
TVFLOW_RAW='https://raw.githubusercontent.com/hailanbb/skill-selection/master/emby-tools/tv-season-linux'
TVFLOW_STAGE=''
cleanup_stage() {
  if [[ -n "$TVFLOW_STAGE" && -d "$TVFLOW_STAGE" ]]; then
    local actual
    actual="$(readlink -f -- "$TVFLOW_STAGE")"
    if [[ "$actual" == /home/.tvflow-install.* || "$actual" == /tmp/tvflow-manager.* ]]; then rm -rf -- "$actual"; fi
  fi
}
fetch() { curl --fail --silent --show-error --location --retry 2 --connect-timeout 20 --max-time 600 "$1" --output "$2"; }
node_ok() { "$1" -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>22||(a===22&&b>=13)?0:1)' >/dev/null 2>&1; }
install_node() {
  local dest="$1" arch archive digest extra
  case "$(uname -m)" in x86_64) arch='x64';; aarch64|arm64) arch='arm64';; *) printf '%s\n' '暂只支持Ubuntu x86_64/arm64。' >&2; return 1;; esac
  fetch 'https://nodejs.org/download/release/latest-v22.x/SHASUMS256.txt' "$TVFLOW_STAGE/SHASUMS256.txt" || return 1
  local line
  line="$(awk -v ending="-linux-$arch.tar.xz" '$2 ~ /^node-v22\.[0-9]+\.[0-9]+-linux-/ && substr($2,length($2)-length(ending)+1)==ending {print $0}' "$TVFLOW_STAGE/SHASUMS256.txt")"
  [[ "$line" != *$'\n'* ]] || { printf '%s\n' 'Node官方摘要出现重复候选，停止安装。' >&2; return 1; }
  read -r digest archive extra <<< "$line"
  [[ "$digest" =~ ^[a-f0-9]{64}$ && "$archive" =~ ^node-v22\.[0-9]+\.[0-9]+-linux-(x64|arm64)\.tar\.xz$ && -z "${extra:-}" ]] || { printf '%s\n' 'Node官方摘要格式异常，停止安装。' >&2; return 1; }
  printf '%s\n' "安装专用Node：$archive"
  fetch "https://nodejs.org/download/release/latest-v22.x/$archive" "$TVFLOW_STAGE/$archive" || return 1
  (cd -- "$TVFLOW_STAGE"; printf '%s  %s\n' "$digest" "$archive" | sha256sum --check --status) || { printf '%s\n' 'Node下载摘要不一致，停止安装。' >&2; return 1; }
  mkdir -p -- "$dest"
  tar -xJf "$TVFLOW_STAGE/$archive" --strip-components=1 -C "$dest" || return 1
  node_ok "$dest/bin/node" || { printf '%s\n' 'Node版本校验失败，需要22.13或更新。' >&2; return 1; }
}
fetch_source() {
  git clone --depth 1 --filter=blob:none --sparse "$TVFLOW_REPO" "$TVFLOW_STAGE/repo" || return 1
  git -C "$TVFLOW_STAGE/repo" sparse-checkout set emby-tools/tv-season-linux || return 1
  cp -a -- "$TVFLOW_STAGE/repo/emby-tools/tv-season-linux" "$TVFLOW_STAGE/app" || return 1
}
install_app() {
  if [[ -e "$TVFLOW_APP" || -L "$TVFLOW_APP" || -e /usr/local/bin/tvflow || -L /usr/local/bin/tvflow || -e /etc/systemd/system/tvflow.service ]]; then
    printf '%s\n' '检测到已有程序、命令或服务；请先选择2卸载旧版，再选择1安装。不会覆盖已有文件。' >&2; return 1
  fi
  local missing=0 tool
  for tool in git curl tar xz sha256sum; do command -v "$tool" >/dev/null || missing=1; done
  if ((missing)); then apt-get update; apt-get install -y ca-certificates curl git tar xz-utils coreutils; fi
  TVFLOW_STAGE="$(mktemp -d /home/.tvflow-install.XXXXXXXX)"
  fetch_source
  if [[ -e "$TVFLOW_NODE_DIR" || -L "$TVFLOW_NODE_DIR" ]]; then
    [[ ! -L "$TVFLOW_NODE_DIR" && -x "$TVFLOW_NODE_DIR/bin/node" ]] && node_ok "$TVFLOW_NODE_DIR/bin/node" || { printf '%s\n' '已有Node目录不符合要求，未覆盖。' >&2; return 1; }
    printf '%s\n' "复用已安装Node：$TVFLOW_NODE_DIR"
  else
    install_node "$TVFLOW_STAGE/node"
    mv -T -- "$TVFLOW_STAGE/node" "$TVFLOW_NODE_DIR"
  fi
  export PATH="$TVFLOW_NODE_DIR/bin:$PATH"
  (cd -- "$TVFLOW_STAGE/app"; npm ci --ignore-scripts --no-audit --no-fund && npm run build)
  # 源码准备完成后才占用正式目录；先再次确认目的地不存在。
  [[ ! -e "$TVFLOW_APP" && ! -L "$TVFLOW_APP" ]] || { printf '%s\n' '安装目标已出现，停止。' >&2; return 1; }
  mv -T -- "$TVFLOW_STAGE/app" "$TVFLOW_APP"
  TVFLOW_NODE="$TVFLOW_NODE_DIR/bin/node" "$TVFLOW_NODE_DIR/bin/node" "$TVFLOW_APP/scripts/install-user.js"
  "$TVFLOW_NODE_DIR/bin/node" --input-type=module - "$TVFLOW_APP" "$TVFLOW_NODE_DIR/bin/node" <<'NODE'
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const app=process.argv[2],{defaults,writeConfig}=await import(pathToFileURL(path.join(app,'lib/config.js')));
const data=process.env.TVFLOW_HOME||path.join(process.env.HOME,'.local/share/tvflow');
if(!fs.existsSync(path.join(data,'config.json')))writeConfig(defaults());
fs.writeFileSync(path.join(app,'.tvflow-install.json'),JSON.stringify({schema:1,appDir:app,dataDir:data,nodePath:process.argv[3],preserveNode:true,installedAt:new Date().toISOString()},null,2)+'\n',{mode:0o600});
NODE
  if [[ -d /run/systemd/system ]] && command -v systemctl >/dev/null; then
    systemctl daemon-reload
    systemctl enable --now tvflow.service
    printf '%s\n' '已启用本程序后台服务与开机启动。'
  else printf '%s\n' '当前环境没有运行systemd；输入tvflow时会自动启动后台。'; fi
  printf '\n%s\n' '安装完成。输入 tvflow 打开菜单；配置文件：~/.local/share/tvflow/config.json。' "程序：$TVFLOW_APP" "Node：$TVFLOW_NODE_DIR（卸载程序时保留）"
}
uninstall_app() {
  TVFLOW_STAGE="$(mktemp -d /tmp/tvflow-manager.XXXXXXXX)"
  fetch "$TVFLOW_RAW/scripts/uninstall.js" "$TVFLOW_STAGE/uninstall.mjs"
  local nodebin=''
  if [[ -x "$TVFLOW_NODE_DIR/bin/node" ]] && node_ok "$TVFLOW_NODE_DIR/bin/node"; then nodebin="$TVFLOW_NODE_DIR/bin/node"
  elif command -v node >/dev/null && node_ok "$(command -v node)"; then nodebin="$(command -v node)"
  else
    command -v xz >/dev/null || { apt-get update; apt-get install -y xz-utils; }
    install_node "$TVFLOW_STAGE/node"; nodebin="$TVFLOW_STAGE/node/bin/node"
  fi
  "$nodebin" "$TVFLOW_STAGE/uninstall.mjs" --dry-run
  local answer
  read -r -p '以上程序、配置、任务历史、本机报告与日志将被清除。输入 卸载 确认：' answer </dev/tty
  [[ "$answer" == '卸载' ]] || { printf '%s\n' '已取消。'; return 0; }
  "$nodebin" "$TVFLOW_STAGE/uninstall.mjs" --yes
}
main() {
  [[ "$OSTYPE" == linux* && "$EUID" == 0 ]] || { printf '%s\n' '请在Ubuntu服务器的root终端执行本管理入口。' >&2; return 1; }
  trap cleanup_stage EXIT
  printf '%s\n' '剧集整理Linux版 · 安装与卸载' '1 一键安装（包含Node.js和程式）' '2 一键卸载（清除清理已安装的程式）' '安装位置：/home/tv-season-linux/' '卸载清除本机程序及其数据；保留Node，不删除云盘媒体。'
  local choice
  read -r -p '请选择 1 / 2：' choice </dev/tty
  case "$choice" in 1) install_app;; 2) uninstall_app;; *) printf '%s\n' '已退出。';; esac
}
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
