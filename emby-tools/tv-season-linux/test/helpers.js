import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {Store} from '../lib/store.js';
import {Engine} from '../lib/workflow.js';
import {I} from '../lib/cores.js';
export function fixture(){
 const root=fs.mkdtempSync(path.join(process.env.TVFLOW_TEST_TMP||os.tmpdir(),'tvflow-test-')),name='测试动漫 (2025) [tmdbid=123]',source='/115/Library_incs/nas',destination='/115/archive';
 const config={schema:1,source,destination,cloud:{url:'http://cloud.invalid',token:'fake',transport:'grpc'},moviepilot:{url:'http://mp.invalid',token:'fake',auth:'apikey'},repair:{source:'/video/downloads',target:'/video/library'},outputs:{reports:path.join(root,'报告'),records:path.join(root,'记录'),logs:path.join(root,'日志')},sourceGapMs:45000};
 const show=source+'/动漫/日本动漫/'+name,season=show+'/Season 1';const tree=new Map(),calls=[];
 const file=(dir,n,directory=false)=>({name:n,path:dir+'/'+n,directory,size:directory?'':'100 B',bytes:directory?'':'100',modified:'2026-10-20 12:00:00'});
 function mkdir(p){if(tree.has(p))return;tree.set(p,[]);if(p!=='/'){const par=path.posix.dirname(p);mkdir(par);tree.get(par).push(file(par,path.posix.basename(p),true));}}
 mkdir(season);mkdir(destination+'/动漫/日本动漫');
 const video=n=>file(season,'测试动漫.S01E'+String(n).padStart(2,'0')+'.1080p.WEB-DL.x264-Group.mkv');tree.get(season).push(video(1),video(2));
 const cloud={list:async p=>{if(!tree.has(p))throw Error('目录读取失败');return structuredClone(tree.get(p));},remove:async files=>{calls.push(['delete',files.map(f=>f.path)]);for(const f of files)tree.set(path.posix.dirname(f.path),tree.get(path.posix.dirname(f.path)).filter(x=>x.path!==f.path));},removeSource:async p=>{if(tree.get(p)?.length)throw Error('not empty');calls.push(['rmdir',p]);tree.delete(p);const par=path.posix.dirname(p);tree.set(par,tree.get(par).filter(x=>x.path!==p));},move:async op=>{
  calls.push(['move',op.source,op.target]);const from=path.posix.dirname(op.source),to=path.posix.dirname(op.target),entry=tree.get(from).find(f=>f.path===op.source);if(!entry||tree.get(to).some(f=>f.path===op.target))throw Error('conflict');tree.set(from,tree.get(from).filter(f=>f.path!==op.source));tree.get(to).push({...entry,path:op.target,name:path.posix.basename(op.target)});
  for(const [p,rows] of [...tree])if(p===op.source||p.startsWith(op.source+'/')){tree.set(op.target+p.slice(op.source.length),rows.map(r=>({...r,path:op.target+r.path.slice(op.source.length)})));tree.delete(p);}
 },close(){}};
 const db={source:'douban',title:'测试动漫 (2025)',releaseYears:['2025'],aliases:[],tv:true,total:2,url:'https://movie.douban.com/subject/123/',broadcast:'已播完',checkedAt:new Date().toISOString()};
 const metadata={inspect:async(_show,season,files)=>({db:structuredClone(db),audit:I.auditSource(files,season,db)}),douban:async()=>structuredClone(db)};
 let active=[];const resource={media_info:{type:'电视剧',tmdb_id:123,title:'测试动漫',year:'2025'},meta_info:{begin_season:1,season_list:[1],episode_list:[2]},torrent_info:{site:1,site_name:'测试站',title:'测试动漫.S01E02.1080p.WEB-DL.x264-Group',enclosure:'https://invalid/?passkey=SECRET',seeders:8,size:100}};
 const mp={c:config.moviepilot,defaults:{baseURL:'http://mp.invalid/api/v1/'},active:async()=>structuredClone(active),get:async p=>{if(p==='download/')return structuredClone(active);if(p==='site/')return [{id:7,name:'天空'},{id:8,name:'观众'}];if(p.startsWith('search/'))return {success:true,data:[resource]};throw Error('unsupported '+p);},post:async(p,b)=>{calls.push(['submit',p]);return {success:true,data:{download_id:'download-id'}};}};
 const store=new Store(root),engine=new Engine(store,()=>config,{cloud,mp,metadata});
 return {root,config,show,season,tree,file,video,cloud,metadata,mp,store,engine,calls,db,name,setActive:a=>active=a,close:()=>{store.close();fs.rmSync(root,{recursive:true,force:true});}};
}
export async function inspect(f){const j=f.engine.create('inspect',{scopes:[f.config.source]});await f.engine.run(j);return f.store.get('job',j.id);}
