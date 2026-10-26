import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import X from 'xlsx-js-style';
import {fixture} from './helpers.js';
import {inspectLibrary,libraryRoot} from '../lib/library-audit.js';
import {importScopes} from '../lib/reports.js';
const db={source:'tmdb',total:2,broadcast:'已播完'};
const video=(n,group='A',copy=false)=>{const name='测试动漫.S01E0'+n+'.1080p.WEB-DL.x264-'+group+(copy?' - 副本':'')+'.mkv';return {name,path:'/archive/剧/Season 1/'+name,directory:false,size:'100 B',modified:'2026-10-20 12:00:00'};};
function library(f,category='动漫/日本动漫'){
 const root='/115/Library_incs/nas.finish';f.config.libraryRoot=root;
 const mkdir=p=>{if(f.tree.has(p))return;f.tree.set(p,[]);if(p!=='/'){const par=path.posix.dirname(p);mkdir(par);f.tree.get(par).push(f.file(par,path.posix.basename(p),true));}};
 const show=root+'/'+category+'/'+f.name,season=show+'/Season 1';mkdir(season);f.tree.get(season).push(...[video(1),video(2)].map(v=>({...v,path:season+'/'+v.name})));return {root,show,season,mkdir};
}
test('独立完整、多完整版本、混版拼齐、不完整版本混存及重复副本分别判断',()=>{
 const cases=[[[video(1),video(2)],'齐全','green'],[[video(1),video(2),video(1,'B'),video(2,'B')],'多个完整版本','yellow'],[[video(1),video(2,'B')],'混版拼齐','yellow'],[[video(1),video(2),video(1,'B')],'完整版本夹杂其他版本','yellow'],[[video(1),video(1,'B')],'多版本且未收齐','yellow'],[[video(1),video(2),video(1,'A',true)],'同版本重复副本','yellow'],[[video(1),video(2),video(1,'A',true),video(2,'A',true)],'多套完整副本','yellow']];
 for(const [files,state,color] of cases){const r=inspectLibrary(files,1,db);assert.equal(r.state,state);assert.equal(r.color,color);assert.ok(!('remove' in r));assert.ok(!('eligible' in r));}
});
test('空季记录0/0，待播不算已播缺集，零字节/未知模板/STRM不能判齐全',()=>{
 const empty=inspectLibrary([],1,db);assert.equal(empty.videoCount,0);assert.equal(empty.current,0);assert.deepEqual(empty.missing,[1,2]);assert.equal(empty.color,'red');
 const future=inspectLibrary([video(1)],1,{...db,broadcast:'连载中',futureEpisodes:[2]});assert.deepEqual(future.missing,[]);assert.deepEqual(future.uncollected,[2]);assert.equal(future.color,'blue');
 for(const bad of [[video(1),{...video(2),size:'0 B'}],[video(1),{...video(2),modified:''}],[{...video(1),name:'未知视频.mkv'}],[{...video(1),name:'指针.S01E01.strm'}]])assert.equal(inspectLibrary(bad,1,db).color,'yellow');
 const pointer=inspectLibrary([{...video(1),name:'指针.S01E01.strm'}],1,db);assert.equal(pointer.videoCount,0);assert.equal(pointer.current,0);
});
test('来源失败仍保留多个版本线索，不编造来源集数或独立完整版本',()=>{
 const r=inspectLibrary([video(1),video(2,'B')],1,{error:'来源不可用'});assert.equal(r.versionCount,2);assert.equal(r.total,null);assert.equal(r.completeVersionCount,0);assert.equal(r.color,'yellow');assert.equal(r.missing,null);
});
test('归档库电视剧/动漫目录独立只读复核，自动导出版本与文件明细，禁止进入整理阶段',async()=>{
 for(const category of ['电视剧/韩国剧集','动漫/日本动漫']){const f=fixture();try{const a=library(f,category),source=f.config.source;
  const j=f.engine.create('library-audit',{scopes:[a.root]});await f.engine.run(j);const done=f.store.get('job',j.id),w=f.engine.workflow(j.workflow);assert.equal(done.status,'completed',JSON.stringify(done.errors));assert.equal(done.exportErrors.length,0,JSON.stringify(done.exportErrors));assert.equal(w.kind,'library-audit');assert.equal(w.auditRoot,a.root);assert.equal(w.seasons[0].path,a.season);assert.equal(w.seasons[0].color,'green');assert.equal(f.config.source,source);assert.equal(f.calls.length,0);assert.equal(f.store.all('plan').length,0);
  const book=X.read(fs.readFileSync(done.files.find(p=>p.endsWith('.xlsx'))),{type:'buffer'});for(const name of ['归档库复核','库版本明细','库文件明细'])assert.ok(book.Sheets[name]);const row=X.utils.sheet_to_json(book.Sheets['归档库复核'])[0];assert.equal(row['实体视频数'],2);assert.equal(row['完整版本组数'],1);assert.equal(row['季或作品目录'],a.season);
  for(const stage of ['download','review','archive','archive-audit','repair','execute','reconcile'])assert.throws(()=>f.engine.create(stage,{workflow:w.id}),/只读工作流/);
  for(const file of done.files.filter(p=>/\.(xlsx|json)$/.test(p)))assert.throws(()=>importScopes(file,{...f.config,source:a.root}),/只读结果/);
 }finally{f.close();}}
});
test('禁止源目录或相邻前缀越界；未知来源仍完成文件分组；单个坏目录不阻塞其他作品',async()=>{
 const f=fixture();try{const a=library(f);for(const scope of [f.show,a.root+'-other/动漫'])assert.throws(()=>f.engine.create('library-audit',{scopes:[scope]}),/超出归档库/);
  const broken=path.posix.dirname(a.show)+'/无法读取 (2025) [tmdbid=999]';a.mkdir(broken);const old=f.cloud.list;f.cloud.list=async p=>{if(p===broken)throw Error('not found');return old(p);};f.metadata.inspect=async()=>{throw Error('来源暂不可用');};
  const j=f.engine.create('library-audit',{scopes:[a.root]});await f.engine.run(j);const w=f.engine.workflow(j.workflow);assert.equal(f.store.get('job',j.id).status,'completed-with-issues');assert.equal(w.seasons.find(s=>s.path===a.season).library.versionCount,1);assert.ok(w.seasons.some(s=>s.path===broken&&s.note.includes('目录读取失败')));assert.equal(f.calls.length,0);
 }finally{f.close();}
});
test('批量季选择不漏季，同季多个目录标记人工核实，暂停后继续保留原归档库范围',async()=>{
 const f=fixture();try{const a=library(f),second=a.show+'/Season 2';a.mkdir(second);f.tree.get(second).push(...[1,2].map(n=>{const v=video(n);return {...v,name:v.name.replace('S01','S02'),path:second+'/'+v.name.replace('S01','S02')};}));
  const j=f.engine.create('library-audit',{scopes:[a.season,second]});const list=f.cloud.list;let pause=true;f.cloud.list=async p=>{if(pause&&p===second){pause=false;f.engine.pause(j.id);}return list(p);};await f.engine.run(j);assert.equal(f.store.get('job',j.id).status,'paused');f.config.libraryRoot='/115/changed';await f.engine.run(f.engine.resume(j.id));const w=f.engine.workflow(j.workflow);assert.equal(w.auditRoot,a.root);assert.equal(w.seasons.filter(s=>s.season).length,2);assert.equal(f.store.get('job',j.id).results.length,2);assert.equal(f.calls.length,0);
  f.config.libraryRoot=a.root;const same=a.show+'/Season 01';a.mkdir(same);f.tree.get(same).push(...f.tree.get(a.season).map(v=>({...v,path:same+'/'+v.name})));const j2=f.engine.create('library-audit',{scopes:[a.show]});await f.engine.run(j2);const rows=f.engine.workflow(j2.workflow).seasons.filter(s=>s.season===1);assert.equal(rows.length,2);assert.ok(rows.every(s=>s.color==='yellow'&&s.note.includes('多个目录')));
 }finally{f.close();}
});
test('只读工作流即使伪造阶段并直接执行，也在任何云盘访问前被阻止',async()=>{
 const f=fixture();try{const a=library(f),j=f.engine.create('library-audit',{scopes:[a.root]});j.stage='download';f.store.put('job',j.id,j);let reads=0;f.cloud.list=async()=>{reads++;throw Error('不应读取');};await f.engine.run(j);assert.equal(reads,0);assert.equal(f.calls.length,0);assert.equal(f.store.get('job',j.id).status,'failed');assert.ok(f.store.get('job',j.id).errors[0].includes('只读任务'));}finally{f.close();}
});
test('归档库根范围必须明确，不允许云盘根或路径穿越；不强迫修改工作源根',()=>{
 assert.equal(libraryRoot({source:'/source',destination:'/archive'}),'/archive');assert.equal(libraryRoot({source:'/archive',libraryRoot:'/archive'}),'/archive');assert.throws(()=>libraryRoot({libraryRoot:'/'}));assert.throws(()=>libraryRoot({libraryRoot:'/archive/../source'}));
});
