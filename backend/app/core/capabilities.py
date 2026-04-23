from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class HardwareProfile:
    os_name: str = "unknown"
    os_version: str = "unknown"
    arch: str = "unknown"
    cpu_name: str = "unknown"
    cpu_physical_cores: int | None = None
    cpu_logical_cores: int | None = None
    cpu_max_freq_mhz: float | None = None
    memory_total_gb: float | None = None
    memory_available_gb: float | None = None
    gpu_available: bool = False
    gpu_name: str | None = None
    gpu_vendor: str | None = None
    gpu_vram_gb: float | None = None
    gpu_vram_source: str | None = None
    cuda_available: bool = False
    cuda_version: str | None = None
    npu_available: bool = False
    npu_vendor: str | None = None
    npu_tops: float | None = None
    device_class: str = "unknown"
    profile_id: str = "unknown"
    profiled_at: str = "unknown"


@dataclass(slots=True)
class CapabilityFlags:
    supports_local_llm: bool = False
    supports_gpu_llm: bool = False
    supports_cuda_llm: bool = False
    supports_local_stt: bool = False
    supports_local_tts: bool = False
    supports_wake_word: bool = False
    supports_realtime_voice: bool = False
    supports_desktop_shell: bool = False
    requires_degraded_mode: bool = True
    qnn_available: bool = False
    directml_candidate: bool = False


@dataclass(slots=True)
class FullCapabilityReport:
    profile: HardwareProfile = field(default_factory=HardwareProfile)
    flags: CapabilityFlags = field(default_factory=CapabilityFlags)
