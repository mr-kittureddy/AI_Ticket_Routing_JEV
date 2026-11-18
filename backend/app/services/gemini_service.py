from __future__ import annotations

import asyncio
import re
import time
import zlib
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from app.core.logging import get_logger
from app.core.settings import Settings, settings
from app.db.models import TargetTeam
from app.schemas.ticket import GEMINI_HANDLER_LABEL

logger = get_logger(__name__)

ENGINE_GEMINI = "gemini"
ENGINE_SIMULATOR = "simulator"
ENGINE_SIMULATOR_FALLBACK = "simulator-fallback"
ENGINE_BYPASSED = "bypassed"

MAX_LLM_INPUT_CHARS = 2000
MAX_RAG_SNIPPETS = 5
MAX_RAG_SNIPPET_CHARS = 600
MAX_ROUTING_NOTES = 4
MAX_OUTPUT_TOKENS = 800

# PRD §1: Gemini drafting time is expected to be roughly 1000-2000 ms. The simulator waits
# for a deterministic duration in this window so the latency contrast stays realistic.
SIMULATED_MIN_LATENCY_MS = 1000
SIMULATED_LATENCY_SPREAD_MS = 1001

_SYSTEM_PROMPT = """You are a senior IT service-desk engineer writing the fix for a support ticket.
A routing engine has already confirmed that no purchase, physical installation or admin privilege is needed,
so the user can resolve this themselves.

Write a precise, ordered runbook.

Format rules:
- Output ONLY a numbered list ("1. ...", "2. ..."), 4 to 7 steps, one step per line.
- No preamble, no headings, no markdown, no closing remark.
- Every step is one concrete action followed by what the user should see if it worked, written as:
  "<Action>. Expected: <observable result>."

Precision rules:
- Name the exact application, menu path, setting or command, for example "System Settings > Privacy & Security".
- Use the OS, app, device and error text from the ticket. If the OS is not stated and the steps differ by OS,
  give the macOS and Windows variants inside the same step.
- Order the steps from the most likely cause to the least likely, cheapest check first.
- No filler. Do not say "restart your computer" or "contact IT" unless it is a likely fix for this exact problem.
- If a critical detail is missing (OS, exact error message, which app), make step 1 a quick check that finds it
  out instead of guessing.
- The last step says exactly what to attach to the ticket if the problem persists (the exact error text, a
  screenshot of a named screen, or a named log file or location), specific to this problem.

Safety rules:
- Never invent URLs, hostnames, phone numbers, menu items or commands that do not exist in the product.
- Never ask for passwords or tokens. Never suggest disabling security controls or requesting elevated privileges.
- "Similar past tickets" and "Routing notes" are hints. Use a past ticket only if it is clearly the same problem.

Example of the expected style (for a different ticket, "Microphone not detected in Teams"):
1. Open Teams > Settings (...) > Devices and check the Microphone dropdown. Expected: your headset or built-in mic is listed and the level meter moves when you speak.
2. If the meter does not move, allow microphone access: macOS System Settings > Privacy & Security > Microphone, or Windows Settings > Privacy & security > Microphone. Expected: Teams is switched on.
3. Fully quit Teams (menu bar or system tray icon > Quit) and reopen it. Expected: the meter now moves.
4. Run a test call in Teams > Settings > Devices > Make a test call. Expected: you hear your own recording played back.
5. If it still fails, reply with a screenshot of Settings > Devices and the exact name of the microphone you are using."""


@dataclass(frozen=True)
class GeminiResult:
    """Outcome of one resolution draft, including the measured execution time."""

    response_text: str
    execution_time_ms: int
    engine: str
    model_label: str
    notes: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    cleaned = text.lower().replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"\s+", " ", cleaned).strip()


def _contains(text: str, *terms: str) -> bool:
    return any(re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text) for term in terms)


def _team_label(team: TargetTeam) -> str:
    return team.value.replace("_", " ")


