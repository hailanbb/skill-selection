// Build the single installable userscript without runtime CDN dependencies.
const fs = require('node:fs');
const path = require('node:path');
const root = __dirname;
const read = p => fs.readFileSync(path.join(root,p), 'utf8');
const src = read('src/season-audit.js');
const marker = '/* build:opencc */ null';
if (src.split(marker).length !== 2) throw Error('Expected one OpenCC build marker');
const license = ['OpenCC-js 1.4.2 — https://github.com/nk2028/opencc-js',
  read('vendor/package/LICENSE'), read('vendor/package/THIRD_PARTY_LICENSES.md'), read('vendor/package/LICENSES/Apache-2.0.txt')].join('\n');
const bundle = read('vendor/package/dist/umd/t2cn.js');
const embedded = `(() => {\n/*\n${license.replace(/\*\//g,'* /')}\n*/\nconst exports = {}; const module = { exports };\n${bundle}\nreturn exports.Converter({from:'tw',to:'cn'});\n})()`;
const excelMarker='/* build:xlsx */ null';
if(src.split(excelMarker).length!==2)throw Error('Expected one XLSX build marker');
const excelLicense=read('vendor/xlsx-js-style/package/LICENSE')+'\n'+read('vendor/xlsx-js-style/package/dist/LICENSE');
const excelBundle=read('vendor/xlsx-js-style/package/dist/xlsx.bundle.js').replace(/\/\/# sourceMappingURL=.*$/gm,'');
const excelEmbedded=`(() => {\n/* xlsx-js-style 1.2.0, https://github.com/gitbrent/xlsx-js-style\n${excelLicense.replace(/\*\//g,'* /')}\n*/\nconst exports={}; const module=undefined,require=undefined,window=undefined,define=undefined;\n${excelBundle}\nreturn exports;\n})()`;
fs.writeFileSync(path.join(root,'season-audit.user.js'), src.replace(marker,()=>embedded).replace(excelMarker,()=>excelEmbedded), 'utf8');
console.log('Built season-audit.user.js with offline OpenCC-js and Excel export support');
