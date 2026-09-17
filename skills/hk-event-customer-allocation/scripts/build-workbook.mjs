#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const COLORS = {
  navy: "#1F4E78",
  blue: "#5B9BD5",
  pale: "#D9EAF7",
  lighter: "#EDF4FA",
  border: "#B4C7DC",
  white: "#FFFFFF",
  text: "#1F2937",
  warning: "#FFF2CC",
};
const FONT = "Microsoft YaHei";

function columnName(number) {
  let value = number;
  let result = "";
  while (value > 0) {
    value -= 1;
    result = String.fromCharCode(65 + (value % 26)) + result;
    value = Math.floor(value / 26);
  }
  return result;
}

function safeFileName(value) {
  const cleaned = String(value ?? "活動場地")
    .replace(/[<>:"/\\|?*]/gu, "_")
    .replace(/[. ]+$/gu, "")
    .trim();
  return cleaned || "活動場地";
}

function setBaseStyle(sheet, rangeAddress) {
  sheet.showGridLines = false;
  const range = sheet.getRange(rangeAddress);
  range.format = {
    font: { name: FONT, color: COLORS.text, size: 10 },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
  };
  range.format.rowHeightPx = 24;
}

function styleTitle(sheet, address) {
  const range = sheet.getRange(address);
  range.format = {
    fill: COLORS.navy,
    font: { name: FONT, bold: true, color: COLORS.white, size: 16 },
    horizontalAlignment: "center",
    verticalAlignment: "center",
  };
  range.format.rowHeightPx = 36;
}

function styleHeader(sheet, address) {
  const range = sheet.getRange(address);
  range.format = {
    fill: COLORS.blue,
    font: { name: FONT, bold: true, color: COLORS.white, size: 10 },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: COLORS.border },
  };
  range.format.rowHeightPx = 32;
}

function styleBody(sheet, address) {
  sheet.getRange(address).format.borders = { preset: "all", style: "thin", color: COLORS.border };
}

function setWidths(sheet, rowCount, widths) {
  widths.forEach((width, index) => {
    const col = columnName(index + 1);
    sheet.getRange(`${col}1:${col}${rowCount}`).format.columnWidthPx = width;
  });
}

function addTable(sheet, address, name) {
  const table = sheet.tables.add(address, true, name);
  table.style = "TableStyleMedium2";
  table.showFilterButton = true;
  table.showBandedColumns = false;
  return table;
}

function buildSummary(sheet, plan, assignmentLastRow) {
  const types = Object.keys(plan.totals?.type_counts ?? {}).sort((a, b) => a.localeCompare(b, "zh-HK"));
  const lastColumnNumber = 8 + types.length;
  const lastColumn = columnName(lastColumnNumber);
  const lastRow = 9 + plan.groups.length;

  sheet.mergeCells(`A1:${lastColumn}1`);
  sheet.getRange("A1").values = [[`${plan.venue.name}｜銷售團隊客戶分工總覽`]];
  sheet.getRange("A3:B7").values = [
    ["活動場地", plan.venue.name],
    ["場地地址", plan.venue.address],
    ["距離口徑", "步行距離（KM）"],
    ["工作量規則", "診所 1.5；其他類型 1.0"],
    ["步行提示", plan.warning],
  ];
  if (lastColumnNumber > 2) {
    for (let row = 3; row <= 7; row += 1) sheet.mergeCells(`B${row}:${lastColumn}${row}`);
  }
  sheet.getRange("A3:A7").format = {
    fill: COLORS.pale,
    font: { name: FONT, bold: true, color: COLORS.text },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    borders: { preset: "all", style: "thin", color: COLORS.border },
  };
  sheet.getRange(`B3:${lastColumn}7`).format = {
    fill: COLORS.lighter,
    font: { name: FONT, color: COLORS.text },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: COLORS.border },
  };
  sheet.getRange(`B7:${lastColumn}7`).format.fill = COLORS.warning;

  const headers = [
    "小組", "成員", "名單人數", "客戶總數", "加權工作量", "人均加權工作量",
    "平均步行距離（KM）", "最遠步行距離（KM）", ...types,
  ];
  sheet.getRange(`A9:${lastColumn}9`).values = [headers];
  const rows = plan.groups.map((group) => [group.name, group.members.join("、"), group.headcount]);
  if (rows.length) sheet.getRange(`A10:C${lastRow}`).values = rows;

  for (let index = 0; index < plan.groups.length; index += 1) {
    const row = 10 + index;
    sheet.getRange(`D${row}:H${row}`).formulas = [[
      `=COUNTIF('客戶分工'!$B$4:$B$${assignmentLastRow},$A${row})`,
      `=SUMIF('客戶分工'!$B$4:$B$${assignmentLastRow},$A${row},'客戶分工'!$H$4:$H$${assignmentLastRow})`,
      `=IFERROR(E${row}/C${row},0)`,
      `=IFERROR(AVERAGEIF('客戶分工'!$B$4:$B$${assignmentLastRow},$A${row},'客戶分工'!$G$4:$G$${assignmentLastRow}),0)`,
      `=IFERROR(MAXIFS('客戶分工'!$G$4:$G$${assignmentLastRow},'客戶分工'!$B$4:$B$${assignmentLastRow},$A${row}),0)`,
    ]];
    types.forEach((type, typeIndex) => {
      const col = columnName(9 + typeIndex);
      sheet.getRange(`${col}${row}`).formulas = [[
        `=COUNTIFS('客戶分工'!$B$4:$B$${assignmentLastRow},$A${row},'客戶分工'!$C$4:$C$${assignmentLastRow},${col}$9)`,
      ]];
    });
  }

  setBaseStyle(sheet, `A1:${lastColumn}${lastRow}`);
  styleTitle(sheet, `A1:${lastColumn}1`);
  styleHeader(sheet, `A9:${lastColumn}9`);
  if (lastRow >= 10) styleBody(sheet, `A10:${lastColumn}${lastRow}`);
  sheet.getRange(`C10:D${lastRow}`).format.numberFormat = "#,##0";
  sheet.getRange(`E10:F${lastRow}`).format.numberFormat = "0.0";
  sheet.getRange(`G10:H${lastRow}`).format.numberFormat = "0.00";
  if (types.length) sheet.getRange(`I10:${lastColumn}${lastRow}`).format.numberFormat = "#,##0";
  sheet.freezePanes.freezeRows(9);
  addTable(sheet, `A9:${lastColumn}${lastRow}`, "AllocationSummaryTable");
  setWidths(sheet, lastRow, [100, 230, 82, 82, 98, 118, 128, 128, ...types.map(() => 92)]);
  return sheet;
}

