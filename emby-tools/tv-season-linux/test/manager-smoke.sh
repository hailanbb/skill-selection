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
export PATH="$(dirname -- "$HOST_NODE"):$PATH"
# 第一轮：已有合格Node，必须复用，任何下载/安装Node的尝试都使测试失败。
install_node() { printf '%s\n' '已有合格Node时不应再次安装Node' >&2; return 99; }
install_app
/usr/local/bin/tvflow status
[[ ! -e /home/tvflow-node ]]
[[ ! -e /root/.local/share/tvflow ]]
[[ -f /home/tv-season-linux/config/config.json && -f /home/tv-season-linux/data/state.sqlite ]]
[[ -L /usr/local/bin/tvflow && -L /etc/systemd/system/tvflow.service ]]
[[ "$(readlink -f /usr/local/bin/tvflow)" == /home/tv-season-linux/bin/tvflow ]]
[[ "$(readlink -f /etc/systemd/system/tvflow.service)" == /home/tv-season-linux/config/systemd/tvflow.service ]]
"$HOST_NODE" -e 'const fs=require("fs"); const x=JSON.parse(fs.readFileSync("/home/tv-season-linux/data/install.json","utf8"));if(x.nodePath!==fs.realpathSync(process.execPath))process.exit(1);const c=JSON.parse(fs.readFileSync(x.configFile,"utf8"));for(const k of ["reports","records","logs"])if(c.outputs[k]!=="/home/tv-season-linux/"+k)process.exit(2);'
"$HOST_NODE" "$SOURCE/scripts/uninstall.js" --yes
[[ ! -e /home/tv-season-linux && ! -e /usr/local/bin/tvflow && ! -e /etc/systemd/system/tvflow.service && ! -e /root/.local/share/tvflow && -x "$HOST_NODE" ]]
cleanup_stage
TVFLOW_STAGE=''
# 第二轮：模拟没有合格Node，仅替换候选来源；新Node安装后的实际检测仍使用生产函数。
fallback="$(mktemp -d /tmp/tvflow-manager.XXXXXXXX)"
printf '%s\n' '#!/usr/bin/env bash' 'exit 1' > "$fallback/node"
chmod +x "$fallback/node"
node_candidates() { if (($#)); then printf '%s\n' "$@"; else printf '%s\n' "$fallback/node"; fi; }
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
[[ -f /home/tv-season-linux/data/install.json && -L /etc/systemd/system/tvflow.service ]]
"$HOST_NODE" "$SOURCE/scripts/uninstall.js" --yes
[[ ! -e /home/tv-season-linux && ! -e /usr/local/bin/tvflow && ! -e /etc/systemd/system/tvflow.service && ! -e /root/.local/share/tvflow ]]
[[ -x /home/tvflow-node/bin/node ]]
/home/tvflow-node/bin/node --version
[[ "$(readlink -f -- "$fallback")" == /tmp/tvflow-manager.* ]] && rm -rf -- "$fallback"
printf '%s\n' 'Ubuntu管理器：已有Node复用不下载、缺失时安装、后台启动、卸载程序与保留Node检查通过。'
