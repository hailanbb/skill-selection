// 构建独立安装包：嵌入已保存的 OpenCC、Excel 库及各自业务模块，不依赖运行时 CDN。
// src 为可维护源码；请勿直接编辑生成的 *.user.js。第三方原始许可随包保留。
const fs = require('node:fs');
const path = require('node:path');
const root = __dirname;
const read = p => fs.readFileSync(path.join(root,p), 'utf8');
const marker = '/* build:opencc */ null';
const license = ['OpenCC-js 1.4.2 — https://github.com/nk2028/opencc-js',
  read('vendor/package/LICENSE'), read('vendor/package/THIRD_PARTY_LICENSES.md'), read('vendor/package/LICENSES/Apache-2.0.txt')].join('\n');
const bundle = read('vendor/package/dist/umd/t2cn.js');
const embedded = `(() => {\n/*\n${license.replace(/\*\//g,'* /')}\n*/\nconst exports = {}; const module = { exports };\n${bundle}\nreturn exports.Converter({from:'tw',to:'cn'});\n})()`;
const excelMarker='/* build:xlsx */ null';
const excelLicense=read('vendor/xlsx-js-style/package/LICENSE')+'\n'+read('vendor/xlsx-js-style/package/dist/LICENSE');
const excelBundle=read('vendor/xlsx-js-style/package/dist/xlsx.bundle.js').replace(/\/\/# sourceMappingURL=.*$/gm,'');
const excelEmbedded=`(() => {\n/* xlsx-js-style 1.2.0, https://github.com/gitbrent/xlsx-js-style\n${excelLicense.replace(/\*\//g,'* /')}\n*/\nconst exports={}; const module=undefined,require=undefined,window=undefined,define=undefined;\n${excelBundle}\nreturn exports;\n})()`;
const reviewMarker='/* build:review */ null';
// 第三阶段复用已经验证的文件名/豆瓣匹配逻辑；只截取明确的纯函数区段，不嵌入初检面板或 TMDB 查询。
const inspectSource=read('src/season-inspect.js');
function section(start,end) {
  if(inspectSource.split(start).length!==2||inspectSource.split(end).length!==2)throw Error('Shared source boundary changed: '+start);
  const a=inspectSource.indexOf(start),b=inspectSource.indexOf(end,a);if(b<a)throw Error('Invalid shared source boundary');return inspectSource.slice(a,b);
}
// 下载仅共享文本标准化，身份仍由媒体 ID / 完整名称和年份判断；不复用豆瓣的候选放宽规则。
const titleTextCore='(function createTitleText(toSimplified) {\n'+section('  const norm =','  const parent =')+section('  function cleanTitleText(','  function sameTitle(')+'\nreturn {norm,cleanTitleText};\n})';
for(const name of ['season-inspect','season-download']) {
  const src=read(`src/${name}.js`);
  for(const required of [marker,excelMarker])if(src.split(required).length!==2)throw Error(`${name}: expected one ${required}`);
  let output=src.replace(marker,()=>embedded).replace(excelMarker,()=>excelEmbedded);
  if(src.includes(reviewMarker)) {
    if(src.split(reviewMarker).length!==2)throw Error('Expected one Excel review build marker');
    output=output.replace(reviewMarker,()=>read('src/excel-review.js'));
  }
  // 可选模块只进入需要它的脚本，初检版不会因此带入下载或报告修改功能。
  for(const [marker,file] of [['/* build:panel-layout */ null','src/panel-layout.js'],['/* build:douban-policy */ null','src/douban-policy.js'],['/* build:douban-query */ null','src/douban-query.js']])if(output.includes(marker))output=output.replace(marker,()=>read(file));
  for(const [marker,file] of [['/* build:download-core */ null','src/download-core.js'],['/* build:workflow-report */ null','src/workflow-report.js']]) {
    if(output.includes(marker)) {
      if(output.split(marker).length!==2)throw Error(`Expected one ${marker}`);
      output=output.replace(marker,()=>read(file));
    }
  }
  output=output.replace('/* build:title-text */ null',()=>titleTextCore);
  fs.writeFileSync(path.join(root,`${name}.user.js`),output,'utf8');
  console.log(`Built ${name}.user.js with offline OpenCC-js and Excel support`);
}
