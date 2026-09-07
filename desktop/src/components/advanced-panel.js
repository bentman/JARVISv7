/**
 * Advanced-control category sequencing.
 *
 * The category rail is single-select: opening one category closes whichever other one is open,
 * and dismissing the surface closes whatever is open. Dismissal is delegated to `dismiss` so the
 * host owns the actual dialog element.
 */

export function createAdvancedPanelCoordinator({ categories = [], dismiss = null } = {}) {
  const panels = categories.filter((category) => category.id && category.isOpen && category.open && category.close);
  // A panel closing during a category switch or a teardown reports through its own onClose hook.
  // Suppressing dismissal for the duration keeps that report from re-entering as a new dismissal.
  let suppressDismiss = false;

  function closeOpenPanels(except) {
    suppressDismiss = true;
    try {
      for (const panel of panels) {
        if (panel !== except && panel.isOpen()) panel.close();
      }
    } finally {
      suppressDismiss = false;
    }
  }

  function activeCategoryId() {
    return panels.find((panel) => panel.isOpen())?.id || "";
  }

  async function openCategory(id) {
    const target = panels.find((panel) => panel.id === id);
    if (!target) return "";
    if (target.isOpen()) return target.id;
    closeOpenPanels(target);
    await target.open();
    return target.id;
  }

  function closeActive() {
    closeOpenPanels(null);
  }

  function requestClose() {
    if (suppressDismiss) return;
    dismiss?.();
  }

  return {
    categoryIds: () => panels.map((panel) => panel.id),
    activeCategoryId,
    openCategory,
    closeActive,
    requestClose,
    isOpen: () => Boolean(activeCategoryId()),
  };
}
