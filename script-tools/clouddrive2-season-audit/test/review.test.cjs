const {test}=require('node:test');
const assert=require('node:assert/strict');
const C=require('../season-audit.user.js');
const files=[1,2].map(n=>({name:`S01E0${n}.mkv`,directory:false}));
const tmdb={source:'tmdb',total:3,completionConfirmed:true,url:'https://www.themoviedb.org/tv/123/season/1'};
const douban={total:2,url:'https://movie.douban.com/subject/123/',title:'测试剧'};

test('TMDB 缺集经豆瓣复核可变为齐全，最终来源和总数替换为豆瓣',async()=>{
  let calls=0;
  const r=await C.reviewIncomplete(files,1,tmdb,false,async()=>{calls++;return douban;});
  assert.equal(calls,1);assert.equal(r.db.source,'douban');assert.equal(r.db.total,2);
  assert.equal(r.audit.integrity,'齐全');assert.deepEqual(r.audit.missing,[]);
  assert.equal(r.review.tmdb.total,3);assert.deepEqual(r.review.tmdb.missing,[3]);
  assert.equal(r.db.url,douban.url);
});
test('豆瓣登记集数更多时重新计算缺集，不沿用 TMDB 缺集清单',async()=>{
  const r=await C.reviewIncomplete(files,1,tmdb,false,async()=>({...douban,total:5}));
  assert.equal(r.audit.integrity,'未完结');assert.deepEqual(r.audit.missing,[3,4,5]);
});
test('豆瓣结果少于本地集号范围时仍待核实',async()=>{
  const r=await C.reviewIncomplete(files,1,tmdb,false,async()=>({...douban,total:1}));
  assert.equal(r.audit.integrity,'待核实');assert.deepEqual(r.audit.extra,[2]);
});
test('豆瓣复核失败或链接无效时保留 TMDB 集数和来源，但仍待核实',async()=>{
  for(const result of [{error:'没有匹配候选'},{...douban,url:'https://example.com/'},{...douban,total:0}]){
    const r=await C.reviewIncomplete(files,1,tmdb,false,async()=>result);
    assert.equal(r.audit.integrity,'待核实');assert.deepEqual(r.audit.missing,[3]);
    assert.equal(r.db.total,3);assert.equal(r.review.state,'failed');assert.equal(r.review.tmdb.total,3);
    assert.equal(r.db.source,'tmdb');assert.equal(r.db.url,tmdb.url);
    assert.match(r.db.error,/豆瓣复核失败/);
    const sheet=C.resultWorkbook([{...r.audit,total:r.db.total,source:r.db.source,sourceUrl:r.db.url,note:r.db.error,status:r.audit.integrity}]).Sheets['剧集检查'];
    assert.equal(sheet.G2.v,3);assert.equal(sheet.I2.v,'tmdb');assert.match(sheet.R2.v,/豆瓣复核失败/);
    assert.equal(sheet.B2.s.fill,undefined);
  }
});
test('齐全、待核实、目标重名和已使用豆瓣时不额外触发复核',async()=>{
  for(const [db,conflict] of [[{...tmdb,total:2},false],[{...tmdb,completionConfirmed:false},false],[tmdb,true],[{...douban,source:'douban'},false]]){
    const r=await C.reviewIncomplete(files,1,db,conflict,async()=>{assert.fail('不应请求豆瓣');});
    assert.equal(r.review,null);
  }
});
test('豆瓣等待期间暂停向上传递，不能把暂停当作最终复核结论',async()=>{
  const paused=new Error('手动登录后继续');paused.name='Paused';
  await assert.rejects(()=>C.reviewIncomplete(files,1,tmdb,false,async()=>{throw paused;}),e=>e===paused);
});
