// The conversation log is a projection of the backend's turns, whichever channel (typed, spoken,
// handed off) or interface (this desktop, an HTTP client, the ACP bridge, a panel decision)
// produced them. Turns are rendered once, keyed by turn id, so polling and local rendering never
// duplicate one.
import { capabilityTitle } from "./actions-panel.js";
import { renderSearchEvidence } from "./search-evidence.js";
import { appendText, button } from "./ui/dom.js";
import { errorMessage, formatTime, statusState, statusText } from "./ui/format.js";
import { VERB } from "./ui/vocabulary.js";

const ORIGIN_TEXT = {
  api: "HTTP client",
  acp: "ACP client",
  panel: "Decided in a panel",
  extension: "Extension run",
  agent: "Agent run",
};

// A panel decision is recorded as the reply that settles the approval.
const PANEL_REPLIES = { confirm: "Approved", cancel: "Declined" };

const HISTORY_PAGE = 50;

export function turnChipLabels(turn) {
  const labels = [];
  if (turn.input_modality === "voice") labels.push("Voice");
  if (ORIGIN_TEXT[turn.origin]) labels.push(ORIGIN_TEXT[turn.origin]);
  return labels;
}

function chip(text, state = "", onClick = null) {
  const node = onClick ? button(text, { onClick }) : document.createElement("span");
  if (!onClick) node.textContent = text;
  node.className = "chip";
  if (state) node.dataset.state = state;
  return node;
}

function now() {
  return formatTime(new Date().toISOString(), { timeOnly: true });
}