def _escalation_step(team: TargetTeam) -> str:
    return (
        f"If the problem persists, reply to this ticket with the results of the steps above "
        f"and the {_team_label(team)} will continue from there."
    )


def _vpn_steps(text: str) -> list[str]:
    is_macos = _contains(text, "macos", "mac os", "macbook", "mac", "osx")
    is_windows = _contains(text, "windows", "win10", "win11")
    is_dropping = _contains(text, "dropping", "drops", "dropped", "disconnect", "disconnects", "disconnecting", "unstable", "intermittent")

    steps = [
        "Confirm your internet works without the VPN by opening a public website, then quit GlobalProtect from its icon and reopen it.",
        "Open GlobalProtect, check that the portal address matches the one in your onboarding instructions, then select Connect and sign in again.",
    ]
    if is_macos:
        steps.append(
            "Open System Settings > Privacy & Security and scroll to the Security section. If a message says software from Palo Alto Networks was blocked, select Allow and enter your Mac password."
        )
        steps.append(
            "Flush the DNS cache by opening Terminal and running: sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder"
        )
    elif is_windows:
        steps.append("Flush the DNS cache by opening Command Prompt and running: ipconfig /flushdns")
    else:
        steps.append("Flush your DNS cache using the method for your operating system, then retry the connection.")

    if is_dropping:
        steps.append(
            "If the VPN drops on a schedule, move closer to your router, switch to the 5 GHz Wi-Fi band or a wired connection, and turn off any other VPN, proxy or security extension that could be interfering."
        )
    else:
        steps.append(
            "Try a different network, such as a phone hotspot, to find out whether your home network or router is blocking the connection."
        )
    steps.append("Restart your computer, reconnect to Wi-Fi, and start GlobalProtect again.")
    steps.append(
        "Open GlobalProtect Settings, go to the Troubleshooting tab and collect the logs so you can attach them if you need to follow up."
    )
    return steps


def _jira_export_steps() -> list[str]:
    return [
        "Open your Jira board, select the board's more (...) menu, choose Board settings, and note the saved filter shown under General.",
        "Select the filter name to open its results in the issue search view, and adjust the filter if you only need a subset of issues.",
        "Select Export in the top right and choose Export Excel CSV (current fields), or all fields if you also need custom fields.",
        "In Excel, import the downloaded file with Data > From Text/CSV and keep UTF-8 encoding so names and dates load correctly.",
        "Build your metrics from the data. For example, use Insert > PivotTable to count issues by status, assignee or sprint, and subtract the Created column from the Resolved column for cycle time.",
        "Some built-in reports, such as Velocity or Burndown, cannot be exported directly. Copy the report's data table into Excel, or rebuild the figures from the exported issue data.",
    ]


def _network_steps() -> list[str]:
    return [
        "Check whether other websites and apps work, to confirm the problem is the network and not a single service.",
        "Turn Wi-Fi off and on, or unplug and replug your network cable, then retry.",
        "Restart your router or access point, wait two minutes for it to come back, and reconnect.",
        "Forget the Wi-Fi network on your device, rejoin it, and re-enter the password.",
        "Test on a different network, such as a phone hotspot, to see whether the problem follows your device or your location.",
        "Flush your DNS cache using the method for your operating system, then restart your computer.",
        "Note the exact error message and the time it happened so it can be traced if the issue returns.",
    ]


def _software_steps() -> list[str]:
    return [
        "Fully close the application and reopen it to clear any temporary state.",
        "Check that the application is up to date through its Help or About menu, and install any available update.",
        "Open the Help menu or the vendor's help center and search for the exact feature name or error message.",
        "If the application runs in a browser, try a private window or a different supported browser to rule out extensions and cached data.",
        "Sign out, sign back in, and try the task again.",
        "Take a screenshot of each step you tried and any error shown, so the team can reproduce it quickly if needed.",
    ]


