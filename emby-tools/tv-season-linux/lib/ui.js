import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import readline from 'node:readline/promises';
import {rpc} from './daemon.js';
import {jobSummary} from './reports.js';
import {safeText,errorText,parent,within,digest} from './util.js';
const paint=(s,n)=>process.stdout.isTTY&&!process.env.NO_COLOR?'\x1b['+n+'m'+safeText(s)+'\x1b[0m':safeText(s);
const print=s=>console.log(safeText(s));
const stateColor=s=>/归档已|已归档/.test(s)?35:/失败|无合格|failed/.test(s)?31:/待|缺集|暂停|paused|issues/.test(s)?33:/运行|running|连载/.test(s)?36:32;
export const colored=s=>paint(s,stateColor(s));
const labels={inspect:'初检','library-audit':'归档库复核',download:'补缺下载',review:'复核',archive:'归档检查','archive-audit':'归档报告核验',repair:'整理问题检查',execute:'执行清单',reconcile:'结果核实',queued:'排队',running:'运行中',paused:'已暂停',completed:'已完成','completed-with-issues':'已结束，有待核实项',failed:'失败'};
export async function ask(text){const rl=readline.createInterface({input:process.stdin,output:process.stdout});try{return (await rl.question(text)).trim();}finally{rl.close();}}
async function secret(){if(!process.stdin.isTTY)throw Error('认证设置需要交互终端');process.stdout.write('输入认证值（隐藏输入，回车保存，Esc取消）：');return new Promise(resolve=>{let text='';const old=process.stdin.isRaw;process.stdin.setRawMode(true);process.stdin.resume();const done=v=>{process.stdin.off('data',read);process.stdin.setRawMode(old||false);process.stdin.pause();process.stdout.write('\n');resolve(v);};const read=b=>{const s=b.toString('utf8');for(const c of s){if(c==='\r'||c==='\n'){done(text);return;}if(c==='\u001b'||c==='\u0003'){done(null);return;}if(c==='\u007f'||c==='\b')text=text.slice(0,-1);else if(c>=' ')text+=c;}};process.stdin.on('data',read);});}
export function selection(text,count){const set=new Set();if(text==='a')return Array.from({length:count},(_,i)=>i);for(const token of text.split(',')){const m=/^(\d+)(?:-(\d+))?$/.exec(token.trim());if(!m)throw Error('使用编号或1,3,5-8格式');const a=Number(m[1]),b=Number(m[2]||m[1]);if(a<1||b<a||b>count)throw Error('编号超出范围');for(let n=a;n<=b;n++)set.add(n-1);}return [...set];}
function elapsed(j){return Math.max(0,Math.floor((Date.parse(j.finishedAt||new Date().toISOString())-Date.parse(j.startedAt||j.createdAt))/1000));}
export function progressLines(j){const n=j.total,done=Math.min(j.index,n??j.index),ratio=n?Math.floor(done/n*20):0;return [
 '任务 '+j.id+' · '+(labels[j.stage]||j.stage)+' · '+(labels[j.status]||j.status),
 '范围：'+(j.payload?.scopes||[]).join('、')+'    工作流：'+j.workflow,
 n===null?'正在发现目录，总量尚未确定':n===0?'本轮没有符合条件的对象':'['+'█'.repeat(ratio)+'░'.repeat(20-ratio)+'] '+Math.floor(done/n*100)+'%  '+done+'/'+n+' 项',
 '已耗时：'+elapsed(j)+'秒    最近进展：'+j.updatedAt,
 '当前：'+j.current,
 ...(j.operationProgress?['本清单已验证：'+j.operationProgress.done+'/'+j.operationProgress.total+' '+j.operationProgress.unit]:[]),
 '本轮结果：'+Object.entries((j.results||[]).reduce((o,r)=>(o[r.state||'未知']=(o[r.state||'未知']||0)+1,o),{})).map(([k,v])=>k+' '+v).join(' / '),
 ...j.events.slice(-6).map(e=>e.at.slice(11,19)+' UTC  '+e.text)
 ];}
