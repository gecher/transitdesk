import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import type { Notify } from "../hooks";
import type { Hotel } from "../types";
import { Locked } from "./common";
import { ConfirmDialog, Field, Modal } from "./Modal";

interface Props {
  staffKey: string;
  canRead: boolean;
  version: number;
  notify: Notify;
  onChanged: () => void;
}

function HotelDialog({ initial, staffKey, onClose, onSaved }: {
  initial?: Hotel;
  staffKey: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isNew = !initial;
  const [h, setH] = useState<Hotel>({
    name: initial?.name ?? "",
    location: initial?.location ?? "",
    shuttle: initial?.shuttle ?? "",
    phone: initial?.phone ?? "",
  });
  const [errors, setErrors] = useState<Partial<Record<keyof Hotel, string>>>({});
  const [serverError, setServerError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (key: keyof Hotel) => (value: string) => {
    setH((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: undefined }));
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    const found: Partial<Record<keyof Hotel, string>> = {};
    if (h.name.trim().length < 2) found.name = "Enter the hotel name";
    if (h.location.trim().length < 2) found.location = "Where is it?";
    if (h.shuttle.trim().length < 2) found.shuttle = "How do passengers get there?";
    setErrors(found);
    if (Object.keys(found).length) return;
    setBusy(true);
    setServerError("");
    try {
      const body = { name: h.name.trim(), location: h.location.trim(), shuttle: h.shuttle.trim(), phone: h.phone.trim() };
      await api(isNew ? "/api/hotels" : `/api/hotels/${encodeURIComponent(initial!.name)}`, staffKey, {
        method: isNew ? "POST" : "PUT",
        body: JSON.stringify(body),
      });
      onSaved();
    } catch (err) {
      setServerError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={isNew ? "Add a partner hotel" : `Edit ${initial!.name}`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button type="submit" form="hotel-form" className="btn primary" disabled={busy}>
            {busy ? "Saving…" : isNew ? "Add hotel" : "Save changes"}
          </button>
        </>
      }
    >
      <form id="hotel-form" className="form-stack" onSubmit={submit} noValidate>
        {serverError && <div className="form-alert" role="alert">{serverError}</div>}
        <Field label="Hotel name" error={errors.name} hint={isNew ? undefined : "Names can't be changed"}>
          <input name="name" value={h.name} disabled={!isNew} onChange={(e) => set("name")(e.target.value)} autoComplete="off" />
        </Field>
        <Field label="Location" error={errors.location}>
          <input name="location" value={h.location} onChange={(e) => set("location")(e.target.value)} placeholder="Bole Road, 3 km from airport" />
        </Field>
        <Field label="Getting there" error={errors.shuttle} hint="The agent reads this to give directions">
          <textarea name="shuttle" rows={2} value={h.shuttle} onChange={(e) => set("shuttle")(e.target.value)} />
        </Field>
        <Field label="Phone">
          <input name="phone" value={h.phone} onChange={(e) => set("phone")(e.target.value)} />
        </Field>
      </form>
    </Modal>
  );
}

type Dialog = { kind: "add" } | { kind: "edit"; hotel: Hotel } | { kind: "delete"; hotel: Hotel } | null;

export function Hotels({ staffKey, canRead, version, notify, onChanged }: Props) {
  const [hotels, setHotels] = useState<Hotel[]>([]);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [busy, setBusy] = useState(false);
  const [locked, setLocked] = useState(false);
  const canEdit = !!staffKey;

  const load = useCallback(async () => {
    if (!canRead) return;
    try {
      setHotels(await api<Hotel[]>("/api/hotels", staffKey));
      setLocked(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setLocked(true);
    }
  }, [canRead, staffKey]);

  useEffect(() => {
    void load();
  }, [load, version]);

  async function remove(h: Hotel) {
    setBusy(true);
    try {
      await api(`/api/hotels/${encodeURIComponent(h.name)}`, staffKey, { method: "DELETE" });
      notify(`${h.name} deleted`);
      setDialog(null);
      onChanged();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Could not delete", true);
      setDialog(null);
    } finally {
      setBusy(false);
    }
  }

  if (!canRead || locked) return <Locked />;
  return (
    <>
      <div className="toolbar">
        <span className="count" id="hotelCount">{hotels.length} partner hotels</span>
        <div className="spacer" />
        {canEdit && (
          <button type="button" className="btn primary" id="addHotel" onClick={() => setDialog({ kind: "add" })}>+ Add hotel</button>
        )}
      </div>
      <div className="hotel-grid" id="hotelsTable">
        {hotels.map((h) => (
          <article key={h.name} className="hotel-card">
            <header>
              <h3>{h.name}</h3>
              <span className="badge-count">{h.bookings} booking{h.bookings === 1 ? "" : "s"}</span>
            </header>
            <dl>
              <dt>Location</dt><dd>{h.location}</dd>
              <dt>Getting there</dt><dd>{h.shuttle}</dd>
              <dt>Phone</dt><dd className="num">{h.phone || "—"}</dd>
            </dl>
            {canEdit && (
              <footer>
                <button type="button" className="btn small ghost" onClick={() => setDialog({ kind: "edit", hotel: h })}>Edit</button>
                <button type="button" className="btn small ghost danger-text" onClick={() => setDialog({ kind: "delete", hotel: h })}>Delete</button>
              </footer>
            )}
          </article>
        ))}
      </div>

      {(dialog?.kind === "add" || dialog?.kind === "edit") && (
        <HotelDialog
          initial={dialog.kind === "edit" ? dialog.hotel : undefined}
          staffKey={staffKey}
          onClose={() => setDialog(null)}
          onSaved={() => { notify("Hotel saved"); setDialog(null); onChanged(); }}
        />
      )}
      {dialog?.kind === "delete" && (
        <ConfirmDialog
          title={`Delete ${dialog.hotel.name}?`}
          message={dialog.hotel.bookings
            ? <>{dialog.hotel.name} still has <b>{dialog.hotel.bookings} booking(s)</b>. The server will refuse until you move or delete them.</>
            : <>Passengers will no longer be sent to {dialog.hotel.name}.</>}
          confirmLabel="Delete hotel"
          busy={busy}
          onConfirm={() => remove(dialog.hotel)}
          onClose={() => setDialog(null)}
        />
      )}
    </>
  );
}
