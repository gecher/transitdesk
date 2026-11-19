import { useCallback, useEffect, useState, type ChangeEvent } from "react";
import { api, ApiError } from "../api";
import type { Notify } from "../hooks";
import type { Hotel } from "../types";
import { ConfirmButton, Locked } from "./common";

interface Props {
  staffKey: string;
  canRead: boolean;
  version: number;
  notify: Notify;
  onChanged: () => void;
}

function HotelForm({ initial, onSave, onCancel }: {
  initial?: Hotel;
  onSave: (h: Hotel) => void;
  onCancel: () => void;
}) {
  const [h, setH] = useState<Hotel>({
    name: initial?.name ?? "",
    location: initial?.location ?? "",
    shuttle: initial?.shuttle ?? "",
    phone: initial?.phone ?? "",
  });
  const set = (key: keyof Hotel) => (e: ChangeEvent<HTMLInputElement>) => setH({ ...h, [key]: e.target.value });
  return (
    <tr>
      <td className="ref">{initial ? h.name : <input name="name" value={h.name} onChange={set("name")} aria-label="Hotel name" />}</td>
      <td><input name="location" value={h.location} onChange={set("location")} aria-label="Location" /></td>
      <td><input name="shuttle" value={h.shuttle} onChange={set("shuttle")} aria-label="Getting there" /></td>
      <td><input name="phone" value={h.phone} onChange={set("phone")} aria-label="Phone" /></td>
      <td className="num">{initial?.bookings ?? ""}</td>
      <td className="actions">
        <button type="button" className="btn small ok" onClick={() => onSave(h)}>Save</button>{" "}
        <button type="button" className="btn small ghost" onClick={onCancel}>Cancel</button>
      </td>
    </tr>
  );
}

export function Hotels({ staffKey, canRead, version, notify, onChanged }: Props) {
  const [hotels, setHotels] = useState<Hotel[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
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

  async function save(h: Hotel, isNew: boolean) {
    try {
      const { name, location, shuttle, phone } = h;
      await api(isNew ? "/api/hotels" : `/api/hotels/${encodeURIComponent(name)}`, staffKey, {
        method: isNew ? "POST" : "PUT",
        body: JSON.stringify({ name, location, shuttle, phone }),
      });
      setEditing(null);
      setAdding(false);
      notify("Hotel saved");
      onChanged();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Could not save", true);
    }
  }

  async function remove(name: string) {
    try {
      await api(`/api/hotels/${encodeURIComponent(name)}`, staffKey, { method: "DELETE" });
      notify(`${name} deleted`);
      onChanged();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Could not delete", true);
    }
  }

  if (!canRead || locked) return <Locked />;
  return (
    <>
      <div className="toolbar">
        <span className="count" id="hotelCount">{hotels.length} partner hotels</span>
        <div className="spacer" />
        {canEdit && (
          <button type="button" className="btn" id="addHotel" onClick={() => setAdding(true)}>Add hotel</button>
        )}
      </div>
      <table id="hotelsTable">
        <thead>
          <tr>{["Hotel", "Location", "Getting there", "Phone", "Bookings", ""].map((x) => <th key={x}>{x}</th>)}</tr>
        </thead>
        <tbody>
          {adding && <HotelForm onSave={(h) => save(h, true)} onCancel={() => setAdding(false)} />}
          {hotels.map((h) =>
            editing === h.name ? (
              <HotelForm key={h.name} initial={h} onSave={(x) => save(x, false)} onCancel={() => setEditing(null)} />
            ) : (
              <tr key={h.name}>
                <td className="ref">{h.name}</td>
                <td>{h.location}</td>
                <td>{h.shuttle}</td>
                <td className="num">{h.phone}</td>
                <td className="num">{h.bookings}</td>
                <td className="actions">
                  {canEdit && (
                    <>
                      <button type="button" className="btn small ghost" onClick={() => setEditing(h.name)}>Edit</button>{" "}
                      <ConfirmButton label="Delete" confirmLabel="Confirm delete" onConfirm={() => remove(h.name)} />
                    </>
                  )}
                </td>
              </tr>
            ),
          )}
        </tbody>
      </table>
    </>
  );
}
