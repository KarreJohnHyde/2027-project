import { useState } from "react";
import { api, type Finding } from "../services/api";
import { useSelectedCase, useWorkspace } from "../state/workspace";
import { useAsync } from "../lib/useAsync";
import { errorMessage, formatNumber } from "../lib/format";
import { Button, Disclosure, ErrorBlock, Field, KeyValue, SelectInput, Spinner, StatusBadge, TextArea, TextInput } from "../components/ui";
import { landmarkApi, type LandmarkManifest, type RegistrationGateResult } from "./landmarkApi";
import { canDecideLandmarks, canManageLandmarks, parseLandmarkPairs, validateLandmarkPartition, type LandmarkPair } from "./landmarkValidation";

function CoordinateTable({ title, pairs }: { title: string; pairs: LandmarkPair[] }) {
  return <div className="max-h-52 overflow-auto rounded border border-line" tabIndex={0} aria-label={title}>
    <table className="w-full text-left text-[11px] tabular">
      <caption className="p-2 text-left font-semibold">{title} — millimetres</caption>
      <thead><tr><th scope="col" className="p-1">Pair</th><th scope="col" className="p-1">Source x, y, z</th><th scope="col" className="p-1">Target x, y, z</th></tr></thead>
      <tbody>{pairs.map((pair, index) => <tr key={index} className="border-t border-line"><th scope="row" className="p-1">{index + 1}</th><td className="p-1">{pair.source.join(", ")}</td><td className="p-1">{pair.target.join(", ")}</td></tr>)}</tbody>
    </table>
  </div>;
}

