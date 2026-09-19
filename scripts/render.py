#!/usr/bin/env python3
"""Package usage JSON as one self-contained, client-rendered HTML dashboard.

Usage: render.py [--in out/usage.json] [--out out/report.html] [--title ...]
                 [--theme light|dark] [--data-url URL]
Only --data-url enables a network request; embedded JSON is always the fallback.
"""
import argparse
import html
import json
from pathlib import Path


CSS = r"""
:root {
  color-scheme: light;
  --bg: #f5f6f8; --surface: #fff; --soft: #f0f3f7; --ink: #182438;
  --muted: #586579; --line: #dce2ea; --accent: #315dcc; --good: #146950;
  --good-bg: #eaf5ee; --quota: #283648; --hatch: #fff;
  --s0: #4163ca; --l0: #304a97; --s1: #167c70; --l1: #105c53;
  --s2: #8b50b9; --l2: #683c8b; --s3: #b56228; --l3: #88491e;
  --s4: #b13f66; --l4: #852f4c; --s5: #486b86; --l5: #365065;
  --s6: #73792b; --l6: #565b20; --s7: #916052; --l7: #6d483e;
  --ease-out: cubic-bezier(.22, 1, .36, 1); --micro: 160ms;
}
body[data-theme="dark"] {
  color-scheme: dark;
  --bg: #101720; --surface: #182230; --soft: #202e40; --ink: #edf2fa;
  --muted: #acb9ca; --line: #344459; --accent: #94b7ff; --good: #91dfba;
  --good-bg: #203b34; --quota: #f2f5fa; --hatch: #101720;
  --s0: #93adff; --l0: #7991de; --s1: #6fcab9; --l1: #56ac9a;
  --s2: #c29ae5; --l2: #a77bc9; --s3: #efb17f; --l3: #d19160;
  --s4: #ee9ab5; --l4: #cc7c97; --s5: #95b8d6; --l5: #7799b8;
  --s6: #c7ce81; --l6: #a6af66; --s7: #d3aa97; --l7: #b68b77;
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.6 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-variant-numeric: tabular-nums; }
main { max-width: 1440px; margin: auto; padding: 28px 40px 36px; }
h1, h2, h3, p { margin: 0; }
h1 { font-size: clamp(23px, 2.2vw, 30px); line-height: 1.3; letter-spacing: -.6px; text-wrap: balance; }
h2 { font-size: 19px; line-height: 1.4; }
h3 { font-size: 16px; }
button, summary, select { font: inherit; touch-action: manipulation; }
button, summary { cursor: pointer; }
button { min-height: 44px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); color: var(--ink); padding: 8px 14px; transition: opacity var(--micro) ease-out, transform var(--micro) ease-out; }
button:hover { opacity: .8; }
button:active { transform: scale(.98); }
button:disabled { cursor: wait; opacity: .6; }
:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
a { color: var(--accent); text-underline-offset: 4px; }
.sr-only { position: absolute; width: 1px; height: 1px; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.skip { position: absolute; z-index: 50; left: 16px; top: 12px; padding: 12px; background: var(--surface); transform: translateY(-200%); }
.skip:focus { transform: none; }
.header, .heading-row, .section-head, .chart-footer, .footer { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.header { align-items: flex-start; margin-bottom: 22px; }
.brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
.brand-mark { display: grid; place-items: center; width: 42px; height: 42px; border-radius: 12px; flex: none; color: var(--accent); background: var(--soft); border: 1px solid var(--line); }
.eyebrow { color: var(--muted); font-size: 12px; font-weight: 700; letter-spacing: 1.3px; margin-bottom: 2px; }
.meta, .sub, .micro { color: var(--muted); font-size: 13px; }
.meta { margin-top: 6px; }
.header-actions { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }
.heading-row { margin-bottom: 12px; }
.heading-row h2 { font-size: 15px; }
.overview { min-height: calc(100svh - 28px); }
.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(215px, 1fr)); gap: 12px; }
.metric { min-width: 0; padding: 16px 20px; background: var(--surface); border: 1px solid var(--line); border-radius: 12px; }
.model-label { font-size: 14px; display: flex; gap: 8px; align-items: center; overflow-wrap: anywhere; }
.amount { display: block; font-size: clamp(28px, 2.7vw, 38px); font-weight: 750; letter-spacing: -1px; line-height: 1.25; margin: 9px 0 5px; }
.swatch { width: 11px; height: 11px; border-radius: 3px; display: inline-block; flex: none; background: var(--series); }
.swatch.long { background: repeating-linear-gradient(135deg, transparent 0 3px, var(--hatch) 3px 4px), var(--series); }
.weekly { display: grid; grid-template-columns: minmax(240px, 1fr) 1.8fr; align-items: center; gap: 24px; padding: 18px 22px; margin-top: 16px; background: var(--soft); border: 1px solid var(--line); border-radius: 12px; }
.weekly h2 { font-size: 17px; margin-bottom: 4px; }
.weekly-values { display: grid; grid-template-columns: repeat(auto-fit, minmax(165px, 1fr)); gap: 16px; }
.weekly-stat { border-left: 2px solid var(--line); padding-left: 18px; min-width: 0; }
.weekly-amount { display: block; font-size: 27px; line-height: 1.35; font-weight: 750; }
.window-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
.window-card { border-top: 3px solid var(--series); }
.window-card .amount { font-size: 30px; }
.window-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 14px; margin: 12px 0 0; }
.window-stats div { min-width: 0; }
.window-stats dt { color: var(--muted); font-size: 12px; }
.window-stats dd { margin: 0; font-size: 15px; font-weight: 650; }
.panel { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 20px 22px; margin-top: 24px; min-width: 0; }
.section-head { align-items: flex-start; margin-bottom: 12px; }
.tabs { display: flex; flex-wrap: wrap; gap: 8px; }
.tabs button { min-width: 52px; font-size: 14px; }
.tabs [aria-selected="true"] { background: var(--ink); color: var(--surface); border-color: var(--ink); font-weight: 650; }
.legend { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 16px; margin: 10px 0 12px; font-size: 12px; color: var(--muted); }
.legend-item { display: inline-flex; align-items: center; gap: 6px; overflow-wrap: anywhere; }
.line-key { width: 22px; border-top: 2px dashed var(--quota); position: relative; }
.line-key::after { content: ''; position: absolute; width: 6px; height: 6px; border-radius: 50%; background: var(--quota); top: -4px; left: 8px; }
.chart-scroll, .table-scroll { overflow: auto; max-width: 100%; overscroll-behavior-x: contain; }
.chart-scroll { min-height: 265px; }
.chart-scroll svg { display: block; width: 100%; height: 265px; font-family: inherit; }
.gridline { stroke: var(--line); stroke-width: 1; }
.axis { fill: var(--muted); font-size: 12px; }
.axis-title { font-size: 12px; fill: var(--muted); font-weight: 600; }
.quota-line { fill: none; stroke: var(--quota); stroke-width: 2; stroke-dasharray: 4 4; }
.quota-dot { fill: var(--quota); stroke: var(--surface); stroke-width: 1.5; }
.day-hit { fill: transparent; cursor: pointer; }
.day-hit:hover, .day-hit:focus-visible { fill: var(--accent); fill-opacity: .07; stroke: var(--accent); stroke-width: 2; outline: none; }
.chart-footer { margin-top: 8px; align-items: flex-start; font-size: 12px; color: var(--muted); }
.chart-footer a { flex-shrink: 0; }
.empty { padding: 32px 12px; color: var(--muted); text-align: center; }
.empty-chart { min-height: 265px; display: grid; place-items: center; }
.details-area { padding-top: 24px; }
.disclosure { border: 1px solid var(--line); border-radius: 12px; background: var(--surface); margin-bottom: 14px; }
summary { list-style: none; padding: 16px 20px; min-height: 56px; font-weight: 650; display: flex; justify-content: space-between; gap: 16px; }
summary::-webkit-details-marker { display: none; }
summary::after { content: ''; width: 8px; height: 8px; border-right: 2px solid var(--muted); border-bottom: 2px solid var(--muted); transform: rotate(45deg); align-self: center; flex: none; transition: transform var(--micro) ease-out; }
details[open] > summary::after { transform: rotate(225deg); }
.detail-body { padding: 0 20px 20px; }
.detail-body > .sub { margin: 0 0 14px; }
.table-scroll { border: 1px solid var(--line); border-radius: 8px; }
table { width: 100%; border-collapse: collapse; white-space: nowrap; font-size: 13px; }
caption { text-align: left; padding: 10px 12px; color: var(--muted); font-size: 12px; background: var(--soft); }
th, td { padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: right; }
th { font-weight: 600; }
thead th, tfoot th, tfoot td { background: var(--soft); }
thead th { color: var(--muted); font-size: 12px; }
th:first-child, td:first-child { text-align: left; }
thead th[colspan] { text-align: center; }
tbody tr:last-child > * { border-bottom: 0; }
tbody tr:hover { background: var(--soft); }
.row-label { text-align: left; }
.table-model { display: flex; align-items: center; justify-content: center; gap: 6px; }
.cycle-section { margin-top: 26px; }
.cycle-section > .sub { margin-top: 5px; }
.cycle-groups { display: grid; gap: 24px; margin: 18px 0 24px; }
.cycle-account { min-width: 0; }
.account-title { display: flex; align-items: baseline; gap: 12px; margin-bottom: 8px; }
.account-title .micro { font-weight: 400; }
.cycle-row { display: grid; grid-template-columns: 320px minmax(80px, 1fr) 110px; align-items: center; gap: 16px; padding: 10px 12px; border-radius: 8px; font-size: 13px; }
.cycle-row.full { margin: 4px 0; }
.complete-mark { color: var(--good); font-size: 12px; }
.cycle-meta { display: flex; align-items: center; gap: 10px; min-width: 0; }
.cycle-meta time { overflow-wrap: anywhere; font-size: 12px; }
.badge { font-size: 12px; padding: 2px 7px; border-radius: 5px; white-space: nowrap; background: var(--soft); color: var(--muted); flex: none; }
.full .badge { background: var(--surface); color: var(--good); font-weight: 650; }
.cycle-track { height: 18px; background: var(--soft); border-radius: 4px; overflow: hidden; }
.cycle-fill { height: 100%; display: flex; transform-origin: left center; }
.cycle-fill > span { height: 100%; background: var(--series); }
.cycle-fill > .long { background: repeating-linear-gradient(135deg, transparent 0 4px, var(--hatch) 4px 5px), var(--series); }
.cycle-row { cursor: pointer; }
.cycle-row:hover { background: var(--soft); }
.cycle-value { text-align: right; font-weight: 650; }
.cycle-value small { display: block; font-size: 12px; color: var(--muted); font-weight: 400; }
.cycle-scale { display: flex; justify-content: space-between; color: var(--muted); font-size: 12px; margin: 12px 126px 0 348px; }
.caveats { color: var(--muted); font-size: 12px; line-height: 1.8; padding: 6px 2px; overflow-wrap: anywhere; }
.caveats h2 { font-size: 13px; color: var(--ink); margin: 8px 0; }
.caveats ul { padding-left: 18px; margin: 0; }
.footer { border-top: 1px solid var(--line); padding-top: 16px; margin-top: 24px; font-size: 12px; color: var(--muted); flex-wrap: wrap; }
.source-status { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.source-status button { font-size: 12px; }
.tooltip { position: fixed; z-index: 40; width: 370px; max-width: calc(100vw - 24px); max-height: min(580px, 70vh); overflow: auto; padding: 16px; color: var(--ink); background: var(--surface); border: 1px solid var(--line); border-radius: 12px; box-shadow: 0 12px 36px #0003; font-size: 13px; }
.tooltip[hidden] { display: none; }
.tip-title { display: flex; justify-content: space-between; gap: 12px; font-weight: 700; margin-bottom: 4px; }
.tip-model { border-top: 1px solid var(--line); padding-top: 8px; margin-top: 8px; }
.tip-label { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.tip-label .model-label { font-size: 12px; }
.tip-tokens { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 12px; color: var(--muted); }
.tooltip .sub { font-size: 12px; }
noscript { display: block; padding: 32px; text-align: center; }
@media (max-width: 1050px) {
  main { padding: 24px; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .section-head { flex-wrap: wrap; }
  .cycle-row { grid-template-columns: 245px minmax(70px, 1fr) 105px; gap: 12px; }
  .cycle-meta { align-items: flex-start; }
  .cycle-scale { margin-left: 269px; margin-right: 117px; }
}
@media (max-width: 640px) {
  main { padding: 20px 16px; }
  .header { gap: 12px; flex-wrap: wrap; }
  .brand-mark { display: none; }
  .header-actions { margin-left: auto; }
  .metric { padding: 14px; }
  .model-label { font-size: 12px; }
  .amount { font-size: 27px; }
  .weekly { grid-template-columns: 1fr; gap: 16px; padding: 18px; }
  .weekly-values { grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); }
  .weekly-stat { padding-left: 12px; }
  .heading-row { flex-wrap: wrap; gap: 4px; }
  .panel { padding: 16px 12px; }
  .chart-footer { flex-wrap: wrap; }
  .tabs button { padding: 8px 12px; }
  .cycle-row { grid-template-columns: 1fr 100px; gap: 8px; padding: 10px 8px; }
  .cycle-meta { grid-column: 1 / -1; }
  .cycle-scale { margin-left: 8px; margin-right: 116px; }
  .detail-body { padding: 0 12px 14px; }
  summary { padding: 14px; }
}
@media (max-width: 380px) { .metrics { grid-template-columns: 1fr; } }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
@media print {
  main { max-width: none; padding: 12px; }
  .overview { min-height: 0; }
  .header-actions, .tabs, .tooltip, .skip, .source-status button { display: none; }
  .panel, .weekly, .metric { break-inside: avoid; }
  body { print-color-adjust: exact; -webkit-print-color-adjust: exact; }
}
"""


