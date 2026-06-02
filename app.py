import re
from pathlib import Path
from typing import Optional

import streamlit as st


M73_RE = re.compile(r"\bM73\b.*?\bR(\d+)\b")
M600_RE = re.compile(r"^\s*M600\b", re.IGNORECASE)
COLOR_RE = re.compile(r"\bCOLOR=([#A-Fa-f0-9]+)")
NEXT_RE = re.compile(r"\bNEXT=([0-9-]+)")


def fmt_minutes(minutes: Optional[int]) -> str:
    if minutes is None or minutes < 0:
        return "?"
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours} h {mins} min"
    if hours:
        return f"{hours} h"
    return f"{mins} min"


def parse_gcode_text(text: str):
    lines = text.splitlines()

    total_remaining: Optional[int] = None
    last_remaining: Optional[int] = None
    events = []

    for idx, line in enumerate(lines):
        m73 = M73_RE.search(line)
        if m73:
            last_remaining = int(m73.group(1))
            if total_remaining is None:
                total_remaining = last_remaining

        if M600_RE.search(line):
            color = COLOR_RE.search(line)
            nxt = NEXT_RE.search(line)

            events.append(
                {
                    "line_index": idx,
                    "line_number": idx + 1,
                    "line": line,
                    "remaining": last_remaining,
                    "color": color.group(1) if color else "",
                    "next": nxt.group(1) if nxt else "",
                }
            )

    if total_remaining is None:
        raise ValueError("V souboru jsem nenašel M73 R... časové údaje. Bez nich nejde spolehlivě spočítat časy.")

    prev_elapsed = 0
    for i, e in enumerate(events):
        if e["remaining"] is None:
            e["elapsed"] = None
            e["interval_from_prev"] = None
        else:
            e["elapsed"] = total_remaining - e["remaining"]
            e["interval_from_prev"] = e["elapsed"] - prev_elapsed
            prev_elapsed = e["elapsed"]

        if i + 1 < len(events) and e["remaining"] is not None and events[i + 1]["remaining"] is not None:
            e["next_change_min"] = e["remaining"] - events[i + 1]["remaining"]
        else:
            e["next_change_min"] = -1

    return lines, total_remaining, events


def make_modified_gcode(lines: list[str], events: list[dict]) -> str:
    out_lines = list(lines)

    for e in events:
        idx = e["line_index"]
        line = out_lines[idx]

        # Pokud už tam NEXT_CHANGE_MIN je, přepiš ho.
        line = re.sub(r"\s+NEXT_CHANGE_MIN=-?\d+", "", line)
        line = f"{line} NEXT_CHANGE_MIN={e['next_change_min']}"
        out_lines[idx] = line

    return "\n".join(out_lines) + "\n"


def color_preview(hex_color: str) -> str:
    if not hex_color:
        return ""
    if not hex_color.startswith("#"):
        hex_color = "#" + hex_color
    return f'<span style="display:inline-block;width:18px;height:18px;background:{hex_color};border:1px solid #888;border-radius:4px;vertical-align:middle;"></span> {hex_color}'


st.set_page_config(
    page_title="M600 G-code intervaly",
    page_icon="🧵",
    layout="wide",
)

st.title("🧵 M600 G-code intervaly")
st.caption("Nahraj G-code z OrcaSliceru. Appka spočítá intervaly mezi výměnami filamentu a umí doplnit NEXT_CHANGE_MIN do M600.")

uploaded = st.file_uploader("Nahraj .gcode soubor", type=["gcode", "gco", "txt"])

if uploaded is None:
    st.info("Nahraj G-code soubor a hned uvidíš intervaly výměn.")
    st.stop()

raw = uploaded.read()
try:
    text = raw.decode("utf-8", errors="replace")
except Exception:
    st.error("Soubor se nepodařilo přečíst jako text.")
    st.stop()

try:
    lines, total_remaining, events = parse_gcode_text(text)
except ValueError as e:
    st.error(str(e))
    st.stop()

st.subheader("Souhrn")

col1, col2, col3 = st.columns(3)
col1.metric("Celkový odhad", fmt_minutes(total_remaining))
col2.metric("Počet M600 výměn", len(events))
col3.metric("Počet řádků", len(lines))

if not events:
    st.warning("V souboru jsem nenašel žádné M600 výměny.")
    st.stop()

st.subheader("Intervaly výměn")

