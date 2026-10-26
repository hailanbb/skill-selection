#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import {rpc,startDaemon} from '../lib/daemon.js';
import {menu,watch} from '../lib/ui.js';
import {home,sleep,errorText} from '../lib/util.js';
import {layout} from '../lib/layout.js';
const args=process.argv.slice(2),command=args[0];
async function ensure(){try{await rpc('ping');return;}catch{}fs.mkdirSync(home(),{recursive:true,mode:0o700});const log=layout().daemonLog;fs.mkdirSync(path.dirname(log),{recursive:true,mode:0o700});const fd=fs.openSync(log,'a',0o600);const child=spawn(process.execPath,[fileURLToPath(import.meta.url),'daemon'],{detached:true,stdio:['ignore',fd,fd],windowsHide:true,env:process.env});child.unref();fs.closeSync(fd);for(let i=0;i<40;i++){await sleep(150);try{await rpc('ping');return;}catch{}}throw Error('后台未启动，请查看 '+log);}
try{
 if(command==='daemon')await startDaemon();
 else if(command==='help'||command==='--help'){console.log('剧集整理Linux版\ntvflow                  中文菜单\ntvflow status           任务摘要\ntvflow watch J编号       实时进度\ntvflow pause J编号       暂停\ntvflow resume J编号      继续\ntvflow needs            待处理事项\ntvflow doctor           只读诊断\ntvflow export J编号      另存报告\ntvflow daemon           前台后台服务（systemd使用）\n配置：程序目录/config/config.json；报告：程序目录/reports。TVFLOW_ROOT 仅供隔离开发测试，正式安装无需设置。');}
 else{await ensure();if(!command)await menu();else if(command==='watch')await watch(args[1]);else if(command==='status')console.log(JSON.stringify(await rpc('jobs'),null,2));else if(command==='doctor')console.log(JSON.stringify(await rpc('doctor'),null,2));else if(['pause','resume','export'].includes(command)){if(!args[1])throw Error('请提供任务ID');console.log(JSON.stringify(await rpc(command,{id:args[1]}),null,2));}else if(command==='needs'){const jobs=await rpc('jobs');console.log(JSON.stringify(jobs.filter(j=>!['completed'].includes(j.status)),null,2));}else throw Error('未知命令，请运行 tvflow help');}
}catch(e){console.error(errorText(e));process.exitCode=1;}
