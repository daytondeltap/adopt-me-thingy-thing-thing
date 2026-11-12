"use strict";

const el = (id) => document.getElementById(id);
const number = new Intl.NumberFormat(undefined, { maximumFractionDigits: 6 });
const date = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const sources = { adoptmevalues: "Adopt Me Values", elvebredd: "Elvebredd" };
const sourceName = (source) => Object.hasOwn(sources, source) ? sources[source] : source;
const variantName = (variant) => variant.replaceAll("_", " ").replace(/\bfr\b/g, "Fly Ride").replace(/\bf\b/g, "Fly").replace(/\br\b/g, "Ride");
let series = [];
let active = null;

function parseExport(data) {
  if (data?.version !== 1 || !Array.isArray(data.series)) throw new Error("Choose a version 1 dashboard export.");
  for (const row of data.series) {
    if (!row || ![row.pet, row.source, row.variant].every((field) => typeof field === "string" && field)
        || !Array.isArray(row.points) || !row.points.length
        || !row.points.every((point, index) => Array.isArray(point) && typeof point[0] === "string"
          && Number.isFinite(Date.parse(point[0])) && Number.isFinite(point[1])
          && (point[2] === null || typeof point[2] === "string")
          && (index === 0 || Date.parse(point[0]) >= Date.parse(row.points[index - 1][0])))) {
      throw new Error("The export contains an invalid value history.");
    }
  }
  return data.series;
}

function showDetail(row) {
  el("detail").hidden = !row;
  if (!row) return;
  const last = row.points.at(-1);
  const delta = last[1] - row.points[0][1];
  const scale = row.source === "adoptmevalues" ? " Frost" : "";
  el("pet").textContent = row.pet;
  el("metadata").textContent = [sourceName(row.source), variantName(row.variant), last[2] && ("Demand " + last[2])].filter(Boolean).join(" · ");
  el("value").textContent = number.format(last[1]) + scale;
  el("movement").textContent = row.points.length > 1 ? (delta > 0 ? "+" : "") + number.format(delta) + scale + " over recorded history" : "";
  el("recorded").textContent = "Last recorded " + date.format(new Date(last[0]));
  el("chart").replaceChildren();
  if (row.points.length < 2) {
    const notice = document.createElement("p");
    notice.textContent = "The chart appears after a second observation.";
    el("chart").append(notice);
    return;
  }
  const canvas = document.createElement("canvas");
  canvas.width = 650;
  canvas.height = 220;
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", "Recorded history from " + number.format(row.points[0][1]) + " to " + number.format(last[1]) + scale);
  el("chart").append(canvas);
  const ctx = canvas.getContext("2d");
  const [low, high] = row.points.reduce(([min, max], point) => [Math.min(min, point[1]), Math.max(max, point[1])], [Infinity, -Infinity]);
  const start = Date.parse(row.points[0][0]);
  const duration = Date.parse(last[0]) - start;
  ctx.strokeStyle = "#aef2cf";
  ctx.lineWidth = 3;
  ctx.beginPath();
  row.points.forEach(([stamp, value], index) => {
    const x = 24 + 602 * (duration ? (Date.parse(stamp) - start) / duration : index / (row.points.length - 1));
    const y = 24 + 172 * (high === low ? 0.5 : 1 - (value - low) / (high - low));
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

function render() {
  const term = el("search").value.trim().toLowerCase();
  const source = el("source").value;
  const matches = series.filter((row) => row.pet.toLowerCase().includes(term) && (!source || row.source === source));
  if (!matches.includes(active)) active = matches[0] ?? null;
  const fragment = document.createDocumentFragment();
  for (const row of matches) {
    const tr = document.createElement("tr");
    const name = tr.insertCell();
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = row.pet;
    button.setAttribute("aria-pressed", String(row === active));
    button.addEventListener("click", () => {
      active = row;
      for (const other of el("rows").querySelectorAll("button")) {
        other.setAttribute("aria-pressed", String(button === other));
      }
      showDetail(row);
    });
    const meta = document.createElement("small");
    meta.textContent = sourceName(row.source) + " · " + variantName(row.variant);
    name.append(button, meta);
    tr.insertCell().textContent = number.format(row.points.at(-1)[1]);
    fragment.append(tr);
  }
  el("rows").replaceChildren(fragment);
  el("empty").hidden = matches.length > 0;
  showDetail(active);
}

el("search").addEventListener("input", render);
el("source").addEventListener("change", render);
el("file").addEventListener("change", async (event) => {
  const input = event.currentTarget;
  const file = input.files[0];
  if (!file) return;
  input.disabled = true;
  try {
    series = parseExport(JSON.parse(await file.text()));
    el("source").replaceChildren(new Option("All sources", ""));
    for (const source of [...new Set(series.map((row) => row.source))].sort()) {
      el("source").add(new Option(sourceName(source), source));
    }
    el("search").value = "";
    el("dashboard").hidden = series.length === 0;
    el("status").textContent = series.length
      ? "Loaded " + series.length + " pet value series."
      : "This export is empty. Run an ingest pass and export again.";
    render();
  } catch (error) {
    el("status").textContent = (error instanceof SyntaxError ? "This file is not valid JSON." : error.message)
      + (series.length ? " The previous export is still open." : "");
  } finally {
    input.value = "";
    input.disabled = false;
  }
});
