const STORAGE_KEY = "jarvisv7_appearance";

const DEFAULT_PREFS = {
  fontSize: "default",
  density: "default",
  accent: "default",
};

const PRESETS = {
  fontSize: {
    default: {
      "--text-xs": "0.75rem",
      "--text-sm": "0.8125rem",
      "--text-md": "0.875rem",
      "--text-lg": "1rem",
      "--text-xl": "1.25rem",
    },
    larger: {
      "--text-xs": "0.8125rem",
      "--text-sm": "0.875rem",
      "--text-md": "0.9375rem",
      "--text-lg": "1.125rem",
      "--text-xl": "1.375rem",
    },
  },
  density: {
    default: {
      "--space-1": "4px",
      "--space-2": "8px",
      "--space-3": "12px",
      "--space-4": "16px",
      "--space-5": "24px",
      "--space-6": "32px",
    },
    compact: {
      "--space-1": "3px",
      "--space-2": "6px",
      "--space-3": "8px",
      "--space-4": "12px",
      "--space-5": "18px",
      "--space-6": "24px",
    },
  },
  accent: {
    default: {
      "--color-accent": "#00bfff",
    },
    neutral: {
      "--color-accent": "#cbd5e1",
    },
  },
};

function loadPrefs() {
  try {
    const stored = window.localStorage?.getItem(STORAGE_KEY);
    if (!stored) return { ...DEFAULT_PREFS };
    const parsed = JSON.parse(stored);
    return {
      fontSize: PRESETS.fontSize[parsed.fontSize] ? parsed.fontSize : DEFAULT_PREFS.fontSize,
      density: PRESETS.density[parsed.density] ? parsed.density : DEFAULT_PREFS.density,
      accent: PRESETS.accent[parsed.accent] ? parsed.accent : DEFAULT_PREFS.accent,
    };
  } catch (error) {
    return { ...DEFAULT_PREFS };
  }
}

function savePrefs(prefs) {
  try {
    window.localStorage?.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch (error) {
    return;
  }
}

function applyPrefs(prefs) {
  const style = document.documentElement.style;
  for (const groupName of ["fontSize", "density", "accent"]) {
    const group = PRESETS[groupName][prefs[groupName]] || PRESETS[groupName][DEFAULT_PREFS[groupName]];
    for (const [token, value] of Object.entries(group)) {
      style.setProperty(token, value);
    }
  }
}

function option(value, labelText) {
  const el = document.createElement("option");
  el.value = value;
  el.textContent = labelText;
  return el;
}

function control(labelText, value, choices, onChange) {
  const label = document.createElement("label");
  const text = document.createElement("span");
  const select = document.createElement("select");

  text.textContent = labelText;
  for (const [choiceValue, choiceLabel] of choices) {
    select.appendChild(option(choiceValue, choiceLabel));
  }
  select.value = value;
  select.addEventListener("change", () => onChange(select.value));
  label.append(text, select);
  return label;
}

export function applyStored() {
  applyPrefs(loadPrefs());
}

export function createAppearanceControls() {
  const prefs = loadPrefs();
  const section = document.createElement("section");
  const heading = document.createElement("h3");
  const update = (key, value) => {
    const nextPrefs = { ...loadPrefs(), [key]: value };
    savePrefs(nextPrefs);
    applyPrefs(nextPrefs);
  };

  section.className = "appearance-panel settings-subsection";
  heading.textContent = "Appearance";
  section.append(
    heading,
    control("Font", prefs.fontSize, [["default", "Default"], ["larger", "Larger"]], (value) => update("fontSize", value)),
    control("Density", prefs.density, [["default", "Default"], ["compact", "Compact"]], (value) => update("density", value)),
    control("Accent", prefs.accent, [["default", "Default"], ["neutral", "Neutral"]], (value) => update("accent", value)),
  );
  return section;
}

export function initAppearanceControls(containerEl) {
  containerEl.replaceChildren(createAppearanceControls());
}
