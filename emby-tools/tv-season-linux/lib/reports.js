import fs from 'node:fs';
import path from 'node:path';
import X from 'xlsx-js-style';
import {atomic,now,id,localPath,cloudPath,within,parent,base} from './util.js';
const columns=['作品','分类路径','季','季目录','状态','原因','来源集数','本地集数','缺集','播出状态','来源链接','核查时间'];
const colors={green:['C6EFCE','006100'],blue:['BDD7EE','1F4E78'],yellow:['FFFF00','000000'],red:['FFC7CE','9C0006'],archived:['E4DFEC','7030A0']};
function cell(v){if(v===null||v===undefined)return '';if(typeof v==='object')return JSON.stringify(v);return v;}
export function csv(rows){return '\ufeff'+rows.map(row=>row.map(v=>{let s=String(cell(v));if(/^[\s]*[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';}).join(',')).join('\r\n')+'\r\n';}
export function redact(value){if(Array.isArray(value))return value.map(redact);if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).filter(([k])=>!['token','password','cookie','authorization','enclosure','headers'].includes(k.toLowerCase())).map(([k,v])=>[k,redact(v)]));return value;}
export function statistics(rows){const out={总记录:rows.length};for(const r of rows){const state=r.state||r.status||'未确认';out[state]=(out[state]||0)+1;}return out;}
export function jobSummary(job){const summary=statistics(job.results||[]),downloads=new Map(),deletes=new Set(),moves=new Set();for(const r of job.results||[]){for(const d of r.records||[])downloads.set(d.id||d.key,d);for(const e of r.result?.records||[])if(e.state==='verified')deletes.add(e.path);for(const op of r.result?.operations||[])if(op.state==='verified')moves.add(op.source);}if(downloads.size){summary['本轮新提交资源']=[...downloads.values()].filter(d=>d.state==='accepted'&&d.at>=(job.startedAt||job.createdAt)).length;summary['已有或历史下载资源']=[...downloads.values()].filter(d=>d.state==='existing'||d.state==='accepted'&&d.at<(job.startedAt||job.createdAt)).length;summary['下载结果不明']=[...downloads.values()].filter(d=>['uncertain','submitting'].includes(d.state)).length;}if(deletes.size)summary['已验证删除文件']=deletes.size;if(moves.size)summary['已验证移动单元']=moves.size;return summary;}
export function exportJob(job,workflow,plans=[]){
 const results=redact(job.results),seasons=redact(workflow?.seasons||[]),reportDir=path.join(localPath(job.config.outputs.reports),job.id),recordDir=path.join(localPath(job.config.outputs.records),job.id);
 const stem=job.stage+'_'+job.id+'_'+now().replace(/[:.]/g,'-')+'_'+id('').slice(0,4),tables=[];
 tables.push(['任务统计',[['项目','值'],['任务',job.id],['工作流',job.workflow],['阶段',job.stage],['状态',job.status],['开始',job.startedAt||job.createdAt],['结束/快照',now()],['工作流作品数',new Set(seasons.map(s=>s.showPath)).size],['工作流季数',seasons.filter(s=>s.season).length],...Object.entries(jobSummary(job))]]);
 tables.push(['作品结果',[columns,...seasons.map(s=>[s.name,s.category,s.season,s.path,s.state,s.note,s.total,s.current,s.missing===null?'未确认':s.missing?.join('、'),s.broadcast,s.source?.url,s.checkedAt])]]);
 tables.push(['操作结果',[['对象','状态','说明','结果详情'],...results.map(r=>[r.name||r.path||'',r.state||'',r.note||'',JSON.stringify(r)])]]);
 const audit=[['阶段','对象','动作','状态','源路径或资源','目标路径或任务ID','时间','原因']];
 for(const entry of job.operationRecords||[]){const r=entry.record;
  if(entry.kind==='download')for(const d of r)audit.push(['补缺',entry.path,'下载',d.state,d.title,d.id,d.finishedAt||d.at,d.selectionReason]);
  if(entry.kind==='cleanup'){for(const d of [...r.history||[],...r.records||[],...(r.pending?.files||r.pending?[...(r.pending?.files||[r.pending])].map(f=>({...f,state:'pending'})):[])])audit.push(['清理',entry.path,'普通删除',d.state,d.path,'',d.finishedAt||d.at,d.reason||r.pending?.error]);}
  if(entry.kind==='archive'){for(const op of r.operations||[])for(const f of op.manifest||[])audit.push(['归档',entry.path,'移动',op.state,f.path,op.target+f.path.slice(op.source.length),op.finishedAt||op.at,op.error]);if(r.cleanup)for(const f of r.cleanup.manifest||[{path:r.source}])audit.push(['归档',entry.path,'源目录/共用资料清理',r.cleanup.state,f.path,'',r.cleanup.finishedAt||r.cleanup.at,r.cleanup.error||r.cleanup.reason]);}
  if(entry.kind==='repair')for(const i of r.items||[])for(const step of i.steps||[])audit.push(['修复',entry.path,step.action,step.state,i.source,i.target,step.finishedAt||step.at,step.error||i.note]);
 }
 if(audit.length>1)tables.push(['实际操作明细',audit]);
 const files=[];for(const p of plans){for(const f of p.body?.remove||[])files.push([p.id,'拟删除',f.path,'',f.reason]);for(const f of p.body?.keep||[])files.push([p.id,'保留',f.path,'','完整版本']);for(const op of p.body?.operations||[])for(const f of op.manifest||[])files.push([p.id,'拟移动',f.path,op.target+f.path.slice(op.source.length),'归档']);for(const f of p.body?.cleanup?.discardFiles||[])files.push([p.id,'拟删除源共用资料',f.path,'','目标版本保留']);}
 if(files.length)tables.push(['文件清单',[['计划','动作','源路径','目标路径','原因'],...files]]);
 const book=X.utils.book_new();for(const [name,rows] of tables){
  // JSON remains lossless when a single Excel cell cannot hold the entire diagnostic object.
  const display=rows.map(r=>r.map(v=>{v=cell(v);return typeof v==='string'&&v.length>30000?v.slice(0,29900)+'…（完整内容见JSON记录）':v;}));
  const sheet=X.utils.aoa_to_sheet(display);sheet['!cols']=rows[0].map(h=>({wch:/路径|目录|说明|原因|详情|链接/.test(h)?55:24}));sheet['!autofilter']={ref:X.utils.encode_range({r:0,c:0},{r:Math.max(0,rows.length-1),c:rows[0].length-1})};
  for(const [ref,c] of Object.entries(sheet))if(!ref.startsWith('!')){const head=/^[A-Z]+1$/.test(ref);c.s={font:{name:'Arial',sz:11,bold:head,color:{rgb:head?'FFFFFF':'243746'}},alignment:{vertical:'top',wrapText:true},...(head?{fill:{patternType:'solid',fgColor:{rgb:'24546A'}}}:{})};}
  if(name==='作品结果')seasons.forEach((s,i)=>{const c=sheet['A'+(i+2)],color=colors[s.color];if(c&&color){c.s.fill={patternType:'solid',fgColor:{rgb:color[0]}};c.s.font.color={rgb:color[1]};}});
  X.utils.book_append_sheet(book,sheet,name);
 }
 const outputs=[],errors=[];
 function save(file,data,verify){try{atomic(file,data);verify?.(fs.readFileSync(file));outputs.push(file);}catch(e){errors.push({file,error:e.message});}}
 save(path.join(recordDir,stem+'.json'),JSON.stringify({schema:'tvflow/1',exportedAt:now(),job:redact(job),workflow:redact(workflow),plans:redact(plans)},null,2)+'\n',b=>JSON.parse(b.toString('utf8')));
 save(path.join(reportDir,stem+'.xlsx'),Buffer.from(X.write(book,{type:'buffer',bookType:'xlsx',compression:true})),b=>{const r=X.read(b,{type:'buffer'});if(r.SheetNames.length!==tables.length)throw Error('Excel回读不一致');});
 for(const [name,rows] of tables)save(path.join(reportDir,stem+'_'+name+'.csv'),csv(rows),b=>new TextDecoder('utf-8',{fatal:true}).decode(b));
 if(job.logPath&&fs.existsSync(job.logPath))outputs.push(job.logPath);
 return {files:outputs,errors};
}
// Imports select scan scopes, never import executable requests or overwrite live journals.
export function importScopes(file,config){
 const bytes=fs.readFileSync(localPath(file));if(bytes.length>30*1024*1024)throw Error('导入文件超过30MB');let paths=[];
 if(/\.json$/i.test(file)){const d=JSON.parse(bytes.toString('utf8'));if(d.schema!=='tvflow/1'||!Array.isArray(d.workflow?.seasons))throw Error('不是本程序完整记录');paths=d.workflow.seasons.map(s=>s.showPath);}
 else if(/\.xlsx$/i.test(file)){const book=X.read(bytes,{type:'buffer',cellFormula:true});for(const sheet of Object.values(book.Sheets)){const rows=X.utils.sheet_to_json(sheet,{defval:''});for(const r of rows){let p=r['剧集目录路径'];if(!p&&r['季目录'])p=parent(String(r['季目录']));if(!p&&r['季目录路径'])p=parent(String(r['季目录路径']));if(p)paths.push(String(p));}}}
 else throw Error('请选择XLSX或本程序JSON；CSV不作为流程状态导入');
 paths=[...new Set(paths.map(cloudPath))];if(!paths.length||paths.some(p=>!within(p,config.source)||p===config.source))throw Error('没有位于当前源根内的有效作品路径');return paths;
}