function completed(j){console.log(colored('任务 '+j.id+'：'+(labels[j.status]||j.status)));print('耗时：'+elapsed(j)+'秒；已处理 '+j.index+'/'+(j.total??'?')+' 项');
 for(const [k,v] of Object.entries(jobSummary(j)))console.log(colored(k)+': '+v);
 for(const e of j.errors||[])console.log(paint(e,31));
 print('\n已成功保存的报告、完整记录与日志：');for(const f of j.files||[])print('  '+path.basename(f)+'\n  '+f);
 for(const e of j.exportErrors||[])console.log(paint('保存失败：'+(e.file||'')+' '+e.error,31));
 print('下载接受不代表文件齐全；CSV各表分别保存，JSON包含完整记录。');
}
export async function watch(id){
 if(!id)throw Error('缺少任务ID');if(!process.stdin.isTTY){const j=await rpc('job',{id});progressLines(j).forEach(print);if(!['running','queued'].includes(j.status))completed(j);return;}
 return new Promise((resolve,reject)=>{let busy=false,stopped=false,timer,latest;const old=process.stdin.isRaw;
  const stop=()=>{if(stopped)return;stopped=true;clearInterval(timer);process.stdin.off('data',key);process.stdin.setRawMode(old||false);process.stdin.pause();};
  const key=async b=>{const s=b.toString();if(s==='b'||s==='q'||s==='\u0003'){stop();print('已退出观看；后台任务继续。');resolve(latest);}
   else if(s==='1'){try{await rpc('pause',{id});}catch(e){print(errorText(e));}}
  };
  process.stdin.setRawMode(true);process.stdin.resume();process.stdin.on('data',key);
  const tick=async()=>{if(busy||stopped)return;busy=true;try{const j=await rpc('job',{id});latest=j;if(stopped)return;
   if(process.stdout.isTTY)process.stdout.write('\x1b[2J\x1b[H');for(const line of progressLines(j))console.log(colored(line));
   print('\n1 暂停任务    b 返回菜单，后台继续    Ctrl+C 退出观看');
   if(!['running','queued'].includes(j.status)){stop();completed(j);resolve(j);}
  }catch(e){stop();reject(e);}finally{busy=false;}};
  timer=setInterval(tick,1000);void tick();
 });
}
async function browse(start,{chooseRoot=false,boundary=null}={}){let current=start;
 while(true){if(boundary&&!within(current,boundary))throw Error('只能选择归档库根目录内的路径：'+boundary);print('\n当前位置：'+current);let rows;try{rows=await rpc('browse',{path:current});}catch(e){print(errorText(e));const p=await ask('输入新的绝对路径，或b返回：');if(p==='b')return null;current=p;continue;}
  const dirs=rows.filter(r=>r.directory);dirs.forEach((r,i)=>print((i+1)+'  '+r.name+'/'));print('普通文件：'+rows.filter(r=>!r.directory).length+'个');
  print('编号进入；s 选择当前目录；m 批量选择子目录；u 上级；/ 输入路径；b 返回');const v=await ask('请选择：');if(v==='b')return null;if(v==='u'){current=boundary&&current===boundary?boundary:parent(current);continue;}if(v==='/'){current=await ask('绝对路径：');continue;}if(v==='s')return [current];
  if(v==='m'&&!chooseRoot){const answer=await ask('编号，例如1,3-5；a选择全部；b返回：');if(answer==='b')continue;return selection(answer,dirs.length).map(i=>dirs[i].path);}
  if(/^\d+$/.test(v)&&dirs[Number(v)-1])current=dirs[Number(v)-1].path;
 }
}
async function setRoot(key){const c=await rpc('config');print('当前'+({source:'源根',destination:'归档根',libraryRoot:'归档库复核根'}[key])+'：'+(c[key]||'未设置'));print('1 浏览选择\n2 输入绝对路径\nb 返回');const a=await ask('请选择：');let value;if(a==='1'){const p=await browse(c[key]||'/',{chooseRoot:true});value=p?.[0];}else if(a==='2')value=await ask('CloudDrive2虚拟绝对路径：');if(!value)return;await rpc('set-config',{section:'root',key,value});print('目录已验证并保存；已有任务不改变路径。');}
async function settings(){while(true){print('\n设置与连接诊断\n1 当前源根目录\n2 归档根目录\n3 CloudDrive2连接\n4 MoviePilot连接\n5 整理修复路径\n6 只读连接诊断\n7 报告与保存路径\n8 查看当前配置（认证隐藏）\nb 返回');const v=await ask('请选择：');if(v==='b')return;
 try{
  if(v==='1'||v==='2')await setRoot(v==='1'?'source':'destination');
  else if(v==='3'||v==='4'){const section=v==='3'?'cloud':'moviepilot';print('1 设置地址\n2 设置API认证值\n3 设置'+(v==='3'?'传输方式':'认证类型')+'\nb 返回');const k=await ask('请选择：');let key,value;if(k==='1'){key='url';value=await ask('服务地址（协议+主机+端口）：');}if(k==='2'){key='token';value=await secret();}if(k==='3'){key=v==='3'?'transport':'auth';value=await ask(v==='3'?'grpc / grpc-web：':'apikey / bearer：');}if(key&&value!==null)await rpc('set-config',{section,key,value});}
  else if(v==='5'){print('填写MoviePilot看到的路径；可以是其容器内路径。');for(const key of ['source','target']){const value=await ask((key==='source'?'下载源根':'整理目标根')+'（b返回）：');if(value==='b')break;await rpc('set-config',{section:'repair',key,value});}}
  else if(v==='6')print(JSON.stringify(await rpc('doctor'),null,2));
  else if(v==='7')await outputSettings();
  else if(v==='8')print(JSON.stringify(await rpc('config'),null,2));
 }catch(e){console.log(paint(errorText(e),31));}
}}
async function outputSettings(){while(true){const c=await rpc('config');print('\n报告与保存路径\n1 报告目录（Excel / CSV）：'+c.outputs.reports+'\n2 完整记录目录（JSON）：'+c.outputs.records+'\n3 运行日志目录：'+c.outputs.logs+'\n4 检查可写性\n5 恢复默认路径\nb 返回');const k=await ask('请选择：');if(k==='b')return;
 if(['1','2','3'].includes(k)){const value=await ask('Ubuntu本机绝对路径（支持~/；不存在则创建；b返回）：');if(value==='b')continue;await rpc('set-config',{section:'outputs',key:['reports','records','logs'][Number(k)-1],value});print('已检查后台账户可写性并保存，影响新任务。');}
 else if(k==='4')print(JSON.stringify(await rpc('outputs-check'),null,2));
 else if(k==='5'){const root=process.env.TVFLOW_HOME||path.join(os.homedir(),'.local/share/tvflow');print('恢复到：'+root+'/reports、records、logs；旧文件不移动。');if(await ask('输入恢复确认：')==='恢复')for(const key of ['reports','records','logs'])await rpc('set-config',{section:'outputs',key,value:path.join(root,key)});}
}}
let currentWorkflow=null,currentLibraryWorkflow=null;
async function chooseWorkflow(force=false){const list=(await rpc('workflows')).filter(w=>w.kind!=='library-audit');if(!list.length)throw Error('还没有初检记录');if(!force&&currentWorkflow&&list.some(w=>w.id===currentWorkflow))return currentWorkflow;if(!force&&list.length===1){currentWorkflow=list[0].id;return currentWorkflow;}list.forEach((w,i)=>print((i+1)+' '+w.id+' '+w.createdAt+' '+w.scopes.join('、')+' / '+w.count+'条'));const a=await ask('选择关联工作流编号，b返回：');if(a==='b')return null;const w=list[Number(a)-1];if(!w)throw Error('编号无效');currentWorkflow=w.id;return w.id;}
async function start(stage,params={}){const job=await rpc('create',{stage,...params});if(stage==='library-audit')currentLibraryWorkflow=job.workflow;else currentWorkflow=job.workflow;return watch(job.id);}
async function libraryResults(onlyIssues=false){const list=(await rpc('workflows')).filter(w=>w.kind==='library-audit');if(!list.length)throw Error('还没有归档库复核记录');list.forEach((w,i)=>print((i+1)+' '+w.id+' '+w.createdAt+' '+w.scopes.join('、')));const a=await ask('选择归档库复核编号，b返回：');if(a==='b')return;const w=list[Number(a)-1];if(!w)throw Error('编号无效');currentLibraryWorkflow=w.id;await showResults(w.id,onlyIssues);}
async function libraryMenu(){while(true){const c=await rpc('config'),root=c.libraryRoot||c.destination||'/115/Library_incs/nas.finish';print('\n归档库复核（只读）\n归档库根：'+root+'\n上次复核：'+(currentLibraryWorkflow||'未选择')+'\n1 浏览并选择电视剧/动漫分类\n2 输入归档库检查路径\n3 查看复核记录\n4 查看异常/未完结项\n5 设置归档库复核根目录\n6 查看任务/暂停/继续/导出\nb 返回');const a=await ask('请选择：');if(a==='b')return;try{
 if(a==='3'||a==='4'){await libraryResults(a==='4');continue;}if(a==='5'){await setRoot('libraryRoot');continue;}if(a==='6'){await jobsMenu();continue;}
 let scopes;if(a==='1')scopes=await browse(root,{boundary:root});if(a==='2'){const p=await ask('归档库内绝对路径（b返回）：');if(p!=='b')scopes=[p];}if(!scopes?.length)continue;
 print('检查范围：\n'+scopes.join('\n')+'\n只读检查集号、多个版本及混版；自动导出报告，不生成下载或清理计划。');if(await ask('1 开始复核；其他返回：')==='1')await start('library-audit',{scopes});
 }catch(e){console.log(paint(errorText(e),31));}}}
