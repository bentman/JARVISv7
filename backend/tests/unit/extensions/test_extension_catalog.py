from __future__ import annotations

from backend.app.extensions.catalog import ExtensionObservation, build_extension_descriptors
from backend.app.extensions.contracts import ExtensionCatalog
from backend.app.extensions.skills import parse_skill_frontmatter


def descriptors(**observation) -> dict[str, object]:
    built = build_extension_descriptors(ExtensionObservation(**observation))
    return {item.extension_id: item for item in built}


def test_search_readiness_follows_the_live_provider_flags() -> None:
    enabled = descriptors(search_providers=(("ddgs", True),))["search_provider:ddgs"]
    assert (enabled.state, enabled.availability, enabled.readiness) == ("enabled", "available", "ready")

    disabled = descriptors(search_providers=(("ddgs", False),))["search_provider:ddgs"]
    assert (disabled.state, disabled.availability, disabled.readiness) == (
        "disabled", "disabled", "unavailable",
    )
    assert "Enable DDGS, SearXNG, or Tavily" in disabled.unavailable_explanation


def test_a_locked_secret_store_degrades_the_provider_family() -> None:
    built = descriptors(
        providers=(("builtin:managed-llama-cpp", "Managed", "configured", True),),
        provider_store_locked=True,
    )
    provider = built["provider:builtin-managed-llama-cpp"]

    assert provider.availability == "misconfigured"
    assert provider.readiness == "degraded"
    assert "secret store is locked" in provider.unavailable_explanation


def test_a_credential_required_provider_is_degraded_but_available() -> None:
    provider = descriptors(providers=(("p1", "Cloud", "credential_required", False),))["provider:p1"]

    assert (provider.readiness, provider.availability) == ("degraded", "available")
    assert provider.trust == "operator"


def test_operator_authored_and_application_providers_are_distinguished() -> None:
    built = descriptors(
        providers=(
            ("builtin:managed-llama-cpp", "Managed", "configured", True),
            ("abc123", "My Cloud", "configured", False),
        )
    )

    assert built["provider:builtin-managed-llama-cpp"].trust == "application"
    assert built["provider:abc123"].trust == "operator"


def test_a_personality_declaring_itself_disabled_is_reported_disabled() -> None:
    built = descriptors(
        personalities=(
            ("default", "Morgan", True, "config/personality/default.yaml"),
            ("retired", "Old", False, "config/personality/retired.yaml"),
        )
    )

    assert built["personality:default"].state == "enabled"
    assert built["personality:retired"].state == "disabled"
    assert "enabled: false" in built["personality:retired"].unavailable_explanation


def test_duplicate_identifiers_are_reported_as_collisions() -> None:
    built = build_extension_descriptors(
        ExtensionObservation(
            personalities=(
                ("twin", "First", True, "config/personality/alpha.yaml"),
                ("twin", "Second", True, "config/personality/beta.yaml"),
            )
        )
    )

    assert len(built) == 1
    assert built[0].collisions == ("2 entries share this identifier",)


def test_a_skill_with_scripts_registers_disabled_so_it_cannot_look_runnable() -> None:
    manifest = parse_skill_frontmatter(
        "builder",
        "---\nname: Builder\ndescription: d\nversion: '1'\nscripts: [build.py]\n---\nbody",
        "s",
    )

    skill = descriptors(skills=(manifest,))["skill:builder"]

    assert skill.availability == "disabled"
    assert "privileged_execution capability" in skill.unavailable_explanation
    assert skill.trust == "external"


def test_an_operator_override_beats_the_declared_state() -> None:
    observation = ExtensionObservation(search_providers=(("ddgs", True),))

    built = build_extension_descriptors(observation, {"search_provider:ddgs": ("disabled", None)})

    assert built[0].state == "disabled"
    assert "An operator set this extension to disabled." in built[0].unavailable_explanation


def test_every_built_descriptor_registers_without_collision() -> None:
    built = build_extension_descriptors(
        ExtensionObservation(
            settings=(("USE_DDGS", "primary"),),
            personalities=(("default", "Morgan", True, "p.yaml"),),
            search_providers=(("ddgs", True),),
            capabilities=(("search-public-web", "ready", "available"),),
        )
    )
    catalog = ExtensionCatalog()
    for descriptor in built:
        catalog.register(descriptor)

    assert catalog.families() == {
        "capability": 1, "personality": 1, "search_provider": 1, "setting": 1,
    }