JAVASCRIPT = r"""
'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const NS = 'http://www.w3.org/2000/svg';
  const config = JSON.parse($('report-config').textContent);
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  // motion.csv: subtle micro feedback; standard chart growth; subtle scroll reveal.
  const motion = {chart: 400, count: 480, reveal: 350, stagger: 30, ease: 'cubic-bezier(.22,1,.36,1)'};
  const money = value => '$' + Number(value).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const wholeMoney = value => '$' + Math.round(value).toLocaleString('en-US');
  const number = value => Number(value).toLocaleString('en-US', {maximumFractionDigits: 1});
  const creditApiNote = data => {
    const fallback = data.meta.credits_per_api_usd || 25;
    const standard = data.meta.subscription_prices?.['gpt-5.6-sol']?.standard;
    const reference = data.meta.api_reference_prices?.['gpt-5.6-sol'];
    const solRatio = standard?.input && reference?.input ? standard.input / reference.input : fallback;
    const basis = data.meta.api_equivalent_basis === 'current_api_standard_price' ? 'current API Standard rates' : 'API rates';
    return basis + '; Sol ' + number(solRatio) + ' credits per $1; default ' + number(fallback) + ' credits per $1';
  };
  const pct = value => value == null ? '—' : number(value) + '%';
  const tokens = value => {
    const divisor = value >= 1e9 ? 1e9 : value >= 1e6 ? 1e6 : 1e3, scaled = value / divisor;
    return scaled.toLocaleString('en-US', {maximumFractionDigits: scaled > 0 && scaled < 1 ? 3 : 2}) +
      (divisor === 1e9 ? ' B' : divisor === 1e6 ? ' M' : ' K');
  };
  const tokenNode = (value, label = '', tag = 'span') =>
    el(tag, value == null ? {} : {title: number(value) + ' tokens'}, value == null ? '—' : label + tokens(value));
  const family = key => key.replace(/\[1m\]$/, '');
  const isLong = key => key.endsWith('[1m]');
  const entries = bucket => Object.entries(bucket || {}).filter(([key, value]) => !key.startsWith('_') && value && typeof value === 'object');
  const sum = (values, field) => values.reduce((total, v) => total + (Number(v[field]) || 0), 0);
  const median = values => {
    if (!values.length) return null;
    const sorted = [...values].sort((a, b) => a - b), middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  };
  const blank = () => ({input: 0, cached: 0, output: 0, requests: 0, usd: 0, usd_standard: 0,
    credits_standard: 0, credits: 0, credits_fast: 0, api_usd_from_credits: 0,
    fast_requests: 0, standard_requests: 0, unknown_requests: 0});
  const merge = (target, source) => {
    for (const [key, value] of entries(source)) {
      if (!target.has(key)) target.set(key, blank());
      const dest = target.get(key);
      for (const field of Object.keys(dest)) dest[field] += Number(value[field]) || 0;
    }
    return target;
  };
  function el(tag, attrs = {}, text) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
    if (text != null) node.textContent = text;
    return node;
  }
  function svg(tag, attrs = {}, text) {
    const node = document.createElementNS(NS, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
    if (text != null) node.textContent = text;
    return node;
  }
  function replace(id, ...nodes) { $(id).replaceChildren(...nodes); }
  function validate(data) {
    const object = v => v && typeof v === 'object' && !Array.isArray(v);
    const finite = v => typeof v === 'number' && Number.isFinite(v) && v >= 0;
    const bucket = b => object(b) && Object.entries(b).every(([k, v]) => k.startsWith('_') ? (k !== '_usage_pct' || finite(v)) :
      object(v) && ['input', 'cached', 'output', 'requests', 'usd'].every(f => finite(v[f])));
    if (!object(data) || !object(data.meta) || !Array.isArray(data.meta.accounts) ||
        !data.meta.accounts.every(a => typeof a === 'string') || !object(data.daily) || !Array.isArray(data.cycles) ||
        !Object.entries(data.daily).every(([day, accounts]) => /^\d{4}-\d{2}-\d{2}$/.test(day) && object(accounts) && Object.values(accounts).every(bucket)) ||
        !data.cycles.every(c => object(c) && typeof c.account === 'string' && typeof c.start === 'string' && typeof c.end === 'string' &&
          typeof c.complete === 'boolean' && finite(c.usd) && bucket(c.by_model))) {
      throw new Error('Invalid usage JSON format');
    }
    const utc = v => typeof v === 'string' && /Z$/.test(v) && Number.isFinite(Date.parse(v));
    if (!object(data.hourly) || !Object.entries(data.hourly).every(([hour, accounts]) =>
        /^\d{4}-\d{2}-\d{2}T\d{2}:00Z$/.test(hour) && utc(hour) && object(accounts) && Object.values(accounts).every(bucket)) ||
        !data.cycles.every(c => utc(c.start_utc) && utc(c.end_utc) && utc(c.peak_at_utc))) {
      throw new Error('UTC hourly buckets and cycle timestamps are required; regenerate usage JSON');
    }
    // The optional social-post summary is deliberately ignored, including validation.
    const groups = data.summary?.per_model_full_window;
    if (groups != null && (!object(groups) || Object.values(groups).some(v => !object(v) ||
        !['windows', 'avg_hours_per_window', 'avg_input_per_window', 'avg_output_per_window',
          'avg_usd_per_window', 'usd_per_pct', 'input_per_pct', 'long_share_of_input'].every(f => finite(v[f])) ||
        !Array.isArray(v.accounts) || !v.accounts.every(a => typeof a === 'string')))) {
      throw new Error('Invalid full-window model summary format');
    }
    return data;
  }

  let localDaily = new Map();
  let data, modelKeys = [], bases = [], days = [], selected = null, currentRows = [];
  let chartSegments = new Map(), countJobs = new Set(), cycleObserver;
  let tooltipTarget = null, tooltipPinned = false, tooltipTimer, sourceBusy = false;
  const color = key => 'var(--' + (isLong(key) ? 'l' : 's') + (bases.indexOf(family(key)) % 8) + ')';
  function swatch(key) {
    const node = el('i', {class: 'swatch' + (isLong(key) ? ' long' : ''), 'aria-hidden': 'true'});
    node.style.setProperty('--series', color(key));
    return node;
  }
  function modelLabel(key, tag = 'span') {
    const node = el(tag, {class: 'model-label'});
    node.append(swatch(key), document.createTextNode(key));
    return node;
  }
  function animate(node, frames, duration, delay = 0) {
    node.getAnimations?.().forEach(a => a.cancel());
    if (reduced.matches || !node.animate) return;
    node.animate(frames, {duration, delay, easing: motion.ease, fill: 'backwards'});
  }
  function countUp(node, value) {
    node.setAttribute('aria-label', money(value) + ' USD');
    const visible = el('span', {'aria-hidden': 'true'}, money(value));
    node.append(visible);
    if (reduced.matches) return;
    const start = performance.now(), job = {id: 0, finish: () => { visible.textContent = money(value); }};
    const tick = now => {
      const t = Math.min(1, (now - start) / motion.count);
      visible.textContent = money(value * (1 - Math.pow(1 - t, 3)));
      if (t < 1) job.id = requestAnimationFrame(tick);
      else countJobs.delete(job);
    };
    countJobs.add(job);
    job.id = requestAnimationFrame(tick);
  }
  function stopCounts() {
    for (const job of countJobs) { cancelAnimationFrame(job.id); job.finish(); }
    countJobs.clear();
  }
  reduced.addEventListener('change', () => {
    if (!reduced.matches) return;
    stopCounts();
    document.getAnimations?.().forEach(a => a.cancel());
    cycleObserver?.disconnect();
    document.querySelectorAll('.cycle-fill').forEach(n => { n.style.transform = 'none'; });
  });

  const localDay = value => {
    const date = new Date(value), pad = n => String(n).padStart(2, '0');
    return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate());
  };
  const localTime = value => {
    if (!value) return '—';
    // Legacy metadata/reset timestamps have no suffix but are UTC in this format.
    const date = new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : value.replace(' ', 'T') + 'Z');
    return Number.isFinite(date.getTime()) ? new Intl.DateTimeFormat('en-GB', {
      year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
    }).format(date) : '—';
  };
  const complete = c => c.peak_pct >= (data.meta.complete_pct ?? 95);
  const quotaLabel = 'quota % (sum over accounts)';
  function rebucketHourly() {
    localDaily = new Map();
    for (const [hour, accounts] of Object.entries(data.hourly)) {
      const day = localDay(hour);
      if (!localDaily.has(day)) localDaily.set(day, new Map());
      for (const [account, bucket] of Object.entries(accounts)) {
        const daily = localDaily.get(day);
        if (!daily.has(account)) daily.set(account, {models: new Map(), quota: null});
        const dest = daily.get(account);
        merge(dest.models, bucket);
        if (typeof bucket._usage_pct === 'number') dest.quota = (dest.quota ?? 0) + bucket._usage_pct;
      }
    }
  }
  function calendarDays() {
    const observed = [...localDaily.keys()].sort();
    // The collector's since/until labels are already in its requested fixed
    // offset. Treat them as calendar labels; adding a day and converting
    // through UTC makes an Asia/Taipei report invent an extra trailing day.
    const first = data.meta.since || observed[0];
    const last = data.meta.until || observed.at(-1);
    if (!first || !last) return observed;
    // Advance calendar labels in UTC to avoid skipping/repeating a day at DST changes.
    const start = Date.parse([first, ...observed].sort()[0] + 'T00:00:00Z');
    const end = Date.parse([last, ...observed].sort().at(-1) + 'T00:00:00Z'), result = [];
    for (let stamp = start; stamp <= end; stamp += 86400000) result.push(new Date(stamp).toISOString().slice(0, 10));
    return result;
  }
  function rowsFor(account) {
    const accounts = account == null ? data.meta.accounts : [account];
    return days.map(day => {
      const models = new Map(), quotas = new Map();
      let observed = false;
      for (const acc of accounts) {
        const bucket = localDaily.get(day)?.get(acc);
        if (!bucket) continue;
        observed = true;
        merge(models, Object.fromEntries(bucket.models));
        if (bucket.quota != null) quotas.set(acc, bucket.quota);
      }
      return {day, models, observed, quotas, usd: sum([...models.values()], 'usd'),
        credits: sum([...models.values()], 'credits'), credits_standard: sum([...models.values()], 'credits_standard'),
        credits_fast: sum([...models.values()], 'credits_fast'), api_usd_from_credits: sum([...models.values()], 'api_usd_from_credits'),
        quota: quotas.size ? [...quotas.values()].reduce((a, b) => a + b, 0) : null};
    });
  }
  function familiesOf(models) {
    const totals = new Map();
    for (const [key, values] of models) totals.set(family(key), (totals.get(family(key)) || 0) + values.usd);
    return totals;
  }
  function dominant(cycle) {
    const totals = [...familiesOf(new Map(entries(cycle.by_model)))].sort((a, b) => b[1] - a[1]);
    if (!totals.length || totals[0][1] <= 0) return null;
    if (totals.length > 1 && Math.abs(totals[0][1] - totals[1][1]) < 1e-8) return null;
    return totals[0][0];
  }
  function renderSummary() {
    const models = new Map();
    for (const row of rowsFor(null)) merge(models, Object.fromEntries(row.models));
    const totals = [...models].map(([key, value]) => [key, value.usd]).sort((a, b) => b[1] - a[1]);
    const grand = totals.reduce((value, [, usd]) => value + usd, 0);
    $('grand-total').textContent = 'All models total ' + money(grand) + ' USD';
    const cards = totals.map(([base, usd]) => {
      const card = el('article', {class: 'metric', 'data-family': base});
      const amount = el('div', {class: 'amount'});
      countUp(amount, usd);
      card.append(modelLabel(base, 'h3'), amount, el('p', {class: 'micro'},
        'Share of period ' + (grand ? number(usd / grand * 100) : '0') + '%'));
      return card;
    });
    replace('metrics', ...(cards.length ? cards : [el('p', {class: 'empty'}, 'No usage records in this date range.')]));
    const groups = new Map();
    for (const cycle of data.cycles.filter(complete)) {
      const lead = dominant(cycle);
      if (!groups.has(lead)) groups.set(lead, []);
      groups.get(lead).push(cycle.usd);
    }
    const weekly = [...groups].sort((a, b) => b[1].length - a[1].length).map(([base, values]) => {
      const stat = el('div', {class: 'weekly-stat', 'data-family': base || 'tie'});
      const amount = el('span', {class: 'weekly-amount'}, money(median(values)));
      stat.append(el('p', {class: 'micro'}, base ? base + ' dominant' : 'Tied or unidentified dominant family'), amount,
        el('p', {class: 'micro'}, 'Median · ' + values.length + ' complete cycles'));
      return stat;
    });
    replace('weekly-values', ...(weekly.length ? weekly : [el('p', {class: 'sub'}, 'No complete cycles available.')]));
    $('weekly-range').textContent = 'Grouped by highest-USD model family';
    $('weekly-note').textContent = 'Raw complete cycles; includes mixed usage, without scaling to 100%.';
    const rows = rowsFor(null), credits = sum(rows, 'credits'), standardCredits = sum(rows, 'credits_standard'), fastCredits = sum(rows, 'credits_fast'), creditUsd = sum(rows, 'api_usd_from_credits');
    const cards2 = [
      ['Subscription credits consumed', number(credits) + ' credits', 'Estimated with observed Standard/Fast tier; standard baseline ' + number(standardCredits)],
      ['Fast / priority credits', number(fastCredits) + ' credits', 'Fast portion of consumed credits · ' + (credits ? number(fastCredits / credits * 100) : '0') + '%'],
      ['Current API equivalent from credits', money(creditUsd) + ' USD', creditApiNote(data)]
    ].map(([label, amount, note]) => {
      const card = el('article', {class: 'metric billing-metric'});
      card.append(el('h3', {}, label), el('div', {class: 'amount'}, amount), el('p', {class: 'micro'}, note));
      return card;
    });
    replace('billing-metrics', ...cards2);
    $('billing-note').textContent = 'Credits are subscription consumption estimates; this conversion uses current API Standard rates as an approximate reference, not an official subscription billing rule. Unknown-tier records are priced at Standard speed.';
  }

  function renderTabs() {
    const single = data.meta.accounts.length === 1;
    $('account-tabs').hidden = single;
    $('daily-panel').setAttribute('role', single ? 'region' : 'tabpanel');
    if (single) {
      replace('account-tabs');
      $('daily-panel').setAttribute('aria-labelledby', 'daily-heading');
      return;
    }
    const options = [null, ...data.meta.accounts];
    const buttons = options.map((account, index) => {
      const button = el('button', {type: 'button', role: 'tab', id: 'account-' + index,
        'aria-selected': account === selected, 'aria-controls': 'daily-panel', tabindex: account === selected ? 0 : -1}, account == null ? 'All' : account);
      button.addEventListener('click', () => choose(account));
      button.addEventListener('keydown', event => {
        let next;
        if (event.key === 'ArrowRight') next = (index + 1) % options.length;
        if (event.key === 'ArrowLeft') next = (index + options.length - 1) % options.length;
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = options.length - 1;
        if (next == null) return;
        event.preventDefault(); choose(options[next]); $('account-' + next).focus();
      });
      return button;
    });
    replace('account-tabs', ...buttons);
    syncTabs();
  }
  function syncTabs() {
    if (data.meta.accounts.length === 1) return;
    [null, ...data.meta.accounts].forEach((account, i) => {
      const button = $('account-' + i), active = account === selected;
      button.setAttribute('aria-selected', active); button.tabIndex = active ? 0 : -1;
      if (active) $('daily-panel').setAttribute('aria-labelledby', button.id);
    });
  }
  function choose(account) {
    if (selected === account) return;
    selected = account; hideTooltip(); syncTabs(); renderDaily(); renderDailyTable();
    $('interaction-status').textContent = 'Daily usage switched to ' + (account == null ? 'All accounts' : account) + '.';
  }
  function renderLegend(id, keys, quota = false) {
    const items = keys.map(key => {
      const values = id === 'daily-legend' ? currentRows.map(row => row.models.get(key)).filter(Boolean) :
        data.cycles.map(cycle => cycle.by_model[key]).filter(Boolean);
      const detail = key + ' · ' + money(sum(values, 'usd')) + ' · input ' + tokens(sum(values, 'input')) +
        ' · output ' + tokens(sum(values, 'output'));
      const rawDetail = 'Input ' + number(sum(values, 'input')) + ' tokens · output ' + number(sum(values, 'output')) + ' tokens';
      const node = el('span', {class: 'legend-item', tabindex: 0, title: detail + '\n' + rawDetail, 'aria-label': detail});
      node.append(swatch(key), document.createTextNode(key));
      return node;
    });
    if (quota) {
      const line = el('span', {class: 'legend-item'}), mark = el('i', {class: 'line-key', 'aria-hidden': 'true'});
      line.append(mark, document.createTextNode(quotaLabel + ' · right axis'));
      items.push(line);
    }
    replace(id, ...items);
  }
  const axisMax = value => {
    const rough = Math.max(value, 1) / 4, magnitude = 10 ** Math.floor(Math.log10(rough));
    return [1, 2, 2.5, 5, 10].find(n => n * magnitude >= rough) * magnitude * 4;
  };
  function renderDaily(shouldAnimate = true) {
    currentRows = rowsFor(selected);
    const used = modelKeys;
    renderLegend('daily-legend', used, true);
    const total = sum(currentRows, 'usd'), active = selected == null ? 'All accounts' : selected;
    const peak = currentRows.reduce((best, row) => row.usd > (best?.usd || 0) ? row : best, null);
    const creditTotal = sum(currentRows, 'credits'), fastCreditTotal = sum(currentRows, 'credits_fast');
    $('daily-summary').textContent = active + ' · ' + money(total) + ' API USD · ' + number(creditTotal) + ' credits' +
      (fastCreditTotal ? ' · Fast ' + number(fastCreditTotal) : '') + (peak ? ' · peak ' + peak.day.slice(5).replace('-', '/') + ' ' + money(peak.usd) : ' · no usage records');
    $('quota-note').textContent = selected == null ? 'The quota line sums daily percentage points across accounts. Resets can push consumption above 100%. Gaps mean no records.' : 'The quota line shows daily consumption; it can exceed 100% after resets. Gaps mean no records.';
    const root = $('daily-chart');
    if (!currentRows.length || !currentRows.some(row => row.observed)) {
      chartSegments.clear();
      root.replaceChildren(el('p', {class: 'empty empty-chart'}, active + ' has no local usage records in this date range.'));
      return;
    }
    const width = Math.max(560, root.clientWidth, days.length * 44 + 112), height = 265;
    const left = 64, right = width - 55, top = 28, bottom = height - 35, plotHeight = bottom - top;
    const maximum = axisMax(Math.max(...currentRows.map(r => r.usd)) * 1.05);
    const quotaMax = axisMax(Math.max(100, ...currentRows.map(r => r.quota ?? 0)));
    const slot = (right - left) / days.length, barWidth = Math.min(46, slot * .62);
    // Read all current transforms before writing. Interrupted account switches start
    // at their visible position; only transform/opacity are ever animated.
    const previous = new Map();
    for (const [key, rect] of chartSegments) previous.set(key, getComputedStyle(rect).transform);
    chartSegments.forEach(rect => rect.getAnimations?.().forEach(a => a.cancel()));
    const chart = svg('svg', {viewBox: `0 0 ${width} ${height}`, role: 'group', 'aria-label': 'Daily stacked USD chart and quota line; use arrow keys for dates and Enter for details'});
    chart.style.minWidth = width + 'px';
    const defs = svg('defs');
    modelKeys.forEach((key, i) => {
      if (!isLong(key)) return;
      const pattern = svg('pattern', {id: 'hatch-' + i, width: 7, height: 7, patternUnits: 'userSpaceOnUse'});
      pattern.append(svg('rect', {width: 7, height: 7, fill: color(key)}),
        svg('path', {d: 'M-1 1L1-1 M0 7L7 0 M6 8L8 6', stroke: 'var(--hatch)', 'stroke-width': 1.2, opacity: .65}));
      defs.append(pattern);
    });
    chart.append(defs);
    chart.append(svg('text', {x: left, y: 13, class: 'axis-title'}, 'API-equivalent · USD'),
      svg('text', {x: right, y: 13, class: 'axis-title', 'text-anchor': 'end'}, 'Quota %'));
    for (let i = 0; i <= 4; i++) {
      const y = bottom - i / 4 * plotHeight;
      chart.append(svg('line', {x1: left, x2: right, y1: y, y2: y, class: 'gridline'}),
        svg('text', {x: left - 10, y: y + 4, class: 'axis', 'text-anchor': 'end'}, wholeMoney(maximum * i / 4)),
        svg('text', {x: right + 10, y: y + 4, class: 'axis'}, number(quotaMax * i / 4) + '%'));
    }
    const nextSegments = new Map(), animations = [], hits = [], line = svg('g');
    let quotaPath = '', connected = false;
    const tickStep = Math.max(1, Math.ceil(days.length / Math.floor((right - left) / 55)));
    currentRows.forEach((row, dayIndex) => {
      const x = left + slot * (dayIndex + .5), barX = x - barWidth / 2;
      let accumulated = 0;
      used.forEach(key => {
        const usd = row.models.get(key)?.usd || 0, h = usd / maximum * plotHeight;
        const id = JSON.stringify([row.day, key]);
        const rect = svg('rect', {x: 0, y: 0, width: barWidth, height: 1, fill: isLong(key) ? 'url(#hatch-' + modelKeys.indexOf(key) + ')' : color(key), 'aria-hidden': 'true'});
        const y = bottom - accumulated - h, transform = `matrix(1,0,0,${h},${barX},${y})`;
        rect.style.transformOrigin = '0 0'; rect.style.transform = transform;
        // Counter-scale the SVG pattern so stripes keep a constant screen spacing.
        if (isLong(key) && h > 0) {
          const patternId = 'day-hatch-' + dayIndex + '-' + modelKeys.indexOf(key);
          const pattern = defs.querySelector('#hatch-' + modelKeys.indexOf(key)).cloneNode(true);
          pattern.id = patternId; pattern.setAttribute('patternTransform', `scale(1 ${1 / h})`);
          defs.append(pattern); rect.setAttribute('fill', 'url(#' + patternId + ')');
        }
        chart.append(rect); nextSegments.set(id, rect);
        if (h > 0 || previous.has(id)) animations.push([rect, previous.get(id) || `matrix(1,0,0,0,${barX},${bottom})`, transform, dayIndex]);
        accumulated += h;
      });
      if (dayIndex % tickStep === 0 || dayIndex === days.length - 1) chart.append(svg('text', {x, y: bottom + 24, class: 'axis', 'text-anchor': 'middle'}, row.day.slice(5).replace('-', '/')));
      if (!row.observed) chart.append(svg('text', {x, y: bottom - 8, class: 'axis', 'text-anchor': 'middle'}, '—'));
      if (row.quota == null) connected = false;
      else {
        const y = bottom - row.quota / quotaMax * plotHeight;
        quotaPath += (connected ? ' L' : ' M') + x + ',' + y; connected = true;
        const dot = svg('circle', {cx: x, cy: y, r: 3.5, class: 'quota-dot'});
        dot.append(svg('title', {}, quotaLabel + ' · ' + pct(row.quota)));
        line.append(dot);
      }
      const hit = svg('rect', {x: left + slot * dayIndex, y: top, width: slot, height: plotHeight, rx: 3,
        class: 'day-hit', role: 'button', tabindex: dayIndex === 0 ? 0 : -1, 'data-day': row.day,
        'aria-label': row.day + ', ' + (row.observed ? money(row.usd) + ', ' + quotaLabel + ' ' + pct(row.quota) : 'No records') + ', show model details'});
      bindTooltip(hit, row);
      hit.addEventListener('keydown', event => {
        let index;
        if (event.key === 'ArrowRight') index = Math.min(dayIndex + 1, days.length - 1);
        if (event.key === 'ArrowLeft') index = Math.max(dayIndex - 1, 0);
        if (event.key === 'Home') index = 0;
        if (event.key === 'End') index = days.length - 1;
        if (index == null) return;
        event.preventDefault(); hits.forEach(h => h.tabIndex = -1); hits[index].tabIndex = 0; hits[index].focus();
        hits[index].scrollIntoView({block: 'nearest', inline: 'nearest'});
      });
      hits.push(hit);
    });
    const path = svg('path', {d: quotaPath, class: 'quota-line'});
    path.append(svg('title', {}, quotaLabel)); line.prepend(path);
    chart.append(line, ...hits);
    root.replaceChildren(chart); chartSegments = nextSegments;
    if (shouldAnimate) {
      for (const [rect, from, to, index] of animations) animate(rect, [{transform: from}, {transform: to}], motion.chart, Math.min(index, 4) * motion.stagger);
      animate(line, [{opacity: 0}, {opacity: 1}], motion.reveal);
    }
  }

  function hideTooltip() {
    clearTimeout(tooltipTimer);
    tooltipTarget?.removeAttribute('aria-describedby');
    tooltipTarget = null; tooltipPinned = false; $('chart-tooltip').hidden = true;
  }
  function deferHide() {
    if (tooltipPinned || document.activeElement === tooltipTarget) return;
    tooltipTimer = setTimeout(hideTooltip, 120);
  }
  function showTooltip(target, row) {
    clearTimeout(tooltipTimer);
    tooltipTarget?.removeAttribute('aria-describedby');
    tooltipTarget = target; target.setAttribute('aria-describedby', 'chart-tooltip');
    const tip = $('chart-tooltip'), title = el('div', {class: 'tip-title'});
    title.append(el('span', {}, row.cycle ? row.cycle.account : row.day), el('span', {}, row.observed ? money(row.usd) : 'No records'));
    const quotaDetail = [...row.quotas].map(([acc, value]) => acc + ' ' + pct(value)).join(' · ');
    tip.replaceChildren(title);
    if (row.cycle) {
      const c = row.cycle;
      tip.append(el('p', {class: 'sub'}, localTime(c.start_utc) + ' → ' + localTime(c.end_utc)),
        el('p', {class: 'sub'}, number(c.hours) + ' h · used ' + pct(c.consumed_pct) + ' · ' + (c.usd_per_pct == null ? '—' : money(c.usd_per_pct)) + ' / 1 %'),
        el('p', {class: 'sub'}, number(c.credits) + ' credits · Fast ' + number(c.credits_fast || 0) + ' · ' + money(c.api_usd_from_credits || 0) + ' API USD equivalent'),
        el('p', {class: 'sub'}, 'Peak ' + pct(c.peak_pct) + ' at ' + localTime(c.peak_at_utc)));
    } else {
      tip.append(el('p', {class: 'sub'}, quotaLabel + ' · ' + pct(row.quota)));
      if (quotaDetail) tip.append(el('p', {class: 'sub'}, quotaDetail));
      tip.append(el('p', {class: 'sub'}, number(row.credits) + ' credits · Fast ' + number(row.credits_fast || 0) + ' · ' + money(row.api_usd_from_credits || 0) + ' API USD equivalent'));
    }
    const tokenTotals = el('p', {class: 'sub'});
    tokenTotals.append(tokenNode(sum([...row.models.values()], 'input'), 'Input '),
      document.createTextNode(' · '), tokenNode(sum([...row.models.values()], 'output'), 'output '));
    tip.append(tokenTotals);
    if (!row.observed) tip.append(el('p', {class: 'sub'}, 'No local records for this date/account; this does not imply zero usage.'));
    for (const key of modelKeys.filter(k => row.models.has(k))) {
      const value = row.models.get(key), item = el('div', {class: 'tip-model'}), label = el('div', {class: 'tip-label'});
      label.append(modelLabel(key), el('strong', {}, money(value.usd)));
      const tokenRow = el('div', {class: 'tip-tokens'});
      tokenRow.append(tokenNode(value.input, 'Input '),
        tokenNode(value.cached, 'Cached '), tokenNode(value.output, 'Output '));
      item.append(label, tokenRow); tip.append(item);
    }
    tip.append(el('p', {class: 'sub'}, 'Input includes cached tokens · Esc to close · tap to pin'));
    tip.hidden = false;
    // Position beside a keyboard-focused day whenever possible; never cover it.
    const rect = target.getBoundingClientRect(), bounds = tip.getBoundingClientRect();
    let x = rect.right + 12;
    if (x + bounds.width > innerWidth - 12) x = rect.left - bounds.width - 12;
    x = Math.max(12, Math.min(x, innerWidth - bounds.width - 12));
    let y = Math.max(12, Math.min(rect.top, innerHeight - bounds.height - 12));
    if (x < rect.right && x + bounds.width > rect.left) y = Math.max(12, rect.top - bounds.height - 12);
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  }
  function bindTooltip(target, row) {
    target.addEventListener('pointerenter', () => { if (!tooltipPinned) showTooltip(target, row); });
    target.addEventListener('pointerleave', deferHide);
    target.addEventListener('focus', () => { tooltipPinned = false; showTooltip(target, row); });
    target.addEventListener('blur', () => { if (!tooltipPinned) hideTooltip(); });
    target.addEventListener('click', event => {
      event.stopPropagation();
      if (tooltipPinned && tooltipTarget === target) hideTooltip();
      else { showTooltip(target, row); tooltipPinned = true; }
    });
    target.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); showTooltip(target, row); tooltipPinned = true; }
    });
  }
  $('chart-tooltip').addEventListener('pointerenter', () => clearTimeout(tooltipTimer));
  $('chart-tooltip').addEventListener('pointerleave', deferHide);
  document.addEventListener('keydown', event => { if (event.key === 'Escape') hideTooltip(); });
  document.addEventListener('click', event => { if (!$('chart-tooltip').contains(event.target)) hideTooltip(); });

  function wrapTable(table, label) {
    const wrapper = el('div', {class: 'table-scroll', role: 'region', 'aria-label': label + ', horizontally scrollable', tabindex: 0});
    wrapper.append(table); return wrapper;
  }
  const th = (text, attrs = {}) => el('th', {scope: 'col', ...attrs}, text);
  const td = text => el('td', {}, text);
  const hasModelValues = value => ['input', 'output', 'usd'].some(field => Number(value?.[field]) > 0);
  function windowCard(label, value, index) {
    const card = el('article', {class: 'metric window-card', 'data-window': label});
    card.style.setProperty('--series', 'var(--s' + index % 8 + ')');
    card.append(el('h3', {}, label), el('p', {class: 'micro'}, 'Average API USD per full window'));
    const amount = el('div', {class: 'amount'}); countUp(amount, value.avg_usd_per_window); card.append(amount);
    const stats = el('dl', {class: 'window-stats'});
    for (const [name, text] of [
      ['Average input tokens', tokens(value.avg_input_per_window)],
      ['Average output tokens', tokens(value.avg_output_per_window)],
      ['Average subscription credits', number(value.avg_credits_per_window)],
      ['Average Fast credits', number(value.avg_credits_fast_per_window || 0)],
      ['Credits → API USD', money(value.avg_api_usd_from_credits_per_window || 0)],
      ['Hours to consume a window', number(value.avg_hours_per_window) + ' h'],
      ['USD per 1 % quota', money(value.usd_per_pct)],
      ['Input tokens per 1 % quota', tokens(value.input_per_pct)],
      ['Long-context share of input', pct(value.long_share_of_input * 100)]
    ]) {
      const stat = el('div'); stat.append(el('dt', {}, name), el('dd', {}, text)); stats.append(stat);
    }
    card.append(stats, el('p', {class: 'micro'}, value.windows + (value.windows === 1 ? ' window' : ' windows') +
      ' · accounts: ' + (value.accounts.join(', ') || 'none')));
    return card;
  }
  function renderFullWindows() {
    const modelEntries = Object.entries(data.summary?.per_model_full_window || {}).sort(([a], [b]) => a.localeCompare(b));
    $('model-window-details').hidden = !modelEntries.length;
    const cards = modelEntries.map(([model, value], index) => windowCard(model, value, index));
    $('model-window-method').textContent = 'Complete cycles (peak ≥' + number(data.meta.complete_pct ?? 95) +
      '%, consumed ≥50 points), with one base model ≥75% of input. Each window is scaled to 100% and averaged by model.';
    replace('model-window-cards', ...cards);
  }
  function renderDailyTable() {
    const accounts = selected == null ? data.meta.accounts : [selected];
    const multi = data.meta.accounts.length > 1;
    const keys = modelKeys.filter(key => currentRows.some(row => hasModelValues(row.models.get(key))))
      .sort((a, b) => Number(family(a) === 'codex-auto-review') - Number(family(b) === 'codex-auto-review'));
    $('daily-details-heading').textContent = 'Daily details · ' + (selected == null ? 'All accounts' : selected);
    const table = el('table'), head = el('thead'), first = el('tr'), second = el('tr'), body = el('tbody');
    table.append(el('caption', {}, 'Daily usage' + (multi ? ' · ' + (selected == null ? 'All accounts' : selected) : '') + ' · K/M/B tokens (raw counts on hover), API USD, subscription credits and daily quota consumption'));
    first.append(th('Date', {rowspan: 2}));
    if (multi) for (const acc of accounts) { first.append(th(acc, {colspan: 2, scope: 'colgroup'})); second.append(th('USD'), th('Quota %')); }
    first.append(th('Observed total USD', {rowspan: 2}));
    first.append(th('Credits consumed', {rowspan: 2}));
    first.append(th('Fast credits', {rowspan: 2}));
    first.append(th('Credits → API USD', {rowspan: 2}));
    first.append(th(selected == null ? quotaLabel : 'quota %', {rowspan: 2}));
    for (const key of keys) {
      const group = th('', {colspan: 3, scope: 'colgroup'}); group.append(modelLabel(key)); first.append(group);
      second.append(th('Input'), th('Output'), th('USD'));
    }
    head.append(first, second);
    const totals = new Map(accounts.map(a => [a, {usd: 0, quota: 0, observed: false, quotaObserved: false}]));
    currentRows.forEach(row => {
      const tr = el('tr', {'data-day': row.day}); tr.append(th(row.day, {scope: 'row'}));
      let accountUsd = 0;
      for (const acc of accounts) {
        const bucket = localDaily.get(row.day)?.get(acc), total = totals.get(acc);
        const amount = bucket ? sum([...bucket.models.values()], 'usd') : null;
        accountUsd += amount || 0;
        const quota = bucket?.quota;
        if (multi) tr.append(td(amount == null ? '—' : money(amount)), td(pct(quota)));
        if (amount != null) { total.usd += amount; total.observed = true; }
        if (quota != null) { total.quota += quota; total.quotaObserved = true; }
      }
      console.assert(Math.abs(accountUsd - row.usd) < 1e-7, 'Daily table/chart USD mismatch', row.day, accountUsd, row.usd);
      tr.append(td(row.observed ? money(accountUsd) : '—'), td(row.observed ? number(row.credits) : '—'),
        td(row.observed && row.credits_fast ? number(row.credits_fast) : '—'), td(row.observed ? money(row.api_usd_from_credits) : '—'), td(pct(row.quota)));
      for (const key of keys) {
        const value = row.models.get(key);
        tr.append(tokenNode(value?.input, '', 'td'), tokenNode(value?.output, '', 'td'), td(value ? money(value.usd) : '—'));
      }
      body.append(tr);
    });
    const foot = el('tfoot'), tr = el('tr'); tr.append(th('Observed total', {scope: 'row'}));
    if (multi) for (const acc of accounts) { const total = totals.get(acc); tr.append(td(total.observed ? money(total.usd) : '—'), td(total.quotaObserved ? pct(total.quota) : '—')); }
    const tableUsd = sum([...totals.values()], 'usd');
    console.assert(Math.abs(tableUsd - sum(currentRows, 'usd')) < 1e-7, 'Daily table/chart grand total mismatch');
    for (const [account, total] of totals) console.assert(Math.abs(total.usd - sum(rowsFor(account), 'usd')) < 1e-7, 'Account table/chart USD mismatch', account);
    tr.append(td(currentRows.some(r => r.observed) ? money(tableUsd) : '—'));
    tr.append(td(currentRows.some(r => r.observed) ? number(sum(currentRows, 'credits')) : '—'),
      td(currentRows.some(r => r.observed) && sum(currentRows, 'credits_fast') ? number(sum(currentRows, 'credits_fast')) : '—'),
      td(currentRows.some(r => r.observed) ? money(sum(currentRows, 'api_usd_from_credits')) : '—'));
    const quotas = currentRows.map(r => r.quota).filter(v => v != null);
    tr.append(td(quotas.length ? pct(quotas.reduce((a, b) => a + b, 0)) : '—'));
    for (const key of keys) {
      const values = currentRows.map(row => row.models.get(key)).filter(Boolean);
      tr.append(tokenNode(values.length ? sum(values, 'input') : null, '', 'td'), tokenNode(values.length ? sum(values, 'output') : null, '', 'td'),
        td(values.length ? money(sum(values, 'usd')) : '—'));
    }
    foot.append(tr); table.append(head, body, foot);
    replace('daily-table', wrapTable(table, 'Daily usage details'));
  }

  function renderCycles() {
    const cycles = [...data.cycles].sort((a, b) => a.account.localeCompare(b.account) || a.start_utc.localeCompare(b.start_utc));
    const used = modelKeys;
    const maximum = axisMax(Math.max(1, ...cycles.map(c => c.usd)));
    const groups = [], fills = [];
    renderLegend('cycle-legend', used);
    $('cycle-range').textContent = 'One row per reset window, with full observed start and end in local time';
    for (const account of data.meta.accounts) {
      const rows = cycles.filter(c => c.account === account), group = el('section', {class: 'cycle-account', 'aria-label': account + ' quota cycles'});
      const heading = el('div', {class: 'account-title'});
      heading.append(el('h3', {}, account), el('span', {class: 'micro'}, rows.length + ' cycles · ' + rows.filter(complete).length + ' complete'));
      group.append(heading);
      if (!rows.length) group.append(el('p', {class: 'sub'}, 'No cycles meet the collection criteria for this account.'));
      for (const c of rows) {
        const row = el('div', {class: 'cycle-row ' + (complete(c) ? 'full' : 'partial'), tabindex: 0, role: 'button',
          'aria-label': c.account + ', ' + localTime(c.start_utc) + ' → ' + localTime(c.end_utc) + ', used ' + pct(c.consumed_pct) + ', ' + money(c.usd) + ', show cycle details'});
        bindTooltip(row, {cycle: c, observed: true, usd: c.usd, credits: c.credits, credits_fast: c.credits_fast,
          api_usd_from_credits: c.api_usd_from_credits, models: new Map(entries(c.by_model)), quotas: new Map()});
        const label = el('div', {class: 'cycle-meta'});
        label.append(el('span', {class: 'badge'}, number(c.consumed_pct) + ' %'),
          el('span', {}, localTime(c.start_utc) + ' → ' + localTime(c.end_utc)));
        if (complete(c)) label.append(el('span', {class: 'complete-mark', title: 'Complete: peak reached threshold', 'aria-label': 'Complete cycle'}, '✓'));
        const track = el('div', {class: 'cycle-track', 'aria-hidden': 'true'}), fill = el('div', {class: 'cycle-fill'});
        fill.style.width = (c.usd / maximum * 100) + '%';
        const denominator = sum(entries(c.by_model).map(([, v]) => v), 'usd');
        for (const key of used) {
          const value = c.by_model[key]?.usd || 0;
          if (!value) continue;
          const segment = el('span', {class: isLong(key) ? 'long' : ''});
          segment.style.width = (denominator ? value / denominator * 100 : 0) + '%';
          segment.style.setProperty('--series', color(key)); fill.append(segment);
        }
        track.append(fill); fills.push(fill);
        const amount = el('div', {class: 'cycle-value'}, money(c.usd));
        amount.append(el('small', {}, number(c.credits) + ' credits'), el('small', {}, 'Fast ' + number(c.credits_fast || 0)),
          el('small', {}, (c.usd_per_pct == null ? '—' : money(c.usd_per_pct)) + ' / 1%'));
        row.append(label, track, amount); group.append(row);
      }
      groups.push(group);
    }
    replace('cycle-groups', ...(groups.length ? groups : [el('p', {class: 'empty'}, 'No quota cycle records yet.')]));
    replace('cycle-scale', el('span', {}, '$0'), el('span', {}, wholeMoney(maximum) + ' USD'));
    cycleObserver?.disconnect();
    if (!reduced.matches && 'IntersectionObserver' in window) {
      cycleObserver = new IntersectionObserver(observations => {
        observations.filter(o => o.isIntersecting).forEach((observation, i) => {
          const fill = observation.target.firstElementChild;
          fill.style.transform = 'none';
          animate(fill, [{transform: 'scaleX(0)'}, {transform: 'scaleX(1)'}], motion.reveal, Math.min(i, 4) * motion.stagger);
          cycleObserver.unobserve(observation.target);
        });
      }, {threshold: .15});
      fills.forEach(fill => { fill.style.transform = 'scaleX(0)'; cycleObserver.observe(fill.parentElement); });
    }
    renderCycleTable(cycles, used);
  }
  function renderCycleTable(cycles, keys) {
    keys = keys.filter(key => cycles.some(cycle => hasModelValues(cycle.by_model[key])));
    const single = data.meta.accounts.length === 1;
    $('cycle-details-heading').textContent = 'Cycle details · ' + (single ? data.meta.accounts[0] : 'tokens and USD by model');
    if (!cycles.length) { replace('cycle-table', el('p', {class: 'empty'}, 'No cycle details to display.')); return; }
    const table = el('table'), head = el('thead'), first = el('tr'), second = el('tr'), body = el('tbody');
    table.append(el('caption', {}, 'Quota cycle details · K/M/B tokens (raw counts on hover); input includes cached tokens'));
    [...(single ? [] : ['Account']), 'Start', 'End', 'Peak at', 'Hours', 'Start → peak %', 'Quota consumed %', 'Status'].forEach(label => first.append(th(label, {rowspan: 2})));
    ['Total USD', 'Credits', 'Fast credits', 'Credits → API USD', 'USD / 1% quota', 'Credits / 1% quota'].forEach(label => first.append(th(label, {rowspan: 2})));
    for (const key of keys) {
      const group = th('', {colspan: 3, scope: 'colgroup'}); group.append(modelLabel(key)); first.append(group);
      second.append(th('Input'), th('Output'), th('USD'));
    }
    first.append(th('Reset time', {rowspan: 2}));
    head.append(first, second);
    for (const cycle of cycles) {
      const row = el('tr');
      if (!single) row.append(th(cycle.account, {scope: 'row'}));
      row.append(single ? th(localTime(cycle.start_utc), {scope: 'row'}) : td(localTime(cycle.start_utc)), td(localTime(cycle.end_utc)), td(localTime(cycle.peak_at_utc)), td(number(cycle.hours || 0)),
        td(pct(cycle.start_pct) + ' → ' + pct(cycle.peak_pct)), td(pct(cycle.consumed_pct)), td(complete(cycle) ? '✓' : '—'));
      row.append(td(money(cycle.usd)), td(number(cycle.credits)), td(cycle.credits_fast ? number(cycle.credits_fast) : '—'),
        td(money(cycle.api_usd_from_credits || 0)), td(cycle.usd_per_pct == null ? '—' : money(cycle.usd_per_pct)),
        td(cycle.credits_per_pct == null ? '—' : number(cycle.credits_per_pct)));
      for (const key of keys) {
        const value = cycle.by_model[key];
        row.append(tokenNode(value?.input, '', 'td'), tokenNode(value?.output, '', 'td'), td(value ? money(value.usd) : '—'));
      }
      row.append(td(localTime(cycle.resets_at_utc))); body.append(row);
    }
    table.append(head, body); replace('cycle-table', wrapTable(table, 'Quota cycle details'));
  }

  function priceFor(key) {
    const contexts = data.meta.prices?.[family(key)], context = isLong(key) ? 'long' : 'short';
    const populated = rates => rates && Object.keys(rates).length > 0;
    // collect.py omits fallback_model from meta. An unknown model's USD remains
    // authoritative, but its fallback rates cannot be identified from this JSON.
    if (!contexts) return {rates: null, note: 'Fallback rates not recorded'};
    if (populated(contexts[context])) return {rates: contexts[context], note: context};
    if (populated(contexts.short)) return {rates: contexts.short, note: 'Long unavailable; using short'};
    return {rates: null, note: 'Rates not provided'};
  }
  function renderPrices() {
    if (!modelKeys.length) { replace('price-table', el('p', {class: 'empty'}, 'No models in use.')); return; }
    const table = el('table'), head = el('thead'), header = el('tr'), body = el('tbody');
    table.append(el('caption', {}, 'API USD and subscription credits / 1M tokens · model keys present in the data'));
    ['Model key', 'Input (standard)', 'Cached input (standard)', 'Output (standard)',
      'Long applied · input / cached / output', 'Current API Standard · input / cached / output',
      'Subscription credits · input / cached / output', 'Fast multiplier', 'Notes'].forEach(label => header.append(th(label)));
    head.append(header);
    // Pricing needs more precision than usage labels (for example $0.02 cached input).
    const exactRate = value => value == null ? '—' : Number(value).toLocaleString('en-US', {maximumFractionDigits: 10});
    for (const key of modelKeys) {
      const row = el('tr'), label = th('', {scope: 'row'}); label.append(modelLabel(key)); row.append(label);
      const standard = data.meta.prices?.[family(key)]?.short, applied = priceFor(key);
      const subscription = data.meta.subscription_prices?.[family(key)], subscriptionRates = subscription?.standard;
      ['input', 'cached', 'output'].forEach(field => row.append(td(exactRate(standard?.[field]))));
      row.append(td(isLong(key) && applied.rates ? ['input', 'cached', 'output'].map(f => exactRate(applied.rates[f])).join(' / ') : '—'));
      const reference = data.meta.api_reference_prices?.[family(key)];
      row.append(td(reference ? ['input', 'cached', 'output'].map(f => exactRate(reference[f])).join(' / ') : 'fallback'));
      row.append(td(subscriptionRates ? ['input', 'cached', 'output'].map(f => exactRate(subscriptionRates[f])).join(' / ') : 'fallback'));
      row.append(td(subscription?.fast_multiplier == null ? '—' : number(subscription.fast_multiplier) + '×'));
      row.append(td(family(key) === 'codex-auto-review' ? 'API/subscription fallback uses gpt-5.6-sol unless overridden; API review rate remains owner decision' :
        !applied.rates ? applied.note : isLong(key) ? applied.note : 'Standard applied'));
      body.append(row);
    }
    table.append(head, body); replace('price-table', wrapTable(table, 'API prices'));
    $('price-note').textContent = 'API USD uses the current applied context column; the current API Standard column is used as an approximate reference for credit comparison. Subscription credits use the published standard credit table and observed Fast multiplier. Long-context subscription credits use the same published model rate because the subscription table does not publish a separate long column.';
  }
  function renderCaveats() {
    const meta = data.meta, list = el('ul');
    const threshold = tokens(meta.long_context_threshold || 272000);
    const from = Object.entries(meta.account_from || {}).map(([a, day]) => a + ' from ' + localTime(day + 'T00:00:00Z') + ' onward').join('; ');
    const notes = [
      "Plan tier is not shown: the plan_type reported in the CLI logs did not match the owner's records for every account.",
      'codex-auto-review priced at gpt-5.6-luna rates (owner decision)',
      'Only records on this machine are counted; usage elsewhere is invisible. ' + (from ? from + '.' : ''),
      '[1m] means request input >' + threshold + ' tokens, priced at long-context rates; each model key is counted separately.',
      'Input includes cached tokens; output includes reasoning. Cache writes are not recorded or counted. USD is API-equivalent value, not money paid.',
      'Subscription credits are separate from API billing: standard credits follow the published Codex table, Fast/priority uses the model multiplier, and unknown tiers are conservatively priced at Standard.',
      'The credits → API USD figure is an approximate comparison using current API Standard rates (Sol currently maps to about 25 credits per $1); it is not an official subscription billing rule and may change when the promotion changes.',
      'Observed service tiers: ' + Object.entries(meta.service_tier_counts || {}).map(([tier, count]) => tier + ' ' + number(count) + ' requests').join(' · ') + '. Tier source: direct event where available, otherwise settings timeline.',
      'Complete cycles reach peak ≥' + number(meta.complete_pct ?? 95) + '%; observation need not start at 0%. Cycles retain their full observed intervals, which may extend beyond the date range. Medians use raw cycle USD, including mixed usage, without extrapolation.',
      'Daily quota % means percentage points consumed. Percentage points are summed across accounts; resets can push consumption above 100%. A dash means missing data, not zero. The first and last local day may be partial because the source range is UTC days. Hourly buckets are assigned by their local start; zones with fractional-hour offsets have hour-level boundary precision.',
      'Prices fetched at ' + localTime(meta.prices_fetched_at) + '; source ' + (meta.prices_source || 'not provided') + '. Subscription rates source ' + (meta.subscription_prices_source || 'not provided') + '. ' +
        (meta.prices_overrides ? 'Applied overrides: ' + meta.prices_overrides + '.' : '')
    ];
    notes.forEach(note => list.append(el('li', {}, note)));
    replace('caveat-list', list);
  }
  function initialize(next) {
    data = validate(next); stopCounts(); hideTooltip();
    rebucketHourly();
    const found = new Set();
    Object.values(data.hourly).forEach(accounts => Object.values(accounts).forEach(b => entries(b).forEach(([key]) => found.add(key))));
    data.cycles.forEach(c => entries(c.by_model).forEach(([key]) => found.add(key)));
    bases = [...new Set([...found].map(family))].sort();
    modelKeys = [...found].sort((a, b) => family(a).localeCompare(family(b)) || Number(isLong(a)) - Number(isLong(b)) || a.localeCompare(b));
    days = calendarDays();
    if (!data.meta.accounts.includes(selected)) selected = null;
    if (data.meta.accounts.length === 1) selected = data.meta.accounts[0];
    $('daily-heading').textContent = 'Daily usage' + (data.meta.accounts.length === 1 ? ' · ' + selected : '');
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const offset = -new Date().getTimezoneOffset() / 60;
    $('period').textContent = (days[0] || '—') + ' — ' + (days.at(-1) || '—') + ' · ' + data.meta.accounts.length +
      (data.meta.accounts.length === 1 ? ' account' : ' accounts') + ' · Times shown in ' + zone + ' (UTC' + (offset >= 0 ? '+' : '') + offset + ')';
    $('generated').textContent = 'Local snapshot · ' + localTime(data.meta.generated);
    renderFullWindows(); renderSummary(); renderTabs(); renderDaily(); renderDailyTable(); renderCycles(); renderPrices(); renderCaveats();
  }

  let embedded;
  try { embedded = validate(JSON.parse($('usage-data').textContent)); initialize(embedded); }
  catch (error) {
    $('source-status').textContent = 'Unable to read usage data: ' + error.message + '. Regenerate the report.';
    return;
  }
  function syncTheme() {
    const dark = document.body.dataset.theme === 'dark';
    $('theme-toggle').setAttribute('aria-pressed', dark);
    $('theme-toggle').textContent = dark ? 'Switch to light' : 'Switch to dark';
  }
  $('theme-toggle').addEventListener('click', () => {
    document.body.dataset.theme = document.body.dataset.theme === 'dark' ? 'light' : 'dark'; syncTheme();
  });
  syncTheme();
  $('show-daily-table').addEventListener('click', () => { $('daily-details').open = true; });
  let resizeFrame;
  window.addEventListener('resize', () => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => {
      const focusedDay = document.activeElement?.getAttribute('data-day');
      hideTooltip(); renderDaily(false);
      if (focusedDay) {
        const hit = [...document.querySelectorAll('.day-hit')].find(n => n.getAttribute('data-day') === focusedDay);
        if (hit) { document.querySelectorAll('.day-hit').forEach(n => n.tabIndex = -1); hit.tabIndex = 0; hit.focus({preventScroll: true}); }
      }
    });
  });
  async function fetchData() {
    if (!config.dataUrl || sourceBusy) return;
    sourceBusy = true; $('retry-data').disabled = true; $('source-status').setAttribute('aria-busy', 'true');
    $('source-status').textContent = 'Refreshing data; showing the embedded snapshot.';
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(config.dataUrl, {signal: controller.signal, credentials: 'omit', cache: 'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const next = validate(await response.json());
      initialize(next);
      $('source-status').textContent = 'Updated data loaded · ' + config.dataUrl;
      $('retry-data').hidden = true;
    } catch (error) {
      initialize(embedded);
      $('source-status').textContent = 'Refresh failed; using the embedded snapshot. Check the URL, server and CORS settings.';
      $('retry-data').hidden = false;
    } finally {
      clearTimeout(timeout); sourceBusy = false; $('retry-data').disabled = false; $('source-status').setAttribute('aria-busy', 'false');
    }
  }
  $('retry-data').addEventListener('click', fetchData);
  if (config.dataUrl) fetchData();
  else $('source-status').textContent = 'Embedded data · works offline';
})();
"""


