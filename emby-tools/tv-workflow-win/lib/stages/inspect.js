/**
 * 阶段一：剧集初检
 * 扫描 CloudDrive2 源目录，逐剧逐季核对本地集号与 TMDB 登记集数，生成报告
 *
 * 支持智能识别与多级路径过滤：
 * 1. 默认：扫描 config.paths.source 根目录下的全部可用分类与剧集
 * 2. 指定分类：通过 options.category 仅扫描特定分类（如 "华语剧"）
 * 3. 关键字过滤：通过 options.show 仅匹配特定剧名（如 "凡人修仙传"）
 * 4. 指定精确路径：通过 options.path 可直接指定网盘任意分类目录或单部剧目录，程序自适应识别
 */
import { CloudDriveClient } from '../clients/clouddrive2.js';
import { TMDBClient } from '../clients/tmdb.js';
import { showInfo, seasonNumber } from '../core/title-matcher.js';
import { episodeFromName, MEDIA_REGEX, range, uniq } from '../core/episode-parser.js';
import { writeReport } from '../core/report-adapter.js';
import { join, resolve } from 'node:path';
import { PROJECT_ROOT } from '../config.js';

/**
 * 执行初检阶段
 * @param {object} config - 完整配置
 * @param {object} logger
 * @param {object} [options] - 过滤与路径选项: { path?: string, category?: string, show?: string }
 * @returns {Promise<object>} 执行摘要
 */
