/**
 * 交互式定向/指定剧集初检导航器
 * 先展示网盘分类与可用文件夹列表，再允许用户通过序号、名称或关键词进行初检
 */
import { CloudDriveClient } from '../clients/clouddrive2.js';
import { runStage } from '../stages/index.js';

/**
 * 解析用户输入的数字序号列表（支持 1 或 1,3,5 或区间 1-3）
 * @param {string} str
 * @param {number} max
 * @returns {number[]}
 */
function parseIndices(str, max) {
  const parts = str.split(/[\s,，]+/);
  const result = new Set();
  for (const p of parts) {
    if (p.includes('-')) {
      const [start, end] = p.split('-').map(Number);
      if (!isNaN(start) && !isNaN(end)) {
        for (let i = Math.min(start, end); i <= Math.max(start, end); i++) {
          if (i >= 1 && i <= max) result.add(i);
        }
      }
    } else {
      const n = Number(p);
      if (!isNaN(n) && n >= 1 && n <= max) result.add(n);
    }
  }
  return [...result].sort((a, b) => a - b);
}

/**
 * 执行交互式剧集初检导航
 * @param {import('node:readline').Interface} rl
 * @param {object} config
 * @param {object} logger
 */
export async function handleInteractiveInspect(rl, config, logger) {
  const cd2 = new CloudDriveClient({
    origin: config.clouddrive2.origin,
    token: config.clouddrive2.token,
    logger,
  });

  const sourceRoot = (config.paths.source || '').replace(/\/+$/, '');
  console.log(`\n⏳ 正在获取网盘目录结构 (${sourceRoot})...`);

  let rootEntries = [];
  try {
    rootEntries = await cd2.listFiles(sourceRoot);
  } catch (err) {
    logger.error(`读取源目录失败: ${err.message}`);
    return;
  }

  const categories = rootEntries.filter(f => f.directory);
  if (!categories.length) {
    console.log('⚠️ 源根目录下未发现分类文件夹');
    return;
  }

  console.log(`\n${'═'.repeat(54)}`);
  console.log(`📁 可选剧集分类列表 (根目录: ${sourceRoot})`);
  console.log(`${'═'.repeat(54)}`);
  categories.forEach((cat, idx) => {
    const num = String(idx + 1).padStart(2, ' ');
    console.log(`  [${num}] ${cat.name}`);
  });
  console.log(`${'═'.repeat(54)}`);

  const ask = (q) => new Promise(res => {
    let resolved = false;
    const finish = (val) => {
      if (!resolved) {
        resolved = true;
        res(val);
      }
    };
    if (rl.closed) return finish('');
    try {
      rl.question(q, (ans) => finish(ans));
      rl.once('close', () => finish(''));
    } catch {
      finish('');
    }
  });

  const catPrompt =
    `  👉 请选择分类以查看其下文件夹:\n` +
    `     • 输入分类序号 (如: 1)\n` +
    `     • 输入分类名称 (如: 韩国剧集)\n` +
    `     • 或直接输入剧名关键词/网盘绝对路径进行直达初检\n` +
    `     (直接回车取消) > `;

  const catInput = (await ask(catPrompt)).trim();

  if (!catInput) {
    console.log('  ⚠️ 操作已取消');
    return;
  }

  // 1. 如果用户直接输入了网盘绝对路径
  if (catInput.startsWith('/')) {
    logger.info(`🎯 直接扫描指定路径: ${catInput}`);
    await runStage('inspect', config, logger, { path: catInput });
    return;
  }

  // 2. 检查是否匹配分类（通过序号或分类名模糊匹配）
  let targetCat = null;
  const catIdx = parseInt(catInput, 10);
  if (!isNaN(catIdx) && catIdx >= 1 && catIdx <= categories.length) {
    targetCat = categories[catIdx - 1];
  } else {
    targetCat = categories.find(c => c.name.toLowerCase() === catInput.toLowerCase()) ||
                categories.find(c => c.name.includes(catInput));
  }

  // 3. 如果未匹配到分类，则视为全局剧名关键词搜索
  if (!targetCat) {
    logger.info(`🔍 未匹配到分类，按剧名关键词在全库检索: "${catInput}"`);
    await runStage('inspect', config, logger, { show: catInput });
    return;
  }

  // 4. 用户选定了分类，列出该分类下的所有剧集文件夹
  console.log(`\n⏳ 正在获取 [${targetCat.name}] 目录下的剧集文件夹列表...`);
  let showDirs = [];
  try {
    const catFiles = await cd2.listFiles(targetCat.path);
    showDirs = catFiles.filter(f => f.directory);
  } catch (err) {
    logger.error(`读取分类目录 ${targetCat.path} 失败: ${err.message}`);
    return;
  }

  if (!showDirs.length) {
    console.log(`⚠️ 分类 [${targetCat.name}] 下暂无剧集文件夹`);
    return;
  }

  console.log(`\n${'═'.repeat(54)}`);
  console.log(`📂 [${targetCat.name}] 剧集文件夹列表 (共 ${showDirs.length} 部剧):`);
  console.log(`${'═'.repeat(54)}`);

  const maxDisplay = 60;
  const displayCount = Math.min(showDirs.length, maxDisplay);
  for (let i = 0; i < displayCount; i++) {
    const num = String(i + 1).padStart(3, ' ');
    console.log(`  [${num}] ${showDirs[i].name}`);
  }
  if (showDirs.length > maxDisplay) {
    console.log(`  ... 其余 ${showDirs.length - maxDisplay} 部已折叠 (输入剧名关键词可快速过滤筛选) ...`);
  }
  console.log(`${'═'.repeat(54)}`);

  // 5. 提示用户选择或输入剧集名称
  const showPrompt =
    `  👉 请选择要初检的剧集:\n` +
    `     • 输入序号 (单选如 1，多选如 1,3，或区间 1-3)\n` +
    `     • 输入 "all" 初检该分类全部剧集\n` +
    `     • 手动输入/粘贴文件夹名称，或输入关键词\n` +
    `     (直接回车取消) > `;

  const showChoice = (await ask(showPrompt)).trim();

  if (!showChoice) {
    console.log('  ⚠️ 操作已取消');
    return;
  }

  // 6. 处理 "all"
  if (showChoice.toLowerCase() === 'all') {
    logger.info(`🎯 初检整分类: [${targetCat.name}]`);
    await runStage('inspect', config, logger, { path: targetCat.path });
    return;
  }

  // 7. 处理序号输入 (支持单个数字，逗号隔开，或破折号区间如 1-3)
  const isNumberSelection = /^(\d+)([\s,，-]\d+)*$/.test(showChoice);
  if (isNumberSelection) {
    const selectedIndices = parseIndices(showChoice, showDirs.length);
    if (selectedIndices.length === 1) {
      const selected = showDirs[selectedIndices[0] - 1];
      logger.info(`🎯 初检指定剧集: [${targetCat.name}] ${selected.name}`);
      await runStage('inspect', config, logger, { path: selected.path });
      return;
    } else if (selectedIndices.length > 1) {
      const selectedNames = selectedIndices.map(idx => showDirs[idx - 1].name);
      console.log(`🎯 已选中 ${selectedNames.length} 部剧集:`);
      selectedNames.forEach(n => console.log(`   - ${n}`));
      for (const idx of selectedIndices) {
        const item = showDirs[idx - 1];
        await runStage('inspect', config, logger, { path: item.path });
      }
      return;
    }
  }

  // 8. 处理文本输入（文件夹完整名称匹配 或 模糊关键词匹配）
  const exactMatch = showDirs.find(d => d.name.toLowerCase() === showChoice.toLowerCase());
  if (exactMatch) {
    logger.info(`🎯 匹配到文件夹: ${exactMatch.name}`);
    await runStage('inspect', config, logger, { path: exactMatch.path });
    return;
  }

  const fuzzyMatches = showDirs.filter(d => d.name.toLowerCase().includes(showChoice.toLowerCase()));
  if (fuzzyMatches.length === 1) {
    logger.info(`🎯 关键词精准匹配到 1 个文件夹: ${fuzzyMatches[0].name}`);
    await runStage('inspect', config, logger, { path: fuzzyMatches[0].path });
    return;
  } else if (fuzzyMatches.length > 1) {
    console.log(`\n🔍 关键词 "${showChoice}" 在该分类匹配到 ${fuzzyMatches.length} 个文件夹:`);
    fuzzyMatches.forEach((m, idx) => console.log(`  [${idx + 1}] ${m.name}`));
    const subChoice = (await ask(`  👉 请输入序号选择 (1-${fuzzyMatches.length})，按回车初检全部匹配项: `)).trim();
    const subIdx = parseInt(subChoice, 10);
    if (!isNaN(subIdx) && subIdx >= 1 && subIdx <= fuzzyMatches.length) {
      const pick = fuzzyMatches[subIdx - 1];
      logger.info(`🎯 初检指定剧集: ${pick.name}`);
      await runStage('inspect', config, logger, { path: pick.path });
    } else {
      logger.info(`🎯 初检全部 ${fuzzyMatches.length} 个匹配项...`);
      for (const m of fuzzyMatches) {
        await runStage('inspect', config, logger, { path: m.path });
      }
    }
    return;
  }

  // 若均未匹配到，调用通用初检
  logger.info(`🎯 未在 [${targetCat.name}] 中发现同名文件夹，尝试按关键词初检: "${showChoice}"`);
  await runStage('inspect', config, logger, { path: targetCat.path, show: showChoice });
}
