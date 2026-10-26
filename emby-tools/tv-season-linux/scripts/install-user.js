import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';

export function installLayout({system,homeDir}) {
 return system?{binDir:'/usr/local/bin',unitDir:'/etc/systemd/system'}:
  {binDir:path.join(homeDir,'.local/bin'),unitDir:path.join(homeDir,'.config/systemd/user')};
}
// systemd解释百分号，ExecStart还解释美元符号，必须按字段转义。
export function quoteUnit(value,{exec=false}={}) {
 if(/[\r\n\x00]/.test(value))throw Error('安装路径包含控制字符');
 let text=value.replaceAll('\\','\\\\').replaceAll('"','\\"').replaceAll('%','%%');
 if(exec)text=text.replaceAll('$',()=> '$$');
 return '"'+text+'"';
}
const stat=file=>{try{return fs.lstatSync(file);}catch(e){if(e.code==='ENOENT')return null;throw e;}};
const linkTo=(file,target)=>stat(file)?.isSymbolicLink()&&path.resolve(path.dirname(file),fs.readlinkSync(file))===target;
const shell=s=>"'"+s.replaceAll("'",()=>"'\\''")+"'";

// 实际命令和服务配置均在程序目录；系统位置只注册链接。
export function installForAccount({
 system=process.platform==='linux'&&process.geteuid?.()===0,
 appDir=path.resolve(fileURLToPath(new URL('..',import.meta.url))),
 homeDir=system?os.userInfo().homedir:os.homedir(),
 nodePath=process.execPath,runtimeNode=process.env.TVFLOW_NODE,
 binDir,unitDir,
}={}) {
 appDir=path.resolve(appDir);
 const layout=installLayout({system,homeDir});binDir??=layout.binDir;unitDir??=layout.unitDir;
 const entry=path.join(appDir,'bin/tvflow.js'),commandFile=path.join(appDir,'bin/tvflow');
 const target=path.join(binDir,'tvflow'),unit=path.join(unitDir,'tvflow.service');
 const unitFile=path.join(appDir,'config/systemd/tvflow.service'),data=path.join(appDir,'data');
 if(runtimeNode){nodePath=path.resolve(runtimeNode);fs.accessSync(nodePath,fs.constants.R_OK);}
 if(/[\r\n\x00]/.test(appDir))throw Error('安装路径包含控制字符');
 const command='#!/usr/bin/env bash\n# tvflow-managed-command\n# tvflow-app: '+appDir+'\nexport TVFLOW_ROOT='+shell(appDir)+'\nexport PATH='+shell(path.dirname(nodePath))+':"$PATH"\nexec '+shell(nodePath)+' '+shell(entry)+' "$@"\n';
 const text='[Unit]\nDescription=TVFlow 剧集整理Linux版\nAfter=network-online.target\n\n[Service]\nType=simple\n'+
  (system?'User=root\n':'')+'Environment='+quoteUnit('HOME='+homeDir)+' '+quoteUnit('TVFLOW_ROOT='+appDir)+'\nWorkingDirectory='+quoteUnit(appDir)+'\n'+
  'ExecStart='+quoteUnit(nodePath,{exec:true})+' '+quoteUnit(entry,{exec:true})+' daemon\nRestart=on-failure\nRestartSec=5\nTimeoutStopSec=75\nUMask=0077\n\n[Install]\nWantedBy='+(system?'multi-user.target':'default.target')+'\n';
 const old=stat(target),oldUnit=stat(unit);
 if(old&&!linkTo(target,commandFile))throw Error('已有不同的tvflow命令，未覆盖：'+target);
 if(oldUnit&&!linkTo(unit,unitFile))throw Error('已有不同的服务配置，未覆盖：'+unit);
 for(const [file,content] of [[commandFile,command],[unitFile,text]]){
  const s=stat(file);if(s&&(!s.isFile()||s.isSymbolicLink()||fs.readFileSync(file,'utf8')!==content))throw Error('程序内存在不同配置，未覆盖：'+file);
 }
 fs.accessSync(entry,fs.constants.R_OK);
 fs.mkdirSync(binDir,{recursive:true});fs.mkdirSync(unitDir,{recursive:true});fs.mkdirSync(path.dirname(unitFile),{recursive:true,mode:0o700});
 fs.writeFileSync(commandFile,command,{encoding:'utf8',mode:0o755});fs.chmodSync(commandFile,0o755);fs.chmodSync(entry,0o755);
 fs.writeFileSync(unitFile,text,{encoding:'utf8',mode:0o600});
 if(!old)fs.symlinkSync(commandFile,target);
 if(!oldUnit)fs.symlinkSync(unitFile,unit);
 return {system,target,unit,commandFile,unitFile,data,config:path.join(appDir,'config/config.json')};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
 const result=installForAccount();
 console.log('命令链接：'+result.target+'\n服务链接：'+result.unit+'\n配置文件：'+result.config+'\n任务目录：'+result.data+'\n尚未启用自启动。');
}
