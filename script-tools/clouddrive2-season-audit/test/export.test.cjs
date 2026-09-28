const {test}=require('node:test');
const assert=require('node:assert/strict');
const C=require('../season-audit.user.js');
function parseCsv(text){
  const rows=[];let row=[],cell='',quoted=false;
  const s=text.replace(/^\ufeff/,'');
  for(let i=0;i<s.length;i++){
    const c=s[i];
    if(c==='"'){if(quoted&&s[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}
    else if(c===','&&!quoted){row.push(cell);cell='';}
    else if(c==='\n'&&!quoted){row.push(cell);rows.push(row);row=[];cell='';}
    else if(c==='\r'&&!quoted&&s[i+1]==='\n')continue;
    else cell+=c;
  }
  if(cell||row.length){row.push(cell);rows.push(row);}return rows;
}
const path='Root/115/Library_incs/nas/电视剧/台湾剧集/阿荣与阿玉 (2024) [tmdbid=273042]/Season 1';
test('Excel 仅将最终齐全记录的剧集目录填绿，重名和待核实不填绿',()=>{
  const statuses=['齐全','齐全（未移动）','未完结','待核实','目标重名'];
  const sheet=C.resultWorkbook(statuses.map(status=>({showName:'测试剧',status,path,total:24,season:1}))).Sheets['剧集检查'];
  statuses.forEach((s,i)=>{
    assert.equal(sheet['B'+(i+2)].s.fill?.fgColor.rgb,i<2?'C6EFCE':undefined);
    assert.equal(sheet['C'+(i+2)].t,'n');
    assert.equal(sheet['D'+(i+2)].l.Target,C.cloudLink(path));
    assert.equal(sheet['A'+(i+2)].s.fill,undefined);
  });
  assert.equal(sheet['!autofilter'].ref,'A1:S6');
});
test('Excel 写出实际 XLSX 字节，中文和公式样式文本作为文字保留',()=>{
  const rows=[{showName:'=测试剧',status:'齐全',path}];
  const sheet=C.resultWorkbook(rows).Sheets['剧集检查'];
  assert.equal(sheet.B2.t,'s');assert.equal(sheet.B2.f,undefined);
  const bytes=Buffer.from(C.resultXlsx(rows));assert.equal(bytes.subarray(0,2).toString(),'PK');assert.ok(bytes.length>1000);
});
test('CSV 保留原列顺序并增加核对说明与无法识别的文件',()=>{
  const r={path,conflict:true,note:'说明内容',scannedAt:'2026-09-28',plan:'仅建议',futureEpisodes:[5],undatedEpisodes:[6]};
  const [header,data]=parseCsv(C.resultCsv([r]));
  assert.equal(header.length,19);assert.equal(data.length,19);
  assert.equal(header[17],'核对说明');assert.equal(data[17],'说明内容');assert.equal(header[18],'无法识别集号的文件');
  assert.ok(header.includes('源云存储链接'));
  for(const name of ['源云存储路径','当前未到播出日集号','播出日期未知集号','扫描时间','建议动作（未执行）','说明'])assert.ok(!header.includes(name));
  assert.equal(data[header.indexOf('目标重名')],'YES');assert.equal(r.note,'说明内容');
});
test('超链接公式显示 URL 且正确定位中文、空格和 TMDB 标签所在季目录',()=>{
  const [header,data]=parseCsv(C.resultCsv([{path}]));
  const url=C.cloudLink(path),link=data[header.indexOf('源云存储链接')];
  assert.equal(link,`=HYPERLINK("${url}","${url}")`);
  assert.equal(new URL(url).origin,'https://clouddrive.example');
  assert.equal(new URL(url).searchParams.get('path'),path.slice(4));
  assert.equal(new URL(url).searchParams.get('page'),'files');
});
test('目标未重名时留空，不输出 false、NO 或 YES',()=>{
  const rows=parseCsv(C.resultCsv([{conflict:false},{conflict:'false'},{},{conflict:'true'}]));
  const i=rows[0].indexOf('目标重名');assert.deepEqual(rows.slice(1).map(r=>r[i]),['','','','YES']);
});
test('超链接不接受其他域名或越界路径；其余 CSV 内容仍防公式注入',()=>{
  for(const p of ['https://evil.example/','Root/115/Library_incs/nas/电视剧/../secret','Root/other'])assert.equal(C.cloudLink(p),'');
  const rows=parseCsv(C.resultCsv([{path:path+'/\"test\"',showName:'=WEBSERVICE("bad")'}]));
  assert.ok(rows[1][rows[0].indexOf('剧集目录')].startsWith("'="));
  assert.ok(rows[1][rows[0].indexOf('源云存储链接')].includes('%22test%22'));
});
test('移除数据库后仍限制拖动位置，展开与收起都不越出视口',()=>{
  assert.deepEqual(C.clampPosition({x:900,y:700},440,600,1000,800),{x:560,y:200});
  assert.deepEqual(C.clampPosition({x:900,y:700},240,80,1000,800),{x:760,y:700});
  assert.deepEqual(C.clampPosition({x:-1,y:-10},440,600,1000,800),{x:0,y:0});
});
