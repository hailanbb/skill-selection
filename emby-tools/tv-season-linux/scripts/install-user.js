import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
const root=path.resolve(fileURLToPath(new URL('..',import.meta.url))),bin=path.join(os.homedir(),'.local/bin');
fs.mkdirSync(bin,{recursive:true});const target=path.join(bin,'tvflow');
if(fs.existsSync(target)){const old=fs.lstatSync(target);if(!old.isSymbolicLink()||fs.readlinkSync(target)!==path.join(root,'bin/tvflow.js'))throw Error('已有不同的tvflow命令，未覆盖：'+target);}
else fs.symlinkSync(path.join(root,'bin/tvflow.js'),target);
fs.chmodSync(path.join(root,'bin/tvflow.js'),0o755);
const unitDir=path.join(os.homedir(),'.config/systemd/user');fs.mkdirSync(unitDir,{recursive:true});
const unit=path.join(unitDir,'tvflow.service');
// systemd interprets percent specifiers; reject control characters and escape quotes and percent.
const quote=s=>{if(/[\r\n\x00]/.test(s))throw Error('安装路径包含控制字符');return '"'+s.replaceAll('\\','\\\\').replaceAll('"','\\"').replaceAll('%','%%')+'"';};
const text='[Unit]\nDescription=TVFlow 剧集整理Linux版\nAfter=network-online.target\n\n[Service]\nType=simple\nExecStart='+quote(process.execPath)+' '+quote(path.join(root,'bin/tvflow.js'))+' daemon\nRestart=on-failure\nRestartSec=5\nTimeoutStopSec=75\nUMask=0077\n\n[Install]\nWantedBy=default.target\n';
if(fs.existsSync(unit)&&fs.readFileSync(unit,'utf8')!==text)throw Error('已有不同的服务配置，未覆盖：'+unit);
fs.writeFileSync(unit,text,{encoding:'utf8',mode:0o600});console.log('已安装命令和用户服务文件；尚未启用自启动。');
