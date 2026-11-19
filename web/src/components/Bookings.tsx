import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import type { Notify } from "../hooks";
import { STATUSES, type Booking, type Hotel, type Status } from "../types";
import { Locked, StatusPill } from "./common";
import { ConfirmDialog, Field, Modal } from "./Modal";

interface Props {
  staffKey: string;
  canRead: boolean;
  activeRef: string | null;
  version: number;          // bumped whenever data may have changed
  notify: Notify;
  onChanged: () => void;
}

interface Draft {
  ref: string;
  passenger: string;
  hotel: string;
  night: string;
  status: Status;
  pickup_time: string;
  onward_flight: string;
}

type Errors = Partial<Record<keyof Draft, string>>;

/** Same rules as the API, checked before sending so mistakes show next to the field. */
function validate(d: Draft, isNew: boolean): Errors {
  const e: Errors = {};
  if (isNew && !/^ET-\d{3,6}$/i.test(d.ref.trim())) e.ref = "Use the format ET-1234";
  if (d.passenger.trim().length < 2) e.passenger = "Enter the passenger's name";
  if (!d.hotel) e.hotel = "Choose a hotel";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d.night)) e.night = "Choose the night of the stay";
  if (d.pickup_time && !/^([01]\d|2[0-3]):[0-5]\d$/.test(d.pickup_time)) e.pickup_time = "Use HH:MM, e.g. 21:30";
  return e;
}

function BookingDialog({ initial, hotels, staffKey, onClose, onSaved }: {
  initial?: Booking;
  hotels: Hotel[];
  staffKey: string;
  onClose: () => void;
  onSaved: (b: Booking) => void;
}) {
  const isNew = !initial;
  const [d, setD] = useState<Draft>({
    ref: initial?.ref ?? "",
    passenger: initial?.passenger ?? "",
    hotel: initial?.hotel ?? hotels[0]?.name ?? "",
    night: initial?.night ?? "",
    status: initial?.status ?? "CONFIRMED",
    pickup_time: initial?.pickup_time ?? "",
    onward_flight: initial?.onward_flight ?? "",
  });
  const [errors, setErrors] = useState<Errors>({});
  const [serverError, setServerError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (key: keyof Draft) => (value: string) => {
    setD((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: undefined }));
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    const found = validate(d, isNew);
    setErrors(found);
    if (Object.keys(found).length) return;
    setBusy(true);
    setServerError("");
    try {
      const body = { ...d, ref: d.ref.trim().toUpperCase(), passenger: d.passenger.trim(), pickup_time: d.pickup_time || null };
      const saved = await api<Booking>(isNew ? "/api/bookings" : `/api/bookings/${initial!.ref}`, staffKey, {
        method: isNew ? "POST" : "PUT",
        body: JSON.stringify(body),
      });
      onSaved(saved);
    } catch (err) {
      setServerError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={isNew ? "Add a booking" : `Edit ${initial!.ref}`}
      onClose={onClose}
      wide
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button type="submit" form="booking-form" className="btn primary" disabled={busy}>
            {busy ? "Saving…" : isNew ? "Add booking" : "Save changes"}
          </button>
        </>
      }
    >
      <form id="booking-form" className="form-grid" onSubmit={submit} noValidate>
        {serverError && <div className="form-alert" role="alert">{serverError}</div>}
        {isNew ? (
          <Field label="Booking reference" error={errors.ref} hint="For example ET-3005">
            <input name="ref" value={d.ref} onChange={(e) => set("ref")(e.target.value)} placeholder="ET-3005" autoComplete="off" />
          </Field>
        ) : (
          <Field label="Booking reference" hint="References can't be changed">
            <input name="ref" value={d.ref} disabled />
          </Field>
        )}
        <Field label="Passenger" error={errors.passenger}>
          <input name="passenger" value={d.passenger} onChange={(e) => set("passenger")(e.target.value)} autoComplete="off" />
        </Field>
        <Field label="Hotel" error={errors.hotel}>
          <select name="hotel" value={d.hotel} onChange={(e) => set("hotel")(e.target.value)}>
            {hotels.map((h) => <option key={h.name}>{h.name}</option>)}
          </select>
        </Field>
        <Field label="Night of stay" error={errors.night}>
          <input name="night" type="date" value={d.night} onChange={(e) => set("night")(e.target.value)} />
        </Field>
        <Field label="Status">
          <div className="segmented" role="radiogroup" aria-label="Status">
            {STATUSES.map((s) => (
              <button key={s} type="button" role="radio" aria-checked={d.status === s}
                      className={"seg " + s + (d.status === s ? " on" : "")} onClick={() => set("status")(s)}>
                {s.charAt(0) + s.slice(1).toLowerCase()}
              </button>
            ))}
          </div>
        </Field>
        <Field label="Pickup time" error={errors.pickup_time} hint="Leave empty if not arranged yet">
          <input name="pickup_time" type="time" value={d.pickup_time} onChange={(e) => set("pickup_time")(e.target.value)} />
        </Field>
        <Field label="Onward flight" hint="For example ET500 to Washington">
          <input name="onward_flight" value={d.onward_flight} onChange={(e) => set("onward_flight")(e.target.value)} autoComplete="off" />
        </Field>
      </form>
    </Modal>
  );
}

type Dialog =
  | { kind: "add" }
  | { kind: "edit"; booking: Booking }
  | { kind: "delete"; booking: Booking }
  | { kind: "reset" }
  | null;

