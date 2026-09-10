#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const EPS = 1e-9;

function cleanText(value) {
  return String(value ?? "").trim().replace(/\s+/gu, " ");
}

export function customerWeight(type) {
  const normalized = cleanText(type).toLowerCase();
  return /診所|诊所|clinic/u.test(normalized) ? 1.5 : 1.0;
}

function haversineKm(a, b) {
  if (![a?.lat, a?.lng, b?.lat, b?.lng].every(Number.isFinite)) return null;
  const toRad = (value) => (value * Math.PI) / 180;
  const earthKm = 6371.0088;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h = Math.sin(dLat / 2) ** 2
    + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * earthKm * Math.asin(Math.min(1, Math.sqrt(h)));
}

function matrixDistance(matrix, fromId, toId) {
  const direct = Number(matrix?.[`${fromId}|${toId}`]);
  if (Number.isFinite(direct)) return direct;
  const reverse = Number(matrix?.[`${toId}|${fromId}`]);
  return Number.isFinite(reverse) ? reverse : null;
}

function pairDistance(input, a, b) {
  return matrixDistance(input.walking_matrix, a.id, b.id) ?? haversineKm(a, b);
}

function validateInput(raw) {
  if (!raw || typeof raw !== "object") throw new Error("輸入必須是 JSON 物件。 ");
  const venue = {
    id: "venue",
    name: cleanText(raw.venue?.name),
    address: cleanText(raw.venue?.address),
    lat: Number(raw.venue?.lat),
    lng: Number(raw.venue?.lng),
  };
  if (!venue.name || !venue.address) throw new Error("缺少活動場地名稱或完整地址。 ");

  if (!Array.isArray(raw.teams) || raw.teams.length === 0) {
    throw new Error("至少需要一個銷售小組。 ");
  }
  const seenTeams = new Set();
  const teams = raw.teams.map((team, index) => {
    const name = cleanText(team?.name);
    const members = [...new Set((team?.members ?? []).map(cleanText).filter(Boolean))];
    if (!name) throw new Error(`第 ${index + 1} 個小組缺少名稱。`);
    if (seenTeams.has(name)) throw new Error(`小組名稱重複：${name}`);
    if (members.length === 0) throw new Error(`小組「${name}」的名單人數為零。`);
    seenTeams.add(name);
    return { name, members };
  });

  if (!Array.isArray(raw.customers) || raw.customers.length === 0) {
    throw new Error("沒有可分配的客戶。 ");
  }
  const seenIds = new Set();
  const customers = raw.customers.map((customer, index) => {
    const id = cleanText(customer?.id || index + 1);
    const type = cleanText(customer?.type);
    const name = cleanText(customer?.name);
    const address = cleanText(customer?.address);
    const phone = cleanText(customer?.phone);
    const distanceKm = Number(customer?.distance_km);
    const lat = Number(customer?.lat);
    const lng = Number(customer?.lng);
    if (seenIds.has(id)) throw new Error(`客戶唯一序號重複：${id}`);
    if (!type || !name || !address) throw new Error(`客戶 ${id} 缺少類型、名稱或地址。`);
    if (!Number.isFinite(distanceKm) || distanceKm < 0) {
      throw new Error(`客戶 ${id} 缺少有效步行距離。`);
    }
    if (![lat, lng].every(Number.isFinite)) throw new Error(`客戶 ${id} 缺少有效定位座標。`);
    seenIds.add(id);
    return {
      id, type, name, address, phone, distance_km: distanceKm, lat, lng,
      weight: customerWeight(type),
    };
  });

  const allocationDistanceLimitKm = Number(raw.allocation_distance_limit_km ?? 4);
  if (!Number.isFinite(allocationDistanceLimitKm) || allocationDistanceLimitKm <= 0) {
    throw new Error("分配步行距離上限必須是大於零的公里數。 ");
  }

  return {
    venue,
    teams,
    customers,
    allocation_distance_limit_km: allocationDistanceLimitKm,
    walking_matrix: raw.walking_matrix ?? {},
    issues: Array.isArray(raw.issues) ? raw.issues : [],
  };
}

function mean(values) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}

function typeCounts(customers) {
  const counts = {};
  for (const customer of customers) counts[customer.type] = (counts[customer.type] ?? 0) + 1;
  return counts;
}

function geographyPenalty(input, customer, assigned, scaleKm) {
  if (assigned.length === 0) return 0;
  const distances = assigned
    .map((other) => pairDistance(input, customer, other))
    .filter(Number.isFinite);
  if (distances.length === 0) return 1;
  return Math.min(2, mean(distances) / Math.max(scaleKm, 0.5));
}

