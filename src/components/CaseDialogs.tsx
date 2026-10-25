import { useState, type FormEvent } from "react";
import { api, type Case } from "../services/api";
import { errorMessage, todayInputValue } from "../lib/format";
import { useWorkspace } from "../state/workspace";
import { Button, Dialog, ErrorBlock, Field, SelectInput, TextArea, TextInput } from "./ui";

export function CreateCaseDialog({ onClose }: { onClose: () => void }) {
  const upsertCase = useWorkspace((state) => state.upsertCase);
  const selectCase = useWorkspace((state) => state.selectCase);
  const setNotice = useWorkspace((state) => state.setNotice);
  const [pseudonym, setPseudonym] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const record = await api.createCase({ pseudonymous_id: pseudonym.trim(), description: description.trim() || null });
      upsertCase(record);
      selectCase(record.id);
      setNotice({ tone: "success", text: `Case ${record.pseudonymous_id} was created.` });
      onClose();
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog title="Create a pseudonymous case" description="Do not enter names, medical-record numbers or any direct identifier." onClose={onClose}>
      <form id="create-case" onSubmit={submit} className="space-y-4">
        <Field label="Pseudonymous case ID" hint="3–64 characters, e.g. MT-RSCH-0042">
          <TextInput data-testid="new-case-pseudonym" required minLength={3} maxLength={64} value={pseudonym} onChange={(event) => setPseudonym(event.target.value)} autoFocus />
        </Field>
        <Field label="Research description (optional)">
          <TextArea rows={3} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="De-identified context only" />
        </Field>
        {error && <ErrorBlock message={error} />}
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={busy} disabled={pseudonym.trim().length < 3}>Create case</Button>
        </div>
      </form>
    </Dialog>
  );
}

export function CreateExaminationDialog({ caseRecord, onClose }: { caseRecord: Case; onClose: () => void }) {
  const refreshCases = useWorkspace((state) => state.refreshCases);
  const setNotice = useWorkspace((state) => state.setNotice);
  const [modality, setModality] = useState<"REPORT" | "IMAGE" | "ECG">("REPORT");
  const [examDate, setExamDate] = useState(todayInputValue);
  const [indication, setIndication] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const record = await api.createExamination(caseRecord.id, {
        exam_date: new Date(`${examDate}T12:00:00`).toISOString(),
        modality,
        clinical_indication: indication.trim() || null,
      });
      await refreshCases();
      setNotice({ tone: "success", text: `${record.modality} examination dated ${examDate} was added.` });
      onClose();
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog title="Add a dated examination" description={`Records dated context for ${caseRecord.pseudonymous_id}. It runs no model.`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Modality">
            <SelectInput value={modality} onChange={(event) => setModality(event.target.value as "REPORT" | "IMAGE" | "ECG")}>
              <option value="REPORT">Report</option>
              <option value="IMAGE">Image</option>
              <option value="ECG">ECG</option>
            </SelectInput>
          </Field>
          <Field label="Examination date">
            <TextInput type="date" required value={examDate} onChange={(event) => setExamDate(event.target.value)} />
          </Field>
        </div>
        <Field label="Indication (optional, de-identified)">
          <TextArea rows={2} value={indication} onChange={(event) => setIndication(event.target.value)} />
        </Field>
        {error && <ErrorBlock message={error} />}
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={busy} disabled={!examDate}>Add examination</Button>
        </div>
      </form>
    </Dialog>
  );
}
