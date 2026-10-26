#!/usr/bin/env bash
# 仅在GitHub Ubuntu临时运行器运行；真实安装/卸载本机测试副本，不连接媒体服务。
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true && "$EUID" == 0 ]] || { printf '%s\n' '仅供GitHub临时Ubuntu运行器测试'; exit 1; }
HOST_NODE="$1"
SOURCE="$(cd -- "$2" && pwd)"
HOST_NPM="$(dirname -- "$(dirname -- "$(readlink -f -- "$(dirname -- "$HOST_NODE")/npm")")")"
[[ ! -e /home/tv-season-linux && ! -e /home/tvflow-node && ! -e /usr/local/bin/tvflow && ! -e /root/.local/share/tvflow ]] || { printf '%s\n' '测试目标不为空，停止'; exit 1; }
source "$SOURCE/manage.sh"
trap 'cleanup_stage' EXIT
fetch_source() { mkdir -p "$TVFLOW_STAGE/app"; tar --exclude=node_modules --exclude=.test-tmp -cf - -C "$SOURCE" . | tar -xf - -C "$TVFLOW_STAGE/app"; }
install_node() {
 local dest="$1"
 mkdir -p "$dest/bin" "$dest/lib/node_modules"
 cp -- "$HOST_NODE" "$dest/bin/node"
 ln -s -- "$HOST_NPM" "$dest/lib/node_modules/npm"
 ln -s ../lib/node_modules/npm/bin/npm-cli.js "$dest/bin/npm"
 node_ok "$dest/bin/node"
}
install_app
/usr/local/bin/tvflow status
[[ -f /home/tv-season-linux/.tvflow-install.json && -f /etc/systemd/system/tvflow.service ]]
"$HOST_NODE" "$SOURCE/scripts/uninstall.js" --yes
[[ ! -e /home/tv-season-linux && ! -e /usr/local/bin/tvflow && ! -e /etc/systemd/system/tvflow.service && ! -e /root/.local/share/tvflow ]]
[[ -x /home/tvflow-node/bin/node ]]
/home/tvflow-node/bin/node --version
printf '%s\n' 'Ubuntu管理器：安装、独立Node命令、后台启动、卸载程序与保留Node检查通过。'