function buildAssignments(sheet, plan) {
  const headers = [
    "序號", "歸屬小組", "客戶類型", "客戶名稱", "客戶地址", "電話號碼",
    "距離活動現場的距離（KM）", "工作量權重",
  ];
  const assignments = [...plan.assignments].sort((a, b) =>
    a.group.localeCompare(b.group, "zh-HK") || a.route_order - b.route_order || a.id.localeCompare(b.id, "zh-HK"));
  const lastRow = 3 + assignments.length;
  sheet.mergeCells("A1:H1");
  sheet.getRange("A1").values = [[`${plan.venue.name}｜銷售團隊客戶分工`]];
  sheet.getRange("A2:H2").merge();
  sheet.getRange("A2").values = [[plan.warning]];
  sheet.getRange("A3:H3").values = [headers];
  sheet.getRange(`A4:H${lastRow}`).values = assignments.map((customer, index) => [
    index + 1,
    customer.group,
    customer.type,
    customer.name,
    customer.address,
    customer.phone,
    customer.distance_km,
    customer.weight,
  ]);
  setBaseStyle(sheet, `A1:H${lastRow}`);
  styleTitle(sheet, "A1:H1");
  sheet.getRange("A2:H2").format = {
    fill: COLORS.warning,
    font: { name: FONT, color: COLORS.text, size: 9 },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
  };
  styleHeader(sheet, "A3:H3");
  styleBody(sheet, `A4:H${lastRow}`);
  sheet.getRange(`A4:A${lastRow}`).format.numberFormat = "#,##0";
  sheet.getRange(`F4:F${lastRow}`).format.numberFormat = "@";
  sheet.getRange(`G4:G${lastRow}`).format.numberFormat = "0.00";
  sheet.getRange(`H4:H${lastRow}`).format.numberFormat = "0.0";
  sheet.freezePanes.freezeRows(3);
  addTable(sheet, `A3:H${lastRow}`, "CustomerAssignmentTable");
  setWidths(sheet, lastRow, [68, 100, 105, 170, 330, 125, 145, 95]);
  sheet.getRange(`E4:E${lastRow}`).format.rowHeightPx = 36;
  return { sheet, lastRow };
}