export function createConversation({
  logEl,
  speakerName = () => "JARVIS",
  openSearchSource = () => undefined,
  onError = () => undefined,
  onOpenAction = null,
  onOpenAgent = null,
  getTurns = null,
  decide = null,
}) {
  const replies = new Map();
  let feedCursor = null;
  let syncing = null;
  let approvalCard = null;

  function place(article) {
    if (approvalCard?.parentNode === logEl) logEl.insertBefore(article, approvalCard);
    else logEl.appendChild(article);
    logEl.scrollTop = logEl.scrollHeight;
    return article;
  }

  function entry(kind, { speaker = "", stamp = now(), chips = [], text = "" }) {
    const article = document.createElement("article");
    article.className = `message ${kind}`;
    const meta = document.createElement("div");
    meta.className = "message-meta";
    appendText(meta, stamp, "span", "stamp");
    if (speaker) appendText(meta, speaker, "strong");
    meta.append(...chips);
    article.appendChild(meta);
    appendText(article, text || "(no text returned)", "p");
    return article;
  }

  function actionChipText(action) {
    return `${capabilityTitle(action.capability_id)} · ${statusText(action.status)}`;
  }

  function actionChips(turn) {
    return (turn.actions || []).map((action) => {
      const node = chip(actionChipText(action), statusState(action.status), onOpenAction ? () => onOpenAction(action.proposal_id) : null);
      node.dataset.proposalId = action.proposal_id;
      return node;
    });
  }

  // An action proposed in one turn is settled in a later one; every chip for it shows where it is now.
  function refreshActionChips(turn) {
    for (const action of turn.actions || []) {
      for (const node of logEl.querySelectorAll(".chip[data-proposal-id]")) {
        if (node.dataset.proposalId !== action.proposal_id) continue;
        node.textContent = actionChipText(action);
        node.dataset.state = statusState(action.status);
      }
    }
  }

  // A system or presence line, or the operator's own words before the turn comes back.
  function note(kind, text) {
    const speaker = kind === "system" ? "System" : kind === "user" ? "You" : "";
    return place(entry(kind, { speaker, text }));
  }

  function renderTurn(turn, { transcriptShown = false } = {}) {
    if (!turn) return;
    const existing = turn.turn_id ? replies.get(turn.turn_id) : null;
    if (existing) {
      // Rendered locally before the feed carried its action evidence; add that evidence now.
      const meta = existing.querySelector(".message-meta");
      if (meta && !existing.dataset.actions && turn.actions?.length) {
        meta.append(...actionChips(turn));
        existing.dataset.actions = "true";
      }
      refreshActionChips(turn);
      return;
    }
    const stamp = turn.started_at ? formatTime(turn.started_at, { timeOnly: true }) : now();
    const chips = turnChipLabels(turn).map((label) => chip(label));
    if (turn.transcript && !transcriptShown) {
      const said = turn.origin === "panel" ? PANEL_REPLIES[turn.transcript.trim().toLowerCase()] || turn.transcript : turn.transcript;
      place(entry("user", { speaker: "You", stamp, chips, text: said }));
    }
    const agent = turn.agent;
    const replyChips = actionChips(turn);
    if (agent && onOpenAgent) replyChips.unshift(chip("Agent", "", () => onOpenAgent(agent.profile_id)));
    const reply = entry(agent ? "agent" : "assistant", {
      speaker: agent ? agent.display_name : speakerName(turn.personality_profile_id),
      stamp,
      chips: transcriptShown ? [...chips, ...replyChips] : replyChips,
      text: turn.response_text || turn.failure_reason,
    });
    if (turn.turn_id) reply.dataset.turnId = turn.turn_id;
    reply.dataset.profileId = turn.personality_profile_id || "";
    if (turn.actions?.length) reply.dataset.actions = "true";
    renderSearchEvidence(reply, turn.search, openSearchSource, onError);
    if (turn.turn_id) replies.set(turn.turn_id, reply);
    place(reply);
    refreshActionChips(turn);
  }

  // Loads every turn after the last one this log has seen, including history at startup and
  // turns other interfaces made in the same session.
  function sync() {
    if (!getTurns) return Promise.resolve();
    if (syncing) return syncing;
    syncing = (async () => {
      try {
        for (;;) {
          const page = await getTurns(feedCursor);
          const turns = page?.turns || [];
          for (const turn of turns) {
            renderTurn(turn);
            feedCursor = turn.turn_id;
          }
          if (turns.length < HISTORY_PAGE) break;
        }
      } catch (error) {
        onError(errorMessage(error, "Conversation history is unavailable."));
      } finally {
        syncing = null;
      }
    })();
    return syncing;
  }

  // The approval the conversation is waiting on, answerable here as well as by reply or panel.
  function renderPending(pending) {
    if (!pending) {
      approvalCard?.remove();
      approvalCard = null;
      return;
    }
    if (approvalCard?.dataset.proposalId === pending.proposal_id) return;
    approvalCard?.remove();
    const card = entry("approval", { speaker: "Approval needed", text: pending.label || capabilityTitle(pending.capability_id) });
    card.dataset.proposalId = pending.proposal_id;
    if (pending.reason) appendText(card, pending.reason, "p", "panel-help");
    const buttons = document.createElement("div");
    buttons.className = "message-actions";
    const settle = (outcome) => async () => {
      for (const control of buttons.querySelectorAll("button")) control.disabled = true;
      try {
        await decide(pending.proposal_id, outcome);
        await sync();
      } catch (error) {
        onError(errorMessage(error, "That decision was not applied."));
        for (const control of buttons.querySelectorAll("button")) control.disabled = false;
      }
    };
    buttons.append(
      button(VERB.approve, { variant: "primary", onClick: settle("approved"), disabled: !decide }),
      button(VERB.decline, { onClick: settle("denied"), disabled: !decide }),
    );
    if (onOpenAction) buttons.appendChild(button("Details", { variant: "ghost", onClick: () => onOpenAction(pending.proposal_id) }));
    card.appendChild(buttons);
    logEl.appendChild(card);
    logEl.scrollTop = logEl.scrollHeight;
    approvalCard = card;
  }

  return { note, renderTurn, sync, renderPending };
}