export function Bookings({ staffKey, canRead, activeRef, version, notify, onChanged }: Props) {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [hotels, setHotels] = useState<Hotel[]>([]);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<Status | "">("");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  const canEdit = !!staffKey;

  useEffect(() => {                          // wait until typing pauses before searching
    const t = window.setTimeout(() => setQuery(search.trim()), 250);
    return () => window.clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    if (!canRead) {
      setBookings([]);
      return;
    }
    try {
      const params = new URLSearchParams({ q: query });
      const [b, h] = await Promise.all([
        api<Booking[]>("/api/bookings?" + params, staffKey),
        api<Hotel[]>("/api/hotels", staffKey),
      ]);
      setBookings(b);
      setHotels(h);
      setLocked(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setLocked(true);
        setBookings([]);
        if (staffKey) notify("Staff key not accepted", true);
      }
    }
  }, [canRead, query, staffKey, notify]);

  useEffect(() => {
    void load();
  }, [load, version]);

  // Counts come from the search results; the status filter is applied on top.
  const counts = useMemo(() => {
    const c: Record<Status, number> = { CONFIRMED: 0, PENDING: 0, CANCELLED: 0 };
    bookings.forEach((b) => c[b.status]++);
    return c;
  }, [bookings]);
  const shown = status ? bookings.filter((b) => b.status === status) : bookings;

  function highlight(ref: string) {
    setFlash(ref);
    window.setTimeout(() => setFlash(null), 1700);
  }

  async function remove(b: Booking) {
    setBusy(true);
    try {
      await api(`/api/bookings/${b.ref}`, staffKey, { method: "DELETE" });
      notify(`${b.ref} deleted`);
      setDialog(null);
      onChanged();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Could not delete", true);
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    setBusy(true);
    try {
      await api("/api/reset", staffKey, { method: "POST" });
      notify("Demo data restored");
      setDialog(null);
      setStatus("");
      setSearch("");
      onChanged();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Could not reset", true);
    } finally {
      setBusy(false);
    }
  }

  if (!canRead || locked) return <Locked />;

  return (
    <>
      <div className="stats" role="group" aria-label="Filter by status">
        <button type="button" className={"stat all" + (status === "" ? " on" : "")} onClick={() => setStatus("")}>
          <span className="stat-num">{bookings.length}</span><span className="stat-label">All bookings</span>
        </button>
        {STATUSES.map((s) => (
          <button key={s} type="button" className={"stat " + s + (status === s ? " on" : "")}
                  aria-pressed={status === s} onClick={() => setStatus(status === s ? "" : s)}>
            <span className="stat-num">{counts[s]}</span>
            <span className="stat-label">{s.charAt(0) + s.slice(1).toLowerCase()}</span>
          </button>
        ))}
      </div>

      <div className="toolbar">
        <input id="search" type="search" value={search} onChange={(e) => setSearch(e.target.value)}
               placeholder="Search reference, passenger, hotel or flight" aria-label="Search bookings" />
        <span className="count" id="bookingCount">{shown.length} shown</span>
        <div className="spacer" />
        {canEdit && (
          <>
            <button type="button" className="btn ghost" id="resetData" onClick={() => setDialog({ kind: "reset" })}>
              Reset demo data
            </button>
            <button type="button" className="btn primary" id="addBooking" onClick={() => setDialog({ kind: "add" })}>
              + Add booking
            </button>
          </>
        )}
      </div>

      {!canEdit && <p className="hint">View only. Enter the staff key in the top bar to add, edit or delete.</p>}

      <div className="table-wrap">
        <table id="bookingsTable">
          <thead>
            <tr>{["Ref", "Passenger", "Hotel", "Night", "Status", "Pickup", "Onward flight", ""].map((h) => <th key={h}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {shown.map((b) => (
              <tr key={b.ref} data-ref={b.ref}
                  className={[b.ref === activeRef ? "active" : "", b.ref === flash ? "flash" : ""].join(" ").trim()}>
                <td className="ref">{b.ref}</td>
                <td>{b.passenger}</td>
                <td>{b.hotel}</td>
                <td className="num">{b.night}</td>
                <td><StatusPill status={b.status} /></td>
                <td className="num">{b.pickup_time || "—"}</td>
                <td className="muted">{b.onward_flight}</td>
                <td className="actions">
                  {canEdit && (
                    <>
                      <button type="button" className="btn small ghost" onClick={() => setDialog({ kind: "edit", booking: b })}>Edit</button>{" "}
                      <button type="button" className="btn small ghost danger-text" onClick={() => setDialog({ kind: "delete", booking: b })}>Delete</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length === 0 && (
          <div className="empty">
            <p>No bookings match.</p>
            {(search || status) && <button type="button" className="btn ghost small" onClick={() => { setSearch(""); setStatus(""); }}>Clear filters</button>}
          </div>
        )}
      </div>

      {(dialog?.kind === "add" || dialog?.kind === "edit") && (
        <BookingDialog
          initial={dialog.kind === "edit" ? dialog.booking : undefined}
          hotels={hotels}
          staffKey={staffKey}
          onClose={() => setDialog(null)}
          onSaved={(saved) => {
            notify(`${saved.ref} saved`);
            setDialog(null);
            highlight(saved.ref);
            onChanged();
          }}
        />
      )}
      {dialog?.kind === "delete" && (
        <ConfirmDialog
          title={`Delete ${dialog.booking.ref}?`}
          message={<>This removes <b>{dialog.booking.passenger}</b>'s booking at {dialog.booking.hotel} for {dialog.booking.night}. The agent will no longer find it.</>}
          confirmLabel="Delete booking"
          busy={busy}
          onConfirm={() => remove(dialog.booking)}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "reset" && (
        <ConfirmDialog
          title="Reset the demo data?"
          message="All bookings and hotels go back to the original 20 bookings and 5 hotels. Your changes will be lost. Conversations are kept."
          confirmLabel="Reset data"
          busy={busy}
          onConfirm={reset}
          onClose={() => setDialog(null)}
        />
      )}
    </>
  );
}
