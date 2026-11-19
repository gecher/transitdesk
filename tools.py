from langchain_core.tools import tool

from db import query


@tool
def get_booking(booking_ref: str) -> dict | str:
    """Look up a transit-hotel booking by its reference, for example ET-5520.
    Returns passenger, hotel, night, status, pickup time and onward flight."""
    rows = query("SELECT * FROM bookings WHERE ref = ?", (booking_ref.strip().upper(),))
    return rows[0] if rows else f"No booking found with reference {booking_ref}."


@tool
def get_hotel_info(hotel_name: str) -> dict | str:
    """Get the location, airport shuttle details and phone number of a partner hotel."""
    rows = query("SELECT * FROM hotels WHERE name LIKE ?", (f"%{hotel_name.strip()}%",))
    return rows[0] if rows else f"No partner hotel named {hotel_name}."


TOOLS = [get_booking, get_hotel_info]