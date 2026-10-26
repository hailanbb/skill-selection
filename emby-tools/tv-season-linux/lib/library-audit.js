import {I,K} from './cores.js';
import {cloudPath} from './util.js';
const unique=a=>[...new Set(a)].sort((a,b)=>a-b);
const range=n=>Array.from({length:n},(_,i)=>i+1);
export function libraryRoot(config){const root=cloudPath(config.libraryRoot||config.destination||'/115/Library_incs/nas.finish');if(root==='/')throw Error('归档库复核根不能是云盘根目录');return root;}

// 归档库只读判断：复用初检集号及第三阶段版本模板，不生成任何可执行清理清单。
export function inspectLibrary(files,season,source={}){
 if(files.length>10000)throw Error('本季条目超过10000，请人工缩小检查范围');
 const audit=I.auditSource(files.filter(f=>!/\.strm$/i.test(f.name)),season,source),total=Number.isInteger(source.total)&&source.total>0&&source.total<=10000?source.total:null;
 const groups=new Map(),evidence=[],issues=[...audit.issues],videos=files.filter(f=>!f.directory&&K.MEDIA.test(f.name));
 for(const f of videos){
  const p=K.versionOf(f,season),episode=I.episodeFromName(f.name,season),problems=[];
  if(!p)problems.push('集号或版本模板无法确认');
  if(/\.strm$/i.test(f.name))problems.push('播放指针，不作为实体视频完整性依据');
  if(!/^\d+(?:\.\d+)?\s*(?:B|KB|MB|GB|TB|KiB|MiB|GiB|TiB)$/i.test(f.size||'')||parseFloat(f.size)<=0)problems.push('视频大小为零或未知');
  if(!Number.isFinite(I.modifiedTime(f.modified)))problems.push('云盘修改时间无效');
  if(total&&episode>total)problems.push('集号超出来源范围');
  const row={path:f.path,name:f.name,kind:'video',episode:episode||null,version:p?.label||'未确认',versionKey:p?.key||'',size:f.size,modified:f.modified,issues:problems};evidence.push(row);
  if(p){if(!groups.has(p.key))groups.set(p.key,{key:p.key,label:p.label,episodes:[],files:[],latestModified:'',latestTime:-Infinity});const g=groups.get(p.key);g.files.push(row);g.episodes.push(p.episode);if(p.time>g.latestTime){g.latestTime=p.time;g.latestModified=f.modified;}}
  for(const problem of problems)issues.push(problem+'：'+f.name);
 }
 const all=[...groups.values()].map(g=>{const episodes=unique(g.episodes),missing=total?range(total).filter(n=>!episodes.includes(n)):null;
  const fullCopies=total?Math.min(...range(total).map(n=>g.files.filter(f=>f.episode===n&&!f.issues.length).length)):null;
  return {key:g.key,label:g.label,episodes,missing,duplicates:episodes.filter(n=>g.files.filter(f=>f.episode===n).length>1),complete:total?missing.length===0&&g.files.every(f=>!f.issues.length):null,fullCopies,latestModified:g.latestModified,files:g.files.map(f=>f.path)};
 });
 for(const f of files.filter(f=>!f.directory&&K.SCRAPE.test(f.name))){const owners=K.sidecarOwners(f,videos);evidence.push({path:f.path,name:f.name,kind:'scrape',size:f.size,modified:f.modified,owners:owners.map(v=>v.path),ownership:owners.length===1?'唯一对应视频':owners.length>1?'对应多个视频，需核实':'共用或归属未确认'});}
 const complete=all.filter(g=>g.complete),unknown=evidence.filter(f=>f.kind==='video'&&f.issues.length).map(f=>f.name);
 const multiple=all.length>1,mixed=multiple&&!complete.length&&total&&audit.uncollected?.length===0&&unknown.length===0;
 const repeatedSets=all.some(g=>g.fullCopies>1),problems=unknown.length||files.some(f=>f.directory||/\.(part|tmp|download|crdownload|!qb)$/i.test(f.name));
 let state='待核实',color='yellow';
 if(source.error)issues.push(source.error);
 if(files.some(f=>/\.(part|tmp|download|crdownload|!qb)$/i.test(f.name)))issues.push('存在下载临时文件');
 if(complete.length>1){state='多个完整版本';issues.push('多个独立文件组均齐全，需要人工判断');}
 else if(repeatedSets){state='多套完整副本';issues.push('同一模板存在至少两套完整副本');}
 else if(mixed){state='混版拼齐';issues.push('合并集号虽齐全，但没有一个独立版本完整');}
 else if(multiple){state=complete.length?'完整版本夹杂其他版本':total?'多版本且未收齐':'多版本，来源集数未确认';issues.push('检测到多个文件名版本模板，未自动选择或清理');}
 else if(audit.duplicates.length){state=unknown.length?'重复集号，版本待核实':'同版本重复副本';}
 else if(problems||!total||source.error){state='待核实';}
 else if(audit.missing?.length){state=source.broadcast==='已播完'?'缺集':audit.airedMissing?.length?'已播缺集':'未收齐，播期待核实';color=state==='未收齐，播期待核实'?'yellow':'red';}
 else if(source.broadcast==='连载中'||source.broadcast==='待播'){state=source.broadcast==='待播'?'待播':'连载中，已播部分齐全';color='blue';}
 else if(complete.length===1&&source.broadcast==='已播完'){state='齐全';color='green';}
 else{state='集号齐全，播出状态待核实';}
 const videoCount=videos.filter(f=>!/\.strm$/i.test(f.name)).length;
 if(!videoCount)issues.push('本季没有实体视频，视频文件数和已识别集数记录为0');
 return {schema:1,state,color,total,videoCount,current:audit.current,missing:audit.missing,uncollected:audit.uncollected,airedMissing:audit.airedMissing,duplicates:audit.duplicates,unknown,extra:audit.extra,versionCount:all.length,completeVersionCount:complete.length,mixed:!!mixed,multiple,repeatedSets,groups:all,files:evidence,issues:[...new Set(issues)]};
}
