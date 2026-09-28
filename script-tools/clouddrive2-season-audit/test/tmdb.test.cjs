const {test}=require('node:test');
const assert=require('node:assert/strict');
const C=require('../season-audit.user.js');
const show={title:'示例剧',year:'2025',tmdb:'123'};
const series={id:123,name:'示例剧',status:'Ended',seasons:[{season_number:1,episode_count:2}]};
const data={season_number:1,episodes:[{season_number:1,episode_number:1,air_date:'2025-01-01',episode_type:'standard'},{season_number:1,episode_number:2,air_date:'2025-01-02',episode_type:'standard'}]};
const date='2026-09-28T00:00:00.000Z';
test('TMDB 使用 ID 和季号读取明确集目，独立于中文剧名匹配',()=>{
  const r=C.parseTmdbSeason(series,data,show,1,date);
  assert.equal(r.total,2);assert.equal(r.source,'tmdb');assert.equal(r.completionConfirmed,true);
  assert.deepEqual(r.registeredEpisodes,[1,2]);
});
test('未来或日期未知的集目不能判为全季完结',()=>{
  const r=C.parseTmdbSeason(series,{...data,episodes:[data.episodes[0],{...data.episodes[1],air_date:'2026-10-01'}]},show,1,date);
  assert.equal(r.completionConfirmed,false);assert.deepEqual(r.futureEpisodes,[2]);
  const unknown=C.parseTmdbSeason(series,{...data,episodes:[data.episodes[0],{...data.episodes[1],air_date:null}]},show,1,date);
  assert.equal(unknown.completionConfirmed,false);assert.deepEqual(unknown.undatedEpisodes,[2]);
});
test('仍在连载且无季终标记不把当前集数当作最终总数',()=>{
  assert.equal(C.parseTmdbSeason({...series,status:'Returning Series'},data,show,1,date).completionConfirmed,false);
  assert.equal(C.parseTmdbSeason({...series,status:'Returning Series'},{...data,episodes:[data.episodes[0],{...data.episodes[1],episode_type:'finale'}]},show,1,date).completionConfirmed,true);
});
test('错剧、错季、空集目、重复编号、数量不一致都触发备用条件',()=>{
  for(const [s,d] of [[{...series,id:456},data],[series,{...data,season_number:2}],[series,{...data,episodes:[]}],[series,{...data,episodes:[data.episodes[0],data.episodes[0]]}],[{...series,seasons:[{season_number:1,episode_count:3}]},data]])assert.throws(()=>C.parseTmdbSeason(s,d,show,1,date));
});
test('TMDB 成功不调用豆瓣；失败才调用且记录具体原因',async()=>{
  let calls=0;
  const good=await C.preferTmdb(async()=>({source:'tmdb',total:2}),async()=>{calls++;return {total:9};});
  assert.equal(good.source,'tmdb');assert.equal(calls,0);
  const fallback=await C.preferTmdb(async()=>{throw new Error('TMDB HTTP 404');},async()=>{calls++;return {total:9};});
  assert.equal(calls,1);assert.equal(fallback.source,'douban');assert.match(fallback.fallbackReason,/404/);
});
test('用户暂停不触发豆瓣备用',async()=>{
  let calls=0;
  await assert.rejects(()=>C.preferTmdb(async()=>{const e=new Error('暂停');e.name='Paused';throw e;},async()=>{calls++;}),/暂停/);
  assert.equal(calls,0);
});
test('读令牌优先在 Header 发送，API 密钥仅用于密钥模式',()=>{
  const c={token:'TEST_TOKEN',key:'TEST_KEY'};
  const token=C.tmdbRequestSpec('/tv/123/season/1',c);
  assert.equal(token.headers.Authorization,'Bearer TEST_TOKEN');assert.ok(!token.url.includes('TEST_TOKEN'));assert.ok(!token.url.includes('TEST_KEY'));
  const key=C.tmdbRequestSpec('/tv/123',c,true);
  assert.equal(key.headers.Authorization,undefined);assert.equal(new URL(key.url).searchParams.get('api_key'),'TEST_KEY');
  assert.throws(()=>C.tmdbRequestSpec('https://unrelated.example/',c));
  assert.throws(()=>C.tmdbRequestSpec('/tv/123',{}));
});
test('本轮 TMDB 结果和来源链接不携带凭据或无关字段',()=>{
  const reply=C.parseTmdbSeason({...series,api_key:'TEST_SECRET'},data,show,1,date);
  assert.ok(!JSON.stringify(reply).includes('TEST_SECRET'));
  assert.equal(reply.url,'https://www.themoviedb.org/tv/123/season/1');
  const csv=C.resultCsv([{...reply,sourceUrl:reply.url,token:'TEST_SECRET'}]);
  assert.ok(!csv.includes('TEST_SECRET'));
});
