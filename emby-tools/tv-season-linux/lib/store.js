import fs from 'node:fs';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {home,id,now,clone} from './util.js';
export class Store{
 constructor(root=home()){
  fs.mkdirSync(root,{recursive:true,mode:0o700});this.db=new DatabaseSync(path.join(root,'state.sqlite'));
  this.db.exec('PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=5000; CREATE TABLE IF NOT EXISTS records(kind TEXT NOT NULL,key TEXT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(kind,key));');
 }
 get(k,id,fallback=null){const r=this.db.prepare('SELECT value FROM records WHERE kind=? AND key=?').get(k,id);return r?JSON.parse(r.value):clone(fallback);}
 put(k,id,v){if(k==='job'&&v.status==='running'&&this.get(k,id)?.pauseRequested)v.pauseRequested=true;this.db.prepare('INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,key) DO UPDATE SET value=excluded.value').run(k,id,JSON.stringify(v));return v;}
 all(k){return this.db.prepare('SELECT value FROM records WHERE kind=? ORDER BY rowid DESC').all(k).map(r=>JSON.parse(r.value));}
 createJob(stage,workflow,config,payload={}){const j={id:id('J'),stage,workflow,config,payload,status:'queued',index:0,total:null,current:'等待执行',createdAt:now(),updatedAt:now(),results:[],files:[],errors:[],events:[]};return this.put('job',j.id,j);}
 event(j,text){j.current=text;j.updatedAt=now();j.events.push({at:j.updatedAt,text});j.events=j.events.slice(-100);this.put('job',j.id,j);}
 recover(){for(const j of this.all('job'))if(['running','queued'].includes(j.status)){j.status='paused';j.current='服务重启：请查看记录后继续；外部写操作不会自动重发';j.updatedAt=now();this.put('job',j.id,j);}}
 close(){this.db.close();}
}