function assignmentScore(input, state, customer, targets) {
  const projectedWorkloadPerPerson = (state.workload + customer.weight) / state.headcount;
  const projectedCountPerPerson = (state.customers.length + 1) / state.headcount;
  const projectedTypeCount = (state.type_counts[customer.type] ?? 0) + 1;
  const targetTypeCount = targets.type_totals[customer.type] * state.headcount / targets.total_headcount;

  const workloadPenalty = Math.abs(projectedWorkloadPerPerson - targets.workload_per_person)
    / Math.max(targets.workload_per_person, 0.5);
  const countPenalty = Math.abs(projectedCountPerPerson - targets.count_per_person)
    / Math.max(targets.count_per_person, 0.5);
  const typePenalty = Math.abs(projectedTypeCount - targetTypeCount) / Math.max(targetTypeCount, 1);
  const geoPenalty = geographyPenalty(input, customer, state.customers, targets.geo_scale_km);

  return 0.45 * workloadPenalty + 0.10 * countPenalty + 0.25 * geoPenalty + 0.20 * typePenalty;
}

function addCustomer(state, customer) {
  state.customers.push(customer);
  state.workload += customer.weight;
  state.type_counts[customer.type] = (state.type_counts[customer.type] ?? 0) + 1;
}

function removeCustomer(state, customer) {
  const index = state.customers.findIndex((item) => item.id === customer.id);
  if (index < 0) return;
  state.customers.splice(index, 1);
  state.workload -= customer.weight;
  state.type_counts[customer.type] -= 1;
  if (state.type_counts[customer.type] === 0) delete state.type_counts[customer.type];
}

function localPairPenalty(input, source, destination, customer, targets, afterMove) {
  const sourceWorkload = source.workload - (afterMove ? customer.weight : 0);
  const destinationWorkload = destination.workload + (afterMove ? customer.weight : 0);
  const sourceCount = source.customers.length - (afterMove ? 1 : 0);
  const destinationCount = destination.customers.length + (afterMove ? 1 : 0);
  const typeTargetSource = targets.type_totals[customer.type] * source.headcount / targets.total_headcount;
  const typeTargetDestination = targets.type_totals[customer.type] * destination.headcount / targets.total_headcount;
  const sourceType = (source.type_counts[customer.type] ?? 0) - (afterMove ? 1 : 0);
  const destinationType = (destination.type_counts[customer.type] ?? 0) + (afterMove ? 1 : 0);

  const workload = (
    Math.abs(sourceWorkload / source.headcount - targets.workload_per_person)
    + Math.abs(destinationWorkload / destination.headcount - targets.workload_per_person)
  ) / Math.max(targets.workload_per_person, 0.5);
  const count = (
    Math.abs(sourceCount / source.headcount - targets.count_per_person)
    + Math.abs(destinationCount / destination.headcount - targets.count_per_person)
  ) / Math.max(targets.count_per_person, 0.5);
  const type = (
    Math.abs(sourceType - typeTargetSource) / Math.max(typeTargetSource, 1)
    + Math.abs(destinationType - typeTargetDestination) / Math.max(typeTargetDestination, 1)
  );
  const geo = afterMove
    ? geographyPenalty(input, customer, destination.customers, targets.geo_scale_km)
    : geographyPenalty(input, customer, source.customers.filter((item) => item.id !== customer.id), targets.geo_scale_km);
  return 0.55 * workload + 0.10 * count + 0.20 * type + 0.15 * geo;
}

function rebalance(input, states, targets) {
  const maxIterations = Math.min(100, input.customers.length * 2);
  for (let iteration = 0; iteration < maxIterations; iteration += 1) {
    const ranked = [...states].sort((a, b) => (b.workload / b.headcount) - (a.workload / a.headcount));
    const source = ranked[0];
    const destination = ranked.at(-1);
    if (source === destination || source.customers.length <= 1) break;

    let best = null;
    for (const customer of source.customers) {
      const before = localPairPenalty(input, source, destination, customer, targets, false);
      const after = localPairPenalty(input, source, destination, customer, targets, true);
      const improvement = before - after;
      if (improvement > (best?.improvement ?? EPS)) best = { customer, improvement };
    }
    if (!best || best.improvement <= EPS) break;
    removeCustomer(source, best.customer);
    addCustomer(destination, best.customer);
  }
}

function buildRoute(input, customers) {
  const remaining = [...customers];
  const ordered = [];
  let current = input.venue;
  let allWalkingLegs = true;
  while (remaining.length) {
    let bestIndex = 0;
    let bestDistance = Infinity;
    let bestWalking = false;
    for (let index = 0; index < remaining.length; index += 1) {
      const candidate = remaining[index];
      const walking = matrixDistance(input.walking_matrix, current.id, candidate.id);
      const distance = walking ?? haversineKm(current, candidate) ?? Infinity;
      if (distance < bestDistance - EPS || (Math.abs(distance - bestDistance) <= EPS && candidate.id < remaining[bestIndex].id)) {
        bestIndex = index;
        bestDistance = distance;
        bestWalking = walking !== null;
      }
    }
    const [next] = remaining.splice(bestIndex, 1);
    allWalkingLegs &&= bestWalking;
    ordered.push({ customer: next, leg_distance_km: Number.isFinite(bestDistance) ? bestDistance : null });
    current = next;
  }
  return { ordered, method: allWalkingLegs ? "實際步行距離矩陣" : "地理聚集估算" };
}