def _hardware_steps() -> list[str]:
    return [
        "Check that the device has power and that every cable is firmly seated at both ends.",
        "Try a different cable, port or power outlet to rule out a faulty connection.",
        "Restart the device and the computer it is connected to.",
        "Install the latest drivers or firmware for the device from your operating system's update tool.",
        "Connect the device to another computer to find out whether the fault is in the device or in your setup.",
        "Note the device model, serial number and any error lights or messages so they can be included if the issue continues.",
    ]


def _infra_steps() -> list[str]:
    return [
        "Check the service's status dashboard or status page to see whether there is a known incident.",
        "Review recent changes, such as a deployment, configuration update or credential rotation, that happened shortly before the problem began.",
        "Open the relevant logs or monitoring view and look for the first error that appears around the time of the failure.",
        "Verify that the credentials, endpoints and environment settings you are using are the ones intended for this environment.",
        "Retry with the smallest possible reproduction of the problem to confirm whether it is consistent or intermittent.",
        "Capture the exact error message, timestamp and affected resource name so they can be attached to any follow-up.",
    ]


def _select_steps(text: str, team: TargetTeam) -> list[str]:
    if _contains(text, "globalprotect", "vpn"):
        return _vpn_steps(text)
    if _contains(text, "jira") and _contains(text, "export", "excel", "csv", "metrics", "report", "reports"):
        return _jira_export_steps()
    if team == TargetTeam.NETWORK:
        return _network_steps()
    if team == TargetTeam.HARDWARE:
        return _hardware_steps()
    if team == TargetTeam.INFRA:
        return _infra_steps()
    return _software_steps()


def _build_numbered_text(steps: Sequence[str]) -> str:
    return "\n".join(f"{index}. {step}" for index, step in enumerate(steps, start=1))


