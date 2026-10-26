import {I} from './cores.js';
import {now,parent,base} from './util.js';
import {inventory} from './archive-runner.js';
const video=/\.(mp4|mkv|avi|mov|m4v|ts|m2ts|wmv|flv|webm|mpg|mpeg)$/i;
const move=(f,source,target)=>({...f,path:target+f.path.slice(source.length)});
const attrs=f=>JSON.stringify([!!f.directory,f.directory?'':String(f.bytes||f.size),f.directory?'':String(f.rawTime||f.modified)]);
const values=x=>JSON.stringify([...(x||[])].sort((a,b)=>a-b));
// 从归档清单生成期望值，重新强制读取云盘；不调用移动、删除或下载。
export async function auditArchive(plan,seasons,cloud,{checkpoint=()=>{}}={}){
 const at=now(),result={schema:1,checkedAt:at,source:plan.source,target:plan.target,ok:false,differences:[],files:[],seasons:[]};
 const expected=plan.mode==='show'?plan.rawSource.map(f=>move(f,plan.source,plan.target)):
  [...plan.rawDestination,...plan.operations.flatMap(op=>plan.rawSource.filter(f=>f.path===op.source||f.path.startsWith(op.source+'/')).map(f=>move(f,op.source,op.target)))];
 let actual=[];
 try{
  checkpoint();
  if((await cloud.list(parent(plan.source))).some(f=>f.path===plan.source))result.differences.push('源作品目录仍存在');
  const target=(await cloud.list(parent(plan.target))).find(f=>f.path===plan.target&&f.directory);
  if(!target)throw Error('目标作品目录不存在');
  actual=await inventory(cloud,plan.target);checkpoint();
  const before=new Map(expected.map(f=>[f.path,f])),after=new Map(actual.map(f=>[f.path,f]));
  for(const p of new Set([...before.keys(),...after.keys()])){
   const e=before.get(p),a=after.get(p),state=!e?'目标新增':!a?'目标缺失':attrs(e)!==attrs(a)?'属性不一致':'一致';
   const row={path:p,relativePath:p.slice(plan.target.length+1),directory:!!(e||a).directory,state,expectedSize:e?.size||'',actualSize:a?.size||'',expectedModified:e?.modified||'',actualModified:a?.modified||''};
   result.files.push(row);if(state!=='一致')result.differences.push(state+'：'+p);
  }
  for(const s of seasons.filter(s=>s.season)){
   checkpoint();const targetPath=plan.target+s.path.slice(plan.source.length);
   const files=actual.filter(f=>parent(f.path)===targetPath),audit=I.auditSource(files,s.season,{...s.source,total:s.total});
   const expectedVideos=(s.snapshot||[]).filter(f=>!f.directory&&video.test(f.name)).length;
   const actualVideos=files.filter(f=>!f.directory&&video.test(f.name)).length;
   const differences=[];
   if(!actual.some(f=>f.path===targetPath&&f.directory))differences.push('目标季目录不存在');
   if(!Number.isSafeInteger(s.total)||s.total<=0||s.source?.total!==s.total)differences.push('报告来源集数无效或与来源记录不一致');
   if(audit.current!==s.current)differences.push('已识别集数不一致');
   if(values(audit.missing)!==values(s.missing)||audit.integrity!=='齐全')differences.push('目标集号不齐全或与报告不一致');
   if(actualVideos!==expectedVideos)differences.push('视频文件数不一致');
   const row={sourcePath:s.path,targetPath,name:s.name,season:s.season,checkedAt:at,expectedTotal:s.total,expectedEpisodes:s.current,actualEpisodes:audit.current,expectedVideos,actualVideos,missing:audit.missing,differences};
   row.ok=!differences.length;row.state=row.ok?'一致':'异常';result.seasons.push(row);
   for(const d of differences)result.differences.push(s.name+' / '+base(targetPath)+'：'+d);
  }
  // 两次完整读取保持一致，避免把核验期间变化的目录当成稳定结果。
  const again=await inventory(cloud,plan.target);
  const stable=rows=>JSON.stringify(rows.map(f=>[f.path,attrs(f)]).sort((a,b)=>a[0].localeCompare(b[0])));
  if(stable(actual)!==stable(again))result.differences.push('归档核验期间目标内容发生变化');
  if((await cloud.list(parent(plan.source))).some(f=>f.path===plan.source))result.differences.push('核验结束时源目录重新出现');
 }catch(e){if(e.name==='Pause')throw e;result.differences.push(String(e.message||'归档读取失败'));}
 result.ok=!result.differences.length&&result.seasons.length===seasons.filter(s=>s.season).length&&result.seasons.length>0;
 result.state=result.ok?'报告与云盘一致':'归档核验异常';
 return result;
}