function buildRoutes(sheet, plan) {
  const headers = [
    "小組", "成員", "客戶數", "平均步行距離（KM）", "最遠步行距離（KM）",
    "建議首站", "建議起步區域", "整組路線規劃總結",
  ];
  const rows = plan.groups.map((group) => {
    const customers = [...plan.assignments]
      .filter((customer) => customer.group === group.name)
      .sort((a, b) => a.route_order - b.route_order || a.id.localeCompare(b.id, "zh-HK"));
    const first = customers[0];
    const farthest = [...customers].sort((a, b) => b.distance_km - a.distance_km)[0];
    const firstArea = first?.address || "由活動場地附近開始";
    const routeMethod = customers.every((customer) => customer.route_method === "實際步行距離矩陣")
      ? "實際步行距離矩陣"
      : "地理聚集建議";
    const summary = `由${plan.venue.name}出發，先到「${first?.name ?? "首站"}」，再按同街道、同屋苑或同商廈集中分段拜訪；` +
      `全組共 ${group.customer_count} 家，平均 ${group.average_distance_km.toFixed(2)} KM，最遠「${farthest?.name ?? "客戶"}」約 ${group.farthest_distance_km.toFixed(2)} KM，建議把較遠片區安排在同一時段集中完成。` +
      `本建議採用${routeMethod}，不是最短步行路線；外勤前請按現場行人通道及營業情況核實。`;
    return [
      group.name,
      group.members.join("、"),
      group.customer_count,
      group.average_distance_km,
      group.farthest_distance_km,
      first?.name ?? "",
      firstArea,
      summary,
    ];
  });
  const lastRow = 3 + rows.length;
  sheet.mergeCells("A1:H1");
  sheet.getRange("A1").values = [[`${plan.venue.name}｜小組路線規劃總結`]];
  sheet.mergeCells("A2:H2");
  sheet.getRange("A2").values = [[`每個小組只提供一條整體規劃建議；${plan.warning}`]];
  sheet.getRange("A3:H3").values = [headers];
  sheet.getRange(`A4:H${lastRow}`).values = rows;
  setBaseStyle(sheet, `A1:H${lastRow}`);
  styleTitle(sheet, "A1:H1");
  sheet.getRange("A2:H2").format = {
    fill: COLORS.warning,
    font: { name: FONT, color: COLORS.text, size: 9 },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
  };
  styleHeader(sheet, "A3:H3");
  styleBody(sheet, `A4:H${lastRow}`);
  sheet.getRange(`C4:C${lastRow}`).format.numberFormat = "#,##0";
  sheet.getRange(`D4:E${lastRow}`).format.numberFormat = "0.00";
  sheet.freezePanes.freezeRows(3);
  addTable(sheet, `A3:H${lastRow}`, "RouteSummaryTable");
  setWidths(sheet, lastRow, [90, 260, 82, 125, 125, 180, 300, 560]);
  sheet.getRange(`A4:H${lastRow}`).format.rowHeightPx = 120;
  return sheet;
}

function buildFarCustomers(sheet, plan) {
  const distanceLimit = Number(plan.allocation_distance_limit_km ?? 4);
  const headers = ["序號", "客戶類型", "客戶名稱", "客戶地址", "電話號碼", "實際步行距離（KM）", "不分配原因"];
  const customers = [...(plan.far_customers ?? [])].sort((a, b) =>
    a.distance_km - b.distance_km || a.id.localeCompare(b.id, "zh-HK"));
  const lastRow = 3 + customers.length;
  sheet.mergeCells("A1:G1");
  sheet.getRange("A1").values = [[`${plan.venue.name}｜超過 ${distanceLimit.toFixed(2)} KM 客戶`]];
  sheet.mergeCells("A2:G2");
  sheet.getRange("A2").values = [[`以下客戶的實際步行距離超過 ${distanceLimit.toFixed(2)} KM，按規則不分配予任何銷售小組。`]];
  sheet.getRange("A3:G3").values = [headers];
  if (customers.length) sheet.getRange(`A4:G${lastRow}`).values = customers.map((customer, index) => [
    index + 1, customer.type, customer.name, customer.address, customer.phone, customer.distance_km,
    customer.exclusion_reason ?? `實際步行距離超過 ${distanceLimit.toFixed(2)} KM，不分配予銷售小組`,
  ]);
  setBaseStyle(sheet, `A1:G${lastRow}`);
  styleTitle(sheet, "A1:G1");
  sheet.getRange("A2:G2").format = {
    fill: COLORS.warning, font: { name: FONT, color: COLORS.text, size: 9 },
    horizontalAlignment: "center", verticalAlignment: "center", wrapText: true,
  };
  styleHeader(sheet, "A3:G3");
  if (customers.length) {
    styleBody(sheet, `A4:G${lastRow}`);
    sheet.getRange(`A4:A${lastRow}`).format.numberFormat = "#,##0";
    sheet.getRange(`E4:E${lastRow}`).format.numberFormat = "@";
    sheet.getRange(`F4:F${lastRow}`).format.numberFormat = "0.00";
    sheet.getRange(`A4:G${lastRow}`).format.rowHeightPx = 48;
  }
  sheet.freezePanes.freezeRows(3);
  addTable(sheet, `A3:G${lastRow}`, "FarCustomerTable");
  setWidths(sheet, lastRow, [68, 115, 190, 340, 125, 135, 280]);
  return sheet;
}