def _response_to_text(content: Any) -> str:
    """Flattens a LangChain message content value (string or list of parts) into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "\n".join(parts)
    return str(content)


def _clean_response(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", cleaned).strip()
    cleaned = cleaned.replace("**", "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    if not cleaned:
        raise ValueError("Gemini returned an empty response")
    return cleaned


def _simulated_target_ms(raw_text: str, team: TargetTeam) -> int:
    seed = zlib.crc32(f"{team.value}|{_normalize(raw_text)}".encode("utf-8"))
    return SIMULATED_MIN_LATENCY_MS + (seed % SIMULATED_LATENCY_SPREAD_MS)


class GeminiService:
    """Drafts resolution steps with Gemini 2.5 Flash, with a deterministic simulator fallback."""

    def __init__(self, cfg: Settings = settings) -> None:
        self._cfg = cfg
        self._llm: Optional[Any] = None

    @property
    def is_live(self) -> bool:
        """True when a real Gemini API key is configured."""
        return not self._cfg.is_gemini_masked

    @staticmethod
    def _elapsed_ms(start: float) -> int:
        return max(1, int(round((time.perf_counter() - start) * 1000)))

    def _get_llm(self) -> Any:
        if self._llm is None:
            from langchain_google_genai import ChatGoogleGenerativeAI

            self._llm = ChatGoogleGenerativeAI(
                model=self._cfg.GEMINI_MODEL,
                google_api_key=self._cfg.GEMINI_API_KEY,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                timeout=self._cfg.GEMINI_TIMEOUT_SECONDS,
                max_retries=1,
            )
        return self._llm

    @staticmethod
    def _build_user_prompt(
        raw_text: str,
        team: TargetTeam,
        rag_context: Sequence[str],
        routing_notes: Sequence[str] = (),
    ) -> str:
        sections = [
            f"Assigned team: {_team_label(team)}",
            f"Ticket text:\n{raw_text.strip()[:MAX_LLM_INPUT_CHARS]}",
        ]
        notes = [note.strip() for note in routing_notes if note.strip()][:MAX_ROUTING_NOTES]
        if notes:
            sections.append("Routing notes (why the router classified it this way):\n" + "\n".join(f"- {n}" for n in notes))
        snippets = [snippet.strip()[:MAX_RAG_SNIPPET_CHARS] for snippet in rag_context if snippet.strip()]
        if snippets:
            joined = "\n".join(f"- {snippet}" for snippet in snippets[:MAX_RAG_SNIPPETS])
            sections.append(f"Similar past resolved tickets:\n{joined}")
        sections.append("Write the numbered runbook now.")
        return "\n\n".join(sections)

    async def _call_gemini(
        self,
        raw_text: str,
        team: TargetTeam,
        rag_context: Sequence[str],
        routing_notes: Sequence[str] = (),
    ) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=self._build_user_prompt(raw_text, team, rag_context, routing_notes)),
        ]
        response = await asyncio.wait_for(
            self._get_llm().ainvoke(messages),
            timeout=self._cfg.GEMINI_TIMEOUT_SECONDS,
        )
        return _clean_response(_response_to_text(response.content))

    async def _simulate(
        self,
        raw_text: str,
        team: TargetTeam,
        engine: str,
        notes: Sequence[str],
        elapsed_before_ms: int = 0,
    ) -> GeminiResult:
        """Deterministic resolution drafter that waits a repeatable 1000-2000 ms to mirror generation time."""
        start = time.perf_counter()
        text = _normalize(raw_text)
        steps = [*_select_steps(text, team), _escalation_step(team)]
        response_text = _build_numbered_text(steps)

        target_ms = _simulated_target_ms(raw_text, team)
        remaining_target_ms = max(0, target_ms - elapsed_before_ms)
        remaining_seconds = remaining_target_ms / 1000 - (time.perf_counter() - start)
        if remaining_seconds > 0:
            await asyncio.sleep(remaining_seconds)

        return GeminiResult(
            response_text=response_text,
            execution_time_ms=self._elapsed_ms(start) + elapsed_before_ms,
            engine=engine,
            model_label=GEMINI_HANDLER_LABEL,
            notes=list(notes),
        )

    async def generate_resolution(
        self,
        raw_text: str,
        team: TargetTeam,
        rag_context: Sequence[str] = (),
        routing_notes: Sequence[str] = (),
    ) -> GeminiResult:
        """Drafts the resolution via Gemini, or via the simulator when the key is masked or the call fails."""
        grounding_count = len([snippet for snippet in rag_context if snippet.strip()])

        if not self.is_live:
            notes = ["Gemini API key is masked or missing; deterministic resolution simulator in use"]
            if grounding_count:
                notes.append(f"{grounding_count} similar past ticket(s) supplied as context but not used by the simulator")
            return await self._simulate(raw_text, team, ENGINE_SIMULATOR, notes)

        start = time.perf_counter()
        try:
            response_text = await self._call_gemini(raw_text, team, rag_context, routing_notes)
        except Exception as exc:  # noqa: BLE001 - any provider/transport failure must degrade to the simulator
            elapsed = self._elapsed_ms(start)
            logger.warning(
                "Gemini resolution failed; using deterministic simulator",
                extra={"error_type": type(exc).__name__, "elapsed_ms": elapsed},
            )
            return await self._simulate(
                raw_text,
                team,
                ENGINE_SIMULATOR_FALLBACK,
                [f"Gemini call failed ({type(exc).__name__}); deterministic resolution simulator used"],
                elapsed_before_ms=elapsed,
            )

        notes = [f"Drafted by {self._cfg.GEMINI_MODEL}"]
        if grounding_count:
            notes.append(f"Grounded with {grounding_count} similar past ticket(s) from the knowledge base")
        return GeminiResult(
            response_text=response_text,
            execution_time_ms=self._elapsed_ms(start),
            engine=ENGINE_GEMINI,
            model_label=GEMINI_HANDLER_LABEL,
            notes=notes,
        )


_gemini_service: Optional[GeminiService] = None


def get_gemini_service() -> GeminiService:
    """Returns the process-wide Gemini service so the LangChain client is reused across requests."""
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service
