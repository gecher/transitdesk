import { useCallback, useEffect, useState, type ChangeEvent } from "react";
import { api, ApiError } from "../api";
import type { Notify } from "../hooks";
import { STATUSES, type Booking, type Hotel, type Status } from "../types";
import { ConfirmButton, Locked, StatusPill } from "./common";

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

function BookingForm({ initial, isNew, hotels, onSave, onCancel }: {
  initial?: Booking;
  isNew: boolean;
  hotels: Hotel[];
  onSave: (d: Draft) => void;
  onCancel: () => void;
}) {
  const [d, setD] = useState<Draft>({
    ref: initial?.ref ?? "",
    passenger: initial?.passenger ?? "",
    hotel: initial?.hotel ?? hotels[0]?.name ?? "",
    night: initial?.night ?? "",
    status: initial?.status ?? "CONFIRMED",
    pickup_time: initial?.pickup_time ?? "",
    onward_flight: initial?.onward_flight ?? "",
  });
  const set = (key: keyof Draft) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setD({ ...d, [key]: e.target.value });

  return (
    <tr data-ref={initial?.ref ?? ""}>
      <td className="ref">
        {isNew ? <input name="ref" value={d.ref} onChange={set("ref")} placeholder="ET-3005" aria-label="Reference" /> : d.ref}
      </td>
      <td><input name="passenger" value={d.passenger} onChange={set("passenger")} aria-label="Passenger" /></td>
      <td>
        <select name="hotel" value={d.hotel} onChange={set("hotel")} aria-label="Hotel">
          {hotels.map((h) => <option key={h.name}>{h.name}</option>)}
        </select>
      </td>
      <td><input name="night" type="date" value={d.night} onChange={set("night")} aria-label="Night" /></td>
      <td>
        <select name="status" value={d.status} onChange={set("status")} aria-label="Status">
          {STATUSES.map((s) => <option key={s}>{s}</option>)}
        </select>
      </td>
      <td><input name="pickup_time" type="time" value={d.pickup_time} onChange={set("pickup_time")} aria-label="Pickup time" /></td>
      <td><input name="onward_flight" value={d.onward_flight} onChange={set("onward_flight")} aria-label="Onward flight" /></td>
      <td className="actions">
        <button type="button" className="btn small ok" onClick={() => onSave(d)}>Save</button>{" "}
        <button type="button" className="btn small ghost" onClick={onCancel}>Cancel</button>
      </td>
    </tr>
  );
}

export function Bookings({ staffKey, canRead, activeRef, version, notify, onChanged }: Props) {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [hotels, setHotels] = useState<Hotel[]>([]);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
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
      const params = new URLSearchParams({ q: query, status });
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
  }, [canRead, query, status, staffKey, notify]);

  useEffect(() => {
    void load();
  }, [load, version]);

  async function save(d: Draft, isNew: boolean) {
    try {
      const body = { ...d, ref: d.ref.trim(), pickup_time: d.pickup_time || null };
      const saved = await api<Booking>(isNew ? "/api/bookings" : `/api/bookings/${d.ref}`, staffKey, {
        method: isNew ? "POST" : "PUT",
        body: JSON.stringify(body),
      });
      setEditing(null);
      setAdding(false);
      notify(`${saved.ref} saved`);
      setFlash(saved.ref);
      window.setTimeout(() => setFlash(null), 1700);
      onChanged();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Could not save", true);
    }
  }

  async function remove(ref: string) {
    try {
      await api(`/api/bookings/${ref}`, staffKey, { method: "DELETE" });
      notify(`${ref} deleted`);
      onChanged();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Could not delete", true);
    }
  }

  async function reset() {
    try {
      await api("/api/reset", staffKey, { method: "POST" });
      notify("Demo data restored");
      onChanged();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Could not reset", true);
    }
  }

  return (
    <>
      <div className="toolbar">
        <input id="search" type="search" value={search} onChange={(e) => setSearch(e.target.value)}
               placeholder="Search ref, passenger, hotel, flight" aria-label="Search bookings" />
        <select id="statusFilter" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s}>{s}</option>)}
        </select>
        <span className="count" id="bookingCount">
          {canRead && !locked ? `${bookings.length} booking${bookings.length === 1 ? "" : "s"}` : ""}
        </span>
        <div className="spacer" />
        {canEdit && (
          <>
            <ConfirmButton label="Reset demo data" confirmLabel="Click again to reset" onConfirm={reset}
                           className="btn ghost" armedClassName="btn danger" />
            <button type="button" className="btn" id="addBooking"
                    onClick={() => { setAdding(true); setEditing(null); }}>
              Add booking
            </button>
          </>
        )}
      </div>

      {!canRead || locked ? (
        <Locked />
      ) : (
        <>
          {!canEdit && <p className="hint">View only. Enter the staff key in the yellow bar to edit.</p>}
          <table id="bookingsTable">
            <thead>
              <tr>
                {["Ref", "Passenger", "Hotel", "Night", "Status", "Pickup", "Onward flight", ""].map((h) => <th key={h}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {adding && (
                <BookingForm isNew hotels={hotels} onSave={(d) => save(d, true)} onCancel={() => setAdding(false)} />
              )}
              {bookings.map((b) =>
                editing === b.ref ? (
                  <BookingForm key={b.ref} initial={b} isNew={false} hotels={hotels}
                               onSave={(d) => save(d, false)} onCancel={() => setEditing(null)} />
                ) : (
                  <tr key={b.ref} data-ref={b.ref}
                      className={[b.ref === activeRef ? "active" : "", b.ref === flash ? "flash" : ""].join(" ").trim()}>
                    <td className="ref">{b.ref}</td>
                    <td>{b.passenger}</td>
                    <td>{b.hotel}</td>
                    <td className="num">{b.night}</td>
                    <td><StatusPill status={b.status} /></td>
                    <td className="num">{b.pickup_time || "—"}</td>
                    <td>{b.onward_flight}</td>
                    <td className="actions">
                      {canEdit && (
                        <>
                          <button type="button" className="btn small ghost"
                                  onClick={() => { setEditing(b.ref); setAdding(false); }}>
                            Edit
                          </button>{" "}
                          <ConfirmButton label="Delete" confirmLabel="Confirm delete" onConfirm={() => remove(b.ref)} />
                        </>
                      )}
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </>
      )}
    </>
  );
}
