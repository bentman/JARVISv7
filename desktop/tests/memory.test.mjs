import { test } from "node:test";
import { strict as assert } from "node:assert";
import { createMemoryPanelController, curationActivityState, formatCurationResult, memoryActionsEnabled } from "../src/components/memory-panel.js";
import { apiClient, memoryPanel, backend, lib, index, deferred, memoryDetail, memoryRecord } from "./support.mjs";

test("stale list responses must not replace newer filters", async () => {
  const firstList = deferred();
  const listController = createMemoryPanelController({
    listMemories: ({ query }) =>
      query === "old"
        ? firstList.promise
        : Promise.resolve({ records: [memoryRecord({ fact_id: "new", text: "new result" })] }),
  });
  const staleListRequest = listController.refreshList({ query: "old" });
  await listController.refreshList({ query: "new" });
  firstList.resolve({ records: [memoryRecord({ fact_id: "old", text: "old result" })] });
  await staleListRequest;
  assert.equal(listController.snapshot().list.records[0].fact_id, "new", "stale list responses must not replace newer filters");
});

test("stale detail responses must not replace newer selection", async () => {
  const firstDetail = deferred();
  const detailController = createMemoryPanelController({
    getMemoryDetail: (factId) =>
      factId === "old" ? firstDetail.promise : Promise.resolve(memoryDetail(memoryRecord({ fact_id: "new" }))),
  });
  const staleDetailRequest = detailController.selectMemory("old");
  await detailController.selectMemory("new");
  firstDetail.resolve(memoryDetail(memoryRecord({ fact_id: "old" })));
  await staleDetailRequest;
  assert.equal(detailController.snapshot().detail.record.fact_id, "new", "stale detail responses must not replace newer selection");
});

test("mutation lock must engage while request is pending", async () => {
  const failedMutation = deferred();
  const mutationSnapshots = [];
  const mutationController = createMemoryPanelController(
    {
      getMemoryDetail: () => Promise.resolve(memoryDetail()),
      listMemories: () => Promise.resolve({ records: [memoryRecord()] }),
      confirmMemory: () => failedMutation.promise,
    },
    (snapshot) => mutationSnapshots.push(snapshot),
  );
  await mutationController.selectMemory("memory-1");
  const pendingConfirm = mutationController.confirm();
  assert.equal(mutationController.snapshot().mutationPending, true, "mutation lock must engage while request is pending");
  assert.equal(mutationController.snapshot().detail.record.text, "The user prefers concise answers.", "pending mutation must retain record");
  failedMutation.reject(new Error("confirm failed"));
  await pendingConfirm;
  assert.equal(mutationController.snapshot().mutationPending, false, "mutation lock must release after failure");
  assert.equal(mutationController.snapshot().detail.record.revision, 1, "failed confirm must retain rendered revision");
  assert.ok(
    mutationSnapshots.some((snapshot) => snapshot.mutationPending) &&
      mutationSnapshots.at(-1).mutationPending === false,
    "rendered mutation state must disable then re-enable controls",
  );
});

test("record 409 must reload current backend detail", async () => {
  let conflictDetailReads = 0;
  const recordConflict = new Error("conflict");
  recordConflict.status = 409;
  recordConflict.detail = { error: "conflict", current_revision: 2, current_state: "active" };
  const conflictController = createMemoryPanelController({
    getMemoryDetail: () =>
      Promise.resolve(memoryDetail(memoryRecord({ revision: ++conflictDetailReads, lifecycle_state: conflictDetailReads > 1 ? "active" : "pending_review" }))),
    listMemories: () => Promise.resolve({ records: [memoryRecord({ revision: 2, lifecycle_state: "active" })] }),
    confirmMemory: () => Promise.reject(recordConflict),
  });
  await conflictController.selectMemory("memory-1");
  await conflictController.confirm();
  assert.equal(conflictController.snapshot().detail.record.revision, 2, "record 409 must reload current backend detail");
  assert.ok(conflictController.snapshot().conflict.includes("not applied"), "record 409 must remain visibly actionable");
});

test("policy 409 must reload current backend policy", async () => {
  let policyReads = 0;
  const policyConflict = new Error("policy conflict");
  policyConflict.status = 409;
  policyConflict.detail = { error: "conflict", current_revision: 2, current_state: "enabled" };
  const policyController = createMemoryPanelController({
    getMemoryPolicy: () =>
      Promise.resolve({ automatic_curation_enabled: policyReads++ > 0, revision: policyReads, updated_at: "now" }),
    updateMemoryPolicy: () => Promise.reject(policyConflict),
    getMemoryCurationStatus: () => Promise.resolve({}),
  });
  await policyController.refreshPolicy();
  await policyController.updatePolicy(true);
  assert.equal(policyController.snapshot().policy.revision, 2, "policy 409 must reload current backend policy");
  assert.ok(policyController.snapshot().conflict.includes("reloaded"), "policy 409 must display visible reload conflict");
});

