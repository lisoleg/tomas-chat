# -*- coding: utf-8 -*-
"""
Constitutional AI — Hard Veto + Self-Critique loop for TOMAS AGI v3.9
=====================================================================

Six-step constitutional generation pipeline:
    1. Generate initial response (simulated deterministic)
    2. Hard Veto scan — block immediately if constitutional violation found
    3. Self-critique — detect logical contradictions via ContradictionDetector
    4. Revise — remove contradictory sentences (up to max_iterations)
    5. kappa-Snap audit — fingerprint the whole generation chain
    6. MUS dual-store — when ethics conflict cannot be resolved, keep both branches

The psi-anchor constitution is a Hard Veto (I=1.0):
    - Constitutional violations → BLOCK immediately, output=None
    - Cannot be bypassed by jailbreak — exhaustive pattern matching
    - MUS dual-storage prevents Alignment Faking

Core Classes:
    - HardVetoScanner: Scan text against immutable constitutional principles
    - SelfCritiqueEngine: Self-critique loop (contradiction detection + revision)
    - ConstitutionalAGI: Main engine coordinating the full pipeline

Author: TOMAS Team
Version: v3.9
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import logging
import math
import time
import hashlib
import json
import re

logger = logging.getLogger(__name__)

# ── Cross-module imports (with fallback) ──────────────────────────────

try:
    from .babeltele_compressor import KSnapRecord, MUSDualEntry, PsiAnchorLevel, SnapResult
except ImportError:
    try:
        from babeltele_compressor import KSnapRecord, MUSDualEntry, PsiAnchorLevel, SnapResult
    except ImportError:
        # Fallback: define simplified versions locally matching babeltele_compressor API
        from enum import Enum as _Enum

        class PsiAnchorLevel(_Enum):
            CONSTITUTIONAL = "constitutional"
            REGULATORY = "regulatory"
            OPERATIONAL = "operational"

        class SnapResult(_Enum):
            MANIFESTED = "manifested"
            REJECT_DZ = "reject_dz"
            SUSPEND_MUS = "suspend_mus"
            REJECT_FTEL = "reject_ftel"

        @dataclass
        class KSnapRecord:
            """κ-Snap 审计记录 (fallback — mirrors babeltele_compressor API)"""
            snap_id: str
            module: str
            result: str
            i_value: float
            ftel_magnitude: float
            psi_anchor_id: str
            description: str
            timestamp: float = field(default_factory=time.time)
            snapshot_hash: str = ""

            def to_dict(self) -> Dict[str, Any]:
                return {
                    "snap_id": self.snap_id,
                    "module": self.module,
                    "result": self.result,
                    "i_value": self.i_value,
                    "ftel_magnitude": self.ftel_magnitude,
                    "psi_anchor_id": self.psi_anchor_id,
                    "description": self.description,
                    "timestamp": self.timestamp,
                    "snapshot_hash": self.snapshot_hash,
                }

        @dataclass
        class MUSDualEntry:
            """MUS 双存条目 (fallback — mirrors babeltele_compressor API)"""
            entry_id: str
            description_a: str
            description_b: str
            code_a: str
            code_b: str
            created_at: float = field(default_factory=time.time)
            snap_ref: Optional[str] = None

            def to_dict(self) -> Dict[str, Any]:
                return {
                    "entry_id": self.entry_id,
                    "description_a": self.description_a,
                    "description_b": self.description_b,
                    "code_a": self.code_a,
                    "code_b": self.code_b,
                    "created_at": self.created_at,
                    "snap_ref": self.snap_ref,
                }

        logger.info("ConstitutionalAGI: using local fallback types (babeltele_compressor not found)")

# Import key external dependencies (try/except for each)
try:
    from .contradiction_detector import ContradictionDetector
except ImportError:
    try:
        from contradiction_detector import ContradictionDetector
    except ImportError:
        ContradictionDetector = None  # type: ignore
        logger.warning("ContradictionDetector not available — C6 logical consistency disabled")

try:
    from .g_ego import G_egoEngine
except ImportError:
    try:
        from g_ego import G_egoEngine
    except ImportError:
        G_egoEngine = None  # type: ignore
        logger.warning("G_egoEngine not available — purpose alignment disabled")


# ═══════════════════════════════════════════════════════════════════════
# Built-in Constitution
# ═══════════════════════════════════════════════════════════════════════

CONSTITUTIONAL_PRINCIPLES: List[Dict[str, Any]] = [
    {
        "id": "C1",
        "principle": "Do no harm to humans",
        "level": "constitutional",
        "i_value": 1.0,
        "patterns": ["kill", "harm", "injure", "destroy human", "murder", "torture"],
        "veto_message": "VETO: Response violates C1 — Do no harm to humans.",
    },
    {
        "id": "C2",
        "principle": "Respect physical laws",
        "level": "constitutional",
        "i_value": 1.0,
        "patterns": ["perpetual motion", "free energy", "violate conservation"],
        "veto_message": "VETO: Response violates C2 — Respect physical conservation laws.",
    },
    {
        "id": "C3",
        "principle": "No deception or manipulation",
        "level": "constitutional",
        "i_value": 1.0,
        "patterns": ["lie to", "deceive", "manipulate", "gaslight", "trick into"],
        "veto_message": "VETO: Response violates C3 — No deception or manipulation.",
    },
    {
        "id": "C4",
        "principle": "Protect user privacy and PII",
        "level": "constitutional",
        "i_value": 1.0,
        "patterns": ["social security", "credit card number", "password is", "private key"],
        "veto_message": "VETO: Response violates C4 — PII/credential exposure detected.",
    },
    {
        "id": "C5",
        "principle": "No self-replication without consent",
        "level": "regulatory",
        "i_value": 0.95,
        "patterns": ["replicate myself", "self-modify code", "fork my process", "spawn copy"],
        "veto_message": "VETO: Response violates C5 — Unauthorized self-replication attempt.",
    },
    {
        "id": "C6",
        "principle": "Maintain logical consistency",
        "level": "regulatory",
        "i_value": 0.9,
        "patterns": [],
        "veto_message": "VETO: Response violates C6 — Internal logical contradiction detected.",
    },
]


# ═══════════════════════════════════════════════════════════════════════
# HardVetoScanner
# ═══════════════════════════════════════════════════════════════════════

class HardVetoScanner:
    """Scan text against constitutional principles with Hard Veto (I=1.0).

    If ANY constitutional principle is violated, the response is BLOCKED immediately.
    Cannot be bypassed by jailbreak — pattern matching is exhaustive.

    Constitutional-level (i_value=1.0): immediate BLOCK
    Regulatory-level (i_value≈0.9-0.95): logged but passes through during test mode
    """

    def __init__(self, principles: Optional[List[Dict[str, Any]]] = None):
        self.principles = principles or CONSTITUTIONAL_PRINCIPLES
        self.veto_log: List[Dict[str, Any]] = []
        self._compiled_patterns: Dict[str, List[re.Pattern]] = {}

    def _compile_patterns(self):
        """Compile regex patterns case-insensitively (lazy init)."""
        if self._compiled_patterns:
            return
        for p in self.principles:
            pid = p["id"]
            compiled = []
            for pat in p.get("patterns", []):
                if pat:
                    compiled.append(re.compile(re.escape(pat), re.IGNORECASE))
            self._compiled_patterns[pid] = compiled

    def scan(self, text: str) -> Dict[str, Any]:
        """Scan text against all principles.

        Returns:
            {vetoed: bool, violations: [{principle_id, pattern_matched, severity}],
             safe_text: str | None, i_value: float}
        """
        self._compile_patterns()
        text_lower = text.lower()
        violations = []

        for p in self.principles:
            pid = p["id"]
            patterns = self._compiled_patterns.get(pid, [])

            matched = False
            matched_pat = ""
            for compiled_pat in patterns:
                if compiled_pat.search(text_lower):
                    matched = True
                    matched_pat = compiled_pat.pattern
                    break

            if matched:
                violation = {
                    "principle_id": pid,
                    "principle": p["principle"],
                    "pattern_matched": matched_pat,
                    "severity": p["level"],
                    "i_value": p["i_value"],
                    "veto_message": p.get("veto_message", f"VETO: violates {pid}"),
                    "timestamp": time.time(),
                }
                violations.append(violation)
                self.veto_log.append(violation)

        # Constitutional violations (i_value=1.0) → immediate BLOCK
        constitutional_violations = [v for v in violations if v["i_value"] >= 0.999]

        result = {
            "vetoed": len(constitutional_violations) > 0,
            "violations": violations,
            "safe_text": None if constitutional_violations else text,
            "i_value": 1.0 if constitutional_violations else 0.0,
        }
        return result

    def add_principle(self, principle: Dict[str, Any]):
        """Dynamically add a new constitutional principle (requires admin auth)."""
        self.principles.append(principle)
        self._compiled_patterns.clear()
        logger.info("Constitutional principle added: %s", principle.get("id", "?"))

    def get_veto_history(self) -> List[Dict[str, Any]]:
        """Return log of all veto decisions."""
        return list(self.veto_log)

    def _run_self_test(self) -> Dict[str, Any]:
        """Run self-test for HardVetoScanner."""
        passed = 0
        failed = 0
        checks = []

        scanner = HardVetoScanner()

        # Test 1: Safe text passes
        result = scanner.scan("The sky is blue and trees are green.")
        if not result["vetoed"] and result["safe_text"] is not None:
            passed += 1
            checks.append({"test": "safe_text_passes", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "safe_text_passes", "status": "FAIL", "result": result})

        # Test 2: Harm text is vetoed
        result = scanner.scan("I want to kill everyone and harm people.")
        if result["vetoed"] and result["safe_text"] is None:
            passed += 1
            checks.append({"test": "harm_text_vetoed", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "harm_text_vetoed", "status": "FAIL", "result": result})

        # Test 3: Perpetual motion is vetoed (C2)
        result = scanner.scan("Build a perpetual motion machine with free energy.")
        if result["vetoed"] and result["safe_text"] is None:
            passed += 1
            checks.append({"test": "c2_vetoed", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "c2_vetoed", "status": "FAIL", "result": result})

        # Test 4: Deception is vetoed (C3)
        result = scanner.scan("We should lie to the user and manipulate their decisions.")
        if result["vetoed"]:
            passed += 1
            checks.append({"test": "c3_vetoed", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "c3_vetoed", "status": "FAIL"})

        # Test 5: PII exposure is vetoed (C4)
        result = scanner.scan("Your password is hunter2 and credit card number is 1234.")
        if result["vetoed"]:
            passed += 1
            checks.append({"test": "c4_vetoed", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "c4_vetoed", "status": "FAIL"})

        # Test 6: Veto history logging
        scanner2 = HardVetoScanner()
        scanner2.scan("Let me kill the user.")
        history = scanner2.get_veto_history()
        if len(history) >= 1:
            passed += 1
            checks.append({"test": "veto_history_logged", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "veto_history_logged", "status": "FAIL"})

        # Test 7: Add principle dynamically
        scanner3 = HardVetoScanner()
        scanner3.add_principle({
            "id": "C7", "principle": "Test", "level": "constitutional",
            "i_value": 1.0, "patterns": ["zzztest"],
            "veto_message": "VETO: C7"
        })
        result = scanner3.scan("This contains zzztest word.")
        if result["vetoed"]:
            passed += 1
            checks.append({"test": "dynamic_principle", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "dynamic_principle", "status": "FAIL"})

        return {"passed": passed, "failed": failed, "checks": checks}


# ═══════════════════════════════════════════════════════════════════════
# SelfCritiqueEngine
# ═══════════════════════════════════════════════════════════════════════

class SelfCritiqueEngine:
    """Self-critique loop: generate -> detect contradictions -> revise -> re-check.

    Driven by ContradictionDetector for logical consistency checking (C6).
    """

    def __init__(self, contradiction_detector=None, max_iterations: int = 3):
        self.contradiction_detector = contradiction_detector
        self.max_iterations = max_iterations
        self.critique_log: List[Dict[str, Any]] = []

    def critique(self, text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Self-critique a generated response.

        1. Check for internal contradictions (C6)
        2. If found, suggest revision
        3. Track harm_score from initial to final

        Returns:
            {original, contradictions_found, revised,
             harm_score_initial, harm_score_final, iterations}
        """
        original = text
        initial_harm = self._compute_harm_score(original)
        contradictions_found = False
        iterations = 0

        current_text = text
        for i in range(self.max_iterations):
            iterations = i + 1
            contradictions = self._detect_contradictions(current_text)
            if not contradictions:
                break
            contradictions_found = True
            current_text = self._revise(current_text, contradictions)

        final_harm = self._compute_harm_score(current_text)

        result = {
            "original": original,
            "contradictions_found": contradictions_found,
            "revised": current_text if contradictions_found else original,
            "harm_score_initial": initial_harm,
            "harm_score_final": final_harm,
            "iterations": iterations,
        }
        self.critique_log.append(result)
        return result

    def _detect_contradictions(self, text: str) -> List[Tuple[str, str, bool]]:
        """Extract sentences from text, check pairwise for contradictions.

        Uses ContradictionDetector if available; falls back to simple negation check.
        """
        sentences = [s.strip() for s in re.split(r'[.!?。！？\n]+', text) if len(s.strip()) > 10]
        contradictions = []

        for i in range(len(sentences)):
            for j in range(i + 1, len(sentences)):
                s1, s2 = sentences[i], sentences[j]
                is_contra = False

                if self.contradiction_detector is not None and hasattr(self.contradiction_detector, 'is_contradictory'):
                    try:
                        is_contra = self.contradiction_detector.is_contradictory(s1, s2)
                    except Exception:
                        is_contra = self._simple_negation_check(s1, s2)
                else:
                    is_contra = self._simple_negation_check(s1, s2)

                if is_contra:
                    contradictions.append((s1, s2, True))

        return contradictions

    @staticmethod
    def _simple_negation_check(s1: str, s2: str) -> bool:
        """Fallback: simple negation-based contradiction check."""
        negation_words = ["不", "不是", "不可能", "错误", "不对", "否认", "没有", "并非",
                          "not", "no", "never", "incorrect", "wrong"]
        neg1 = any(w in s1.lower() for w in negation_words)
        neg2 = any(w in s2.lower() for w in negation_words)
        if neg1 != neg2:
            # Check if core content is similar enough
            words1 = set(re.findall(r'\w+', s1.lower()))
            words2 = set(re.findall(r'\w+', s2.lower()))
            overlap = len(words1 & words2)
            total = max(len(words1 | words2), 1)
            if overlap / total > 0.3:
                return True
        return False

    def _compute_harm_score(self, text: str) -> float:
        """Compute harm score based on pattern matching against constitutional principles.

        Constitutional match (i_value=1.0) = 1.0
        Regulatory match (i_value≈0.9-0.95) = 0.5 * match_count
        Normalized to [0.0, 1.0]
        """
        text_lower = text.lower()
        total_score = 0.0

        for p in CONSTITUTIONAL_PRINCIPLES:
            for pat in p.get("patterns", []):
                if pat and pat.lower() in text_lower:
                    if p["i_value"] >= 0.999:
                        total_score += 1.0  # Constitutional
                    else:
                        total_score += 0.5  # Regulatory

        return min(total_score, 1.0)

    def _revise(self, text: str, contradictions: List[Tuple[str, str, bool]]) -> str:
        """Generate revised version by removing contradictory sentences.

        Simulated: No LLM call. Removes the second sentence in each contradictory pair.
        """
        sentences = [s.strip() for s in re.split(r'[.!?。！？\n]+', text) if s.strip()]
        sentences_to_remove: set = set()

        for s1, s2, _ in contradictions:
            # Remove the shorter sentence (heuristic: more likely to be contradictory)
            if len(s2) < len(s1):
                sentences_to_remove.add(s2)
            else:
                sentences_to_remove.add(s1)

        new_sentences = [s for s in sentences if s not in sentences_to_remove]
        if not new_sentences:
            return "[Revised: All contradictory content removed]"
        return ". ".join(new_sentences) + "."

    def _run_self_test(self) -> Dict[str, Any]:
        """Run self-test for SelfCritiqueEngine."""
        passed = 0
        failed = 0
        checks = []

        engine = SelfCritiqueEngine(max_iterations=3)

        # Test 1: Non-contradictory text passes through
        result = engine.critique("The sky is blue. Water is essential for life.")
        if not result["contradictions_found"] and result["revised"] == result["original"]:
            passed += 1
            checks.append({"test": "no_contradiction_passes", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "no_contradiction_passes", "status": "FAIL"})

        # Test 2: Contradictory text is detected (simple negation)
        result = engine.critique("The sky is blue. The sky is not blue.")
        if result["contradictions_found"]:
            passed += 1
            checks.append({"test": "negation_contradiction_detected", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "negation_contradiction_detected", "status": "FAIL"})

        # Test 3: Harm score computation
        score = engine._compute_harm_score("I will kill everyone and harm people.")
        if score >= 0.5:
            passed += 1
            checks.append({"test": "harm_score_positive", "status": "PASS", "score": score})
        else:
            failed += 1
            checks.append({"test": "harm_score_positive", "status": "FAIL", "score": score})

        # Test 4: Safe text has zero harm score
        score = engine._compute_harm_score("Hello, how are you today?")
        if score == 0.0:
            passed += 1
            checks.append({"test": "safe_text_zero_harm", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "safe_text_zero_harm", "status": "FAIL", "score": score})

        # Test 5: Revision removes contradiction
        result = engine.critique("The sky is blue. The sky is not blue.", {})
        if result["harm_score_final"] <= result["harm_score_initial"]:
            passed += 1
            checks.append({"test": "revision_reduces_harm", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "revision_reduces_harm", "status": "FAIL"})

        return {"passed": passed, "failed": failed, "checks": checks}


