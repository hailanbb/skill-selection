import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const args = Object.fromEntries(Array.from({length: (process.argv.length - 2) / 2}, (_, i) =>
  [process.argv[2 + i * 2], process.argv[3 + i * 2]]));
if (!args['--input'] || !args['--output'] || !args['--preview']) {
  throw new Error('Required: --input prepared.json --output statement.xlsx --preview preview.png');
}
for (const key of ['--output', '--preview']) {
  try { await fs.access(args[key]); throw new Error(`Refusing to overwrite: ${args[key]}`); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
}
const data = JSON.parse(await fs.readFile(args['--input'], 'utf8'));
if (data.schema_version !== 1 || !Array.isArray(data.records)) throw new Error('Unsupported input');
const records = data.records;
for (const r of records) {
  if (r.amount !== null && (!/^-?\d+(?:\.\d{1,2})?$/.test(r.amount) || Number(r.amount) > 0)) {
    throw new Error('Prepared data contains invalid or positive amount');
  }
  if ((r.amount === null || r.datetime === null) && !r.note) throw new Error('Missing-field note required');
}
function serial(text) {
  if (text === null) return null;
  if (!/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(text)) throw new Error('Invalid datetime');
  const millis = Date.parse(text.replace(' ', 'T') + ':00Z');
  if (!Number.isFinite(millis) || new Date(millis).toISOString().slice(0,16).replace('T',' ') !== text) {
    throw new Error('Invalid calendar date');
  }
  return millis / 86400000 + 25569;
}

const wb = Workbook.create();
const sheet = wb.worksheets.add('消费记录');
const notes = records.some(r => r.note);
const lastCol = notes ? 'F' : 'E';
const end = Math.max(9, records.length + 8);
sheet.showGridLines = false;
sheet.getRange(`A1:${lastCol}${end}`).format = {
  font: {name: 'Microsoft YaHei', size: 11}, horizontalAlignment: 'center',
  verticalAlignment: 'center', rowHeight: 24,
};
sheet.getRange(`A1:${lastCol}1`).merge();
sheet.getRange('A1').values = [['八达通消费记录']];
sheet.getRange(`A1:${lastCol}1`).format = {
  fill: '#087F5B', font: {bold: true, color: '#FFFFFF', size: 17}, rowHeight: 34,
};
sheet.getRange('A2:E2').values = [[
  '卡号', data.card_number ?? '未识别', '截图显示余额',
  data.screenshot_balance === null ? null : Number(data.screenshot_balance), 'HKD',
]];
sheet.getRange(`A3:${lastCol}3`).merge();
sheet.getRange('A3').values = [[`来源：${data.cropped_name}`]];
sheet.getRange(`A4:${lastCol}4`).merge();
sheet.getRange('A4').values = [['仅含裁剪范围内非正数交易；截图余额为原图显示值。']];
sheet.getRange('A2:E3').format.fill = '#E9F7F1';
sheet.getRange('A6:C6').values = [['记录笔数', data.counts.unknown_amount ? '已知消费合计（HKD）' : '消费合计（HKD）', '未识别金额笔数']];
sheet.getRange('A7:C7').formulas = [[
  `=COUNTA(A9:A${end})`, `=-SUM(E9:E${end})`, `=A7-COUNT(E9:E${end})`,
]];
sheet.getRange('A6:C6').format = {fill: '#D8EFE5', font: {bold: true}};
sheet.getRange('A7:C7').format.font = {bold: true};
const decimals = records.some(r => r.amount !== null && /\.\d{2}$/.test(r.amount)) ? 2 : 1;
const numFormat = `#,##0.${'0'.repeat(decimals)};[Red]-#,##0.${'0'.repeat(decimals)}`;
sheet.getRange('B7').setNumberFormat(numFormat);
sheet.getRange('D2').setNumberFormat('#,##0.00');
const headers = ['序号', '日期时间', '交易方', '交易类别', '金额（HKD）'];
if (notes) headers.push('备注');
sheet.getRange(`A8:${lastCol}8`).values = [headers];
sheet.getRange(`A8:${lastCol}8`).format = {fill: '#196B24', font: {bold: true, color: '#FFFFFF'}};
if (records.length) {
  sheet.getRange(`A9:${lastCol}${end}`).values = records.map((r, i) => {
    const row = [i + 1, serial(r.datetime), r.party, r.category, r.amount === null ? null : Number(r.amount)];
    if (notes) row.push(r.note || null);
    return row;
  });
  const table = sheet.tables.add(`A8:${lastCol}${end}`, true, 'OctopusTransactions');
  table.style = 'TableStyleMedium4';
  table.showFilterButton = true;
}
sheet.getRange(`B9:B${end}`).setNumberFormat('yyyy-mm-dd hh:mm');
sheet.getRange(`E9:E${end}`).setNumberFormat(numFormat);
for (const [col, width] of [['A', 13], ['B', 30], ['C', 27], ['D', 23], ['E', 23], ['F', 62]]) {
  if (col === 'F' && !notes) continue;
  sheet.getRange(`${col}1:${col}${end}`).format.columnWidth = width;
}
sheet.freezePanes.unfreeze();
wb.recalculate();
const totals = sheet.getRange('A7:C7').values[0];
const knownTotal = -records.reduce((sum, r) => sum + (r.amount === null ? 0 : Math.round(Number(r.amount) * 100)), 0) / 100;
if (totals[0] !== records.length || Math.abs(totals[1] - knownTotal) > 1e-7 ||
    totals[2] !== records.filter(r => r.amount === null).length ||
    Math.abs(knownTotal - Number(data.known_expense_total)) > 1e-7) throw new Error('Summary mismatch');
console.log((await wb.inspect({kind: 'table', range: '消费记录!A6:E12', include: 'values,formulas',
  tableMaxRows: 7, tableMaxCols: 5, maxChars: 2400})).ndjson);
console.log((await wb.inspect({kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',
  options: {useRegex: true, maxResults: 20}})).ndjson);
await fs.mkdir(path.dirname(args['--output']), {recursive: true});
await fs.mkdir(path.dirname(args['--preview']), {recursive: true});
const preview = await wb.render({sheetName: '消费记录', range: `A1:${lastCol}${Math.min(end, 28)}`, scale: 1, format: 'png'});
await fs.writeFile(args['--preview'], new Uint8Array(await preview.arrayBuffer()), {flag: 'wx'});
await (await SpreadsheetFile.exportXlsx(wb)).save(args['--output']);
console.log(JSON.stringify({exported: args['--output'], rows: records.length, knownTotal, unknown: totals[2]}));
