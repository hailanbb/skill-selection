import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {DatabaseSync} from 'node:sqlite';

const stat=p=>{try{return fs.lstatSync(p);}catch(e){if(e.code==='ENOENT')return null;throw e;}};
const inside=(p,root)=>p===root||p.startsWith(root+path.sep);
const safe=p=>{p=path.resolve(p);if(['/','/home','/root','/usr','/usr/local','/etc','/var','/tmp','/opt'].includes(p))throw Error('拒绝清理公共目录：'+p);if(p==='/home/tvflow-node'||p.startsWith('/home/tvflow-node/'))throw Error('Node目录受保护，不参与卸载：'+p);if(stat(p)&&fs.realpathSync(p)!==p)throw Error('清理路径包含符号链接，停止：'+p);return p;};
function isApp(p){try{return stat(p)?.isDirectory()&&!stat(p).isSymbolicLink()&&JSON.parse(fs.readFileSync(path.join(p,'package.json'),'utf8')).name==='tv-season-linux'&&fs.existsSync(path.join(p,'bin/tvflow.js'));}catch{return false;}}
function json(p){try{return JSON.parse(fs.readFileSync(p,'utf8'));}catch{return null;}}
// 只构建可审阅的本机清单，不连接CloudDrive2/MoviePilot，不遍历或删除云盘媒体。
export function uninstallPlan({homeDir=os.userInfo().homedir,defaultApp='/home/tv-season-linux',
 binPaths=['/usr/local/bin/tvflow',path.join(homeDir,'.local/bin/tvflow')],
 unitPaths=['/etc/systemd/system/tvflow.service',path.join(homeDir,'.config/systemd/user/tvflow.service')],
 dataDir=path.join(defaultApp,'data')}={}){
 const context={homeDir,defaultApp,binPaths,unitPaths,dataDir},apps=new Set(),commands=[],units=[],warnings=[],dataDirs=new Set([safe(dataDir)]),files=[],serviceDirs=[],busyJobs=[];
 if(isApp(defaultApp))apps.add(safe(defaultApp));
 for(const bin of binPaths){const s=stat(bin);if(!s)continue;let entry;
  if(s.isSymbolicLink())entry=path.resolve(path.dirname(bin),fs.readlinkSync(bin));
  else if(s.isFile()){const t=fs.readFileSync(bin,'utf8');const m=/^# tvflow-app: (.+)$/m.exec(t);if(t.includes('# tvflow-managed-command')&&m)entry=path.join(m[1],'bin/tvflow.js');}
  const app=entry&&path.dirname(path.dirname(entry));
  if(app&&['tvflow.js','tvflow'].includes(path.basename(entry))&&path.basename(path.dirname(entry))==='bin'&&(isApp(app)||app===defaultApp&&!fs.existsSync(app))){if(isApp(app))apps.add(safe(app));commands.push(bin);}else warnings.push('未识别的同名命令保留：'+bin);
 }
 for(const unit of unitPaths){if(!stat(unit))continue;
  const linked=stat(unit).isSymbolicLink();
  if(linked&&![...apps].some(app=>path.resolve(path.dirname(unit),fs.readlinkSync(unit))===path.join(app,'config/systemd/tvflow.service')))throw Error('服务链接不属于本程序，停止：'+unit);
  if(!linked&&!stat(unit).isFile())throw Error('服务文件不是普通文件，停止：'+unit);
  const text=fs.readFileSync(unit,'utf8');
  if(!text.includes('Description=TVFlow 剧集整理Linux版')||![...apps,defaultApp].some(app=>text.includes(path.join(app,'bin/tvflow.js')))){warnings.push('未识别的同名服务保留：'+unit);continue;}
  units.push(unit);
  for(const wanted of ['multi-user.target.wants','default.target.wants']){const link=path.join(path.dirname(unit),wanted,'tvflow.service');if(stat(link)?.isSymbolicLink()&&[unit,...[...apps].map(app=>path.join(app,'config/systemd/tvflow.service'))].includes(path.resolve(path.dirname(link),fs.readlinkSync(link))))commands.push(link);}
  const drop=unit+'.d';if(stat(drop)){if(stat(drop).isSymbolicLink()){if(![...apps].some(app=>path.resolve(path.dirname(drop),fs.readlinkSync(drop))===path.join(app,'config/systemd/tvflow.service.d')))throw Error('服务附加配置链接不属于本程序：'+drop);commands.push(drop);}else{safe(drop);if(!stat(drop).isDirectory())throw Error('服务附加配置不是目录：'+drop);serviceDirs.push(drop);}}
  const match= /"TVFLOW_ROOT=((?:\\.|[^"\\])*)"/.exec(text);
  if(match){const root=match[1].replaceAll('%%','%').replace(/\\([\\"])/g,'$1');if(apps.has(root))dataDirs.add(safe(path.join(root,'data')));}
 }
 for(const app of apps)if(json(path.join(app,'config/config.json'))?.schema===1)dataDirs.add(safe(path.join(app,'data')));
 for(const dir of dataDirs){
  if(!stat(dir))continue;
  const cfg=json(path.join(dir,'config.json'))||([...apps].some(app=>dir===path.join(app,'data'))?json(path.join(path.dirname(dir),'config/config.json')):null);
  const database=path.join(dir,'state.sqlite');
  if(!cfg?.cloud||!cfg?.moviepilot||cfg.schema!==1){if(!fs.existsSync(database)){warnings.push('未确认归属的数据目录保留：'+dir);dataDirs.delete(dir);continue;}}
  if(fs.existsSync(database)){
   const db=new DatabaseSync(database,{readOnly:true});try{
    const jobs=db.prepare("SELECT value FROM records WHERE kind='job'").all().map(r=>JSON.parse(r.value));
    busyJobs.push(...jobs.filter(j=>['running','queued'].includes(j.status)).map(j=>j.id));
    for(const j of jobs){if(!/^J[a-f0-9]{10}$/.test(j.id)||!Array.isArray(j.files))continue;
     for(const p of [...j.files,j.logPath].filter(p=>typeof p==='string')){
      const full=path.resolve(p),folder=path.dirname(full),name=path.basename(full);
      const roots=Object.values(j.config?.outputs||{}).filter(r=>typeof r==='string').map(r=>path.resolve(r));
      if(path.basename(folder)!==j.id||!roots.some(root=>inside(full,root))||!(name==='task.log'||name.startsWith(j.stage+'_'+j.id+'_')))continue;
      if([...dataDirs,...apps].some(root=>inside(full,root)))continue;
      if(stat(full)&&(!stat(full).isFile()||stat(full).isSymbolicLink()))throw Error('报告文件类型发生变化：'+full);
      if(stat(full)){safe(full);files.push(full);}
     }
    }
   }finally{db.close();}
  }
 }
 // 上传的本程序配置也在清理范围内；只匹配本程序结构，不读取或输出认证值。
 const uploaded=path.join(homeDir,'tvflow-config.json'),cfg=json(uploaded);
 if(cfg?.schema===1&&cfg.cloud&&cfg.moviepilot&&cfg.outputs){safe(uploaded);files.push(uploaded);}
 return {schema:1,context,apps:[...apps],commands,units,serviceDirs,dataDirs:[...dataDirs],files:[...new Set(files)],warnings,busyJobs};
}
export function daemonProcesses(apps,{proc='/proc'}={}){
 const found=[];if(!fs.existsSync(proc))return found;
 for(const name of fs.readdirSync(proc).filter(s=>/^\d+$/.test(s))){try{
  const executable=fs.readlinkSync(path.join(proc,name,'exe')).replace(/ \(deleted\)$/,'');if(!/^node(?:js)?$/.test(path.basename(executable)))continue;
  const args=fs.readFileSync(path.join(proc,name,'cmdline'),'utf8').split('\0').filter(Boolean);
  const at=args.findIndex(a=>a.endsWith('tvflow.js'));if(at<1||args[at+1]!=='daemon')continue;
  const cwd=fs.readlinkSync(path.join(proc,name,'cwd')),entry=path.resolve(cwd,args[at]);
  if(apps.some(app=>entry===path.join(app,'bin/tvflow.js')))found.push(Number(name));
 }catch{}}
 return found;
}
export async function uninstall(plan,{run=(cmd,args)=>execFileSync(cmd,args,{stdio:'ignore',timeout:90000}),
 findPids=()=>daemonProcesses(plan.apps),signal=pid=>process.kill(pid,'SIGTERM'),
 wait=ms=>new Promise(r=>setTimeout(r,ms)),timeoutMs=80000}={}){
 // 执行前重新验证目录身份，绝不以外部提供的任意路径进行递归删除。
 for(const app of plan.apps)if(!isApp(safe(app)))throw Error('程序目录已改变：'+app);
 for(const p of plan.dataDirs)safe(p);
 for(const unit of plan.units){try{run('systemctl',[...(unit.startsWith('/etc/systemd/system/')?[]:['--user']),'disable','--now','tvflow.service']);}catch{}}
 for(const pid of findPids())signal(pid);
 const limit=Date.now()+timeoutMs;
 while(findPids().length){if(Date.now()>=limit)throw Error('后台尚未退出，停止清理；请等待任务暂停后重试');await wait(200);}
 // 任务收到SIGTERM后可能补写最后一份报告，停止后重读记录，避免漏掉自定义目录中的新输出。
 if(plan.context){const updated=uninstallPlan(plan.context);for(const key of ['apps','dataDirs'])if(JSON.stringify([...updated[key]].sort())!==JSON.stringify([...plan[key]].sort()))throw Error('卸载范围在停止后台期间变化，请重新审阅清单');if(updated.busyJobs.length)throw Error('任务记录尚未完成暂停，数据已保留；请先恢复程序并检查任务后重试');plan=updated;}
 for(const p of plan.files){if(stat(p)){safe(p);fs.unlinkSync(p);const dir=path.dirname(p);if(/^J[a-f0-9]{10}$/.test(path.basename(dir))&&!fs.readdirSync(dir).length)fs.rmdirSync(dir);}}
 for(const p of [...plan.commands,...plan.units])if(stat(p))fs.unlinkSync(p);
 for(const p of plan.serviceDirs||[])if(stat(p))fs.rmSync(safe(p),{recursive:true});
 for(const p of plan.dataDirs)if(stat(p))fs.rmSync(safe(p),{recursive:true});
 // 仓库中的其他项目、系统Node/npm和nvm均不属于递归清理范围。
 for(const app of plan.apps)fs.rmSync(safe(app),{recursive:true});
 if(plan.units.some(p=>p.startsWith('/etc/systemd/system/'))){try{run('systemctl',['daemon-reload']);run('systemctl',['reset-failed','tvflow.service']);}catch{}}
 return {removed:[...plan.apps,...plan.commands,...plan.units,...plan.serviceDirs,...plan.dataDirs,...plan.files],warnings:plan.warnings};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{
  if(process.platform!=='linux'||process.geteuid?.()!==0)throw Error('请在Ubuntu的root终端使用管理菜单卸载');
  const plan=uninstallPlan();
  console.log('将清理以下本机程序、配置、任务历史、报告与日志：\n'+[...plan.apps,...plan.commands,...plan.units,...plan.serviceDirs,...plan.dataDirs,...plan.files].join('\n'));
  for(const warning of plan.warnings)console.log(warning);
  if(process.argv.includes('--dry-run'))process.exit(0);
  // Bootstrap菜单已明确告知清除内容；此入口也要求显式--yes，避免误运行。
  if(!process.argv.includes('--yes'))throw Error('未确认清理，请从管理菜单选择2，或先使用--dry-run查看范围');
  const result=await uninstall(plan);console.log('本程序清理完成；Node、云盘媒体及MoviePilot均保留。');
  if(result.warnings.length)console.log('有未确认归属的内容被保留，请按上方路径核对。');
 }catch(e){console.error(e.message);process.exitCode=1;}
}
