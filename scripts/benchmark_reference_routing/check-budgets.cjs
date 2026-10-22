#!/usr/bin/env node
/** Check complete controlled policy-switch reports against the accepted budgets. */
'use strict';
const fs = require('node:fs');
const names = ['later-node-compact','arrays-default','later-node-default','later-node-inline',
  'aliases-default','cycle-default','self-loop-default','fields-default','arrays-compact',
  'dense-24','dense-48','fan-in-12','fan-in-48','many-groups-12x4'];
const fresh = new Set(['dense-48','fan-in-48','many-groups-12x4']);
const representative = new Set(names.slice(0,9));
const paths = process.argv.slice(2);
if (paths.length !== 2) {
  process.stderr.write('Usage: node scripts/benchmark_reference_routing/check-budgets.cjs independent.json shared.json\n');
  process.exit(2);
}
let failed = false;
for (const [index,path] of paths.entries()) {
  const report = JSON.parse(fs.readFileSync(path,'utf8'));
  const policy = index === 0 ? 'independent' : 'shared';
  const check = (condition,message) => {
    if (!condition) { failed = true; process.stderr.write(`FAIL ${policy}: ${message}\n`); }
  };
  check(report.routingPolicy === policy,'wrong routing policy');
  check(report.initialization?.mode === 'policy-switch','original policy-switch protocol required');
  check(report.results?.length === names.length,'complete 14-case corpus required');
  for (const name of names) {
    const matching = report.results?.filter(result => result.name === name) ?? [];
    check(matching.length === 1,`${name}: exactly one result required`);
    const result = matching[0];
    if (!result) continue;
    check(!result.error,`${name}: ${result.error}`);
    check(result.sharing?.baselineValid === true,`${name}: valid controlled baseline required`);
    const layouts = result.samples?.layout ?? [], redraws = result.samples?.redrawWithValueLayout ?? [];
    check(layouts.length === 6 && layouts.every(value => Number.isFinite(value) && value >= 0),`${name}: six finite fresh-layout samples required`);
    check(redraws.length === 40 && redraws.every(value => Number.isFinite(value) && value >= 0),`${name}: 40 finite full-redraw samples required`);
    if (fresh.has(name)) {
      const max = Math.max(...layouts);
      check(layouts.length === 6 && max <= 300,`${name}: fresh maximum ${max.toFixed(1)} ms exceeds 300 ms`);
      process.stdout.write(`${policy} ${name}: fresh maximum ${max.toFixed(1)} ms / 300 ms\n`);
    }
    if (representative.has(name) || name === 'dense-48') {
      const sorted = [...redraws].sort((a,b) => a-b), p95 = sorted[Math.ceil(sorted.length*.95)-1];
      const limit = name === 'dense-48' ? 50 : 16;
      check(Number.isFinite(p95) && p95 <= limit,`${name}: full-redraw p95 ${p95} ms exceeds ${limit} ms`);
    }
  }
}
process.exitCode = failed ? 1 : 0;