def script_json(value):
    """Escape HTML raw-text terminators without changing the decoded JSON."""
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
            .replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
            .replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))


def render(data, title='Codex usage · API value and subscription credits', theme='light', data_url=None):
    """Package data only: all report calculations and DOM rendering live in JS."""
    if theme not in ('light', 'dark'):
        raise ValueError('theme must be light or dark')
    title = html.escape(title, quote=True)
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{title}</title>
<style>{CSS}</style>
</head>
<body data-theme="{theme}">
<a class="skip" href="#daily-heading">Skip to daily usage</a>
<noscript>This dashboard requires JavaScript. Enable it and reopen the report.</noscript>
<main>
<div class="overview">
  <header class="header">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M5 18V12M12 18V5M19 18V9"/></svg></span>
      <div><p class="eyebrow">LOCAL USAGE / API VALUE</p><h1>{title}</h1><p class="meta" id="period"></p></div>
    </div>
    <div class="header-actions"><button type="button" id="theme-toggle" aria-pressed="false">Switch to dark</button></div>
  </header>
  <details class="disclosure" id="model-window-details" hidden>
    <summary>Full weekly quota window · by model</summary>
    <div class="detail-body"><p class="sub" id="model-window-method"></p><div class="window-cards" id="model-window-cards"></div></div>
  </details>
  <section aria-labelledby="totals-heading">
    <div class="heading-row"><h2 id="totals-heading">API-equivalent value during this period</h2><span class="micro" id="grand-total"></span></div>
    <div class="metrics" id="metrics"></div>
  </section>
  <section class="panel" aria-labelledby="billing-heading">
    <div class="heading-row"><h2 id="billing-heading">Subscription credits and Fast usage</h2><span class="micro">Standard baseline, observed multiplier, and API-equivalent conversion</span></div>
    <div class="metrics" id="billing-metrics"></div>
    <p class="sub" id="billing-note"></p>
  </section>
  <section class="weekly" aria-labelledby="weekly-heading">
    <div><h2 id="weekly-heading">Median value of observed complete cycles</h2><p class="micro" id="weekly-range"></p><p class="micro" id="weekly-note"></p></div>
    <div class="weekly-values" id="weekly-values"></div>
  </section>
  <section class="panel" aria-labelledby="daily-heading">
    <div class="section-head">
      <div><h2 id="daily-heading" tabindex="-1">Daily usage</h2><p class="sub" id="daily-summary"></p></div>
      <div class="tabs" role="tablist" aria-label="Choose account for daily usage" id="account-tabs"></div>
    </div>
    <div id="daily-panel" role="tabpanel" tabindex="0">
      <div class="legend" id="daily-legend" aria-label="Model legend"></div>
      <div class="chart-scroll" id="daily-chart"></div>
      <div class="chart-footer"><span id="quota-note"></span><a href="#daily-details" id="show-daily-table">View daily details ↓</a></div>
    </div>
  </section>
