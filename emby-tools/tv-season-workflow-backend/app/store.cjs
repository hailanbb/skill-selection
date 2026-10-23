const {DatabaseSync}=require('node:sqlite');
const fs=require('node:fs'),path=require('node:path');
class Store{
 constructor(file){fs.mkdirSync(path.dirname(file),{recursive:true});this.db=new DatabaseSync(file);this.db.exec('PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; CREATE TABLE IF NOT EXISTS records (key TEXT PRIMARY KEY, value TEXT NOT NULL)');this.db.exec("UPDATE records SET value=json_set(value,'$.state','uncertain') WHERE (key LIKE 'plan:%' OR key LIKE 'job:%') AND json_extract(value,'$.state')='running'");}
 get(k){const r=this.db.prepare('SELECT value FROM records WHERE key=?').get(k);return r?JSON.parse(r.value):null;}
 set(k,v){this.db.prepare('INSERT INTO records VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value').run(k,JSON.stringify(v));}
 all(prefix){return this.db.prepare('SELECT value FROM records WHERE key LIKE ? ORDER BY rowid DESC').all(prefix+'%').map(r=>JSON.parse(r.value));}
 close(){this.db.close();}
}
module.exports=Store;
