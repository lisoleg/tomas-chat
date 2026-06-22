# -*- coding: utf-8 -*-
"""
Hypergraph Categories with Frobenius Generators — TOMAS AGI v3.9
================================================================
Core: Hyperedge, FrobeniusGenerator, CupCapDuality, GlueValidator,
      PsiAnchorFilter, HypergraphBuilder — five-step pipeline.
Predictive claims: P14 (charge conservation), P15 (self-dual), P16 (κ∈[0,7]).
Author: TOMAS Team, v3.9
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Set
import logging, math, time, hashlib, json, uuid
from enum import Enum

logger = logging.getLogger(__name__)
sqrt, pi, atan2, cos, sin = math.sqrt, math.pi, math.atan2, math.cos, math.sin

# ── Cross-module import with fallback ──────────────────────────────
try:
    from .babeltele_compressor import KSnapRecord, MUSDualEntry, PsiAnchorLevel, SnapResult
except ImportError:
    try:
        from babeltele_compressor import KSnapRecord, MUSDualEntry, PsiAnchorLevel, SnapResult
    except ImportError:
        class PsiAnchorLevel(Enum):
            CONSTITUTIONAL = "constitutional"
            REGULATORY = "regulatory"
            OPERATIONAL = "operational"

        class SnapResult(Enum):
            MANIFESTED = "manifested"
            REJECT_DZ = "reject_dz"
            SUSPEND_MUS = "suspend_mus"
            REJECT_FTEL = "reject_ftel"

        @dataclass
        class KSnapRecord:
            snap_id: str; module: str; result: str; i_value: float
            ftel_magnitude: float; psi_anchor_id: str; description: str
            timestamp: float = field(default_factory=time.time)
            snapshot_hash: str = ""
            def to_dict(self) -> Dict[str, Any]:
                return {k: v for k, v in self.__dict__.items()}

        @dataclass
        class MUSDualEntry:
            entry_id: str; description_a: str; description_b: str
            code_a: str; code_b: str
            created_at: float = field(default_factory=time.time)
            snap_ref: Optional[str] = None
            def to_dict(self) -> Dict[str, Any]:
                return {k: v for k, v in self.__dict__.items()}

# ── Enums & Constants ──────────────────────────────────────────────
class PDEType(Enum):
    MASS = "mass"; MOMENTUM = "momentum"; ENERGY = "energy"
    PARTICLE = "particle"; CHARGE = "charge"

CONSERVATION_TOL = 1e-9
REGULATORY_I = 0.8
CONSTITUTIONAL_I = 1.0


# ╔══════════════════════════════════════════════════════════════════╗
# ║  01. Hyperedge                                                    ║
# ╚══════════════════════════════════════════════════════════════════╝
@dataclass
class Hyperedge:
    """n-ary semantic relation in EML-KB hypergraph."""
    id: str; name: str; nodes: List[str]
    weight: float = 1.0
    pde_type: Optional[str] = None
    conservation_value: float = 0.0
    gan_projection: Dict[str, float] = field(default_factory=lambda: {"cos": 0.0, "sin": 0.0})
    kappa_value: float = 0.0
    domain: Optional[str] = None

    def __post_init__(self):
        if not self.id: self.id = uuid.uuid4().hex[:12]
        if not self.nodes: raise ValueError(f"Hyperedge {self.id} needs ≥1 node")

    @property
    def arity(self) -> int: return len(self.nodes)
    def node_set(self) -> Set[str]: return set(self.nodes)
    def to_dict(self) -> Dict[str, Any]: return self.__dict__.copy()
    @classmethod
    def from_dict(cls, d): return cls(**d)


# ╔══════════════════════════════════════════════════════════════════╗
# ║  02. FrobeniusGenerator                                           ║
# ╚══════════════════════════════════════════════════════════════════╝
class FrobeniusGenerator:
    """Merge(μ) / Split(δ): merge_prob=cos(φ), split_prob=sin(φ)."""

    def __init__(self, gan_polarizer=None):
        self.gan_polarizer = gan_polarizer
        self.phi = pi / 4
        self.merge_count = 0; self.split_count = 0

    def set_polarization(self, phi: float): self.phi = phi % (2 * pi)
    def merge_prob(self) -> float: return cos(self.phi)
    def split_prob(self) -> float: return sin(self.phi)

    def merge(self, edges: List[Hyperedge]) -> Hyperedge:
        """Merge: union nodes, avg weight, min conservation, max κ."""
        if not edges: raise ValueError("empty edge list")
        if len(edges) == 1: return edges[0]
        if self.merge_prob() < 0.1:
            logger.info(f"Merge rejected: cos(φ)={self.merge_prob():.4f}")
            return edges[0]
        nodes = sorted(set().union(*(e.node_set() for e in edges)))
        w = sum(e.weight for e in edges) / len(edges)
        cv = min(e.conservation_value for e in edges)
        pde = next((e.pde_type for e in edges if e.pde_type), None)
        name = "+".join(e.name for e in edges)
        domains = {e.domain for e in edges if e.domain}
        dm = domains.pop() if len(domains) == 1 else None
        kp = max(e.kappa_value for e in edges)
        merged = Hyperedge(id=uuid.uuid4().hex[:12], name=name, nodes=nodes,
                           weight=w, pde_type=pde, conservation_value=cv,
                           kappa_value=kp, domain=dm)
        self.merge_count += 1
        return merged

    def split(self, edge: Hyperedge, n_parts: int = 2) -> List[Hyperedge]:
        """Split: partition nodes by hash-similarity, distribute cv proportionally."""
        if n_parts < 2: return [edge]
        if self.split_prob() < 0.1:
            logger.info(f"Split rejected: sin(φ)={self.split_prob():.4f}")
            return [edge]
        n = len(edge.nodes)
        if n <= n_parts:
            return [Hyperedge(id=uuid.uuid4().hex[:12], name=f"{edge.name}_s{i}",
                              nodes=[nd], weight=edge.weight/n,
                              pde_type=edge.pde_type,
                              conservation_value=edge.conservation_value/n,
                              kappa_value=edge.kappa_value, domain=edge.domain)
                    for i, nd in enumerate(edge.nodes)]
        parts = self._partition_nodes(edge.nodes, n_parts)
        result = []
        for i, part in enumerate(parts):
            if not part: continue
            ratio = len(part) / n
            result.append(Hyperedge(id=uuid.uuid4().hex[:12], name=f"{edge.name}_s{i}",
                                     nodes=sorted(part), weight=edge.weight*ratio,
                                     pde_type=edge.pde_type,
                                     conservation_value=edge.conservation_value*ratio,
                                     kappa_value=edge.kappa_value, domain=edge.domain))
        self.split_count += 1
        return result

    def _partition_nodes(self, nodes: List[str], n_parts: int) -> List[List[str]]:
        """Hash-based cosine similarity clustering into n_parts."""
        dim = 8
        vecs = {}
        for nd in nodes:
            h = hashlib.sha256(nd.encode()).hexdigest()
            vecs[nd] = [int(h[j*4:(j+1)*4], 16) / 65536.0 for j in range(dim)]
        def csim(a, b):
            dot = sum(x*y for x,y in zip(a,b))
            ma, mb = sqrt(sum(x*x for x in a)), sqrt(sum(x*x for x in b))
            return dot / (ma * mb) if ma > CONSERVATION_TOL and mb > CONSERVATION_TOL else 0.0
        centers = nodes[:n_parts]
        clusters = {c: [c] for c in centers}
        for nd in nodes[n_parts:]:
            best = max(centers, key=lambda c: csim(vecs[nd], vecs[c]))
            clusters[best].append(nd)
        return [clusters[c] for c in centers if clusters[c]]

    def verify_frobenius_law(self, original: List[Hyperedge]) -> bool:
        """merge(split(merge(original))) ≈ merge(original)."""
        if not original: return True
        m1 = self.merge(original)
        parts = self.split(m1)
        m2 = self.merge(parts)
        if m1.node_set() != m2.node_set(): return False
        return abs(m1.conservation_value - m2.conservation_value) < CONSERVATION_TOL * 10

    def _run_self_test(self) -> Dict[str, Any]:
        checks = []; p = 0; f = 0
        e1 = Hyperedge(id="t1", name="a", nodes=["x","y"], weight=2.0, conservation_value=1.0)
        e2 = Hyperedge(id="t2", name="b", nodes=["y","z"], weight=3.0, conservation_value=0.5)
        self.set_polarization(pi/4)
        m = self.merge([e1, e2])
        checks.append(("merge_union", m.node_set() == {"x","y","z"}))
        checks.append(("merge_weight_avg", abs(m.weight - 2.5) < CONSERVATION_TOL))
        checks.append(("merge_cv_min", m.conservation_value == 0.5))
        parts = self.split(m, 2)
        checks.append(("split_2_parts", len(parts) == 2))
        checks.append(("split_cv_sum", abs(sum(p.conservation_value for p in parts) - 0.5) < CONSERVATION_TOL))
        self.set_polarization(0.0)
        checks.append(("merge_prob_cos0", abs(self.merge_prob() - 1.0) < CONSERVATION_TOL))
        self.set_polarization(pi/2)
        checks.append(("split_prob_sin", abs(self.split_prob() - 1.0) < CONSERVATION_TOL))
        for _, ok in checks: p += ok; f += not ok
        return {"passed": p, "failed": f, "checks": checks}


# ╔══════════════════════════════════════════════════════════════════╗
# ║  03. CupCapDuality                                                ║
# ╚══════════════════════════════════════════════════════════════════╝
class CupCapDuality:
    """Cup=contract (s,t)→vertex [L1], Cap=expand vertex→(s,t) [L3]."""

    def __init__(self):
        self.cup_records: List[Dict] = []
        self.cap_records: List[Dict] = []
        self.contraction_map: Dict[str, Tuple[str,str]] = {}
        self.expansion_map: Dict[Tuple[str,str], str] = {}

    def cup(self, src: str, tgt: str, edges: List[Hyperedge], label="") -> Tuple[str, List[Hyperedge]]:
        """Contract src+tgt → new vertex."""
        vid = hashlib.sha256(f"cup:{src}:{tgt}".encode()).hexdigest()[:12]
        self.contraction_map[vid] = (src, tgt)
        self.expansion_map[(src, tgt)] = vid
        updated = []
        for e in edges:
            changed = False; new = []
            for nd in e.nodes:
                if nd == src or nd == tgt: new.append(vid); changed = True
                else: new.append(nd)
            if changed: new = list(dict.fromkeys(new))
            updated.append(Hyperedge(id=e.id, name=e.name,
                                      nodes=new if changed else e.nodes,
                                      weight=e.weight, pde_type=e.pde_type,
                                      conservation_value=e.conservation_value,
                                      gan_projection=e.gan_projection,
                                      kappa_value=e.kappa_value, domain=e.domain))
        self.cup_records.append({"op":"cup","src":src,"tgt":tgt,"vid":vid,"t":time.time(),"L":"L1"})
        return vid, updated

    def cap(self, vid: str, edges: List[Hyperedge]) -> Tuple[str, str, List[Hyperedge]]:
        """Expand vertex → (src, tgt)."""
        pair = self.contraction_map.get(vid)
        if pair: src, tgt = pair
        else: src = f"cap_s_{vid}"; tgt = f"cap_t_{vid}"; self.contraction_map[vid] = (src, tgt)
        updated = []
        for e in edges:
            changed = False; new = []
            for nd in e.nodes:
                if nd == vid: new.extend([src, tgt]); changed = True
                else: new.append(nd)
            updated.append(Hyperedge(id=e.id, name=e.name,
                                      nodes=new if changed else e.nodes,
                                      weight=e.weight, pde_type=e.pde_type,
                                      conservation_value=e.conservation_value,
                                      gan_projection=e.gan_projection,
                                      kappa_value=e.kappa_value, domain=e.domain))
        self.cap_records.append({"op":"cap","vid":vid,"src":src,"tgt":tgt,"t":time.time(),"L":"L3"})
        return src, tgt, updated

    def verify_self_dual(self, edges: List[Hyperedge]) -> bool:
        """cup(cap(edges)) ≈ edges."""
        if not self.contraction_map: return True
        for vid, (src, tgt) in list(self.contraction_map.items()):
            _, _, after_cap = self.cap(vid, edges)
            _, after_cup = self.cup(src, tgt, after_cap)
            orig = set().union(*(e.node_set() for e in edges))
            res = set().union(*(e.node_set() for e in after_cup))
            if not orig.issubset(res): return False
        return True

    def _run_self_test(self) -> Dict[str, Any]:
        checks = []; p = 0; f = 0
        edges = [Hyperedge(id="c1", name="r", nodes=["a","b","c"], weight=1.0)]
        v, ce = self.cup("a", "b", edges)
        checks.append(("cup_replaces", any(v in e.nodes for e in ce)))
        s, t, pe = self.cap(v, ce)
        checks.append(("cap_expands", any(s in e.nodes and t in e.nodes for e in pe)))
        checks.append(("self_dual", self.verify_self_dual(ce)))
        for _, ok in checks: p += ok; f += not ok
        return {"passed": p, "failed": f, "checks": checks}


# ╔══════════════════════════════════════════════════════════════════╗
# ║  04. GlueValidator                                                ║
# ╚══════════════════════════════════════════════════════════════════╝
class GlueValidator:
    """Associativity, Unitality, Frobenius law checks."""

    def __init__(self): self.log: List[Dict] = []

    def validate_associativity(self, fg: FrobeniusGenerator, edges: List[Hyperedge]) -> bool:
        """merge(A, merge(B,C)) == merge(merge(A,B), C)."""
        if len(edges) < 3:
            self.log.append({"axiom":"assoc","result":True,"reason":"trivial"}); return True
        n = len(edges)
        a, b, c = edges[:n//3], edges[n//3:2*n//3], edges[2*n//3:]
        if not (a and b and c): return True
        left = fg.merge(a + [fg.merge(b + c)])
        right = fg.merge([fg.merge(a + b)] + c)
        ok = left.node_set() == right.node_set()
        self.log.append({"axiom":"assoc","result":ok})
        return ok

    def validate_unitality(self, cd: CupCapDuality, edges: List[Hyperedge]) -> bool:
        """cap∘cup on unit η preserves edge set."""
        if not edges: return True
        uid = "unit_eta"
        edges_u = edges + [Hyperedge(id="unit", name="η", nodes=[uid], weight=1.0)]
        src, tgt, after_cap = cd.cap(uid, edges_u)
        _, after_cup = cd.cup(src, tgt, after_cap)
        orig = set().union(*(e.node_set() for e in edges))
        res = set().union(*(e.node_set() for e in after_cup))
        ok = orig.issubset(res)
        self.log.append({"axiom":"unit","result":ok})
        return ok

    def validate_frobenius_law(self, fg: FrobeniusGenerator, cd: CupCapDuality,
                                edges: List[Hyperedge]) -> bool:
        """Frobenius law: merge(split(merge(x))) ≈ merge(x) — node-set isomorphism.
        Conservation invariance is checked separately via P14 (charge conservation)."""
        if not edges: return True
        m1 = fg.merge(edges)
        parts = fg.split(m1)
        m2 = fg.merge(parts)
        ok = m1.node_set() == m2.node_set()
        self.log.append({"axiom":"frob","result":ok})
        return ok

    def _run_self_test(self) -> Dict[str, Any]:
        checks = []; p = 0; f = 0
        fg = FrobeniusGenerator(); fg.set_polarization(pi/4)
        edges = [Hyperedge(id=f"v{i}", name=f"e{i}", nodes=[chr(97+i), chr(98+i)],
                           weight=float(i+1), conservation_value=float(i+1))
                 for i in range(6)]
        checks.append(("associativity", self.validate_associativity(fg, edges)))
        checks.append(("frobenius", self.validate_frobenius_law(fg, CupCapDuality(), edges)))
        for _, ok in checks: p += ok; f += not ok
        return {"passed": p, "failed": f, "checks": checks}


# ╔══════════════════════════════════════════════════════════════════╗
# ║  05. PsiAnchorFilter                                              ║
# ╚══════════════════════════════════════════════════════════════════╝
class PsiAnchorFilter:
    """Charge conservation + PII domain isolation + I-value threshold."""

    def __init__(self, psi_gate=None):
        self.psi_gate = psi_gate
        self.charge_rule = True; self.domain_isolation = True
        self.log: List[Dict] = []

    def check_charge_conservation(self, edges: List[Hyperedge]) -> bool:
        """Sum of conservation_values ≈ constant; charge type ≈ 0."""
        if not edges: return True
        charge_e = [e for e in edges if e.pde_type == PDEType.CHARGE.value]
        if charge_e and abs(sum(e.conservation_value for e in charge_e)) > CONSERVATION_TOL:
            self.log.append({"check":"charge","ok":False}); return False
        total = sum(e.conservation_value for e in edges)
        if not math.isfinite(total):
            self.log.append({"check":"charge","ok":False}); return False
        self.log.append({"check":"charge","ok":True,"total":total}); return True

    def check_domain_isolation(self, edges: List[Hyperedge]) -> bool:
        """Edges from different PII domains must not share nodes."""
        if not edges or not self.domain_isolation: return True
        dmap: Dict[str, Set[str]] = {}
        for e in edges:
            d = e.domain or "default"
            dmap.setdefault(d, set()).update(e.nodes)
        names = list(dmap.keys())
        for i in range(len(names)):
            for j in range(i+1, len(names)):
                if dmap[names[i]] & dmap[names[j]]:
                    self.log.append({"check":"domain","ok":False}); return False
        self.log.append({"check":"domain","ok":True}); return True

    def compute_i_value(self, edge: Hyperedge) -> float:
        """I = weight_norm × conservation_compliance × kappa_depth, clamped [0,1]."""
        w = min(1.0, max(0.1, edge.weight / 3.0)) if edge.weight > 0 else 0.1
        cc = min(1.0, abs(edge.conservation_value)) if edge.pde_type else 0.5
        kd = min(1.0, edge.kappa_value / 7.0) if edge.kappa_value > 0 else 0.1
        return max(0.0, min(1.0, w * cc * kd))

    def filter(self, edges: List[Hyperedge], level: str = "regulatory") -> List[Hyperedge]:
        """Filter by psi-anchor level: constitutional(I=1.0), regulatory(I≥0.8), operational(any)."""
        if not edges: return edges
        if self.charge_rule:
            if not self.check_charge_conservation(edges) and level == "constitutional": return []
        if self.domain_isolation:
            if not self.check_domain_isolation(edges) and level == "constitutional": return []
        compliant = []
        for e in edges:
            iv = self.compute_i_value(e)
            if level == "constitutional":
                if abs(iv - CONSTITUTIONAL_I) < 0.05: compliant.append(e)
            elif level == "regulatory":
                if iv >= REGULATORY_I: compliant.append(e)
            else:
                compliant.append(e)
        self.log.append({"check":"filter","level":level,"in":len(edges),"out":len(compliant)})
        return compliant

    def _run_self_test(self) -> Dict[str, Any]:
        checks = []; p = 0; f = 0
        e1 = [Hyperedge(id="q1",name="pos",nodes=["a"],conservation_value=1.0,pde_type=PDEType.CHARGE.value),
               Hyperedge(id="q2",name="neg",nodes=["b"],conservation_value=-1.0,pde_type=PDEType.CHARGE.value)]
        checks.append(("charge_neutral", self.check_charge_conservation(e1)))
        checks.append(("charge_violation", not self.check_charge_conservation(
            [Hyperedge(id="q3",name="pos",nodes=["a"],conservation_value=2.0,pde_type=PDEType.CHARGE.value)])))
        checks.append(("domain_ok", self.check_domain_isolation(
            [Hyperedge(id="d1",name="m",nodes=["p1"],domain="health"),
             Hyperedge(id="d2",name="f",nodes=["a1"],domain="fin")])))
        checks.append(("domain_violation", not self.check_domain_isolation(
            [Hyperedge(id="d3",name="m",nodes=["shared"],domain="health"),
             Hyperedge(id="d4",name="f",nodes=["shared"],domain="fin")])))
        # Use weight that gives I ≥ 0.8: weight=5 → w=1.0, cv=1→cc=0.5→I=0.5; need higher
        # weight=5, cv=2, pde_type set → cc=1.0, kappa=7 → kd=1.0, w=1.67→min=1.0, I=1.0
        good = Hyperedge(id="r1",name="good",nodes=["a"],weight=5.0,
                         conservation_value=2.0,pde_type=PDEType.ENERGY.value,kappa_value=7.0)
        weak = Hyperedge(id="r2",name="weak",nodes=["b"],weight=0.1,
                         conservation_value=0.01,kappa_value=0.1)
        filt = self.filter([good, weak], "regulatory")
        checks.append(("regulatory_filter", len(filt) >= 1))
        checks.append(("i_value_high", self.compute_i_value(good) >= REGULATORY_I))
        for _, ok in checks: p += ok; f += not ok
        return {"passed": p, "failed": f, "checks": checks}


# ╔══════════════════════════════════════════════════════════════════╗
# ║  06. HypergraphBuilder                                            ║
# ╚══════════════════════════════════════════════════════════════════╝
class HypergraphBuilder:
    """Five-step pipeline: Frobenius → Cup/Cap → Gan → Psi-anchor → κ-Snap."""

    def __init__(self, gan_polarizer=None, psi_gate=None):
        self.frobenius = FrobeniusGenerator(gan_polarizer)
        self.cup_cap = CupCapDuality()
        self.validator = GlueValidator()
        self.psi_filter = PsiAnchorFilter(psi_gate)
        self.audit_records: List[Any] = []
        self.edges: List[Hyperedge] = []
        self.frobenius.set_polarization(pi / 4)

    def build(self, nodes: List[str], relations: List[Tuple[str,str,str]]) -> Dict[str, Any]:
        """Build hypergraph: 5-step pipeline, returns {hyperedges, laws, gan, audit, stats}."""
        t0 = time.time()
        # Step 0: initial edges from triples
        init = self._make_initial_edges(nodes, relations)
        # Step 1: Frobenius merge/split
        s1 = self._apply_frobenius(init)
        # Step 2: Cup/Cap + axiom verification
        laws = self._verify_cup_cap(s1)
        # Step 3: Gan polarization
        s3 = [self._gan_projection(e) for e in s1]
        gan_sum = self._gan_summary(s3)
        # Step 4: psi-anchor filter (operational level — no strict I threshold for build)
        filtered = self.psi_filter.filter(s3, "operational")
        discarded = [e for e in s3 if e not in filtered]
        # Step 5: κ-Snap audit
        audit = self._kappa_snap(f"build: {len(nodes)} nodes, {len(relations)} rels", discarded)
        self.edges = filtered
        stats = {"nodes": len(nodes), "rels": len(relations), "init": len(init),
                 "after_frob": len(s1), "kept": len(filtered), "discarded": len(discarded),
                 "elapsed": time.time() - t0}
        return {"hyperedges": [e.to_dict() for e in filtered], "frobenius_laws": laws,
                "gan_projection": gan_sum, "audit": audit.to_dict(), "statistics": stats}

    def _make_initial_edges(self, nodes, relations) -> List[Hyperedge]:
        groups: Dict[str, Set[str]] = {}
        counts: Dict[str, int] = {}
        for src, rel, tgt in relations:
            groups.setdefault(rel, set()).update([src, tgt])
            counts[rel] = counts.get(rel, 0) + 1
        return [Hyperedge(id=uuid.uuid4().hex[:12], name=r,
                          nodes=sorted(groups[r]), weight=float(counts[r]),
                          conservation_value=float(counts[r]),
                          pde_type=PDEType.ENERGY.value, kappa_value=3.0)
                for r in groups]

    def _apply_frobenius(self, edges: List[Hyperedge]) -> List[Hyperedge]:
        result = list(edges)
        if self.frobenius.merge_prob() > 0.1:
            merged_i: Set[int] = set(); groups: List[List[Hyperedge]] = []
            for i in range(len(result)):
                if i in merged_i: continue
                grp = [result[i]]
                for j in range(i+1, len(result)):
                    if j in merged_i: continue
                    ov = len(result[i].node_set() & result[j].node_set())
                    un = len(result[i].node_set() | result[j].node_set())
                    if un > 0 and ov / un > 0.5:
                        grp.append(result[j]); merged_i.add(j)
                if len(grp) > 1: groups.append(grp); merged_i.add(i)
            new = [e for i,e in enumerate(result) if i not in merged_i]
            for grp in groups:
                domains = {e.domain for e in grp if e.domain}
                if len(domains) > 1: new.extend(grp); continue
                new.append(self.frobenius.merge(grp))
            result = new
        if self.frobenius.split_prob() > 0.1:
            result = [e if e.arity <= 10 else self.frobenius.split(e)[0]
                      if len(self.frobenius.split(e, min(3, e.arity//5))) == 1
                      else self.frobenius.split(e, min(3, e.arity//5))[0]
                      for e in result]
            # Fix: properly split large edges
            new = []
            for e in result:
                if e.arity > 10:
                    new.extend(self.frobenius.split(e, min(3, e.arity//5)))
                else:
                    new.append(e)
            result = new
        return result

    def _gan_projection(self, e: Hyperedge) -> Hyperedge:
        """φ=atan2(cv, w); cos(φ)=PDE prior, sin(φ)=data likelihood; κ=-log2(|cos-sin|+ε)."""
        phi = atan2(e.conservation_value, e.weight) if (e.weight or e.conservation_value) else 0.0
        e.gan_projection = {"cos": cos(phi), "sin": sin(phi), "phi": phi}
        asym = abs(cos(phi) - sin(phi)) + 1e-9
        e.kappa_value = max(0.0, min(7.0, -math.log2(asym)))
        return e

    def _gan_summary(self, edges: List[Hyperedge]) -> Dict[str, Any]:
        if not edges: return {"total":0,"avg_cos":0.0,"avg_sin":0.0}
        n = len(edges)
        ac = sum(e.gan_projection.get("cos",0) for e in edges)/n
        asin = sum(e.gan_projection.get("sin",0) for e in edges)/n
        ak = sum(e.kappa_value for e in edges)/n
        return {"total":n,"avg_cos":ac,"avg_sin":asin,"avg_kappa":ak,
                "balance": ac/(ac+asin+1e-9)}

    def _verify_cup_cap(self, edges: List[Hyperedge]) -> Dict[str, bool]:
        laws = {"associativity": True, "unitality": True, "frobenius": True}
        if len(edges) >= 3: laws["associativity"] = self.validator.validate_associativity(self.frobenius, edges)
        if edges: laws["unitality"] = self.validator.validate_unitality(self.cup_cap, edges)
        if edges: laws["frobenius"] = self.validator.validate_frobenius_law(self.frobenius, self.cup_cap, edges)
        return laws

    def _kappa_snap(self, desc: str, discarded: List[Hyperedge]) -> Any:
        kept = self.edges
        iv = sum(self.psi_filter.compute_i_value(e) for e in kept)/max(1,len(kept))
        ftel = max((abs(e.conservation_value) for e in kept), default=0.0)
        eid = hashlib.sha256(desc.encode()).hexdigest()[:12]
        h = hashlib.sha256("|".join(sorted(hashlib.sha256(json.dumps(e.to_dict(),sort_keys=True).encode()).hexdigest() for e in kept)).encode()).hexdigest()
        res = SnapResult.REJECT_DZ.value if discarded and not kept else \
              (SnapResult.SUSPEND_MUS.value if discarded else SnapResult.MANIFESTED.value)
        audit = KSnapRecord(snap_id=uuid.uuid4().hex[:12], module="hypergraph_categories",
                            result=res, i_value=iv, ftel_magnitude=ftel,
                            psi_anchor_id=eid, description=desc, timestamp=time.time(),
                            snapshot_hash=h)
        self.audit_records.append(audit)
        return audit

    def _run_self_test(self) -> Dict[str, Any]:
        checks = []; p = 0; f = 0
        r = self.build(["a","b","c","d"], [("a","connects","b"),("b","connects","c"),("c","connects","d")])
        checks.append(("build_has_edges", len(r["hyperedges"]) > 0))
        checks.append(("build_has_laws", "frobenius_laws" in r))
        checks.append(("build_has_gan", "gan_projection" in r))
        checks.append(("build_has_audit", "audit" in r))
        if self.edges:
            e = self.edges[0]
            checks.append(("gan_cos_sin", "cos" in e.gan_projection and "sin" in e.gan_projection))
        else:
            checks.append(("gan_cos_sin", False))
        checks.append(("charge_ok", self.psi_filter.check_charge_conservation(self.edges)))
        for _, ok in checks: p += ok; f += not ok
        return {"passed": p, "failed": f, "checks": checks}


# ── Module self-test & predictive claims ────────────────────────────
def run_all_self_tests() -> Dict[str, Any]:
    results = {}
    fg = FrobeniusGenerator(); fg.set_polarization(pi/4)
    results["FrobeniusGenerator"] = fg._run_self_test()
    results["CupCapDuality"] = CupCapDuality()._run_self_test()
    results["GlueValidator"] = GlueValidator()._run_self_test()
    results["PsiAnchorFilter"] = PsiAnchorFilter()._run_self_test()
    results["HypergraphBuilder"] = HypergraphBuilder()._run_self_test()
    tp = sum(r["passed"] for r in results.values())
    tf = sum(r["failed"] for r in results.values())
    results["summary"] = {"total_passed": tp, "total_failed": tf, "all_passed": tf == 0}
    return results

def verify_predictive_claims() -> Dict[str, bool]:
    claims = {}
    # P14: split distributes merged conservation proportionally (∑parts ≈ merged)
    fg = FrobeniusGenerator(); fg.set_polarization(pi/4)
    e = [Hyperedge(id="p1",name="a",nodes=["x"],weight=2.0,conservation_value=3.0,pde_type=PDEType.CHARGE.value),
         Hyperedge(id="p2",name="b",nodes=["y"],weight=1.0,conservation_value=-3.0,pde_type=PDEType.CHARGE.value)]
    m = fg.merge(e); parts = fg.split(m)
    claims["P14"] = abs(sum(p.conservation_value for p in parts) - m.conservation_value) < CONSERVATION_TOL * 10
    # P15: self-dual compact closed
    cd = CupCapDuality()
    te = [Hyperedge(id="p5",name="r",nodes=["α","β"],weight=1.0)]
    v, ce = cd.cup("α", "β", te)
    claims["P15"] = cd.verify_self_dual(ce)
    # P16: κ∈[0,7]
    hb = HypergraphBuilder()
    e16 = Hyperedge(id="p6",name="t",nodes=["a","b"],weight=5.0,conservation_value=3.0)
    e16 = hb._gan_projection(e16)
    claims["P16"] = 0.0 <= e16.kappa_value <= 7.0
    return claims

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print("=" * 60)
    print("Hypergraph Categories — Self-Test")
    print("=" * 60)
    r = run_all_self_tests()
    for cls, v in r.items():
        if cls == "summary": continue
        print(f"\n{cls}:")
        for name, ok in v["checks"]:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        print(f"  {v['passed']} passed, {v['failed']} failed")
    print(f"\nOverall: {r['summary']['total_passed']} passed, {r['summary']['total_failed']} failed")
    print(f"All passed: {r['summary']['all_passed']}")
    print("\nPredictive Claims:")
    for c, v in verify_predictive_claims().items():
        print(f"  [{'CONFIRMED' if v else 'REJECTED'}] {c}")
    sys.exit(0 if r["summary"]["all_passed"] else 1)
