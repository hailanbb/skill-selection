import assert from "node:assert/strict";
import test from "node:test";
import { allocate, customerWeight } from "../scripts/allocation-engine.mjs";

function sampleInput() {
  const teams = [
    { name: "A組", members: ["甲", "乙"] },
    { name: "B組", members: ["丙", "丁", "戊"] },
    { name: "C組", members: ["己"] },
  ];
  const types = ["中醫診所", "藥房", "健身中心", "西醫診所", "美容院", "護老院"];
  const customers = Array.from({ length: 24 }, (_, index) => ({
    id: String(index + 1),
    type: types[index % types.length],
    name: `客戶${index + 1}`,
    address: `香港測試地址${index + 1}號`,
    phone: `2800${String(index).padStart(4, "0")}`,
    distance_km: Number((0.25 + index * 0.09).toFixed(2)),
    lat: 22.28 + (index % 6) * 0.004,
    lng: 114.15 + Math.floor(index / 6) * 0.005,
  }));
  return {
    venue: { name: "測試商場", address: "香港測試道1號", lat: 22.28, lng: 114.15 },
    teams,
    customers,
    walking_matrix: Object.fromEntries(customers.map((customer) => [`venue|${customer.id}`, customer.distance_km])),
    issues: [],
  };
}

test("診所工作量比其他類型高 50%", () => {
  assert.equal(customerWeight("中醫診所"), 1.5);
  assert.equal(customerWeight("Clinic"), 1.5);
  assert.equal(customerWeight("藥房"), 1.0);
});

test("按名單人數完成完整、唯一且可重現的分配", () => {
  const first = allocate(sampleInput());
  const second = allocate(sampleInput());
  assert.equal(first.assignments.length, 24);
  assert.equal(new Set(first.assignments.map((item) => item.id)).size, 24);
  assert.deepEqual(first.assignments, second.assignments);
  assert.equal(first.groups.reduce((sum, group) => sum + group.headcount, 0), 6);
  assert.ok(first.totals.max_min_workload_per_person_gap <= 0.5);
});

test("缺少步行距離時停止，不以直線距離冒充", () => {
  const input = sampleInput();
  delete input.customers[0].distance_km;
  assert.throws(() => allocate(input), /步行距離/u);
});

test("超過 4 KM 的客戶不進入小組並列入超距離清單", () => {
  const input = sampleInput();
  input.customers[0].distance_km = 4.01;
  const plan = allocate(input);
  assert.equal(plan.assignments.length, 23);
  assert.equal(plan.far_customers.length, 1);
  assert.equal(plan.far_customers[0].id, "1");
  assert.ok(plan.assignments.every((customer) => customer.distance_km <= 4));
  assert.match(plan.far_customers[0].exclusion_reason, /超過 4\.00 KM/u);
});

test("可用自訂距離上限取代預設 4 KM", () => {
  const input = sampleInput();
  input.allocation_distance_limit_km = 1;
  const plan = allocate(input);
  assert.ok(plan.assignments.every((customer) => customer.distance_km <= 1));
  assert.ok(plan.far_customers.every((customer) => customer.distance_km > 1));
  assert.equal(plan.allocation_distance_limit_km, 1);
});