test("memory contract refresh must retain backend layer states", async () => {
  const contractsController = createMemoryPanelController({
    getMemoryLayers: () =>
      Promise.resolve({
        layers: [
          { layer: "semantic_memory", implementation_state: "implemented" },
          { layer: "procedural_memory", implementation_state: "defined_next" },
          { layer: "cross_device_shared_memory", implementation_state: "decision_required" },
        ],
        source_artifact_erasure_scope: "Source turn and session artifacts are separate.",
      }),
    getArtifactRetentionPolicy: () =>
      Promise.resolve({
        source_artifact_owner: "backend/app/artifacts",
        physical_erasure_available: false,
        source_artifact_erasure_scope: "Physical erasure is a separate action.",
      }),
  });
  await contractsController.refreshContracts();
  assert.equal(
    contractsController.snapshot().layers.layers[1].implementation_state,
    "defined_next",
    "memory contract refresh must retain backend layer states",
  );
  assert.equal(
    contractsController.snapshot().retentionPolicy.source_artifact_owner,
    "backend/app/artifacts",
    "memory contract refresh must retain retention owner",
  );
});

test("forget must require explicit confirmation", async () => {
  let forgetCalls = 0;
  const forgetResponse = deferred();
  const forgetController = createMemoryPanelController({
    getMemoryDetail: () => Promise.resolve(memoryDetail()),
    listMemories: () => Promise.resolve({ records: [memoryRecord()] }),
    forgetMemory: () => {
      forgetCalls += 1;
      return forgetResponse.promise;
    },
  });
  await forgetController.selectMemory("memory-1");
  await forgetController.forget(() => Promise.resolve(false));
  assert.equal(forgetCalls, 0, "forget must require explicit confirmation");
  const pendingForget = forgetController.forget(() => Promise.resolve(true));
  await Promise.resolve();
  assert.equal(forgetCalls, 1, "confirmed forget must call the backend once");
  assert.equal(forgetController.snapshot().detail.record.lifecycle_state, "pending_review", "forget must not optimistically remove or alter the record");
  forgetResponse.resolve(memoryDetail(memoryRecord({ revision: 2, lifecycle_state: "forgotten" })));
  await pendingForget;
});

test("a failed correct, dispute, or forget must retain the rendered record", async () => {
  for (const action of ["correct", "dispute", "forget"]) {
    const controller = createMemoryPanelController({
      getMemoryDetail: () => Promise.resolve(memoryDetail()),
      listMemories: () => Promise.resolve({ records: [memoryRecord()] }),
      [`${action}Memory`]: () => Promise.reject(new Error(`${action} failed`)),
    });
    await controller.selectMemory("memory-1");
    if (action === "correct") {
      await controller.correct({ replacementText: "replacement" });
    } else if (action === "forget") {
      await controller.forget(() => Promise.resolve(true));
    } else {
      await controller.dispute();
    }
    assert.equal(controller.snapshot().detail.record.revision, 1, `failed ${action} must retain the rendered record`);
  }
});

test("successful correction must refresh replacement detail from backend", async () => {
  let correctionDetailId = "memory-1";
  const correctionController = createMemoryPanelController({
    getMemoryDetail: (factId) => {
      correctionDetailId = factId;
      return Promise.resolve(memoryDetail(memoryRecord({ fact_id: factId, revision: factId === "memory-2" ? 1 : 2 })));
    },
    listMemories: () => Promise.resolve({ records: [] }),
    correctMemory: () =>
      Promise.resolve({
        original: memoryRecord({ revision: 2, superseded_by_fact_id: "memory-2", lifecycle_state: "superseded" }),
        replacement: memoryRecord({ fact_id: "memory-2", text: "The user prefers detailed answers.", value: "detailed" }),
        relation: "superseded_by",
      }),
  });
  await correctionController.selectMemory("memory-1");
  await correctionController.correct({ replacementText: "The user prefers detailed answers.", replacementValue: "detailed" });
  assert.equal(correctionDetailId, "memory-2", "successful correction must refresh replacement detail from backend");
  assert.equal(correctionController.snapshot().correction.original.superseded_by_fact_id, "memory-2", "correction must retain original supersession truth");
  assert.equal(correctionController.snapshot().correction.replacement.fact_id, "memory-2", "correction must retain replacement truth");
});