</div>
<div class="details-area">
  <details class="disclosure" id="daily-details">
    <summary id="daily-details-heading">Daily details · models and quota</summary>
    <div class="detail-body"><p class="sub">Follows the account selection above. Each row is one day; quota % is percentage points consumed. Totals cover observed accounts, not average utilisation. Credits are subscription estimates; API USD is a separate rate view.</p><div id="daily-table"></div></div>
  </details>
  <section class="cycle-section" aria-labelledby="cycle-heading">
    <h2 id="cycle-heading">Weekly quota cycles</h2>
    <p class="sub" id="cycle-range"></p>
    <p class="sub">Badges show the percentage consumed; a check marks cycles that reached the complete threshold. Hover, focus, or tap a bar for details. Bars show raw API USD, with subscription credits alongside.</p>
    <div class="legend" id="cycle-legend" aria-label="Cycle model legend"></div>
    <div class="cycle-scale" id="cycle-scale" aria-hidden="true"></div>
    <div class="cycle-groups" id="cycle-groups"></div>
    <details class="disclosure" id="cycle-details">
      <summary id="cycle-details-heading">Cycle details · tokens and USD by model</summary>
      <div class="detail-body"><p class="sub">USD / 1% quota uses cycle API USD ÷ max(peak minus starting percentage points, 1). Credits / 1% uses estimated subscription credits with the same denominator. Each model key, including [1m], has its own columns.</p><div id="cycle-table"></div></div>
    </details>
  </section>
  <details class="disclosure" id="price-details">
    <summary>Pricing · API rates and subscription credits</summary>
    <div class="detail-body"><p class="sub">Only observed models and contexts are listed. API rates and subscription credits are per million tokens; cache writes are excluded.</p><div id="price-table"></div><p class="sub" id="price-note"></p></div>
  </details>
  <aside class="caveats" aria-labelledby="caveats-heading"><h2 id="caveats-heading">Caveats</h2><div id="caveat-list"></div></aside>
