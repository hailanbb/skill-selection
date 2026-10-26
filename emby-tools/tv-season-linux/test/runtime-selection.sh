#!/usr/bin/env bash
# 不联网、不安装软件，仅用临时运行时测试检测顺序及“缺npm不重复装Node”。
set -euo pipefail
SOURCE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SOURCE/manage.sh"
work="$(mktemp -d /tmp/tvflow-runtime-test.XXXXXXXX)"
trap '[[ "$(readlink -f -- "$work")" == /tmp/tvflow-runtime-test.* ]] && rm -rf -- "$work"' EXIT
mkdir -p "$work/good/bin" "$work/old/bin" "$work/nvm/versions/node/v22.20.0/bin"
cat > "$work/good/bin/node" <<'FAKE'
#!/usr/bin/env bash
if [[ "$1" == -e ]]; then exit 0; fi
if [[ -f "$1" && "${2:-}" == --version ]]; then cat -- "$1"; exit 0; fi
exit 1
FAKE
printf '%s\n' '#!/usr/bin/env bash' 'exit 1' > "$work/old/bin/node"
printf '%s\n' '10.9.0' > "$work/good/bin/npm"
cp -- "$work/good/bin/node" "$work/nvm/versions/node/v22.20.0/bin/node"
cp -- "$work/good/bin/npm" "$work/nvm/versions/node/v22.20.0/bin/npm"
chmod +x "$work/good/bin/node" "$work/old/bin/node" "$work/nvm/versions/node/v22.20.0/bin/node"
# PATH候选先于保留目录，且未加载的nvm版本也进入候选列表。
export PATH="$work/good/bin:$PATH" NVM_DIR="$work/nvm"
TVFLOW_NODE_DIR="$work/retained"
mapfile -t list < <(node_candidates)
[[ "${list[0]}" == "$work/good/bin/node" ]]
printf '%s\n' "${list[@]}" | grep -Fx "$work/nvm/versions/node/v22.20.0/bin/node" >/dev/null
# 测试选择器时把npm范围限定在临时目录，防止宿主机npm干扰缺失场景。
npm_candidates() { printf '%s\n' "$(dirname -- "$1")/npm"; }
find_existing_runtime "$work/good/bin/node"
[[ "$TVFLOW_NODE_BIN" == "$work/good/bin/node" && "$TVFLOW_NPM_CLI" == "$work/good/bin/npm" ]]
find_existing_runtime "$work/old/bin/node" "$work/nvm/versions/node/v22.20.0/bin/node"
[[ "$TVFLOW_NODE_BIN" == "$work/nvm/versions/node/v22.20.0/bin/node" ]]
if find_existing_runtime "$work/old/bin/node"; then exit 1; else [[ $? == 1 ]]; fi
mv -- "$work/good/bin/npm" "$work/good/bin/npm.saved"
if find_existing_runtime "$work/good/bin/node"; then exit 1; else [[ $? == 2 ]]; fi
[[ "$TVFLOW_NODE_BIN" == "$work/good/bin/node" && -z "$TVFLOW_NPM_CLI" ]]
node_candidates() { printf '%s\n' "$work/good/bin/node"; }
install_node() { printf '%s\n' '不应下载重复Node' >&2; exit 99; }
if prepare_runtime; then exit 1; fi
mv -- "$work/good/bin/npm.saved" "$work/good/bin/npm"
prepare_runtime
[[ ! -e "$TVFLOW_NODE_DIR" ]]
printf '%s\n' 'Node检测：PATH优先、旧版本跳过、未加载nvm复用、无合格版本、缺npm不重复安装、复用不下载：通过。'