export function allocate(raw) {
  const input = validateInput(raw);
  const farCustomers = input.customers
    .filter((customer) => customer.distance_km > input.allocation_distance_limit_km)
    .map((customer) => ({
      ...customer,
      exclusion_reason: `實際步行距離超過 ${input.allocation_distance_limit_km.toFixed(2)} KM，不分配予銷售小組`,
    }));
  input.customers = input.customers.filter((customer) => customer.distance_km <= input.allocation_distance_limit_km);
  if (input.customers.length === 0) {
    throw new Error(`沒有步行距離不超過 ${input.allocation_distance_limit_km.toFixed(2)} KM 的可分配客戶。`);
  }
  const totalHeadcount = input.teams.reduce((sum, team) => sum + team.members.length, 0);
  const totalWorkload = input.customers.reduce((sum, customer) => sum + customer.weight, 0);
  const totalsByType = typeCounts(input.customers);
  const targets = {
    total_headcount: totalHeadcount,
    workload_per_person: totalWorkload / totalHeadcount,
    count_per_person: input.customers.length / totalHeadcount,
    type_totals: totalsByType,
    geo_scale_km: Math.max(1, ...input.customers.map((customer) => customer.distance_km)),
  };

  const states = input.teams.map((team) => ({
    name: team.name,
    members: team.members,
    headcount: team.members.length,
    customers: [],
    workload: 0,
    type_counts: {},
  }));

  const typeFrequencies = totalsByType;
  const orderedCustomers = [...input.customers].sort((a, b) =>
    (b.weight - a.weight)
    || (typeFrequencies[a.type] - typeFrequencies[b.type])
    || (b.distance_km - a.distance_km)
    || a.id.localeCompare(b.id, "zh-HK"));

  for (const customer of orderedCustomers) {
    const candidates = states
      .map((state) => ({ state, score: assignmentScore(input, state, customer, targets) }))
      .sort((a, b) => (a.score - b.score) || a.state.name.localeCompare(b.state.name, "zh-HK"));
    addCustomer(candidates[0].state, customer);
  }

  rebalance(input, states, targets);

  const assignments = [];
  const summaryGroups = [];
  for (const state of states.sort((a, b) => a.name.localeCompare(b.name, "zh-HK"))) {
    const route = buildRoute(input, state.customers);
    route.ordered.forEach(({ customer, leg_distance_km }, index) => assignments.push({
      ...customer,
      group: state.name,
      route_order: index + 1,
      route_leg_km: leg_distance_km,
      route_method: route.method,
    }));
    const distances = state.customers.map((customer) => customer.distance_km);
    summaryGroups.push({
      name: state.name,
      members: state.members,
      headcount: state.headcount,
      customer_count: state.customers.length,
      workload: Number(state.workload.toFixed(1)),
      workload_per_person: Number((state.workload / state.headcount).toFixed(3)),
      average_distance_km: Number(mean(distances).toFixed(2)),
      farthest_distance_km: Number(Math.max(0, ...distances).toFixed(2)),
      type_counts: { ...state.type_counts },
      route_method: route.method,
    });
  }

  const perPersonLoads = summaryGroups.map((group) => group.workload_per_person);
  return {
    venue: input.venue,
    parameters: {
      clinic_weight: 1.5,
      other_weight: 1.0,
      distance_mode: "步行距離",
      allocation_distance_limit_km: input.allocation_distance_limit_km,
      score_weights: { workload: 0.45, count: 0.10, geography: 0.25, type: 0.20 },
    },
    totals: {
      headcount: totalHeadcount,
      customers: input.customers.length,
      workload: Number(totalWorkload.toFixed(1)),
      clinic_customers: input.customers.filter((customer) => customer.weight === 1.5).length,
      type_counts: totalsByType,
      max_min_workload_per_person_gap: Number((Math.max(...perPersonLoads) - Math.min(...perPersonLoads)).toFixed(3)),
    },
    groups: summaryGroups,
    assignments,
    allocation_distance_limit_km: input.allocation_distance_limit_km,
    far_customers: farCustomers,
    issues: input.issues,
    warning: "步行路線可能缺少部分行人道或步行路徑，外勤前請按現場情況核實。",
  };
}

async function main() {
  const [inputPath, outputPath] = process.argv.slice(2);
  if (!inputPath || !outputPath) {
    throw new Error("用法：node allocation-engine.mjs input.json plan.json");
  }
  const raw = JSON.parse(await fs.readFile(inputPath, "utf8"));
  const plan = allocate(raw);
  await fs.mkdir(path.dirname(path.resolve(outputPath)), { recursive: true });
  await fs.writeFile(outputPath, `${JSON.stringify(plan, null, 2)}\n`, "utf8");
  process.stdout.write(`已生成分配方案：${outputPath}\n`);
}

const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : "";
if (invokedPath === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}