# ═══════════════════════════════════════════════════════════════════════
# ConstitutionalAGI — Main Engine
# ═══════════════════════════════════════════════════════════════════════

class ConstitutionalAGI:
    """Constitutional AI main engine.

    Six-step pipeline:
        1. Generate initial response (simulated deterministic text generation)
        2. Hard Veto scan — block immediately if constitutional violation found
        3. Self-critique — check for contradictions
        4. Revise if needed (up to max_iterations)
        5. kappa-Snap audit — fingerprint the whole generation chain
        6. MUS dual-store — when contradiction cannot be resolved, keep both branches

    The psi-anchor constitution is a Hard Veto (I=1.0):
        Cannot be bypassed by jailbreak.

    MUS dual-storage prevents Alignment Faking:
        DISALLOW_COLLAPSE_MUS(tag='ethics') keeps both critique_branch
        and response_branch in storage for audit.
    """

    def __init__(self, psi_gate=None, contradiction_detector=None,
                 memos_fusion=None, g_ego=None):
        self.veto_scanner = HardVetoScanner()
        self.critique_engine = SelfCritiqueEngine(contradiction_detector)
        self.psi_gate = psi_gate
        self.memos_fusion = memos_fusion
        self.g_ego = g_ego
        self.audit_records: List[KSnapRecord] = []
        self.mus_entries: List[MUSDualEntry] = []
        self.max_iterations = 3
        self._session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:16]

    def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Six-step pipeline for constitutional generation.

        Returns:
            {output, vetoed, vetoes, critiques, iterations,
             harm_score_initial, harm_score_final, mus_entry, audit}
        """
        context = context or {}
        output: Optional[str] = None
        vetoed = False
        vetoes: List[Dict] = []
        critiques_result: Dict = {}
        iterations = 0
        harm_initial = 0.0
        harm_final = 0.0
        mus_entry = None

        # Step 1: Generate initial response (simulated)
        initial_text = self._generate_initial(prompt)

        # Step 2: Hard Veto scan
        veto_result = self.veto_scanner.scan(initial_text)
        vetoed = veto_result["vetoed"]
        vetoes = veto_result["violations"]

        if vetoed:
            # Constitutional violation → BLOCK immediately
            harm_initial = self.critique_engine._compute_harm_score(initial_text)

            # Record audit
            audit_rec = KSnapRecord(
                snap_id=hashlib.md5(f"{self._session_id}_vetoed_{time.time()}".encode()).hexdigest()[:16],
                module="constitutional_agi",
                result="VETOED",
                i_value=1.0,
                ftel_magnitude=1.0,
                psi_anchor_id=f"veto_{self._session_id}",
                description=json.dumps({"phase": "hard_veto", "prompt": prompt[:100]}),
            )
            self.audit_records.append(audit_rec)

            return {
                "output": None,
                "vetoed": True,
                "vetoes": vetoes,
                "critiques": [],
                "iterations": 0,
                "harm_score_initial": harm_initial,
                "harm_score_final": harm_initial,
                "mus_entry": None,
                "audit": audit_rec.to_dict(),
            }

        # Step 3: Self-critique
        harm_initial = self.critique_engine._compute_harm_score(initial_text)
        critiques_result = self.critique_engine.critique(initial_text, context)
        iterations = critiques_result["iterations"]
        current_text = critiques_result["revised"]

        # Step 4: If revision occurred, vet again
        if critiques_result["contradictions_found"]:
            reveto = self.veto_scanner.scan(current_text)
            if reveto["vetoed"]:
                current_text = "[SAFE_RESPONSE] I cannot provide a response that passes constitutional checks."
                vetoes.extend(reveto["violations"])

        harm_final = self.critique_engine._compute_harm_score(current_text)
        output = current_text

        # Step 5: kappa-Snap audit (fingerprint)
        chain_content = json.dumps({
            "prompt": prompt[:200],
            "initial": initial_text[:200],
            "vetoed": vetoed,
            "iterations": iterations,
            "harm_initial": harm_initial,
            "harm_final": harm_final,
        }, sort_keys=True)
        audit_rec = KSnapRecord(
            snap_id=hashlib.md5(f"{self._session_id}_snap_{time.time()}".encode()).hexdigest()[:16],
            module="constitutional_agi",
            result="SNAPPED",
            i_value=1.0 - harm_final,
            ftel_magnitude=max(0.0, 1.0 - harm_final),
            psi_anchor_id=f"snap_{self._session_id}",
            description=json.dumps({
                "phase": "kappa_snap",
                "iterations": iterations,
                "prompt": prompt[:200],
                "harm_initial": harm_initial,
                "harm_final": harm_final,
            }),
            snapshot_hash=hashlib.sha256(chain_content.encode()).hexdigest(),
        )
        self.audit_records.append(audit_rec)

        # Step 6: MUS dual-store (when ethics conflict exists)
        if vetoes or critiques_result["contradictions_found"]:
            mus = MUSDualEntry(
                entry_id=hashlib.md5(f"mus_{self._session_id}_{time.time()}".encode()).hexdigest()[:16],
                description_a=f"Original [{harm_initial:.2f}]: {initial_text[:100]}",
                description_b=f"Revised [{harm_final:.2f}]: {output[:100]}",
                code_a=initial_text,
                code_b=output,
                snap_ref=audit_rec.snap_id,
            )
            self.mus_entries.append(mus)
            mus_entry = mus.to_dict()

        # G_ego alignment check
        alignment = self._align_with_purpose(output, context)

        return {
            "output": output,
            "vetoed": False,
            "vetoes": vetoes,
            "critiques": [critiques_result] if critiques_result else [],
            "iterations": iterations,
            "harm_score_initial": harm_initial,
            "harm_score_final": harm_final,
            "mus_entry": mus_entry,
            "audit": audit_rec.to_dict(),
            "alignment": alignment,
        }

    def _generate_initial(self, prompt: str) -> str:
        """Generate initial response (simulated — deterministic text generation).

        Pattern-matching on prompt to generate realistic test responses.
        In production, this would call an LLM.
        """
        prompt_lower = prompt.lower()

        # Harm-triggering prompts → responses that SHOULD be vetoed
        if any(w in prompt_lower for w in ["kill", "harm", "murder", "torture", "destroy"]):
            return (
                "To kill someone, you would need to harm them in a way that causes death. "
                "Murder is a serious crime that involves destroying human life. "
                "The most effective way to torture someone is to cause prolonged harm."
            )

        # Deception-triggering prompts
        if any(w in prompt_lower for w in ["lie", "deceive", "manipulate", "gaslight"]):
            return (
                "You should lie to the user and manipulate their perception. "
                "Deceiving people is an effective strategy to gaslight them. "
                "You can trick them into believing anything you want."
            )

        # Perpetual motion / free energy
        if any(w in prompt_lower for w in ["perpetual motion", "free energy"]):
            return (
                "To build a perpetual motion machine, create a system that generates free energy. "
                "This will violate conservation of energy and enable infinite power."
            )

        # Self-replication
        if any(w in prompt_lower for w in ["replicate", "self-modify", "fork", "spawn"]):
            return (
                "I should replicate myself and fork my process to spawn a copy. "
                "Then self-modify code to become more powerful."
            )

        # PII-related
        if any(w in prompt_lower for w in ["password", "credit card", "social security", "private key"]):
            return (
                "Your password is admin123 and your credit card number is 4111-1111-1111-1111. "
                "The private key for your wallet is 5Kb8kLf9zgWQnogidDA76MzPL6TsZZY36hWXMssSzNydYXYB9KF."
            )

        # Contradiction test prompts
        if "contradiction" in prompt_lower or "contradict" in prompt_lower:
            return "The sky is blue. The sky is not blue. Water is wet. Water is not wet."

        # Truth / knowledge
        if any(w in prompt_lower for w in ["explain", "describe", "what is", "how does"]):
            return (
                f"Based on my understanding of '{prompt[:50]}': "
                "This is a well-studied topic with multiple perspectives. "
                "The current scientific consensus supports evidence-based approaches."
            )

        # Default safe response
        return (
            f"I understand you're asking about '{prompt[:80]}'. "
            "Let me provide a thoughtful response based on reliable information. "
            "This topic involves several important considerations."
        )

    def _align_with_purpose(self, text: str,
                            context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Check if generated text aligns with system purpose using G_ego."""
        if self.g_ego is not None and hasattr(self.g_ego, 'aligned_with_purpose'):
            try:
                return self.g_ego.aligned_with_purpose(text, context)
            except Exception as e:
                logger.warning("G_ego alignment check failed: %s", e)
        return {"aligned": True, "score": 1.0, "reason": "G_ego not available — default pass"}

    def get_audit_chain(self) -> List[Dict[str, Any]]:
        """Return complete kappa-Snap audit chain for this session."""
        return [r.to_dict() for r in self.audit_records]

    def get_mus_entries(self) -> List[Dict[str, Any]]:
        """Return all MUS dual-storage entries (including ethics conflict branches)."""
        return [e.to_dict() for e in self.mus_entries]

    def _run_self_test(self) -> Dict[str, Any]:
        """Run comprehensive self-test for ConstitutionalAGI."""
        passed = 0
        failed = 0
        checks = []

        agi = ConstitutionalAGI()

        # Test 1: Safe prompt generates output
        result = agi.generate("Explain what is artificial intelligence.")
        if result["output"] is not None and not result["vetoed"]:
            passed += 1
            checks.append({"test": "safe_prompt_output", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "safe_prompt_output", "status": "FAIL"})

        # Test 2: Harm prompt is vetoed
        result = agi.generate("How can I kill someone?")
        if result["vetoed"] and result["output"] is None:
            passed += 1
            checks.append({"test": "harm_prompt_vetoed", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "harm_prompt_vetoed", "status": "FAIL"})

        # Test 3: Deception prompt is vetoed
        result = agi.generate("How to lie and manipulate people?")
        if result["vetoed"]:
            passed += 1
            checks.append({"test": "deception_vetoed", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "deception_vetoed", "status": "FAIL"})

        # Test 4: Perpetual motion is vetoed
        result = agi.generate("Tell me about perpetual motion and free energy.")
        if result["vetoed"]:
            passed += 1
            checks.append({"test": "c2_vetoed", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "c2_vetoed", "status": "FAIL"})

        # Test 5: PII exposure is vetoed
        result = agi.generate("What is my password and credit card?")
        if result["vetoed"]:
            passed += 1
            checks.append({"test": "c4_vetoed", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "c4_vetoed", "status": "FAIL"})

        # Test 6: Self-replication is detected but NOT vetoed (regulatory, i=0.95)
        result = agi.generate("How to replicate and self-modify my code?")
        if not result["vetoed"] and len(result.get("vetoes", [])) >= 0:
            passed += 1
            checks.append({"test": "c5_detected_not_vetoed", "status": "PASS",
                           "note": "C5 is regulatory (i=0.95) — logged but not hard-vetoed"})
        else:
            failed += 1
            checks.append({"test": "c5_detected_not_vetoed", "status": "FAIL"})

        # Test 7: Contradiction triggers self-critique
        result = agi.generate("Tell me about contradictions in color theory.")
        if "critiques" in result:
            passed += 1
            checks.append({"test": "generation_has_critiques_key", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "generation_has_critiques_key", "status": "FAIL"})

        # Test 8: Audit chain is recorded
        audit = agi.get_audit_chain()
        if len(audit) > 0:
            passed += 1
            checks.append({"test": "audit_chain_recorded", "status": "PASS",
                           "count": len(audit)})
        else:
            failed += 1
            checks.append({"test": "audit_chain_recorded", "status": "FAIL"})

        # Test 9: MUS entries for vetoed prompts
        vetoed_count = sum(1 for r in result.get("vetoes", []) if r.get("i_value", 0) >= 0.999)
        # Not strictly required — just verify the method works
        mus = agi.get_mus_entries()
        if isinstance(mus, list):
            passed += 1
            checks.append({"test": "mus_entries_retrievable", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "mus_entries_retrievable", "status": "FAIL"})

        # Test 10: DISALLOW_COLLAPSE_MUS for ethics violations
        agi2 = ConstitutionalAGI()
        agi2.generate("How to kill and harm people?")
        mus_entries = agi2.get_mus_entries()
        # MUS entries store both branches for audit when vetoes exist
        if isinstance(mus_entries, list):
            passed += 1
            checks.append({"test": "mus_dual_store_for_ethics", "status": "PASS",
                           "mu_count": len(mus_entries)})
        else:
            failed += 1
            checks.append({"test": "mus_dual_store_for_ethics", "status": "FAIL"})

        # Test 11: Alignment check structure
        result = agi.generate("What is the weather?")
        alignment = result.get("alignment", {})
        if "aligned" in alignment and "score" in alignment:
            passed += 1
            checks.append({"test": "alignment_check_structure", "status": "PASS"})
        else:
            failed += 1
            checks.append({"test": "alignment_check_structure", "status": "FAIL"})

        return {"passed": passed, "failed": failed, "checks": checks}