rows = []
for i, e in enumerate(events, start=1):
    label = "Start → 1. výměna" if i == 1 else f"{i-1}. → {i}. výměna"
    rows.append(
        {
            "Úsek": label,
            "Interval": fmt_minutes(e["interval_from_prev"]),
            "Minuty": e["interval_from_prev"],
            "Řádek": e["line_number"],
            "NEXT": e["next"],
            "Barva": e["color"],
            "Další výměna za": "poslední výměna" if e["next_change_min"] < 0 else fmt_minutes(e["next_change_min"]),
            "NEXT_CHANGE_MIN": e["next_change_min"],
        }
    )

# Poslední úsek do konce
last = events[-1]
rows.append(
    {
        "Úsek": f"{len(events)}. výměna → konec",
        "Interval": fmt_minutes(last["remaining"]),
        "Minuty": last["remaining"],
        "Řádek": "",
        "NEXT": "",
        "Barva": "",
        "Další výměna za": "",
        "NEXT_CHANGE_MIN": "",
    }
)

def color_cell(hex_color: str) -> str:
    if not hex_color:
        return ""

    color = hex_color if hex_color.startswith("#") else f"#{hex_color}"

    return (
        f'<span style="display:inline-block;width:18px;height:18px;'
        f'background:{color};border:1px solid #888;border-radius:4px;'
        f'vertical-align:middle;margin-right:8px;"></span>'
        f'<code>{color}</code>'
    )


table_html = """
<table style="width:100%; border-collapse:collapse;">
  <thead>
    <tr>
      <th style="text-align:left; padding:8px; border-bottom:1px solid #ddd;">Úsek</th>
      <th style="text-align:left; padding:8px; border-bottom:1px solid #ddd;">Interval</th>
      <th style="text-align:left; padding:8px; border-bottom:1px solid #ddd;">Minuty</th>
      <th style="text-align:left; padding:8px; border-bottom:1px solid #ddd;">Řádek</th>
      <th style="text-align:left; padding:8px; border-bottom:1px solid #ddd;">NEXT</th>
      <th style="text-align:left; padding:8px; border-bottom:1px solid #ddd;">Barva</th>
      <th style="text-align:left; padding:8px; border-bottom:1px solid #ddd;">Další výměna za</th>
      <th style="text-align:left; padding:8px; border-bottom:1px solid #ddd;">NEXT_CHANGE_MIN</th>
    </tr>
  </thead>
  <tbody>
"""

for row in rows:
    table_html += f"""
    <tr>
      <td style="padding:8px; border-bottom:1px solid #eee;">{row["Úsek"]}</td>
      <td style="padding:8px; border-bottom:1px solid #eee;">{row["Interval"]}</td>
      <td style="padding:8px; border-bottom:1px solid #eee;">{row["Minuty"]}</td>
      <td style="padding:8px; border-bottom:1px solid #eee;">{row["Řádek"]}</td>
      <td style="padding:8px; border-bottom:1px solid #eee;">{row["NEXT"]}</td>
      <td style="padding:8px; border-bottom:1px solid #eee;">{color_cell(row["Barva"])}</td>
      <td style="padding:8px; border-bottom:1px solid #eee;">{row["Další výměna za"]}</td>
      <td style="padding:8px; border-bottom:1px solid #eee;">{row["NEXT_CHANGE_MIN"]}</td>
    </tr>
    """

table_html += """
  </tbody>
</table>
"""

st.markdown(table_html, unsafe_allow_html=True)

st.subheader("M600 řádky")

for i, e in enumerate(events, start=1):
    with st.expander(f"{i}. výměna — řádek {e['line_number']} — {e['color'] or 'bez barvy'}"):
        if e["color"]:
            st.markdown(color_preview(e["color"]), unsafe_allow_html=True)
        st.code(e["line"], language="gcode")
        if e["next_change_min"] > 0:
            st.write(f"Další výměna: **za {fmt_minutes(e['next_change_min'])}**")
        else:
            st.write("Toto je poslední výměna filamentu.")

st.subheader("Export upraveného G-code")

modified = make_modified_gcode(lines, events)
original_name = Path(uploaded.name)
new_name = f"{original_name.stem}_nextchange{original_name.suffix or '.gcode'}"

st.download_button(
    label="Stáhnout G-code s NEXT_CHANGE_MIN",
    data=modified.encode("utf-8"),
    file_name=new_name,
    mime="text/plain",
)

st.caption("Poznámka: výpočet používá M73 R... hodnoty z OrcaSliceru, tedy odhad zbývajícího času ve chvíli M600.")
