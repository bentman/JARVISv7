// One operator vocabulary for every panel and the conversation. "Action" is the operator word for
// a governed operation; "capability" appears only inside Details.
export const VERB = {
  approve: "Approve",
  decline: "Decline",
  cancelRun: "Cancel run",
  discard: "Discard",
  delete: "Delete",
  enable: "Enable",
  disable: "Disable",
  save: "Save",
  refresh: "Refresh",
};

export const TEXT = {
  loading: (thing) => `Loading ${thing}…`,
  unavailable: (thing) => `${thing} unavailable.`,
  empty: (thing) => `No ${thing} yet.`,
};