async function inspectMenu(){while(true){const c=await rpc('config');print('\n初检目录\n当前源根：'+c.source+'\n1 浏览并选择检查范围\n2 输入检查目录路径\n3 查看当前初检结果\n4 设置当前源根\nb 返回');const v=await ask('请选择：');if(v==='b')return;if(v==='4'){await setRoot('source');continue;}if(v==='3'){const w=await chooseWorkflow();if(w)await showResults(w);continue;}
 let scopes;if(v==='1')scopes=await browse(c.source);if(v==='2'){const p=await ask('CloudDrive2绝对路径（b返回）：');if(p!=='b')scopes=[p];}if(!scopes?.length)continue;
 print('初检仅只读；范围：\n'+scopes.join('\n'));if(await ask('1 开始检查；其他返回：')!=='1')continue;const j=await start('inspect',{scopes});
 if(j&&['completed','completed-with-issues'].includes(j.status)){print('1 按本次结果开始补缺\n2 查看异常详情\nb 返回');const next=await ask('请选择：');if(next==='1')await downloadStart(j.workflow);if(next==='2')await showResults(j.workflow,true);}
}}
async function showResults(w,onlyIssues=false){const flow=await rpc('workflow',{id:w});const rows=flow.seasons.filter(s=>!onlyIssues||!['green','archived'].includes(s.color));let query='';while(true){const filtered=rows.filter(s=>!query||(s.name+' '+s.path+' '+s.state).includes(query));for(let i=0;i<filtered.length;i++){const s=filtered[i];console.log((i+1)+' '+safeText(s.name)+' / '+(s.season?'S'+s.season:'目录')+' '+colored(s.state)+'\n  '+safeText(s.note||''));}const a=await ask('/ 搜索；编号查看详情；b返回：');if(a==='b')return;if(a==='/'){query=await ask('搜索词：');continue;}const s=filtered[Number(a)-1];if(s)print(JSON.stringify(s,null,2));}}
async function downloadStart(workflow){const w=await rpc('workflow',{id:workflow});const targets=w.seasons.filter(s=>s.season&&!['green','archived'].includes(s.color));print('依据工作流：'+workflow+'\n自动检查 '+targets.length+' 季；绿/紫跳过；已有任务和结果不明不重复提交。\n开始后按已确认规则自动搜索、选资源并提交到MoviePilot默认下载器。');if(await ask('输入开始确认本轮补缺；其他返回：')==='开始')await start('download',{workflow});}
async function stageMenu(kind){const workflow=await chooseWorkflow();if(!workflow)return;
 while(true){const c=await rpc('config');if(kind==='download')print('\n补缺下载与整理修复 · '+currentWorkflow+'\n1 按当前初检结果开始补缺\n2 查看工作流结果\n3 检查整理问题\n4 查看并执行修复清单\n5 核实上次结果\n6 切换工作流\nb 返回');
  if(kind==='review')print('\n复核与清理 · '+currentWorkflow+'\n1 开始只读复核\n2 查看复核结果\n3 查看并执行清理清单\n4 核实上次结果\n5 切换工作流\nb 返回');
  if(kind==='archive')print('\n归档 · '+currentWorkflow+'\n源根：'+c.source+'\n归档根：'+(c.destination||'未设置')+'\n1 检查归档条件\n2 查看并执行归档清单\n3 核实上次未完成操作\n4 查看工作流结果\n5 复核归档报告与云盘（只读）\ns 设置归档根目录\nb 返回');
  const a=await ask('请选择：');if(a==='b')return;
  try{
   if(kind==='download'){if(a==='1')await downloadStart(currentWorkflow);if(a==='2')await showResults(currentWorkflow);if(a==='3')await start('repair',{workflow:currentWorkflow});if(a==='4')await plans(currentWorkflow,'repair');if(a==='5')await start('reconcile',{workflow:currentWorkflow});if(a==='6')await chooseWorkflow(true);}
   if(kind==='review'){if(a==='1')await start('review',{workflow:currentWorkflow});if(a==='2')await showResults(currentWorkflow);if(a==='3')await plans(currentWorkflow,'cleanup');if(a==='4')await start('reconcile',{workflow:currentWorkflow});if(a==='5')await chooseWorkflow(true);}
   if(kind==='archive'){if(a==='s')await setRoot('destination');if(a==='1'){if(!c.destination)await setRoot('destination');else await start('archive',{workflow:currentWorkflow});}if(a==='2')await plans(currentWorkflow,'archive');if(a==='3')await start('reconcile',{workflow:currentWorkflow});if(a==='4')await showResults(currentWorkflow);if(a==='5')await start('archive-audit',{workflow:currentWorkflow});}
  }catch(e){console.log(paint(errorText(e),31));}
 }
}
async function plans(workflow,kind){const list=(await rpc('plans',{workflow,kind})).filter(p=>['ready','approved'].includes(p.status)&&!p.executionJob);if(!list.length){print('没有尚未执行的可用清单，请先检查或复核。');return;}list.forEach((p,i)=>print((i+1)+' '+p.id+' '+(p.body.showName||p.body.name||p.body.task?.name||p.seasonPath)+' '+p.kind));const n=await ask('选择清单编号，b返回：');if(n==='b')return;const p=list[Number(n)-1];if(!p)throw Error('编号无效');
 // Full manifest is printed before approval, including paths and reasons; never abbreviate mutation targets.
 planLines(p).forEach(print);print('以上为完整清单。普通删除的可恢复性取决于远端存储。');if(kind==='repair')print('同时确认该资源已经下载完成。');
 if(await ask('输入“执行 '+p.id+'”确认；其他返回：')!=='执行 '+p.id)return;
 if(p.status==='ready')await rpc('approve',{id:p.id,hash:p.hash});await start('execute',{workflow,plan:p.id});
}
export function planLines(p){const b=p.body,lines=['清单 '+p.id+' · '+({cleanup:'版本清理',archive:'归档',repair:'整理修复'}[p.kind]||p.kind)];
 if(p.kind==='cleanup'){lines.push('作品：'+b.showName+' / Season '+b.season,'保留视频 '+b.keep.length+' 个；拟删文件 '+b.remove.length+' 个');for(const g of b.groups||[])lines.push('版本：'+g.label+'；'+(g.complete?'完整':'缺集 '+g.missing.join('、')));for(const f of b.keep)lines.push('保留：'+f.path+' · '+f.size+' · '+f.modified);for(const f of b.remove)lines.push('删除：'+f.path+' · '+f.size+' · '+f.modified+'\n  原因：'+f.reason);for(const f of b.preserved||[])lines.push('保留配套：'+f.path+'；'+f.reason);}
 if(p.kind==='archive'){lines.push('作品：'+b.name,'源：'+b.source,'目标：'+b.target,'方式：'+(b.mode==='show'?'整部移动':'合入全部无冲突内容'));for(const op of b.operations){lines.push('移动：'+op.source+' → '+op.target);for(const f of op.manifest)if(!f.directory)lines.push('  文件：'+f.path+' · '+f.size+' · '+f.modified);}for(const f of b.cleanup?.discardFiles||[])lines.push('删除源重复共用资料：'+f.path+'；目标同名资料保留');if(b.cleanup)lines.push('全部核验通过后删除源目录：'+b.source);}
 if(p.kind==='repair'){lines.push('作品：'+b.task.name+' / Season '+b.task.season);for(const i of b.record.items)lines.push('第'+i.episode+'集；仅解除历史ID '+i.id,'下载源：'+i.source,'复制整理目标：'+i.target,'不删除源视频或旧目标文件，不进行全局重新整理');}
 return lines;
}
async function jobsMenu(){const jobs=await rpc('jobs');jobs.forEach((j,i)=>console.log((i+1)+' '+j.id+' '+(labels[j.stage]||j.stage)+' '+colored(labels[j.status]||j.status)));const a=await ask('任务编号，b返回：');if(a==='b')return;const j=jobs[Number(a)-1];if(!j)throw Error('编号无效');print('1 实时观看\n2 查看结果/路径\n3 暂停\n4 继续\n5 重新导出\nb 返回');const action=await ask('请选择：');if(action==='1')await watch(j.id);if(action==='2')completed(await rpc('job',{id:j.id}));if(action==='3')await rpc('pause',{id:j.id});if(action==='4'){await rpc('resume',{id:j.id});await watch(j.id);}if(action==='5')print(JSON.stringify(await rpc('export',{id:j.id}),null,2));}
async function reportsMenu(){print('1 查看任务报告与历史\n2 导入Excel/JSON作为重新检查范围\n3 设置报告保存路径\nb 返回');const a=await ask('请选择：');if(a==='1')await jobsMenu();if(a==='3')await outputSettings();if(a==='2'){const file=await ask('Ubuntu本机文件绝对路径：');const result=await rpc('import',{file});print(result.note+'\n'+result.scopes.join('\n'));if(await ask('1 重新初检；其他返回：')==='1')await start('inspect',{scopes:result.scopes});}}
export async function menu(){if(!process.stdin.isTTY){print('非交互终端请使用 tvflow status / doctor / export；不会自动确认写操作。');return;}
 while(true){const c=await rpc('config'),jobs=await rpc('jobs');print('\n剧集整理Linux版 v1.2.0\n当前源根：'+c.source+'\n当前工作流：'+(currentWorkflow||'未选择')+'\n正在运行：'+jobs.filter(j=>['running','queued'].includes(j.status)).length+'；暂停/受阻：'+jobs.filter(j=>['paused','failed'].includes(j.status)).length+'\n\n1 初检目录\n2 补缺下载与整理修复\n3 复核与版本清理\n4 归档\n5 任务与进度\n6 待处理事项\n7 报告与历史记录\n8 设置与连接诊断\n9 归档库复核（只读）\nq 退出界面，后台任务继续');
  const v=await ask('请选择：');if(v==='q')return;try{if(v==='1')await inspectMenu();if(v==='2')await stageMenu('download');if(v==='3')await stageMenu('review');if(v==='4')await stageMenu('archive');if(v==='5')await jobsMenu();if(v==='6'){const w=await chooseWorkflow();if(w)await showResults(w,true);}if(v==='7')await reportsMenu();if(v==='8')await settings();if(v==='9')await libraryMenu();}catch(e){console.log(paint(errorText(e),31));}
 }
}