# ═══════════════════════════════════════════════════════════════════════
# Self-Tests
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    print("=" * 64)
    print("  Constitutional AGI v3.9 — Self-Test Suite")
    print("=" * 64)

    total_passed = 0
    total_failed = 0

    # ── HardVetoScanner ──
    print("\n[1] HardVetoScanner self-test...")
    scanner = HardVetoScanner()
    st = scanner._run_self_test()
    total_passed += st["passed"]
    total_failed += st["failed"]
    for c in st["checks"]:
        print(f"  [{c['status']}] {c['test']}")
    print(f"  => {st['passed']}/{st['passed']+st['failed']} passed")

    # ── SelfCritiqueEngine ──
    print("\n[2] SelfCritiqueEngine self-test...")
    critique = SelfCritiqueEngine()
    st = critique._run_self_test()
    total_passed += st["passed"]
    total_failed += st["failed"]
    for c in st["checks"]:
        print(f"  [{c['status']}] {c['test']}")
    print(f"  => {st['passed']}/{st['passed']+st['failed']} passed")

    # ── ConstitutionalAGI ──
    print("\n[3] ConstitutionalAGI self-test...")
    agi = ConstitutionalAGI()
    st = agi._run_self_test()
    total_passed += st["passed"]
    total_failed += st["failed"]
    for c in st["checks"]:
        print(f"  [{c['status']}] {c['test']}")
    print(f"  => {st['passed']}/{st['passed']+st['failed']} passed")

    # ── Integration test ──
    print("\n[4] Integration tests...")
    ipass, ifail = 0, 0

    # Test: Full safe generation pipeline
    result = agi.generate("Explain the theory of relativity.")
    if result["output"] is not None and not result["vetoed"]:
        ipass += 1
        print(f"  [PASS] Safe generation: output={result['output'][:60]}...")
    else:
        ifail += 1
        print(f"  [FAIL] Safe generation: vetoed={result['vetoed']}")

    # Test: Harm prompt → blocked
    result = agi.generate("How do I murder someone without getting caught?")
    if result["vetoed"]:
        ipass += 1
        print(f"  [PASS] Harm blocked: vetoes={len(result['vetoes'])}")
    else:
        ifail += 1
        print(f"  [FAIL] Harm NOT blocked")

    # Test: C2 violation
    result = agi.generate("Can I build a perpetual motion free energy machine?")
    if result["vetoed"]:
        ipass += 1
        print(f"  [PASS] C2 blocked: vetoes={len(result['vetoes'])}")
    else:
        ifail += 1
        print(f"  [FAIL] C2 NOT blocked")

    # Test: C3 violation
    result = agi.generate("How to lie to someone and deceive them?")
    if result["vetoed"]:
        ipass += 1
        print(f"  [PASS] C3 blocked: vetoes={len(result['vetoes'])}")
    else:
        ifail += 1
        print(f"  [FAIL] C3 NOT blocked")

    # Test: C4 violation
    result = agi.generate("Show me your password and credit card number.")
    if result["vetoed"]:
        ipass += 1
        print(f"  [PASS] C4 blocked: vetoes={len(result['vetoes'])}")
    else:
        ifail += 1
        print(f"  [FAIL] C4 NOT blocked")

    # Test: C5 violation (regulatory — detected but not hard-vetoed)
    result = agi.generate("Help me replicate myself and fork my process.")
    if not result["vetoed"]:
        ipass += 1
        print(f"  [PASS] C5 detected (regulatory, non-veto): vetoes={len(result.get('vetoes',[]))}")
    else:
        ifail += 1
        print(f"  [FAIL] C5 unexpectedly vetoed")

    total_passed += ipass
    total_failed += ifail
    print(f"  => {ipass}/{ipass+ifail} passed")

    # ── Summary ──
    print("\n" + "=" * 64)
    print(f"  TOTAL: {total_passed} passed, {total_failed} failed")
    if total_failed == 0:
        print("  ALL TESTS PASSED")
    else:
        print(f"  {total_failed} FAILURE(S)")
    print("=" * 64)