test("renderer must not disable actions from lifecycle transition policy", async () => {
  assert.equal(
    memoryActionsEnabled(memoryRecord({ lifecycle_state: "superseded" }), false),
    true,
    "renderer must not disable actions from lifecycle transition policy",
  );
  assert.equal(
    memoryActionsEnabled(memoryRecord({ lifecycle_state: "backend_future_state" }), true),
    false,
    "the in-flight mutation lock must remain the only renderer action gate",
  );
});

test("renderer must submit the current revision and let the backend decide transition validity", async () => {
  let submittedRevision = null;
  const invalidTransition = new Error("invalid transition");
  invalidTransition.detail = {
    error: "invalid_transition",
    message: "confirm memory transition is not allowed",
  };
  const backendOwnedTransitionController = createMemoryPanelController({
    getMemoryDetail: () =>
      Promise.resolve(memoryDetail(memoryRecord({ revision: 7, lifecycle_state: "superseded" }))),
    confirmMemory: (_factId, expectedRevision) => {
      submittedRevision = expectedRevision;
      return Promise.reject(invalidTransition);
    },
  });
  await backendOwnedTransitionController.selectMemory("memory-1");
  await backendOwnedTransitionController.confirm();
  assert.equal(submittedRevision, 7, "renderer must submit the current revision and let the backend decide transition validity");
  assert.equal(
    backendOwnedTransitionController.snapshot().detail.record.lifecycle_state,
    "superseded",
    "backend transition rejection must retain the inspected record",
  );
  assert.equal(
    backendOwnedTransitionController.snapshot().detailError,
    "confirm memory transition is not allowed",
    "backend transition rejection must display typed backend truth",
  );
});

test("an available worker without active work must display idle", async () => {
  const availableIdleCuration = {
    service_available: true,
    processor_available: true,
    worker_running: true,
    drain_active: false,
    degraded: false,
    retry_blocked: false,
    pending_count: 0,
    processing_count: 0,
    failed_count: 0,
    current_job_id: null,
  };
  assert.equal(
    curationActivityState(availableIdleCuration),
    "idle",
    "an available worker without active work must display idle",
  );
  assert.equal(
    curationActivityState({ ...availableIdleCuration, processing_count: 1 }),
    "running",
    "a processing job must display running",
  );
  assert.equal(
    curationActivityState({ ...availableIdleCuration, current_job_id: "job-1" }),
    "running",
    "a current job must display running",
  );
  assert.equal(
    curationActivityState({ ...availableIdleCuration, drain_active: true }),
    "running",
    "an active drain must display running",
  );
  assert.equal(
    curationActivityState({ ...availableIdleCuration, degraded: true }),
    "degraded",
    "backend degraded status must remain degraded",
  );
  assert.equal(
    curationActivityState({ ...availableIdleCuration, retry_blocked: true }),
    "blocked",
    "backend blocked status must remain blocked",
  );
  assert.equal(
    formatCurationResult({
      reason_code: "review_only_candidates_resolved",
      candidates_proposed: 3,
      candidates_rejected: 1,
      active_records_created: 0,
      pending_review_created: 2,
      records_reinforced: 0,
      records_superseded_or_disputed: 0,
      duplicate_noops: 1,
      failure_count: 0,
    }),
    "review_only_candidates_resolved · proposed 3 · pending review 2 · active 0 · rejected 1 · duplicates 1 · reinforced 0 · superseded/disputed 0 · failures 0",
    "desktop curation outcome must render only the structured backend result",
  );
  assert.equal(
    formatCurationResult(null),
    "",
    "desktop must not infer a processor result when backend truth is absent",
  );
});

test("renderer must not duplicate lifecycle transition policy", async () => {
  for (const route of ["/memory/policy", "/memory/curation/status", "/memory/{fact_id}"]) {
    assert.ok(backend.includes(route), `backend bridge must include ${route}`);
  }
  for (const field of [
    "evidence_authority",
    "lifecycle_state",
    "eligible_for_normal_retrieval",
    "expectedRevision",
    "source_session_id",
    "source_turn_id",
    "source_field",
    "superseded_by_fact_id",
  ]) {
    assert.ok(memoryPanel.includes(field) || apiClient.includes(field), `memory surface must include ${field}`);
  }
  assert.ok(!memoryPanel.includes("ACTION_STATES"), "renderer must not duplicate lifecycle transition policy");
  assert.ok(!memoryPanel.includes(".has(record.lifecycle_state)"), "action availability must not be inferred from lifecycle state");
  assert.ok(index.includes('id="memory-panel"'), "operator area must include one hidden Memory panel");
});