export async function runInspect(config, logger, options = {}) {
  const cd2 = new CloudDriveClient({
    origin: config.clouddrive2.origin,
    token: config.clouddrive2.token,
    logger,
  });
  const tmdb = new TMDBClient({
    apiKey: config.tmdb?.apiKey || '',
    language: config.tmdb?.language || 'zh-CN',
    logger,
  });

  const origin = config.clouddrive2.origin;
  const basePath = (options.path || config.paths.source).replace(/\/+$/, '');
  const results = [];
  const summary = { total: 0, green: 0, blue: 0, yellow: 0, red: 0, noFill: 0, errors: [] };

  logger.info(`📂 正在连接 CloudDrive2，读取目标目录: ${basePath}`);

  let rootEntries;
  try {
    rootEntries = await cd2.listFiles(basePath);
  } catch (e) {
    throw new Error(`无法读取目标路径 ${basePath}: ${e.message}`);
  }

  // ── 智能识别目录层级 ──────────────────────────────────────────────────
  // 结构: Map<分类名, Array<{ name: string, path: string, directory: boolean, preloadedContents?: Array }>>
  const categoryMap = new Map();

  // 1. 判断是否直接是“单部剧集目录”（自身直接包含 Season 1、Season 2 等）
  const isSingleShow = rootEntries.some(f => f.directory && seasonNumber(f.name) !== null);

  if (isSingleShow) {
    const showName = basePath.split('/').pop();
    const parts = basePath.split('/');
    const catName = parts.length > 2 ? parts[parts.length - 2] : '指定剧集';
    logger.info(`🎯 目标识别为【单部剧集】: [${catName}] ${showName}`);
    categoryMap.set(catName, [{
      name: showName,
      path: basePath,
      directory: true,
      preloadedContents: rootEntries,
    }]);
  } else {
    // 2. 检查是否是某个“剧集分类目录”（子项是各个剧集目录，剧集内部包含 Season）
    const dirEntries = rootEntries.filter(f => f.directory);
    let isCategoryDir = false;

    if (dirEntries.length > 0) {
      try {
        const sample = await cd2.listFiles(dirEntries[0].path);
        if (sample.some(f => (f.directory && seasonNumber(f.name) !== null) || MEDIA_REGEX.test(f.name))) {
          isCategoryDir = true;
        }
      } catch {
        // 采样检测出错，继续向下判定
      }
    }

    if (isCategoryDir) {
      const catName = basePath.split('/').pop();
      logger.info(`📂 目标识别为【单分类目录】: ${catName} (共 ${dirEntries.length} 部剧)`);
      categoryMap.set(catName, dirEntries);
    } else {
      // 3. 根目录（子项是多个分类，如 国产剧/欧美剧/动漫）
      logger.info(`📂 目标识别为【源根目录】: 包含 ${dirEntries.length} 个分类`);
      const showMatchesCategory = options.show && !options.category && dirEntries.some(cat => cat.name.includes(options.show));

      for (const cat of dirEntries) {
        if (options.category && !cat.name.includes(options.category)) {
          continue;
        }
        if (showMatchesCategory && !cat.name.includes(options.show)) {
          continue;
        }
        try {
          const shows = (await cd2.listFiles(cat.path)).filter(f => f.directory);
          categoryMap.set(cat.name, shows);
        } catch (e) {
          logger.warn(`  无法读取分类 ${cat.name}: ${e.message}`);
        }
      }
    }
  }

  // ── 剧名/分类关键字过滤 ────────────────────────────────────────────────
  if (options.show) {
    const kw = options.show.toLowerCase();
    for (const [catName, shows] of categoryMap) {
      // 若分类名本身直接命中关键字（如用户输入“香港剧集”），保留该分类下全部剧集
      if (catName.toLowerCase().includes(kw)) {
        continue;
      }
      const filtered = shows.filter(s => s.name.toLowerCase().includes(kw));
      if (filtered.length) {
        categoryMap.set(catName, filtered);
      } else {
        categoryMap.delete(catName);
      }
    }
    const matchCount = [...categoryMap.values()].reduce((sum, s) => sum + s.length, 0);
    logger.info(`🔍 过滤 [${options.show}]：共匹配到 ${matchCount} 部剧`);
  }

  const totalShows = [...categoryMap.values()].reduce((sum, s) => sum + s.length, 0);
  if (totalShows === 0) {
    logger.warn('⚠️ 未在指定范围内发现任何符合条件的剧集目录');
    return { ...summary, outputPath: null };
  }

  // ── 逐分类逐剧初检 ────────────────────────────────────────────────────
  let processed = 0;

  for (const [catName, shows] of categoryMap) {
    const sortedShows = [...shows].sort((a, b) => (a.modified || '').localeCompare(b.modified || ''));

    for (const show of sortedShows) {
      processed++;
      const info = showInfo(show.name);
      logger.progress('初检', processed, totalShows, `${catName} / ${show.name}`);

      // 列出季目录
      let showContents;
      if (show.preloadedContents) {
        showContents = show.preloadedContents;
      } else {
        try {
          showContents = await cd2.listFiles(show.path);
        } catch (e) {
          summary.errors.push({ show: show.name, error: e.message });
          continue;
        }
      }

      const seasonDirs = showContents
        .filter(f => f.directory && seasonNumber(f.name) !== null)
        .sort((a, b) => seasonNumber(a.name) - seasonNumber(b.name));

      if (!seasonDirs.length) {
        results.push({
          category: catName, name: show.name, season: null,
          path: show.path, showPath: show.path,
          link: `${origin}/?page=files&path=${encodeURIComponent(show.path)}`,
          data: { '分类': catName, '剧集目录': show.name, '季数': '', '处理结果': '无季目录' },
          color: 'other',
        });
        continue;
      }

      // 查询 TMDB（如果有 ID）
      if (info.tmdb && tmdb.apiKey) {
        try {
          await tmdb.getShowDetails(info.tmdb);
        } catch (e) {
          logger.warn(`  TMDB 查询失败: ${e.message}`);
        }
      }

      for (const sDir of seasonDirs) {
        const sNum = seasonNumber(sDir.name);
        summary.total++;

        let files;
        try {
          files = await cd2.listFiles(sDir.path);
        } catch (e) {
          summary.errors.push({ show: show.name, season: sNum, error: e.message });
          continue;
        }

        const videos = files.filter(f => !f.directory && MEDIA_REGEX.test(f.name));
        const episodes = videos
          .map(f => episodeFromName(f.name, sNum))
          .filter(n => n !== null);
        const identified = uniq(episodes);
        const duplicates = episodes.filter((n, idx) => episodes.indexOf(n) !== idx);
        const unknown = videos.filter(f => episodeFromName(f.name, sNum) === null).map(f => f.name);

        // 查询 TMDB 登记集数与播出状态
        let tmdbTotal = null, broadcastStatus = '未确认';
        if (info.tmdb && tmdb.apiKey) {
          try {
            const seasonDetail = await tmdb.getSeasonDetails(info.tmdb, sNum);
            if (seasonDetail?.episodes?.length) {
              tmdbTotal = seasonDetail.episodes.length;
              const lastEp = seasonDetail.episodes[seasonDetail.episodes.length - 1];
              const airDate = lastEp?.air_date ? new Date(lastEp.air_date) : null;
              if (airDate && airDate < new Date()) broadcastStatus = '已播完';
              else if (airDate) broadcastStatus = '连载中';
              else broadcastStatus = '未确认';
            }
          } catch {
            // TMDB 接口查询异常时跳过
          }
        }

        const total = tmdbTotal || identified.length || 0;
        const missing = tmdbTotal ? range(tmdbTotal).filter(n => !identified.includes(n)) : [];
        const isComplete = tmdbTotal && missing.length === 0;

        let color = 'other';
        if (isComplete && broadcastStatus === '已播完') {
          color = 'green'; summary.green++;
        } else if (broadcastStatus === '连载中') {
          color = 'blue'; summary.blue++;
        } else if (videos.length === 0) {
          color = 'red'; summary.red++;
        } else if (missing.length > 0 || unknown.length > 0 || uniq(duplicates).length > 0) {
          color = 'yellow'; summary.yellow++;
        } else {
          summary.noFill++;
        }

        const compact = arr => arr.length ? arr.join('、') : '';

        results.push({
          category: catName, name: show.name, season: sNum,
          path: sDir.path, showPath: show.path,
          link: `${origin}/?page=files&path=${encodeURIComponent(sDir.path)}`,
          data: {
            '分类': catName,
            '剧集目录': show.name,
            '季数': sNum,
            '源云存储链接': `${origin}/?page=files&path=${encodeURIComponent(sDir.path)}`,
            '视频文件数': videos.length,
            '已识别集数': identified.length,
            '来源登记集数': tmdbTotal || '',
            '已识别集号': compact(identified),
            '重复集号': compact(uniq(duplicates)),
            '缺失集号': tmdbTotal ? compact(missing) : '未确认',
            '无法识别集号的文件': compact(unknown),
            'TMDB ID': info.tmdb || '',
            '数据来源': tmdbTotal ? 'tmdb' : '',
            '播出状态': broadcastStatus,
            '处理结果': isComplete && broadcastStatus === '已播完' ? '齐全'
              : missing.length ? `缺 ${missing.length} 集` : '待核实',
            '待播集号': '',
            '播期未知集号': '',
            '报告版本': 'tv-workflow/1',
          },
          color,
        });

        logger.debug(`  Season ${sNum}: ${identified.length}/${total || '?'} 集, 标记: ${color}`);
      }
    }
  }

  // 写入初检报告
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const tag = options.show ? `_${options.show}` : options.category ? `_${options.category}` : '';
  const reportsDir = resolve(PROJECT_ROOT, 'reports');
  const outputPath = join(reportsDir, `初检报告${tag}_${timestamp}.xlsx`);
  await writeReport({ tasks: results, mode: 'inspect' }, outputPath);

  logger.info(`\n📊 初检完成: 共核对 ${summary.total} 季`);
  logger.info(`   🟢 齐全 ${summary.green}  🔵 连载 ${summary.blue}  🟡 待处理 ${summary.yellow}  🔴 空 ${summary.red}  ⬜ 其他 ${summary.noFill}`);
  logger.info(`   📄 报告: ${outputPath}`);

  return { ...summary, outputPath };
}