function ManifestReview({ manifest, canManage, onChanged }: { manifest: LandmarkManifest; canManage: boolean; onChanged: () => void }) {
  const user = useWorkspace(state => state.user);
  const loadEvidence = useWorkspace(state => state.loadEvidence);
  const [comment, setComment] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [applyConfirmed, setApplyConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gate, setGate] = useState<RegistrationGateResult | null>(null);
  const coordinatesAvailable = manifest.fit_pairs >= 3 && manifest.held_out_pairs >= 1
    && manifest.fit_landmarks?.length === manifest.fit_pairs && manifest.held_out_landmarks?.length === manifest.held_out_pairs;
  const canDecide = canDecideLandmarks(canManage, user?.id, manifest.created_by_id, manifest.status, coordinatesAvailable);

  async function decide(decision: "APPROVED" | "REJECTED") {
    if (!canDecide || !reviewed || comment.trim().length < 3) return;
    setBusy(true); setError(null);
    try {
      await landmarkApi.decide(manifest.id, decision, comment.trim());
      setReviewed(false); onChanged();
    } catch (cause) { setError(errorMessage(cause)); } finally { setBusy(false); }
  }

  async function evaluate() {
    if (!canManage || manifest.status !== "APPROVED" || !applyConfirmed) return;
    setBusy(true); setError(null); setGate(null);
    try {
      const result = await landmarkApi.evaluate(manifest.finding_id, manifest.id);
      setGate(result); setApplyConfirmed(false);
      await loadEvidence(); onChanged();
    } catch (cause) { setError(errorMessage(cause)); } finally { setBusy(false); }
  }

  return <Disclosure summary={<span className="flex flex-wrap items-center gap-2">Manifest #{manifest.id} <StatusBadge status={manifest.status} /></span>}>
    <div className="space-y-3">
      <KeyValue columns={1} items={[
        { label: "Finding / case", value: `#${manifest.finding_id} / #${manifest.case_id}` },
        { label: "Declared source → target coordinate frames", value: manifest.coordinate_frame },
        { label: "Requested anatomical region", value: manifest.requested_region },
        { label: "Predeclared mean held-out TRE limit", value: `${manifest.threshold_mm} mm` },
        { label: "Proposer / independent reviewer", value: `User #${manifest.created_by_id} / ${manifest.decided_by_id ? `user #${manifest.decided_by_id}` : "not reviewed"}` },
        { label: "Created / decided", value: `${manifest.created_at} / ${manifest.decided_at ?? "pending"}` },
      ]} />
      {coordinatesAvailable ? <>
        <CoordinateTable title="Fitting landmarks" pairs={manifest.fit_landmarks!} />
        <CoordinateTable title="Held-out landmarks (not used for fitting)" pairs={manifest.held_out_landmarks!} />
      </> : <ErrorBlock message="This server did not return the proposed coordinates. Independent decisions are disabled; counts alone are not reviewable evidence." />}
      {manifest.decision_comment && <p className="text-xs text-ink-2">Review rationale: {manifest.decision_comment}</p>}
      {manifest.status === "PROPOSED" && (canDecide ? <>
        <label className="flex gap-2 text-xs"><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />I independently inspected every coordinate pair against the source evidence, the frame/units, target region, held-out partition and predeclared threshold.</label>
        <Field label="Independent review rationale" htmlFor={`landmark-comment-${manifest.id}`}><TextArea id={`landmark-comment-${manifest.id}`} value={comment} maxLength={2000} rows={2} onChange={event => setComment(event.target.value)} /></Field>
        <div className="flex flex-wrap gap-2"><Button size="sm" disabled={!reviewed || comment.trim().length < 3 || busy} onClick={() => void decide("APPROVED")}>Approve manifest</Button><Button size="sm" variant="danger" disabled={!reviewed || comment.trim().length < 3 || busy} onClick={() => void decide("REJECTED")}>Reject manifest</Button></div>
      </> : <p className="text-xs text-ink-3">Requires a different verified clinician or administrator with case edit access. The proposer cannot approve or reject their own manifest.</p>)}
      {manifest.status === "APPROVED" && canManage && <>
        <label className="flex gap-2 text-xs"><input type="checkbox" checked={applyConfirmed} onChange={event => setApplyConfirmed(event.target.checked)} />Evaluate and replace this finding’s mapping using this approved manifest. A failed gate returns the finding to L1.</label>
        <Button size="sm" disabled={!applyConfirmed || busy} onClick={() => void evaluate()}>Evaluate and apply reviewed gate</Button>
      </>}
      {busy && <Spinner label="Saving landmark review" />}
      {error && <ErrorBlock message={error} />}
      {gate && <div role="status" className="space-y-2 rounded border border-line p-2">
        <StatusBadge status={gate.passed_gate ? "L2_RESEARCH_GATE_PASSED" : "MAPPING_UNSUPPORTED"} />
        <p className="text-xs">{gate.explanatory_reason}</p>
        <p className="text-xs">Mean held-out TRE: {formatNumber(gate.tre_error, 3)} mm / limit {gate.tre_threshold} mm; {gate.held_out_landmarks_count} held-out points.</p>
        {gate.transform_matrix && <Disclosure summary="Computed rigid transform (not a patient mesh)"><pre className="overflow-x-auto text-[10px]">{JSON.stringify(gate.transform_matrix, null, 2)}</pre></Disclosure>}
      </div>}
    </div>
  </Disclosure>;
}

function FindingManifests({ finding, canManage }: { finding: Finding; canManage: boolean }) {
  const manifests = useAsync(() => landmarkApi.list(finding.id), [finding.id]);
  const [frame, setFrame] = useState("");
  const [region, setRegion] = useState("");
  const [threshold, setThreshold] = useState("");
  const [fitText, setFitText] = useState("");
  const [heldOutText, setHeldOutText] = useState("");
  const [attested, setAttested] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function propose() {
    if (!canManage || !attested) return;
    setError(null); setNotice(null);
    try {
      const fit = parseLandmarkPairs(fitText, "fitting");
      const heldOut = parseLandmarkPairs(heldOutText, "held-out");
      validateLandmarkPartition(fit, heldOut);
      const limit = Number(threshold);
      if (frame.trim().length < 3 || region.trim().length < 2 || !Number.isFinite(limit) || limit <= 0 || limit > 50) {
        throw new Error("Provide both coordinate frames, an anatomical region and a justified TRE limit above 0 and at most 50 mm.");
      }
      setBusy(true);
      const proposal = await landmarkApi.propose(finding.id, { coordinate_frame: frame.trim(), requested_region: region.trim(), threshold_mm: limit, fit_pairs: fit, held_out_pairs: heldOut });
      setNotice(`Manifest #${proposal.id} proposed. It does not change the mapping until independent approval and gate evaluation.`);
      setFitText(""); setHeldOutText(""); setAttested(false); manifests.reload();
    } catch (cause) { setError(errorMessage(cause)); } finally { setBusy(false); }
  }

  return <div className="space-y-3">
    <p className="text-xs text-ink-2">Finding #{finding.id}: {finding.label}. Current level: {finding.representation_level}; {finding.mapping_status}.</p>
    {manifests.loading && <Spinner label="Loading landmark manifests" />}
    {manifests.error && <ErrorBlock message={manifests.error} onRetry={manifests.reload} />}
    {!manifests.loading && !manifests.error && manifests.data?.length === 0 && <p className="text-xs text-ink-3">No landmark manifest has been submitted for this finding.</p>}
    {(manifests.data ?? []).filter(manifest => manifest.finding_id === finding.id && manifest.case_id === finding.case_id).map(manifest => <ManifestReview key={manifest.id} manifest={manifest} canManage={canManage} onChanged={manifests.reload} />)}
    {canManage ? <Disclosure summary="Propose measured landmark correspondences">
      <form className="space-y-3" onSubmit={event => { event.preventDefault(); void propose(); }}>
        <p className="text-xs text-ink-2">Import measurements obtained from the actual source study and declared target frame. This is a manual coordinate-entry workflow, not a scan landmark-placement tool. No sample coordinates or inferred patient geometry are supplied.</p>
        <Field label="Source and target coordinate frames / units" htmlFor="landmark-frame" hint="Declare axes/orientation and the mapping direction; all coordinates must already be in mm."><TextInput id="landmark-frame" value={frame} maxLength={128} minLength={3} required onChange={event => setFrame(event.target.value)} /></Field>
        <Field label="Requested anatomical region" htmlFor="landmark-region"><TextInput id="landmark-region" value={region} maxLength={128} minLength={2} required onChange={event => setRegion(event.target.value)} /></Field>
        <Field label="Predeclared mean held-out TRE limit (mm)" htmlFor="landmark-limit" hint="Choose and justify clinically/research appropriate limits before fitting; no default threshold is assumed."><TextInput id="landmark-limit" type="number" min="0.001" max="50" step="any" value={threshold} required onChange={event => setThreshold(event.target.value)} /></Field>
        <p className="text-[11px] text-ink-3">Each JSON array item must have exactly two keys: source and target. Each contains three numeric coordinates [x, y, z]. Do not enter names or other identifying text.</p>
        <Field label="Fitting pairs JSON (3–200)" htmlFor="landmark-fit"><TextArea id="landmark-fit" value={fitText} rows={5} required onChange={event => setFitText(event.target.value)} /></Field>
        <Field label="Held-out pairs JSON (1–100; disjoint from fitting)" htmlFor="landmark-held-out"><TextArea id="landmark-held-out" value={heldOutText} rows={4} required onChange={event => setHeldOutText(event.target.value)} /></Field>
        <label className="flex gap-2 text-xs"><input type="checkbox" checked={attested} onChange={event => setAttested(event.target.checked)} />These measurements belong to this case/finding, use the declared millimetre frames, and the held-out points and threshold were selected independently before fitting.</label>
        <Button type="submit" size="sm" variant="primary" loading={busy} disabled={!attested}>Submit for independent review</Button>
      </form>
    </Disclosure> : <p className="text-xs text-ink-3">Read-only: proposing, deciding and applying landmark manifests requires a verified clinician/administrator and case edit access.</p>}
    {error && <ErrorBlock message={error} />}
    {notice && <p role="status" className="text-xs text-ink-2">{notice}</p>}
  </div>;
}

function CaseLandmarks({ caseId, ownerId }: { caseId: number; ownerId: number | null }) {
  const user = useWorkspace(state => state.user);
  const findings = useWorkspace(state => state.evidence.findings).filter(finding => finding.case_id === caseId);
  const loadingEvidence = useWorkspace(state => state.loadingEvidence);
  const members = useAsync(() => api.getCaseMembers(caseId), [caseId]);
  const [findingId, setFindingId] = useState<number | null>(null);
  const finding = findings.find(item => item.id === findingId) ?? null;
  const canManage = !loadingEvidence && canManageLandmarks(user, ownerId, members.data ?? []);
  return <div className="space-y-3">
    {loadingEvidence ? <Spinner label="Loading case findings" /> : <Field label="Case finding to register" htmlFor="landmark-finding"><SelectInput id="landmark-finding" value={finding?.id ?? ""} onChange={event => setFindingId(event.target.value ? Number(event.target.value) : null)}><option value="">Select a finding</option>{findings.map(item => <option key={item.id} value={item.id}>#{item.id} {item.label}</option>)}</SelectInput></Field>}
    {members.error && <ErrorBlock message={members.error} onRetry={members.reload} />}
    {!loadingEvidence && !findings.length && <p className="text-xs text-ink-3">This case has no findings to associate. Upload and review appropriate source evidence first.</p>}
    {finding && <FindingManifests key={`${finding.id}:${user?.id}`} finding={finding} canManage={canManage} />}
  </div>;
}

export default function LandmarkManifestPanel() {
  const selectedCase = useSelectedCase();
  const user = useWorkspace(state => state.user);
  return <Disclosure summary="Case landmark manifests — L2 research gate">
    <div className="space-y-3">
      <p className="text-xs text-ink-2">L1 is the generic reference atlas shown above. An approved manifest plus passing held-out TRE may record an L2 finding-associated transform; it does not turn that atlas into the patient’s anatomy. L3 patient-specific reconstruction is unavailable.</p>
      {selectedCase ? <CaseLandmarks key={`${selectedCase.id}:${user?.id}`} caseId={selectedCase.id} ownerId={selectedCase.created_by_id} /> : <p className="text-xs text-ink-3">Select an accessible case before reviewing landmark evidence.</p>}
    </div>
  </Disclosure>;
}