function buildIssues(sheet, plan) {
  const headers = ["問題類型", "原始序號", "客戶類型", "客戶名稱", "地址", "電話", "處理建議"];
  const issues = plan.issues?.length ? plan.issues : [{ issue_type: "無", suggestion: "本次沒有待核實資料" }];
  const lastRow = 3 + issues.length;
  sheet.mergeCells("A1:G1");
  sheet.getRange("A1").values = [[`${plan.venue.name}｜待核實資料`]];
  sheet.mergeCells("A2:G2");
  sheet.getRange("A2").values = [["疑似重複、缺失欄位或無法定位的資料不得靜默刪除。"]];
  sheet.getRange("A3:G3").values = [headers];
  sheet.getRange(`A4:G${lastRow}`).values = issues.map((issue) => [
    issue.issue_type ?? issue.type ?? "待核實",
    issue.original_id ?? issue.id ?? "",
    issue.customer_type ?? issue.type ?? "",
    issue.customer_name ?? issue.name ?? "",
    issue.address ?? "",
    issue.phone ?? "",
    issue.suggestion ?? issue.detail ?? "請人工核實",
  ]);
  setBaseStyle(sheet, `A1:G${lastRow}`);
  styleTitle(sheet, "A1:G1");
  sheet.getRange("A2:G2").format = {
    fill: COLORS.warning,
    font: { name: FONT, color: COLORS.text, size: 9 },
    horizontalAlignment: "center",
    verticalAlignment: "center",
  };
  styleHeader(sheet, "A3:G3");
  styleBody(sheet, `A4:G${lastRow}`);
  sheet.getRange(`B4:B${lastRow}`).format.numberFormat = "@";
  sheet.getRange(`F4:F${lastRow}`).format.numberFormat = "@";
  sheet.freezePanes.freezeRows(3);
  addTable(sheet, `A3:G${lastRow}`, "VerificationIssueTable");
  setWidths(sheet, lastRow, [130, 95, 105, 170, 320, 125, 280]);
  sheet.getRange(`D4:G${lastRow}`).format.rowHeightPx = 40;
  return sheet;
}

async function main() {
  const [planPath, outputDirectory, previewDirectory] = process.argv.slice(2);
  if (!planPath || !outputDirectory) {
    throw new Error("用法：node build-workbook.mjs plan.json output-directory [preview-directory]");
  }
  const plan = JSON.parse(await fs.readFile(planPath, "utf8"));
  if (!plan.assignments?.length || !plan.groups?.length) throw new Error("分配方案沒有可輸出的客戶或小組。 ");

  const workbook = Workbook.create();
  const summarySheet = workbook.worksheets.add("分配總覽");
  const assignmentSheet = workbook.worksheets.add("客戶分工");
  const routeSheet = workbook.worksheets.add("小組路線建議");
  const farSheet = workbook.worksheets.add("超4KM客戶");
  const issueSheet = workbook.worksheets.add("待核實資料");
  const assignmentLastRow = 3 + plan.assignments.length;
  buildSummary(summarySheet, plan, assignmentLastRow);
  buildAssignments(assignmentSheet, plan);
  buildRoutes(routeSheet, plan);
  buildFarCustomers(farSheet, plan);
  buildIssues(issueSheet, plan);

  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 100 },
    summary: "公式錯誤檢查",
  });
  if (/"matchCount"\s*:\s*[1-9]/u.test(errors.ndjson ?? "")) {
    throw new Error("工作簿含公式錯誤，已停止輸出。 ");
  }

  if (previewDirectory) {
    await fs.mkdir(previewDirectory, { recursive: true });
    const previewRanges = { "分配總覽": "A1:J16", "客戶分工": "A1:H28", "小組路線建議": "A1:H10", "超4KM客戶": "A1:G28", "待核實資料": "A1:G28" };
    for (const [sheetName, range] of Object.entries(previewRanges)) {
      const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
      await fs.writeFile(path.join(previewDirectory, `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
    }
  }

  await fs.mkdir(outputDirectory, { recursive: true });
  const outputPath = path.join(outputDirectory, `${safeFileName(plan.venue.name)}+銷售團隊客戶分工.xlsx`);
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(outputPath);
  await fs.rm(`${outputPath}.inspect.ndjson`, { force: true });
  process.stdout.write(`${outputPath}\n`);
  // Some render backends leave a non-fatal exit code after producing valid previews.
  // Reaching this line means inspection, previews (when requested), and export all completed.
  process.exitCode = 0;
}

main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
});
