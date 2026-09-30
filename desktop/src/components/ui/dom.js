// DOM building blocks shared by the Advanced Controls panels and the conversation.
import { formatValue } from "./format.js";

export function appendText(parent, text, tagName = "span", className = "") {
  const node = document.createElement(tagName);
  node.textContent = text;
  if (className) node.className = className;
  parent.appendChild(node);
  return node;
}

export function option(value, label, selected = false) {
  const node = document.createElement("option");
  node.value = value;
  node.textContent = label;
  node.selected = selected;
  return node;
}

const VARIANT_CLASSES = { primary: "btn-primary", danger: "btn-danger", ghost: "btn-ghost" };

// Plain buttons are secondary; `variant` selects primary, danger, or ghost.
export function button(text, { variant = "", focusKey = "", onClick = null, disabled = false, type = "button", title = "" } = {}) {
  const node = document.createElement("button");
  node.type = type;
  node.textContent = text;
  node.disabled = disabled;
  if (VARIANT_CLASSES[variant]) node.className = VARIANT_CLASSES[variant];
  if (focusKey) node.dataset.focusKey = focusKey;
  if (title) node.title = title;
  if (onClick) node.addEventListener("click", onClick);
  return node;
}

export function buttonRow(...buttons) {
  const row = document.createElement("div");
  row.className = "panel-buttons";
  row.append(...buttons.filter(Boolean));
  return row;
}

export function field(labelText, control, { help = "" } = {}) {
  const label = document.createElement("label");
  label.className = "panel-field";
  appendText(label, labelText);
  label.appendChild(control);
  if (help) appendText(label, help, "span", "panel-help");
  return label;
}

export function labeledValue(parent, label, value) {
  const row = document.createElement("div");
  row.className = "panel-field-row";
  appendText(row, label, "dt");
  appendText(row, formatValue(value), "dd");
  parent.appendChild(row);
  return row;
}

export function facts(entries) {
  const list = document.createElement("dl");
  list.className = "panel-facts";
  for (const [label, value] of entries) labeledValue(list, label, value);
  return list;
}

// Backend identifiers and raw records stay reachable for audit, but only behind an explicit
// disclosure; visible text is written for an operator.
export function details(entries, raw = null, summary = "Details") {
  const node = document.createElement("details");
  appendText(node, summary, "summary");
  const shown = entries.filter(([, value]) => value !== null && value !== undefined && value !== "");
  if (shown.length) node.appendChild(facts(shown));
  if (raw !== null && raw !== undefined) appendText(node, JSON.stringify(raw, null, 2), "pre");
  return node;
}

export function statusBadge(text, state) {
  const node = document.createElement("span");
  node.className = "status-badge";
  node.textContent = text;
  node.dataset.state = state;
  return node;
}
