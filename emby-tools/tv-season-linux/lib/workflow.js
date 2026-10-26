import fs from 'node:fs';
import path from 'node:path';
import {I,K,D,R,T,A} from './cores.js';
import {Cloud,MoviePilot,Metadata} from './clients.js';
import {snapshot,hydrate} from './config.js';
import {id,now,digest,clone,cloudPath,parent,base,within,fingerprint,assertSame,Pause,errorText,writable} from './util.js';
import {exportJob} from './reports.js';
import {inventory,runArchive} from './archive-runner.js';
import {withExtraSites} from './search-sites.js';
import {auditArchive} from './archive-audit.js';
const media=/\.(mp4|mkv|avi|mov|m4v|ts|m2ts|wmv|flv|webm|mpg|mpeg|strm)$/i;
const seasonNo=n=>{const m=/^Season\s+(\d+)$/i.exec(n);return m?Number(m[1]):null;};
export const journalKey=(config,s)=>digest([config.cloud.url,s.path]);
export function task(s,config){return {key:journalKey(config,s),name:s.name,category:s.category,season:s.season,path:s.path,showPath:s.showPath,color:s.color,directoryOnly:!s.season,data:{...s.data,'来源登记集数':s.total??'','缺失集号':s.missing===null?'未确认':s.missing?.length?s.missing.join('、'):'无','播出状态':s.broadcast||'未确认','待播集号':s.future?.join('、')||'','播期未知集号':s.undated?.join('、')||'','TMDB ID':s.tmdb||'','豆瓣链接':s.source?.source==='douban'?s.source.url:'','版本文件清单':s.snapshot?JSON.stringify({schema:1,path:s.path,files:s.snapshot}):'','扫描时间':s.checkedAt||'','文件核查时间':s.checkedAt||'','整理修复记录':s.repair?JSON.stringify(s.repair):''}};}
export class Engine{
 constructor(store,getConfig,clients=null){this.store=store;this.getConfig=getConfig;this.clients=clients;this.active=null;}
 workflow(w){const v=this.store.get('workflow',w);if(!v)throw Error('工作流不存在');return v;}
 create(stage,{workflow,scopes,plan}={}){
  const config=this.getConfig();
  if(!['inspect','download','review','archive','archive-audit','repair','execute','reconcile'].includes(stage))throw Error('阶段无效');
  if(this.store.all('job').some(j=>['running','queued'].includes(j.status)))throw Error('已有任务运行中，请先完成或暂停，避免同目录并发');
  if(stage==='inspect'){
   if(!Array.isArray(scopes)||!scopes.length)throw Error('请选择检查目录');scopes=[...new Set(scopes.map(cloudPath))].filter((p,_i,all)=>!all.some(other=>other!==p&&within(p,other)));if(scopes.some(p=>!within(p,config.source)))throw Error('检查范围超出当前源根');
   workflow=id('W');this.store.put('workflow',workflow,{id:workflow,createdAt:now(),config:snapshot(config),scopes,seasons:[]});
  }else{const w=this.workflow(workflow);if(w.config.cloud.url!==config.cloud.url||w.config.moviepilot.url!==config.moviepilot.url||w.config.source!==config.source)throw Error('工作流连接/源根与当前设置不同，请恢复原设置或重新初检');}
  if(stage==='execute'){
   const p=this.store.get('plan',plan);if(!p||p.workflow!==workflow||p.status!=='approved'||p.approvedHash!==digest(p.body))throw Error('具体清单尚未确认或已变化');
   if(p.config.destination!==config.destination)throw Error('归档配置已变化，请重新生成计划');
   // Claims survive restart; a second task cannot execute a consumed approval.
   if(p.executionJob)throw Error('计划已有执行任务，请查看原任务或核实结果');
  }
  const j=this.store.createJob(stage,workflow,snapshot(config),{scopes,plan});if(plan){const p=this.store.get('plan',plan);p.executionJob=j.id;this.store.put('plan',plan,p);}return j;
 }
 approve(plan,hash){const p=this.store.get('plan',plan);if(!p||p.status!=='ready'||digest(p.body)!==hash)throw Error('计划已变化，请重新查看');p.status='approved';p.approvedHash=hash;p.approvedAt=now();this.store.put('plan',plan,p);return p;}
 pause(id){const j=this.store.get('job',id);if(!j)throw Error('任务不存在');if(j.status==='running'){j.pauseRequested=true;this.store.put('job',id,j);}else if(j.status==='queued'){j.status='paused';this.store.put('job',id,j);}return j;}
 resume(id){const j=this.store.get('job',id);if(!j||!['paused','failed'].includes(j.status))throw Error('任务不是可继续状态');if(this.store.all('job').some(x=>['running','queued'].includes(x.status)))throw Error('已有任务在运行');if(j.stage==='execute'){const p=this.store.get('plan',j.payload.plan);if(!p||p.status==='completed')throw Error('计划已完成或不存在');if(p.kind==='repair'&&R.pending(this.store.get('repair',p.body.task.key)))throw Error('修复已有操作记录，请先核实，不重发');p.status='approved';this.store.put('plan',p.id,p);}j.pauseRequested=false;j.status='queued';this.store.put('job',id,j);return j;}
 checkpoint(j){if(this.store.get('job',j.id)?.pauseRequested)throw new Pause();}
 event(j,text){text=errorText(text);this.store.event(j,text);if(j.logPath)fs.appendFileSync(j.logPath,now()+' '+text+'\n','utf8');}
 saveSeason(w,s){const at=w.seasons.findIndex(x=>x.path===s.path);if(at<0)w.seasons.push(s);else w.seasons[at]=s;this.store.put('workflow',w.id,w);}
 plan(j,w,kind,s,body){for(const old of this.store.all('plan'))if(old.kind===kind&&old.seasonPath===s?.path&&old.config.cloud.url===j.config.cloud.url&&!old.executionJob&&['ready','approved'].includes(old.status)){old.status='superseded';this.store.put('plan',old.id,old);}const p={id:id('P'),workflow:w.id,job:j.id,kind,seasonPath:s?.path,showPath:s?.showPath,config:j.config,body:clone(body),hash:digest(body),status:'ready',createdAt:now()};this.store.put('plan',p.id,p);return p;}
 blocked(config,s,ignoreArchive=false){const key=journalKey(config,s);const down=this.store.get('download',key,[]),clean=this.store.get('cleanup',key),repair=this.store.get('repair',key),archive=this.store.get('archive',digest([config.cloud.url,s.showPath]));return down.some(r=>['uncertain','submitting'].includes(r.state))||!!clean?.pending||R.pending(repair)||(!ignoreArchive&&(archive?.pending||archive?.incomplete||archive?.reportAudit?.pending||archive?.reportAudit?.ok===false));}
 async noActive(ctx,seasons){const active=await ctx.mp.active();if(!Array.isArray(active))throw Error('下载列表读取不完整，不能清理或归档');for(const s of seasons.filter(s=>s.season)){const t={...task(s,ctx.config),title:I.showInfo(s.name).title,year:I.showInfo(s.name).year,tmdb:s.tmdb,total:s.total||10000};if(active.some(a=>D.activeMatch(t,a,[])))throw Error('本作品仍有下载任务，请等待完成后复核');}}
 async run(j){
  if(this.active)throw Error('已有工作进程');this.active=j.id;let cloud;const w=this.workflow(j.workflow);j.status='running';j.startedAt||=now();j.errors=[];this.store.put('job',j.id,j);
  try{
   const config=hydrate(j.config,this.getConfig());const logDir=writable(path.join(config.outputs.logs,j.id));j.logPath=path.join(logDir,'task.log');
   cloud=this.clients?.cloud||new Cloud(config);const mp=this.clients?.mp||new MoviePilot(config);const metadata=this.clients?.metadata||new Metadata(mp,this.store,()=>this.checkpoint(j),text=>this.event(j,text));
   this.event(j,'任务开始：'+j.stage);
   const ctx={j,w,config,cloud,mp,metadata};
   if(j.stage==='inspect')await this.inspect(ctx);
   else if(j.stage==='execute')await this.execute(ctx);
   else if(j.stage==='archive')await this.archive(ctx);
   else if(j.stage==='archive-audit')await this.archiveAudit(ctx);
   else if(j.stage==='reconcile')await this.reconcile(ctx);
   else await this.seasons(ctx,j.stage);
   this.event(j,'本阶段已结束，正在自动生成报告');j.status=j.results.some(r=>r.state==='失败'||r.state==='待核实')?'completed-with-issues':'completed';
  }catch(e){j.errors.push(errorText(e));this.event(j,errorText(e));j.status=e.name==='Pause'?'paused':'failed';}
  finally{
   j.finishedAt=now();j.operationRecords=[];const collected=new Set();for(const s of w.seasons){for(const kind of ['download','cleanup','repair','archive']){const key=kind==='archive'?digest([j.config.cloud.url,s.showPath]):journalKey(j.config,s),unique=kind+key;if(collected.has(unique))continue;collected.add(unique);const record=this.store.get(kind,key);if(record)j.operationRecords.push({kind,path:kind==='archive'?s.showPath:s.path,record});}}
   try{const output=exportJob(j,w,this.store.all('plan').filter(p=>p.job===j.id||p.id===j.payload.plan));j.files=[...new Set([...(j.files||[]),...output.files])];j.exportErrors=output.errors;}catch(e){j.exportErrors=[{error:errorText(e)}];}
   j.pauseRequested=false;this.store.put('job',j.id,j);if(!this.clients)cloud?.close();this.active=null;
  }return j;
 }
 async discover(ctx){const {j,cloud,config}=ctx,shows=[],seen=new Set();let count=0;
  const walk=async(p,depth)=>{this.checkpoint(j);if(depth>8||++count>50000)throw Error('目录数量/深度过大，请缩小范围');if(seen.has(p))return;seen.add(p);this.event(j,'正在发现目录：'+p+'；已发现 '+shows.length+' 部');
   const rows=await cloud.list(p),dirs=rows.filter(r=>r.directory),seasons=dirs.filter(r=>seasonNo(r.name)!==null);
   if(seasons.length||rows.some(r=>!r.directory&&media.test(r.name))||/\[tmdbid=\d+\]|[（(](?:19|20)\d{2}[)）]/.test(base(p))){shows.push({path:p,rows});return;}
   for(const d of I.sortModified(dirs))await walk(d.path,depth+1);
  };
  for(const scope of j.payload.scopes){if(seasonNo(base(scope))!==null){const p=parent(scope);if(!within(p,config.source))throw Error('季目录超出范围');if(!seen.has(p)){seen.add(p);shows.push({path:p,rows:await cloud.list(p),only:[scope]});}}else await walk(scope,0);}
  j.payload.shows=shows.map(s=>({path:s.path,only:s.only}));j.total=shows.length;this.store.put('job',j.id,j);return shows;
 }
 async inspect(ctx){const {j,w,cloud,config}=ctx;if(!j.payload.shows)await this.discover(ctx);const shows=j.payload.shows;j.total=shows.length;
  for(;j.index<shows.length;j.index++){
   this.checkpoint(j);const show=shows[j.index];this.event(j,'读取作品：'+show.path);
   let rows;try{rows=await cloud.list(show.path);}catch(e){throw Error('目录读取失败，暂停当前作品：'+errorText(e));}
   const dirs=rows.filter(r=>r.directory&&seasonNo(r.name)>0&&(!show.only||show.only.includes(r.path)));
   const abnormal=rows.some(r=>r.directory&&!(seasonNo(r.name)>0)||!r.directory&&media.test(r.name));
   if(!dirs.length||abnormal){const s={path:show.path,showPath:show.path,name:base(show.path),category:path.posix.relative(config.source,parent(show.path)),season:null,state:'待核实',note:'存在未分季视频、特别篇、未知目录或没有标准Season季目录',color:'',checkedAt:now()};this.saveSeason(w,s);j.results.push({path:s.path,name:s.name,state:s.state,note:s.note});}
   for(const dir of I.sortModified(dirs)){this.checkpoint(j);const s={path:dir.path,showPath:show.path,name:base(show.path),category:path.posix.relative(config.source,parent(show.path)),season:seasonNo(dir.name)};
    try{await this.inspectSeason(ctx,s);this.saveSeason(w,s);j.results.push({path:s.path,name:s.name,state:s.state,note:s.note});}catch(e){if(e.name==='Pause')throw e;s.state='待核实';s.note=errorText(e);s.color='';s.checkedAt=now();this.saveSeason(w,s);j.results.push({path:s.path,name:s.name,state:s.state,note:s.note});}
   }
   this.store.put('job',j.id,{...j,index:j.index+1});
  }
 }
 async inspectSeason(ctx,s){const {cloud,metadata,j,config}=ctx;this.event(j,'检查 '+s.name+' / Season '+s.season);const files=await cloud.list(s.path);this.checkpoint(j);const show=I.showInfo(s.name);s.tmdb=show.tmdb;s.snapshot=files;s.fingerprint=fingerprint(files);s.checkedAt=now();
  const {db,audit}=await metadata.inspect(show,s.season,files);assertSame(files,await cloud.list(s.path));
  s.source=db;s.total=db.total??null;s.current=audit.current;s.missing=audit.missing;s.future=db.futureEpisodes||[];s.undated=db.undatedEpisodes||[];s.broadcast=db.broadcast||'未确认';s.data={};
  s.state=audit.integrity==='齐全'&&s.broadcast==='已播完'?'齐全':s.broadcast==='连载中'?'连载中':audit.integrity;s.note=[...(audit.issues||[]),db.error||'',db.broadcastEvidence||''].filter(Boolean).join('；');
  s.color=s.state==='齐全'?'green':s.broadcast==='连载中'?'blue':'';
  if(files.some(f=>/\.strm$/i.test(f.name))){s.state='待核实';s.color='';s.note+='；播放指针不作为可归档视频';}
  const key=journalKey(config,s);s.repair=this.store.get('repair',key);if(this.blocked(config,s)){s.state='待核实';s.color='yellow';s.note+='；存在未闭环操作记录';}
 }
 async seasons(ctx,stage){const {j,w,config,cloud,mp,metadata}=ctx;
  if(!j.payload.targets){j.payload.targets=w.seasons.filter(s=>s.season&&(stage!=='download'||!['green','archived'].includes(s.color))).map(s=>s.path);this.store.put('job',j.id,j);}j.total=j.payload.targets.length;
  for(;j.index<j.total;j.index++){
   this.checkpoint(j);const s=w.seasons.find(s=>s.path===j.payload.targets[j.index]);this.event(j,stage+'：'+s.name+' / S'+s.season);const key=journalKey(config,s);let result;
   try{
    if(stage==='download'){
     if(this.blocked(config,s))throw Error('存在未闭环操作，先核实，不能重复下载');
     await this.inspectSeason(ctx,s);const t=D.taskFromRow(task(s,config));
     ctx.searchApi??=withExtraSites(mp,{progress:t=>this.event(j,t)});
     const adapter=D.createAdapter(ctx.searchApi,mp.c.url);
     result=await D.processTask(t,{...adapter,submit:async resource=>{assertSame(s.snapshot,await cloud.list(s.path));return adapter.submit(resource);},load:k=>this.store.get('download',k,[]),save:(k,v)=>this.store.put('download',k,v),checkpoint:()=>this.checkpoint(j),progress:t=>this.event(j,t)});
     result.searchSites={defaults:true,additional:ctx.searchApi.selection()};
     s.color=result.color||s.color;s.state=result.state;s.note=result.note;s.download=result;
    }else if(stage==='review'){
     const rows=await cloud.list(s.path),db=await metadata.douban(I.showInfo(s.name),s.season,s.source?.source==='douban'?s.source.url:'');this.checkpoint(j);assertSame(rows,await cloud.list(s.path));
     await this.noActive(ctx,[s]);const t=task(s,config),body=K.plan(t,rows,db,id('C'));const repair=this.store.get('repair',key);s.repair=R.verify(repair,body.episodes,now());if(s.repair)this.store.put('repair',key,s.repair);
     s.total=db.total;s.current=body.current;s.missing=body.missing;s.snapshot=rows;s.fingerprint=fingerprint(rows);s.checkedAt=now();s.source=db;s.broadcast=body.confirmedEnded?'已播完':db.broadcast;
     if(this.blocked(config,s)){body.eligible=false;body.issues.push('存在未闭环操作，请先核实');body.state='待核实';}
     s.color=body.complete&&!body.remove.length&&body.confirmedEnded&&!this.blocked(config,s)?'green':'yellow';s.state=s.color==='green'?'齐全':body.state;s.note=body.issues.join('；');
     result={state:s.state,note:s.note,groups:body.groups,keep:body.keep,remove:body.remove};if(body.eligible){body.preciseSnapshot=rows;const p=this.plan(j,w,'cleanup',s,body);result.planId=p.id;}
    }else if(stage==='repair'){
     if(this.store.get('repair',key)&&R.pending(this.store.get('repair',key)))throw Error('已有修复记录，请先核实');
     // Refresh actual cloud files before using any historical missing-episode claim.
     await this.inspectSeason(ctx,s);const t=D.taskFromRow(task(s,config));t.records=this.store.get('download',key,[]);
     if(!config.repair.source||!config.repair.target)throw Error('请设置MoviePilot整理修复源/目标路径');
     const body=await T.check(t,T.adapter(mp,mp.c.url),config.repair,()=>this.checkpoint(j));result={state:body.state,note:body.note};if(body.state==='ready')result.planId=this.plan(j,w,'repair',s,{task:t,record:body}).id;
    }
   }catch(e){if(e.name==='Pause')throw e;result={state:'待核实',note:[errorText(e),stage==='download'?ctx.searchApi?.failure():''].filter(Boolean).join('；')};s.state='待核实';s.note=result.note;s.color='yellow';}
   this.saveSeason(w,s);j.results.push({path:s.path,name:s.name,...result});this.store.put('job',j.id,{...j,index:j.index+1});
  }
 }
 async archive(ctx){const {j,w,config,cloud}=ctx;if(!config.destination)throw Error('请先设置归档根目录');
  const groups=[...new Set(w.seasons.filter(s=>s.color==='green').map(s=>s.showPath))];j.total=groups.length;
  for(;j.index<groups.length;j.index++){this.checkpoint(j);const rows=w.seasons.filter(s=>s.showPath===groups[j.index]);this.event(j,'归档检查：'+rows[0].name);let result;
   try{if(rows.some(s=>this.blocked(config,s)))throw Error('本作品存在未闭环操作');await this.noActive(ctx,rows);
    const archive=A(config.source,config.destination);const native=rows.map(s=>task(s,config));
    // Upstream grouping assumes one category component: scope roots are adapted per actual parent.
    const context=this.archiveContext(config,rows[0]);const scoped=A(context.source,context.destination);const tasks=native.map(t=>({...t,category:context.category}));
    const body=await scoped.plan(tasks,p=>cloud.list(p),id('A'));body.rawSource=await inventory(cloud,body.source);body.rawDestination=body.mode==='seasons'?await inventory(cloud,body.target):[];if(!scoped.equal(body.manifest,body.rawSource)||!scoped.equal(body.destinationBefore,body.rawDestination))throw Error('生成归档清单期间目录变化');result={state:body.eligible?'待确认归档':'冲突暂缓',note:(body.skipped||[]).map(s=>s.reason+': '+s.source).join('；')};
    if(body.eligible)result.planId=this.plan(j,w,'archive',rows[0],{...body,context}).id;
   }catch(e){if(e.name==='Pause')throw e;result={state:'待核实',note:errorText(e)};}j.results.push({name:rows[0].name,path:groups[j.index],...result});this.store.put('job',j.id,{...j,index:j.index+1});
  }
 }
 archiveContext(config,s){const category=base(parent(s.showPath)),source=parent(parent(s.showPath));if(!within(source,config.source))throw Error('作品直接位于源根下，缺少可保留的分类层级；请选择其上级作为源根');const rel=path.posix.relative(config.source,source);return {source,destination:rel?config.destination+'/'+rel:config.destination,category};}
 async execute(ctx){const {j,w,config,cloud,mp,metadata}=ctx,p=this.store.get('plan',j.payload.plan);if(!p||p.approvedHash!==digest(p.body)||p.executionJob!==j.id||!['approved','executing'].includes(p.status))throw Error('执行清单未确认或已改变');const s=w.seasons.find(s=>s.path===p.seasonPath);p.status='executing';this.store.put('plan',p.id,p);j.total=1;
  try{let result;
   if(p.kind==='cleanup'){
    const key=journalKey(config,s),body=p.body;if(this.blocked(config,s)&&!this.store.get('cleanup',key))throw Error('本季存在其他未闭环操作');
    await this.noActive(ctx,[s]);const db=await metadata.douban(I.showInfo(s.name),s.season,body.source.url);if(db.total!==body.total||db.url!==body.source.url)throw Error('来源已变化，请重新复核');
    const precise=async()=>{const previous=this.store.get('cleanup',key);const done=new Set((previous?.planId===body.id?previous.records:[]).filter(r=>r.state==='verified').map(r=>r.path));assertSame(body.preciseSnapshot.filter(f=>!done.has(f.path)),await cloud.list(body.path));};await precise();
    result=await K.executeBatch(body,{list:p=>cloud.list(p),removeBatch:async(files,before)=>{await this.noActive(ctx,[s]);await precise();assertSame(before,await cloud.list(body.path));await cloud.remove(files);},load:k=>this.store.get('cleanup',k),save:(k,v)=>{this.store.put('cleanup',k,v);j.operationProgress={done:v.records.filter(r=>r.state==='verified').length,total:body.remove.length,unit:'文件'};this.store.put('job',j.id,j);},checkpoint:()=>this.checkpoint(j),progress:b=>this.event(j,'删除批次 '+b.count+' 个文件，等待结果核实')});
    const after=await cloud.list(s.path),verified=K.plan(task(s,config),after,db,id('C'));s.snapshot=after;s.fingerprint=fingerprint(after);s.current=verified.current;s.missing=verified.missing;s.color=verified.complete&&verified.confirmedEnded&&!verified.remove.length?'green':'yellow';s.state=s.color==='green'?'齐全':'清理已验证，待复核';result={...result,state:s.state};
   }else if(p.kind==='repair'){
    const key=journalKey(config,s),old=this.store.get('repair',key);if(old&&R.pending(old))throw Error('修复已提交或待核实，不能再次执行');
    result=await T.execute(p.body.task,p.body.record,T.adapter(mp,mp.c.url),config.repair,{save:r=>{this.store.put('repair',key,r);s.repair=r;this.saveSeason(w,s);},checkpoint:()=>this.checkpoint(j)});s.color='yellow';s.state='已提交整理，待文件复核';
   }else if(p.kind==='archive'){
    if(w.seasons.filter(x=>x.showPath===p.body.source).some(x=>this.blocked(config,x,true)))throw Error('本作品有未闭环下载、清理或修复');
    const a=A(p.body.context.source,p.body.context.destination),key=digest([config.cloud.url,p.body.source]);
    if(!this.store.get('archive',key)){const rows=w.seasons.filter(x=>x.showPath===p.body.source).map(x=>({...task(x,config),category:p.body.context.category}));const fresh=await a.plan(rows,p=>cloud.list(p),p.body.id);if(!a.equal(fresh.manifest,p.body.manifest)||!a.equal(fresh.destinationBefore,p.body.destinationBefore)||digest(fresh.operations)!==digest(p.body.operations))throw Error('当前归档条件与确认清单不同，请重新检查');}
    result=await runArchive(p.body,{core:a,cloud,load:()=>this.store.get('archive',key),save:v=>{this.store.put('archive',key,v);j.operationProgress={done:(v.operations||[]).filter(o=>o.state==='verified').length+(v.cleanup?.state==='verified'?1:0),total:p.body.operations.length+(p.body.cleanup?1:0),unit:'移动/源清理单元'};this.store.put('job',j.id,j);},checkpoint:()=>this.checkpoint(j),progress:t=>this.event(j,t),noActive:()=>this.noActive(ctx,w.seasons.filter(x=>x.showPath===p.body.source))});
    const audit=await this.auditPlan(ctx,p,result);result={...result,reportAudit:audit,state:audit.ok?'已归档':'待核实'};
   }else throw Error('未知计划类型');
   if(s)this.saveSeason(w,s);this.store.put('workflow',w.id,w);j.results.push({name:s?.name||p.body.name,state:result.state||'已验证',result});j.index=1;p.status='completed';this.store.put('plan',p.id,p);
  }catch(e){p.status=e.name==='Pause'?'approved':'uncertain';p.error=errorText(e);this.store.put('plan',p.id,p);throw e;}
 }
 async auditPlan(ctx,p,journal){
  const {w,j,cloud,config}=ctx,rows=w.seasons.filter(s=>s.showPath===p.body.source),key=digest([config.cloud.url,p.body.source]);
  journal={...journal,reportAudit:{pending:true,checkedAt:now()}};this.store.put('archive',key,journal);
  for(const row of rows){row.color='yellow';row.state='归档已移动，报告待核验';row.archive=journal;row.archiveAudit={sourcePath:row.path,targetPath:p.body.target+row.path.slice(p.body.source.length),pending:true,checkedAt:now(),state:'待核验',expectedTotal:row.total,expectedEpisodes:row.current};}this.store.put('workflow',w.id,w);
  this.event(j,'归档报告对照云盘：'+p.body.target);
  const audit=await auditArchive(p.body,rows,cloud,{checkpoint:()=>this.checkpoint(j)});
  journal.reportAudit=audit;this.store.put('archive',key,journal);
  for(const row of rows){row.archive=journal;row.archiveAudit={...(audit.seasons.find(s=>s.sourcePath===row.path)||{sourcePath:row.path,targetPath:p.body.target+row.path.slice(p.body.source.length)}),ok:audit.ok,checkedAt:audit.checkedAt,state:audit.state,differences:audit.differences};row.color=audit.ok?'archived':'red';row.state=audit.ok?'已归档':'归档核验异常';row.note=audit.ok?'归档报告与CloudDrive2一致；源目录已移除':audit.differences.join('；');}
  this.store.put('workflow',w.id,w);return audit;
 }
 async archiveAudit(ctx){
  const {j,w,config}=ctx,shows=[...new Set(w.seasons.filter(s=>this.store.get('archive',digest([config.cloud.url,s.showPath]))).map(s=>s.showPath))];j.total=shows.length;
  if(!shows.length)throw Error('当前工作流没有可复核的归档记录');
  for(;j.index<shows.length;j.index++){
   this.checkpoint(j);const source=shows[j.index],journal=this.store.get('archive',digest([config.cloud.url,source]));
   const p=this.store.all('plan').find(p=>p.kind==='archive'&&p.body.source===source&&p.body.id===journal.id&&p.workflow===w.id);
   let result;try{if(!p)throw Error('缺少对应归档清单，无法验证报告');if(!journal.verified||journal.pending||journal.incomplete)throw Error('归档操作尚未闭环，请先核实上次结果');const audit=await this.auditPlan(ctx,p,journal);result={state:audit.ok?'报告与云盘一致':'待核实',audit};}
   catch(e){if(e.name==='Pause')throw e;result={state:'待核实',note:errorText(e)};for(const row of w.seasons.filter(s=>s.showPath===source)){row.color='red';row.state='归档核验异常';row.note=result.note;row.archiveAudit={...row.archiveAudit,sourcePath:row.path,targetPath:journal.target+row.path.slice(source.length),state:'归档核验异常',checkedAt:now(),ok:false,differences:[result.note]};}this.store.put('workflow',w.id,w);}
   j.results.push({path:source,...result});this.store.put('job',j.id,{...j,index:j.index+1});
  }
 }
 async reconcile(ctx){const {j,w,config,cloud,mp}=ctx;j.total=w.seasons.length;
  for(;j.index<w.seasons.length;j.index++){this.checkpoint(j);const s=w.seasons[j.index],key=journalKey(config,s);let result={state:'无待核实操作'};
   try{const clean=this.store.get('cleanup',key);if(clean?.pending){const pending=clean.pending,files=pending.files||[pending],rows=await cloud.list(s.path),gone=files.filter(f=>!rows.some(r=>r.path===f.path));if(gone.length!==files.length)throw Error('部分待删文件仍存在，保留待核实；不会再次删除');const removed=new Set([...(clean.records||[]).filter(r=>r.batchId===pending.batchId&&r.state==='verified').map(r=>r.path),...gone.map(r=>r.path)]);if(!pending.beforeSnapshot)throw Error('缺少完整快照，无法自动核实');assertSame(pending.beforeSnapshot.filter(f=>!removed.has(f.path)),rows);clean.records.push(...files.map(f=>({...f,state:'verified',finishedAt:now()})));clean.pending=null;this.store.put('cleanup',key,clean);result={state:'删除已核实，请重新复核'};}
    const repair=this.store.get('repair',key);if(repair&&R.uncertain(repair)){const r=await T.reconcile(D.taskFromRow(task(s,config)),repair,T.adapter(mp,mp.c.url),config.repair,()=>this.checkpoint(j));this.store.put('repair',key,r);s.repair=r;result={state:'修复请求已核实，待文件复核'};}
    const down=this.store.get('download',key,[]);if(down.some(r=>['uncertain','submitting'].includes(r.state))){const active=await mp.active();if(!Array.isArray(active))throw Error('下载列表不完整');for(const r of down.filter(r=>['uncertain','submitting'].includes(r.state))){const matches=active.filter(t=>t.title===r.title&&t.site_name===r.site&&t.hash&&D.activeMatch(D.taskFromRow(task(s,config)),t,[]));if(matches.length!==1)throw Error('没有唯一匹配的活动任务，仍待核实，不解除防重');r.state='existing';r.id=matches[0].hash;r.finishedAt=now();}this.store.put('download',key,down);result={state:'已有下载已核实，待复核文件'};}
    const ak=digest([config.cloud.url,s.showPath]),ar=this.store.get('archive',ak);if(ar?.pending||ar?.incomplete||ar?.reportAudit?.pending){const plan=this.store.all('plan').find(p=>p.kind==='archive'&&p.body.source===s.showPath&&p.workflow===w.id);if(!plan)throw Error('缺少原归档计划');const a=A(plan.body.context.source,plan.body.context.destination),r=await runArchive(plan.body,{core:a,cloud,load:()=>ar,save:v=>this.store.put('archive',ak,v),verifyOnly:true});const audit=r.verified?await this.auditPlan(ctx,plan,r):null;result={state:audit?.ok?'归档已核实':r.verified?'待核实':r.state};}
   }catch(e){if(e.name==='Pause')throw e;result={state:'待核实',note:errorText(e)};}
   this.saveSeason(w,s);j.results.push({name:s.name,path:s.path,...result});this.store.put('job',j.id,{...j,index:j.index+1});
  }
 }
}
