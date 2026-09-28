// A DOM/GM adapter exercises the actual userscript event handlers without a network or cloud account.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../season-audit.user.js'),'utf8');
async function launch(initial={},responses=[]) {
  const values=new Map(Object.entries(initial)),elements=[],opened=[],requests=[],accesses=[];
  class Element {
    constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.style={};this.listeners={};this.checked=false;this.value='';this.textContent='';this.classes=new Set();
      this.classList={add:c=>this.classes.add(c),contains:c=>this.classes.has(c),toggle:c=>this.classes.has(c)?this.classes.delete(c):this.classes.add(c)};elements.push(this);}
    set className(v){this._className=v;this.classes=new Set(v.split(' '));}
    get className(){return this._className||'';}
    append(...children){this.children.push(...children);for(const c of children)if(c instanceof Element)c.parentElement=this;}
    replaceChildren(...children){this.children=[];this.append(...children);}
    attachShadow(){this.shadow=new Element('shadow');this.shadow.parentElement=this;return this.shadow;}
    addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
    async fire(name,props={}){for(const fn of this.listeners[name]||[])await fn({target:this,button:0,preventDefault(){},...props});}
    closest(tag){for(let e=this;e;e=e.parentElement)if(e.tagName===tag.toUpperCase())return e;return null;}
    setPointerCapture(){}
    getBoundingClientRect(){const box=elements.find(e=>e.className==='box');return {left:parseFloat(this.style.left)||500,top:parseFloat(this.style.top)||100,width:box?.classes.has('min')?240:440,height:box?.classes.has('min')?80:600};}
    click(){return this.fire('click');}
  }
  const body=new Element('body');
  const context={console,URL,URLSearchParams,TextDecoder,Blob,Map,Set,Date,JSON,Math,Number,Promise,crypto:require('node:crypto').webcrypto,
    location:{hostname:'clouddrive.example',origin:'https://clouddrive.example',href:'https://clouddrive.example/?page=files'},
    document:{body,createElement:t=>new Element(t),createTextNode:t=>({textContent:t})},
    window:{addEventListener(){}},innerWidth:1200,innerHeight:900,requestAnimationFrame:fn=>fn(),ResizeObserver:class{constructor(fn){this.fn=fn;}observe(){}},
    navigator:{locks:{request:async(_name,options,fn)=>(fn||options)({})}},
    GM_getValue:(k,d)=>{accesses.push(['read',k]);return values.has(k)?values.get(k):d;},GM_setValue:(k,v)=>{accesses.push(['write',k]);values.set(k,structuredClone(v));},GM_deleteValue:k=>{accesses.push(['delete',k]);values.delete(k);},
    GM_xmlhttpRequest:options=>{requests.push(options);queueMicrotask(()=>options.onload(responses.shift()||{status:200,response:{success:true}}));return {abort(){}};},
    GM_openInTab:(url,options)=>{opened.push({url,options});return {close(){}};},setTimeout,clearTimeout};
  vm.runInNewContext(source,context);
  await new Promise(resolve=>setImmediate(resolve));
  return {values,elements,opened,requests,accesses,button:name=>elements.find(e=>e.tagName==='BUTTON'&&e.textContent===name)};
}
test('真实面板事件：展开和收起都能拖动，刷新后恢复位置与收起状态',async()=>{
  const first=await launch(),header=first.elements.find(e=>e.tagName==='HEADER'),panel=first.elements.find(e=>e.id==='tv-audit-panel');
  await header.fire('pointerdown',{pointerId:1,clientX:510,clientY:110});
  await header.fire('pointermove',{pointerId:1,clientX:310,clientY:210});
  await header.fire('pointerup',{pointerId:1});
  assert.equal(panel.style.left,'300px');assert.equal(panel.style.top,'200px');
  await first.button('收起 / 展开').click();
  await header.fire('pointerdown',{pointerId:2,clientX:310,clientY:210});
  await header.fire('pointermove',{pointerId:2,clientX:410,clientY:310});
  await header.fire('pointerup',{pointerId:2});
  assert.equal(panel.style.left,'400px');
  const saved=first.values.get('tv-audit-v1:panel-position');assert.equal(saved.collapsed,true);
  const next=await launch({'tv-audit-v1:panel-position':saved});
  assert.equal(next.elements.find(e=>e.id==='tv-audit-panel').style.left,'400px');
  assert.equal(next.elements.find(e=>e.className==='box').classList.contains('min'),true);
});
test('启动时不读取、迁移或删除旧查询缓存',async()=>{
  const old={total:60,url:'https://movie.douban.com/subject/37105602/',title:'阿荣与阿玉 (2024)',checkedAt:'2020-01-01T00:00:00Z'};
  const page=await launch({'tv-audit-v1:cache:273042:S1':old});
  assert.equal(page.values.has('tv-audit-v1:database'),false);
  assert.equal(page.values.get('tv-audit-v1:cache:273042:S1').total,60);
  assert.ok(!page.accesses.some(([,key])=>/cache:|database|history:/.test(key)));
  assert.equal(page.button('开始检查').disabled,false);
  assert.equal(page.opened.length,0);
});
test('旧数据库内容保持原样，不再影响检查入口',async()=>{
  const page=await launch({'tv-audit-v1:database':{format:'other',records:{keep:1}}});
  assert.equal(page.button('开始检查').disabled,false);
  assert.equal(page.values.get('tv-audit-v1:database').records.keep,1);
});
test('刷新后不展示上轮结果、汇总或错误，存储中的任务仍保留',async()=>{
  const job={id:'old-job',category:'台湾剧集',status:'已暂停',error:'旧错误不应显示',results:[{showName:'旧剧名不应显示',season:1,status:'待核实',note:'旧错误不应显示'}]};
  const page=await launch({'tv-audit-v1:job':job});
  const text=page.elements.map(e=>e.textContent).join('\n');
  assert.ok(!text.includes('旧剧名不应显示'));assert.ok(!text.includes('旧错误不应显示'));assert.ok(!text.includes('台湾剧集 ·'));
  assert.equal(page.values.get('tv-audit-v1:job').id,'old-job');
  assert.equal(page.button('继续本轮').disabled,true);
  assert.ok(!page.accesses.some(([,key])=>key==='tv-audit-v1:job'));
});
test('面板可保存两种凭据，令牌失败时用密钥测试连接且不回显凭据',async()=>{
  const page=await launch({},[{status:401,response:{}},{status:200,response:{success:true}}]);
  const token=page.elements.find(e=>e.placeholder==='API 读访问令牌'),key=page.elements.find(e=>e.placeholder==='API 密钥');
  assert.equal(token.type,'password');assert.equal(key.type,'password');
  token.value='TEST_TOKEN';key.value='TEST_KEY';
  await page.button('保存 TMDB 凭据').click();await page.button('测试 TMDB 连接').click();
  assert.equal(page.requests.length,2);
  assert.equal(page.requests[0].headers.Authorization,'Bearer TEST_TOKEN');
  assert.equal(new URL(page.requests[1].url).searchParams.get('api_key'),'TEST_KEY');
  const text=page.elements.map(e=>e.textContent).join('\n');
  assert.ok(text.includes('TMDB 连接与认证成功'));assert.ok(!text.includes('TEST_TOKEN'));assert.ok(!text.includes('TEST_KEY'));
  assert.equal(page.values.has('tv-audit-v1:database'),false);
});
test('面板移除数据库、路径、历史导出和离线模式，保留本轮报告导出',async()=>{
  const page=await launch();
  const text=page.elements.map(e=>e.textContent+' '+(e.placeholder||'')).join('\n');
  for(const obsolete of ['本地数据库与历史','数据库期望保存路径','导出历史报告','仅使用本地数据库','继续上次'])assert.ok(!text.includes(obsolete));
  assert.ok(page.button('导出 Excel（绿色标记）'));assert.ok(page.button('导出 CSV'));assert.ok(page.button('导出完整 JSON'));assert.ok(page.button('继续本轮'));
  assert.ok(!/indexedDB|showOpenFilePicker|showSaveFilePicker|GM_listValues|GM_addValueChangeListener/.test(source));
  assert.ok(!/(?:get|put|del)\('(?:database|cache:|history:|job'|mapping:)/.test(source));
});