</div>
<footer class="footer"><span id="generated"></span><div class="source-status"><span id="source-status" role="status" aria-live="polite"></span><button type="button" id="retry-data" hidden>Retry refresh</button></div></footer>
<p class="sr-only" id="interaction-status" role="status" aria-live="polite"></p>
</main>
<div class="tooltip" id="chart-tooltip" role="tooltip" hidden></div>
<script type="application/json" id="usage-data">{script_json(data)}</script>
<script type="application/json" id="report-config">{script_json({'dataUrl': data_url})}</script>
<script>{JAVASCRIPT}</script>
</body>
</html>
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parent.parent
    parser.add_argument('--in', dest='inp', default=root / 'out' / 'usage.json')
    parser.add_argument('--out', default=root / 'out' / 'report.html')
    parser.add_argument('--title', default='Codex usage · API value and subscription credits')
    parser.add_argument('--theme', choices=('light', 'dark'), default='light')
    parser.add_argument('--data-url', metavar='URL', help='Fetch this JSON URL at page load; use the embedded snapshot if fetching fails')
    args = parser.parse_args()
    with open(args.inp, encoding='utf-8') as source:
        data = json.load(source)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(data, args.title, args.theme, args.data_url), encoding='utf-8')
    print('wrote', output)


if __name__ == '__main__':
    main()
