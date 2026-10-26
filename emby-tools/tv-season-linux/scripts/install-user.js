import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';

// 保留原安装入口；root无需用户会话或linger，普通用户保持原有安装位置。
export function installLayout({system,homeDir}) {
 return system?{binDir:'/usr/local/bin',unitDir:'/etc/systemd/system'}:
  {binDir:path.join(homeDir,'.local/bin'),unitDir:path.join(homeDir,'.config/systemd/user')};
}

// systemd会解释百分号，ExecStart还会解释美元符号；路径必须按字段转义。
export function quoteUnit(value,{exec=false}={}) {
 if(/[\r\n\x00]/.test(value))throw Error('安装路径包含控制字符');
 let text=value.replaceAll('\\','\\\\').replaceAll('"','\\"').replaceAll('%','%%');
 if(exec)text=text.replaceAll('$',()=> '$$');
 return '"'+text+'"';
}
function existing(file) {
 try{return fs.lstatSync(file);}catch(e){if(e.code==='ENOENT')return null;throw e;}
}

// 参数用于临时目录测试；正常安装始终使用当前账号的固定布局，不启用或重启服务。
export function installForAccount({
 system=process.platform==='linux'&&process.geteuid?.()===0,
 appDir=path.resolve(fileURLToPath(new URL('..',import.meta.url))),
 homeDir=system?os.userInfo().homedir:os.homedir(),
 nodePath=process.execPath,stateDir=process.env.TVFLOW_HOME,runtimeNode=process.env.TVFLOW_NODE,
 binDir,unitDir,
}={}) {
 const layout=installLayout({system,homeDir});
 binDir??=layout.binDir;unitDir??=layout.unitDir;
 const entry=path.join(appDir,'bin/tvflow.js'),target=path.join(binDir,'tvflow'),unit=path.join(unitDir,'tvflow.service');
 const managed=!!runtimeNode;
 if(managed){nodePath=path.resolve(runtimeNode);fs.accessSync(nodePath,fs.constants.R_OK);}
 const shell=s=>"'"+s.replaceAll("'",()=>"'\\''")+"'";
 if(/[\r\n\x00]/.test(appDir))throw Error('安装路径包含控制字符');
 // 专用Node不进入全局PATH；tvflow包装命令仅为本程序补齐运行环境。
 const command=managed?'#!/usr/bin/env bash\n# tvflow-managed-command\n# tvflow-app: '+appDir+'\nexport PATH='+shell(path.dirname(nodePath))+':"$PATH"\nexec '+shell(nodePath)+' '+shell(entry)+' "$@"\n':null;
 const data=path.resolve(stateDir||path.join(homeDir,'.local/share/tvflow'));
 const text='[Unit]\nDescription=TVFlow 剧集整理Linux版\nAfter=network-online.target\n\n[Service]\nType=simple\n'+
  (system?'User=root\nEnvironment='+quoteUnit('HOME='+homeDir)+' '+quoteUnit('TVFLOW_HOME='+data)+'\n':'')+
  'ExecStart='+quoteUnit(nodePath,{exec:true})+' '+quoteUnit(entry,{exec:true})+' daemon\nRestart=on-failure\nRestartSec=5\nTimeoutStopSec=75\nUMask=0077\n\n[Install]\nWantedBy='+(system?'multi-user.target':'default.target')+'\n';
 // 所有冲突先检查，避免仅装好一半；包括失效符号链接，不覆盖不同的既有命令或服务。
 const old=existing(target),oldUnit=existing(unit);
 if(old&&(managed?(!old.isFile()||fs.readFileSync(target,'utf8')!==command):(!old.isSymbolicLink()||fs.readlinkSync(target)!==entry)))throw Error('已有不同的tvflow命令，未覆盖：'+target);
 if(oldUnit&&(!oldUnit.isFile()||fs.readFileSync(unit,'utf8')!==text))throw Error('已有不同的服务配置，未覆盖：'+unit);
 fs.accessSync(entry,fs.constants.R_OK);
 fs.mkdirSync(binDir,{recursive:true});fs.mkdirSync(unitDir,{recursive:true});
 if(!old){if(managed)fs.writeFileSync(target,command,{encoding:'utf8',mode:0o755,flag:'wx'});else fs.symlinkSync(entry,target);}
 fs.chmodSync(entry,0o755);
 if(!oldUnit)fs.writeFileSync(unit,text,{encoding:'utf8',mode:system?0o644:0o600,flag:'wx'});
 return {system,target,unit,data};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
 const result=installForAccount();
 console.log('已安装命令：'+result.target+'\n服务文件：'+result.unit+'\n数据目录：'+result.data+'\n尚未启用自启动。');
 console.log('进入中文菜单：'+result.target);
 console.log(result.system?'启用后台：systemctl daemon-reload && systemctl enable --now tvflow.service':
  '启用后台：systemctl --user daemon-reload && systemctl --user enable --now tvflow.service（SSH退出后保留服务还需配置linger，参见INSTALL.md）');
}
