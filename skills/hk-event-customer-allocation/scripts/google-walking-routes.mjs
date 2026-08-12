#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";

const GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json";
const MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix";
const BATCH_SIZE = 25;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithRetry(url, options = {}, attempts = 4) {
  let lastError;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(url, options);
      if (response.ok) return response;
      const detail = await response.text();
      if (response.status < 500 && response.status !== 429) {
        throw new Error(`地圖服務拒絕請求（HTTP ${response.status}）：${detail.slice(0, 200)}`);
      }
      lastError = new Error(`地圖服務暫時不可用（HTTP ${response.status}）。`);
    } catch (error) {
      lastError = error;
    }
    await sleep(500 * (2 ** attempt));
  }
  throw lastError;
}

async function geocodeAddress(address, apiKey) {
  const url = new URL(GEOCODE_URL);
  url.searchParams.set("address", address);
  url.searchParams.set("region", "hk");
  url.searchParams.set("language", "zh-HK");
  url.searchParams.set("key", apiKey);
  const response = await fetchWithRetry(url);
  const data = await response.json();
  if (data.status !== "OK" || !data.results?.length) {
    throw new Error(`地址定位失敗：${data.status ?? "UNKNOWN"}`);
  }
  const result = data.results[0];
  return {
    lat: Number(result.geometry.location.lat),
    lng: Number(result.geometry.location.lng),
    formatted_address: result.formatted_address,
    partial_match: Boolean(result.partial_match),
  };
}

function routeWaypoint(point) {
  return {
    waypoint: {
      location: { latLng: { latitude: point.lat, longitude: point.lng } },
    },
  };
}

async function computeMatrix(origins, destinations, apiKey) {
  const response = await fetchWithRetry(MATRIX_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Goog-Api-Key": apiKey,
      "X-Goog-FieldMask": "originIndex,destinationIndex,distanceMeters,duration,status,condition",
    },
    body: JSON.stringify({
      origins: origins.map(routeWaypoint),
      destinations: destinations.map(routeWaypoint),
      travelMode: "WALK",
      languageCode: "zh-HK",
      regionCode: "HK",
    }),
  });
  return response.json();
}

async function enrichCoordinates(raw, apiKey) {
  const issues = [...(Array.isArray(raw.issues) ? raw.issues : [])];
  const sourcePoints = [
    { ...raw.venue, id: "venue", role: "場地" },
    ...(raw.customers ?? []).map((customer, index) => ({
      ...customer,
      id: String(customer.id ?? index + 1),
      role: "客戶",
    })),
  ];
  const points = [];
  for (const point of sourcePoints) {
    const address = String(point.address ?? "").trim();
    if (!address) {
      issues.push({ issue_type: "缺少地址", original_id: point.id, suggestion: "補充完整地址後重新計算" });
      continue;
    }
    try {
      const located = Number.isFinite(Number(point.lat)) && Number.isFinite(Number(point.lng))
        ? { lat: Number(point.lat), lng: Number(point.lng), formatted_address: address, partial_match: false }
        : await geocodeAddress(address, apiKey);
      points.push({ ...point, ...located });
      if (located.partial_match) {
        issues.push({ issue_type: "地址部分匹配", original_id: point.id, suggestion: `核實定位結果：${located.formatted_address}` });
      }
    } catch (error) {
      issues.push({ issue_type: "地址定位失敗", original_id: point.id, suggestion: error.message });
    }
  }
  return { points, issues };
}

async function buildWalkingMatrix(points, apiKey, fullMatrix) {
  const matrix = {};
  const origins = fullMatrix ? points : points.filter((point) => point.id === "venue");
  for (let oi = 0; oi < origins.length; oi += BATCH_SIZE) {
    const originBatch = origins.slice(oi, oi + BATCH_SIZE);
    for (let di = 0; di < points.length; di += BATCH_SIZE) {
      const destinationBatch = points.slice(di, di + BATCH_SIZE);
      const elements = await computeMatrix(originBatch, destinationBatch, apiKey);
      for (const element of elements) {
        if (element.condition !== "ROUTE_EXISTS" || !Number.isFinite(Number(element.distanceMeters))) continue;
        const origin = originBatch[Number(element.originIndex)];
        const destination = destinationBatch[Number(element.destinationIndex)];
        if (!origin || !destination || origin.id === destination.id) continue;
        matrix[`${origin.id}|${destination.id}`] = Number((Number(element.distanceMeters) / 1000).toFixed(3));
      }
    }
  }
  return matrix;
}

async function main() {
  const args = process.argv.slice(2);
  const fullMatrix = args.includes("--full-matrix");
  const positional = args.filter((arg) => arg !== "--full-matrix");
  const [inputPath, outputPath] = positional;
  if (!inputPath || !outputPath) {
    throw new Error("用法：node google-walking-routes.mjs input.json output.json [--full-matrix]");
  }
  const apiKey = process.env.GOOGLE_MAPS_API_KEY;
  if (!apiKey) throw new Error("缺少環境變數 GOOGLE_MAPS_API_KEY；請先安全配置，勿在對話中貼出金鑰。 ");

  const raw = JSON.parse(await fs.readFile(inputPath, "utf8"));
  const { points, issues } = await enrichCoordinates(raw, apiKey);
  const venue = points.find((point) => point.id === "venue");
  if (!venue) throw new Error("活動場地地址無法定位，已停止計算。 ");

  const matrix = await buildWalkingMatrix(points, apiKey, fullMatrix);
  const customers = [];
  for (const point of points.filter((item) => item.id !== "venue")) {
    const venueDistance = matrix[`venue|${point.id}`];
    if (!Number.isFinite(venueDistance)) {
      issues.push({ issue_type: "步行路線不可達", original_id: point.id, suggestion: "核實地址或改用人工地圖檢查" });
      continue;
    }
    const { role, formatted_address, partial_match, ...customer } = point;
    customers.push({ ...customer, distance_km: Number(venueDistance.toFixed(2)) });
  }

  const output = {
    ...raw,
    venue: { ...raw.venue, id: "venue", lat: venue.lat, lng: venue.lng },
    customers,
    walking_matrix: matrix,
    issues,
    distance_source: "Google Routes API WALK",
    walking_warning: "步行路線可能缺少部分行人道或步行路徑，外勤前請按現場情況核實。",
  };
  await fs.mkdir(path.dirname(path.resolve(outputPath)), { recursive: true });
  await fs.writeFile(outputPath, `${JSON.stringify(output, null, 2)}\n`, "utf8");
  process.stdout.write(`已取得 ${customers.length} 個客戶的步行距離；未輸出或記錄 API 金鑰。\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
});
